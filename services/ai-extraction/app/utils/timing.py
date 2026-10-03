"""
Timing utility for measuring extraction duration against target.
"""
import time


class TimingTracker:
    """Measures wall-clock total duration for an extraction pipeline run."""

    def __init__(self) -> None:
        self._start = time.perf_counter()

    @property
    def total_duration_seconds(self) -> float:
        return round(time.perf_counter() - self._start, 4)
