# Native Windows backend and Raspberry Pi kiosk

Run RAG, Admin, ingestion, and Ollama on Windows x64. Keep the UI, Vosk STT,
and Piper TTS on the Pi as in [the split-device guide](WSL_PI_SETUP.md).
Use the Windows instructions below instead of that guide's WSL backend,
Linux package installation, and WSL port-forwarding steps.

## Dependency audit

`requirements_windows.txt` contains the backend's direct dependencies, preserving
their versions from the existing snapshot. Transitive dependencies are resolved by
pip; this file is not a complete lockfile.

Validation: a native Windows x64 Python 3.11 `pip install --dry-run
--ignore-installed -r requirements_windows.txt` completed successfully. This checks
dependency resolution and available distributions, not runtime imports, model
inference, or ingestion. No packages were installed by that check.

| Existing dependency or setup | Windows backend action |
| --- | --- |
| ChromaDB, Docling, Transformers, Sentence Transformers, Ollama, LangChain Core/Ollama, bm25s, python-dotenv, watchdog | Retained in the Windows requirements. |
| PyTorch, torchvision, ONNX Runtime, NumPy, SciPy and other transitive packages | Let pip select compatible dependencies. GPU builds need a separate hardware-specific choice. |
| `python-magic`, `unstructured`, `faiss-cpu`, LangChain Community/Classic | Not imported by this backend; omitted. The active index is ChromaDB and ingestion uses Docling. |
| `pywin32` | Not directly required by the backend; omitted as a direct requirement. |
| `piper-tts`, `vosk`, `sounddevice`, ALSA/`aplay`, PortAudio | Keep on the Pi for this deployment. The voice modules import optional engines lazily. Windows terminal `tts on` remains unsupported because `tts.py` uses `aplay`. |
| Uvicorn | Not the API entry point: `api.py` uses Python's `ThreadingHTTPServer`. Chroma may still install Uvicorn transitively. |
| `apt`, `source .../bin/activate`, WSL portproxy rules | Replaced by native Python commands and direct Windows LAN access. |

The original `requirements.txt` is a broad UTF-16 environment snapshot, including
unrelated packages and an unconditional Windows-only `pywin32` pin. The new file
is UTF-8 and independent of that snapshot. Do not install both into the new venv.
Evaluation tools have separate requirements and are outside this backend setup.

Official platform references: [Docling installation](https://docling-project.github.io/docling/getting_started/installation/),
[PyTorch Windows installation](https://pytorch.org/get-started/locally/), and
[Ollama for Windows](https://docs.ollama.com/windows).

## 1. Create a fresh Windows environment

Use Windows PowerShell from the repository root. Python 3.11 x64 is the target
for this setup (it is installed on this computer). Do not reuse the Linux venv,
or the existing root-level `Lib`/`Scripts` directories.

```powershell
cd C:\Users\USER\Documents\AIOK\RAG
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements_windows.txt
.\.venv\Scripts\python.exe -m pip check
```

Explicit interpreter paths avoid PowerShell activation-policy changes. For GPU
acceleration of reranking/ingestion, use the official PyTorch selector for your
Windows GPU and install its matching torch/torchvision build in this venv.
Ollama manages its own inference runtime separately.

## 2. Install Ollama and configure paths

Install [Ollama for Windows](https://ollama.com/download/windows). The installed
app normally serves in the background; run `ollama serve` only if it is not already
running. WSL's downloaded models are not automatically Windows model downloads.

```powershell
ollama pull embeddinggemma
ollama pull llama3.2:3b
ollama list
```

Merge these values into your existing `.env`; preserve any other settings:

```dotenv
OLLAMA_BASE_URL=http://localhost:11434
EMBED_MODEL=embeddinggemma
LLM_MODEL=llama3.2:3b
DOCS_DIR=./docs
INDEX_DIR=./chromadb_index
CHAT_DB_PATH=./chat_history.sqlite3
```

`llama3.2:3b` is the current code default. If you use another `LLM_MODEL`, pull
that model instead. Set `ADMIN_PIN` to your chosen PIN. Replace `/home/...` or
`/mnt/c/...` overrides with relative paths or Windows paths such as
`C:/Users/USER/Documents/AIOK/RAG/docs`. Keep the same embedding model and
collection name as your existing index.

## 3. Preserve data and start the backend

Stop the old backend before switching. Back up the entire `chromadb_index`
directory and chat database with their processes stopped. For the same checkout,
the data already resides on the Windows drive; do not run WSL and Windows
backends against it simultaneously. Keep `docs` and the ingestion state file.
Do not use `--reset` merely to change operating systems: it deletes the collection.

For a new or empty index, ingest first:

```powershell
.\.venv\Scripts\python.exe ingest.py
```

First use may download Docling, tokenizer, and reranker model files. Validate
retrieval, then start both APIs in one process:

```powershell
.\.venv\Scripts\python.exe ingest.py --test-query "What are the requirements for graduation?"
.\.venv\Scripts\python.exe api.py --host 0.0.0.0 --port 8000 --admin-port 8003
```

From another PowerShell terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
Invoke-RestMethod http://127.0.0.1:8003/api/health
```

Health checks do not test Ollama inference. Send a chat question and test an Admin
upload/ingestion after installation to verify the full pipeline.

## 4. Connect the Pi

Allow inbound TCP 8000 and 8003 in Windows Firewall on the private network,
restricted to the Pi's address. Use the Windows LAN IPv4 address from `ipconfig`.
Ollama can remain on loopback; the Pi only needs the two API ports.

If existing WSL portproxy rules occupy these ports, remove only the old rules for
this application before starting the native server. Native Windows needs no WSL
forwarding. Keep the Pi's STT/TTS and UI configuration from the split-device guide;
set the UI proxy targets to `http://WINDOWS_LAN_IP:8000` and
`http://WINDOWS_LAN_IP:8003`, then restart Vite or reload Nginx as appropriate.

The API is intended for a trusted LAN; RAG has no authentication and Admin uses
the configured PIN. Do not expose these ports publicly.
