# ADR-0027: Exclude High-Frequency Telemetry from Domain Streams

Status: Accepted
Acceptance date: 2026-08-04

## Context
Temperature, humidity, and camera telemetry can overwhelm animal/enclosure streams and SQLite projections.

## Decision
Do not ingest high-frequency readings into business streams. Future telemetry uses a dedicated ingestion, retention, sampling, and rollup architecture; only meaningful threshold transitions may emit domain events.

## Alternatives
One event per sensor sample or unstructured metadata on animal events.

## Tradeoffs
Sensor support is deferred until separately designed.

## Future impact
Telemetry requires workload qualification, privacy/security analysis, and a superseding/additional ADR.
