"""
build_exe.py - Atalho na raiz para compilar o executável BaixarBoletos.
"""
import sys
from pathlib import Path

raiz = Path(__file__).resolve().parent
if str(raiz) not in sys.path:
    sys.path.insert(0, str(raiz))

from baixar_boletos.build_exe import compilar

if __name__ == "__main__":
    compilar()
