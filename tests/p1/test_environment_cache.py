from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.environment_cache import (
    delete_numeric_environment_cache_dirs,
    numeric_environment_cache_dirs,
)


class EnvironmentCacheSafetyTests(unittest.TestCase):
    def test_deletes_only_19_digit_direct_child_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            targets = (root / "1234567890123456789", root / "9876543210987654321")
            for target in targets:
                (target / "nested").mkdir(parents=True)
                (target / "nested" / "state.txt").write_text("state", encoding="utf-8")
            preserved_dir = root / "123456789012345678"
            preserved_dir.mkdir()
            preserved_file = root / "notes.txt"
            preserved_file.write_text("keep", encoding="utf-8")

            discovered = numeric_environment_cache_dirs(root)
            self.assertEqual([path.name for path in discovered], sorted(path.name for path in targets))

            deleted = delete_numeric_environment_cache_dirs(root)

            self.assertEqual(list(deleted), sorted(path.name for path in targets))
            self.assertTrue(preserved_dir.is_dir())
            self.assertTrue(preserved_file.is_file())
            self.assertEqual(numeric_environment_cache_dirs(root), ())

    def test_refuses_19_digit_file_instead_of_deleting_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "1234567890123456789"
            target.write_text("must remain", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "not a directory"):
                delete_numeric_environment_cache_dirs(root)

            self.assertEqual(target.read_text(encoding="utf-8"), "must remain")

    def test_refuses_relative_cache_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be absolute"):
            delete_numeric_environment_cache_dirs(Path("relative-cache"))


if __name__ == "__main__":
    unittest.main()
