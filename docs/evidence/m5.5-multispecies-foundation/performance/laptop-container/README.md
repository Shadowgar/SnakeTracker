# Laptop/Docker Mixed-collection Measurements

Qualification target, not a universal guarantee. Measured August 11, 2026 at revision `fe4a476`
on the approved development laptop/Docker environment using the five-animal mixed fixture.

| Measurement | Result |
|---|---:|
| Authoritative replay of five Animal streams / 12 events, 30 passes, p50 | 2.043 ms |
| Authoritative replay of five Animal streams / 12 events, 30 passes, p95 | 2.713 ms |
| Authenticated `/animals`, 30 browser navigations, minimum | 47 ms |
| Authenticated `/animals`, p50 | 53 ms |
| Authenticated `/animals`, p95 | 69 ms |
| Authenticated `/animals`, maximum | 90 ms |
| SQLite database | 512,000 bytes |
| Stored domain events | 14 |
| Finalized profile photos | 5 |
| Web memory | 61.84 MiB |
| Worker memory | 38.52 MiB |
| Nginx memory | 8.414 MiB |

SQLite reported `integrity_check=ok` and no foreign-key violations. The fixture contains Snake A,
Snake B, Spider A, Spider B, and Spider C. These are non-production development measurements;
native Pi, SSD/ext4, thermal, and deployment budgets remain pending under M7.

The replay measurement loads each authoritative `animal:{uuid}` stream through the production
event registry and checksum-verifying SQLite event-store adapter. It is a representative
mixed-fixture growth measurement, not ordinary command latency or a universal guarantee.
