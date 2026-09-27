# Media Collector

**Collect a project's media. Keep its folder structure.**

Media Collector reads a video edit project, finds every media file its timelines actually use (proxies
included), and copies them to a folder or drive you choose, **keeping the folder structure** instead of dumping
everything into one flat folder. It can also write a relinked copy of the project that points at the copies.

It is a native macOS app (SwiftUI) over a Python engine. Status: early development, macOS 14+ on Apple silicon.

## What it does

- **Reads** Premiere Pro (`.prproj`), Final Cut Pro XML (`.xml`) and FCPXML (`.fcpxml`, `.fcpxmld`),
  OpenTimelineIO (`.otio`), AAF (`.aaf`) and After Effects (`.aep`, read only) projects. Projects made on
  Windows are readable too.
- **Copies** only what the chosen sequences use (or everything the project references), with the option to
  include proxies. You choose how many top folder levels to skip; the rest of each file's path is kept.
- **Never overwrites.** Every file is copied whole, then re-read and checked with SHA-256. A file already at the
  destination is skipped if identical, and reported (never replaced) if different. Sources are only read.
- **Relinks.** With the option on, the project is saved again with every path pointing at the copies. Both the
  original project and the relinked one (`Name_relinked.ext`) are copied next to the media; if either already
  exists, both new files get the next number (`Name_1.ext`, `Name_1_relinked.ext`, ...).
- **Cancels cleanly**, keeps the files already copied, and reports anything that needs attention.

## Install

There are no published builds yet. Build the app yourself:

```bash
app/scripts/build_app.sh        # needs Xcode command line tools and uv
open "app/build/Media Collector.app"
```

For development: `cd app && swift run MediaCollector` (the engine runs from the repository's Python
environment; see [docs/agent_docs/how-to-run.md](docs/agent_docs/how-to-run.md)).

## Known limitations

Windows drive/share mapping has no UI yet, image sequences are not supported, `.aep` projects cannot be relinked,
and proxies are only found where the project records them. See the open issues for the full list.

## Documentation

[docs/agent_docs/](docs/agent_docs/README.md) has the architecture, the app/engine protocol and the run guide;
[docs/adr/](docs/adr/) has the decisions behind it. Contributions are welcome, see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache License 2.0, see [LICENSE](LICENSE) and [NOTICE](NOTICE). Third-party components:
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Adobe, Premiere Pro, After Effects, Final Cut Pro, DaVinci Resolve and Avid are trademarks of their respective
owners. Media Collector is an independent project and is not affiliated with or endorsed by any of them.
