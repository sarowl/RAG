"""HTTP API for Piper speech synthesis. Run on the device that owns the speakers."""

import argparse
import io
import json
import logging
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import wave

MAX_BODY = 128 * 1024
MAX_TEXT = 12000
log = logging.getLogger(__name__)


def load_speech(model_path):
    from piper import PiperVoice
    voice = PiperVoice.load(str(model_path))

    def synthesize(text):
        output = io.BytesIO()
        with wave.open(output, 'wb') as wav:
            voice.synthesize_wav(text, wav)
        return output.getvalue()

    return synthesize


def create_server(address, speech=None):
    synthesis_lock = threading.Lock()

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
                self.respond(200, {'status': 'ready', 'tts_enabled': speech is not None})
            else:
                self.respond(404, {'error': 'Not found.'})

        def do_POST(self):
            if self.path != '/api/tts':
                self.respond(404, {'error': 'Not found.'})
                return
            if self.headers.get_content_type() != 'application/json':
                self.respond(415, {'error': 'Use application/json.'})
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= MAX_BODY:
                    self.respond(413, {'error': 'Request body is empty or too large.'})
                    return
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('Expected a JSON object.')
                text = data.get('text')
                if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
                    raise ValueError('Text must contain 1–12000 characters.')
            except (ValueError, UnicodeDecodeError, OSError) as exc:
                self.respond(400, {'error': str(exc)})
                return
            if speech is None:
                self.respond(503, {'error': 'Spoken answers are off. Start the Pi TTS service with --tts to enable them.'})
                return
            if not synthesis_lock.acquire(blocking=False):
                self.respond(503, {'error': 'Speech synthesis is busy. Please try again shortly.'})
                return
            try:
                audio = speech(text.strip())
                self.send_response(200)
                self.send_header('Content-Type', 'audio/wav')
                self.send_header('Content-Length', str(len(audio)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(audio)
            except Exception:
                log.exception('Speech synthesis failed')
                self.respond(503, {'error': 'Speech is unavailable. You can still read the answer.'})
            finally:
                synthesis_lock.release()

    return ThreadingHTTPServer(address, Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8002)
    parser.add_argument('--tts', action='store_true', help='Enable Piper speech synthesis')
    parser.add_argument('--tts-model', default=os.getenv('PIPER_MODEL', str(Path(__file__).resolve().parent / 'voices/en_US-lessac-medium.onnx')))
    args = parser.parse_args()
    speech = None
    if args.tts:
        try:
            speech = load_speech(Path(args.tts_model).expanduser())
        except Exception as exc:
            parser.error(f'Cannot enable TTS: {exc}')
    with create_server((args.host, args.port), speech=speech) as server:
        print(f'TTS API ready at http://{args.host}:{args.port} (speech {"on" if speech else "off"})', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()