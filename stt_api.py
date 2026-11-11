"""HTTP API for browser speech recognition. Run on the device with the Vosk model."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import threading

from stt import VoskSTT

MAX_AUDIO_BODY = 30 * 96000 * 2 + 44
log = logging.getLogger(__name__)


def create_server(address, stt=None):
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
                pass

        def do_GET(self):
            if self.path == '/api/health':
                self.respond(200, {'status': 'ready', 'stt_enabled': True})
            else:
                self.respond(404, {'error': 'Not found.'})

        def do_POST(self):
            if self.path != '/api/stt':
                self.respond(404, {'error': 'Not found.'})
                return
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
                self.respond(503, {'error': 'Voice input is unavailable. Check the Pi Vosk model and requirements_stt.txt installation.'})
            finally:
                transcription_lock.release()

    return ThreadingHTTPServer(address, Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8001)
    args = parser.parse_args()
    with create_server((args.host, args.port)) as server:
        print(f'STT API ready at http://{args.host}:{args.port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()