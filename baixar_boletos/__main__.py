from pathlib import Path
import sys

# Garante path
_BASE_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _BASE_DIR.parent
for _p in [str(_ROOT_DIR), str(_BASE_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from baixar_boletos.gui import main
except ImportError:
    from gui import main

if __name__ == "__main__":
    main()
