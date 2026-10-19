#!/usr/bin/env python3
"""Independent product gate; does not write the manager release report or any catalog."""
from pathlib import Path
import runpy

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).with_name('rebuild-public-products.py')), run_name='__main__')
