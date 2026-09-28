import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import sys
from types import SimpleNamespace

from admin_manager import AdminManager
from api import create_server


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.admin = AdminManager(docs_dir=self.temp.name)
        self.server = create_server(('127.0.0.1', 0), Mock(), Mock(), stt=Mock(), admin=self.admin)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, body=None, token=None):
        conn = HTTPConnection(*self.server.server_address)
        headers = {'Authorization': f'Bearer {token}'} if token else {}
        conn.request('GET' if body is None else 'POST', '/api/admin/' + path,
                     json.dumps(body) if isinstance(body, dict) else body, headers)
        response = conn.getresponse()
        result = response.status, json.loads(response.read())
        conn.close()
        return result

    @patch.dict('os.environ', {'ADMIN_PIN': '123456'})
    def test_auth_upload_list_and_logout(self):
        self.assertEqual(self.request('files')[0], 401)
        self.assertEqual(self.request('upload?name=a.pdf', b'hello')[0], 401)
        self.assertEqual(self.request('login', {'pin': 'wrong'})[0], 401)
        status, result = self.request('login', {'pin': '123456'})
        self.assertEqual(status, 200)
        token = result['token']
        self.assertEqual(self.request('upload?name=a.pdf', b'hello', token)[0], 201)
        self.assertEqual(self.request('upload?name=a.pdf', b'other', token)[0], 400)
        self.assertEqual(self.request('files', token=token)[1]['files'], [{'name': 'a.pdf', 'size': 5}])
        for name in ('../bad.pdf', '/tmp/bad.pdf', 'bad.txt', '..\\bad.pdf'):
            with self.assertRaises(ValueError):
                self.admin.path(name)
        self.request('logout', {}, token)
        self.assertEqual(self.request('files', token=token)[0], 401)

    def test_remove_refreshes_search_and_persists_state(self):
        path = Path(self.temp.name) / 'a.pdf'
        path.write_bytes(b'document')
        ingester = SimpleNamespace(collection=Mock(), state={str(path): 'hash'}, index_dir=Path(self.temp.name))
        self.admin.factory = lambda: ingester
        self.admin.retriever = Mock()
        lock = threading.Lock()
        save = Mock()
        with patch.dict(sys.modules, {'ingest': SimpleNamespace(save_state=save)}):
            self.admin.start('remove', lock, 'a.pdf')
            self.assertTrue(lock.acquire(timeout=3))
            lock.release()
        self.assertFalse(path.exists())
        ingester.collection.delete.assert_called_once_with(where={'source': 'a.pdf'})
        self.admin.retriever._build_bm25_index.assert_called_once()
        save.assert_called_once_with({}, Path(self.temp.name))
        self.assertEqual(self.admin.snapshot()['job']['state'], 'succeeded')

    def test_reset_clears_index_and_reingests_documents(self):
        path = Path(self.temp.name) / 'guide.pdf'
        path.write_bytes(b'document')
        collection = Mock()
        collection.get.return_value = {'ids': ['old-chunk']}
        ingester = SimpleNamespace(collection=collection, state={'old-file': 'old-hash'},
                                   index_dir=Path(self.temp.name))
        def ingest_file(document):
            ingester.state[str(document.resolve())] = 'new-hash'
        ingester.ingest_file = Mock(side_effect=ingest_file)
        self.admin.factory = lambda: ingester
        lock = threading.Lock()
        save = Mock()
        module = SimpleNamespace(save_state=save, file_hash=lambda _: 'new-hash')
        with patch.dict(sys.modules, {'ingest': module}):
            self.admin.start('reset', lock)
            self.assertTrue(lock.acquire(timeout=3))
            lock.release()
        collection.delete.assert_called_once_with(ids=['old-chunk'])
        ingester.ingest_file.assert_called_once_with(path)
        self.assertEqual(ingester.state, {str(path): 'new-hash'})
        self.assertTrue(path.exists())
        self.assertEqual(self.admin.job['state'], 'succeeded')

    def test_busy_chat_prevents_ingestion(self):
        lock = threading.Lock()
        lock.acquire()
        with self.assertRaises(ValueError):
            self.admin.start('reset', lock)
        lock.release()
        self.assertEqual(self.admin.job['state'], 'idle')

    @patch.dict('os.environ', {'ADMIN_PIN': '654321'})
    def test_pin_override_and_throttling(self):
        self.assertTrue(self.admin.authorized(self.admin.login('654321')))
        for _ in range(5):
            with self.assertRaises(PermissionError):
                self.admin.login('bad')
        with self.assertRaisesRegex(PermissionError, 'Too many'):
            self.admin.login('654321')
