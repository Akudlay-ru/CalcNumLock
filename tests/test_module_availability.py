import importlib
from pathlib import Path
import tempfile
import unittest


class ModuleAvailabilityTests(unittest.TestCase):
    def test_bundled_module_is_available_without_external_source_file(self):
        try:
            module = importlib.import_module("module_availability")
        except ModuleNotFoundError as exc:
            self.fail(f"runtime module detection is unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            app_root = Path(tmp)
            self.assertTrue(module.module_is_available("json", app_root))
            self.assertFalse(module.module_is_available("calcnumlock_missing_module_for_test", app_root))


if __name__ == "__main__":
    unittest.main()
