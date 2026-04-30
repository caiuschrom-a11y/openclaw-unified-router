"""Vercel serverless entry point for the unified-router FastAPI app.

Vercel's Python runtime expects `app` (or `handler`) as the WSGI/ASGI callable
exported from this module. FastAPI is ASGI; Vercel auto-detects it.
"""

import sys
from pathlib import Path

# Vercel's build copies api/ into the deployment alongside src/. Make sure
# `from src.app import app` resolves regardless of CWD.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.app import app  # noqa: E402

# Vercel Python runtime needs `app` at module level for ASGI auto-detection.
__all__ = ["app"]
