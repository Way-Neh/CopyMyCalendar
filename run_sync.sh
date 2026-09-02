#!/bin/zsh
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# Use venv python if present, else fallback
if [ -f "$DIR/venv/bin/python" ]; then
    PYTHON="$DIR/venv/bin/python"
else
    PYTHON="$(which python3)"
fi

exec "$PYTHON" "$DIR/sync.py" --sync
