#!/bin/zsh
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# Use venv python if present, else fallback
if [ -f "$DIR/venv/bin/python" ]; then
    PYTHON="$DIR/venv/bin/python"
elif [ -f "$DIR/venv/bin/python3" ]; then
    PYTHON="$DIR/venv/bin/python3"
else
    PYTHON="$(which python3)"
fi

if [ "$#" -eq 0 ]; then
    exec "$PYTHON" "$DIR/gui_app.py"
else
    exec "$PYTHON" "$DIR/sync.py" "$@"
fi
