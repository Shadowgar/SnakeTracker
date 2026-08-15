#!/usr/bin/env sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
demo_data_dir=${SNAKETRACKER_M6_DEMO_DATA_DIR:-$repo_root/runtime/m6-owner-review-demo}
demo_port=${SNAKETRACKER_M6_DEMO_PORT:-18087}
demo_origin="http://localhost:$demo_port"
compose_project=snaketracker-m6-demo

cd "$repo_root"

compose_demo() {
    SNAKETRACKER_DATA_DIR="$demo_data_dir" \
    SNAKETRACKER_HTTP_PORT="$demo_port" \
    SNAKETRACKER_EXTERNAL_ORIGIN="$demo_origin" \
    docker compose -p "$compose_project" "$@"
}

case "${1:-}" in
    seed)
        shift
        exec uv run python -m scripts.fixtures.seed_m6_owner_review \
            --data-dir "$demo_data_dir" "$@"
        ;;
    start)
        compose_demo up --build -d --wait
        printf 'M6 owner-review demo: %s\n' "$demo_origin"
        ;;
    status)
        compose_demo ps
        ;;
    stop)
        compose_demo down
        ;;
    *)
        printf '%s\n' \
            'Usage: scripts/development/m6_owner_review_demo.sh seed [--as-of YYYY-MM-DD] [--replace]' \
            '       scripts/development/m6_owner_review_demo.sh start|status|stop' >&2
        exit 2
        ;;
esac
