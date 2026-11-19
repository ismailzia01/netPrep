"""Unit tests for configuration loading and management."""

import unittest
from pathlib import Path

from netprep.config import AppConfig, load_config, save_config


class TestConfig(unittest.TestCase):
    def test_default_config_values(self) -> None:
        config = AppConfig()
        self.assertEqual(config.hotkey, "<ctrl>+<alt>+s")
        self.assertEqual(config.active_subject, "computer_networks")
        self.assertEqual(config.model_name, "dummy")
        self.assertEqual(config.scan_timeout, 10.0)
        self.assertEqual(config.subjects_dir, "subjects")

    def test_config_from_dict_and_to_dict(self) -> None:
        data = {
            "hotkey": "<cmd>+<shift>+p",
            "active_subject": "operating_systems",
            "model_name": "qwen2.5:1.5b",
            "scan_timeout": 5.5,
            "subjects_dir": "custom_subjects",
        }
        cfg = AppConfig.from_dict(data)
        self.assertEqual(cfg.hotkey, "<cmd>+<shift>+p")
        self.assertEqual(cfg.active_subject, "operating_systems")
        self.assertEqual(cfg.model_name, "qwen2.5:1.5b")
        self.assertEqual(cfg.scan_timeout, 5.5)
        self.assertEqual(cfg.subjects_dir, "custom_subjects")

        exported = cfg.to_dict()
        self.assertEqual(exported["hotkey"], "<cmd>+<shift>+p")
        self.assertEqual(exported["scan_timeout"], 5.5)

    def test_load_config_missing_file_returns_defaults(self) -> None:
        non_existent = Path("non_existent_config_123.yaml")
        cfg = load_config(non_existent)
        self.assertEqual(cfg.active_subject, "computer_networks")
        self.assertEqual(cfg.hotkey, "<ctrl>+<alt>+s")

    def test_load_and_save_config_roundtrip(self) -> None:
        cfg_file = Path("test_temp_config.json")
        try:
            original = AppConfig(
                hotkey="<ctrl>+<space>",
                active_subject="algorithms",
                model_name="test_model",
                scan_timeout=3.0,
            )
            save_config(original, cfg_file)
            self.assertTrue(cfg_file.exists())

            loaded = load_config(cfg_file)
            self.assertEqual(loaded.hotkey, "<ctrl>+<space>")
            self.assertEqual(loaded.active_subject, "algorithms")
            self.assertEqual(loaded.model_name, "test_model")
            self.assertEqual(loaded.scan_timeout, 3.0)
        finally:
            if cfg_file.exists():
                cfg_file.unlink()

    def test_load_config_malformed_returns_defaults(self) -> None:
        bad_file = Path("test_temp_broken.json")
        try:
            bad_file.write_text("{ broken json content ...", encoding="utf-8")
            cfg = load_config(bad_file)
            self.assertIsInstance(cfg, AppConfig)
            self.assertEqual(cfg.hotkey, "<ctrl>+<alt>+s")
        finally:
            if bad_file.exists():
                bad_file.unlink()


if __name__ == "__main__":
    unittest.main()
