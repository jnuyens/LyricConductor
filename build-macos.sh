#!/usr/bin/env bash
set -euo pipefail

source .venv/bin/activate

rm -rf dist build

python -m PyInstaller -y --clean LyricConductor.spec

APP="dist/LyricConductor.app"
PLIST="$APP/Contents/Info.plist"

# Inject mic permission string (works even if spec support is flaky)
/usr/libexec/PlistBuddy -c 'Print :NSMicrophoneUsageDescription' "$PLIST" >/dev/null 2>&1 || \
/usr/libexec/PlistBuddy -c 'Add :NSMicrophoneUsageDescription string "LyricConductor needs microphone access to detect music timing and sync lyrics."' "$PLIST"

# Ensure stable bundle id
/usr/libexec/PlistBuddy -c 'Set :CFBundleIdentifier com.lyricconductor' "$PLIST" >/dev/null 2>&1 || true

# Re-sign after plist modification
codesign --force --deep --sign - "$APP"

echo "Verify:"
plutil -p "$PLIST" | grep -E "CFBundleIdentifier|NSMicrophoneUsageDescription" || true

tccutil reset Microphone
open "$APP"

#or if I have an apple id:
#codesign --force --deep --options runtime \
#  --sign "Developer ID Application: YOUR NAME (TEAMID)" \
#  "dist/LyricConductor.app"
