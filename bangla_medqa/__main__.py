"""Support `python -m bangla_medqa` — delegates to `run_bangla_medqa.py` at repo root."""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from run_bangla_medqa import main

if __name__ == "__main__":
    main()
