"""Unit tests for subject pack loading and discovery."""

import unittest
from pathlib import Path

from netprep.subjects import (
    get_subject_pack,
    list_subject_packs,
    load_subject_pack,
)


class TestSubjects(unittest.TestCase):
    def test_load_computer_networks_pack(self) -> None:
        pack_dir = Path("subjects/computer_networks")
        self.assertTrue(pack_dir.exists())

        pack = load_subject_pack(pack_dir)
        self.assertEqual(pack.id, "computer_networks")
        self.assertEqual(pack.name, "Computer Networks")
        self.assertIn("OSI", pack.description)
        self.assertIn("protocol", pack.prompt_hint.lower())
        self.assertTrue(pack.notes_dir.exists())
        self.assertTrue(pack.eval_file.exists())

    def test_list_subject_packs(self) -> None:
        packs = list_subject_packs("subjects")
        self.assertGreaterEqual(len(packs), 1)
        ids = [p.id for p in packs]
        self.assertIn("computer_networks", ids)

    def test_get_subject_pack_by_id_and_name(self) -> None:
        # By exact id
        p1 = get_subject_pack("computer_networks", "subjects")
        self.assertIsNotNone(p1)
        self.assertEqual(p1.name, "Computer Networks")

        # By display name (case-insensitive)
        p2 = get_subject_pack("computer networks", "subjects")
        self.assertIsNotNone(p2)
        self.assertEqual(p2.id, "computer_networks")

        # Non-existent
        p3 = get_subject_pack("astrophysics", "subjects")
        self.assertIsNone(p3)

    def test_load_custom_pack(self) -> None:
        custom_dir = Path("subjects/_temp_test_pack")
        try:
            custom_dir.mkdir(parents=True, exist_ok=True)
            pack_yaml = custom_dir / "pack.yaml"
            pack_yaml.write_text(
                "name: Quantum Computing\n"
                "description: Qubits and quantum gates.\n"
                "prompt_hint: Focus on superposition and entanglement.\n",
                encoding="utf-8",
            )

            pack = load_subject_pack(custom_dir)
            self.assertEqual(pack.id, "_temp_test_pack")
            self.assertEqual(pack.name, "Quantum Computing")
            self.assertEqual(pack.prompt_hint, "Focus on superposition and entanglement.")
        finally:
            if (custom_dir / "pack.yaml").exists():
                (custom_dir / "pack.yaml").unlink()
            if custom_dir.exists():
                custom_dir.rmdir()


if __name__ == "__main__":
    unittest.main()
