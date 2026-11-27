#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

fail() {
    printf '%s\n' "$*" >&2
    exit 1
}

if (( $# > 1 )); then
    fail "Usage: bash run-pi.sh [backend-PC-IP]"
fi
if (( $# == 1 )); then
    export VITE_RAG_API="http://$1:8000"
    export VITE_ADMIN_API="http://$1:8003"
fi

if [[ -x venv_pi/bin/python ]]; then
    venv=venv_pi
elif [[ -x .venv/bin/python ]]; then
    venv=.venv
else
    fail "Create venv_pi or .venv and install the speech dependencies. See deploy/WSL_PI_SETUP.md."
fi
export PATH="$PWD/$venv/bin:$PATH"
export VOSK_MODEL="${VOSK_MODEL:-$PWD/models/vosk-model-small-en-us-0.15}"
export PIPER_MODEL="${PIPER_MODEL:-$PWD/voices/en_US-lessac-medium.onnx}"
export VITE_STT_API=http://127.0.0.1:8001
export VITE_TTS_API=http://127.0.0.1:8002

[[ -d "$VOSK_MODEL" ]] || fail "Vosk model directory missing: $VOSK_MODEL"
[[ -f "$PIPER_MODEL" && -f "$PIPER_MODEL.json" ]] || fail "Piper voice or its JSON config missing: $PIPER_MODEL"
command -v node >/dev/null || fail "Install Node.js on the Pi."
[[ -f aiok_ui/node_modules/vite/bin/vite.js ]] || fail "Install the frontend dependencies with: cd aiok_ui && npm ci"

pids=()
cleanup() {
    if (( ${#pids[@]} )); then
        kill "${pids[@]}" 2>/dev/null || true
        wait "${pids[@]}" 2>/dev/null || true
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

python stt_api.py --host 127.0.0.1 --port 8001 &
pids+=("$!")
python tts_api.py --host 127.0.0.1 --port 8002 --tts &
pids+=("$!")
(
    cd aiok_ui
    browser_args=()
    if [[ ${AIOK_OPEN_BROWSER:-0} == 1 ]]; then
        browser_args+=(--open)
    fi
    exec node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort "${browser_args[@]}"
) &
pids+=("$!")

printf 'Open http://localhost:5173 in the Pi browser. Press Ctrl+C to stop all three services.\n'
status=0
wait -n "${pids[@]}" || status=$?
printf 'A service exited (status %s). Stopping the launcher.\n' "$status" >&2
exit "$status"
