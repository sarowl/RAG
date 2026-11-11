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

## Optional terminal voice input (Vosk STT)

Run `python3 aichatbot.py` and type `voice` to speak a question. Recording starts
only after the **Listening** message, ends after a pause or 15 seconds, and can
be cancelled with Ctrl+C. Review the transcript: press Enter to send it, type a
replacement question, or enter `/cancel`. Accepted questions use the same RAG,
history, SQLite logging, and optional Piper answers as typed questions. Spoken
text is treated as a question, not as a terminal command.

Install the optional dependencies in your chatbot's Python environment.
Run these commands from the repository root (the directory containing
`aichatbot.py`), not from inside `models/`:

```bash
sudo apt install libportaudio2 unzip
python3 -m pip install -r requirements_stt.txt
mkdir -p models
curl -L --fail https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip -o /tmp/vosk-model.zip
unzip /tmp/vosk-model.zip -d models
```

Recognition runs locally after this one-time download; no audio is saved or sent
to a transcription service. The model loads on first use. Missing dependencies,
model files, or microphone access leave typed chat available.

Optional `.env` settings:

```dotenv
VOSK_MODEL=models/vosk-model-small-en-us-0.15
# Input device ID or a substring of its name; omit for the default microphone.
# STT_DEVICE=USB
```

List microphone devices with `python3 -m sounddevice`. Linux/Pi needs a working
PortAudio input device; WSL also needs microphone access configured in its audio
environment. To recognize another language, download the appropriate
[Vosk model](https://alphacephei.com/vosk/models) and set `VOSK_MODEL` to its
extracted directory. Capture follows the official
[Vosk microphone example](https://github.com/alphacep/vosk-api/blob/master/python/example/test_microphone.py).

## React UI with the RAG backend

Run the RAG backend and its Admin API on the device that has the knowledge
base, Ollama, and the configured LLM (the current default is
`phi4-mini:3.8b`). RAG and Admin use separate ports in one process so Admin
ingestion shares the chat lock and refreshes the same in-memory retriever.
On that backend device:

```bash
source venv_pi/bin/activate
python api.py --host 0.0.0.0 --port 8000 --admin-port 8003
```

Only bind to `0.0.0.0` on a trusted LAN and firewall ports 8000 and 8003 so only
the Pi can reach them. The RAG API has no authentication; Admin has PIN-based
sessions, and `ADMIN_PIN` should be changed from its default. Do not port-forward
these ports to the internet.

On the Pi, install and start the voice services in an environment with the
project code, Vosk model, and Piper voice files:

```bash
source venv_pi/bin/activate
python -m pip install -r requirements_stt.txt piper-tts==1.8.0
python stt_api.py --host 127.0.0.1 --port 8001
```

In another Pi terminal, start TTS (speech is off unless `--tts` is supplied):

```bash
source venv_pi/bin/activate
python tts_api.py --host 127.0.0.1 --port 8002 --tts
```

Use `--tts-model /path/to/voice.onnx` or `PIPER_MODEL` to select the voice; its
matching `.json` file is required. The Pi generates the WAV and the kiosk
browser plays it through the Pi's speakers. The Pi browser also captures
microphone audio; only its WAV is sent to Pi-local Vosk, while chat text and
answers travel to/from the RAG device.

For development, start Vite on the Pi and set the remote backend targets; STT
and TTS default to loopback on the Pi:

```bash
cd aiok_ui
npm install
VITE_RAG_API=http://BACKEND_IP:8000 VITE_ADMIN_API=http://BACKEND_IP:8003 npm run dev -- --host 0.0.0.0
```

Open the printed URL in the Pi's browser using `localhost` so microphone access
works. The Vite dev and preview proxies route `/api/admin` to Admin, `/api/stt`
and `/api/tts` to the Pi voice services, and other `/api` requests to RAG.
Environment variables `VITE_STT_API` and `VITE_TTS_API` can override the local
voice targets.

For production, build the UI and serve `aiok_ui/dist` on the Pi behind a web
server configured like [deploy/nginx.conf.example](deploy/nginx.conf.example).
The static files alone do not run the Python APIs. Use HTTPS if clients other
than the Pi itself need browser microphone access.

`POST /api/chat` accepts `{"question":"...","history":[["question","answer"]]}`
(up to five completed exchanges) and returns `answer`, deduplicated `sources`,
`tps`, `ttft`, and a `saved` flag. `GET /api/health` reports when startup finished;
it does not probe Ollama. Each browser manages its own conversation context.
New chat clears that context without deleting SQLite records. Retry regenerates
an answer and logs another completed exchange. Errors remain visible with a
retry button. Stop discards the pending browser response; backend inference may
finish and be logged. While inference is active, other requests receive a busy
response rather than queueing. Piper speech remains available in the CLI;
response rather than queueing. RAG responses contain no speech audio; the browser
requests it separately from the Pi's TTS API.

### Browser speech APIs

The Pi's Vosk service loads the model on first use. Set `VOSK_MODEL` if the
model is outside its default `models/vosk-model-small-en-us-0.15` path. The
browser sends mono 16-bit PCM WAV audio (8–96 kHz, maximum 30 seconds) to
`POST /api/stt`; the service returns `{"text":"..."}`. Audio is processed in
memory and is not forwarded to the RAG device.

Click the mic icon to start and allow browser microphone permission. Click it
again to stop and transcribe; recording also stops after 30 seconds. The text
is appended to your draft for review before sending. New chat cancels recording
or a pending transcript. The mic can also cancel while opening or transcribing.
Use localhost or HTTPS for browser microphone access. Capture uses the browser's
microphone, so no server audio device is needed for browser input.

After the answer appears, the UI posts its text to `POST /api/tts` on the Pi.
That endpoint returns `audio/wav`; the browser plays it and provides audio
controls. Piper is off unless the Pi TTS service is started with `--tts`.
Synthesis errors do not remove the text answer. Direct requests to each service's
`/api/health` report its readiness; the proxied `/api/health` targets RAG, which
does not probe Ollama.

### Knowledge-base administration

Open **Settings**, enter the administrator PIN (default **123456**), and select
**Open admin page**. Set `ADMIN_PIN` in the backend environment or `.env` to
change the PIN. PIN validation happens on the server; admin sessions expire
30 minutes after login. **Lock admin & return to chat** signs out.

Administrators can upload PDF, DOCX, PPTX, and HTML documents (25 MB maximum
per file), list documents, and permanently remove a document and its search
content. Uploaded files go to `DOCS_DIR` (default `./docs`). Duplicate upload
names are rejected. Run **ingestion** after uploading; **Reset & reingest**
clears the search index and rebuilds it from the current source files, keeping
the files themselves. Both removal and reset require confirmation on the page.

Ingestion uses the existing `ingest.py` dependencies and embedding settings on
the API host. Operations run in the background with status shown on the admin
page. Chat is temporarily unavailable during index changes, and the in-memory
search index is refreshed afterward. Failures are reported on the page; backend
logs contain details. Restart the API after installing this feature.

### Semantic answer caching

The CLI and HTTP API reuse answers and their sources for semantically similar
standalone questions, using the shared Ollama embedding model and cosine
similarity. Follow-ups are condensed before lookup; entries are scoped to the
exact conversation history. Cache hits skip retrieval, reranking, and answer
generation (history condensation still runs for follow-ups).

Configure these environment variables before starting the backend:

| Variable | Default | Meaning |
| --- | --- | --- |
| `SEMANTIC_CACHE_ENABLED` | `true` | Set to `false` to disable caching. |
| `SEMANTIC_CACHE_THRESHOLD` | `0.95` | Minimum cosine similarity, greater than 0 and at most 1. |
| `SEMANTIC_CACHE_TTL_SECONDS` | `259200` | Entry lifetime in seconds (3 days). |
| `SEMANTIC_CACHE_MAX_ENTRIES` | `256` | Maximum entries, with least recently used eviction. |

The cache lives in process memory and resets on restart. Admin ingestion,
removal, and reset operations invalidate it when refreshing search, including
partially failed operations. Restart the backend after external ingestion.
Similarity is approximate: raise the threshold or disable caching when closely
related questions require different answers.

HTTP chat responses include `cache_hit` and `cache_similarity`. On hits, `tps`
is null because no answer tokens were generated, and `ttft` measures elapsed
time until the cached answer is ready. Embedding/cache failures fall back to
the normal answer pipeline. Empty answers and answers without sources are not
cached. Saving chat history runs for every request; speech synthesis is a
separate request to the Pi TTS API after the answer appears.
