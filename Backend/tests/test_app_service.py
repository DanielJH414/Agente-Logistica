import os
import sys
import tempfile
import unittest
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.append(str(backend_dir))

from app_service import build_document_folders, get_documents_dir


class AppServiceTests(unittest.TestCase):
    def test_build_document_folders_groups_files_by_top_level_folder(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "Financiero").mkdir(parents=True)
            (root / "Financiero" / "reporte.pdf").write_bytes(b"reporte")
            (root / "Logística").mkdir(parents=True)
            (root / "Logística" / "manual.txt").write_text("manual", encoding="utf-8")

            payload = build_document_folders(root)

            self.assertIn("Financiero", {folder["title"] for folder in payload["folders"]})
            self.assertIn("Logística", {folder["title"] for folder in payload["folders"]})
            self.assertTrue(any(folder["files"] for folder in payload["folders"] if folder["title"] == "Financiero"))

    def test_get_documents_dir_uses_environment_override(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            previous = os.environ.get("DOCUMENTS_DIR")
            os.environ["DOCUMENTS_DIR"] = tmp_dir
            try:
                self.assertEqual(Path(tmp_dir).resolve(), get_documents_dir())
            finally:
                if previous is None:
                    os.environ.pop("DOCUMENTS_DIR", None)
                else:
                    os.environ["DOCUMENTS_DIR"] = previous


if __name__ == "__main__":
    unittest.main()
