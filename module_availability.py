"""Runtime module detection for source and frozen builds."""

import importlib.util
from pathlib import Path


def module_is_available(module_name: str, app_root: Path) -> bool:
    source_path = Path(app_root) / (module_name.replace(".", "/") + ".py")
    if source_path.exists():
        return True
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, AttributeError, ValueError):
        return False
