import unittest

from semantic_cache import SemanticCache


class SemanticCacheTests(unittest.TestCase):
    def test_semantic_hit_and_unrelated_miss(self):
        cache = SemanticCache()
        cache.store([1, 0], {'answer': 'Bring ID', 'source_documents': [{'page': 2}]})
        payload, score = cache.lookup([10, 1])
        self.assertGreater(score, .95)
        self.assertEqual(payload['answer'], 'Bring ID')
        self.assertIsNone(cache.lookup([0, 1]))
        payload['source_documents'][0]['page'] = 99
        self.assertEqual(cache.lookup([1, 0])[0]['source_documents'][0]['page'], 2)

    def test_history_isolation(self):
        cache = SemanticCache()
        history = (('Admissions?', 'Bring ID'),)
        cache.store([1, 0], {'answer': 'Yes'}, history)
        self.assertIsNone(cache.lookup([1, 0]))
        self.assertIsNotNone(cache.lookup([1, 0], history))

    def test_expiry_capacity_lru_and_clear(self):
        now = [0]
        cache = SemanticCache(ttl=10, max_entries=2, clock=lambda: now[0])
        cache.store([1, 0, 0], {'answer': 'a'})
        cache.store([0, 1, 0], {'answer': 'b'})
        cache.lookup([1, 0, 0])
        cache.store([0, 0, 1], {'answer': 'c'})
        self.assertIsNone(cache.lookup([0, 1, 0]))
        self.assertIsNotNone(cache.lookup([1, 0, 0]))
        now[0] = 10
        self.assertIsNone(cache.lookup([1, 0, 0]))
        cache.store([1, 0], {'answer': 'new'})
        cache.clear()
        self.assertIsNone(cache.lookup([1, 0]))

    def test_invalid_vectors_and_dimensions(self):
        cache = SemanticCache()
        for vector in ([], [0, 0], [float('nan')], [float('inf')]):
            with self.assertRaises(ValueError):
                cache.store(vector, {})
        cache.store([1, 0], {})
        self.assertIsNone(cache.lookup([1, 0, 0]))

    def test_configuration_validation(self):
        for config in ({'threshold': 0}, {'threshold': 2}, {'ttl': 0},
                       {'ttl': float('nan')}, {'max_entries': 0}):
            with self.assertRaises(ValueError):
                SemanticCache(**config)


if __name__ == '__main__':
    unittest.main()
