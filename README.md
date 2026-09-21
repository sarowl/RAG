## Ollama embeddings

Both `ingest.py` and `aichatbot.py` use Ollama's `embeddinggemma` by default.
Start Ollama (`ollama serve` if it is not already running) and check `ollama list`
for `embeddinggemma:latest`. If needed, download it with `ollama pull embeddinggemma`.
The Python `ollama` dependency is already included in both requirements files.

Optional `.env` settings (use the same embedding model on the laptop and Pi):

```dotenv
EMBED_MODEL=embeddinggemma
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_EMBED_TIMEOUT=120
CHUNK_TOKENIZER=sentence-transformers/all-MiniLM-L6-v2
```

When switching from Hugging Face embeddings, rebuild the vectors before chatting.
Back up your index if you need to retain it: `--reset` deletes the configured collection
and clears the ingestion cache so unchanged source documents are processed again.
Run these commands on the machine with your source documents and Ollama model:

```bash
python3 ingest.py --reset
python3 ingest.py --test-query "What are the requirements for graduation?"
python3 aichatbot.py
```

You can also build a separate index by setting `INDEX_DIR` in `.env` before running
both scripts. If indexing on a laptop, copy the rebuilt index to the Pi afterward.

Only embeddings moved to Ollama. Ingestion still uses a Hugging Face tokenizer
(`CHUNK_TOKENIZER`) for chunk sizing, and the chatbot still uses its Hugging Face
cross-encoder (`RERANK_MODEL`) for reranking. These need cached models or internet
access on first use. The chunking tokenizer does not generate vectors.

Integration reference: [Chroma's Ollama embedding function](https://docs.trychroma.com/integrations/embedding-models/ollama).

 ### Step 1: Open WSL Terminal

  Open Windows Terminal, PowerShell, or Command Prompt and launch WSL:

    wsl

  (Optionally navigate to your project directory in WSL, e.g. cd /mnt/c/Projects/LLM)
  ──────
  ### Step 2: Install & Start Ollama in WSL

  Ollama serves the local LLM (llama3:8b) that aichatbot.py uses for generation.

  1. Install Ollama (inside your WSL shell):
    curl -fsSL https://ollama.com/install.sh | sh

  2. Start the Ollama Server (run in the background or a separate WSL terminal window):
    ollama serve

  3. Pull the Llama model:
    ollama pull llama3.2:3b

  ──────
  ### Step 3: Set Up Python Virtual Environment & Install Dependencies

  Inside your WSL terminal, navigate to your project folder and set up Python:

  1. Navigate to project folder:
    cd /mnt/c/Projects/LLM

  2. Install required Linux system packages (if not already installed):
    sudo apt update
    sudo apt install -y python3-venv python3-pip rsync

  3. Create and activate a Linux virtual environment:
    python3 -m venv venv_wsl
    source venv_wsl/bin/activate

  4. Install Python packages:
    pip install --upgrade pip
    pip install docling chromadb sentence-transformers transformers watchdog rank_bm25 python-dotenv langchain
  langchain-core langchain-ollama

  ──────
  ### Step 4: Run the Ingestion Pipeline (ingest.py)

  This parses your PDFs in ./docs/, creates text chunks, computes embeddings, and builds the ChromaDB index in
  ./chromadb_index/.

  1. Run ingestion:
    python3 ingest.py --reset

  2. Run a test query to verify indexing:
    python3 ingest.py --test-query "What are the requirements for graduation?"
    You should see top matching text chunks with relevance scores printed to your screen.
  ──────
  ### Step 5: Run the Kiosk Chatbot (aichatbot.py)

  Now start the interactive RAG chatbot in your active WSL virtual environment:

    python3 aichatbot.py

  • Ask questions: Type any question related to the documents in ./docs/.
  • View citations: Type sources after getting an answer to inspect exact page numbers and section headings.
  • Reset context: Type clear to reset chat history.
  • Exit: Type exit or quit