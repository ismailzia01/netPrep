"""Configuration management for netPrep."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


@dataclass
class AppConfig:
    """Application configuration settings."""

    hotkey: str = "<ctrl>+<alt>+s"
    active_subject: str = "computer_networks"
    model_name: str = "qwen2.5:1.5b"
    scan_timeout: float = 10.0
    subjects_dir: str = "subjects"
    capture_region: tuple[int, int, int, int] | None = None
    ollama_host: str = "http://localhost:11434"
    ollama_timeout: float = 15.0
    ollama_keep_alive: str = "5m"
    overlay_duration: float = 6.0
    overlay_highlight_color: str = "#10B981"
    overlay_badge_color: str = "#059669"
    overlay_text_color: str = "#FFFFFF"
    overlay_fallback_position: str = "top_center"
    extra_settings: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AppConfig:
        """Create AppConfig from dictionary with graceful defaults."""
        raw_region = data.get("capture_region")
        capture_region: tuple[int, int, int, int] | None = None
        if isinstance(raw_region, (list, tuple)) and len(raw_region) == 4:
            try:
                capture_region = (
                    int(raw_region[0]),
                    int(raw_region[1]),
                    int(raw_region[2]),
                    int(raw_region[3]),
                )
            except (ValueError, TypeError):
                capture_region = None

        return cls(
            hotkey=str(data.get("hotkey", "<ctrl>+<alt>+s")),
            active_subject=str(data.get("active_subject", "computer_networks")),
            model_name=str(data.get("model_name", "qwen2.5:1.5b")),
            scan_timeout=float(data.get("scan_timeout", 10.0)),
            subjects_dir=str(data.get("subjects_dir", "subjects")),
            capture_region=capture_region,
            ollama_host=str(data.get("ollama_host", "http://localhost:11434")),
            ollama_timeout=float(data.get("ollama_timeout", 15.0)),
            ollama_keep_alive=str(data.get("ollama_keep_alive", "5m")),
            overlay_duration=float(data.get("overlay_duration", 6.0)),
            overlay_highlight_color=str(data.get("overlay_highlight_color", "#10B981")),
            overlay_badge_color=str(data.get("overlay_badge_color", "#059669")),
            overlay_text_color=str(data.get("overlay_text_color", "#FFFFFF")),
            overlay_fallback_position=str(data.get("overlay_fallback_position", "top_center")),
            extra_settings=data.get("extra_settings", {}),
        )


DEFAULT_CONFIG_PATH = Path("config.yaml")


def load_config(config_path: Path | str | None = None) -> AppConfig:
    """Load configuration from YAML or JSON file.

    Falls back to default AppConfig if file does not exist or fails to parse.
    """
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH

    if not path.exists():
        return AppConfig()

    try:
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            return AppConfig()

        parsed: dict[str, Any] | None = None
        if yaml is not None:
            loaded = yaml.safe_load(content)
            if isinstance(loaded, dict):
                parsed = loaded
        if parsed is None:
            # Fall back to JSON parsing
            loaded_json = json.loads(content)
            if isinstance(loaded_json, dict):
                parsed = loaded_json

        if parsed is not None:
            return AppConfig.from_dict(parsed)
    except Exception:
        # Fall back gracefully to default settings on read/parse errors
        pass

    return AppConfig()


def save_config(config: AppConfig, config_path: Path | str | None = None) -> None:
    """Save configuration to YAML or JSON file."""
    path = Path(config_path) if config_path is not None else DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    data = config.to_dict()

    if yaml is not None and (path.suffix in {".yaml", ".yml"} or not path.suffix):
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False)
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
