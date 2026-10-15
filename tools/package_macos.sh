#!/usr/bin/env bash
# Build a relocatable macOS .app, ZIP and DMG from an already-generated game.
# The private disc image and generated game C are inputs to CI, never committed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FW="$ROOT/psxrecomp-v4"
BUILD_DIR="${BUILD_DIR:-$ROOT/build-macos-release}"
OUT_DIR="${OUT_DIR:-$ROOT/release-macos}"
VERSION="${VERSION:-$(tr -d ' \t\r\n' < "$ROOT/packaging/release/VERSION")}"
BUNDLE_VERSION="${VERSION#v}"
ARCH="$(uname -m)"
case "$ARCH" in
  arm64|aarch64) ARCH=arm64; PLATFORM_TAG=macos-arm64 ;;
  x86_64|amd64)  ARCH=x86_64; PLATFORM_TAG=macos-x64 ;;
  *) echo "Unsupported macOS architecture: $ARCH" >&2; exit 2 ;;
esac

BIN="$BUILD_DIR/ApeEscapeRecomp"
[ -x "$BIN" ] || BIN="$BUILD_DIR/psx-runtime"
[ -x "$BIN" ] || { echo "Runtime executable not found in $BUILD_DIR" >&2; exit 1; }
[ -d "$BUILD_DIR/assets/img" ] || { echo "Build did not stage launcher assets." >&2; exit 1; }
[ -f "$BUILD_DIR/bios/openbios.bin" ] || { echo "Build did not stage OpenBIOS." >&2; exit 1; }

mkdir -p "$OUT_DIR"
APP="$OUT_DIR/Ape Escape Recompiled.app"
CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
FRAMEWORKS="$CONTENTS/Frameworks"
RESOURCES="$CONTENTS/Resources"
rm -rf "$APP"
mkdir -p "$MACOS" "$FRAMEWORKS" "$RESOURCES"

# The wrapper is the Finder entry point. The real runtime stays beside its
# assets, as SDL_GetBasePath() expects, while user-writable data lives outside
# the signed app bundle in ~/Library/Application Support.
cp "$BIN" "$MACOS/ApeEscapeRecomp.bin"
cp -R "$BUILD_DIR/assets" "$MACOS/assets"
cp -R "$BUILD_DIR/bios" "$MACOS/bios"
cp "$ROOT/packaging/release/input.ini" "$MACOS/input.ini"

# Strip developer-only audit settings just as the Windows/Linux packagers do.
python3 - "$ROOT/game.toml" "$MACOS/game.toml" <<'PY'
import pathlib, sys
src = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
for marker in ("Audit-specific", "[audit]"):
    index = src.find(marker)
    if index >= 0:
        line_start = src.rfind("\n", 0, index)
        src = src[:max(0, line_start)].rstrip() + "\n"
        break
pathlib.Path(sys.argv[2]).write_text(src, encoding="utf-8")
PY

# The shared framework owns mod catalog validation, cache tagging and
# platform-specific overlay-toolchain staging. Do not duplicate that logic.
# shellcheck source=/dev/null
. "$FW/tools/release_overlay_stage.sh"
psx_release_stage_init "$FW"
psx_add_mod_catalog --build-path "$BUILD_DIR" --stage "$MACOS" --runtime-target psx-runtime >/dev/null

cp "$ROOT/LICENSE" "$RESOURCES/LICENSE"
cp "$ROOT/README.md" "$RESOURCES/README.md"
cp "$ROOT/RELEASE_NOTES.md" "$RESOURCES/RELEASE_NOTES.md"
cp "$ROOT/docs/AOT_OVERLAYS.md" "$RESOURCES/AOT_OVERLAYS.md"
cp "$ROOT/packaging/macos/START_HERE.txt" "$RESOURCES/START_HERE.txt"
[ ! -f "$ROOT/framework_pins.txt" ] || cp "$ROOT/framework_pins.txt" "$RESOURCES/framework_pins.txt"

# Precompile the repository's audited original-disc overlays for this exact
# host ABI. This is an optimization: interpreter/runtime compilation fallback
# remains enabled, so an AOT extraction failure must not block the macOS app.
# Stage separately so a failed attempt cannot leave a partial cache in the app.
AOT_STAGE="$ROOT/build-aot-macos-stage"
rm -rf "$AOT_STAGE"
mkdir -p "$AOT_STAGE"
if python3 "$FW/tools/aot_overlay_pipeline.py" release \
  --profile "$ROOT/aot/overlays.json" \
  --game-toml "$ROOT/game.toml" \
  --runtime-config "$MACOS/game.toml" \
  --runtime-build-dir "$BUILD_DIR" \
  --runtime-target psx-runtime \
  --recompiler "$FW/recompiler/build/psxrecomp-game" \
  --work-dir "$ROOT/build-aot-macos" \
  --stage "$AOT_STAGE" \
  --gcc gcc \
  --workers "${AOT_WORKERS:-2}"; then
  ditto "$AOT_STAGE" "$MACOS"
  rm -rf "$AOT_STAGE"
else
  AOT_STATUS=$?
  echo "::warning::Original-disc AOT overlay precompilation failed (exit $AOT_STATUS). Packaging the app with runtime compilation/interpreter fallback; no partial AOT cache will be shipped."
  find "$ROOT/build-aot-macos" -type f -name extract.log -print -exec tail -n 160 {} \; 2>/dev/null || true
  rm -rf "$AOT_STAGE"
fi

# Bundled Python + native recompiler lets the runtime compile overlays missed
# by the prebuilt cache, without requiring users to install developer tools.
psx_add_overlay_toolchain --stage "$MACOS" \
  --recomp-dir "$FW/recompiler/build" \
  --recomp-tools "$FW/tools" \
  --recomp-include "$FW/runtime/include" \
  --dl-cache "$ROOT/tools/_toolchain_cache" \
  --platform "$PLATFORM_TAG" >/dev/null

cat > "$MACOS/Ape Escape Recompiled" <<'SH'
#!/bin/sh
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
DATA="$HOME/Library/Application Support/Ape Escape Recompiled"
mkdir -p "$DATA"
export APE_ESCAPE_RECOMP_DATA_DIR="$DATA"
export SDL_JOYSTICK_HIDAPI_STEAM=1
# Seed first-run writable state from the packaged defaults. Never overwrite a
# player's configuration, mods, saves or compiled cache on later launches.
[ -f "$DATA/game.toml" ] || cp "$HERE/game.toml" "$DATA/game.toml"
[ -f "$DATA/input.ini" ] || cp "$HERE/input.ini" "$DATA/input.ini"
for tree in cache mods; do
  if [ -d "$HERE/$tree" ] && [ ! -e "$DATA/$tree" ]; then
    ditto "$HERE/$tree" "$DATA/$tree"
  fi
done
cd "$DATA"
exec "$HERE/ApeEscapeRecomp.bin" "$@"
SH
chmod 0755 "$MACOS/Ape Escape Recompiled"

cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Ape Escape Recompiled</string>
  <key>CFBundleDisplayName</key><string>Ape Escape Recompiled</string>
  <key>CFBundleIdentifier</key><string>io.github.nvdemu.apeescaperecomp</string>
  <key>CFBundleExecutable</key><string>Ape Escape Recompiled</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleVersion</key><string>$BUNDLE_VERSION</string>
  <key>CFBundleShortVersionString</key><string>$BUNDLE_VERSION</string>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

# Bundle Homebrew dylibs and rewrite install names to be relative to the app.
if command -v dylibbundler >/dev/null 2>&1; then
  dylibbundler -od -b -x "$MACOS/ApeEscapeRecomp.bin" \
    -d "$FRAMEWORKS" -p @executable_path/../Frameworks
fi

# Ad-hoc signing permits local testing without a paid Developer ID certificate.
# It is not notarization; the first launch instructions explain Gatekeeper.
codesign --force --deep --sign - "$APP"

# Keep a copy of the how-to beside the downloads as well as inside the bundle.
cp "$ROOT/packaging/macos/START_HERE.txt" "$OUT_DIR/START_HERE-macos.txt"
ZIP="$OUT_DIR/ApeEscapeRecomp-$VERSION-macos-$ARCH.zip"
DMG="$OUT_DIR/ApeEscapeRecomp-$VERSION-macos-$ARCH.dmg"
rm -f "$ZIP" "$DMG"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
hdiutil create -volname "Ape Escape Recompiled" -srcfolder "$APP" -ov -format UDZO "$DMG"
(
  cd "$OUT_DIR"
  shasum -a 256 "$(basename "$ZIP")" "$(basename "$DMG")" > "SHA256SUMS-macos-$ARCH.txt"
)
echo "App: $APP"
echo "ZIP: $ZIP"
echo "DMG: $DMG"
