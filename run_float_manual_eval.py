from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
SRC = REPO_ROOT / "scheme3" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ce_scheme3.manual_eval import main


if __name__ == "__main__":
    main()
