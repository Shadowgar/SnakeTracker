# ADR-0010: Govern SQLite Pragmas and Maintenance

Status: Accepted
Acceptance date: 2026-08-04

## Context
SQLite safety and performance depend on filesystem and pragma choices.

## Decision
Require local SSD storage with reliable locks; prohibit NFS, SMB, synced folders, and SD cards. Enable foreign keys and WAL, use full durability for authoritative commits, bounded busy timeout/retry, monitored checkpoints, daily quick and scheduled full integrity checks, incremental vacuum, statistics maintenance, and measured FTS optimization. Pin exact values in each release qualification manifest.

## Alternatives
Defaults without governance, weaker durability, or remote filesystems.

## Tradeoffs
Full durability and maintenance consume I/O; correctness takes priority over benchmark optics.

## Future impact
Pragma changes require qualification evidence and an ADR amendment/supersession.
