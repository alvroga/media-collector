# Changelog

All notable changes to Media Collector are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/) (`0.MINOR.PATCH` until the first stable 1.0).
This file is what users and contributors read.

## [Unreleased]

### Added
- The copy screen shows it is alive: the icon pulses, the progress bar breathes and a band of light travels along
  the whole bar even when the percentage is not changing (also at 2%), and an elapsed-time counter ticks every second (a big file or a slow network share
  no longer looks stalled).

### Changed
- The project file now travels with the media: the original project is always copied (verified) into the
  folder its own source folder maps to under the same layout rule as the media (e.g. `Show/`, next to
  `Show/MediaFiles/`; the destination root if that folder is above the skipped levels), and the relinked one is saved next to it as `<name>_relinked.<ext>`. The original is copied
  even when relinking is off. Nothing is overwritten: if either file already exists, both new files get the next
  number, `Name_1.ext` + `Name_1_relinked.ext`, then `_2`, and so on, so a pair always stays matched. Re-running
  into the same folder saves a new numbered pair instead of failing.

### Fixed
- Cancel now takes effect within a few seconds on network shares. Data is flushed to the destination every
  32 MB instead of once at the end of each file, so a slow share no longer hides a long, uncancellable transfer
  in one final flush, and the progress bar follows the real transfer. The cancelling screen explains what is
  happening.
- Network volumes (SMB/NFS) no longer show "Zero KB free — not enough space" and block the copy. The app asked
  macOS for "important usage" capacity, which is 0 on many network shares; it now also reads the plain available
  capacity and `statfs` and takes the largest, treats a 0 on a network volume as unknown, and on network volumes
  a low reading is only a warning (Start stays available).

## [0.2.1] - 2026-09-24

### Added
- "Select All" / "Select None" button for the sequence list (shown when a project has more than one).

### Changed
- The window grows to fit the whole setup screen (up to the screen height) so the scroll bar does not
  appear by default.

## [0.2.0] - 2026-09-24

### Changed
- Environment variables are `MEDIA_COLLECTOR_REPO`, `MEDIA_COLLECTOR_PYTHON` and `MEDIA_COLLECTOR_SNAPSHOT_DIR`;
  partial copies use the suffix `.mc-partial`.

### Fixed
- Files and relinked projects are moved into place with an exclusive rename, so a file that appears at the
  destination during a copy is never replaced (on filesystems without it, a check-then-replace fallback is used).
- A failed relink no longer leaves a partial file or a half-built `.fcpxmld` bundle that blocks the retry; if
  re-reading the finished project fails, the file is kept and a note explains it.
- A path with no file name no longer fails the whole plan; it is left out and counted.
- `.aep` footage records that cannot be read are reported as a warning instead of dropped silently.
- The app shows how many project references were ignored because they are not files on disk.
- The sequence list scrolls when there are many sequences.
- The engine is given a few seconds to shut down cleanly when the app stops it.
- Developer CLI: Ctrl-C cancels cleanly, and a bad `--map` or negative `--keep-from-level` is a usage error.
- The relinked project is now saved inside the project folder (when one is set), next to the copied media.
- The project folder name can no longer contain `..` or start with `/` to escape the destination.
- Engine errors are written to `~/Library/Logs/Media Collector/engine.log` instead of being discarded.
- A project path containing `..` (or `.`) can no longer make a copy land outside the destination folder.
- A file that appears at the destination while a copy is in flight is reported as a conflict instead of
  being overwritten.

### Added
- Packaged app: `app/scripts/build_app.sh` builds a self-contained "Media Collector.app" (Apple
  silicon, macOS 14+) with its own Python engine inside, so no Python or developer tools are needed to run
  it, plus a `.zip` and a `.dmg`. Ad-hoc signed; Developer ID signing and notarization are not part of it.
  Finder and the Dock can open project files with the app.
- Read After Effects projects (`.aep`, read-only): footage locations are found; all footage counts as
  used, the project has no sequences (so no Scope choice), and it cannot be relinked.
- Clear messages for projects we cannot read yet: Final Cut libraries (`.fcpbundle`), DaVinci Resolve
  projects (`.drp`/`.drt`), EDL, `.aepx` — each says what to do instead.
- App: file-type badges (Premiere, FCP XML, FCPXML, OTIO, AAF) on the drop zone and for the loaded
  project; original artwork, not vendor logos.
- App icon (shown in the Dock for dev builds; `.icns` ready for packaging).
- App: choose the destination folder right under the project (or drop a folder), with free-space check.
- App: **Start** button, live progress with Cancel, and a report (copied / already there / problems,
  relink result, Reveal in Finder). The relink option ("Relink the project to the copied files") is on by
  default.

### Fixed
- Opening a Final Cut `.fcpxmld` bundle (dropped or chosen) failed with "not a file"; bundles and the
  `Info.fcpxml` inside them now open as the same project.
- App: errors while opening a project were not shown on the empty drop zone; they are now.

### Changed
- App: cards now stand clearly off the window background (darker window, lighter bordered cards; light
  mode adjusted to match).
- Messages no longer say "yet": relinking simply is or is not available for a format, and the unsupported-
  format messages say what to do instead.
- App: the relink option is greyed out, unchecked and locked for formats that can be read but not relinked
  (currently After Effects), with a one-line explanation; the engine reports `can_relink` per project.
- App: the Scope choice is hidden for projects that have no sequences (After Effects).
- App: the drop zone lists the extensions (.prproj .otio .xml .aaf .fcpxmld .aep) under the file badges.
- App: the destination shows the macOS icon of its volume (internal disk, external drive or network
  volume) and what kind it is.
- App: the folder example shows the path as it will land, so folders drop off the front as you skip more
  levels; the "Scope" card (entire project or chosen sequences; formerly "Take") is shown whenever a project has
  sequences; the
  copy screen lists the files just finished.
- App icon: now the designed artwork (`app/Branding/AppIcon.svg`), converted to `AppIcon.png` and
  `AppIcon.icns` by `app/scripts/make_icon.py`.
- App: small polish — card titles carry icons, the options card is titled "Options", the Start bar
  reads "24 files · 559.6 MB → TEST", and the empty drop zone no longer crowds its border.
- App: "Include proxies" is on by default when the project has proxies (they are part of the project),
  and the report explains why references were left pointing at their original location.
- App: the folder structure is always kept. There is no on/off switch and no "put everything in a
  folder" option; the only folder setting is how many leading levels to skip, shown with a labelled
  "Example" path.

## [0.1.0] - 2026-09-24

First tagged version: a working engine, a developer CLI, and the first milestone of the macOS app.

### Added
- **Read** project files from Premiere Pro (`.prproj`), Final Cut Pro 7 XML, FCPXML (including
  `.fcpxmld` bundles), OpenTimelineIO (`.otio`) and AAF (`.aaf`). Every reader produces the same media
  model, and all five agree on the same project in our cross-format test fixture.
- **Copy** the media a project uses, whole files only, with SHA-256 verification, atomic writes, skip of
  identical files, no overwriting, dry run, byte-level progress, cancellation and parallel workers.
- **Keep the folder structure** (Resolve-style "skip the first N folder levels"), optional flattening,
  optional project-name folder, collision handling (`_2` suffix).
- **Choose what to take**: entire project or selected sequences; used media only or all media.
- **Proxies**: Premiere proxies (and FCPXML `proxy-media`) are paired with their originals and can be
  copied with them.
- **Relink**: write a new copy of the project pointing at the copied files, for Premiere (including
  proxies), FCP7 XML, FCPXML, OTIO and AAF. Sources are never modified. Verified by opening the results in
  Premiere, Final Cut Pro and other apps.
- Never copies application cache (Premiere previews, media cache, peak files).
- Windows-authored projects: drive-letter and share mappings, and folder mappings for projects from
  another Mac.
- macOS boot-volume aliases (`/Volumes/Macintosh HD/...`) are treated as the same file as `/...`.
- `media_collector serve`: the engine as a JSON-lines server for the app (protocol version 1).
- Developer CLI: `python -m media_collector inspect|copy`.
- macOS app (SwiftUI, development build): open a project, choose sequences, set the copy options with a
  live example path and file/size summary. Copying and relinking from the app are not in 0.1.0 yet.

### Known limitations
- Image sequences (EXR/TIFF/DPX) are not supported yet; OTIO image-sequence references are reported as
  warnings.
- Avid MXF-linked AAF and media embedded in an AAF are not supported.
- No proxy discovery for formats that do not record proxies (OTIO, FCP7 XML, AAF, Resolve exports).
- DaVinci Resolve project archives (`.drp`) and EDL are not supported.
- The app is a development build (run with `swift run`); it is not packaged or signed.

[Unreleased]: https://github.com/alvroga/media-collector/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/alvroga/media-collector/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/alvroga/media-collector/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/alvroga/media-collector/releases/tag/v0.1.0
