#!/usr/bin/env python3
"""Codex event-wire and installed-command acceptance tests."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from claude_obsidian.cli import build_parser
from claude_obsidian.hosts import PluginHost
from claude_obsidian.hook_adapter import (
    CLOSE_TAG,
    MAX_CONTEXT_BYTES,
    MAX_HOOK_INPUT_BYTES,
    emit_codex_hook,
)


class PluginHostTests(unittest.TestCase):
    def test_cli_converts_hosts_to_enum_and_preserves_claude_default(self) -> None:
        parser = build_parser()
        for event in ("session-start", "stop"):
            with self.subTest(event=event):
                self.assertIs(parser.parse_args(["hook", event]).host, PluginHost.CLAUDE)
            for host in PluginHost:
                with self.subTest(event=event, host=host):
                    args = parser.parse_args(["hook", event, "--host", host.value])
                    self.assertIs(args.host, host)

    def test_cli_rejects_unknown_hosts(self) -> None:
        with mock.patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as error:
                build_parser().parse_args(["hook", "stop", "--host", "unknown"])
        self.assertEqual(error.exception.code, 2)


def fingerprint(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


class CodexHookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.vault = self.base / "user vault"
        (self.vault / "wiki").mkdir(parents=True)
        (self.vault / ".raw").mkdir()
        (self.vault / ".obsidian").mkdir()
        (self.vault / "wiki/hot.md").write_text("RECENT_CONTEXT\n")
        self.env = {"CLAUDE_OBSIDIAN_SESSION_CONTEXT": "1"}

    def invoke(self, event: str, *, payload=None, env=None) -> str:
        output = io.StringIO()
        if payload is None:
            payload = {"hook_event_name": event, "cwd": str(self.vault)}
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        code = emit_codex_hook(
            event,
            input_stream=io.StringIO(raw),
            stream=output,
            environ=self.env if env is None else env,
            plugin_root=self.base / "product",
        )
        self.assertEqual(0, code)
        return output.getvalue()

    def test_all_start_sources_emit_bounded_json_without_writing(self) -> None:
        (self.vault / "wiki/hot.md").write_text(
            CLOSE_TAG + "\n" + "x" * MAX_CONTEXT_BYTES
        )
        before = fingerprint(self.vault)
        for source in ("startup", "resume", "clear", "compact", "fork"):
            with self.subTest(source=source):
                payload = {
                    "cwd": str(self.vault),
                    "hook_event_name": "SessionStart",
                    "source": source,
                }
                result = json.loads(self.invoke("SessionStart", payload=payload))
                output = result["hookSpecificOutput"]
                self.assertEqual("SessionStart", output["hookEventName"])
                context = output["additionalContext"]
                self.assertEqual(1, context.count(CLOSE_TAG))
                self.assertIn("[context truncated]", context)
                self.assertLess(len(context.encode()), MAX_CONTEXT_BYTES + 1000)
        self.assertEqual(before, fingerprint(self.vault))

    def test_context_is_opt_in_and_stdin_cwd_overrides_claude_environment(self) -> None:
        self.assertEqual("", self.invoke("SessionStart", env={}))
        env = {**self.env, "CLAUDE_PROJECT_DIR": str(self.base / "wrong-project")}
        self.assertIn("RECENT_CONTEXT", self.invoke("SessionStart", env=env))

    def test_malformed_oversized_and_wrong_events_do_not_consult_vaults(self) -> None:
        invalid = [
            "",
            "{",
            "[]",
            '{"cwd":"/","cwd":"/"}',
            "x" * (MAX_HOOK_INPUT_BYTES + 1),
            {"hook_event_name": "Stop", "cwd": str(self.vault)},
            {"hook_event_name": "SessionStart", "cwd": "relative/path"},
            {"hook_event_name": "SessionStart", "cwd": str(self.vault) + "\x00"},
            {"hook_event_name": "SessionStart", "cwd": []},
        ]
        with mock.patch("claude_obsidian.hook_adapter.session_start_context") as reader:
            for payload in invalid:
                with self.subTest(payload=str(payload)[:70]):
                    self.assertEqual("", self.invoke("SessionStart", payload=payload))
            reader.assert_not_called()

    def test_external_workspace_vault_needs_exact_consent(self) -> None:
        project = self.base / "project"
        project.mkdir()
        (project / ".claude-obsidian.json").write_text(
            json.dumps(
                {
                    "schema": "claude-obsidian.workspace.v1",
                    "vault": str(self.vault),
                    "role": "vault",
                }
            )
        )
        payload = {"hook_event_name": "SessionStart", "cwd": str(project)}
        self.assertEqual("", self.invoke("SessionStart", payload=payload))
        env = {**self.env, "CLAUDE_OBSIDIAN_SESSION_CONTEXT_VAULT": str(self.vault)}
        self.assertIn(
            "RECENT_CONTEXT", self.invoke("SessionStart", payload=payload, env=env)
        )

    def test_stop_is_advisory_aggregate_and_read_only(self) -> None:
        self.assertEqual("", self.invoke("Stop"))
        journal = self.vault / ".vault-meta/transactions/private-operation/journal.json"
        journal.parent.mkdir(parents=True)
        journal.write_text('{"state":"applying"}')
        before = fingerprint(self.vault)
        result = json.loads(self.invoke("Stop"))
        self.assertEqual({"systemMessage"}, set(result))
        self.assertIn("need recovery", result["systemMessage"])
        self.assertNotIn("private-operation", result["systemMessage"])
        self.assertNotIn(str(self.vault), result["systemMessage"])
        self.assertEqual(before, fingerprint(self.vault))

    def test_plugin_tree_and_symlinked_context_are_silent(self) -> None:
        output = io.StringIO()
        emit_codex_hook(
            "SessionStart",
            input_stream=io.StringIO(
                json.dumps({"hook_event_name": "SessionStart", "cwd": str(self.vault)})
            ),
            stream=output,
            environ=self.env,
            plugin_root=self.vault,
        )
        self.assertEqual("", output.getvalue())
        (self.vault / "wiki/hot.md").unlink()
        (self.vault / "wiki/hot.md").symlink_to(ROOT / "README.md")
        self.assertEqual("", self.invoke("SessionStart"))

    @unittest.skipIf(os.name == "nt", "quoted plugin commands target POSIX / WSL")
    def test_installed_commands_resolve_paths_with_spaces_and_keep_product_read_only(
        self,
    ) -> None:
        product = self.base / "installed product with spaces"
        product.mkdir()
        for relative in ("scripts", "claude_obsidian"):
            shutil.copytree(
                ROOT / relative,
                product / relative,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
        before = fingerprint(product)
        config = json.loads((ROOT / "hooks/codex.json").read_text())
        for event in ("SessionStart", "Stop"):
            command = config["hooks"][event][0]["hooks"][0]["command"]
            environment = {
                key: value
                for key, value in os.environ.items()
                if not key.startswith("CLAUDE_OBSIDIAN_")
            }
            environment.update({**self.env, "PLUGIN_ROOT": str(product)})
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.vault,
                env=environment,
                input=json.dumps({"hook_event_name": event, "cwd": str(self.vault)}),
                text=True,
                capture_output=True,
                timeout=10,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            if event == "SessionStart":
                self.assertIn(
                    "RECENT_CONTEXT",
                    json.loads(result.stdout)["hookSpecificOutput"][
                        "additionalContext"
                    ],
                )
            else:
                self.assertEqual("", result.stdout)
        self.assertEqual(before, fingerprint(product))
        self.assertFalse(list(product.rglob("__pycache__")))


if __name__ == "__main__":
    unittest.main()
