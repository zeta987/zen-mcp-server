import json

import pytest

from clink import get_registry
from clink.agents import AgentOutput
from clink.parsers.base import ParsedCLIResponse
from clink.registry import ClinkRegistry
from tools.clink import MAX_RESPONSE_CHARS, CLinkTool


@pytest.mark.asyncio
async def test_clink_tool_execute(monkeypatch):
    tool = CLinkTool()

    async def fake_run(**kwargs):
        return AgentOutput(
            parsed=ParsedCLIResponse(content="Hello from Gemini", metadata={"model_used": "gemini-2.5-pro"}),
            sanitized_command=["gemini", "-o", "json"],
            returncode=0,
            stdout='{"response": "Hello from Gemini"}',
            stderr="",
            duration_seconds=0.42,
            parser_name="gemini_json",
            output_file_content=None,
        )

    class DummyAgent:
        async def run(self, **kwargs):
            return await fake_run(**kwargs)

    def fake_create_agent(client):
        return DummyAgent()

    monkeypatch.setattr("tools.clink.create_agent", fake_create_agent)

    arguments = {
        "prompt": "Summarize the project",
        "cli_name": "gemini",
        "role": "default",
        "absolute_file_paths": [],
        "images": [],
    }

    results = await tool.execute(arguments)
    assert len(results) == 1

    payload = json.loads(results[0].text)
    assert payload["status"] in {"success", "continuation_available"}
    assert "Hello from Gemini" in payload["content"]
    metadata = payload.get("metadata", {})
    assert metadata.get("cli_name") == "gemini"
    assert metadata.get("command") == ["gemini", "-o", "json"]


@pytest.mark.asyncio
async def test_clink_tool_returns_agy_plain_text_payload(monkeypatch):
    tool = CLinkTool()

    class DummyAgent:
        async def run(self, **kwargs):
            _ = kwargs
            return AgentOutput(
                parsed=ParsedCLIResponse(content="hi from agy", metadata={}),
                sanitized_command=["agy", "--dangerously-skip-permissions", "--print"],
                returncode=0,
                stdout="hi from agy",
                stderr="",
                duration_seconds=0.25,
                parser_name="plain_text",
                output_file_content=None,
            )

    monkeypatch.setattr("tools.clink.create_agent", lambda client: DummyAgent())

    results = await tool.execute(
        {
            "prompt": "echo hi",
            "cli_name": "gemini",
            "role": "default",
            "absolute_file_paths": [],
            "images": [],
        }
    )

    payload = json.loads(results[0].text)
    assert payload["status"] in {"success", "continuation_available"}
    assert payload["content"] == "hi from agy"
    metadata = payload["metadata"]
    assert metadata["cli_name"] == "gemini"
    assert metadata["parser"] == "plain_text"
    assert metadata["return_code"] == 0
    assert metadata["command"] == ["agy", "--dangerously-skip-permissions", "--print"]


def test_registry_lists_roles():
    registry = get_registry()
    clients = registry.list_clients()
    assert {"codex", "gemini"}.issubset(set(clients))
    roles = registry.list_roles("gemini")
    assert "default" in roles
    assert "default" in registry.list_roles("codex")
    gemini_client = registry.get_client("gemini")
    assert gemini_client.executable[-1].endswith("agy")
    assert gemini_client.internal_args == ["--print"]
    assert gemini_client.config_args == ["--dangerously-skip-permissions"]
    assert gemini_client.parser == "plain_text"
    assert gemini_client.execution_mode == "conpty"
    assert gemini_client.strip_ansi is True
    codex_client = registry.get_client("codex")
    # Verify codex uses --enable web_search_request (not --search which is unsupported by exec)
    assert codex_client.config_args == [
        "--json",
        "--dangerously-bypass-approvals-and-sandbox",
        "--enable",
        "web_search_request",
    ]


def test_registry_keeps_legacy_gemini_json_defaults(monkeypatch, tmp_path):
    config_path = tmp_path / "gemini.json"
    config_path.write_text(
        json.dumps(
            {
                "name": "gemini",
                "command": "gemini",
                "roles": {
                    "default": {
                        "prompt_path": "systemprompts/clink/default.txt",
                        "role_args": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLI_CLIENTS_CONFIG_PATH", str(config_path))

    registry = ClinkRegistry()
    gemini_client = registry.get_client("gemini")

    assert gemini_client.executable == ["gemini"]
    assert gemini_client.internal_args == ["-o", "json"]
    assert gemini_client.parser == "gemini_json"
    assert gemini_client.execution_mode == "pipe"
    assert gemini_client.strip_ansi is False


@pytest.mark.asyncio
async def test_clink_tool_defaults_to_first_cli(monkeypatch):
    tool = CLinkTool()

    async def fake_run(**kwargs):
        return AgentOutput(
            parsed=ParsedCLIResponse(content="Default CLI response", metadata={"events": ["foo"]}),
            sanitized_command=["gemini"],
            returncode=0,
            stdout='{"response": "Default CLI response"}',
            stderr="",
            duration_seconds=0.1,
            parser_name="gemini_json",
            output_file_content=None,
        )

    class DummyAgent:
        async def run(self, **kwargs):
            return await fake_run(**kwargs)

    monkeypatch.setattr("tools.clink.create_agent", lambda client: DummyAgent())

    arguments = {
        "prompt": "Hello",
        "absolute_file_paths": [],
        "images": [],
    }

    result = await tool.execute(arguments)
    payload = json.loads(result[0].text)
    metadata = payload.get("metadata", {})
    assert metadata.get("cli_name") == tool._default_cli_name
    assert metadata.get("events_removed_for_normal") is True


@pytest.mark.asyncio
async def test_clink_tool_truncates_large_output(monkeypatch):
    tool = CLinkTool()

    summary_section = "<SUMMARY>This is the condensed summary.</SUMMARY>"
    long_text = "A" * (MAX_RESPONSE_CHARS + 500) + summary_section

    async def fake_run(**kwargs):
        return AgentOutput(
            parsed=ParsedCLIResponse(content=long_text, metadata={"events": ["event1", "event2"]}),
            sanitized_command=["codex"],
            returncode=0,
            stdout="{}",
            stderr="",
            duration_seconds=0.2,
            parser_name="codex_jsonl",
            output_file_content=None,
        )

    class DummyAgent:
        async def run(self, **kwargs):
            return await fake_run(**kwargs)

    monkeypatch.setattr("tools.clink.create_agent", lambda client: DummyAgent())

    arguments = {
        "prompt": "Summarize",
        "cli_name": tool._default_cli_name,
        "absolute_file_paths": [],
        "images": [],
    }

    result = await tool.execute(arguments)
    payload = json.loads(result[0].text)
    assert payload["status"] in {"success", "continuation_available"}
    assert payload["content"].strip() == "This is the condensed summary."
    metadata = payload.get("metadata", {})
    assert metadata.get("output_summarized") is True
    assert metadata.get("events_removed_for_normal") is True
    assert metadata.get("output_original_length") == len(long_text)


@pytest.mark.asyncio
async def test_clink_tool_truncates_without_summary(monkeypatch):
    tool = CLinkTool()

    long_text = "B" * (MAX_RESPONSE_CHARS + 1000)

    async def fake_run(**kwargs):
        return AgentOutput(
            parsed=ParsedCLIResponse(content=long_text, metadata={"events": ["event"]}),
            sanitized_command=["codex"],
            returncode=0,
            stdout="{}",
            stderr="",
            duration_seconds=0.2,
            parser_name="codex_jsonl",
            output_file_content=None,
        )

    class DummyAgent:
        async def run(self, **kwargs):
            return await fake_run(**kwargs)

    monkeypatch.setattr("tools.clink.create_agent", lambda client: DummyAgent())

    arguments = {
        "prompt": "Summarize",
        "cli_name": tool._default_cli_name,
        "absolute_file_paths": [],
        "images": [],
    }

    result = await tool.execute(arguments)
    payload = json.loads(result[0].text)
    assert payload["status"] in {"success", "continuation_available"}
    assert "exceeding the configured clink limit" in payload["content"]
    metadata = payload.get("metadata", {})
    assert metadata.get("output_truncated") is True
    assert metadata.get("events_removed_for_normal") is True
    assert metadata.get("output_original_length") == len(long_text)
