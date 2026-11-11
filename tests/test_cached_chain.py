"""Pipeline tests; run using the project's RAG environment."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from aichatbot import build_chain, HybridRetriever
from langchain_core.documents import Document
from semantic_cache import SemanticCache


class CachedChainTests(unittest.TestCase):
    def setUp(self):
        self.cache = SemanticCache()
        self.retriever = Mock()
        self.retriever.retrieve.return_value = [Document(page_content='Bring ID', metadata={'page': 1})]
        self.llm = Mock()
        self.llm.generate.return_value = SimpleNamespace(generations=[[
            SimpleNamespace(text='Bring your ID.', generation_info={})]])
        self.llm.invoke.return_value = 'What documents are needed?'
        self.embed = Mock(return_value=[[1, 0]])
        self.chain = build_chain(self.retriever, self.llm, self.embed, self.cache)

    def test_hit_skips_generation_and_retrieval_preserves_current_inputs(self):
        self.assertFalse(self.chain.invoke({'question': 'Required documents?'})['cache_hit'])
        result = self.chain.invoke({'question': 'What documents are needed?'})
        self.assertTrue(result['cache_hit'])
        self.assertEqual(result['question'], 'What documents are needed?')
        self.assertEqual(result['source_documents'][0].page_content, 'Bring ID')
        self.assertIsNone(result['tps'])
        self.assertGreaterEqual(result['ttft'], 0)
        self.llm.generate.assert_called_once()
        self.retriever.retrieve.assert_called_once()

    def test_history_condensation_and_isolation(self):
        self.chain.invoke({'question': 'Required documents?'})
        result = self.chain.invoke({'question': 'Which ones?', 'chat_history': [('Hi', 'Hello')]})
        self.assertFalse(result['cache_hit'])
        self.llm.invoke.assert_called_once()
        self.assertEqual(result['standalone_question'], 'What documents are needed?')
        self.assertEqual(self.llm.generate.call_count, 2)

    def test_embedding_failure_falls_back(self):
        self.embed.side_effect = RuntimeError('offline')
        self.assertEqual(self.chain.invoke({'question': 'Documents?'})['answer'], 'Bring your ID.')
        self.llm.generate.assert_called_once()

    def test_refresh_invalidates_cache(self):
        self.chain.invoke({'question': 'Documents?'})
        # Empty collection also exercises refresh without loading a BM25 model.
        retriever = object.__new__(HybridRetriever)
        retriever.semantic_cache = self.cache
        retriever.collection = Mock()
        retriever.collection.get.return_value = {'ids': [], 'documents': [], 'metadatas': []}
        retriever._build_bm25_index()
        self.assertFalse(self.chain.invoke({'question': 'Documents?'})['cache_hit'])


if __name__ == '__main__':
    unittest.main()
