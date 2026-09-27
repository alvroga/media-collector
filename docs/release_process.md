# Versioning and releases

**Scheme:** [Semantic Versioning](https://semver.org/), `MAJOR.MINOR.PATCH`. Until 1.0: a new capability
bumps MINOR, a fix bumps PATCH, and breaking changes to the engine API, the app protocol or output layout
are allowed in a MINOR bump but must be called out in the changelog.

**Three version numbers, one meaning:**
- Product version — `src/media_collector/__init__.py` `__version__` (pyproject reads it), mirrored in
  `app/Sources/MediaCollector/AppVersion.swift` and the top entry of `CHANGELOG.md`. `tests/test_version.py` fails if
  they disagree. The app bundles the engine of the same version.
- Protocol version — `PROTOCOL` in `src/media_collector/server.py` (`docs/agent_docs/app-protocol.md`). Bumped only when
  the app/engine message contract changes incompatibly.
- Project-file compatibility is documented per format in `docs/agent_docs/`, not versioned.

## Every change
Any user-visible change (feature, fix, behaviour change, new limitation) adds a line under
`## [Unreleased]` in `CHANGELOG.md` in the same commit, under **Added / Changed / Fixed / Removed /
Known limitations**. Purely internal work needs no entry.

## Cutting a release
1. Make sure `main` is green (`pytest`, `swift test` in `app/`, `ruff check`).
2. Pick the number. In `CHANGELOG.md` rename `[Unreleased]` to `[X.Y.Z] - YYYY-MM-DD`, add a fresh empty
   `[Unreleased]` above it, and update the compare links at the bottom.
3. Set the same number in `src/media_collector/__init__.py` and `app/Sources/MediaCollector/AppVersion.swift`.
4. Commit `Release vX.Y.Z`, then tag it: `git tag -a vX.Y.Z -m "vX.Y.Z"`, and push the commit and the tag.
5. Build the app with `app/scripts/build_app.sh` (output in `app/build/`: `.app`, `.zip`, `.dmg`; see Signing
   below), attach the `.zip`/`.dmg` to a GitHub Release and copy the changelog entry into the
   release notes.

**Signing and notarization.** `build_app.sh` signs with a "Developer ID Application" certificate when one is in the
keychain (or named in `SIGN_IDENTITY`), hardened runtime included, and notarizes and staples when a `notarytool`
keychain profile exists (default name `media-collector`, or `NOTARY_PROFILE`; create it once with
`xcrun notarytool store-credentials`). Without a certificate it signs ad hoc: the app runs on the Mac that built it
and on others after the user approves it once (System Settings > Privacy & Security > Open Anyway). Attach only
notarized builds to a release. The script prints at the end whether the result is signed and notarized.

Tagging and pushing a tag are outward-facing: do them only when the maintainer says so.
