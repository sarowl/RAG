"""Local HTTP adapter for the kiosk RAG pipeline. Run from the project root."""

import argparse
import base64
import io
import os
from pathlib import Path
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import sqlite3
import threading
from urllib.parse import urlsplit, parse_qs
from admin_manager import AdminManager, MAX_UPLOAD

MAX_BODY = 128 * 1024
MAX_TEXT = 12000
MAX_HISTORY = 5
MAX_AUDIO_BODY = 30 * 96000 * 2 + 44
log = logging.getLogger(__name__)


def validate_request(data):
    if not isinstance(data, dict):
        raise ValueError('Expected a JSON object.')
    question = data.get('question')
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_TEXT:
        raise ValueError('Question must contain 1–12000 characters.')
    history = data.get('history', [])
    if not isinstance(history, list) or len(history) > MAX_HISTORY:
        raise ValueError('History must contain at most five exchanges.')
    for pair in history:
        if (not isinstance(pair, list) or len(pair) != 2
                or any(not isinstance(text, str) or len(text) > MAX_TEXT for text in pair)):
            raise ValueError('Each history exchange must contain two text strings.')
    return {'question': question.strip(), 'chat_history': history}


def load_speech(model_path):
    from piper import PiperVoice
    voice = PiperVoice.load(str(model_path))

    def synthesize(answer):
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            voice.synthesize_wav(answer, wav)
        return output.getvalue()

    return synthesize


def create_server(address, chain, storage, speech=None, stt=None, admin=None):
    # Protect the shared reranker and avoid concurrent generations on the kiosk.
    generation_lock = threading.Lock()
    admin = admin if admin is not None else AdminManager()
    from stt import VoskSTT
    transcriber = stt if stt is not None else VoskSTT()
    transcription_lock = threading.Lock()

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
                pass  # The browser stopped waiting for this answer.

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
                return
            if self.path == '/api/health':
                self.respond(200, {'status': 'ready', 'tts_enabled': speech is not None})
            else:
                self.respond(404, {'error': 'Not found.'})

        def do_POST(self):
            if self.path.startswith('/api/admin/'):
                self.admin_request()
                return
            if self.path == '/api/stt':
                self.transcribe()
                return
            if self.path != '/api/chat':
                self.respond(404, {'error': 'Not found.'})
                return
            if self.headers.get_content_type() != 'application/json':
                self.respond(415, {'error': 'Use application/json.'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0 or length > MAX_BODY:
                    self.respond(413, {'error': 'Request body is empty or too large.'})
                    return
                self.connection.settimeout(15)
                inputs = validate_request(json.loads(self.rfile.read(length)))
            except (ValueError, UnicodeDecodeError, OSError) as exc:
                self.respond(400, {'error': str(exc)})
                return
            if not generation_lock.acquire(blocking=False):
                self.respond(503, {'error': 'The assistant is busy. Please try again shortly.'})
                return
            try:
                result = chain.invoke(inputs)
                sources = []
                for doc in result.get('source_documents', []):
                    source = {key: doc.metadata.get(key) for key in ('source', 'page', 'headings')}
                    if source not in sources:
                        sources.append(source)
                saved = True
                try:
                    storage.save(inputs['question'], result['answer'], result.get('tps'), result.get('ttft'))
                except sqlite3.Error:
                    saved = False
                    log.exception('Could not persist exchange')
                payload = {'answer': result['answer'], 'sources': sources,
                           'tps': result.get('tps'), 'ttft': result.get('ttft'), 'saved': saved,
                           'tts_enabled': speech is not None}
                if speech is not None:
                    try:
                        payload['audio'] = 'data:audio/wav;base64,' + base64.b64encode(speech(result['answer'])).decode('ascii')
                    except Exception:
                        log.exception('Speech synthesis failed')
                        payload['audio_error'] = 'Speech is unavailable. You can still read the answer.'
                self.respond(200, payload)
            except Exception:
                log.exception('RAG request failed')
                self.respond(503, {'error': 'Unable to answer. Check Ollama and the knowledge base, then retry.'})
            finally:
                generation_lock.release()

        def transcribe(self):
            if self.headers.get_content_type() != 'audio/wav':
                self.respond(415, {'error': 'Use audio/wav.'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 44 < length <= MAX_AUDIO_BODY:
                    self.respond(413, {'error': 'Audio is empty or too large (maximum 30 seconds).'})
                    return
                self.connection.settimeout(15)
                data = self.rfile.read(length)
                if len(data) != length:
                    raise ValueError('Incomplete audio upload.')
            except (ValueError, OSError) as exc:
                self.respond(400, {'error': str(exc)})
                return
            if not transcription_lock.acquire(blocking=False):
                self.respond(503, {'error': 'Voice input is busy. Please try again shortly.'})
                return
            try:
                self.respond(200, {'text': transcriber.transcribe_wav(data)})
            except ValueError as exc:
                self.respond(400, {'error': str(exc)})
            except Exception:
                log.exception('Speech recognition failed')
                self.respond(503, {'error': 'Voice input is unavailable. Check the backend Vosk model and requirements_stt.txt installation.'})
            finally:
                transcription_lock.release()

    return ThreadingHTTPServer(address, Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--tts', action='store_true', help='Generate Piper audio for browser answers')
    parser.add_argument('--tts-model', default=os.getenv('PIPER_MODEL', str(Path(__file__).resolve().parent / 'voices/en_US-lessac-medium.onnx')), help='Piper ONNX voice path (used with --tts)')
    args = parser.parse_args()
    speech = None
    if args.tts:
        try:
            speech = load_speech(Path(args.tts_model).expanduser())
        except Exception as exc:
            parser.error(f'Cannot enable TTS: {exc}')
    from aichatbot import CHAT_DB_PATH, init_chatbot
    from chat_storage import ChatStorage
    chain, retriever = init_chatbot()
    with create_server((args.host, args.port), chain, ChatStorage(CHAT_DB_PATH), speech=speech, admin=AdminManager(retriever)) as server:
        print(f'RAG API ready at http://{args.host}:{args.port}', flush=True)
        print(f'Browser speech: {"on" if speech else "off"}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
