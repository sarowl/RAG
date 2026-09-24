import json
import sqlite3
import threading
import unittest
from http.client import HTTPConnection
from types import SimpleNamespace
from unittest.mock import Mock

from api import create_server


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.chain = Mock()
        self.chain.invoke.return_value = {
            'answer': 'Bring your ID.', 'tps': 12.0, 'ttft': 0.5,
            'source_documents': [SimpleNamespace(metadata={'source': 'guide.pdf', 'page': 2})] * 2,
        }
        self.storage = Mock()
        self.server = create_server(('127.0.0.1', 0), self.chain, self.storage)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, body, path='/api/chat', method='POST'):
        connection = HTTPConnection(*self.server.server_address, timeout=3)
        connection.request(method, path, json.dumps(body), {'Content-Type': 'application/json'})
        response = connection.getresponse()
        result = response.status, json.loads(response.read())
        connection.close()
        return result

    def test_question_history_sources_and_persistence(self):
        status, result = self.request({'question': ' What do I bring? ', 'history': [['Hi', 'Hello']]})
        self.assertEqual(status, 200)
        self.chain.invoke.assert_called_once_with({'question': 'What do I bring?', 'chat_history': [['Hi', 'Hello']]})
        self.assertEqual(len(result['sources']), 1)
        self.storage.save.assert_called_once_with('What do I bring?', 'Bring your ID.', 12.0, 0.5)
        self.assertTrue(result['saved'])

    def test_invalid_input_never_reaches_chain(self):
        for body in ({'question': ''}, {'question': 4}, {'question': 'Hi', 'history': ['bad']}, {'question': 'Hi', 'history': [['a', 'b']] * 6}):
            self.assertEqual(self.request(body)[0], 400)
        self.chain.invoke.assert_not_called()

    def test_generation_failure_and_recovery(self):
        self.chain.invoke.side_effect = RuntimeError('private internal detail')
        status, result = self.request({'question': 'Hi'})
        self.assertEqual(status, 503)
        self.assertNotIn('private', result['error'])
        self.storage.save.assert_not_called()
        self.chain.invoke.side_effect = None
        self.assertEqual(self.request({'question': 'Try again'})[0], 200)

    def test_storage_failure_preserves_answer(self):
        self.storage.save.side_effect = sqlite3.OperationalError('disk full')
        status, result = self.request({'question': 'Hi'})
        self.assertEqual(status, 200)
        self.assertFalse(result['saved'])
        self.assertEqual(result['answer'], 'Bring your ID.')

    def test_health_and_unknown_routes(self):
        self.assertEqual(self.request(None, '/api/health', 'GET')[0], 200)
        self.assertEqual(self.request({}, '/missing')[0], 404)


if __name__ == '__main__':
    unittest.main()
