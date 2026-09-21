"""
aichatbot.py — AI Kiosk Chatbot  (improved)

Document and query embeddings use the shared Ollama configuration in embeddings.py.
Hybrid retrieval and the Hugging Face cross-encoder reranker are retained.
"""

import logging
import os
from pathlib import Path
from time import perf_counter
from typing import Any

from dotenv import load_dotenv
load_dotenv()

import chromadb
from embeddings import create_embedding_function, OLLAMA_BASE_URL

# LCEL imports — replaces deprecated ConversationalRetrievalChain
from langchain_core.prompts import PromptTemplate
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.documents import Document
from langchain_ollama import OllamaLLM

# Cross-encoder reranker
from sentence_transformers import CrossEncoder

# BM25 for hybrid search keyword leg
try:
    import bm25s
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    logging.getLogger("kiosk_chatbot").warning(
        "bm25s not installed — falling back to vector-only retrieval. "
        "Run: pip install bm25s"
    )

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — must match ingest.py exactly
# All values can be overridden via .env file
# ─────────────────────────────────────────────────────────────────────────────

INDEX_DIR       = Path(os.getenv("INDEX_DIR", "./chromadb_index"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "kiosk_docs")
RERANK_MODEL    = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
LLM_MODEL       = os.getenv("LLM_MODEL", "phi4-mini:3.8b")

K_RETRIEVE  = 20   # candidates fetched before reranking
K_RERANK    = 5    # top-k kept after reranking, passed to LLM
MAX_HISTORY = 5    # rolling window — prevents context overflow
RRF_K       = 60   # RRF constant (standard value from the paper)

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("kiosk_chatbot")


# ─────────────────────────────────────────────────────────────────────────────
# RECIPROCAL RANK FUSION
# ─────────────────────────────────────────────────────────────────────────────

def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    k: int = RRF_K,
) -> list[str]:
    """
    Merge multiple ranked lists of document IDs into one list using RRF.
    Higher combined score → earlier position in the output.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=scores.__getitem__, reverse=True)


# ─────────────────────────────────────────────────────────────────────────────
# HYBRID RETRIEVER
# ─────────────────────────────────────────────────────────────────────────────

class HybridRetriever:
    """
    Two-stage retrieval:
      1. Fetch K_RETRIEVE candidates via hybrid BM25 + vector search (RRF fusion).
      2. Rerank with a cross-encoder, return top K_RERANK.
    """

    def __init__(self, collection: Any, reranker: CrossEncoder):
        self.collection = collection
        self.reranker   = reranker
        self._bm25: bm25s.BM25 | None = None
        self._all_ids:  list[str] = []
        self._all_docs: list[str] = []
        self._all_meta: list[dict] = []
        self._build_bm25_index()

    def _build_bm25_index(self):
        """Load all chunks from ChromaDB and build an in-memory BM25 index."""
        if not BM25_AVAILABLE:
            return

        log.info("Building BM25 index from collection …")
        result = self.collection.get(include=["documents", "metadatas"])
        self._all_ids   = result["ids"]
        self._all_docs  = result["documents"]
        self._all_meta  = result["metadatas"]

        self._bm25 = None
        tokenised = [(doc or "").lower().split() for doc in self._all_docs]
        if not any(tokenised):
            log.info("No text to index — using vector-only retrieval")
            return

        self._bm25 = bm25s.BM25(method="lucene", k1=1.5, b=0.75)
        self._bm25.index(tokenised, show_progress=False)
        log.info("BM25 index built — %d documents", len(self._all_ids))

    def _vector_search(self, query: str) -> list[str]:
        """Return K_RETRIEVE doc IDs ranked by cosine similarity."""
        count = self.collection.count()
        if not count:
            return []
        results = self.collection.query(
            query_texts=[query],
            n_results=min(K_RETRIEVE, count),
            include=["metadatas", "distances"],
        )
        return results["ids"][0]

    def _bm25_search(self, query: str) -> list[str]:
        """Return K_RETRIEVE doc IDs ranked by BM25 score."""
        if self._bm25 is None or not self._all_ids:
            return []
        tokens = query.lower().split()
        if not tokens:
            return []
        ranked_indices, scores = self._bm25.retrieve(
            [tokens],
            k=min(K_RETRIEVE, len(self._all_ids)),
            show_progress=False,
        )
        return [
            self._all_ids[i]
            for i, score in zip(ranked_indices[0], scores[0])
            if score > 0
        ]

    def _id_to_document(self, doc_id: str) -> Document | None:
        """Fetch a single document by ID from ChromaDB."""
        try:
            result = self.collection.get(
                ids=[doc_id],
                include=["documents", "metadatas"],
            )
            if not result["documents"]:
                return None
            text = result["documents"][0]
            meta = result["metadatas"][0]

            source   = meta.get("source", "unknown")
            page     = meta.get("page", -1)
            headings = meta.get("headings", "")

            content = f"[{source}, page {page}] {text}"
            if headings:
                content = f"[{headings}]\n{content}"

            return Document(page_content=content, metadata=meta)
        except Exception:
            return None

    def retrieve(self, query: str) -> list[Document]:
        """Full hybrid + rerank pipeline. Returns at most K_RERANK docs, best first."""
        vector_ranked = self._vector_search(query)
        bm25_ranked   = self._bm25_search(query)

        fused_ids = (
            reciprocal_rank_fusion([vector_ranked, bm25_ranked])
            if bm25_ranked
            else vector_ranked
        )

        candidates: list[Document] = []
        for doc_id in fused_ids[:K_RETRIEVE]:
            doc = self._id_to_document(doc_id)
            if doc:
                candidates.append(doc)

        if not candidates:
            return []

        pairs  = [(query, doc.page_content) for doc in candidates]
        scores = self.reranker.predict(pairs)

        reranked = [
            doc for _, doc in sorted(
                zip(scores, candidates), key=lambda t: t[0], reverse=True
            )
        ]
        return reranked[:K_RERANK]


# ─────────────────────────────────────────────────────────────────────────────
# LCEL CHAIN BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_chain(retriever: HybridRetriever, llm: OllamaLLM):
    """
    LCEL pipeline — one LLM call per query (no history),
    two calls when history exists (condense + answer).
    """

    condense_prompt = PromptTemplate(
        input_variables=["chat_history", "question"],
        template="""Given the conversation history and a follow-up question,
rephrase the follow-up into a clear, standalone question.
If there is no history, return the question unchanged.

Chat History:
{chat_history}

Follow-up question: {question}
Standalone question:""",
    )

    qa_prompt = PromptTemplate(
        input_variables=["context", "question"],
        template="""You are a helpful kiosk assistant. Answer the visitor's question
using ONLY the information found in the context below.
If the answer is not covered by the context, say:
"I'm sorry, I don't have information about that in my knowledge base."
Do not make up, assume, or infer anything beyond what the context states.

Context:
{context}

Question: {question}

Answer:""",
    )

    def format_history(history: list[tuple[str, str]]) -> str:
        if not history:
            return "(no prior conversation)"
        return "\n".join(f"Human: {q}\nAssistant: {a}" for q, a in history)

    def condense_question(inputs: dict) -> str:
        question = inputs["question"]
        if not inputs.get("chat_history"):
            return question
        prompt_text = condense_prompt.format(
            chat_history=format_history(inputs["chat_history"]),
            question=question,
        )
        return llm.invoke(prompt_text)

    def format_context(docs: list[Document]) -> str:
        return "\n\n".join(doc.page_content for doc in docs)

    def generate_answer(inputs: dict) -> dict:
        class FirstTokenTimer(BaseCallbackHandler):
            # Record arrival synchronously, excluding callback scheduling delay.
            run_inline = True
            ttft: float | None = None

            def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
                if token and self.ttft is None:
                    self.ttft = perf_counter() - inputs["query_started_at"]

        timer = FirstTokenTimer()
        prompt_text = qa_prompt.format(
            context=inputs["context"], question=inputs["standalone_question"],
        )
        generation = llm.generate(
            [prompt_text], callbacks=[timer],
        ).generations[0][0]
        metrics = generation.generation_info or {}
        token_count = metrics.get("eval_count")
        duration_ns = metrics.get("eval_duration")
        # Ollama reports generation duration in nanoseconds.
        tps = (
            token_count * 1_000_000_000 / duration_ns
            if token_count is not None and duration_ns and duration_ns > 0
            else None
        )
        return {**inputs, "answer": generation.text, "tps": tps, "ttft": timer.ttft}

    chain = (
        RunnablePassthrough.assign(
            query_started_at=RunnableLambda(lambda _: perf_counter()),
        )
        | RunnablePassthrough.assign(
            standalone_question=RunnableLambda(condense_question),
        )
        | RunnablePassthrough.assign(
            source_documents=RunnableLambda(
                lambda x: retriever.retrieve(x["standalone_question"])
            ),
        )
        | RunnablePassthrough.assign(
            context=RunnableLambda(
                lambda x: format_context(x["source_documents"])
            ),
        )
        | RunnableLambda(generate_answer)
    )

    return chain


# ─────────────────────────────────────────────────────────────────────────────
# INITIALIZATION
# ─────────────────────────────────────────────────────────────────────────────

def init_chatbot():
    if not INDEX_DIR.exists():
        log.error("ChromaDB index not found at %s", INDEX_DIR)
        log.info("Run first:  python ingest.py")
        raise FileNotFoundError(f"Index directory '{INDEX_DIR}' does not exist")

    log.info("Loading ChromaDB from %s", INDEX_DIR)

    embed_fn = create_embedding_function()
    client   = chromadb.PersistentClient(path=str(INDEX_DIR))

    try:
        collection = client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=embed_fn,
        )
    except Exception as e:
        log.error("Could not open collection '%s': %s", COLLECTION_NAME, e)
        log.info("If switching embedding models, rebuild with: python ingest.py --reset")
        raise

    chunk_count = collection.count()
    log.info("Collection loaded — %d chunks indexed", chunk_count)

    if chunk_count == 0:
        log.warning("Collection is empty! Add documents and run ingest.py first.")

    log.info("Loading cross-encoder reranker: %s", RERANK_MODEL)
    reranker  = CrossEncoder(RERANK_MODEL)
    retriever = HybridRetriever(collection=collection, reranker=reranker)
    llm       = OllamaLLM(model=LLM_MODEL, base_url=OLLAMA_BASE_URL)
    chain     = build_chain(retriever, llm)

    return chain, retriever


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def print_sources(sources: list[Document]):
    if not sources:
        print("No sources available.\n")
        return

    print("\nSources:")
    seen: set[tuple] = set()
    for doc in sources:
        key = (doc.metadata.get("source"), doc.metadata.get("page"))
        if key in seen:
            continue
        seen.add(key)
        heading = doc.metadata.get("headings") or "—"
        print(f"  • {doc.metadata.get('source')}  "
              f"(page {doc.metadata.get('page')})  "
              f"| {heading}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# CHAT LOOP
# ─────────────────────────────────────────────────────────────────────────────

def main():
    log.info("Initializing AI Kiosk Chatbot …")
    chain, _ = init_chatbot()

    print("\n" + "=" * 60)
    print("         AI Kiosk — Knowledge Base Assistant")
    print("=" * 60)
    print("  Ask any question answered by the loaded documents.")
    print("  Commands:")
    print("    sources  — show sources from the last answer")
    print("    clear    — reset conversation history")
    print("    exit / quit / q — exit")
    print("=" * 60 + "\n")

    chat_history: list[tuple[str, str]] = []
    last_sources: list[Document]        = []

    while True:
        try:
            query = input("You: ").strip()
            if not query:
                continue

            if query.lower() in ("exit", "quit", "q"):
                print("Thank you for using the kiosk. Goodbye!")
                break

            if query.lower() == "clear":
                chat_history.clear()
                last_sources.clear()
                print("Conversation history cleared.\n")
                continue

            if query.lower() == "sources":
                print_sources(last_sources)
                continue

            result = chain.invoke({
                "question":     query,
                "chat_history": chat_history,
            })

            answer       = result["answer"]
            last_sources = result.get("source_documents", [])

            print(f"\nKiosk: {answer}\n")
            tps = result.get("tps")
            ttft = result.get("ttft")
            print(f"Time to first token: {ttft:.2f} sec (including retrieval)"
                  if ttft is not None else "Time to first token: unavailable")
            print(f"TPS: {tps:.2f} tokens/sec\n" if tps is not None
                  else "TPS: unavailable\n")

            chat_history.append((query, answer))
            if len(chat_history) > MAX_HISTORY:
                chat_history = chat_history[-MAX_HISTORY:]

        except KeyboardInterrupt:
            print("\n\nSession ended. Goodbye!")
            break
        except Exception as e:
            log.error("Unexpected error: %s", e, exc_info=True)
            print("Something went wrong. Please try again.\n")


if __name__ == "__main__":
    main()
