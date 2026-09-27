# ADR-0005: Copy full files only — no trimming, handles, transcoding or rewrapping

Status: Accepted
Date: 2026-09-23
Decided by: You (Claude agreed)

## Context
Resolve's Media Management can copy "used media and trim keeping N frame handles", and can transcode. Doing that means cutting/re-encoding or rewrapping files: codec and container support per format, quality choices, timecode/metadata preservation, and many failure modes.

## Decision
The tool copies whole files, byte-for-byte, and verifies them. No trimming, no handles, no transcoding, no rewrapping, no "consolidate". Scope is chosen at the file level ("all media", "used media", chosen sequences).

## Consequences
- Output is verifiable (checksums match the source) and safe for any codec/camera format, including R3D/MXF/BRAW.
- Copies can be larger than a trimmed Resolve export; that is accepted.
- Readers do not need in/out ranges; the media-reference model stays file-level.
- Revisiting this needs a new ADR that supersedes this one.
