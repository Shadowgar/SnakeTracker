# Laptop/Docker Product Experience Qualification

Result: **Pass** on the versioned `snaketracker-reference-v1-m6-product-experience` dataset.

The run at revision `02919d8` used Python 3.13.14, SQLite 3.53.1, x86_64, and ext4. It seeded 100
mixed Snake/Spider profiles and 102 events. All six production projection definitions rebuilt in
cold and warm states. Measured results:

- authorized FTS query p95: 0.51 ms;
- collection read p95: 1.00 ms;
- maximum projection-group rebuild: less than 0.04 seconds;
- database: 1,626,112 bytes; peak observed WAL: 4,136,512 bytes;
- peak process RSS: 65.11 MiB;
- integrity: `ok`; foreign-key violations: 0.

These are qualification measurements on the pinned development dataset, not universal ratios or
production/Pi guarantees. See [results](results.json) and the [dataset](dataset/dataset.json).

Reproduce with:

```sh
uv run python -m scripts.fixtures.generate_representative_dataset \
  --output-dir docs/evidence/m6-product-experience/performance/laptop-container/dataset \
  --animals 100
SNAKETRACKER_QUALIFICATION_REVISION=$(git rev-parse --short HEAD) \
  uv run python -m scripts.benchmarks.phase6_qualification \
  --database /tmp/snaketracker-m6-qualification.sqlite3 \
  --output-dir docs/evidence/m6-product-experience/performance/laptop-container \
  --animals 100 --samples 30
```
