"""
autourgos-hcix.

Self-contained Human Cognitive Interrupt middleware for Autourgos agents.
"""
from __future__ import annotations

from .base import CallbackHandler
from .hcix import CognitiveInterruptManager, InterruptState
from .interrupt import HumanInterrupt, HumanInterruptHandler, HumanStateEditor
from .middleware import (
    HcixInterruptMiddleware,
    format_human_override,
)

try:
    from importlib.metadata import PackageNotFoundError, version

    try:
        __version__ = version("autourgos-hcix")
    except PackageNotFoundError:
        __version__ = "2.1.0"
except Exception:
    __version__ = "2.1.0"

__all__ = [
    "CallbackHandler",
    "CognitiveInterruptManager",
    "HcixInterruptMiddleware",
    "HumanInterrupt",
    "HumanInterruptHandler",
    "HumanStateEditor",
    "InterruptState",
    "format_human_override",
]
