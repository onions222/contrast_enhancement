from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "scheme3" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ce_scheme3.starter_test_images import main


if __name__ == "__main__":
    main()
