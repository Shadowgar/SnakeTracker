#!/usr/bin/env sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
promoted_data_dir=${SNAKETRACKER_DATA_DIR:-$repo_root/runtime/phase2}
runtime_secret_file=${SNAKETRACKER_RUNTIME_SECRET_FILE:-$repo_root/secrets/runtime_secret}

cd "$repo_root"

case "${1:-}" in
    seed)
        shift
        exec uv run python -m scripts.fixtures.seed_m6_owner_review \
            --data-dir "$promoted_data_dir" \
            --runtime-secret-file "$runtime_secret_file" \
            "$@"
        ;;
    status)
        docker compose ps
        curl --fail --silent --show-error http://localhost:8081/health/ready
        printf '\nCare Keeper owner review: http://localhost:8081\n'
        ;;
    *)
        printf '%s\n' \
            'Usage: scripts/development/m6_owner_review_demo.sh seed [--as-of YYYY-MM-DD]' \
            '       scripts/development/m6_owner_review_demo.sh status' >&2
        exit 2
        ;;
esac
