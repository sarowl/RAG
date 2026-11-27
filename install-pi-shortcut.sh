#!/usr/bin/env bash
set -euo pipefail

if (( $# > 1 )); then
    printf 'Usage: bash install-pi-shortcut.sh [backend-PC-IP]\n' >&2
    exit 1
fi
if (( $# == 1 )) && [[ ! $1 =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    printf 'Enter the backend PC’s IPv4 address, such as 192.168.1.50.\n' >&2
    exit 1
fi

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
desktop_dir=$(xdg-user-dir DESKTOP 2>/dev/null || true)
mkdir -p -- "${desktop_dir:=$HOME/Desktop}"
shortcut="$desktop_dir/AIOK Kiosk.desktop"

# Escape the script path for the desktop entry's quoted Exec argument.
script="$repo_dir/run-pi.sh"
script=${script//\\/\\\\\\\\}
script=${script//\"/\\\\\"}
script=${script//\$/\\\\\$}
script=${script//\`/\\\\\`}
script=${script//%/%%}

cat > "$shortcut" <<EOF
[Desktop Entry]
Type=Application
Name=AIOK Kiosk
Exec=env AIOK_OPEN_BROWSER=1 bash "$script"${1:+ $1}
Icon=web-browser
Terminal=true
EOF
chmod +x -- "$shortcut"
printf 'Shortcut installed at %s\n' "$shortcut"
