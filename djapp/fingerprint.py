from __future__ import annotations
import os
import numpy as np
import soundfile as sf
from dataclasses import dataclass
from scipy.signal import stft
from scipy.ndimage import maximum_filter


def _to_mono(x: np.ndarray) -> np.ndarray:
    if x.ndim == 1:
        return x
    return np.mean(x, axis=1)


@dataclass
class Fingerprinter:
    sample_rate: int = 22050
    fft_size: int = 4096
    hop_size: int = 512
    peak_neighborhood: tuple = (12, 20)
    max_peaks_per_frame: int = 6
    fanout: int = 8
    min_dt: int = 1
    max_dt: int = 60

    def _spectrogram(self, audio: np.ndarray):
        _f, _t, Z = stft(
            audio,
            fs=self.sample_rate,
            nperseg=self.fft_size,
            noverlap=self.fft_size - self.hop_size,
        )
        return np.abs(Z)

    def _find_peaks(self, S: np.ndarray) -> np.ndarray:
        eps = 1e-10
        logS = np.log(S + eps)
        neighborhood = (self.peak_neighborhood[0], self.peak_neighborhood[1])
        local_max = maximum_filter(logS, size=neighborhood) == logS

        if np.any(local_max):
            thresh = np.percentile(logS[local_max], 75)
        else:
            thresh = np.max(logS)

        candidates = np.argwhere(local_max & (logS >= thresh))
        if candidates.size == 0:
            return np.zeros((0, 2), dtype=np.int32)

        peaks = np.stack([candidates[:, 1], candidates[:, 0]], axis=1)  # (t, f)

        out = []
        for t_idx in np.unique(peaks[:, 0]):
            idx = np.where(peaks[:, 0] == t_idx)[0]
            if idx.size <= self.max_peaks_per_frame:
                out.append(peaks[idx])
                continue
            f_idx = peaks[idx, 1]
            mags = logS[f_idx, t_idx]
            top = idx[np.argsort(mags)[-self.max_peaks_per_frame :]]
            out.append(peaks[top])

        return np.concatenate(out, axis=0).astype(np.int32)

    @staticmethod
    def _hash_triplet(f1: int, f2: int, dt: int) -> int:
        f1 &= 0x3FF
        f2 &= 0x3FF
        dt &= 0xFFF
        return (f1 << 22) | (f2 << 12) | dt

    def fingerprint_audio(self, audio: np.ndarray):
        audio = _to_mono(audio).astype(np.float32)
        audio = audio - np.mean(audio)

        S = self._spectrogram(audio)
        peaks = self._find_peaks(S)
        if peaks.shape[0] < 10:
            return []

        peaks = peaks[np.argsort(peaks[:, 0])]

        hashes = []
        for i in range(len(peaks)):
            t1, f1 = peaks[i]
            for j in range(1, self.fanout + 1):
                if i + j >= len(peaks):
                    break
                t2, f2 = peaks[i + j]
                dt = int(t2 - t1)
                if dt < self.min_dt or dt > self.max_dt:
                    continue
                h = self._hash_triplet(int(f1), int(f2), dt)
                hashes.append((int(h), int(t1)))
        return hashes

    def fingerprint_file(self, path: str):
        audio, sr = sf.read(path, always_2d=False)
        x = _to_mono(audio).astype(np.float32)

        if sr != self.sample_rate:
            old_n = x.shape[0]
            new_n = int(old_n * (self.sample_rate / sr))
            xp = np.linspace(0, 1, old_n, endpoint=False)
            xq = np.linspace(0, 1, new_n, endpoint=False)
            x = np.interp(xq, xp, x).astype(np.float32)

        return self.fingerprint_audio(x)


def save_fp_cache(cache_path: str, hashes):
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    h = np.array([x[0] for x in hashes], dtype=np.uint32)
    t = np.array([x[1] for x in hashes], dtype=np.int32)
    np.savez_compressed(cache_path, h=h, t=t)


def load_fp_cache(cache_path: str):
    d = np.load(cache_path)
    h = d["h"].astype(np.uint32)
    t = d["t"].astype(np.int32)
    return list(zip(h.tolist(), t.tolist()))
