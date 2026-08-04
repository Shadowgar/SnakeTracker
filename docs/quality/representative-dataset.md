# Versioned Representative Dataset Specification

Dataset ID: `snaketracker-reference-v1`
Seed: fixed and recorded by the future generator
Purpose: reproducible performance, capacity, replay, search, backup, and migration qualification

## Population

- 1 household with 10 users distributed across all roles
- 500 animals across active, quarantine, archived, deceased, and rehomed states
- 1,000 enclosures across active and retired states
- 1,000,000 domain events
- 100,000 finalized attachment metadata records
- 20 GiB content-addressed attachment corpus
- 10 concurrent interactive users in the benchmark mix

## Event distribution

The dataset specification fixes percentages and distributions rather than using uniform random rows:

- 30% feedings, including refusals and inventory-linked feedings
- 15% weight and length measurements
- 8% sheds
- 8% enclosure cleaning and water changes
- 10% health observations, medications, and vet visits
- 6% behavior, handling, and baths
- 8% inventory movements
- 5% expenses
- 4% profile, lifecycle, and enclosure assignments
- 3% reminder rules and preference changes
- 3% documents and other supported contracts

At least 5% of correctable events have correction chains, 1% have valid void/reinstatement behavior, and multi-stream workflows appear at realistic intervals. Stream lengths include a long-tail distribution, with designated streams near snapshot and architecture-review thresholds.

## Text and search distribution

Notes include empty, short, median, 95th-percentile, Unicode, punctuation, and maximum-allowed examples. Search terms include common and rare tokens, animal names, health terms, inventory, expenses, tags, and authorization-negative cases. Sensitive cross-role records are deliberately seeded to test leakage.

## Attachments

The corpus includes approved images and documents across typical and maximum dimensions and sizes, duplicate content for deduplication, immutable replacements, missing/corrupt negative fixtures, and malicious samples kept only in isolated test fixtures: active SVG/HTML, misleading signatures, oversized pixels, archives, and decompression bombs.

## Qualification environment manifest

Every run pins and records board revision/firmware, OS image digest, kernel, CPU governor/cooling, ext4 options, SSD controller/capacity/performance and fsync latency, Docker/Compose, container digests, Python patch, SQLite version and compile options, dependencies, Nginx, encryption settings, dataset commit/hash, cache state, and concurrency mix.

Both cold-cache and warm-cache runs are required. Network shaping defines the mobile 4G profile. Results include sample count, percentiles, variance, failures, memory, CPU, I/O, WAL, storage, and thermal throttling.

## Qualification targets

Targets in ADR-0024 and the architecture specification apply only to this dataset/environment version. New distributions or platform changes require a new dataset version and comparative report. Two consecutive releases missing a target require remediation or a superseding ADR.
