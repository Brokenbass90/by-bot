from __future__ import annotations

import sys
import warnings
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

InPlayWrapper = None
InPlayWrapperConfig = None

_ARCHIVE_PATH = (
    Path(__file__).resolve().parent.parent
    / "archive"
    / "strategies_retired"
    / "inplay_wrapper.py"
)

try:
    _SPEC = spec_from_file_location("_archived_inplay_wrapper", _ARCHIVE_PATH)
    if _SPEC is None or _SPEC.loader is None:
        raise ImportError(f"spec_from_file_location returned None for {_ARCHIVE_PATH}")
    _MODULE = module_from_spec(_SPEC)
    sys.modules[_SPEC.name] = _MODULE
    _SPEC.loader.exec_module(_MODULE)
    InPlayWrapperConfig = _MODULE.InPlayWrapperConfig
    InPlayWrapper = _MODULE.InPlayWrapper
except Exception as _shim_exc:
    warnings.warn(
        f"[inplay_wrapper shim] Could not load archived module from "
        f"{_ARCHIVE_PATH}: {_shim_exc}. "
        "InPlayWrapper and InPlayWrapperConfig will be None. "
        "Any code that instantiates InPlayWrapper will raise at runtime.",
        stacklevel=1,
    )

__all__ = ["InPlayWrapper", "InPlayWrapperConfig"]
