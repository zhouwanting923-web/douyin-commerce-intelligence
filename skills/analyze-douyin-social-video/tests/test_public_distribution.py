from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from prepare_video import find_downloader  # noqa: E402


class PublicDistributionTests(unittest.TestCase):
    def test_url_mode_requires_explicit_adapter(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(FileNotFoundError, "local MP4"):
                find_downloader()

    def test_explicit_adapter_path_is_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = Path(temp_dir) / "adapter.py"
            adapter.write_text("# authorized test adapter\n", encoding="utf-8")
            with patch.dict(os.environ, {"DOUYIN_DOWNLOADER": str(adapter)}, clear=True):
                self.assertEqual(find_downloader(), adapter.resolve())


if __name__ == "__main__":
    unittest.main()
