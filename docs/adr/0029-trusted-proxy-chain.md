# ADR-0029: Define a Trusted Proxy Chain

Status: Accepted
Acceptance date: 2026-08-04

## Context
Cloudflare, cloudflared, Nginx, and FastAPI can misinterpret spoofable forwarded headers.

## Decision
Support only client→Cloudflare→cloudflared→Nginx→FastAPI. Block direct public access. Nginx replaces forwarding headers and accepts Cloudflare client identity only from the tunnel ingress. FastAPI trusts only Nginx, uses explicit allowed hosts and validated external origin, and never accepts arbitrary client forwarding headers.

## Alternatives
Trust all proxy headers or expose FastAPI directly.

## Tradeoffs
Proxy networks/configuration require coordinated maintenance and regression tests.

## Future impact
Any ingress change must update trust boundaries, tests, and threat model before deployment.
