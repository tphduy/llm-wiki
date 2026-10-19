"""Supported plugin hosts and their hook configuration."""

from enum import Enum
from typing import assert_never


class PluginHost(Enum):
    CLAUDE = "claude"
    CODEX = "codex"

    def __str__(self) -> str:
        return self.value

    @property
    def hooks_path(self) -> str:
        match self:
            case PluginHost.CLAUDE:
                return "hooks/hooks.json"
            case PluginHost.CODEX:
                return "hooks/codex.json"
            case _:
                assert_never(self)
