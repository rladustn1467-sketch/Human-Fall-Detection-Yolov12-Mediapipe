"""The deployment copy: server and web app at the top of the folder, nothing private."""
import sys
import tempfile
import unittest
from pathlib import Path

from . import ROOT

sys.path.insert(0, str(Path(ROOT) / "tools"))
import export_deploy


class ExportTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)

    def test_server_is_at_the_top_without_development_files(self):
        self.assertEqual(export_deploy.export(self.dir), [])
        for name in ("main.py", "requirements.txt", "README.md", ".gitignore", ".env.example", "app/next/index.html"):
            self.assertTrue((self.dir / name).is_file(), name)
        for name in ("tests", "server", "pc", "mobile", "run_server.bat", "app/next/dev.html", "app/next/js/dev.js"):
            self.assertFalse((self.dir / name).exists(), name)

    def test_keeps_git_and_removes_stale_files(self):
        (self.dir / ".git").mkdir()
        (self.dir / ".git" / "HEAD").write_text("ref")
        (self.dir / "old.py").write_text("x")
        export_deploy.export(self.dir)
        self.assertTrue((self.dir / ".git" / "HEAD").exists())
        self.assertFalse((self.dir / "old.py").exists())

    def test_untracked_private_files_are_not_copied(self):
        names = [str(rel) for _, rel in export_deploy.server_files()]
        for name in (".env", "fall.db", "events.json", "residents.json", "access_token.txt"):
            self.assertNotIn(name, names)

    def test_private_files_and_secrets_are_reported(self):
        (self.dir / ".env").write_text("x")
        (self.dir / "note.txt").write_text("-----BEGIN PRIVATE KEY-----")
        found = export_deploy.problems(self.dir)
        self.assertEqual(len(found), 2)


if __name__ == "__main__":
    unittest.main()
