"""Local HTTP adapter for the kiosk RAG pipeline. Run from the project root."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import sqlite3
import threading

MAX_BODY = 128 * 1024
MAX_TEXT = 12000
MAX_HISTORY = 5
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


def create_server(address, chain, storage):
    # Protect the shared reranker and avoid concurrent generations on the kiosk.
    generation_lock = threading.Lock()

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

        def do_GET(self):
            if self.path == '/api/health':
                self.respond(200, {'status': 'ready'})
            else:
                self.respond(404, {'error': 'Not found.'})

        def do_POST(self):
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
                self.respond(200, {'answer': result['answer'], 'sources': sources,
                                   'tps': result.get('tps'), 'ttft': result.get('ttft'), 'saved': saved})
            except Exception:
                log.exception('RAG request failed')
                self.respond(503, {'error': 'Unable to answer. Check Ollama and the knowledge base, then retry.'})
            finally:
                generation_lock.release()

    return ThreadingHTTPServer(address, Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    from aichatbot import CHAT_DB_PATH, init_chatbot
    from chat_storage import ChatStorage
    chain, _ = init_chatbot()
    with create_server((args.host, args.port), chain, ChatStorage(CHAT_DB_PATH)) as server:
        print(f'RAG API ready at http://{args.host}:{args.port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
