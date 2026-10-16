"""As tarefas dos robôs. Cada uma recebe (ctx, params) e devolve o resultado que a Central mostra.
Reaproveitam os serviços de baixar_boletos (Global Office, planilha, termo, webmail)."""
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from baixar_boletos import email_service as E
from baixar_boletos.config import mes_inicial_boletos, normalizar_texto

from .protocolo import Contexto, Falha, Parado

ADVOGADO = re.compile(r"adv|juridico|jurídico", re.I)


# ── utilidades ──
def _nomes(p: dict) -> list:
    vistos, out = set(), []
    for n in p.get("nomes", []):
        n = " ".join(str(n).split())
        if n and normalizar_texto(n) not in vistos:
            vistos.add(normalizar_texto(n))
            out.append(n)
    return out


def _vencimento_pdf(arq: Path) -> Optional[date]:
    import pymupdf
    try:
        with pymupdf.open(str(arq)) as d:
            texto = " ".join(pg.get_text() for pg in d)
    except Exception:
        return None
    m = re.search(r"Vencimento\s+(\d{2}/\d{2}/\d{4})", texto)
    return datetime.strptime(m.group(1), "%d/%m/%Y").date() if m else None


def _boletos_do_mes(pasta, mes: tuple) -> list:
    return [f for f in E.boletos_a_enviar(pasta) if E.mes_do_boleto(f) == mes] if pasta else []


def _vencido(arqs: list) -> bool:
    hoje = date.today()
    return any((v is None or v < hoje) for v in (_vencimento_pdf(f) for f in arqs))


# ── conferir (sem Global Office) ──
def conferir_mes(ctx: Contexto, p: dict) -> dict:
    """Para cada cliente: pasta, boleto do mês (e se está vencido), e-mail e avisos. Não envia nada."""
    mes = mes_inicial_boletos()
    try:
        lista = E.carregar_lista_emails()
    except Exception as e:
        ctx.log(f"Lista de envio não lida ({e}): e-mails serão procurados no termo e na planilha da LAYNA.", "WARNING")
        lista = {}
    itens = []
    nomes = _nomes(p)
    for nome in nomes:
        ctx.checar()
        ctx.item(nome, "Conferindo pasta e e-mail", "rodando")
        alertas = []
        item = lista.get(normalizar_texto(nome), {})
        pasta = E.localizar_pasta_boletos(nome, item.get("pasta", ""))
        arqs = _boletos_do_mes(pasta, mes)
        baixar = (not arqs) or _vencido(arqs)
        if not pasta:
            alertas.append(("info", "pasta de boletos ainda não existe (será criada ao baixar)"))
        elif not arqs:
            alertas.append(("info", f"sem o boleto de {E.rotulo_mes(mes)} na pasta (será baixado)"))
        elif baixar:
            alertas.append(("info", "boleto da pasta está vencido (será reemitido para daqui a 2 dias)"))
        if pasta and normalizar_texto(Path(pasta).parent.name) != normalizar_texto(nome):
            alertas.append(("atencao", f"a pasta encontrada se chama \"{Path(pasta).parent.name}\": confira se é a mesma pessoa"))

        emails, fonte = list(item.get("emails") or []), "lista de envio"
        if not emails:
            a = E.buscar_email_cliente(nome, lista)
            emails, fonte = a["emails"], a["fonte"] or ""
            if not emails:
                motivos = a.get("motivos") or []
                alertas.append(("erro", "sem e-mail" + (": " + "; ".join(motivos) if motivos else "")))
        limpos = []
        for e in emails:
            if E.e_do_escritorio(e):
                alertas.append(("info", f"e-mail do escritório ignorado ({e})"))
                continue
            novo, aviso = E.corrigir_email(e)
            if aviso:
                alertas.append(("info", aviso))
            if novo not in limpos:
                limpos.append(novo)
        if emails and not limpos:
            alertas.append(("erro", "só havia e-mail do próprio escritório"))
        if "SÓ PELO NOME" in fonte.upper():
            alertas.append(("atencao", "e-mail achado só pelo nome: confira se é da mesma pessoa"))
        if any(ADVOGADO.search(e.split("@")[0]) for e in limpos):
            alertas.append(("atencao", "e-mail parece de advogado(a)"))
        anterior = E.ultimo_envio_do_mes(nome, mes)
        if anterior:
            alertas.append(("atencao", f"boleto de {E.rotulo_mes(mes)} já foi enviado em {anterior['data'][:10].split('-')[2]}/{anterior['data'][5:7]} para {', '.join(anterior['para'])} (marque para reenviar)"))

        bloqueado = any(n == "erro" for n, _ in alertas)
        itens.append({"nome": nome, "pasta": str(pasta) if pasta else "", "arquivos": [f.name for f in arqs],
                      "baixar": baixar, "emails": limpos, "fonte": fonte,
                      "alertas": [{"nivel": n, "msg": m} for n, m in alertas],
                      "marcar": not bloqueado and not any(n == "atencao" for n, _ in alertas),
                      "bloqueado": bloqueado, "ja_enviado": bool(anterior)})
        ctx.item(nome, "Conferido", "aviso" if bloqueado else "ok",
                 "; ".join(m for n, m in alertas if n in ("erro", "bloqueio", "atencao")))
    return {"mes": E.rotulo_mes(mes), "mes_ref": list(mes), "itens": itens}


# ── Global Office: acordo, boleto vencido, download ──
def _servico_acordo(ctx: Contexto, est: dict):
    if est.get("svc"):
        return est["svc"]
    from baixar_boletos.acordo_service import AcordoService
    svc = AcordoService(log_callback=ctx.log_servico)
    ctx.registrar(svc)

    def confirmar(resumo: str) -> bool:
        # Reemissão de UM boleto vencido do mês (vencimento hoje+2, mesmo valor): pode vir autorizada no lote.
        if est.get("auto_reemitir") and "venceu sem ter sido enviado" in resumo and "Repetição: 0" in resumo:
            ctx.log("Reemissão do boleto vencido autorizada no início do lote.")
            return True
        return ctx.perguntar("Gravar no Global Office?", resumo, ["Gravar", "Não gravar"]) == "Gravar"
    svc.confirmar_gravacao = confirmar
    est["svc"] = svc
    return svc


def _recomecar_sessao(svc, visivel: bool):
    """Depois de GRAVAR algo, a tela de boletos da mesma sessão trava: fecha e abre outra."""
    if svc.gravou_algo:
        svc.fechar_sessao()
        time.sleep(3)
        svc.gravou_algo = False


def _garantir_boletos(ctx: Contexto, est: dict, nome: str, visivel: bool,
                      subir_acordo: bool = False, reemitir: bool = True) -> dict:
    """(acordo) -> (reemitir boleto vencido do mês) -> baixar os boletos para a pasta do Dropbox."""
    from baixar_boletos.acordo_service import ProcessamentoCancelado
    from baixar_boletos.downloader_service import DownloaderService
    svc = _servico_acordo(ctx, est)
    out = {"acordo": None, "reemitido": [], "baixados": 0, "encontrados": 0}
    try:
        if subir_acordo:
            ctx.item(nome, "Subindo o acordo no Global Office")
            if not svc.subir_acordo_completo(nome, visivel=visivel):
                raise Falha("o acordo não subiu (ver o registro) e os boletos avulsos não foram criados")
            out["acordo"] = "gravado" if svc.gravou_algo else "já existia"
            _recomecar_sessao(svc, visivel)
        if reemitir:
            ctx.item(nome, "Conferindo se o boleto do mês venceu")
            novos = svc.reemitir_boleto_vencido_mes(nome, visivel=visivel)
            if novos is None:
                raise Falha("não consegui reemitir o boleto vencido do mês")
            out["reemitido"] = novos
            _recomecar_sessao(svc, visivel)
        ctx.item(nome, "Baixando os boletos")
        svc.garantir_sessao_ativa(visivel=visivel)
        dl = DownloaderService(log_callback=ctx.log_servico, cancelado=ctx.parar.is_set)
        ctx.registrar(dl)
        r = dl.baixar_boletos_cliente(nome, page_existente=svc.page) or {}
        out["baixados"], out["encontrados"] = r.get("total_baixados", 0), r.get("total_encontrados", 0)
    except ProcessamentoCancelado:
        raise Parado()
    return out


def _encerrar(est: dict):
    if est.get("svc"):
        try:
            est["svc"].fechar_sessao()
        except Exception:
            pass


def baixar(ctx: Contexto, p: dict) -> dict:
    est, itens = {"auto_reemitir": bool(p.get("auto_reemitir"))}, []
    visivel = bool(p.get("visivel"))
    try:
        for nome in _nomes(p):
            ctx.checar()
            try:
                r = _garantir_boletos(ctx, est, nome, visivel, reemitir=bool(p.get("reemitir", True)))
                ok = r["baixados"] > 0 or r["encontrados"] > 0
                nota = f"{r['baixados']} boleto(s) baixado(s)" + (f"; vencido reemitido p/ {r['reemitido'][0]}" if r["reemitido"] else "")
                ctx.item(nome, "Boletos na pasta" if ok else "Nenhum boleto encontrado", "ok" if ok else "aviso", nota)
                itens.append({"nome": nome, "ok": ok, **r})
            except Falha as e:
                ctx.item(nome, "Falhou", "falhou", str(e))
                itens.append({"nome": nome, "ok": False, "erro": str(e)})
    finally:
        _encerrar(est)
    return {"itens": itens, "nomes": [i["nome"] for i in itens if i.get("ok")]}


def acordo(ctx: Contexto, p: dict) -> dict:
    """Sobe o acordo (conferido com o termo) e já baixa os boletos."""
    est, itens = {"auto_reemitir": bool(p.get("auto_reemitir"))}, []
    visivel = bool(p.get("visivel"))
    try:
        for nome in _nomes(p):
            ctx.checar()
            try:
                r = _garantir_boletos(ctx, est, nome, visivel, subir_acordo=True)
                ctx.item(nome, "Acordo e boletos prontos", "ok" if r["baixados"] else "aviso",
                         f"acordo {r['acordo']}; {r['baixados']} boleto(s) baixado(s)")
                itens.append({"nome": nome, "ok": r["baixados"] > 0, **r})
            except Falha as e:
                ctx.item(nome, "Falhou", "falhou", str(e))
                itens.append({"nome": nome, "ok": False, "erro": str(e)})
    finally:
        _encerrar(est)
    return {"itens": itens, "nomes": [i["nome"] for i in itens if i.get("ok")]}


def processar(ctx: Contexto, p: dict) -> dict:
    """Completo: pasta já tem tudo? senão sobe o acordo; reemite o vencido do mês; baixa. O e-mail vem em seguida
    (Conferir e enviar), com a lista que sobrou na mão."""
    est, itens = {"auto_reemitir": bool(p.get("auto_reemitir"))}, []
    visivel = bool(p.get("visivel"))
    try:
        for nome in _nomes(p):
            ctx.checar()
            try:
                ctx.item(nome, "Conferindo a pasta de boletos")
                svc = _servico_acordo(ctx, est)
                completo = bool(svc.verificar_boletos_completos(nome).get("completo"))
                r = _garantir_boletos(ctx, est, nome, visivel, subir_acordo=not completo)
                ctx.item(nome, "Processamento completo", "ok" if r["baixados"] else "aviso",
                         f"{'pasta já completa' if completo else 'acordo ' + str(r['acordo'])}; {r['baixados']} boleto(s) baixado(s)")
                itens.append({"nome": nome, "ok": r["baixados"] > 0, **r})
            except Falha as e:
                ctx.item(nome, "Falhou", "falhou", str(e))
                itens.append({"nome": nome, "ok": False, "erro": str(e)})
    finally:
        _encerrar(est)
    return {"itens": itens, "nomes": [i["nome"] for i in itens if i.get("ok")]}


# ── enviar o boleto do mês ──
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _emails_validos(lista) -> list:
    """O navegador não é confiável: refaz a limpeza e recusa e-mail inválido ou do próprio escritório."""
    out = []
    for e in lista or []:
        e = str(e).strip().lower()
        if not e:
            continue
        e, _ = E.corrigir_email(e)
        if E.e_do_escritorio(e) or not _EMAIL.match(e):
            raise Falha(f"e-mail inválido ou do próprio escritório: {e}")
        if e not in out:
            out.append(e)
    return out


def _pasta_do_plano(it: dict, nome: str):
    """A MESMA pasta que o plano mostrou (se existir e estiver no Dropbox dos acordos); senão, procura de novo."""
    from baixar_boletos.acordo_parser import AcordoParser
    p = AcordoParser()
    bases = [Path(b).resolve() for b in (p.dropbox_base_padrao, p.dropbox_base_juridico, p.dropbox_base_fechados) if b]
    if it.get("pasta"):
        pp = Path(it["pasta"])
        if pp.is_dir() and any(b == pp.resolve() or b in pp.resolve().parents for b in bases):
            return pp
    return E.localizar_pasta_boletos(nome)


def enviar_mes(ctx: Contexto, p: dict) -> dict:
    mes = mes_inicial_boletos()
    rot = E.rotulo_mes(mes)
    if p.get("mes_ref") and tuple(p["mes_ref"]) != mes:
        raise RuntimeError(f"O mês de referência mudou desde a conferência (era {p['mes_ref']}, agora {list(mes)}). "
                           "Confira de novo antes de enviar.")
    visivel = bool(p.get("visivel"))
    est = {"auto_reemitir": bool(p.get("auto_reemitir"))}
    email = E.EmailService(log_callback=ctx.log, cancelado=ctx.parar.is_set)
    fila_email = ThreadPoolExecutor(max_workers=1, thread_name_prefix="webmail")   # Playwright: um por thread
    saida = []
    try:
        for it in p["itens"]:
            ctx.checar()
            nome = " ".join(str(it.get("nome") or "").split())
            if not nome:
                ctx.log("Item sem nome ignorado.", "WARNING")
                continue
            try:
                emails = _emails_validos(it.get("emails"))
                if not emails:
                    raise Falha("sem e-mail")
                if E.mes_ja_enviado(nome, mes) and not it.get("reenviar"):
                    raise Falha(f"boleto de {rot} já foi enviado antes (marque \"reenviar\" no plano para repetir)")
                if it.get("baixar"):
                    _garantir_boletos(ctx, est, nome, visivel)
                pasta = _pasta_do_plano(it, nome)
                arqs = _boletos_do_mes(pasta, mes)
                if not arqs:
                    raise Falha(f"boleto de {rot} não está na pasta")
                if _vencido(arqs):
                    raise Falha("o boleto do mês está vencido e não foi reemitido")
                ctx.item(nome, "Enviando o e-mail")
                r = fila_email.submit(email.enviar_mes, nome, emails, arqs, mes, None, visivel).result()
                if r["status"] == "enviado":
                    ctx.item(nome, "E-mail enviado", "ok", f"{len(arqs)} boleto(s) para {', '.join(emails)}")
                    saida.append({"nome": nome, "estado": "enviado", "para": emails, "arquivos": len(arqs)})
                else:
                    raise Parado() if r["status"] == "parado" else Falha(r.get("msg", r["status"]))
            except Falha as e:
                ctx.item(nome, "Não enviado", "falhou", str(e))
                saida.append({"nome": nome, "estado": "falhou", "erro": str(e)})
            except Parado:
                raise
            except Exception as e:
                ctx.item(nome, "Erro", "falhou", str(e).splitlines()[0][:200] if str(e) else type(e).__name__)
                saida.append({"nome": nome, "estado": "falhou", "erro": str(e)[:300]})
                try:
                    fila_email.submit(email.descartar).result()
                except Exception:
                    pass
    finally:
        _encerrar(est)
        try:
            fila_email.submit(email.fechar_sessao).result(timeout=30)
        except Exception:
            pass
        fila_email.shutdown(wait=False)
    return {"mes": rot, "itens": saida, "enviados": sum(1 for s in saida if s["estado"] == "enviado")}


# ── demonstração (testes e treino; não toca em nada real) ──
def demo(ctx: Contexto, p: dict) -> dict:
    nomes = _nomes(p) or ["CLIENTE DE TESTE UM", "CLIENTE DE TESTE DOIS"]
    for n in nomes:
        ctx.item(n, "Aguardando", "espera")
    saida = []
    for n in nomes:
        ctx.checar()
        ctx.item(n, "Conferindo")
        ctx.log(f"conferindo {n}")
        time.sleep(float(p.get("pausa", 0.3)))
        if p.get("perguntar") and n == nomes[0]:
            r = ctx.perguntar("Continuar?", f"Posso seguir com {n}?", ["Sim", "Não"])
            if r != "Sim":
                ctx.item(n, "Pulado", "pulado", "você respondeu Não")
                saida.append({"nome": n, "estado": "pulado"})
                continue
        ctx.item(n, "Concluído", "ok", "tudo certo")
        saida.append({"nome": n, "estado": "ok"})
    return {"itens": saida}


TAREFAS = {"conferir_mes": conferir_mes, "enviar_mes": enviar_mes, "baixar": baixar,
           "acordo": acordo, "processar": processar, "demo": demo}

# O que a tela mostra. Campos: nomes (lista), e booleanos.
CATALOGO = [
    {"id": "conferir_mes", "titulo": "Boleto do mês: conferir e enviar", "go": False,
     "descricao": "Confere pasta, boleto do mês e e-mail de cada cliente (sem abrir o Global Office) e mostra o plano para você aprovar antes de enviar. Boleto vencido é reemitido (vencimento em 2 dias).",
     "campos": ["nomes"]},
    {"id": "processar", "titulo": "Processar clientes", "go": True,
     "descricao": "Para cada cliente: sobe o acordo se a pasta estiver incompleta (valores conferidos com o termo), reemite o boleto vencido do mês e baixa os boletos.",
     "campos": ["nomes", "auto_reemitir", "visivel"]},
    {"id": "baixar", "titulo": "Baixar boletos", "go": True,
     "descricao": "Baixa do Global Office os boletos do mês vigente em diante para a pasta do cliente no Dropbox.",
     "campos": ["nomes", "auto_reemitir", "visivel"]},
    {"id": "acordo", "titulo": "Subir acordo judicial", "go": True,
     "descricao": "Abre o devedor pelo CPF, confere os valores com o termo e grava o acordo; depois baixa os boletos. Sem valores na GEAP, cria os boletos avulsos (com sua confirmação).",
     "campos": ["nomes", "auto_reemitir", "visivel"]},
]
