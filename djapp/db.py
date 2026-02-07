from __future__ import annotations
import json
import sqlite3
from typing import Dict, List, Tuple

Hash = Tuple[int, int]  # (hash32, t_anchor_frame)


class FingerprintDB:
    def __init__(self, path: str):
        self.path = path

    def _conn(self):
        return sqlite3.connect(self.path, timeout=5.0)

    def init_schema(self):
        with self._conn() as c:
            c.execute(
                """
            CREATE TABLE IF NOT EXISTS tracks(
              track_id TEXT PRIMARY KEY,
              meta_json TEXT NOT NULL
            )
            """
            )
            c.execute(
                """
            CREATE TABLE IF NOT EXISTS hashes(
              hash32 INTEGER NOT NULL,
              track_id TEXT NOT NULL,
              t_frame INTEGER NOT NULL,
              FOREIGN KEY(track_id) REFERENCES tracks(track_id)
            )
            """
            )
            c.execute("CREATE INDEX IF NOT EXISTS idx_hash32 ON hashes(hash32)")
            c.execute("CREATE INDEX IF NOT EXISTS idx_hash32_track ON hashes(hash32, track_id)")
            c.commit()

    def upsert_track(self, track_id: str, meta: dict):
        meta_json = json.dumps(meta, ensure_ascii=False)
        with self._conn() as c:
            c.execute(
                """
              INSERT INTO tracks(track_id, meta_json) VALUES(?, ?)
              ON CONFLICT(track_id) DO UPDATE SET meta_json=excluded.meta_json
            """,
                (track_id, meta_json),
            )
            c.commit()

    def replace_hashes(self, track_id: str, hashes: List[Hash]):
        with self._conn() as c:
            c.execute("DELETE FROM hashes WHERE track_id=?", (track_id,))
            c.executemany(
                "INSERT INTO hashes(hash32, track_id, t_frame) VALUES(?, ?, ?)",
                [(int(h), track_id, int(t)) for (h, t) in hashes],
            )
            c.commit()

    def all_tracks_meta(self) -> Dict[str, dict]:
        out = {}
        with self._conn() as c:
            for track_id, meta_json in c.execute("SELECT track_id, meta_json FROM tracks"):
                out[track_id] = json.loads(meta_json)
        return out

    def query_hashes(self, hash32_values: List[int]) -> List[Tuple[int, str, int]]:
        if not hash32_values:
            return []
        q_marks = ",".join("?" for _ in hash32_values)
        sql = f"SELECT hash32, track_id, t_frame FROM hashes WHERE hash32 IN ({q_marks})"
        with self._conn() as c:
            return list(c.execute(sql, hash32_values))
