#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# Match the environment selection in run-pi.sh.
venv=.venv
if [[ -x venv_pi/bin/python ]]; then
    venv=venv_pi
fi

if [[ ! -x "$venv/bin/python" ]]; then
    if [[ -e "$venv" || -L "$venv" ]]; then
        printf 'Cannot use %s as a Pi virtual environment.\n' "$PWD/$venv" >&2
        exit 1
    fi
    python3 -m venv "$venv"
fi

"$venv/bin/python" -m pip install -r requirements_stt.txt piper-tts==1.8.0
"$venv/bin/python" -m pip check
printf 'Pi speech environment ready at %s.\n' "$PWD/$venv"
