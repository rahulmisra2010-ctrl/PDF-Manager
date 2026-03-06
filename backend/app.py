"""
backend/app.py — Backend application entry point (Flask).

Thin wrapper that imports and runs the root Flask application.
For historical reasons this file exists alongside the root app.py;
both ultimately run the same Flask application.
"""

from __future__ import annotations

import importlib.util
import os
import sys

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_BACKEND_DIR)
_ROOT_APP = os.path.join(_ROOT_DIR, "app.py")

if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

# ---------------------------------------------------------------------------
# Load root app.py via importlib to avoid circular-import when backend/ is
# earlier on sys.path than the repo root.
# ---------------------------------------------------------------------------
try:
    _spec = importlib.util.spec_from_file_location("_root_app", _ROOT_APP)
    _root_module = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
    _spec.loader.exec_module(_root_module)  # type: ignore[union-attr]
    app = _root_module.app
    create_app = _root_module.create_app
except Exception as _exc:
    raise ImportError(
        f"Could not load root app.py from {_ROOT_APP}: {_exc}\n"
        "Ensure all dependencies are installed: pip install -r backend/requirements.txt"
    ) from _exc

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)

