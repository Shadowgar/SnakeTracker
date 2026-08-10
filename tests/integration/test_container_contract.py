from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[2]


def read_project_file(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_dockerfile_is_pinned_frozen_non_root_and_multi_arch_safe() -> None:
    dockerfile = read_project_file("Dockerfile")

    assert re.search(r"^FROM .+@sha256:[0-9a-f]{64}", dockerfile, re.MULTILINE)
    assert "uv sync --frozen --no-dev" in dockerfile
    assert "ARG SNAKETRACKER_UID=1000" in dockerfile
    assert "--uid $SNAKETRACKER_UID" in dockerfile
    assert "USER snaketracker" in dockerfile
    assert "COPY .env" not in dockerfile
    assert "ENTRYPOINT [" in dockerfile


def test_compose_services_are_hardened_and_local_only() -> None:
    compose = read_project_file("compose.yaml")

    for service in ("migrate", "web", "worker", "nginx"):
        assert re.search(rf"^  {service}:$", compose, re.MULTILINE)
    assert "cloudflared:" not in compose
    assert (
        '"${SNAKETRACKER_BIND_ADDRESS:-127.0.0.1}:${SNAKETRACKER_HTTP_PORT:-8081}:8080"' in compose
    )
    assert "0.0.0.0:8081:8080" not in compose
    assert compose.count("<<: *app-common") == 3
    assert "SNAKETRACKER_UID: ${SNAKETRACKER_UID:-1000}" in compose
    assert compose.count("read_only: true") == 2
    assert compose.count("no-new-privileges:true") == 2
    assert compose.count("cap_drop:") == 2
    assert compose.count("resources:") >= 3
    assert '"--workers", "1"' in compose
    assert "healthcheck:" in compose
    assert "SNAKETRACKER_RUNTIME_SECRET_FILE" in compose
    assert "SNAKETRACKER_RUNTIME_SECRET:" not in compose
    assert "SNAKETRACKER_BACKUP_ENCRYPTION_KEY_FILE" in compose
    assert "SNAKETRACKER_BACKUP_ENCRYPTION_KEY:" not in compose
    assert "SNAKETRACKER_IMAGE_TAG:-phase4" in compose
    assert "SNAKETRACKER_ENVIRONMENT: development" in compose
    assert 'SNAKETRACKER_SESSION_COOKIE_SECURE: "false"' in compose
    assert "SNAKETRACKER_EXTERNAL_ORIGIN:-http://localhost:8081" in compose
    assert 'user: "101:101"' in compose
    assert "/tmp:size=16m,mode=1777,uid=101,gid=101" in compose


def test_migrations_complete_before_processes_start() -> None:
    compose = read_project_file("compose.yaml")

    assert compose.count("condition: service_completed_successfully") >= 2
    assert 'command: ["alembic", "upgrade", "head"]' in compose


def test_nginx_does_not_expose_internal_metrics_or_trust_forwarded_headers() -> None:
    nginx = read_project_file("deploy/nginx/nginx.conf")

    assert "location /internal/" in nginx
    assert "return 404" in nginx
    assert "proxy_set_header X-Forwarded-For $remote_addr" in nginx
    assert "proxy_set_header X-Forwarded-Proto $scheme" in nginx
    assert "server_tokens off" in nginx
    assert "X-Content-Type-Options" in nginx
    assert 'Referrer-Policy "same-origin"' in nginx


def test_nginx_reresolves_web_service_after_container_replacement() -> None:
    nginx = read_project_file("deploy/nginx/nginx.conf")

    assert "resolver 127.0.0.11" in nginx
    assert "set $snaketracker_web web:8000;" in nginx
    assert "proxy_pass http://$snaketracker_web;" in nginx


def test_container_context_excludes_secrets_and_runtime_state() -> None:
    ignored = read_project_file(".dockerignore")

    for pattern in (".env", "secrets/", "data/", "runtime/", "output/", "backups/", ".git/"):
        assert pattern in ignored
