"""Configurable candidate discovery from deterministic market filters."""

from .core import ScanConfig, evaluate_daily, scan_daily

__all__ = ["ScanConfig", "evaluate_daily", "scan_daily"]
