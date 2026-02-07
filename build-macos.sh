pyinstaller -y --clean \
  --windowed \
  --name "LyricConductor" \
  --icon "assets/LyricConductor.icns" \
  --osx-bundle-identifier "com.lyricconductor" \
  --info-plist "build/macos/Info.plist" \
  app.py

codesign --force --deep --sign - "dist/LyricConductor.app"

#or if I have an apple id:
codesign --force --deep --options runtime \
  --sign "Developer ID Application: YOUR NAME (TEAMID)" \
  "dist/LyricConductor.app"
