"""Authenticated knowledge-base operations; ingestion runs off the HTTP thread."""
import hmac
import logging
import os
from pathlib import Path
import secrets
import threading
import time

SUPPORTED = {'.pdf', '.docx', '.pptx', '.html'}
MAX_UPLOAD = 25 * 1024 * 1024


class AdminManager:
    def __init__(self, retriever=None, docs_dir=None, ingester_factory=None):
        self.docs = Path(docs_dir or os.getenv('DOCS_DIR', './docs')).resolve()
        self.retriever = retriever
        self.factory = ingester_factory
        self.lock = threading.Lock()
        self.sessions = {}
        self.failures = []
        self.job = {'state': 'idle', 'message': 'Ready.'}

    def login(self, pin):
        with self.lock:
            now = time.monotonic()
            self.failures = [t for t in self.failures if now - t < 60]
            if len(self.failures) >= 5:
                raise PermissionError('Too many attempts. Wait one minute and retry.')
            if not isinstance(pin, str) or not hmac.compare_digest(pin.encode(), os.getenv('ADMIN_PIN', '123456').encode()):
                self.failures.append(now)
                raise PermissionError('Incorrect administrator PIN.')
            self.sessions = {token: expiry for token, expiry in self.sessions.items() if expiry > now}
            token = secrets.token_urlsafe(32)
            self.sessions[token] = now + 1800
            return token

    def authorized(self, token):
        with self.lock:
            return self.sessions.get(token, 0) > time.monotonic()

    def logout(self, token):
        with self.lock:
            self.sessions.pop(token, None)

    def path(self, name):
        if (not isinstance(name, str) or not name or '\\' in name
                or any(part in ('', '.', '..') for part in name.split('/'))):
            raise ValueError('Invalid filename.')
        path = self.docs / name
        if not path.resolve().is_relative_to(self.docs) or path.is_symlink() or path.suffix.lower() not in SUPPORTED:
            raise ValueError('Use a PDF, DOCX, PPTX, or HTML file inside the documents folder.')
        return path

    def snapshot(self):
        with self.lock:
            files = []
            if self.docs.exists():
                for path in sorted(self.docs.rglob('*')):
                    if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(self.docs) and path.suffix.lower() in SUPPORTED:
                        stat = path.stat()
                        files.append({'name': path.relative_to(self.docs).as_posix(), 'size': stat.st_size})
            return {'files': files, 'job': dict(self.job)}

    def upload(self, name, data):
        if '/' in name:
            raise ValueError('Upload a filename without folders.')
        path = self.path(name)
        if not data or len(data) > MAX_UPLOAD:
            raise ValueError('Files must contain 1 byte to 25 MB.')
        with self.lock:
            if self.job['state'] == 'running':
                raise ValueError('Wait for the current operation to finish.')
            self.docs.mkdir(parents=True, exist_ok=True)
            try:
                with path.open('xb') as output:
                    output.write(data)
            except FileExistsError:
                raise ValueError('A file with that name already exists. Remove it first or rename the upload.') from None

    def start(self, action, generation_lock, name=None):
        with self.lock:
            if self.job['state'] == 'running' or not generation_lock.acquire(blocking=False):
                raise ValueError('The assistant or knowledge base is busy. Try again shortly.')
            self.job = {'state': 'running', 'message': f'{action.capitalize()} in progress…'}
        def work():
            try:
                if self.factory:
                    ingester = self.factory()
                else:
                    from ingest import Ingester
                    ingester = Ingester()
                if action == 'remove':
                    path = self.path(name)
                    if not path.is_file():
                        raise ValueError('File no longer exists.')
                    ingester.collection.delete(where={'source': path.name})
                    ingester.state.pop(str(path.resolve()), None)
                    path.unlink()
                else:
                    if action == 'reset':
                        ids = ingester.collection.get(include=[])['ids']
                        if ids:
                            ingester.collection.delete(ids=ids)
                        ingester.state.clear()
                    # Verify state after each file: conversion failures return False too.
                    from ingest import file_hash
                    for path in sorted(self.docs.rglob('*')):
                        if path.is_file() and not path.is_symlink() and path.suffix.lower() in SUPPORTED:
                            ingester.ingest_file(path)
                            if ingester.state.get(str(path.resolve())) != file_hash(path):
                                raise ValueError(f'Could not ingest {path.name}. Check the backend logs.')
                message = 'File removed from documents and search.' if action == 'remove' else 'Ingestion complete. Search is up to date.'
                state = 'succeeded'
            except Exception:
                logging.exception('Knowledge-base operation failed')
                state, message = 'failed', 'Operation failed; some changes may have been applied. Check backend logs and retry ingestion.'
            finally:
                try:
                    if 'ingester' in locals():
                        from ingest import save_state
                        save_state(ingester.state, ingester.index_dir)
                    if self.retriever is not None:
                        self.retriever._build_bm25_index()
                except Exception:
                    logging.exception('Could not refresh knowledge base')
                    state, message = 'failed', 'Search refresh failed. Restart the backend before using chat.'
                with self.lock:
                    self.job = {'state': state, 'message': message}
                generation_lock.release()
        threading.Thread(target=work, daemon=True).start()
