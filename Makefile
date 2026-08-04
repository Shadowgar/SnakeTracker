.PHONY: bootstrap check container-config test

bootstrap:
	./scripts/development/bootstrap.sh

check:
	./scripts/quality/check.sh

container-config:
	docker compose config --quiet

test:
	uv run pytest -v
