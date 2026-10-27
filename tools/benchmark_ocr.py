"""Repository-local launcher; no package installation or OCR model needed."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from smartarchive.evaluation.runner import main

if __name__ == '__main__':
    raise SystemExit(main())
