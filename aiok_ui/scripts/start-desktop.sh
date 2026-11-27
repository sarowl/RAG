#!/usr/bin/env bash
set -eo pipefail

# Desktop launchers do not inherit the interactive shell's NVM setup.
if ! command -v node >/dev/null 2>&1; then
    export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
    if [[ -s "$NVM_DIR/nvm.sh" ]]; then
        source "$NVM_DIR/nvm.sh"
    fi
fi

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
export AIOK_OPEN_BROWSER=1
exec bash "$repo_dir/run-pi.sh"
