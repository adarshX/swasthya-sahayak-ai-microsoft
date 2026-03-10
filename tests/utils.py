"""Shared test utilities for Swasthya Sahayak tests."""

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# ANSI colour codes
# ---------------------------------------------------------------------------
RESET  = "\033[0m"
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
BLUE   = "\033[94m"

# Compound status labels (include leading spaces + label text)
PASS = f"{GREEN}  PASS{RESET}"
FAIL = f"{RED}  FAIL{RESET}"
INFO = f"{BLUE}  INFO{RESET}"
WARN = f"{YELLOW}  WARN{RESET}"

# ---------------------------------------------------------------------------
# .env loader
# ---------------------------------------------------------------------------
def load_env(path: str = ".env") -> None:
    """Load key=value pairs from *path* into os.environ (does not override existing vars)."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())
