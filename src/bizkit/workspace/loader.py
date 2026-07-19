"""Workspace config file loading (spec D22/D23/D30).

The file is versioned and schema-validated: ``version`` is required,
unknown keys are rejected, and ``${ENV_VAR}`` placeholders are resolved
at load time. The content fingerprint is computed over the **raw
unresolved text** so secrets never influence or appear in audit.
"""

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from bizkit.config import (
    AccessConfig,
    BizkitConfig,
    TargetConfig,
    WorkflowConfig,
)
from bizkit.domain.access import Grant, Role, Scope
from bizkit.domain.table import TableRef
from bizkit.domain.table_config import TableConfig
from bizkit.domain.validation import Rule
from bizkit.exceptions import ConfigError

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_LITERAL_SECRET_PATTERN = re.compile(r"://[^/@\s]+:[^/@\s]+@")


class WorkspaceTable(BaseModel):
    """One ``tables:`` entry in the workspace file."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    backend: str
    schema_name: str | None = Field(default=None, alias="schema")
    table: str
    review_ttl: timedelta | None = None
    apply_ttl: timedelta | None = None
    allow_self_approval: bool | None = None
    max_changeset_items: int | None = None
    rules: list[Rule] = Field(default_factory=list)


class WorkspaceGrant(BaseModel):
    """One ``grants:`` entry in the workspace file."""

    model_config = ConfigDict(extra="forbid")

    principal: str
    role: Role
    scope: str = "*/*/*"


class WorkspaceFile(BaseModel):
    """The versioned workspace config file schema (spec D23).

    ``bizkit config schema`` emits this model's JSON Schema for editor
    tooling. Unknown keys are hard errors so typos cannot silently drop
    a grant or rule.
    """

    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    store_url: str | None = None
    targets: dict[str, TargetConfig] = Field(default_factory=dict)
    access: AccessConfig = Field(default_factory=AccessConfig)
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    tables: list[WorkspaceTable] = Field(default_factory=list)
    grants: list[WorkspaceGrant] = Field(default_factory=list)


@dataclass(frozen=True)
class LoadedWorkspace:
    """Result of loading a workspace file.

    Attributes:
        config: The resolved top-level configuration.
        tables: Registered table configurations.
        grants: Parsed grants (file access provider).
        fingerprint: SHA-256 hex digest of the raw unresolved file text.
    """

    config: BizkitConfig
    tables: list[TableConfig]
    grants: list[Grant]
    fingerprint: str


def _resolve_env(text: str) -> str:
    """Substitute ``${ENV_VAR}`` placeholders from the environment."""

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        value = os.environ.get(name)
        if value is None:
            raise ConfigError(
                f"Workspace config references undefined environment "
                f"variable ${{{name}}}"
            )
        return value

    return _ENV_PATTERN.sub(_sub, text)


def _parse_raw(path: Path, text: str) -> object:
    """Parse JSON (stdlib) or YAML (optional pyyaml) into plain data."""
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - env dependent
            raise ConfigError(
                "YAML workspace files require the 'pyyaml' package; "
                "install it or use a JSON workspace file"
            ) from exc
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Invalid YAML in {path}: {exc}") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc


def check_no_literal_secrets(raw_text: str) -> list[str]:
    """Find URL-embedded literal passwords (spec D30).

    Returns:
        Offending fragments (redacted); empty when the file is clean.
    """
    findings: list[str] = []
    for match in _LITERAL_SECRET_PATTERN.finditer(raw_text):
        fragment = match.group(0)
        user = fragment[3:].split(":", 1)[0]
        findings.append(f"://{user}:***@")
    return findings


def fingerprint_text(raw_text: str) -> str:
    """SHA-256 fingerprint of the raw unresolved file text (D22/D30)."""
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def load_workspace(path: str | Path) -> LoadedWorkspace:
    """Load, resolve, and validate a workspace config file.

    Args:
        path: Path to a ``.json``/``.yaml``/``.yml`` workspace file.

    Returns:
        The loaded workspace with config, tables, grants, fingerprint.

    Raises:
        ConfigError: On missing file, parse errors, schema violations,
            unresolvable environment references, or bad scope patterns.
    """
    file_path = Path(path)
    try:
        raw_text = file_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise ConfigError(f"Cannot read workspace config {file_path}: {exc}") from exc

    fingerprint = fingerprint_text(raw_text)
    resolved = _resolve_env(raw_text)
    data = _parse_raw(file_path, resolved)

    try:
        parsed = WorkspaceFile.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(f"Invalid workspace config {file_path}: {exc}") from exc

    config = BizkitConfig(
        store_url=parsed.store_url or BizkitConfig().store_url,
        targets=parsed.targets,
        access=parsed.access,
        workflow=parsed.workflow,
    )
    tables = [
        TableConfig(
            table=TableRef(
                backend=entry.backend,
                schema_name=entry.schema_name,
                table=entry.table,
            ),
            review_ttl=entry.review_ttl,
            apply_ttl=entry.apply_ttl,
            allow_self_approval=entry.allow_self_approval,
            max_changeset_items=entry.max_changeset_items,
            rules=entry.rules,
        )
        for entry in parsed.tables
    ]
    grants = [
        Grant(
            principal=entry.principal,
            role=entry.role,
            scope=Scope.parse(entry.scope),
        )
        for entry in parsed.grants
    ]
    return LoadedWorkspace(
        config=config, tables=tables, grants=grants, fingerprint=fingerprint
    )
