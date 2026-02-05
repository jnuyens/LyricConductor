from __future__ import annotations
import time
import threading
import numpy as np
import sounddevice as sd

from djapp.audioio import resolve_input_device
from djapp.fingerprint import Fingerprinter
from djapp.drift import DriftModel
from djapp.lrc import load_lrc


class LiveMatcher:
    def __init__(self, cfg: dict, db):
        self.cfg = cfg
        self.db = db
        self.meta_by_id = db.all_tracks_meta()

        fp_cfg = cfg["fingerprinting"]
        audio_cfg = cfg["audio"]

        self.sample_rate = int(audio_cfg["sample_rate"])
        self.channels = int(audio_cfg["channels"])
        self.block_seconds = float(audio_cfg["block_seconds"])
        self.listen_seconds = float(audio_cfg["listen_seconds"])
        self.match_every = float(audio_cfg["match_every_seconds"])
        self.min_conf = int(audio_cfg["min_confidence"])
        self.device = resolve_input_device(audio_cfg.get("device"))

        self.fp = Fingerprinter(
            sample_rate=self.sample_rate,
            fft_size=int(fp_cfg["fft_size"]),
            hop_size=int(fp_cfg["hop_size"]),
            peak_neighborhood=tuple(fp_cfg["peak_neighborhood"]),
            max_peaks_per_frame=int(fp_cfg["max_peaks_per_frame"]),
            fanout=int(fp_cfg["fanout"]),
            min_dt=int(fp_cfg["min_dt"]),
            max_dt=int(fp_cfg["max_dt"]),
        )

        self._lock = threading.Lock()
        self._running = False

        self.current_track_id = None
        self.current_conf = 0
        self.current_wall_t0 = None
        self.drift = DriftModel()
        self.lrc = None

        self.buf_n = int(self.listen_seconds * self.sample_rate)
        self.buf = np.zeros(self.buf_n, dtype=np.float32)
        self.buf_pos = 0

        self._thread = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def get_state(self):
        with self._lock:
            return {
                "track_id": self.current_track_id,
                "confidence": self.current_conf,
                "meta": self.meta_by_id.get(self.current_track_id) if self.current_track_id else None,
                "track_time": self._current_track_time_locked(),
                "lrc": self.lrc,
            }

    def _current_track_time_locked(self):
        if self.current_wall_t0 is None:
            return None
        wall_now = time.monotonic()
        wall_rel = wall_now - self.current_wall_t0
        return max(0.0, float(self.drift.predict(wall_rel)))

    def _append_audio(self, x: np.ndarray):
        n = x.shape[0]
        if n >= self.buf_n:
            self.buf[:] = x[-self.buf_n :]
            self.buf_pos = 0
            return
        end = self.buf_pos + n
        if end <= self.buf_n:
            self.buf[self.buf_pos : end] = x
        else:
            k = self.buf_n - self.buf_pos
            self.buf[self.buf_pos :] = x[:k]
            self.buf[: end - self.buf_n] = x[k:]
        self.buf_pos = (self.buf_pos + n) % self.buf_n

    def _get_buffer_ordered(self):
        return np.concatenate([self.buf[self.buf_pos :], self.buf[: self.buf_pos]])

    def _match_segment(self, audio_segment: np.ndarray):
        hashes = self.fp.fingerprint_audio(audio_segment)
        if not hashes:
            return None

        hash32_vals = [h for (h, _t) in hashes]
        rows = self.db.query_hashes(hash32_vals)
        if not rows:
            return None

        live_t_by_hash = {}
        for h, t in hashes:
            live_t_by_hash.setdefault(int(h), []).append(int(t))

        votes = {}
        for h, track_id, db_t in rows:
            h = int(h)
            db_t = int(db_t)
            for live_t in live_t_by_hash.get(h, []):
                off = db_t - int(live_t)
                d = votes.setdefault(track_id, {})
                d[off] = d.get(off, 0) + 1

        best_track = None
        best_conf = 0
        best_off = 0
        for track_id, offs in votes.items():
            off, conf = max(offs.items(), key=lambda kv: kv[1])
            if conf > best_conf:
                best_conf = conf
                best_track = track_id
                best_off = off

        if best_track is None:
            return None

        hop = self.fp.hop_size
        off_sec = (best_off * hop) / self.sample_rate
        #return {"track_id": best_track, "confidence": int(best_conf), "offset_sec": float(off_sec)}
        # off_sec refers to the start of the audio_segment (the window)
        # Convert to "now" by adding the window duration
        now_sec = float(off_sec + self.listen_seconds)
        return {"track_id": best_track, "confidence": int(best_conf), "offset_sec": float(now_sec)}

    def _switch_track(self, track_id: str, offset_sec: float, confidence: int):
        meta = self.meta_by_id.get(track_id)
        if not meta:
            return
        wall_now = time.monotonic()
        self.current_wall_t0 = wall_now
        self.drift.reset(initial_track_time=max(0.0, offset_sec), initial_wall_time=0.0)
        self.lrc = load_lrc(meta.get("lrc_file")) if meta.get("lrc_file") else None
        self.current_track_id = track_id
        self.current_conf = confidence

    def _update_drift(self, observed_track_time: float):
        wall_rel = time.monotonic() - self.current_wall_t0
        self.drift.update(wall_time=wall_rel, track_time=observed_track_time)

    def _run(self):
        block_n = int(self.block_seconds * self.sample_rate)

        def callback(indata, frames, time_info, status):
            x = indata[:, 0].astype(np.float32)
            self._append_audio(x)

        with sd.InputStream(
            device=self.device,
            channels=self.channels,
            samplerate=self.sample_rate,
            blocksize=block_n,
            dtype="float32",
            callback=callback,
        ):
            last_match = 0.0
            while self._running:
                now = time.monotonic()
                if now - last_match >= self.match_every:
                    last_match = now
                    audio_seg = self._get_buffer_ordered()
                    res = self._match_segment(audio_seg)
                    if res and res["confidence"] >= self.min_conf:
                        with self._lock:
                            if self.current_track_id != res["track_id"]:
                                self._switch_track(res["track_id"], res["offset_sec"], res["confidence"])
                            else:
                                self.current_conf = res["confidence"]
                                self._update_drift(observed_track_time=max(0.0, res["offset_sec"]))
                time.sleep(0.02)
