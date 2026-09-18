"""Compatibility entry point: python simulator/simulator.py --register ..."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from simulator.client import main

if __name__ == '__main__':
    main()
