from __future__ import annotations

import sys
from pathlib import Path

# Vercel executes this file from the repository root.  Keep the existing
# FastAPI application in backend/app as the single source of truth and expose
# it through the standard Vercel Python entrypoint.
ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402,F401
