#!/usr/bin/env bash
# Builds a self-contained "Media Collector.app" (Apple silicon) with the Python engine inside.
#
#   app/scripts/build_app.sh
#
# Output in app/build/: the .app, a .zip and a .dmg.
#
# Signing: if a "Developer ID Application" certificate is in the keychain (or SIGN_IDENTITY names one) the app is
# signed with it, every embedded binary included, with the hardened runtime. Otherwise it is signed ad hoc (runs
# on this Mac and any Mac where you approve it once).
# Notarization: if a notarytool keychain profile exists (default name "media-collector", or NOTARY_PROFILE) the
# app is notarized and stapled, so it opens on other Macs without a Gatekeeper warning. Create the profile once:
#   xcrun notarytool store-credentials media-collector --apple-id YOU --team-id TEAM
# Needs: Xcode command line tools, uv (https://github.com/astral-sh/uv), network for the first run.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APP_DIR="$ROOT/app"
BUILD="$APP_DIR/build"
NAME="Media Collector"
BUNDLE_ID="io.github.alvroga.media-collector"
PY_MINOR="3.13"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/src/media_collector/__init__.py")"
BUILD_NUMBER="$(git -C "$ROOT" rev-list --count HEAD 2>/dev/null || echo 1)"
ARCH="$(uname -m)"
APP="$BUILD/$NAME.app"
RES="$APP/Contents/Resources"

echo "==> Media Collector $VERSION (build $BUILD_NUMBER, $ARCH)"

echo "==> 1/6 Swift release build"
( cd "$APP_DIR" && swift build -c release )
BIN="$( cd "$APP_DIR" && swift build -c release --show-bin-path )/MediaCollector"

echo "==> 2/6 Relocatable Python $PY_MINOR"
export UV_PYTHON_INSTALL_DIR="$BUILD/python-runtime"
uv python install "$PY_MINOR" >/dev/null
PYSRC="$(find "$UV_PYTHON_INSTALL_DIR" -maxdepth 1 -type d -name "cpython-$PY_MINOR*" | head -1)"
[ -n "$PYSRC" ] || { echo "no Python runtime found under $UV_PYTHON_INSTALL_DIR" >&2; exit 1; }

echo "==> 3/6 Assemble the app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$RES/engine"
cp "$BIN" "$APP/Contents/MacOS/MediaCollector"
cp "$APP_DIR/Packaging/AppIcon.icns" "$RES/AppIcon.icns"
cp "$ROOT/LICENSE" "$ROOT/NOTICE" "$ROOT/THIRD_PARTY_NOTICES.md" "$RES/"
ditto "$PYSRC" "$RES/engine/python"
PY="$RES/engine/python/bin/python3"
uv pip install --quiet --python "$PY" --target "$RES/engine/site-packages" "$ROOT"

echo "==> 4/6 Trim and precompile the runtime"
PYLIB="$RES/engine/python/lib/python$PY_MINOR"
rm -rf "$PYLIB/test" "$PYLIB/idlelib" "$PYLIB/tkinter" "$PYLIB/turtledemo" "$PYLIB/ensurepip" \
       "$RES/engine/python/include" "$RES/engine/python/share"
find "$RES/engine/python/lib" -maxdepth 1 \( -name 'tcl*' -o -name 'tk*' -o -name 'libtcl*' -o -name 'libtk*' \) \
       -exec rm -rf {} + 2>/dev/null || true
find "$RES/engine" -name '__pycache__' -type d -prune -exec rm -rf {} +
"$PY" -m compileall -q "$PYLIB" "$RES/engine/site-packages" >/dev/null || true

echo "==> 5/6 Info.plist and signature"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>$NAME</string>
<key>CFBundleDisplayName</key><string>$NAME</string>
<key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
<key>CFBundleExecutable</key><string>MediaCollector</string>
<key>CFBundleIconFile</key><string>AppIcon</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>$VERSION</string>
<key>CFBundleVersion</key><string>$BUILD_NUMBER</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>LSApplicationCategoryType</key><string>public.app-category.video</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSPrincipalClass</key><string>NSApplication</string>
<key>NSHumanReadableCopyright</key><string>Copyright © 2026 Alvaro Robles. Apache License 2.0.</string>
<key>NSRemovableVolumesUsageDescription</key><string>Media Collector reads your project's media and copies it to the drive you choose.</string>
<key>NSNetworkVolumesUsageDescription</key><string>Media Collector reads your project's media and copies it to the network volume you choose.</string>
<key>NSDocumentsFolderUsageDescription</key><string>Media Collector reads your project's media and copies it where you choose.</string>
<key>NSDesktopFolderUsageDescription</key><string>Media Collector reads your project's media and copies it where you choose.</string>
<key>NSDownloadsFolderUsageDescription</key><string>Media Collector reads your project's media and copies it where you choose.</string>
<key>CFBundleDocumentTypes</key><array><dict>
<key>CFBundleTypeName</key><string>Editing project</string>
<key>CFBundleTypeRole</key><string>Viewer</string>
<key>LSHandlerRank</key><string>Alternate</string>
<key>CFBundleTypeExtensions</key><array>
<string>prproj</string><string>otio</string><string>xml</string><string>aaf</string>
<string>fcpxml</string><string>fcpxmld</string><string>aep</string></array>
</dict></array>
</dict></plist>
PLIST

IDENTITY="${SIGN_IDENTITY:-$(security find-identity -v -p codesigning 2>/dev/null \
  | sed -n 's/.*"\(Developer ID Application:[^"]*\)".*/\1/p' | head -1)}"
ENTITLEMENTS="$APP_DIR/Packaging/entitlements.plist"
if [ -n "$IDENTITY" ]; then
  echo "    signing with: $IDENTITY (hardened runtime)"
  # Inside-out: every Mach-O in the bundle first (the embedded Python), then the app itself.
  while IFS= read -r f; do
    if file -b "$f" | grep -q "Mach-O"; then
      codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$f"
    fi
  done < <(find "$APP/Contents" -type f ! -path "$APP/Contents/MacOS/*" ! -name '*.py' ! -name '*.pyc' ! -name '*.txt' ! -name '*.json')
  codesign --force --timestamp --options runtime --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$APP"
else
  echo "    no Developer ID certificate found: signing ad hoc"
  codesign --force --deep --sign - "$APP" >/dev/null 2>&1
fi
codesign --verify --deep --strict "$APP"

NOTARY_PROFILE="${NOTARY_PROFILE:-media-collector}"
NOTARIZED=no
if [ -n "$IDENTITY" ] && xcrun notarytool history --keychain-profile "$NOTARY_PROFILE" >/dev/null 2>&1; then
  echo "==> Notarizing (this waits for Apple, usually a few minutes)"
  NZIP="$BUILD/notarize.zip"
  rm -f "$NZIP"
  ditto -c -k --keepParent "$APP" "$NZIP"
  xcrun notarytool submit "$NZIP" --keychain-profile "$NOTARY_PROFILE" --wait
  rm -f "$NZIP"
  xcrun stapler staple "$APP"
  NOTARIZED=yes
elif [ -n "$IDENTITY" ]; then
  echo "    no notarytool profile \"$NOTARY_PROFILE\": skipping notarization (Macs will warn on first open)"
fi

echo "==> 6/6 Package"
ZIP="$BUILD/MediaCollector-$VERSION-$ARCH.zip"
DMG="$BUILD/MediaCollector-$VERSION-$ARCH.dmg"
rm -f "$ZIP" "$DMG"
ditto -c -k --keepParent "$APP" "$ZIP"
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -quiet -volname "$NAME $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG"
[ -n "$IDENTITY" ] && codesign --force --timestamp --sign "$IDENTITY" "$DMG"
rm -rf "$STAGE"

echo
du -sh "$APP" "$ZIP" "$DMG" | sed "s#$BUILD/##"
echo "Signed: ${IDENTITY:-ad hoc}   Notarized: $NOTARIZED"
echo "Built: $APP"
