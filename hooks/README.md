# Claude Code hooks

`hooks.json` is a thin Claude Code adapter around the portable core.

Hooks require a current Claude Code release: the exec-form `command` and
`args` hook shape and the `compact` `SessionStart` matcher used below need it
(see the [Claude Code hooks contract](https://code.claude.com/docs/en/hooks)).
Both hooks also need an interpreter reachable as `python3` on `PATH`; see the
[Windows and WSL guide](../docs/windows-wsl.md#claude-code-hooks-and-python3-on-windows)
for native Windows setup.

| Event | Matcher | Behavior |
|---|---|---|
| `SessionStart` | `startup|resume|clear|compact` | Silent by default. With `CLAUDE_OBSIDIAN_SESSION_CONTEXT=1`, resolves a real user vault and emits a bounded, sanitized `wiki/hot.md` data block. A workspace-configured vault outside that project also requires an exact `CLAUDE_OBSIDIAN_SESSION_CONTEXT_VAULT` path. |
| `Stop` | unsupported/omitted | Emits a bounded, aggregate JSON `systemMessage` when recovery is needed. It omits operation identifiers, paths, and note content; otherwise it is silent. |

Both are `command` hooks using an executable plus an argument array and
`${CLAUDE_PLUGIN_ROOT}` only to locate plugin code. They do not use the plugin
cache as a vault.

The response shapes follow the current [Claude Code hooks contract](https://code.claude.com/docs/en/hooks):
An opted-in SessionStart may add context through stdout, while Stop warnings use the
supported top-level `systemMessage` field. Stop has no matcher because that
event does not support one. Both readers reject symlinked paths and cap their
scan count and output bytes.

Hooks never write knowledge, update `wiki/hot.md`, stage files, commit Git, run
remote calls, or bypass transaction approval. The same workflows remain usable
on hosts that do not support Claude hooks.

## Codex hooks

`.codex-plugin/plugin.json` explicitly selects `hooks/codex.json`, keeping Claude’s
exec-form handlers separate from Codex’s quoted command strings. Codex supplies
`${PLUGIN_ROOT}` for code lookup. Both adapters share the portable vault reader
and the same `CLAUDE_OBSIDIAN_SESSION_CONTEXT` consent variables.

| Event | Matcher | Output |
|---|---|---|
| `SessionStart` | `startup`, `resume`, `clear`, `compact`, `fork` | Silent without consent; otherwise JSON `hookSpecificOutput.additionalContext` containing the sanitized hot-cache data block. |
| `Stop` | omitted | Aggregate JSON `systemMessage` recovery warning, or silence. |

The Codex adapter consumes at most 64 KiB of event input and uses only its
absolute `cwd` and matching event name. Invalid events fail closed without
reading a vault. Context retains the shared 32 KiB input cap and trust envelope;
`additionalContextLimit: 0` preserves that already-bounded envelope instead of
letting the host spill it into a separate file. Status output retains its 4 KiB
cap and never includes operation identifiers or note paths.

Review and trust bundled hooks through Codex’s `/hooks` interface before use;
installation alone does not trust them. No installer changes hook trust or
context consent. These hooks target local Codex execution on macOS, Linux, and
WSL with `python3` on PATH. Hook-bearing plugins use manual/repo marketplace
distribution and are not currently eligible for OpenAI’s public directory.

See the [Codex hook contract](https://learn.chatgpt.com/docs/hooks) and
[plugin packaging rules](https://developers.openai.com/plugins/build/plugins#bundled-mcp-servers-and-lifecycle-hooks).
