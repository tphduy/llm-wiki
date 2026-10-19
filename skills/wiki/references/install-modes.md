# Supported installation modes

Resolve the installed product root from the invoking skill's own location, not
from the user-vault working directory:

```bash
PRODUCT_ROOT=/absolute/path/to/installed/llm-wiki
CORE="$PRODUCT_ROOT/scripts/claude-obsidian.py"
test -f "$CORE"
```

## Claude marketplace plugin

Install the plugin through its marketplace and invoke namespaced skills such as
`/llm-wiki:wiki`. Plugin assets live in an ephemeral cache. Mutable vault
state must resolve from the project, `--vault`, or workspace configuration,
never `${CLAUDE_PLUGIN_ROOT}`.

## Local Claude plugin development

```bash
claude --plugin-dir /path/to/llm-wiki
```

Skills remain namespaced. Run Claude from the user vault, not the plugin source
directory, or configure the vault explicitly.

## Codex marketplace plugin

Install `llm-wiki@tphduy-llm-wiki` from `tphduy/llm-wiki`, then select the
packaged skill in Codex. Resolve helpers from that skill’s installed location.
`${PLUGIN_ROOT}` locates hook code only; user knowledge belongs in the selected
vault. Codex uses `hooks/codex.json`; Claude uses `hooks/hooks.json`.

Review and trust Codex hooks before use. Context injection remains gated by
`CLAUDE_OBSIDIAN_SESSION_CONTEXT=1` and the existing external-vault consent rule.
For setup, upgrades, uninstall, or switching from standalone links, read the
[installation guide](../../../docs/install-guide.md#codex-marketplace).

## Portable Agent Skills

Use `scripts/setup-multi-agent.sh` or link each `skills/<name>/` directory at the
host's direct `<skill-root>/<name>/SKILL.md` discovery path. Codex, OpenCode,
and other Agent Skills hosts consume the same `SKILL.md` files. Host-specific
hooks are adapters, not core workflow logic.

## Product clone

A source clone is product/development code, not an automatically installed
plugin and not the recommended user vault. Create a separate vault:

```bash
python3 "$CORE" init /path/to/vault \
  --generated-at <ISO-UTC> --operation-id init-reviewed
python3 "$CORE" init /path/to/vault \
  --generated-at <ISO-UTC> --operation-id init-reviewed \
  --approved-plan-sha256 <reviewed-sha256> --apply
```

Adopt an existing Obsidian vault non-destructively:

```bash
python3 "$CORE" adopt /path/to/vault \
  --generated-at <ISO-UTC> --operation-id adopt-reviewed
python3 "$CORE" adopt /path/to/vault \
  --generated-at <ISO-UTC> --operation-id adopt-reviewed \
  --approved-plan-sha256 <reviewed-sha256> --apply
```

Both commands default to dry-run. New user vaults receive no upstream product
remote.
