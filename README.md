# DJVisualLyrics (macOS Apple Silicon)

This project scans a music root folder where each song lives in its own directory that contains:
- one .mp3
- optionally one .lrc
- optionally one .mp4 (preferred background)
- optionally one .png/.jpg/.jpeg (fallback background)

If no .mp4 and no image exists, embedded ID3 album art is extracted from the mp3 if present.

It then builds a local fingerprint DB (constellation peaks) and runs a full-screen lyric presenter:
- Letterboxed background image or looping video
- Lyrics overlaid at the top inside a dark translucent box
- Title, album, artist bottom-left
- Esc exits presentation mode and returns to the control window

## Setup (development)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

If PortAudio is missing:
```bash
brew install portaudio
```

## Run
```bash
python app.py
```

## Build a standalone macOS app
```bash
source .venv/bin/activate
pyinstaller --noconfirm --windowed --name "DJVisualLyrics" app.py
```

Output:
- dist/DJVisualLyrics.app
