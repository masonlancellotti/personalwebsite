#!/usr/bin/env python3
"""Main entry point for Alpaca Crypto Trading Bot CLI."""

import sys
from pathlib import Path

# Ensure project root is in Python path for absolute imports
project_root = Path(__file__).parent.resolve()
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from cli import app

if __name__ == "__main__":
    app()








