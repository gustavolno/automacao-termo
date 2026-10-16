"""API da Central AC Cobrança."""
import os
import threading
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from baixar_boletos import email_service as E
from baixar_boletos.config import normalizar_texto

from . import settings, store
from .dados import repo
from .robots import tarefas
from .robots.jobs import Ocupado, gerenciador


@asynccontextmanager
async def ciclo(app: FastAPI):
    store.iniciar()
    gerenciador.limpar_antigos()
    threading.Thread(target=repo.fontes, daemon=True).start()   # carrega a planilha (~14 s) já na partida
    yield


app = FastAPI(title="Central AC Cobrança", lifespan=ciclo)


@app.middleware("http")
async def protecao(request: Request, call_next):
    """A Central só atende este computador. Páginas de outros sites não podem acionar robôs:
    exige Host local e, em qualquer alteração, o cabeçalho X-Central (que o navegador não deixa
    uma página alheia enviar sem pré-autorização)."""
    host = request.headers.get("host", "").split(":")[0]
    if host not in ("127.0.0.1", "localhost"):
        return JSONResponse({"detail": "host não permitido"}, status_code=403)
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-central") != "1":
        return JSONResponse({"detail": "requisição não autorizada"}, status_code=403)
    return await call_next(request)


@app.get("/api/ping")
def ping():
    return {"ok": True}


# ── dados ──
@app.get("/api/estado")
def estado():
    job = gerenciador.atual()
    return {"fontes": repo.fontes(), "hoje": date.today().isoformat(), "robo_ativo": job.resumo() if job else None,
            "negociadoras": [{"id": k, "nome": v} for k, v in settings.NEGOCIADORAS.items()]}


@app.get("/api/carteiras")
def carteiras():
    return repo.carteiras()


@app.get("/api/resumo")
def resumo(carteira: str = settings.TODAS):
    return repo.resumo(carteira)


@app.get("/api/clientes")
def clientes(carteira: str = settings.TODAS, status: str = "TODOS", q: str = "", limite: int = 60, offset: int = 0):
    lista = repo.clientes(carteira, status, q)
    # mais urgente primeiro: atraso, depois valor em aberto, depois nome
    lista.sort(key=lambda c: (-c["dias_atraso"], -(c["valor_pendente"] or 0), c["nome"]))
    return {"total": len(lista), "itens": lista[offset:offset + limite]}


_parser = None


def _pasta_cliente(c: dict) -> Optional[Path]:
    global _parser
    if _parser is None:
        from baixar_boletos.acordo_parser import AcordoParser
        _parser = AcordoParser()
    return _parser.obter_pasta_cliente_dropbox(c["nome"])


@app.get("/api/clientes/{cid}")
def ficha(cid: str):
    c = repo.cliente(cid)
    if not c:
        raise HTTPException(404, "cliente não encontrado")
    pasta = _pasta_cliente(c)
    docs = []
    if pasta and pasta.exists():
        docs = [{"nome": f.name, "kb": round(f.stat().st_size / 1024)} for f in sorted(pasta.iterdir()) if f.is_file()]
    boletos = pasta / "BOLETOS DO ACORDO" if pasta else None
    envios = E.carregar_historico().get(normalizar_texto(c["nome"]), [])
    return {"cliente": c, "parcelas": repo.parcelas(cid), "contatos": store.contatos_de(cid),
            "documentos": docs, "pasta": str(pasta) if pasta else None,
            "boletos_na_pasta": len(list(boletos.glob("*.pdf"))) if boletos and boletos.exists() else 0,
            "emails_enviados": [{"data": e["data"], "para": e["para"], "arquivos": len(e["arquivos"])} for e in reversed(envios)]}


class NovoContato(BaseModel):
    autor: str = ""
    canal: str = "Telefone"
    texto: str = Field(min_length=1, max_length=2000)
    lembrar_em: Optional[str] = None


@app.post("/api/clientes/{cid}/contatos")
def novo_contato(cid: str, body: NovoContato):
    if not repo.cliente(cid):
        raise HTTPException(404, "cliente não encontrado")
    return store.adicionar_contato(cid, body.autor, body.canal, body.texto, body.lembrar_em)


class Feito(BaseModel):
    feito: bool = True


@app.patch("/api/contatos/{contato_id}")
def contato_feito(contato_id: int, body: Feito):
    store.marcar_contato_feito(contato_id, body.feito)
    return {"ok": True}


class Atribuicao(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)
    carteira: str
    por: str = ""


@app.post("/api/atribuir")
def atribuir(body: Atribuicao):
    if body.carteira not in list(settings.NEGOCIADORAS) + [settings.A_DISTRIBUIR]:
        raise HTTPException(400, "carteira inválida")
    store.atribuir(body.ids, body.carteira, body.por)
    return {"ok": True, "atribuidos": len(body.ids)}


@app.post("/api/clientes/{cid}/abrir-pasta")
def abrir_pasta(cid: str):
    c = repo.cliente(cid)
    pasta = _pasta_cliente(c) if c else None
    if not pasta or not pasta.exists():
        raise HTTPException(404, "pasta do cliente não encontrada")
    os.startfile(str(pasta))
    return {"ok": True}


# ── robôs ──
@app.get("/api/robos")
def robos():
    return tarefas.CATALOGO


class NovoJob(BaseModel):
    tarefa: str
    params: dict = {}


@app.post("/api/jobs")
def iniciar_job(body: NovoJob):
    if body.tarefa not in tarefas.TAREFAS or (body.tarefa == "demo" and not os.getenv("CENTRAL_DEMO")):
        raise HTTPException(400, "tarefa desconhecida")
    if body.tarefa != "enviar_mes" and not [n for n in body.params.get("nomes", []) if str(n).strip()]:
        raise HTTPException(400, "informe ao menos um cliente")
    if body.tarefa == "enviar_mes":
        itens = body.params.get("itens")
        if not isinstance(itens, list) or not itens:
            raise HTTPException(400, "nenhum cliente selecionado para envio")
        for it in itens:
            if not isinstance(it, dict) or not str(it.get("nome", "")).strip() or not isinstance(it.get("emails"), list):
                raise HTTPException(400, "item de envio inválido (precisa de nome e lista de e-mails)")
    titulo = next((r["titulo"] for r in tarefas.CATALOGO if r["id"] == body.tarefa), body.tarefa)
    try:
        return gerenciador.iniciar(body.tarefa, body.params, titulo).resumo()
    except Ocupado as o:
        return JSONResponse({"detail": str(o), "job": o.job.resumo()}, status_code=409)


@app.get("/api/jobs")
def jobs():
    return store.listar_jobs()


@app.get("/api/jobs/{job_id}")
def job(job_id: str, desde: int = 0):
    j = gerenciador.obter(job_id)
    base = j.resumo() if j else store.obter_job(job_id)
    eventos = gerenciador.eventos(job_id, desde)
    if base is None or eventos is None:
        raise HTTPException(404, "robô não encontrado")
    return {**base, "eventos_novos": eventos}


class Resposta(BaseModel):
    pergunta: str
    resposta: str


@app.post("/api/jobs/{job_id}/resposta")
def responder(job_id: str, body: Resposta):
    try:
        gerenciador.responder(job_id, body.pergunta, body.resposta)
    except KeyError as e:
        raise HTTPException(409, str(e))
    return {"ok": True}


@app.post("/api/jobs/{job_id}/parar")
def parar(job_id: str):
    gerenciador.parar(job_id)
    return {"ok": True}


app.mount("/", StaticFiles(directory=settings.WEB_DIR, html=True), name="web")
