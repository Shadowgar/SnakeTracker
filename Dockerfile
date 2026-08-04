FROM ghcr.io/astral-sh/uv@sha256:cf4eedcaa81655197f625739489effcbe71b61ceb1506f332c3facae5deceded AS uv
FROM python@sha256:9d7f287598e1a5a978c015ee176d8216435aaf335ed69ac3c38dd1bbb10e8d64 AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

ARG SNAKETRACKER_UID=1000
RUN groupadd --gid $SNAKETRACKER_UID snaketracker \
    && useradd --uid $SNAKETRACKER_UID --gid $SNAKETRACKER_UID --create-home --shell /usr/sbin/nologin snaketracker

WORKDIR /app
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable \
    && rm -rf /root/.cache/uv

COPY alembic.ini ./
COPY migrations ./migrations
COPY deploy/docker/entrypoint.sh /usr/local/bin/snaketracker-entrypoint
RUN chmod 0555 /usr/local/bin/snaketracker-entrypoint \
    && chown -R snaketracker:snaketracker /app

USER snaketracker
ENTRYPOINT ["/usr/local/bin/snaketracker-entrypoint"]
CMD ["uvicorn", "snaketracker.bootstrap.application:application_factory", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
