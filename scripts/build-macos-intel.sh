#!/bin/bash
# Build-machine only. The app recipient installs neither Python nor Homebrew.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Darwin || "$(uname -m)" != x86_64 ]]; then
  echo 'Build requires an Intel Mac or an x86_64 macOS runner.' >&2
  exit 1
fi
python3 -m venv .venv
P="$PWD/.venv/bin/python"
export CMAKE_ARGS='-DGGML_METAL=OFF -DGGML_NATIVE=OFF -DGGML_AVX512=OFF'
"$P" -m pip install -r requirements.txt
"$P" scripts/preflight.py
QT_QPA_PLATFORM=offscreen "$P" -m unittest discover -s tests -v
"$P" -m PyInstaller --noconfirm --clean LocalDocRenamer.spec
# PyInstaller scans binary dependencies and rewrites Mach-O paths. Verify the final bundle
# on a clean Mac; don't rely on the Homebrew environment of the build machine.
"$P" scripts/release-manifest.py dist/LocalDocRenamer.app
codesign --force --deep --sign - dist/LocalDocRenamer.app
codesign --verify --deep --strict dist/LocalDocRenamer.app
"$PWD/dist/LocalDocRenamer.app/Contents/MacOS/LocalDocRenamer" --self-test "$PWD/release-macos-selftest.json"
mkdir -p release
stage="$(mktemp -d "$PWD/release/dmg-stage.XXXXXX")"
trap 'rm -rf "$stage"' EXIT
cp -R dist/LocalDocRenamer.app "$stage/LocalDocRenamer.app"
ln -s /Applications "$stage/Applications"
hdiutil create -volname LocalDocRenamer -srcfolder "$stage" -ov -format UDZO release/LocalDocRenamer-macOS-Intel.dmg
printf '%s\n' 'DMG candidate created. Signing/notarization and acceptance testing are still required.'
