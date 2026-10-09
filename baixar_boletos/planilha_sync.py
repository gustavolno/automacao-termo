"""Sincronização da planilha oficial e detecção de atualizações.

1. Baixa a planilha direto do link do OneDrive (Excel Online > Arquivo > Criar uma Cópia >
   Baixar uma cópia). O link dá acesso de EDIÇÃO: este módulo só navega pelo menu de
   download e nunca clica nas células.
2. Escolhe a cópia mais recente entre a baixada e a do Dropbox.
3. Compara com a última leitura (snapshot) e informa clientes novos, removidos e alterados.
"""
import json
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional

from playwright.sync_api import sync_playwright

from baixar_boletos.acordo_parser import carregar_planilha_segura, normalizar_texto
from baixar_boletos.config import (
    PLANILHA_ONLINE_URL,
    PLANILHA_ONLINE_FILE,
    PLANILHA_DROPBOX_FILE,
    PLANILHA_SNAPSHOT_FILE,
    PLANILHA_HISTORICO_FILE,
)

Log = Callable[..., None]

HORAS_ALERTA_DESATUALIZADA = 24
MAX_DETALHES_LOG = 15


# ------------------------------------------------------------------ download
def _aba_fechados(wb):
    for nome in wb.sheetnames:
        if "FECHADO" in nome.upper():
            return wb[nome]
    return None


def baixar_planilha_online(log: Log) -> bool:
    """Baixa a planilha do link para PLANILHA_ONLINE_FILE. Só substitui a cópia local
    se o arquivo baixado for uma planilha válida (aba FECHADOS com BENEFICIÁRIO)."""
    log("Baixando a planilha oficial direto do OneDrive...")
    tmp = Path(tempfile.gettempdir()) / "planilha_online_download.xlsx"
    try:
        with sync_playwright() as pw:
            try:
                browser = pw.chromium.launch(channel="chrome", headless=True)
            except Exception:
                browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(accept_downloads=True, locale="pt-BR",
                                              viewport={"width": 1600, "height": 900})
                page = context.new_page()
                page.goto(PLANILHA_ONLINE_URL, timeout=90000)

                # O Excel Online roda dentro do iframe WacFrame_Excel_0
                frame = None
                for _ in range(60):
                    frame = next((f for f in page.frames if "WacFrame_Excel" in (f.name or "")), None)
                    if frame and frame.get_by_text("Arquivo", exact=True).first.is_visible():
                        break
                    page.wait_for_timeout(1000)
                if frame is None:
                    raise RuntimeError("Excel Online não carregou.")

                frame.get_by_text("Arquivo", exact=True).first.click()
                page.wait_for_timeout(2000)
                frame.get_by_text("Criar uma Cópia", exact=True).first.click()
                page.wait_for_timeout(2000)
                with page.expect_download(timeout=120000) as dl:
                    frame.get_by_text("Baixar uma cópia", exact=False).first.click()
                dl.value.save_as(str(tmp))
            finally:
                browser.close()

        wb = carregar_planilha_segura(tmp)
        ws = _aba_fechados(wb)
        cabecalhos = [normalizar_texto(str(ws.cell(1, c).value or "")) for c in range(1, 30)] if ws else []
        if not ws or "BENEFICIARIO" not in cabecalhos:
            raise RuntimeError("Arquivo baixado não tem a aba FECHADOS com a coluna BENEFICIÁRIO.")

        PLANILHA_ONLINE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp.replace(PLANILHA_ONLINE_FILE)
        log(f"Planilha online baixada ({round(PLANILHA_ONLINE_FILE.stat().st_size / 1024)} KB).", "SUCCESS")
        return True
    except Exception as e:
        log(f"Não foi possível baixar a planilha online: {e}", "WARNING")
        return False


# ------------------------------------------------------------------ escolha
def planilha_mais_recente() -> Optional[Path]:
    """Entre a cópia baixada e a do Dropbox, devolve a modificada por último."""
    candidatas = [p for p in (PLANILHA_ONLINE_FILE, PLANILHA_DROPBOX_FILE) if p.exists()]
    if not candidatas:
        return None
    return max(candidatas, key=lambda p: p.stat().st_mtime)


# ------------------------------------------------------------------ detecção de mudanças
def _texto_celula(v) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%d/%m/%Y")
    if isinstance(v, float):
        return f"{v:.2f}"
    return " ".join(str(v).split())


def gerar_snapshot(caminho: Path) -> Dict[str, Dict[str, str]]:
    """{chave_cliente: {coluna: valor}} da aba FECHADOS. Chave = nome normalizado + CPF."""
    ws = _aba_fechados(carregar_planilha_segura(caminho))
    if ws is None:
        return {}
    cabecalhos = {}
    for c in range(1, ws.max_column + 1):
        h = ws.cell(1, c).value
        if h:
            cabecalhos[c] = " ".join(str(h).split())
    col_nome = next((c for c, h in cabecalhos.items() if "BENEFICIARIO" in normalizar_texto(h)), 4)
    col_cpf = next((c for c, h in cabecalhos.items() if normalizar_texto(h) == "CPF"), 5)

    snap = {}
    for r in range(2, ws.max_row + 1):
        nome = ws.cell(r, col_nome).value
        if not nome or not str(nome).strip():
            continue
        cpf = re.sub(r"\D", "", str(ws.cell(r, col_cpf).value or ""))
        chave = f"{normalizar_texto(str(nome))}|{cpf}"
        snap[chave] = {h: _texto_celula(ws.cell(r, c).value) for c, h in cabecalhos.items()}
    return snap


def comparar_snapshots(antigo: Dict, novo: Dict) -> Dict:
    novos = [k for k in novo if k not in antigo]
    removidos = [k for k in antigo if k not in novo]
    alterados = []
    for k in novo:
        if k in antigo and novo[k] != antigo[k]:
            campos = [(col, antigo[k].get(col, ""), val)
                      for col, val in novo[k].items() if antigo[k].get(col, "") != val]
            alterados.append((k, campos))
    return {"novos": novos, "removidos": removidos, "alterados": alterados}


def _nome(chave: str) -> str:
    return chave.split("|")[0]


def _registrar_mudancas(log: Log, dif: Dict, origem: Path):
    n, r, a = len(dif["novos"]), len(dif["removidos"]), len(dif["alterados"])
    if not (n or r or a):
        log("Planilha sem alterações desde a última leitura.")
        return

    log(f"PLANILHA ATUALIZADA: {n} cliente(s) novo(s), {a} alterado(s), {r} removido(s).", "WARNING")
    linhas = [f"=== {datetime.now():%d/%m/%Y %H:%M} | origem: {origem}"]
    for k in dif["novos"]:
        linhas.append(f"NOVO: {_nome(k)}")
    for k in dif["removidos"]:
        linhas.append(f"REMOVIDO: {_nome(k)}")
    for k, campos in dif["alterados"]:
        mud = "; ".join(f"{col}: '{de}' -> '{para}'" for col, de, para in campos)
        linhas.append(f"ALTERADO: {_nome(k)} | {mud}")

    for linha in linhas[1:MAX_DETALHES_LOG + 1]:
        log(f"  {linha}")
    if len(linhas) - 1 > MAX_DETALHES_LOG:
        log(f"  ... e mais {len(linhas) - 1 - MAX_DETALHES_LOG}. Lista completa em: {PLANILHA_HISTORICO_FILE}")

    with open(PLANILHA_HISTORICO_FILE, "a", encoding="utf-8") as f:
        f.write("\n".join(linhas) + "\n")


def detectar_atualizacoes(caminho: Path, log: Log) -> Optional[Dict]:
    """Compara a planilha com a última leitura e grava a leitura atual como referência."""
    try:
        novo = gerar_snapshot(caminho)
    except Exception as e:
        log(f"Não foi possível analisar alterações da planilha: {e}", "WARNING")
        return None

    antigo = None
    if PLANILHA_SNAPSHOT_FILE.exists():
        try:
            antigo = json.loads(PLANILHA_SNAPSHOT_FILE.read_text(encoding="utf-8"))
        except Exception:
            antigo = None

    dif = None
    if antigo is None:
        log(f"Primeira leitura registrada ({len(novo)} clientes). Alterações serão detectadas a partir da próxima.")
    else:
        dif = comparar_snapshots(antigo, novo)
        _registrar_mudancas(log, dif, caminho)

    PLANILHA_SNAPSHOT_FILE.write_text(json.dumps(novo, ensure_ascii=False), encoding="utf-8")
    return dif


# ------------------------------------------------------------------ fluxo completo
def sincronizar_planilha(log: Log, baixar: bool = True) -> Optional[Path]:
    """Baixa a planilha online, escolhe a cópia mais recente, avisa se estiver velha e
    detecta alterações. Devolve o caminho a ser usado pelo robô."""
    if baixar:
        baixar_planilha_online(log)

    caminho = planilha_mais_recente()
    if caminho is None:
        log("Nenhuma cópia da planilha oficial encontrada (online nem Dropbox).", "ERROR")
        return None

    modificada = datetime.fromtimestamp(caminho.stat().st_mtime)
    horas = (time.time() - caminho.stat().st_mtime) / 3600
    origem = "online (OneDrive)" if caminho == PLANILHA_ONLINE_FILE else "Dropbox"
    log(f"Planilha em uso: {origem} | atualizada em {modificada:%d/%m/%Y %H:%M}")
    if horas > HORAS_ALERTA_DESATUALIZADA:
        log(f"ATENÇÃO: a planilha em uso tem {int(horas)}h. Pode não conter os acordos mais recentes.", "WARNING")

    detectar_atualizacoes(caminho, log)
    return caminho
