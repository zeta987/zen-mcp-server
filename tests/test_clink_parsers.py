import pytest

from clink.parsers.base import ParserError
from clink.parsers.codex import CodexJSONLParser
from clink.parsers.plain_text import PlainTextParser


def test_codex_parser_success():
    parser = CodexJSONLParser()
    stdout = """
{"type":"item.completed","item":{"id":"item_0","type":"agent_message","text":"Hello"}}
{"type":"turn.completed","usage":{"input_tokens":10,"output_tokens":5}}
"""
    parsed = parser.parse(stdout=stdout, stderr="")
    assert parsed.content == "Hello"
    assert parsed.metadata["usage"]["output_tokens"] == 5


def test_codex_parser_requires_agent_message():
    parser = CodexJSONLParser()
    stdout = '{"type":"turn.completed"}'
    with pytest.raises(ParserError):
        parser.parse(stdout=stdout, stderr="")


def test_plain_text_parser_success():
    parser = PlainTextParser()
    parsed = parser.parse(stdout="  Hello from agy\n", stderr="warning\n")

    assert parsed.content == "Hello from agy"
    assert parsed.metadata["stderr"] == "warning"


def test_plain_text_parser_strips_terminal_control_sequences():
    parser = PlainTextParser()
    stdout = "\x1b[?25l\x1b[2J\x1b]0;npm\x07Ciallo\r\nAGY_OK\x1b]0;pwsh\x1b\\"

    parsed = parser.parse(stdout=stdout, stderr="")

    assert parsed.content == "Ciallo\nAGY_OK"


def test_plain_text_parser_requires_stdout():
    parser = PlainTextParser()

    with pytest.raises(ParserError):
        parser.parse(stdout="   ", stderr="")
