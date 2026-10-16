"""Armazenamento local da Central (SQLite): contatos, redistribuição de carteira e histórico de robôs.
Quando o PostgreSQL chegar, esta é a camada que troca: as funções abaixo viram consultas SQL no banco."""
import json
import sqlite3
import threading
import time
from contextlib import contextmanager

from . import settings

_lock = threading.Lock()

ESQUEMA = """
CREATE TABLE IF NOT EXISTS contatos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id TEXT NOT NULL,
    quando TEXT NOT NULL,
    autor TEXT NOT NULL DEFAULT '',
    canal TEXT NOT NULL DEFAULT 'Telefone',
    texto TEXT NOT NULL,
    lembrar_em TEXT,
    feito INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_contatos_cliente ON contatos(cliente_id);
CREATE TABLE IF NOT EXISTS atribuicoes (
    cliente_id TEXT PRIMARY KEY,
    carteira TEXT NOT NULL,
    quando TEXT NOT NULL,
    por TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    tarefa TEXT NOT NULL,
    titulo TEXT NOT NULL,
    params TEXT NOT NULL,
    estado TEXT NOT NULL,
    inicio TEXT NOT NULL,
    fim TEXT,
    resultado TEXT
);
"""


@contextmanager
def _con():
    with _lock:
        con = sqlite3.connect(settings.DB_PATH, timeout=30)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()


def iniciar():
    with _con() as c:
        c.executescript(ESQUEMA)
        c.execute("UPDATE jobs SET estado='interrompido', fim=? WHERE estado IN ('rodando','aguardando')", (agora(),))


def agora() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


# ── contatos ──
def contatos_de(cliente_id: str) -> list:
    with _con() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM contatos WHERE cliente_id=? ORDER BY quando DESC, id DESC", (cliente_id,))]


def adicionar_contato(cliente_id, autor, canal, texto, lembrar_em=None) -> dict:
    with _con() as c:
        cur = c.execute("INSERT INTO contatos (cliente_id, quando, autor, canal, texto, lembrar_em) VALUES (?,?,?,?,?,?)",
                        (cliente_id, agora(), autor, canal, texto.strip(), lembrar_em or None))
        return dict(c.execute("SELECT * FROM contatos WHERE id=?", (cur.lastrowid,)).fetchone())


def marcar_contato_feito(contato_id: int, feito: bool = True):
    with _con() as c:
        c.execute("UPDATE contatos SET feito=? WHERE id=?", (1 if feito else 0, contato_id))


def resumo_contatos() -> dict:
    """{cliente_id: {"ultimo": 'AAAA-MM-DD HH:MM:SS', "lembrar_em": 'AAAA-MM-DD' (o mais próximo pendente)}}"""
    with _con() as c:
        ultimos = {r["cliente_id"]: r["u"] for r in c.execute("SELECT cliente_id, MAX(quando) u FROM contatos GROUP BY cliente_id")}
        lembretes = {r["cliente_id"]: r["l"] for r in c.execute(
            "SELECT cliente_id, MIN(lembrar_em) l FROM contatos WHERE feito=0 AND lembrar_em IS NOT NULL GROUP BY cliente_id")}
    return {k: {"ultimo": ultimos.get(k), "lembrar_em": lembretes.get(k)} for k in set(ultimos) | set(lembretes)}


# ── redistribuição de carteira ──
def atribuicoes() -> dict:
    with _con() as c:
        return {r["cliente_id"]: r["carteira"] for r in c.execute("SELECT cliente_id, carteira FROM atribuicoes")}


def atribuir(cliente_ids: list, carteira: str, por: str = ""):
    with _con() as c:
        c.executemany("INSERT INTO atribuicoes (cliente_id, carteira, quando, por) VALUES (?,?,?,?) "
                      "ON CONFLICT(cliente_id) DO UPDATE SET carteira=excluded.carteira, quando=excluded.quando, por=excluded.por",
                      [(i, carteira, agora(), por) for i in cliente_ids])


# ── histórico de robôs ──
def salvar_job(job: dict):
    with _con() as c:
        c.execute("INSERT INTO jobs (id, tarefa, titulo, params, estado, inicio, fim, resultado) VALUES (?,?,?,?,?,?,?,?) "
                  "ON CONFLICT(id) DO UPDATE SET estado=excluded.estado, fim=excluded.fim, resultado=excluded.resultado",
                  (job["id"], job["tarefa"], job["titulo"], json.dumps(job["params"], ensure_ascii=False),
                   job["estado"], job["inicio"], job.get("fim"), json.dumps(job.get("resultado"), ensure_ascii=False)))


def listar_jobs(limite: int = 30) -> list:
    with _con() as c:
        rows = c.execute("SELECT * FROM jobs ORDER BY inicio DESC LIMIT ?", (limite,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["params"] = json.loads(d["params"])
        d["resultado"] = json.loads(d["resultado"]) if d["resultado"] else None
        out.append(d)
    return out


def obter_job(job_id: str):
    with _con() as c:
        r = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["params"] = json.loads(d["params"])
    d["resultado"] = json.loads(d["resultado"]) if d["resultado"] else None
    return d
