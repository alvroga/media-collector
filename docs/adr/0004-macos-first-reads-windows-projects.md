# ADR-0004: macOS is the runtime target; Windows-authored projects must still be readable

Status: Accepted
Date: 2026-09-23
Decided by: You (Claude recommended)

## Context
The tool is for macOS editors for now. But project files travel between platforms: the complex sample project was saved on Windows (`O:\...`, `\\?\N:\...`). Premiere itself remaps paths well when a project is opened on another OS, so the best workflow is "open on the Mac in Premiere, save, then run this tool". Projects that skip that step still need to work, ideally.

## Decision
- **Supported and tested platform: macOS only.** Packaging, filesystem handling and CI target macOS.
- **Readers must accept Windows-authored projects.** Paths from project files are stored as strings tagged with their original style (POSIX/Windows), never as host `Path` objects, so a Windows path is never mangled on macOS.
- **Locating media for a foreign-OS path**, in order: (1) user-supplied drive-letter/UNC-to-volume mapping (`O:` → `/Volumes/Media`), (2) the project's relative path where present, (3) search a user-given root by filename (and size, if known). Anything not found is reported, never guessed silently.
- **OS-specific code lives in one small platform module** (mount discovery, filesystem quirks) so a Windows runtime is a later, deliberate addition, not a rewrite.

## Consequences
- Removes drive letters and `\\?\` handling from the *destination* side entirely.
- Editors who already fixed paths through Premiere need no extra steps.
- Adds a path-mapping/search feature to the reader side; needs tests using the Windows-authored sample.
- Windows as a runtime target is not promised; a later ADR would supersede this one.
