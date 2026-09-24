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

## SQLite chat history

Each completed question and answer is saved automatically in
`./chat_history.sqlite3` using Python's built-in SQLite support. Set
`CHAT_DB_PATH` in `.env` to use a different database path (relative paths are
resolved from the working directory). Parent directories are created automatically.

The `chat_history` table contains `id`, `created_at` (UTC), `user_query`,
`llm_answer`, `tps` (tokens per second), and `ttft` (seconds, including retrieval
and any question rewriting). Unavailable metrics are stored as SQL `NULL`.
Commands and failed generations are not saved. The `clear` command only resets
in-memory conversation context; saved exchanges remain across restarts.

To inspect saved exchanges with the SQLite CLI:

```bash
sqlite3 -header -column chat_history.sqlite3 'SELECT * FROM chat_history ORDER BY id DESC LIMIT 10;'
```

## Optional spoken answers (Piper TTS)

Speech is an accessibility option, **off by default**. In the chat, type
`tts on` to enable it, `tts off` to stop speech and disable it, or `tts` to
check its status. Only the final LLM answer is spoken; prompts, sources,
performance metrics, commands, and errors are not sent to Piper. Playback runs
in the background. A new question, `clear`, or exiting stops existing playback.

The implementation is in `tts.py`. On Raspberry Pi OS/Linux (including WSL
with working audio), install the playback utility and download a voice once:

```bash
sudo apt install alsa-utils
python3 -m pip install piper-tts==1.8.0
mkdir -p voices
cd voices
python3 -m piper.download_voices en_US-lessac-medium
cd ..
python3 aichatbot.py
```

Both `voices/en_US-lessac-medium.onnx` and its `.onnx.json` configuration are
required. To use another voice or location, set `PIPER_MODEL` in `.env` to the
ONNX file path. Relative paths are resolved from the working directory.
Synthesis runs locally on CPU after the download. Piper loads only when speech
is enabled, and missing voice/audio dependencies leave text chat available.
Playback uses the default ALSA output; verify the kiosk's speaker configuration
if no sound is heard. Native Windows playback is not implemented.

API reference: [Piper Python API](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md).
