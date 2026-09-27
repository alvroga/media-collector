# ADR-0001: Implementation language and delivery form

Status: Accepted
Date: 2026-09-23
Decided by: Claude (proposed, you approve)

## Context
The tool parses several project formats (gzipped XML, OTIO JSON, AAF binary), walks/copies large file trees with verification, and should be easy for editors (not developers) to run on macOS and Windows. It's open source, so contributors adding format readers matters.

## Options
1. **Python core + CLI, GUI later (Qt/PySide or web UI)** — best ecosystem for formats (`opentimelineio`, `pyaaf2`, `lxml`), lowest barrier for contributors writing readers. Packaging to a double-click app (PyInstaller/Briefcase) is workable but heavier.
2. **Rust core + CLI/Tauri GUI** — single fast binary, great for big copies; AAF/OTIO library support is weak, so more work per reader.
3. **TypeScript/Electron** — easy GUI, poor fit for AAF and heavy file I/O.

## Decision (proposed)
Option 1: Python 3.11+ core library (`media_collector`) with a CLI first; GUI is a thin layer added later over the same library.

## Consequences
Fastest path to Premiere + OTIO + AAF readers. Costs: distribution to non-technical editors needs a packaged app later; raw copy throughput is I/O-bound anyway, so Python speed is not the bottleneck.

## Update 2026-09-23
The delivery form is a macOS desktop app, not a CLI-first tool. See ADR-0006 (SwiftUI shell over the Python engine). The choice of Python for the engine stands.
