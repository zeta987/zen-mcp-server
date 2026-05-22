"""Parser for CLIs that emit plain text responses."""

from __future__ import annotations

import re

from .base import BaseParser, ParsedCLIResponse, ParserError

OSC_SEQUENCE_RE = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)")
CSI_SEQUENCE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
ANSI_ESCAPE_RE = re.compile(r"\x1b[@-Z\\-_]")


def strip_terminal_control_sequences(text: str) -> str:
    """Remove terminal control sequences from PTY-captured CLI output."""

    cleaned = OSC_SEQUENCE_RE.sub("", text)
    cleaned = CSI_SEQUENCE_RE.sub("", cleaned)
    cleaned = ANSI_ESCAPE_RE.sub("", cleaned)
    return cleaned.replace("\r\n", "\n").replace("\r", "\n").strip()


class PlainTextParser(BaseParser):
    """Parse stdout as the final assistant response."""

    name = "plain_text"

    def parse(self, stdout: str, stderr: str) -> ParsedCLIResponse:
        content = strip_terminal_control_sequences(stdout)
        if not content:
            raise ParserError("CLI returned empty stdout while plain text output was expected")

        metadata: dict[str, str] = {}
        if stderr and stderr.strip():
            metadata["stderr"] = stderr.strip()

        return ParsedCLIResponse(content=content, metadata=metadata)
