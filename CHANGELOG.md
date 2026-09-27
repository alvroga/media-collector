# Changelog

All notable changes to Media Collector are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (`0.MINOR.PATCH` until the first stable 1.0).
This file is what users and contributors read.

## [Unreleased]

## [0.2.2] - 2026-09-27

First public release: a working engine, a developer CLI, and the macOS app end to end (open a
project, plan, copy, relink, get a report).

### Added
- **Read** project files from Premiere Pro (`.prproj`), Final Cut Pro 7 XML, FCPXML (including
  `.fcpxmld` bundles), OpenTimelineIO (`.otio`), AAF (`.aaf`) and After Effects (`.aep`, read-only:
  every footage item counts as used, no sequences, no relink). Every reader produces the same media
  model, and all agree on the same project in the cross-format test fixture.
- **Copy** the media a project uses, whole files only, with SHA-256 verification, atomic writes, skip
  of identical files, no overwriting, dry run, byte-level progress, cancellation and parallel workers.
- **Keep the folder structure** (Resolve-style "skip the first N folder levels"), optional flattening
  (developer CLI only), optional project-name folder, collision handling (`_2` suffix).
- **Choose what to take**: entire project or selected sequences (with "Select All"/"Select None"),
  used media only or all media.
- **Proxies**: Premiere proxies (and FCPXML `proxy-media`) are paired with their originals and can be
  copied with them.
- **Relink**: write a new copy of the project pointing at the copied files, for Premiere (including
  proxies), FCP7 XML, FCPXML, OTIO and AAF. Sources are never modified. Verified by opening the
  results in Premiere, Final Cut Pro and other apps. The original project is always copied alongside
  the media (in the folder its own source folder maps to), and the relinked copy is saved next to it
  as `<name>_relinked.<ext>`; if either already exists, both new files get the next number
  (`Name_1.ext` + `Name_1_relinked.ext`, then `_2`, ...), so nothing is ever overwritten and a run can
  always be repeated into the same folder.
- Never copies application cache (Premiere previews, media cache, peak files).
- Windows-authored projects: drive-letter and share mappings, and folder mappings for projects from
  another Mac. macOS boot-volume aliases (`/Volumes/Macintosh HD/...`) are treated as the same file as
  `/...`.
- `media_collector serve`: the engine as a JSON-lines server for the app (protocol version 1).
  Developer CLI: `python -m media_collector inspect|copy`.
- **macOS app** (SwiftUI): drop or choose a project (Finder and the Dock can also open project files
  with it directly), choose the destination with a free-space check (reliable on network volumes too),
  set the copy options with a live example path and file/size summary, **Start** with progress
  (a visibly alive progress bar and an elapsed-time counter) and Cancel (takes effect within a few
  seconds, including on network shares), and a report (copied / already there / problems, relink
  result, Reveal in Finder). The relink option is on by default. File-type badges (original artwork,
  not vendor logos) and an app icon.
- Packaged app: `app/scripts/build_app.sh` builds a self-contained "Media Collector.app" (Apple
  silicon, macOS 14+) with its own Python engine inside, plus a `.zip` and a `.dmg`. Signed with a
  Developer ID certificate when one is available (ad hoc otherwise), with notarization when
  credentials are configured.
- Clear messages for projects that are not supported yet: Final Cut libraries (`.fcpbundle`), DaVinci
  Resolve projects (`.drp`/`.drt`), EDL, After Effects XML (`.aepx`) — each says what to do instead.

### Known limitations
- Image sequences (EXR/TIFF/DPX) are not supported yet; OTIO image-sequence references are reported
  as warnings.
- Avid MXF-linked AAF and media embedded in an AAF are not supported.
- No proxy discovery for formats that do not record proxies (OTIO, FCP7 XML, AAF, Resolve exports).
- DaVinci Resolve project archives (`.drp`) and EDL are not supported.
- No path-mapping UI yet for Windows drives/shares (the engine supports it; see the open issues).

[Unreleased]: https://github.com/alvroga/media-collector/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/alvroga/media-collector/releases/tag/v0.2.2
