# Premiere `.prproj` format — findings

Status: **research notes from two real samples** (Premiere project `Version="3"` / `Project Version="45"`), not a spec. Verify against new samples before relying on any detail. Probe script: `research/prproj_probe.py`. Samples live in `assets/` (git-ignored).

## Container
- gzip-compressed XML. Root `<PremiereData>`; every top-level child is an object with `ObjectID` (integer, file-local) or `ObjectUID` (GUID). Cross-references use `ObjectRef="<id>"` / `ObjectURef="<uid>"`.
- Sizes: simple sample 28 KB gz (0.4 MB XML); complex sample 76 MB gz → **900 MB XML, ~1.95M objects, 222 sequences, 6,937 Media objects**. Must be **stream-parsed** (`iterparse`, handle top-level children, `clear()`); prototype does it in ~22 s / ~860 MB RSS, keeping all refs in memory. Memory can be cut further by keeping only ref edges for object types on the path to Media.

## Object chain (what matters for media)
```
RootProjectItem ─ ProjectItemContainer/Items/Item ─▶ BinProjectItem (recursive) | ClipProjectItem
ClipProjectItem ─ <MasterClip ObjectURef> ─▶ MasterClip ─ Clips/Clip ─▶ VideoClip | AudioClip
VideoClip/AudioClip ─ Clip/Source ─▶ VideoMediaSource | AudioMediaSource ─ MediaSource/Media ─▶ Media
Media: FilePath, ActualMediaFilePath, RelativePath, Title, OfflineReason, MediaFileHistory0..n
```
- **Bins** (names via `ProjectItem/Name`) are Premiere's own hierarchy, separate from the on-disk one, which comes from `Media` paths. ADR-0003: output layout follows the on-disk tree; bins are optional metadata only.
- **Sequences are also ClipProjectItems** whose MasterClip leads to `VideoSequenceSource`/`AudioSequenceSource` → `<Sequence ObjectURef>`. Sequence → `TrackGroups` → tracks → track items → `SubClip` → MasterClip/Clip → Source → Media. Nested sequences work through the same chain.
- **Generic reachability works**: "all Media reachable from Sequence X by following any ref" gave correct results on both samples and avoids modelling every track/effect class. Caveat: it returns media of any *master clip* touched, which is "used clips", not "used ranges" (fine for v1; handles/trim would need in/out from SubClip).

## Gotchas found in the samples
1. **Paths from another OS.** Complex sample was made on Windows: `O:\...`, UNC-style `\\?\N:\...`; simple sample is macOS `/Volumes/...`. Reader must keep the original string and have a **path-mapping layer** (drive letter/volume → local root) to locate files on the machine running the tool.
2. **Offline is normal.** In the complex sample virtually every Media had `OfflineReason` set (drives not mounted). `OfflineReason` reflects the state when saved, not now → always **check existence at run time**, report missing files, and never treat the flag as truth.
3. **Same file, many Media objects.** Repeated identical paths (e.g. one R3D referenced by 8+ Media). Deduplicate by normalized path.
4. **Non-file Media.** e.g. `FilePath` = `1398035014`, Title `SyntheticTranscript` (DataStream, different `ImplementationID`). Filter: require a plausible path; skip data-only/synthetic media.
5. **Proxies are explicitly linked (resolved).** A `VideoMediaSource`/`AudioMediaSource` carries `MediaSource/Content/ProxyMedia ObjectURef="<uid>"` alongside `MediaSource/Media` (the original). The referenced `Media` is the proxy file (e.g. `Q:\EMAM_Proxies\...mp4`). Complex sample: 3,619 `ProxyMedia` links; simple sample: none. So the probe's "reachable Media" mixes originals and proxies — the reader must **tag each Media as `original` or `proxy`** by which slot references it, and pair them (original ↔ proxy). **Pairing is many-to-many**: in the complex sample 107 of 854 proxy files serve more than one original path, and one original has two proxies — model as `paired_paths` sets, not 1:1. Reader result (complex): 3,222 distinct files = 2,368 originals + 854 proxies (766 originals have a proxy), 524 non-file Media skipped, 1,004 in the project but used by no sequence. Unverified: `AudioProxy`/`AudioProxyItem`/`ProxyStreamIndex` (2,636 each) look like audio-side proxy bookkeeping; `IsProxy` (1,591) meaning unknown.
6. **Same clip, two locations.** Simple sample has the same MXF under `/Volumes/random-tests/296800/00/...` and `/.../296800/...` (relinked). Dedup by path will not merge these; report both.
7. **Multi-file media.** R3D (`.RDM/.RDC/*_001.R3D`), MXF `PRIVATE/XDROOT` cards and similar: copying the single referenced file may break the clip's package/sidecars (see backlog: sidecar handling).
8. `RelativePath` (relative to the project file) exists alongside the absolute path — useful fallback for locating media when the project has moved.

## Cache references (checked on a test project)
- **Preview renders** are referenced as ordinary `Media` objects (complex sample: ~500 `Rendered - *.mov` under `Adobe Premiere Pro Video Previews/*.PRV`) — but only once a preview has actually been rendered. A project with no renders has none; `PreviewRenderingPresetPath` / `PreviewFormatIdentifier` are just settings, not files.
- **Audio peak/conform files** are *not* Media objects: they appear as `<ConformedAudioPath>` / `<PeakFilePath>` fields (`.../Application Support/Adobe/Common/Peak Files/<date>/<name> 48000.pek`) on audio stream objects. The reader ignores them (only `Media` path fields are read), and the relink writer must leave them alone (Premiere regenerates them).
- Proxies: one `<ProxyMedia>` element per video *and* per audio source, so N proxied clips give 2N `ProxyMedia` links (test project: 9 proxies, 18 links).

## Open questions
- Audio-proxy elements (`AudioProxy*`, `IsProxy`) semantics.
- Multicam / `SubClip` in/out ranges, and dynamic-link (After Effects/Audition) items — not seen in samples.
- Premiere format version differences (samples are one version).
- **Relink (write-back) feasibility**: paths live in a handful of `Media` fields (`FilePath`, `ActualMediaFilePath`, `RelativePath`, `MediaFileHistory0..n`), so a relinked project can be produced by a streaming rewrite of those fields only, leaving everything else byte-identical. **Confirmed 2026-09-23 (Premiere, macOS, test project):** rewriting only `FilePath`, `ActualMediaFilePath`, `RelativePath`, `MediaFileHistory*` and the project's `lastknowngoodprojectpath` is enough — the project opens with no link prompt, nothing offline, proxies attached. `ModificationState`/`FileKey`/`CCFileModTime` were left untouched (the copier preserves file mtimes). Not yet tested: Windows-authored projects, very large projects, files whose mtime differs. `RelativePath` must be recomputed relative to the *new* project location.
