# CLAUDE.md — Media Collector

## What this project is
An open-source "collect / consolidate project media" tool for video editors. It reads an edit project (Premiere `.prproj` first; then FCP XML / FCPXML, OTIO, AAF, EDL, Resolve exports), finds every media file the timeline(s) actually use, and copies them to a destination **preserving folder structure to a configurable depth**, instead of dumping everything into one flat folder (the complaint about Premiere's Project Manager). Open-source alternative to [Tidy Media Manager](https://editingtools.io/software/tidy-media-manager), mirroring the structure-preserving behavior of DaVinci Resolve's Media Management.

Design lives in `docs/agent_docs/architecture.md`.

The product is a **native macOS app**: a SwiftUI shell (`app/`) over the Python engine (`src/media_collector`), talking JSON lines over stdio (ADR-0006). The engine is UI-free and must stay so; the Swift side knows nothing about formats or copying. The CLI (`python -m media_collector`) is a dev/test harness, not a deliverable.

## Why format-agnostic from day one
Premiere is the first target but not the only one. Every format reader must emit the same internal media-reference model, and the copy engine must only ever consume that model — never a format-specific structure. Adding a format = adding a reader, nothing else.

## Platform
macOS is the only supported/tested runtime (ADR-0004). Project files authored on Windows must still be readable: keep paths from projects as OS-tagged strings, never host `Path`s, and put OS-specific code in one platform module.

## Boundaries — never do these without explicit approval
- **Never modify, move, or delete source media or the source project file.** Copy-only, read-only on inputs; whole files only, never trim or transcode (ADR-0005). Relinking writes a *new* project file, never edits the original in place.
- **Never overwrite existing files at the destination silently.** Skip-identical (verified), or surface a conflict; never clobber.
- **Always keep the folder structure.** It is the whole point of the tool (depth setting: skip the first N levels). The app has no flatten switch and no wrapper-folder option, by the maintainer's decision; flattening survives only as a developer-CLI flag (`--flatten`) and is not part of the product.
- **Format readers must not import from the copy engine and vice versa** — the shared media-reference model is the only interface.

Keep this list intact even as the file grows — move narrative elsewhere, never a load-bearing constraint itself. 

## How to run it
See `docs/agent_docs/how-to-run.md`.

## Standing workflow
1. Real architecture choices → propose an ADR in `docs/adr/` before implementing.
2. Open work lives in GitHub Issues; check them before starting something new.
3. User-visible change (feature, fix, behaviour, new limitation) → add a line under `[Unreleased]` in
   `CHANGELOG.md` in the same commit. Versioning and release steps: `docs/release_process.md`.
4. Before a commit: `ruff check src tests`, `pytest`, and `swift test` in `app/` (see `docs/agent_docs/how-to-run.md`).
5. Commit and push only when explicitly asked.
