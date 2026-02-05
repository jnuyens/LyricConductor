from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class LRCLine:
    t: float
    text: str


@dataclass
class LRC:
    lines: List[LRCLine]

    def current_line(self, t: float) -> Tuple[Optional[str], Optional[str]]:
        if not self.lines:
            return None, None
        idx = None
        for i in range(len(self.lines)):
            if self.lines[i].t <= t:
                idx = i
            else:
                break
        if idx is None:
            return None, self.lines[0].text
        cur = self.lines[idx].text
        nxt = self.lines[idx + 1].text if idx + 1 < len(self.lines) else None
        return cur, nxt


_TIME_RE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")


def load_lrc(path: str) -> LRC:
    lines: List[LRCLine] = []
    if not path:
        return LRC(lines=[])

    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            raw = raw.rstrip("\n")
            times = _TIME_RE.findall(raw)
            if not times:
                continue
            text = _TIME_RE.sub("", raw).strip()
            for mm, ss in times:
                t = int(mm) * 60 + float(ss)
                lines.append(LRCLine(t=t, text=text))

    lines.sort(key=lambda x: x.t)
    return LRC(lines=lines)
