import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from runtime.overlay import IsolationError, load_overlay
from runtime.schemas import SchemaError

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "overlays"


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "overlays"
        shutil.copytree(FIXTURES, self.root)

    def load(self, requested="alpha", **kwargs):
        return load_overlay(self.root, authorized_clients={"alpha"}, session_client="alpha",
                            requested_client=requested, **kwargs)

    def test_only_bound_client_loaded(self):
        alpha = self.load()
        self.assertIn("ALPHA_ONLY", alpha["canary"])
        self.assertNotIn("BETA_ONLY", json.dumps(alpha))
        beta = load_overlay(self.root, authorized_clients={"beta"}, session_client="beta",
                            requested_client="beta")
        self.assertIn("BETA_ONLY", beta["canary"])

    def test_cross_client_denied_before_file_open(self):
        with patch("runtime.overlay.os.open") as opened:
            with self.assertRaises(IsolationError):
                self.load("beta")
            opened.assert_not_called()

    def test_document_traversal_denied_before_open(self):
        with patch("runtime.overlay.os.open") as opened:
            with self.assertRaises(IsolationError):
                self.load(document="../beta/facts.json")
            opened.assert_not_called()

    def test_symlink_client_directory_rejected(self):
        shutil.rmtree(self.root / "alpha")
        (self.root / "alpha").symlink_to(self.root / "beta", target_is_directory=True)
        with self.assertRaises(OSError):
            self.load()

    def test_symlink_document_rejected(self):
        (self.root / "alpha" / "facts.json").unlink()
        (self.root / "alpha" / "facts.json").symlink_to(self.root / "beta" / "facts.json")
        with self.assertRaises(OSError):
            self.load()

    def test_fifo_rejected_without_waiting_for_writer(self):
        target = self.root / "alpha" / "facts.json"
        target.unlink()
        os.mkfifo(target)
        with self.assertRaises(IsolationError):
            self.load()

    def test_mislabeled_and_nonsynthetic_content_rejected(self):
        target = self.root / "alpha" / "facts.json"
        data = json.loads(target.read_text())
        data["client_id"] = "beta"
        target.write_text(json.dumps(data))
        with self.assertRaises(IsolationError):
            self.load()
        data.update(client_id="alpha", synthetic=False)
        target.write_text(json.dumps(data))
        with self.assertRaises(SchemaError):
            self.load()


if __name__ == "__main__":
    unittest.main()
