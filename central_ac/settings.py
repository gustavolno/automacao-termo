import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from baixar_boletos.config import USER_DATA_DIR  # noqa: E402

DATA_DIR = USER_DATA_DIR / "central"
JOBS_DIR = DATA_DIR / "jobs"
DB_PATH = Path(os.getenv("CENTRAL_DB", DATA_DIR / "central.db"))
for _d in (DATA_DIR, JOBS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

HOST = os.getenv("CENTRAL_HOST", "127.0.0.1")   # só este computador; rede interna só depois do banco e dos logins
PORT = int(os.getenv("CENTRAL_PORT", "8765"))

# Negociadoras atuais (coluna "OPERADOR RESPONSAVEL" da planilha da Jaci). Os demais operadores
# são advogados/antigos e ficam em "A distribuir" até a gestão atribuir.
NEGOCIADORAS = {"EMILIA": "Emília", "YANCA": "Yanca", "LITIELLY": "Litielly",
                "GABRIELLE": "Gabrielle", "LUISA": "Luisa"}
A_DISTRIBUIR = "DISTRIBUIR"
TODAS = "TODAS"

WEB_DIR = Path(__file__).resolve().parent / "web"
