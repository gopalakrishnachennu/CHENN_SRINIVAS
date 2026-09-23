"""Technology registry edits with audit trail."""

from __future__ import annotations

import json
from typing import Any

from resume_engine.config.settings import PROJECT_ROOT
from resume_engine.ui.services.audit_service import record_audit_event

REGISTRY_PATH = PROJECT_ROOT / "resume_engine_data" / "skill_registry.json"


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.exists():
        return {"technologies": {}, "aliases": {}, "adjacent": {}}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def save_registry(registry: dict[str, Any], *, actor: str | None = None, action: str = "registry.save") -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    old = load_registry() if REGISTRY_PATH.exists() else {}
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    record_audit_event(
        action=action,
        actor=actor,
        entity_type="registry",
        entity_id="skill_registry",
        old_value={"keys": list(old.keys())},
        new_value={"keys": list(registry.keys())},
    )


def search_technologies(query: str = "", limit: int = 100) -> list[dict[str, Any]]:
    registry = load_registry()
    q = query.lower().strip()
    # Support multiple historical shapes
    techs = registry.get("technologies") or registry.get("skills") or registry
    rows = []
    if isinstance(techs, dict):
        for name, meta in techs.items():
            if isinstance(meta, dict):
                row = {"canonical_name": name, **meta}
            else:
                row = {"canonical_name": name, "value": meta}
            if not q or q in name.lower() or q in json.dumps(row).lower():
                rows.append(row)
            if len(rows) >= limit:
                break
    elif isinstance(techs, list):
        for item in techs:
            if isinstance(item, dict):
                name = item.get("name") or item.get("canonical_name") or ""
                if not q or q in name.lower():
                    rows.append(item)
            if len(rows) >= limit:
                break
    return rows


def add_alias(canonical: str, alias: str, *, actor: str | None = None) -> dict[str, Any]:
    registry = load_registry()
    aliases = registry.setdefault("aliases", {})
    aliases[alias] = canonical
    save_registry(registry, actor=actor, action="registry.add_alias")
    return {"canonical": canonical, "alias": alias}


def block_technology(name: str, *, actor: str | None = None) -> None:
    registry = load_registry()
    blocked = registry.setdefault("blocked", [])
    if name not in blocked:
        blocked.append(name)
    save_registry(registry, actor=actor, action="registry.block")
