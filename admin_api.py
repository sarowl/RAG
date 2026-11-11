"""Authenticated API for knowledge-base administration and chat history."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import sqlite3
import threading
from urllib.parse import parse_qs, urlsplit

from admin_manager import AdminManager, MAX_UPLOAD

MAX_BODY = 128 * 1024
log = logging.getLogger(__name__)


def create_server(address, storage, admin=None, generation_lock=None):
    admin = admin if admin is not None else AdminManager()
    generation_lock = generation_lock if generation_lock is not None else threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status, payload):
            body = json.dumps(payload).encode('utf-8')
            try:
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def admin_request(self):
            route = urlsplit(self.path)
            token = self.headers.get('Authorization', '').removeprefix('Bearer ')
            try:
                if route.path != '/api/admin/login' and not admin.authorized(token):
                    self.respond(401, {'error': 'Administrator session expired. Enter your PIN again.'})
                    return
                if self.command == 'GET' and route.path == '/api/admin/files':
                    self.respond(200, admin.snapshot())
                    return
                if self.command == 'GET' and route.path == '/api/admin/history':
                    try:
                        limit = int(parse_qs(route.query).get('limit', ['500'])[0])
                    except ValueError:
                        raise ValueError('History limit must be a number.') from None
                    self.respond(200, {'records': storage.list_recent(limit)})
                    return
                if self.command != 'POST':
                    self.respond(404, {'error': 'Not found.'})
                    return
                length = int(self.headers.get('Content-Length', '0'))
                limit = MAX_UPLOAD if route.path == '/api/admin/upload' else MAX_BODY
                if not 0 < length <= limit:
                    self.respond(413, {'error': 'Empty or oversized request (uploads: maximum 25 MB).'})
                    return
                self.connection.settimeout(30)
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError('Incomplete upload.')
                if route.path == '/api/admin/upload':
                    name = parse_qs(route.query).get('name', [''])[0]
                    admin.upload(name, body)
                    self.respond(201, {'message': 'Uploaded. Run ingestion to make this file searchable.'})
                    return
                data = json.loads(body)
                if not isinstance(data, dict):
                    raise ValueError('Expected a JSON object.')
                if route.path == '/api/admin/login':
                    self.respond(200, {'token': admin.login(data.get('pin'))})
                elif route.path == '/api/admin/logout':
                    admin.logout(token)
                    self.respond(200, {'message': 'Signed out.'})
                elif route.path in ('/api/admin/ingest', '/api/admin/reset', '/api/admin/remove'):
                    action = route.path.rsplit('/', 1)[-1]
                    if action == 'remove':
                        admin.path(data.get('name'))
                    admin.start(action, generation_lock, data.get('name'))
                    self.respond(202, {'message': 'Operation started.'})
                else:
                    self.respond(404, {'error': 'Not found.'})
            except PermissionError as exc:
                self.respond(401, {'error': str(exc)})
            except (ValueError, OSError) as exc:
                self.respond(400, {'error': str(exc)})
            except Exception:
                log.exception('Admin request failed')
                self.respond(500, {'error': 'Knowledge-base operation unavailable. Check backend logs.'})

        def do_GET(self):
            if self.path.startswith('/api/admin/'):
                self.admin_request()
            elif self.path == '/api/health':
                self.respond(200, {'status': 'ready', 'service': 'admin'})
            else:
                self.respond(404, {'error': 'Not found.'})

        def do_POST(self):
            if self.path.startswith('/api/admin/'):
                self.admin_request()
            else:
                self.respond(404, {'error': 'Not found.'})

    return ThreadingHTTPServer(address, Handler)