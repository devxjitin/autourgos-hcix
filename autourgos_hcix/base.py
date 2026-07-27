"""
base.py - middleware base class for HCIx.

Re-exports CallbackHandler from autourgos-react-agent, the package that owns
this interface, to avoid divergent duplicate copies.
"""
from __future__ import annotations

from autourgos_react_agent import CallbackHandler

__all__ = ["CallbackHandler"]
