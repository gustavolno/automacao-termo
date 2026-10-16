"""Testa a Central ponta a ponta com um servidor de verdade (porta de teste, banco temporário,
tarefa 'demo': nada de Global Office nem e-mail)."""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PORTA = 8799
BASE = f"http://127.0.0.1:{PORTA}"


def chamar(metodo, caminho, corpo=None, cabecalhos=None):
    h = {"X-Central": "1", "Content-Type": "application/json", **(cabecalhos or {})}
    req = urllib.request.Request(BASE + caminho, method=metodo, headers=h,
                                 data=json.dumps(corpo).encode() if corpo is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("central")
    env = dict(os.environ, CENTRAL_PORT=str(PORTA), CENTRAL_DB=str(tmp / "t.db"), CENTRAL_DEMO="1",
               PYTHONIOENCODING="utf-8")
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "central_ac.main:app", "--port", str(PORTA), "--log-level", "warning"],
                         cwd=RAIZ, env=env)
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/api/ping", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        p.kill()
        pytest.fail("servidor não subiu")
    yield
    p.kill()


def esperar_job(job_id, estados, tempo=60):
    fim = time.time() + tempo
    while time.time() < fim:
        _, j = chamar("GET", f"/api/jobs/{job_id}")
        if j["estado"] in estados:
            return j
        time.sleep(0.3)
    pytest.fail(f"job não chegou a {estados}: {j['estado']}")


def test_protecao_contra_outros_sites(servidor):
    assert chamar("POST", "/api/jobs", {"tarefa": "demo"}, {"X-Central": "0"})[0] == 403
    req = urllib.request.Request(BASE + "/api/ping", headers={"Host": "site-mal.com"})
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req)
    assert e.value.code == 403


def test_carteiras_e_clientes(servidor):
    st, cart = chamar("GET", "/api/carteiras")
    assert st == 200
    ids = {c["id"]: c["clientes"] for c in cart}
    assert set(ids) == {"EMILIA", "YANCA", "LITIELLY", "GABRIELLE", "LUISA", "DISTRIBUIR", "TODAS"}
    assert ids["TODAS"] == sum(v for k, v in ids.items() if k != "TODAS") > 800
    st, r = chamar("GET", "/api/clientes?carteira=TODAS&status=INADIMPLENTE")
    assert r["total"] > 0 and all(c["status"] == "INADIMPLENTE" for c in r["itens"])
    atrasos = [c["dias_atraso"] for c in r["itens"]]
    assert atrasos == sorted(atrasos, reverse=True)      # mais atrasado primeiro
    st, busca = chamar("GET", "/api/clientes?q=" + urllib.parse.quote(r["itens"][0]["nome"].split()[0]))
    assert busca["total"] >= 1


def test_ficha_contatos_e_atribuicao(servidor):
    _, r = chamar("GET", "/api/clientes?carteira=DISTRIBUIR&limite=1")
    cid = r["itens"][0]["id"]
    st, f = chamar("GET", f"/api/clientes/{cid}")
    assert st == 200 and f["cliente"]["id"] == cid and "parcelas" in f
    st, c = chamar("POST", f"/api/clientes/{cid}/contatos", {"autor": "Teste", "canal": "WhatsApp", "texto": "prometeu pagar dia 20", "lembrar_em": "2020-01-01"})
    assert st == 200
    _, f = chamar("GET", f"/api/clientes/{cid}")
    assert f["contatos"][0]["texto"] == "prometeu pagar dia 20"
    _, lem = chamar("GET", "/api/clientes?status=LEMBRETES")
    assert cid in [x["id"] for x in lem["itens"]]
    chamar("PATCH", f"/api/contatos/{c['id']}", {"feito": True})
    _, lem = chamar("GET", "/api/clientes?status=LEMBRETES")
    assert cid not in [x["id"] for x in lem["itens"]]
    # redistribuição
    assert chamar("POST", "/api/atribuir", {"ids": [cid], "carteira": "LUISA", "por": "Teste"})[0] == 200
    _, f = chamar("GET", f"/api/clientes/{cid}")
    assert f["cliente"]["carteira"] == "LUISA"
    assert chamar("POST", "/api/atribuir", {"ids": [cid], "carteira": "INVENTADA"})[0] == 400


def test_robo_com_pergunta_e_historico(servidor):
    st, job = chamar("POST", "/api/jobs", {"tarefa": "demo", "params": {"nomes": ["ANA", "BIA"], "perguntar": True, "pausa": 0.1}})
    assert st == 200
    # com robô ativo, outro não inicia
    assert chamar("POST", "/api/jobs", {"tarefa": "demo", "params": {"nomes": ["X"]}})[0] == 409
    j = esperar_job(job["id"], ("aguardando",))
    assert j["pergunta"]["titulo"] == "Continuar?"
    assert chamar("POST", f"/api/jobs/{job['id']}/resposta", {"pergunta": "errada", "resposta": "Sim"})[0] == 409
    assert chamar("POST", f"/api/jobs/{job['id']}/resposta", {"pergunta": j["pergunta"]["id"], "resposta": "Sim"})[0] == 200
    j = esperar_job(job["id"], ("concluido",))
    assert [i["estado"] for i in j["resultado"]["itens"]] == ["ok", "ok"]
    tipos = [e["t"] for e in j["eventos_novos"]]
    assert "item" in tipos and "ask" in tipos and "resp" in tipos and tipos[-1] == "fim"
    # leitura incremental
    _, resto = chamar("GET", f"/api/jobs/{job['id']}?desde={len(j['eventos_novos']) - 1}")
    assert len(resto["eventos_novos"]) == 1
    _, hist = chamar("GET", "/api/jobs")
    assert hist[0]["id"] == job["id"] and hist[0]["estado"] == "concluido"


def test_parar_robo(servidor):
    _, job = chamar("POST", "/api/jobs", {"tarefa": "demo", "params": {"nomes": [f"C{i}" for i in range(30)], "pausa": 0.5}})
    time.sleep(1.5)
    chamar("POST", f"/api/jobs/{job['id']}/parar")
    j = esperar_job(job["id"], ("parado",), tempo=20)
    feitos = [e for e in j["eventos_novos"] if e["t"] == "item" and e["estado"] == "ok"]
    assert 0 < len(feitos) < 30


def test_validacoes(servidor):
    assert chamar("POST", "/api/jobs", {"tarefa": "inexistente"})[0] == 400
    assert chamar("POST", "/api/jobs", {"tarefa": "baixar", "params": {"nomes": ["  "]}})[0] == 400
    assert chamar("GET", "/api/clientes/nao-existe")[0] == 404
    assert chamar("GET", "/api/jobs/nao-existe")[0] == 404


def test_identificador_de_robo_nao_vira_caminho(servidor):
    for ruim in ("..%5C..%5Cnada", "..%2F..%2Fnada", "20260101-000000-zzzz"):
        assert chamar("GET", f"/api/jobs/{ruim}")[0] == 404


def test_telas_abrem_sem_erro_de_javascript(servidor):
    """Importa cada módulo e abre cada tela num navegador de verdade; qualquer erro de JS reprova."""
    from playwright.sync_api import sync_playwright
    erros = []
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page()
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
        pg.goto(BASE + "/")
        for modulo in ("api", "ui", "estado", "contatos", "carteira", "ficha", "robos"):
            r = pg.evaluate("async (m) => { try { await import('/js/' + m + '.js'); return 'ok'; } catch (e) { return String(e); } }", modulo)
            assert r == "ok", f"{modulo}.js: {r}"
        _, r = chamar("GET", "/api/clientes?limite=1")
        cid = r["itens"][0]["id"]
        for rota, espera in (("#/carteira/TODAS", ".kpi .valor"), (f"#/cliente/{cid}", ".dados-acordo"), ("#/robos", "#nomes")):
            pg.goto(BASE + "/" + rota)
            pg.wait_for_selector(espera, timeout=60000)
        b.close()
    assert not erros, erros
