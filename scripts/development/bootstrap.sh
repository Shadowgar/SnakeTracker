#!/usr/bin/env sh
set -eu

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required; install it using the approved uv installation procedure." >&2
    exit 1
fi

python_version="$(tr -d '[:space:]' < .python-version)"
required_uv_version="0.12.1"
installed_uv_version="$(uv --version | awk '{print $2}')"
if [ "$installed_uv_version" != "$required_uv_version" ]; then
    echo "uv $required_uv_version is required; found $installed_uv_version." >&2
    exit 1
fi

uv python install "$python_version"
uv sync --frozen
