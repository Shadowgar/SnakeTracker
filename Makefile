.PHONY: bootstrap check test

bootstrap:
	./scripts/development/bootstrap.sh

check:
	./scripts/quality/check.sh

test:
	uv run pytest -v
