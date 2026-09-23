import importlib.util
import pathlib
import tempfile
import unittest
from unittest import mock


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / ".github" / "scripts" / "release_version.py"

spec = importlib.util.spec_from_file_location("release_version", MODULE_PATH)
release_version = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_version)


class ReleaseVersionTest(unittest.TestCase):
    def test_default_increment_updates_last_numeric_component(self):
        self.assertEqual(
            release_version.compute_release_version("1.3.7"),
            "1.3.8",
        )

    def test_default_increment_updates_prerelease_suffix_counter(self):
        self.assertEqual(
            release_version.compute_release_version("1.4.0rc1"),
            "1.4.0rc2",
        )

    def test_requested_version_is_returned_when_valid(self):
        self.assertEqual(
            release_version.compute_release_version("1.3.7", "2.0.0"),
            "2.0.0",
        )

    def test_invalid_requested_version_raises_clear_error(self):
        with self.assertRaisesRegex(ValueError, "Requested version 'not-a-version'"):
            release_version.compute_release_version("1.3.7", "not-a-version")

    def test_main_reads_version_file_and_prints_result(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            version_file = pathlib.Path(tmp_dir) / "VERSION"
            version_file.write_text("1.3.7\n", encoding="utf-8")

            with mock.patch(
                "sys.argv",
                [
                    "release_version.py",
                    "--current-version-file",
                    str(version_file),
                ],
            ):
                with mock.patch("builtins.print") as mock_print:
                    release_version.main()

            mock_print.assert_called_once_with("1.3.8")

    def test_main_exits_cleanly_for_invalid_requested_version(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            version_file = pathlib.Path(tmp_dir) / "VERSION"
            version_file.write_text("1.3.7\n", encoding="utf-8")

            with mock.patch(
                "sys.argv",
                [
                    "release_version.py",
                    "--current-version-file",
                    str(version_file),
                    "--requested-version",
                    "not-a-version",
                ],
            ):
                with self.assertRaises(SystemExit) as context:
                    release_version.main()

        self.assertEqual(context.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
