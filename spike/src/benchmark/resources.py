from __future__ import annotations

import threading
import time
from typing import Self

import psutil


class ResourceMonitor:
    """Sample current-process RSS without external profilers."""

    def __init__(self, interval_seconds: float = 0.05) -> None:
        self.interval_seconds = interval_seconds
        self.peak_rss_bytes = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Self:
        process = psutil.Process()

        def sample() -> None:
            while not self._stop.is_set():
                try:
                    rss = process.memory_info().rss
                    for child in process.children(recursive=True):
                        rss += child.memory_info().rss
                    self.peak_rss_bytes = max(self.peak_rss_bytes, rss)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                time.sleep(self.interval_seconds)

        self._thread = threading.Thread(target=sample, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1)

    @property
    def peak_memory_mb(self) -> float:
        return self.peak_rss_bytes / (1024 * 1024)
