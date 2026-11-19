"""Subject pack discovery and management for netPrep."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


@dataclass
class SubjectPack:
    """Represents a subject domain pack with guidance notes and eval questions."""

    id: str
    name: str
    description: str
    prompt_hint: str
    path: Path
    notes_dir: Path
    eval_file: Path

    def to_dict(self) -> dict[str, Any]:
        """Convert pack metadata to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "prompt_hint": self.prompt_hint,
            "path": str(self.path),
            "notes_dir": str(self.notes_dir),
            "eval_file": str(self.eval_file),
        }


def _read_pack_metadata(pack_dir: Path) -> dict[str, Any]:
    """Read metadata dictionary from pack.yaml or pack.json."""
    yaml_file = pack_dir / "pack.yaml"
    yml_file = pack_dir / "pack.yml"
    json_file = pack_dir / "pack.json"

    target_file = None
    if yaml_file.exists():
        target_file = yaml_file
    elif yml_file.exists():
        target_file = yml_file
    elif json_file.exists():
        target_file = json_file

    if target_file is None:
        raise FileNotFoundError(f"No pack.yaml or pack.json found in {pack_dir}")

    text = target_file.read_text(encoding="utf-8")

    if yaml is not None and target_file.suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data

    if target_file.suffix == ".json" or yaml is None:
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Simple fallback parser for key: value pairs if yaml library isn't installed
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            result[key.strip()] = val.strip().strip("\"'")
    return result


def load_subject_pack(pack_dir: Path | str) -> SubjectPack:
    """Load a single subject pack from its directory."""
    dir_path = Path(pack_dir).resolve()
    if not dir_path.is_dir():
        raise NotADirectoryError(f"Subject pack directory does not exist: {dir_path}")

    metadata = _read_pack_metadata(dir_path)

    folder_id = dir_path.name
    name = str(metadata.get("name", folder_id.replace("_", " ").title()))
    description = str(metadata.get("description", ""))
    prompt_hint = str(metadata.get("prompt_hint", ""))

    notes_dir = dir_path / "notes"
    eval_file = dir_path / "eval" / "questions.json"

    return SubjectPack(
        id=folder_id,
        name=name,
        description=description,
        prompt_hint=prompt_hint,
        path=dir_path,
        notes_dir=notes_dir,
        eval_file=eval_file,
    )


def list_subject_packs(subjects_dir: Path | str) -> list[SubjectPack]:
    """Scan subjects directory and return all discovered subject packs."""
    root = Path(subjects_dir).resolve()
    if not root.exists() or not root.is_dir():
        return []

    packs: list[SubjectPack] = []
    for item in sorted(root.iterdir()):
        if item.is_dir() and not item.name.startswith("."):
            try:
                pack = load_subject_pack(item)
                packs.append(pack)
            except Exception:
                # Ignore non-pack directories
                continue

    return packs


def get_subject_pack(identifier: str, subjects_dir: Path | str) -> SubjectPack | None:
    """Retrieve a subject pack by id (folder name) or human-readable name."""
    packs = list_subject_packs(subjects_dir)
    target = identifier.strip().lower()

    for pack in packs:
        if pack.id.lower() == target or pack.name.lower() == target:
            return pack
    return None
