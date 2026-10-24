"""Unit tests for metadata validation and safe local data inspection."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from simulation.inventory import build_report, fingerprint_file, validate_inventory

TEMPLATE = Path(__file__).resolve().parents[1] / "data/sample/inventory.json"


class InventoryTests(unittest.TestCase):
    """Exercise incomplete inventories, invalid inputs and file boundaries."""

    def setUp(self):
        """Load fresh template JSON; inputs: none; output: self.inventory fixture."""
        self.inventory = json.loads(TEMPLATE.read_text())

    def test_template_is_pending_not_ready(self):
        """Check template without files; input: template; output: pending report."""
        report = build_report(self.inventory, "data")
        self.assertEqual(report["errors"], [])
        self.assertTrue(report["pending"])
        self.assertEqual(report["files"], [])

    def test_invalid_inventory_shapes(self):
        """Validate malformed JSON shapes; inputs: bad values; output: errors."""
        for value in (None, [], 5, {"study_area": {}, "datasets": None}):
            with self.subTest(value=value):
                self.assertTrue(validate_inventory(value))

    def test_invalid_bounds(self):
        """Reject invalid coordinates; inputs: bad bounds; output: errors."""
        for bounds in ([1, 2, 0, 3], [True, 0, 1, 1], [0, 0, float('nan'), 1], [0, 0, 1]):
            self.inventory["study_area"]["bounds_wgs84"] = bounds
            self.assertTrue(validate_inventory(self.inventory))

    def test_duplicate_and_missing_kinds(self):
        """Detect incomplete categories; input: duplicate entry; output: errors."""
        self.inventory["datasets"][-1] = copy.deepcopy(self.inventory["datasets"][0])
        errors = validate_inventory(self.inventory)
        self.assertTrue(any("duplicate" in e for e in errors))
        self.assertTrue(any("Missing" in e for e in errors))

    def test_available_requires_metadata(self):
        """Require source metadata; input: available empty entry; output: errors."""
        self.inventory["datasets"][0]["status"] = "available"
        self.assertTrue(validate_inventory(self.inventory))

    def test_checksum_and_unsafe_paths(self):
        """Check hash and containment; inputs: local and escaping paths; output: hash or exceptions."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dem.tif").write_bytes(b"test bytes, not real terrain")
            result = fingerprint_file(root, "dem.tif")
            self.assertEqual(result["sha256"], hashlib.sha256((root / "dem.tif").read_bytes()).hexdigest())
            self.assertEqual(result["size_bytes"], 28)
            for path in ("../escape", str(root / "dem.tif"), "missing", ""):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    fingerprint_file(root, path)
            (root / "escape").symlink_to(root.parent)
            with self.assertRaises(ValueError):
                fingerprint_file(root, "escape/outside")


if __name__ == "__main__":
    unittest.main()
