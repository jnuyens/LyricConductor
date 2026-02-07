from __future__ import annotations
from PyQt6.QtGui import QPainter, QImage
from PyQt6.QtMultimedia import QVideoSink
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap, QPalette, QColor
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QStackedLayout

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from djapp.settings import load_settings, save_settings

import sys
import subprocess

_IS_MACOS = sys.platform == "darwin"
_caffeinate_proc = None

def prevent_sleep_start():
    global _caffeinate_proc
    if not _IS_MACOS:
        return

    if _caffeinate_proc is None:
        _caffeinate_proc = subprocess.Popen(
            ["caffeinate", "-dimsu"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def prevent_sleep_stop():
    global _caffeinate_proc
    if not _IS_MACOS:
        return

    if _caffeinate_proc is not None:
        _caffeinate_proc.terminate()
        _caffeinate_proc = None


class VideoCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self._img: QImage | None = None
        self.setStyleSheet("background-color: black;")

    def set_frame(self, img: QImage):
        self._img = img
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._img is None or self._img.isNull():
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # Letterbox scaling
        w = self.width()
        h = self.height()
        iw = self._img.width()
        ih = self._img.height()
        if iw <= 0 or ih <= 0:
            return

        scale = min(w / iw, h / ih)
        tw = int(iw * scale)
        th = int(ih * scale)
        x = (w - tw) // 2
        y = (h - th) // 2

        p.drawImage(x, y, self._img.scaled(tw, th, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation))
        p.end()



class LetterboxImage(QWidget):
    def __init__(self):
        super().__init__()
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setStyleSheet("background-color: black;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)
        self._pix = None

    def set_image(self, path: str):
        self._pix = QPixmap(path) if path else QPixmap()
        self._apply()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply()

    def _apply(self):
        if self._pix is None or self._pix.isNull():
            self.label.setPixmap(QPixmap())
            return
        scaled = self._pix.scaled(
            self.label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.label.setPixmap(scaled)


class LoopingVideo(QWidget):
    def __init__(self):
        super().__init__()
        self.canvas = VideoCanvas()
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.0)
        self.player.setAudioOutput(self.audio)

        self.sink = QVideoSink(self)
        self.player.setVideoOutput(self.sink)
        self.sink.videoFrameChanged.connect(self._on_frame)
        self.player.mediaStatusChanged.connect(self._status)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

        self._url = None

    def set_video(self, path: str):
        if not path:
            return
        self._url = QUrl.fromLocalFile(path)
        self.player.setSource(self._url)
        self.player.play()

    def _status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self._url is not None:
            self.player.setPosition(0)
            self.player.play()

    def _on_frame(self, frame):
        if frame is None or not frame.isValid():
            return
        img = frame.toImage()
        if img.isNull():
            return
        self.canvas.set_frame(img)


class PresentationWindow(QWidget):
    closed = pyqtSignal()

    def __init__(self, cfg: dict, matcher):
        super().__init__()
        self.cfg = cfg
        self.matcher = matcher
        self._last_track_id = None
        self.fallback_mode = False
        self.default_bg = cfg.get("default_background", "")

        st = load_settings()
        self.lyrics_offset_ms = int(st.get("lyrics_offset_ms", -1500))
        if self.lyrics_offset_ms < -3000:
            self.lyrics_offset_ms = -3000
        if self.lyrics_offset_ms > 3000:
            self.lyrics_offset_ms = 3000
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)

        self.setWindowTitle("DJ Visual Lyrics Presentation")
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor("black"))
        self.setPalette(pal)

        self.bg_stack = QStackedLayout()
        self.bg_img = LetterboxImage()
        self.bg_vid = LoopingVideo()
        self.bg_stack.addWidget(self.bg_img)
        self.bg_stack.addWidget(self.bg_vid)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        bg_host = QWidget()
        bg_host.setLayout(self.bg_stack)
        root.addWidget(bg_host)

        self.overlay = QWidget(self)
        self.overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.overlay.setStyleSheet("background: transparent;")
        self.overlay.raise_()

        self.hint_label = QLabel("Press Esc to exit. Press any key to hide lyrics.", self.overlay)
        self.hint_label.setStyleSheet("color: white; background-color: rgba(0,0,0,180); padding: 12px;")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hf = QFont("Helvetica", 22)
        self.hint_label.setFont(hf)
        self.hint_label.setFixedHeight(60)

        self.offset_toast = QLabel("", self.overlay)
        self.offset_toast.setStyleSheet("color: white; background-color: rgba(0,0,0,180); padding: 10px;")
        self.offset_toast.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tf = QFont("Helvetica", 20)
        self.offset_toast.setFont(tf)
        self.offset_toast.setFixedHeight(52)
        self.offset_toast.hide()
        self._toast_timer.timeout.connect(self.offset_toast.hide)

        lyr_cfg = cfg["display"]["lyrics"]
        self.lyrics_label = QLabel("")
        self.lyrics_label.setWordWrap(True)
        self.lyrics_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.lyrics_label.setStyleSheet(
            f"color: white; background-color: rgba(0,0,0,{int(255*float(lyr_cfg['box_opacity']))});"
            f" padding: {int(lyr_cfg['box_padding'])}px;"
        )
        lf = QFont(lyr_cfg["font_family"], int(lyr_cfg["font_size"]))
        lf.setBold(True)
        self.lyrics_label.setFont(lf)

        meta_cfg = cfg["display"]["meta"]
        self.meta_label = QLabel("")
        self.meta_label.setStyleSheet("color: rgba(255,255,255,230); background: transparent;")
        mf = QFont(meta_cfg["font_family"], int(meta_cfg["font_size"]))
        self.meta_label.setFont(mf)

        ov = QVBoxLayout(self.overlay)
        ov.addWidget(self.hint_label, 0)
        QTimer.singleShot(2500, self.hint_label.hide)
        ov.setContentsMargins(0, 0, 0, 0)

        top_wrap = QWidget()
        top_l = QVBoxLayout(top_wrap)
        top_l.setContentsMargins(0, int(lyr_cfg["margin_top"]), 0, 0)
        top_l.addWidget(self.lyrics_label, 0, Qt.AlignmentFlag.AlignTop)
        ov.addWidget(top_wrap, 0)

        ov.addStretch(1)

        # transient offset change display (bottom center)
        ov.addWidget(self.offset_toast, 0)

        bottom = QWidget()
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(int(meta_cfg["margin_left"]), 0, 0, int(meta_cfg["margin_bottom"]))
        bl.addWidget(self.meta_label, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        bl.addStretch(1)
        ov.addWidget(bottom, 0)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(33)

    def closeEvent(self, event):
        self.closed.emit()
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.overlay.setGeometry(0, 0, self.width(), self.height())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return

        k = event.key()

        # Offset adjust during presentation: + and -
        if k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._adjust_offset(+50)
            event.accept()
            return
        if k in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self._adjust_offset(-50)
            event.accept()
            return

        # Any other key toggles fallback mode
        self.fallback_mode = not self.fallback_mode
        self._last_track_id = None  # force refresh

        if self.fallback_mode:
            # Show default background, hide lyrics/meta immediately
            if self.default_bg:
                self.bg_stack.setCurrentWidget(self.bg_img)
                self.bg_img.set_image(self.default_bg)
            self.lyrics_label.setText("")
            self.meta_label.setText("")
        event.accept()

    def _save_offset(self):
        st = load_settings()
        st["lyrics_offset_ms"] = int(self.lyrics_offset_ms)
        save_settings(st)

    def _offset_label(self) -> str:
        v = int(self.lyrics_offset_ms)
        if v < 0:
            return f"Lyrics: {abs(v)} ms early"
        if v > 0:
            return f"Lyrics: {v} ms late"
        return "Lyrics: 0 ms"

    def _show_offset_toast(self):
        self.offset_toast.setText(self._offset_label())
        self.offset_toast.show()
        # Hide after ~1.2s
        self._toast_timer.start(1200)

    def _adjust_offset(self, delta_ms: int):
        v = int(self.lyrics_offset_ms) + int(delta_ms)
        if v < -3000:
            v = -3000
        if v > 3000:
            v = 3000
        self.lyrics_offset_ms = v
        self._save_offset()
        self._show_offset_toast()


    def _apply_background(self, meta: dict):
        bg = (meta or {}).get("background") or {}
        btype = bg.get("type", "image")
        path = bg.get("path", "")

        if btype == "video" and path:
            self.bg_stack.setCurrentWidget(self.bg_vid)
            self.bg_vid.set_video(path)
        else:
            self.bg_stack.setCurrentWidget(self.bg_img)
            self.bg_img.set_image(path)

    def _tick(self):
        if self.fallback_mode:
            return
        st = self.matcher.get_state()
        meta = st["meta"]
        track_id = st["track_id"]
        track_time = st["track_time"]
        lrc = st["lrc"]

        if track_id != self._last_track_id:
            self._last_track_id = track_id
            if meta:
                self._apply_background(meta)
                self.meta_label.setText(f"{meta.get('title','')}\n{meta.get('album','')}\n{meta.get('artist','')}")
            else:
                self.meta_label.setText("")
                self.lyrics_label.setText("")

        if lrc and track_time is not None:
            effective_t = float(track_time) + (float(self.lyrics_offset_ms) / 1000.0)
            cur, nxt = lrc.current_line(effective_t)
            self.lyrics_label.setText(cur or nxt or "")
        else:
            self.lyrics_label.setText("")
