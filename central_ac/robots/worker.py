"""Entrada do robô: python -m central_ac.robots.worker <tarefa> <arquivo-de-parametros.json>"""
import json
import sys
import traceback

from central_ac import settings  # noqa: F401  (coloca a raiz do projeto no sys.path)

from .protocolo import Contexto, Parado, emitir


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    tarefa, arq = sys.argv[1], sys.argv[2]
    with open(arq, encoding="utf-8") as f:
        params = json.load(f)
    ctx = Contexto()
    ctx.ouvir_stdin()
    from . import tarefas
    try:
        resultado = tarefas.TAREFAS[tarefa](ctx, params)
        emitir({"t": "fim", "estado": "parado" if ctx.parar.is_set() else "concluido", "resultado": resultado})
    except Parado:
        emitir({"t": "fim", "estado": "parado", "resultado": None})
    except Exception as e:
        ctx.log("Erro inesperado: " + "".join(traceback.format_exception_only(type(e), e)).strip(), "ERROR")
        ctx.log(traceback.format_exc(), "DEBUG")
        emitir({"t": "fim", "estado": "falhou", "resultado": {"erro": str(e)}})


if __name__ == "__main__":
    main()
