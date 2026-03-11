from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


_ARCHIVE_PATH = Path(__file__).resolve().parent.parent / "archive" / "strategies_retired" / "inplay_wrapper.py"
_SPEC = spec_from_file_location("_archived_inplay_wrapper", _ARCHIVE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Cannot load archived inplay wrapper from {_ARCHIVE_PATH}")

_MODULE = module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)

InPlayWrapperConfig = _MODULE.InPlayWrapperConfig
InPlayWrapper = _MODULE.InPlayWrapper

__all__ = ["InPlayWrapper", "InPlayWrapperConfig"]
