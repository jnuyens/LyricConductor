from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC


@dataclass
class TrackTags:
    title: str
    artist: str
    album: str


def read_id3_tags(mp3_path: str) -> TrackTags:
    audio = MP3(mp3_path)
    tags = audio.tags
    title = ""
    artist = ""
    album = ""

    if tags:
        if "TIT2" in tags:
            title = str(tags["TIT2"])
        if "TPE1" in tags:
            artist = str(tags["TPE1"])
        if "TALB" in tags:
            album = str(tags["TALB"])

    if not title:
        title = mp3_path.split("/")[-1]
    if not artist:
        artist = "Unknown Artist"
    if not album:
        album = "Unknown Album"

    return TrackTags(title=title.strip(), artist=artist.strip(), album=album.strip())


def extract_embedded_art(mp3_path: str) -> Optional[Tuple[bytes, str]]:
    """Return (image_bytes, mime) if embedded art exists, else None."""
    try:
        id3 = ID3(mp3_path)
    except Exception:
        return None

    apics = id3.getall("APIC")
    if not apics:
        return None

    apic: APIC = apics[0]
    return apic.data, apic.mime
