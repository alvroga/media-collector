# ADR-0003: "Keep structure" means the on-disk folder tree

Status: Accepted
Date: 2026-09-23
Decided by: You (Claude recommended, you agreed)

## Context
A project's media can be organised two ways: the folders the files sit in on disk, and the editor's own bin tree (Premiere bins). The tool must preserve "structure" when copying, across many formats. Bins exist in `.prproj` and some XML, but not in EDL, most OTIO, or AAF.

## Decision
Structure preservation is based on the **on-disk folder tree** of each media file: find the common root, keep N levels below it (configurable depth), and mirror that under the destination. Bin hierarchy is not used for output layout.

## Consequences
- Works identically for every format, since every format has file paths. This is what keeps the tool universal.
- Matches what editors expect from Resolve/Tidy-style consolidation.
- Files from different drives/volumes need a rule to avoid collisions (e.g. a per-volume top folder). Detailed in the folder-structure engine design.
- Bin information may still be kept in the media-reference model as optional metadata; a bin-based layout could be added later as an opt-in mode, but is not planned (ADR would be needed).
- Proxies follow the same rule: mirrored by their own on-disk tree, kept paired with their originals in the path map used for relinking.

## Update 2026-09-23 — option semantics
The user-facing control mirrors DaVinci Resolve: "preserve hierarchy after N folder levels" = drop the first N folder levels of each source path (counted from the root; a Windows drive letter or UNC server/share counts as a level) and keep everything below. Flatten is opt-in only. This replaces the earlier "common root + keep N levels" sketch. Collisions get a `_2`, `_3`… suffix and are reported, never overwritten. Wording may change; the exact Resolve semantics for Mac `/Volumes/<name>` are still to be confirmed.
