from __future__ import annotations
import os
import glob
import hashlib
from dataclasses import dataclass
from typing import List, Optional
import yaml

from djapp.id3lib import read_id3_tags, extract_embedded_art

CONFIG_FILENAME = ".djvisuallyrics.yaml"
FPCACHE_EXT = ".djfp.npz"


@dataclass
class TrackInfo:
    track_id: str
    folder: str
    mp3_path: str
    lrc_path: Optional[str]
    bg_type: str
    bg_path: str
    title: str
    artist: str
    album: str
    fp_cache_path: str


def _first_or_none(patterns: List[str]) -> Optional[str]:
    for p in patterns:
        matches = glob.glob(p)
        if matches:
            return sorted(matches)[0]
    return None


def _make_track_id(mp3_path: str) -> str:
    h = hashlib.sha1(mp3_path.encode("utf-8")).hexdigest()[:12]
    return f"trk_{h}"


def _write_embedded_art_if_needed(mp3_path: str, target_jpg: str) -> Optional[str]:
    res = extract_embedded_art(mp3_path)
    if not res:
        return None
    data, _mime = res
    try:
        with open(target_jpg, "wb") as f:
            f.write(data)
        return target_jpg
    except Exception:
        return None


def scan_music_root(root: str) -> List[TrackInfo]:
    root = os.path.abspath(root)
    if not os.path.isdir(root):
        raise ValueError(f"Not a directory: {root}")

    tracks: List[TrackInfo] = []

    for entry in sorted(os.listdir(root)):
        song_dir = os.path.join(root, entry)
        if not os.path.isdir(song_dir):
            continue

        mp3 = _first_or_none([os.path.join(song_dir, "*.mp3")])
        if not mp3:
            continue

        lrc = _first_or_none([os.path.join(song_dir, "*.lrc")])

        mp4 = _first_or_none([os.path.join(song_dir, "*.mp4")])
        img = _first_or_none(
            [
                os.path.join(song_dir, "*.png"),
                os.path.join(song_dir, "*.jpg"),
                os.path.join(song_dir, "*.jpeg"),
            ]
        )

        if mp4:
            bg_type, bg_path = "video", mp4
        elif img:
            bg_type, bg_path = "image", img
        else:
            embedded_path = os.path.join(song_dir, "_embedded_art.jpg")
            if not os.path.exists(embedded_path):
                _write_embedded_art_if_needed(mp3, embedded_path)
            if os.path.exists(embedded_path):
                bg_type, bg_path = "image", embedded_path
            else:
                bg_type, bg_path = "image", ""

        tags = read_id3_tags(mp3)
        track_id = _make_track_id(mp3)

        fp_cache = os.path.join(song_dir, os.path.basename(mp3).rsplit(".", 1)[0] + FPCACHE_EXT)

        tracks.append(
            TrackInfo(
                track_id=track_id,
                folder=song_dir,
                mp3_path=mp3,
                lrc_path=lrc,
                bg_type=bg_type,
                bg_path=bg_path,
                title=tags.title,
                artist=tags.artist,
                album=tags.album,
                fp_cache_path=fp_cache,
            )
        )

    return tracks


def default_config_path(music_root: str) -> str:
    return os.path.join(os.path.abspath(music_root), CONFIG_FILENAME)


def write_config(root: str, tracks: List[TrackInfo], config_path: str) -> dict:
    cfg = {
        "version": 1,
        "music_root": os.path.abspath(root),
        "database": {"path": os.path.join(os.path.abspath(root), ".djvisuallyrics.sqlite")},
        "audio": {
            "sample_rate": 22050,
            "channels": 1,
            "device": None,
            "block_seconds": 1.0,
            "listen_seconds": 12,
            "match_every_seconds": 1.0,
            "min_confidence": 20,
        },
        "fingerprinting": {
            "fft_size": 4096,
            "hop_size": 512,
            "peak_neighborhood": [12, 20],
            "max_peaks_per_frame": 6,
            "fanout": 8,
            "min_dt": 1,
            "max_dt": 60,
        },
        "display": {
            "screen_index": 0,
            "fullscreen": True,
            "lyrics": {
                "font_family": "Helvetica",
                "font_size": 44,
                "margin_top": 30,
                "box_opacity": 0.65,
                "box_padding": 18,
            },
            "meta": {"font_family": "Helvetica", "font_size": 22, "margin_left": 26, "margin_bottom": 22},
        },
        "tracks": [],
    }

    for t in tracks:
        cfg["tracks"].append(
            {
                "id": t.track_id,
                "title": t.title,
                "album": t.album,
                "artist": t.artist,
                "audio_file": t.mp3_path,
                "lrc_file": t.lrc_path,
                "fingerprint_cache": t.fp_cache_path,
                "background": {"type": t.bg_type, "path": t.bg_path},
            }
        )

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True)

    return cfg
