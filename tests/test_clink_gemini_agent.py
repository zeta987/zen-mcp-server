import asyncio
import shutil
import sys
import time
import types
from pathlib import Path

import pytest

from clink.agents.base import CLIAgentError
from clink.agents.gemini import GeminiAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole


class DummyProcess:
    def __init__(self, *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self, _input):
        return self._stdout, self._stderr


@pytest.fixture()
def gemini_agent():
    prompt_path = Path("systemprompts/clink/gemini_default.txt").resolve()
    role = ResolvedCLIRole(name="default", prompt_path=prompt_path, role_args=[])
    client = ResolvedCLIClient(
        name="gemini",
        executable=["gemini"],
        internal_args=[],
        config_args=[],
        env={},
        timeout_seconds=30,
        parser="gemini_json",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return GeminiAgent(client), role


@pytest.fixture()
def agy_agent():
    prompt_path = Path("systemprompts/clink/default.txt").resolve()
    role = ResolvedCLIRole(name="default", prompt_path=prompt_path, role_args=[])
    client = ResolvedCLIClient(
        name="gemini",
        executable=["agy"],
        internal_args=["--print"],
        config_args=["--dangerously-skip-permissions"],
        env={},
        timeout_seconds=30,
        parser="plain_text",
        runner="gemini",
        execution_mode="conpty",
        strip_ansi=True,
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return GeminiAgent(client), role


async def _run_agent_with_process(monkeypatch, agent, role, process):
    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return process

    def fake_which(executable_name):
        return f"/usr/bin/{executable_name}"

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", fake_which)
    return await agent.run(role=role, prompt="do something", files=[], images=[])


@pytest.mark.asyncio
async def test_agy_agent_uses_conpty_output(monkeypatch, agy_agent):
    agent, role = agy_agent
    captured: dict[str, list[str]] = {}

    class FakePtyProcess:
        def __init__(self):
            self._chunks = ["\x1b[?25lAGY_MCP_OK\x1b]0;pwsh\x1b\\"]

        @classmethod
        def spawn(cls, argv, cwd=None, env=None, dimensions=(24, 80), backend=None):
            _ = (cwd, env, dimensions, backend)
            captured["argv"] = list(argv)
            return cls()

        def read(self, _size):
            if self._chunks:
                return self._chunks.pop(0)
            raise EOFError

        def isalive(self):
            return bool(self._chunks)

        def wait(self):
            return 0

        def terminate(self, force=False):
            _ = force

    async def fail_pipe(*_args, **_kwargs):
        raise AssertionError("agy conpty mode must not use PIPE subprocess")

    monkeypatch.setitem(sys.modules, "winpty", types.SimpleNamespace(PtyProcess=FakePtyProcess))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fail_pipe)
    monkeypatch.setattr(shutil, "which", lambda executable_name: f"C:/bin/{executable_name}.exe")

    result = await agent.run(role=role, prompt="Respond with AGY_MCP_OK", files=[], images=[])

    assert result.stdout == "AGY_MCP_OK"
    assert result.parsed.content == "AGY_MCP_OK"
    assert captured["argv"] == [
        "C:/bin/agy.exe",
        "--dangerously-skip-permissions",
        "--print",
        "Respond with AGY_MCP_OK",
    ]


@pytest.mark.asyncio
async def test_agy_agent_drains_conpty_output_after_process_exit(monkeypatch, agy_agent):
    agent, role = agy_agent

    class FakePtyProcess:
        def __init__(self):
            self._chunks = ["AGY_", "MCP_", "DRAINED"]

        @classmethod
        def spawn(cls, *_args, **_kwargs):
            return cls()

        def read(self, _size):
            if self._chunks:
                return self._chunks.pop(0)
            raise EOFError

        def isalive(self):
            return False

        def wait(self):
            return 0

        def terminate(self, force=False):
            _ = force

    monkeypatch.setitem(sys.modules, "winpty", types.SimpleNamespace(PtyProcess=FakePtyProcess))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(shutil, "which", lambda executable_name: f"C:/bin/{executable_name}.exe")

    result = await agent.run(role=role, prompt="Respond with AGY_MCP_DRAINED", files=[], images=[])

    assert result.parsed.content == "AGY_MCP_DRAINED"


@pytest.mark.asyncio
async def test_agy_agent_conpty_read_timeout_is_bounded(monkeypatch, agy_agent):
    agent, role = agy_agent
    agent.client.timeout_seconds = 1

    class BlockingPtyProcess:
        @classmethod
        def spawn(cls, *_args, **_kwargs):
            return cls()

        def read(self, _size):
            time.sleep(2)
            return ""

        def isalive(self):
            return True

        def wait(self):
            return 0

        def terminate(self, force=False):
            _ = force

    monkeypatch.setitem(sys.modules, "winpty", types.SimpleNamespace(PtyProcess=BlockingPtyProcess))
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(shutil, "which", lambda executable_name: f"C:/bin/{executable_name}.exe")

    started = time.monotonic()
    with pytest.raises(CLIAgentError, match="timed out"):
        await agent.run(role=role, prompt="Respond eventually", files=[], images=[])
    assert time.monotonic() - started < 1.5


@pytest.mark.asyncio
async def test_gemini_agent_recovers_tool_error(monkeypatch, gemini_agent):
    agent, role = gemini_agent
    error_json = """{
  "error": {
    "type": "FatalToolExecutionError",
    "message": "Error executing tool replace: Failed to edit",
    "code": "edit_expected_occurrence_mismatch"
  }
}"""
    stderr = ("Error: Failed to edit, expected 1 occurrence but found 2.\n" + error_json).encode()
    process = DummyProcess(stderr=stderr, returncode=54)

    result = await _run_agent_with_process(monkeypatch, agent, role, process)

    assert result.returncode == 54
    assert result.parsed.metadata["cli_error_recovered"] is True
    assert result.parsed.metadata["cli_error_code"] == "edit_expected_occurrence_mismatch"
    assert "Gemini CLI reported a tool failure" in result.parsed.content


@pytest.mark.asyncio
async def test_gemini_agent_propagates_unrecoverable_error(monkeypatch, gemini_agent):
    agent, role = gemini_agent
    stderr = b"Plain failure without structured payload"
    process = DummyProcess(stderr=stderr, returncode=54)

    with pytest.raises(CLIAgentError):
        await _run_agent_with_process(monkeypatch, agent, role, process)
