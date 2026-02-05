from __future__ import annotations
import os
import sys

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QComboBox,
    QMessageBox,
)

from djapp.scanlib import scan_music_root, write_config, default_config_path
from djapp.audioio import list_input_devices
from djapp.db import FingerprintDB
from djapp.matcher import LiveMatcher
from djapp.visuals import PresentationWindow
from djapp.fingerprint import Fingerprinter, load_fp_cache, save_fp_cache


class ControlWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DJ Visual Lyrics")

        self.music_root = None
        self.config = None
        self._presentation_win = None
        self._matcher = None

        self.root_label = QLabel("Music root: not selected")
        self.scan_label = QLabel("Scan: not run")

        self.btn_pick = QPushButton("Choose Music Root…")
        self.btn_scan = QPushButton("Scan / Rescan")
        self.btn_scan.setEnabled(False)

        self.device_combo = QComboBox()
        self.btn_refresh_dev = QPushButton("Refresh Devices")
        self.btn_start = QPushButton("Start Presentation")
        self.btn_start.setEnabled(False)

        self.btn_pick.clicked.connect(self.pick_root)
        self.btn_scan.clicked.connect(self.scan_and_build)
        self.btn_refresh_dev.clicked.connect(self.refresh_devices)
        self.btn_start.clicked.connect(self.start_presentation)

        self.refresh_devices()

        lay = QVBoxLayout(self)
        lay.addWidget(self.root_label)
        lay.addWidget(self.scan_label)

        row = QHBoxLayout()
        row.addWidget(self.btn_pick)
        row.addWidget(self.btn_scan)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Audio input:"))
        row2.addWidget(self.device_combo, 1)
        row2.addWidget(self.btn_refresh_dev)
        lay.addLayout(row2)

        lay.addWidget(self.btn_start)
        self.setMinimumWidth(700)

    def pick_root(self):
        d = QFileDialog.getExistingDirectory(self, "Choose Music Root")
        if not d:
            return
        self.music_root = d
        self.root_label.setText(f"Music root: {d}")
        self.btn_scan.setEnabled(True)
        self.btn_start.setEnabled(False)
        self.scan_label.setText("Scan: pending")

    def refresh_devices(self):
        self.device_combo.clear()
        for idx, name in list_input_devices():
            self.device_combo.addItem(f"[{idx}] {name}", userData=idx)

    def scan_and_build(self):
        if not self.music_root:
            return
        try:
            tracks = scan_music_root(self.music_root)
            if not tracks:
                QMessageBox.warning(self, "No tracks", "No valid song folders found.")
                return

            cfg_path = default_config_path(self.music_root)
            cfg = write_config(self.music_root, tracks, cfg_path)

            db = FingerprintDB(cfg["database"]["path"])
            db.init_schema()

            fp_cfg = cfg["fingerprinting"]
            audio_cfg = cfg["audio"]
            finger = Fingerprinter(
                sample_rate=int(audio_cfg["sample_rate"]),
                fft_size=int(fp_cfg["fft_size"]),
                hop_size=int(fp_cfg["hop_size"]),
                peak_neighborhood=tuple(fp_cfg["peak_neighborhood"]),
                max_peaks_per_frame=int(fp_cfg["max_peaks_per_frame"]),
                fanout=int(fp_cfg["fanout"]),
                min_dt=int(fp_cfg["min_dt"]),
                max_dt=int(fp_cfg["max_dt"]),
            )

            for t in cfg["tracks"]:
                db.upsert_track(track_id=t["id"], meta=t)
                cache_path = t.get("fingerprint_cache")
                if cache_path and os.path.exists(cache_path):
                    hashes = load_fp_cache(cache_path)
                else:
                    hashes = finger.fingerprint_file(t["audio_file"])
                    if cache_path:
                        save_fp_cache(cache_path, hashes)
                db.replace_hashes(track_id=t["id"], hashes=hashes)

            self.config = cfg
            self.scan_label.setText(f"Scan: OK, found {len(cfg['tracks'])} tracks")
            self.btn_start.setEnabled(True)

        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))



    def start_presentation(self):
        if not self.config:
            return

        dev_idx = self.device_combo.currentData()
        self.config["audio"]["device"] = int(dev_idx) if dev_idx is not None else None

        db = FingerprintDB(self.config["database"]["path"])
        db.init_schema()
        self._matcher = LiveMatcher(cfg=self.config, db=db)
        self._matcher.start()

        self.hide()

        # Keep references on self, otherwise the window can get garbage collected
        self._presentation_win = PresentationWindow(self.config, self._matcher)

        app = QApplication.instance()
        screens = app.screens()
        idx = int(self.config["display"].get("screen_index", 0))
        if 0 <= idx < len(screens):
            self._presentation_win.setGeometry(screens[idx].geometry())

        def on_closed():
            try:
                self._matcher.stop()
            finally:
                self.show()
                self._presentation_win = None
                self._matcher = None

        # When user hits Esc, PresentationWindow.close() is called, this triggers destroyed
        self._presentation_win.closed.connect(on_closed)

        if self.config["display"].get("fullscreen", True):
            self._presentation_win.showFullScreen()
        else:
            self._presentation_win.show()



def main():
    app = QApplication(sys.argv)
    w = ControlWindow()
    w.show()
    sys.exit(app.exec())
