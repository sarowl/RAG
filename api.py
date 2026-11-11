"""Local HTTP adapter for the kiosk RAG pipeline. Run from the project root."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import sqlite3
import threading
from admin_manager import AdminManager
from admin_api import create_server as create_admin_server

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


def create_server(address, chain, storage, generation_lock=None):
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
                pass  # The browser stopped waiting for this answer.

        def do_GET(self):
            if self.path == '/api/health':
                self.respond(200, {'status': 'ready', 'service': 'rag'})
            else:
                self.respond(404, {'error': 'Not found.'})

        def do_POST(self):
            if self.path == '/api/feedback':
                self.save_feedback()
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
                    message_id = storage.save(inputs['question'], result['answer'], result.get('tps'), result.get('ttft'))
                except sqlite3.Error:
                    saved = False
                    message_id = None
                    log.exception('Could not persist exchange')
                retrieved_contexts = [
                    doc.page_content for doc in result.get('source_documents', [])
                ]
                payload = {'answer': result['answer'], 'sources': sources,
                           'retrieved_contexts': retrieved_contexts,
                           'tps': result.get('tps'), 'ttft': result.get('ttft'), 'saved': saved,
                           'cache_hit': result.get('cache_hit', False),
                           'cache_similarity': result.get('cache_similarity'),
                           'message_id': message_id}
                self.respond(200, payload)
            except Exception:
                log.exception('RAG request failed')
                self.respond(503, {'error': 'Unable to answer. Check Ollama and the knowledge base, then retry.'})
            finally:
                generation_lock.release()

        def save_feedback(self):
            if self.headers.get_content_type() != 'application/json':
                self.respond(415, {'error': 'Use application/json.'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0 or length > 1024:
                    raise ValueError('Request body is empty or too large.')
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('Expected a JSON object.')
                message_id, feedback = data.get('message_id'), data.get('feedback')
                if (not isinstance(message_id, int) or isinstance(message_id, bool)
                        or message_id <= 0):
                    raise ValueError('A valid message ID is required.')
                if feedback not in ('like', 'dislike', None):
                    raise ValueError('Feedback must be like, dislike, or null.')
                if not storage.set_feedback(message_id, feedback):
                    self.respond(404, {'error': 'Chat response was not found.'})
                    return
                self.respond(200, {'saved': True, 'feedback': feedback})
            except (ValueError, UnicodeDecodeError, OSError, sqlite3.Error) as exc:
                if isinstance(exc, sqlite3.Error):
                    log.exception('Could not persist response feedback')
                    self.respond(500, {'error': 'Could not save feedback.'})
                else:
                    self.respond(400, {'error': str(exc)})

    return ThreadingHTTPServer(address, Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--admin-port', type=int, default=8003)
    args = parser.parse_args()
    from aichatbot import CHAT_DB_PATH, init_chatbot
    from chat_storage import ChatStorage
    chain, retriever = init_chatbot()
    storage = ChatStorage(CHAT_DB_PATH)
    generation_lock = threading.Lock()
    admin = AdminManager(retriever)
    with create_server((args.host, args.port), chain, storage, generation_lock) as rag_server, \
            create_admin_server((args.host, args.admin_port), storage, admin, generation_lock) as admin_server:
        admin_thread = threading.Thread(target=admin_server.serve_forever, daemon=True)
        admin_thread.start()
        print(f'RAG API ready at http://{args.host}:{args.port}', flush=True)
        print(f'Admin API ready at http://{args.host}:{args.admin_port}', flush=True)
        try:
            rag_server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            admin_server.shutdown()
            admin_thread.join()


if __name__ == '__main__':
    main()
