"""Shared, filesystem-independent contracts for the two plugin distributions."""

from __future__ import annotations

import re
from typing import Mapping

from .json_utils import strict_json_loads

PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
CATALOGS = {
    ".claude-plugin/marketplace.json": "config/public-marketplace.json",
    ".agents/plugins/marketplace.json": "config/public-codex-marketplace.json",
}
CANONICAL_MANIFEST = "config/plugin.json"
METADATA_FILES = (
    CANONICAL_MANIFEST,
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    *CATALOGS.values(),
)
SHARED_FIELDS = (
    "name",
    "version",
    "description",
    "author",
    "license",
    "homepage",
    "repository",
)
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SEMVER_RE = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


def validate_metadata(
    payload: Mapping[str, bytes], *, installed: bool = False
) -> list[dict[str, str]]:
    """Validate reviewed templates and any materialized catalogs byte-for-byte."""

    findings: list[dict[str, str]] = []

    def fail(code: str, path: str, message: str) -> None:
        findings.append({"code": code, "path": path, "message": message})

    if "plugin.json" in payload:
        fail(
            "shadowed_codex_adapter",
            "plugin.json",
            "a portable root manifest disables Codex 0.163 compatibility hooks; keep metadata in config/plugin.json",
        )
    overlay = {}
    documents = {}
    for path in METADATA_FILES:
        try:
            document = strict_json_loads(payload[path].decode("utf-8"))
            if not isinstance(document, dict):
                raise ValueError("expected a JSON object")
            documents[path] = document
        except KeyError:
            fail("missing_file", path, "required file is missing")
        except (ValueError, UnicodeError, RecursionError):
            fail("invalid_json", path, "expected a strict UTF-8 JSON object")
    plugin = documents.get(CANONICAL_MANIFEST, {})
    if CANONICAL_MANIFEST in documents:
        if plugin.get("$schema") != PLUGIN_SCHEMA:
            fail(
                "invalid_plugin_schema",
                CANONICAL_MANIFEST,
                "declare the Agent Plugins schema",
            )
        name, version = plugin.get("name"), plugin.get("version")
        if not isinstance(name, str) or not NAME_RE.fullmatch(name):
            fail(
                "invalid_plugin_name",
                CANONICAL_MANIFEST,
                "use a kebab-case plugin name",
            )
        if not isinstance(version, str) or not SEMVER_RE.fullmatch(version):
            fail(
                "missing_version", CANONICAL_MANIFEST, "use a semantic release version"
            )
        for field in ("description", "license", "homepage", "repository"):
            if not isinstance(plugin.get(field), str) or not plugin[field].strip():
                fail("invalid_plugin_metadata", CANONICAL_MANIFEST, field)
        author = plugin.get("author")
        if (
            not isinstance(author, dict)
            or not isinstance(author.get("name"), str)
            or not author["name"].strip()
        ):
            fail("invalid_plugin_metadata", CANONICAL_MANIFEST, "author.name")
        extensions = plugin.get("extensions")
        overlay = extensions.get("com.openai") if isinstance(extensions, dict) else None
        if (
            not isinstance(overlay, dict)
            or overlay.get("hooks") != "./hooks/codex.json"
        ):
            fail(
                "invalid_codex_hooks",
                CANONICAL_MANIFEST,
                "select ./hooks/codex.json explicitly",
            )
        if "hooks/codex.json" not in payload:
            fail(
                "missing_file",
                "hooks/codex.json",
                "Codex hook configuration is missing",
            )
    claude = documents.get(".claude-plugin/plugin.json")
    if claude is not None and plugin:
        for field in SHARED_FIELDS:
            if claude.get(field) != plugin.get(field):
                fail(
                    "version_drift" if field == "version" else "plugin_metadata_drift",
                    ".claude-plugin/plugin.json",
                    field + " differs from config/plugin.json",
                )

    codex = documents.get(".codex-plugin/plugin.json")
    if codex is not None and plugin:
        for field in SHARED_FIELDS:
            if codex.get(field) != plugin.get(field):
                fail(
                    "version_drift" if field == "version" else "plugin_metadata_drift",
                    ".codex-plugin/plugin.json",
                    field + " differs from config/plugin.json",
                )
        overlay = overlay if isinstance(overlay, dict) else {}
        for field in ("hooks", "interface"):
            if codex.get(field) != overlay.get(field):
                fail(
                    "plugin_metadata_drift",
                    ".codex-plugin/plugin.json",
                    field + " differs from canonical OpenAI settings",
                )
        if codex.get("skills") != "./skills/":
            fail(
                "invalid_codex_skills",
                ".codex-plugin/plugin.json",
                "select the shared ./skills/ directory",
            )

    catalog_names = []
    for destination, template in CATALOGS.items():
        catalog = documents.get(template)
        if catalog is not None:
            catalog_name = catalog.get("name")
            if not isinstance(catalog_name, str) or not NAME_RE.fullmatch(catalog_name):
                fail(
                    "invalid_marketplace", template, "use a kebab-case marketplace name"
                )
            catalog_names.append(catalog_name)
            entries = catalog.get("plugins")
            entry = (
                entries[0] if isinstance(entries, list) and len(entries) == 1 else None
            )
            if not isinstance(entry, dict):
                fail(
                    "invalid_marketplace",
                    template,
                    "exactly one plugin entry is required",
                )
            else:
                if entry.get("name") != plugin.get("name"):
                    fail("marketplace_name_drift", template, "plugin names must match")
                if "version" in entry:
                    fail(
                        "duplicate_version_authority",
                        template,
                        "config/plugin.json is the sole plugin-version authority",
                    )
                if destination.startswith(".agents/"):
                    source = {"source": "local", "path": "./"}
                    policy = {
                        "installation": "AVAILABLE",
                        "authentication": "ON_INSTALL",
                    }
                    if (
                        entry.get("policy") != policy
                        or entry.get("category") != "Productivity"
                    ):
                        fail(
                            "invalid_marketplace_policy",
                            template,
                            "declare available, local-first Productivity installation",
                        )
                    interface = catalog.get("interface")
                    if (
                        not isinstance(interface, dict)
                        or not isinstance(interface.get("displayName"), str)
                        or not interface["displayName"].strip()
                    ):
                        fail(
                            "invalid_marketplace",
                            template,
                            "interface.displayName is required",
                        )
                else:
                    source = "./"
                    if catalog.get("version") != plugin.get("version"):
                        fail(
                            "version_drift",
                            template,
                            "marketplace version differs from config/plugin.json",
                        )
                if entry.get("source") != source:
                    fail(
                        "unsafe_marketplace_source",
                        template,
                        "source must be the audited distribution root",
                    )
        if destination in payload:
            if payload[destination] != payload.get(template):
                fail(
                    "marketplace_template_drift",
                    destination,
                    "catalog bytes differ from the reviewed template",
                )
        elif installed:
            fail(
                "incomplete_marketplace", destination, "distribution catalog is missing"
            )
    if len(catalog_names) == 2 and catalog_names[0] != catalog_names[1]:
        fail(
            "marketplace_name_drift",
            "config/public-codex-marketplace.json",
            "host marketplace names must match",
        )
    return findings
