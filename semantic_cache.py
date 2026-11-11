"""Bounded, process-local semantic answer cache using cosine similarity."""
from collections import OrderedDict
from copy import deepcopy
import math
import threading
import time


class SemanticCache:
    def __init__(self, threshold=0.95, ttl=259200, max_entries=256, clock=time.monotonic):
        if not math.isfinite(threshold) or not 0 < threshold <= 1:
            raise ValueError('Semantic cache threshold must be in (0, 1].')
        if not math.isfinite(ttl) or ttl <= 0 or max_entries < 1:
            raise ValueError('Semantic cache TTL and capacity must be positive.')
        self.threshold, self.ttl, self.max_entries = threshold, ttl, max_entries
        self.clock = clock
        self._entries = OrderedDict()
        self._lock = threading.Lock()
        self._sequence = 0

    @staticmethod
    def normalize(vector):
        values = tuple(float(value) for value in vector)
        norm = math.hypot(*values)
        if not values or not math.isfinite(norm) or norm == 0:
            raise ValueError('Cache embeddings must be finite, nonzero vectors.')
        return tuple(value / norm for value in values)

    def clear(self):
        with self._lock:
            self._entries.clear()

    def lookup(self, vector, scope=()):
        vector = self.normalize(vector)
        with self._lock:
            now = self.clock()
            best_key, best_score = None, -1.0
            for key, (stored, entry_scope, expires, payload) in list(self._entries.items()):
                if expires <= now:
                    del self._entries[key]
                    continue
                if scope != entry_scope or len(vector) != len(stored):
                    continue
                score = max(-1.0, min(1.0, sum(a * b for a, b in zip(vector, stored))))
                if score >= self.threshold and score > best_score:
                    best_key, best_score = key, score
            if best_key is None:
                return None
            self._entries.move_to_end(best_key)
            return deepcopy(self._entries[best_key][3]), best_score

    def store(self, vector, payload, scope=()):
        vector = self.normalize(vector)
        with self._lock:
            now = self.clock()
            for key, entry in list(self._entries.items()):
                if entry[2] <= now:
                    del self._entries[key]
            self._sequence += 1
            self._entries[self._sequence] = (vector, scope, now + self.ttl, deepcopy(payload))
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)
