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

from autourgos_core import package_version

__version__ = package_version("autourgos-hcix", fallback="3.2.4")

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
