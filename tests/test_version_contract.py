from pathlib import Path
import unittest

import build_exe
import version


APP_ROOT = Path(__file__).resolve().parents[1]


class VersionContractTests(unittest.TestCase):
    def test_runtime_and_release_files_share_one_version(self):
        self.assertEqual(version.APP_VERSION, "10.2.3")
        self.assertEqual((APP_ROOT / "VERSION").read_text(encoding="utf-8").strip(), version.APP_VERSION)

    def test_stable_download_name_remains_version_10_channel(self):
        self.assertEqual(version.STABLE_EXE_NAME, "NumLockCalc_2026_10.exe")
        self.assertEqual(build_exe.APP_BASENAME, Path(version.STABLE_EXE_NAME).stem)


if __name__ == "__main__":
    unittest.main()
