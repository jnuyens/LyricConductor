from __future__ import annotations
from PyQt6.QtCore import Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap, QPalette, QColor
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QStackedLayout

from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget


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
        self.video = QVideoWidget(self)
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.0)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.player.mediaStatusChanged.connect(self._status)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video)
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


class PresentationWindow(QWidget):
    closed = pyqtSignal()

    def __init__(self, cfg: dict, matcher):
        super().__init__()
        self.cfg = cfg
        self.matcher = matcher
        self._last_track_id = None

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
        ov.setContentsMargins(0, 0, 0, 0)

        top_wrap = QWidget()
        top_l = QVBoxLayout(top_wrap)
        top_l.setContentsMargins(0, int(lyr_cfg["margin_top"]), 0, 0)
        top_l.addWidget(self.lyrics_label, 0, Qt.AlignmentFlag.AlignTop)
        ov.addWidget(top_wrap, 0)

        ov.addStretch(1)

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
            cur, nxt = lrc.current_line(track_time)
            self.lyrics_label.setText(cur or nxt or "")
        else:
            self.lyrics_label.setText("")
