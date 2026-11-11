import json
import threading
import unittest
from http.client import HTTPConnection
from unittest.mock import Mock

from tts_api import create_server


class TTSApiTests(unittest.TestCase):
    def request(self, server, path, body=None, content_type='application/json'):
        connection = HTTPConnection(*server.server_address, timeout=3)
        connection.request('GET' if body is None else 'POST', path, body,
                           {'Content-Type': content_type} if body is not None else {})
        response = connection.getresponse()
        result = response.status, response.getheader('Content-Type'), response.read()
        connection.close()
        return result

    def test_synthesis_returns_wav(self):
        speech = Mock(return_value=b'RIFF-test-wave')
        with create_server(('127.0.0.1', 0), speech=speech) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                status, content_type, body = self.request(server, '/api/tts', json.dumps({'text': ' Hello ' }))
                self.assertEqual((status, content_type, body), (200, 'audio/wav', b'RIFF-test-wave'))
                speech.assert_called_once_with('Hello')
            finally:
                server.shutdown()
                thread.join()

    def test_disabled_health_and_validation(self):
        with create_server(('127.0.0.1', 0)) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                status, _, body = self.request(server, '/api/health')
                self.assertEqual(status, 200)
                self.assertFalse(json.loads(body)['tts_enabled'])
                status, _, body = self.request(server, '/api/tts', json.dumps({'text': 'Hi'}))
                self.assertEqual(status, 503)
                self.assertIn('Spoken answers are off', json.loads(body)['error'])
                for payload in ({'text': ''}, {'text': 42}, []):
                    self.assertEqual(self.request(server, '/api/tts', json.dumps(payload))[0], 400)
                self.assertEqual(self.request(server, '/api/tts', '', 'text/plain')[0], 415)
            finally:
                server.shutdown()
                thread.join()


if __name__ == '__main__':
    unittest.main()