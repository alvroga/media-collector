# ADR-0002: License

Status: Accepted
Date: 2026-09-23
Decided by: You (chose Apache-2.0 after comparison with copyleft; goal is use and contribution, not studio adoption)

## Context
The goal is an open-source alternative to a commercial tool. License choice affects contributors and whether commercial editing-tool vendors can embed it.

## Options
- **MIT / Apache-2.0** — permissive; maximum adoption; anyone can fork closed. Apache-2.0 adds a patent grant.
- **GPL-3.0 / AGPL-3.0** — copyleft; derivatives stay open; may deter studio/vendor adoption.

Note: check dependency licenses (e.g. `opentimelineio` is Apache-2.0; `pyaaf2` is MIT) — all compatible with either choice.

## Decision
Apache-2.0.

## Consequences
Broad adoption and studio-friendly; forks may go proprietary.
