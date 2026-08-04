# ADR-0017: Store Immutable Finalized Attachment Versions

Status: Accepted
Acceptance date: 2026-08-04

## Context
Files are large, mutable filesystem paths are unsafe event references, and active content creates browser/server risk.

## Decision
Stage and validate uploads, then finalize immutable content versions with random keys, checksum, type, size, and dimensions. Events reference finalized versions only. Reject active content by default, constrain expansion/dimensions, use non-executable storage, and deliver through an authenticated endpoint or isolated origin with safe headers.

## Alternatives
SQLite blobs, public static folders, or mutable file paths.

## Tradeoffs
Two-phase lifecycle, orphan cleanup, and coordinated backups are required.

## Future impact
A storage adapter can move immutable versions to S3-compatible storage.
