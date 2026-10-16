"""Conversa entre a Central e o robô (subprocesso): linhas "@@{json}" no stdout do robô;
respostas e pedidos de parada vêm pelo stdin, uma linha JSON cada."""
import json
import re
import sys
import threading
import time

MARCA = "@@"
_NIVEL = re.compile(r"^\d\d:\d\d:\d\d - (\w+) - (.*)$", re.S)
_saida = threading.Lock()


def emitir(obj: dict):
    with _saida:
        sys.stdout.write(MARCA + json.dumps(obj, ensure_ascii=False) + "\n")
        sys.stdout.flush()


class Parado(Exception):
    """O usuário pediu para parar."""


class Falha(Exception):
    """Falha esperada de um item (vai para o resultado, não derruba o lote)."""


class Contexto:
    """O que as tarefas usam para falar com a Central."""

    def __init__(self):
        self.parar = threading.Event()
        self._servicos = []
        self._respostas = {}
        self._cond = threading.Condition()
        self._seq = 0

    # saída
    def log(self, msg: str, nivel: str = "INFO"):
        emitir({"t": "log", "nivel": nivel, "msg": str(msg)})

    def log_servico(self, texto: str, nivel: str = "INFO"):
        """Os serviços antigos logam 'HH:MM:SS - NIVEL - mensagem'."""
        m = _NIVEL.match(str(texto))
        if m:
            nivel, texto = m.group(1), m.group(2)
        self.log(texto, nivel)

    def item(self, nome: str, etapa: str, estado: str = "rodando", detalhe: str = ""):
        """estado: espera | rodando | ok | aviso | falhou | pulado"""
        emitir({"t": "item", "nome": nome, "etapa": etapa, "estado": estado, "detalhe": detalhe})

    # parada
    def registrar(self, servico):
        self._servicos.append(servico)

    def cancelar_tudo(self):
        self.parar.set()
        for s in self._servicos:
            try:
                s.cancelar()
            except Exception:
                pass
        with self._cond:
            self._cond.notify_all()

    def checar(self):
        if self.parar.is_set():
            raise Parado()

    # perguntas
    def perguntar(self, titulo: str, texto: str, opcoes=("Sim", "Não")) -> str:
        """Bloqueia até a resposta do usuário; se mandarem parar, devolve a última opção."""
        self._seq += 1
        pid = f"q{self._seq}-{int(time.time())}"
        emitir({"t": "ask", "id": pid, "titulo": titulo, "texto": texto, "opcoes": list(opcoes)})
        with self._cond:
            while pid not in self._respostas and not self.parar.is_set():
                self._cond.wait(timeout=1)
            return self._respostas.pop(pid, opcoes[-1])

    def receber(self, msg: dict):
        if msg.get("t") == "resp":
            with self._cond:
                self._respostas[msg["id"]] = msg.get("resp")
                self._cond.notify_all()
        elif msg.get("t") == "parar":
            self.cancelar_tudo()

    def ouvir_stdin(self):
        def _ler():
            for linha in sys.stdin:
                try:
                    self.receber(json.loads(linha))
                except Exception:
                    pass
            self.cancelar_tudo()    # a Central fechou o pipe: não deixa o robô órfão
        threading.Thread(target=_ler, daemon=True).start()
