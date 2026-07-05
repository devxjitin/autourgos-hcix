"""
base.py - self-contained middleware base class for HCIx.

This package intentionally avoids an autourgos-core dependency so it can be
installed beside any current Autourgos agent package.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class CallbackHandler:
    """Base class for Autourgos agent middleware / event hooks."""

    def on_agent_start(self, query: str, agent: Any = None, **kwargs: Any) -> None:
        pass

    def on_agent_end(self, result: str, agent: Any = None, **kwargs: Any) -> None:
        pass

    def on_agent_error(self, error: Exception, agent: Any = None, **kwargs: Any) -> None:
        pass

    def on_iteration_start(self, iteration: int, agent: Any = None, **kwargs: Any) -> None:
        pass

    def on_iteration(
        self,
        iteration: int,
        thought: Optional[str] = None,
        agent: Any = None,
        **kwargs: Any,
    ) -> None:
        pass

    def on_llm_end(self, response: str, agent: Any = None, **kwargs: Any) -> None:
        pass

    def on_tool_start(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        agent: Any = None,
        **kwargs: Any,
    ) -> None:
        pass

    def on_tool_end(
        self,
        tool_name: str,
        tool_output: Any,
        agent: Any = None,
        **kwargs: Any,
    ) -> None:
        pass

    def on_tool_error(
        self,
        tool_name: str,
        error: Exception,
        agent: Any = None,
        **kwargs: Any,
    ) -> None:
        pass

    def on_parse_error(self, iteration: int, raw_response: str, **kwargs: Any) -> None:
        pass
