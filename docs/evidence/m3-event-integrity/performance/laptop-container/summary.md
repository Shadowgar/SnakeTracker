# M3 Laptop-Container Qualification Summary

Classification: qualified operational target on the development platform; not Raspberry Pi
deployment evidence.

Dataset: `snaketracker-reference-v1-phase3-event-slice`, exactly 1,000,000 stored events, 500
synthetic streams, one 10,000-event stream, fixed category percentages from the approved
representative dataset, 10 concurrent writers, and test-only reserved contracts. The run used
x86_64 Docker, Python 3.13.14, SQLite 3.40.1 with FTS5, ext4-backed container bind storage, full
durability, 5,000 ms busy timeout, 1,000-page automatic WAL checkpoint, 256 MiB journal limit, and
disabled local-development encryption.

## Measured results

| Measurement | Result | Target/interpretation |
|---|---:|---|
| Dataset seed | 51.67 s | Informational |
| Concurrent append p95 | 180.89 ms | Pass, at most 400 ms |
| SQLite busy failures | 0.0% | Pass, at most 0.1% |
| Unsnapshotted 10,000-event replay p95 | 1,539.63 ms | Stream-growth review signal triggered |
| Normal load from snapshot v9,900 | 100 tail events; 15.76 ms p95 | Pass, at most 50 ms; no full replay |
| FTS5 query p95 | 17.16 ms | Pass, at most 500 ms |
| Cold first shadow rebuild, ordinary + FTS | 165.35 s | Pass, under 30 minutes |
| Immediate warm shadow rebuild, ordinary + FTS | 168.45 s | Pass, under 30 minutes |
| Maximum process RSS | 91.44 MiB | Pass, at most 512 MiB |
| Database before projections | 1,068,134,400 bytes | Qualification measurement |
| Database after active + retained generations | 1,495,236,608 bytes | Qualification measurement |
| FTS storage across generations | 186,236,928 bytes | Qualification measurement |
| Peak observed seed WAL | 14,877,352 bytes | Below 256 MiB journal limit |
| Peak observed projection WAL | 213,679,712 bytes | Below 256 MiB journal limit |
| Final WAL after checkpoint | 0 bytes | Pass |
| Free-space headroom | 544.09 times final DB | Pass, at least 2 times |
| Integrity check | `ok` | Pass |

The 10,000-event full replay intentionally demonstrates why the accepted snapshot and stream-growth
gates exist; it is not ordinary command latency. Normal aggregate loading restored the valid
version-9,900 snapshot and read exactly the 100-event tail on every measured sample. Corrupt,
malformed, incompatible, and boundary-invalid snapshots are separately proven to quarantine and
fall back to complete authoritative replay. The unsnapshotted result requires architecture review
before allowing streams to grow beyond the documented threshold. No high-frequency telemetry was
introduced.

`results.json` is authoritative machine-readable evidence. `qualification.log` retains the exact
run output, and `results.sha256` verifies the result payload. The measured runtime image and full
implementation revision are recorded in the JSON.
