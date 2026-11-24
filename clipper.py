#!/usr/bin/env python3
"""
Convenience launcher for yt-clipper.
Can be executed as `python clipper.py`.
"""
import sys
import os

# Add src to python path for direct local execution without install
src_dir = os.path.join(os.path.dirname(__file__), "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from yt_clipper.cli import main

if __name__ == "__main__":
    main()
