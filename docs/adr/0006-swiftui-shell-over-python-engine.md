# ADR-0006: The product is a native macOS app: SwiftUI shell over the Python engine

Status: Accepted
Date: 2026-09-23
Decided by: You (native macOS app, SwiftUI shell over the Python engine); Claude (proposed the protocol design)

## Context
ADR-0001 chose a Python engine. The product is a **native macOS application for editors**, not a CLI. The engine (readers, plan, copier, relink writers) is UI-independent and tested. An earlier draft of this ADR proposed PySide6; native look-and-feel was then stated as a requirement, and Qt cannot match native controls, sheets, Dock and system integration.

## Decision
- The UI is a **SwiftUI app** (`app/`, Xcode project).
- The Python engine ships **inside the app bundle** as a helper process (embedded Python runtime + the `media_collector` package). The app launches it and talks to it over **stdin/stdout, one JSON message per line** (`media_collector serve`).
- The engine stays UI-free and knows nothing about Swift; the Swift side knows nothing about formats, planning or copying. The protocol is the only interface.
- The developer CLI (`python -m media_collector`) stays as a test harness and shares the engine API with `media_collector serve`.

### Protocol sketch (to be refined in `docs/agent_docs/app-protocol.md` when implemented)
App → engine (requests, each with an `id`): `open_project {path}`, `plan {options}` (returns file count, bytes, missing, cache skipped, example paths for the live preview), `run {options, dest, mappings}`, `cancel`, `volumes` (mounted volumes for the path-mapping sheet).
Engine → app: `result {id, ...}`, `error {id, message}`, and events during `run`: `progress {…Progress fields…}`, `file {status, path, dest, detail}`, `done {report summary, relinked project path}`.
Engine callbacks already fire on worker threads; `serve` serialises them onto stdout.

## Consequences
- Native look, drag-and-drop, sheets, Dock progress, notifications, dark mode come for free.
- Two languages: format readers/writers and engine logic stay Python (contributors adding a format never touch Swift); UI changes need Swift.
- Packaging is real work: embed a relocatable Python runtime, sign and notarize the whole bundle (Apple developer account needed for distribution). File access to external and network volumes needs care with sandboxing/permissions; likely a non-sandboxed, notarized app distributed outside the App Store.
- The protocol becomes a versioned contract; changes to engine option fields must be reflected on both sides.
- A pure-Python UI is no longer planned.
