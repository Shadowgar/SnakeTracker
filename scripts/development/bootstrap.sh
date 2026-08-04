#!/usr/bin/env sh
set -eu

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required; install it using the approved uv installation procedure." >&2
    exit 1
fi

uv python install 3.13
uv sync --frozen
