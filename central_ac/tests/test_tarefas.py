"""Orquestração das tarefas com serviços simulados: nada de Global Office, webmail ou Dropbox reais."""
import pytest

from baixar_boletos import email_service as E
from central_ac.robots import protocolo, tarefas
from central_ac.robots.protocolo import Contexto, Falha, Parado


class EmailFalso:
    instancias = []

    def __init__(self, *a, **k):
        self.enviados, self.descartes, self.fechou = [], 0, False
        EmailFalso.instancias.append(self)

    def enviar_mes(self, nome, emails, arqs, mes, confirmar=None, visivel=False):
        if nome == "QUEBRA":
            raise RuntimeError("webmail caiu")
        self.enviados.append((nome, emails, len(arqs)))
        return {"status": "enviado", "arquivos": len(arqs)}

    def descartar(self):
        self.descartes += 1

    def fechar_sessao(self):
        self.fechou = True


@pytest.fixture
def mundo(monkeypatch):
    eventos = []
    monkeypatch.setattr(protocolo, "emitir", eventos.append)
    EmailFalso.instancias.clear()
    monkeypatch.setattr(E, "EmailService", EmailFalso)
    monkeypatch.setattr(E, "localizar_pasta_boletos", lambda nome, pasta="": "PASTA")
    monkeypatch.setattr(tarefas, "_boletos_do_mes", lambda pasta, mes: ["BOLETO - 2026-10 (OUT).pdf"])
    monkeypatch.setattr(tarefas, "_vencido", lambda arqs: False)
    monkeypatch.setattr(E, "mes_ja_enviado", lambda nome, mes: False)
    chamadas = []
    monkeypatch.setattr(tarefas, "_garantir_boletos", lambda ctx, est, nome, vis, **k: chamadas.append(nome) or {})
    monkeypatch.setattr(tarefas, "_encerrar", lambda est: chamadas.append("ENCERROU"))
    return {"eventos": eventos, "chamadas": chamadas}


def itens(eventos):
    return {e["nome"]: e for e in eventos if e["t"] == "item" and e["estado"] in ("ok", "falhou")}


def test_enviar_mes_falha_de_um_nao_derruba_o_lote(mundo):
    p = {"itens": [{"nome": "ANA", "emails": ["a@x.com"], "baixar": True},
                   {"nome": "SEM EMAIL", "emails": [], "baixar": False},
                   {"nome": "QUEBRA", "emails": ["q@x.com"], "baixar": False},
                   {"nome": "BIA", "emails": ["b@x.com", "b2@x.com"], "baixar": False}]}
    r = tarefas.enviar_mes(Contexto(), p)
    est = {i["nome"]: i["estado"] for i in r["itens"]}
    assert est == {"ANA": "enviado", "SEM EMAIL": "falhou", "QUEBRA": "falhou", "BIA": "enviado"}
    assert r["enviados"] == 2
    mail = EmailFalso.instancias[0]
    assert [e[0] for e in mail.enviados] == ["ANA", "BIA"] and mail.fechou and mail.descartes == 1
    assert mundo["chamadas"] == ["ANA", "ENCERROU"]        # só quem pediu 'baixar' foi ao Global Office


def test_enviar_mes_respeita_reenviar(mundo, monkeypatch):
    monkeypatch.setattr(E, "mes_ja_enviado", lambda nome, mes: True)
    p = {"itens": [{"nome": "ANA", "emails": ["a@x.com"]}, {"nome": "BIA", "emails": ["b@x.com"], "reenviar": True}]}
    r = tarefas.enviar_mes(Contexto(), p)
    assert {i["nome"]: i["estado"] for i in r["itens"]} == {"ANA": "falhou", "BIA": "enviado"}


def test_enviar_mes_nao_envia_boleto_vencido(mundo, monkeypatch):
    monkeypatch.setattr(tarefas, "_vencido", lambda arqs: True)
    r = tarefas.enviar_mes(Contexto(), {"itens": [{"nome": "ANA", "emails": ["a@x.com"]}]})
    assert r["itens"][0]["estado"] == "falhou" and "vencido" in r["itens"][0]["erro"]
    assert EmailFalso.instancias[0].enviados == []


def test_parar_interrompe_no_proximo_cliente(mundo):
    ctx = Contexto()
    real = EmailFalso.enviar_mes

    def enviar_e_parar(self, nome, *a, **k):
        ctx.cancelar_tudo()
        return real(self, nome, *a, **k)
    EmailFalso.enviar_mes = enviar_e_parar
    try:
        with pytest.raises(Parado):
            tarefas.enviar_mes(ctx, {"itens": [{"nome": "ANA", "emails": ["a@x.com"]}, {"nome": "BIA", "emails": ["b@x.com"]}]})
    finally:
        EmailFalso.enviar_mes = real
    assert [e[0] for e in EmailFalso.instancias[0].enviados] == ["ANA"]
    assert EmailFalso.instancias[0].fechou and "ENCERROU" in mundo["chamadas"]


def test_pergunta_resposta_e_parar():
    ctx = Contexto()
    import threading
    resp = {}
    t = threading.Thread(target=lambda: resp.update(r=ctx.perguntar("T", "x", ["Sim", "Não"])))
    t.start()
    for _ in range(50):
        if ctx._seq:
            break
        threading.Event().wait(0.05)
    pid = next(iter(range(1)))  # id é q<seq>-<ts>; descobre pelo estado interno
    ctx.receber({"t": "parar"})
    t.join(5)
    assert resp["r"] == "Não"          # parar responde a última opção (a mais segura)


def test_email_corrigido_e_do_escritorio():
    assert E.corrigir_email("x@gmail.cam") == ("x@gmail.com", "corrigido de x@gmail.cam")
    assert E.e_do_escritorio("jundico@aldnguescand1do.adv.br") and not E.e_do_escritorio("fulano@inss.gov.br")
    assert not E.e_do_escritorio("x@candido.adv.br")      # parecido demais não basta: precisa começar como o domínio do escritório
    assert E.rotulo_mes((2026, 3)) == "março/2026"


def test_conferir_mes_com_dados_reais_somente_leitura(monkeypatch):
    """Lê pastas e termos reais; não abre Global Office nem webmail."""
    eventos = []
    monkeypatch.setattr(protocolo, "emitir", eventos.append)
    r = tarefas.conferir_mes(Contexto(), {"nomes": ["ISABELA MORENO DOS SANTOS", "SHEILA MARIA DA SILVA MACHADO"]})
    por = {i["nome"]: i for i in r["itens"]}
    isa = por["ISABELA MORENO DOS SANTOS"]
    assert len(isa["emails"]) == 1 and "@" in isa["emails"][0] and isa["ja_enviado"] and isa["arquivos"]
    assert not isa["marcar"]                                  # já enviado: desmarcado por padrão
    assert r["mes"].endswith("/2026")


def test_servico_acordo_so_aprova_reemissao_autorizada(monkeypatch):
    """A confirmação de gravação: autorizada no lote vale só para 1 boleto vencido do mês; o resto pergunta."""
    perguntas = []
    monkeypatch.setattr(protocolo, "emitir", lambda e: None)
    ctx = Contexto()
    monkeypatch.setattr(ctx, "perguntar", lambda t, texto, op=("Sim", "Não"): perguntas.append(texto) or "Não gravar")
    reemissao = "Motivo: boleto de 10/10/2026 venceu sem ter sido enviado\n\nVencimento: 17/10/2026  |  Repetição: 0"
    avulsos = "Motivo: aviso da GEAP\nVencimento: 10/11/2026  |  Repetição: 20"
    svc = tarefas._servico_acordo(ctx, {"auto_reemitir": True})
    assert svc.confirmar_gravacao(reemissao) is True and not perguntas
    assert svc.confirmar_gravacao(avulsos) is False and len(perguntas) == 1       # 21 boletos: sempre pergunta
    svc2 = tarefas._servico_acordo(ctx, {"auto_reemitir": False})
    assert svc2.confirmar_gravacao(reemissao) is False and len(perguntas) == 2    # sem autorização: pergunta


def test_servicos_constroem_sem_abrir_navegador():
    from baixar_boletos.downloader_service import DownloaderService
    dl = DownloaderService(log_callback=lambda m: None, cancelado=lambda: False)
    assert dl.page is None and not dl.parado


def test_historico_ilegivel_nao_vira_historico_vazio(tmp_path, monkeypatch):
    """Arquivo que existe mas não lê: recusa (senão todo mundo pareceria não ter recebido e o envio repetiria)."""
    arq = tmp_path / "emails_enviados.json"
    monkeypatch.setattr(E, "EMAILS_ENVIADOS_FILE", arq)
    assert E.carregar_historico() == {}                        # ainda não existe: ok
    E.registrar_envio("ANA", ["a@x.com"], ["BOLETO - 2026-10 (OUT).pdf"])
    assert E.mes_ja_enviado("ANA", (2026, 10)) and not (tmp_path / "emails_enviados.tmp").exists()
    arq.write_text("{ truncado", encoding="utf-8")
    with pytest.raises(RuntimeError, match="não pôde ser lido"):
        E.carregar_historico()
    with pytest.raises(RuntimeError):
        E.mes_ja_enviado("ANA", (2026, 10))


def test_enviar_mes_exige_mes_de_referencia_igual_e_email_valido(mundo):
    with pytest.raises(RuntimeError, match="mês de referência mudou"):
        tarefas.enviar_mes(Contexto(), {"mes_ref": [2020, 1], "itens": [{"nome": "ANA", "emails": ["a@x.com"]}]})
    r = tarefas.enviar_mes(Contexto(), {"itens": [{"nome": "ANA", "emails": ["jundico@aldnguescand1do.adv.br"]},
                                                  {"nome": "BIA", "emails": ["sem-arroba"]}, {"nome": "  ", "emails": []}]})
    assert [i["estado"] for i in r["itens"]] == ["falhou", "falhou"]            # item sem nome é ignorado, os outros falham limpo
    assert EmailFalso.instancias[0].enviados == []
