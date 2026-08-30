"""
base.py - middleware base class for HCIx.

Re-exports CallbackHandler from autourgos-agent, the package that owns
this interface, to avoid divergent duplicate copies.
"""
from __future__ import annotations

from autourgos_agent import CallbackHandler

__all__ = ["CallbackHandler"]
