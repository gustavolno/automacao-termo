"""python -m central_ac  ->  abre a Central no navegador."""
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from . import settings


def _abrir_quando_pronto():
    url = f"http://{settings.HOST}:{settings.PORT}"
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "/api/ping", timeout=1)
            break
        except Exception:
            time.sleep(1)
    webbrowser.open(url)


if __name__ == "__main__":
    if not settings.WEB_DIR.exists():
        raise SystemExit("pasta web não encontrada")
    threading.Thread(target=_abrir_quando_pronto, daemon=True).start()
    uvicorn.run("central_ac.main:app", host=settings.HOST, port=settings.PORT, log_level="warning")
