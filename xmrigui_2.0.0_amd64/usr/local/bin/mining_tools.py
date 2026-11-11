"""Standalone mining UI helpers; importing this module starts no application.

Validation returns only failing fields. Rejection ratios are fractions, not percent.
"""

import math
import re
import shlex
import time
from collections import deque
from collections.abc import Mapping
from urllib.parse import urlsplit

from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget


def _speed(value):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError("Speed must be finite and non-negative")
    return value


class HashrateChart(QWidget):
    """Timestamped chart with at most max_samples points (default 600).

    clock is a monotonic seconds callable. history contains (timestamp, H/s)
    pairs. Call add_sample and clear on the Qt GUI thread.
    """

    def __init__(self, parent=None, *, max_samples=600, clock=None):
        super().__init__(parent)
        if not isinstance(max_samples, int) or max_samples < 2:
            raise ValueError("max_samples must be an integer >= 2")
        self.history = deque(maxlen=max_samples)
        self._clock = clock if clock is not None else time.monotonic
        self.setMinimumHeight(120)

    def add_sample(self, value):
        value = _speed(value)
        self.history.append((self._clock(), value))
        self.update()

    def clear(self):
        self.history.clear()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        area = self.rect().adjusted(62, 22, -18, -35)
        if area.width() <= 0 or area.height() <= 0:
            return
        foreground = self.palette().windowText().color()
        painter.setPen(foreground)
        painter.drawLine(area.bottomLeft(), area.topLeft())
        painter.drawLine(area.bottomLeft(), area.bottomRight())
        painter.drawText(4, 16, "H/s")
        painter.drawText(area.left(), self.height() - 5, "Elapsed minutes")
        painter.drawText(4, area.bottom(), "0")
        if not self.history:
            return
        first = self.history[0][0]
        duration = max(self.history[-1][0] - first, 1.0)
        maximum = max(max(value for _, value in self.history), 1.0)
        painter.drawText(4, area.top() + 10, f"{maximum:.3g}")
        painter.drawText(area.left(), area.bottom() + 16, "0")
        painter.drawText(area.right() - 35, area.bottom() + 16, f"{duration / 60:.2f}")
        points = [
            QPointF(
                area.left() + (stamp - first) / duration * area.width(),
                area.bottom() - value / maximum * area.height(),
            )
            for stamp, value in self.history
        ]
        painter.setPen(QPen(self.palette().highlight().color(), 2))
        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.drawPath(path)
        if len(points) == 1:
            painter.drawEllipse(points[0], 2, 2)


class SessionStats:
    """Pure state holder. start/reset begin a fresh session; stop freezes it.

    add_speed records a sample only while running. update_shares replaces
    cumulative accepted/rejected counts (as reported by XMRig), not increments.
    snapshot returns runtime seconds, average H/s (sample mean), accepted,
    rejected, and rejection_ratio (rejected / total; zero with no shares).
    """

    def __init__(self, clock=None):
        self._clock = clock if clock is not None else time.monotonic
        self._started = None
        self._elapsed = 0.0
        self._sum = 0.0
        self._count = 0
        self.accepted = self.rejected = 0

    def start(self):
        self._started = self._clock()
        self._elapsed = self._sum = 0.0
        self._count = 0
        self.accepted = self.rejected = 0

    def reset(self):
        self.start()

    def stop(self):
        if self._started is not None:
            self._elapsed = max(0.0, self._clock() - self._started)
            self._started = None

    def add_speed(self, value):
        value = _speed(value)
        if self._started is not None:
            self._sum += value
            self._count += 1

    def update_shares(self, accepted, rejected):
        counts = (accepted, rejected)
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in counts):
            raise ValueError("Share counts must be non-negative integers")
        self.accepted, self.rejected = counts

    def snapshot(self):
        runtime = (
            max(0.0, self._clock() - self._started)
            if self._started is not None
            else self._elapsed
        )
        total = self.accepted + self.rejected
        return {
            "runtime": runtime,
            "average": self._sum / self._count if self._count else 0.0,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "rejection_ratio": self.rejected / total if total else 0.0,
        }


def validate_settings(config):
    """Return {field: error} for invalid pool/user/threads/donate/args only.

    default_args=True skips pool and user checks. Args are shell-tokenized,
    never executed or restricted to a known set of XMRig options.
    """
    errors = {}
    if not config.get("default_args", False):
        pool = str(config.get("pool", "")).strip()
        try:
            parsed = urlsplit(pool if "://" in pool else "//" + pool)
            if (
                parsed.scheme not in ("", "stratum+tcp", "stratum+ssl")
                or not parsed.hostname
                or parsed.port is None
                or not 1 <= parsed.port <= 65535
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in ("", "/")
                or parsed.query
                or parsed.fragment
                or any(c.isspace() for c in pool)
            ):
                raise ValueError
        except ValueError:
            errors["pool"] = "Use host:port or a stratum+tcp/ssl URL with a valid port."
        if not str(config.get("user", "") or "").strip():
            errors["user"] = "User or wallet is required."
    for key, limit in (("threads", 2147483647), ("donate", 100)):
        value = str(config.get(key, "")).strip()
        if not re.fullmatch(r"[0-9]+", value) or len(value.lstrip("0")) > 10:
            errors[key] = f"Enter an integer from 0 to {limit}."
        elif int(value.lstrip("0") or "0") > limit:
            errors[key] = f"Enter an integer from 0 to {limit}."
    try:
        shlex.split(str(config.get("args", "")))
    except ValueError:
        errors["args"] = "Additional arguments have invalid quoting or escaping."
    return errors


def redact_log(text, configs):
    """Best-effort conservative redaction, not a guarantee for arbitrary logs.

    configs accepts one settings mapping, a profile->settings mapping, or an
    iterable of settings mappings. Every configured args token AND its equals
    value is scrubbed, even for unknown options. Malformed args are also scrubbed
    using a conservative whitespace fallback. Empty values are ignored.
    """
    if isinstance(configs, Mapping):
        configs = (
            [configs]
            if any(k in configs for k in ("pool", "user", "password", "args"))
            else configs.values()
        )
    secrets = set()
    for config in configs:
        for key in ("pool", "user", "password"):
            value = str(config.get(key, "") or "")
            if value:
                secrets.add(value)
        args = str(config.get("args", "") or "")
        if args:
            secrets.add(args)
            try:
                tokens = shlex.split(args)
            except ValueError:
                tokens = args.split()
            for token in tokens:
                secrets.add(token)
                if "=" in token:
                    secrets.add(token.split("=", 1)[1])
                secrets.add(token.strip("\"'"))
    # Match options before replacing literals, which could themselves be flags.
    text = re.sub(
        r"""(?<![\w-])(--(?:user|pass|url)|-[upo])(?:\s*=\s*|\s+)("[^"\n]*"|'[^'\n]*'|[^\s]+)""",
        lambda m: m[1] + "=[REDACTED]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?<![1-9A-HJ-NP-Za-km-z])[48][1-9A-HJ-NP-Za-km-z]{94}(?:[1-9A-HJ-NP-Za-km-z]{11})?(?![1-9A-HJ-NP-Za-km-z])",
        "[REDACTED]",
        text,
    )
    if secrets:
        text = re.sub(
            "|".join(
                re.escape(s) for s in sorted(secrets - {""}, key=len, reverse=True)
            ),
            lambda _: "[REDACTED]",
            text,
        )
    return text
