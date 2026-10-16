# -*- coding: utf-8 -*-
"""processar_comprovantes.py - consolida os comprovantes de pagamento de todos os clientes do Dropbox na planilha
'Controle Financeiro - Repasse- Alvara.xlsx'.

1. Le os acordos da planilha de producao da Jaci (Dropbox) e da planilha do Eduardo (pasta do projeto).
2. Varre as pastas de clientes do Dropbox (AC COBRANCA e JURIDICO, inclusive pastas de cliente guardadas por engano
   dentro da pasta de outro cliente) e casa pasta, acordo e linha da planilha por nome aproximado, com regra rigida
   (primeiro e ultimo nome iguais) para nao juntar pessoas diferentes.
3. Le os comprovantes: texto do PDF/HTML; imagens e PDFs escaneados pelo OCR do Windows (4 processos em paralelo,
   escalas 2x e 3x e, se preciso, 1x e 1,5x), com cache dos textos ja lidos. So entra na soma o que esta confirmado
   (texto, codigo de barras valido, 2+ leituras iguais ou valor que repete o do acordo) e e plausivel (data entre
   06/2024 e hoje, valor ate R$ 250 mil e nunca acima do acordo inteiro); o resto vai para conferencia manual.
4. Grava uma COPIA da planilha: atualiza as linhas existentes, inclui como linha nova todo cliente do Dropbox que nao
   estava nela e reescreve o bloco SITUACAO DOS PAGAMENTOS | COMPROVANTES A CONFERIR | QUANTIDADE DE PARCELAS |
   VALOR ORIGINAL PARCELA | ENTRADA | 1 Parcela ... N Parcela (valor na celula; data, arquivo e forma de leitura no
   comentario), alem das abas Relatorio_Auditoria e Relatorio_Estatistico. As demais abas ficam como estao.
5. Alimenta conferencia_manual.xlsx com os comprovantes que pedem conferencia a olho; VALOR e DATA preenchidos la
   valem na execucao seguinte (o arquivo anterior fica salvo como "conferencia_manual (anterior).xlsx").

Rodar de novo e seguro: o bloco e reescrito do zero, sem duplicar colunas nem linhas.

Uso:
    python processar_comprovantes.py [planilha.xlsx] [saida.xlsx]
    python processar_comprovantes.py --teste
Cache dos textos e do OCR: %LOCALAPPDATA%\\processar_comprovantes\\cache.json (apague para reler tudo).
Primeira execucao completa: ~27 min (OCR de ~2.800 imagens); as seguintes, ~1 min.
"""
import base64
import datetime as dt
import difflib
import functools
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from copy import copy

import openpyxl
import pymupdf
from openpyxl.comments import Comment
from openpyxl.formula.translate import Translator
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

AQUI = os.path.dirname(os.path.abspath(__file__))
PLANILHA = r"C:\Users\Cob_Geap_05082026\Downloads\Controle Financeiro - Repasse- Alvara.xlsx"
SAIDA = os.path.join(AQUI, "Controle Financeiro - Repasse- Alvara (atualizada).xlsx")
MANUAL = os.path.join(AQUI, "conferencia_manual.xlsx")
JACI = r"C:\Users\Cob_Geap_05082026\Dropbox\COBRANÇA NEGOCIAÇÃO\JACI\ACORDOS GEAP\JACI-PLANILHA DE PRODUÇÃO DE ACORDOS GEAP.xlsx"
EDUARDO = os.path.join(AQUI, "PLANILHA EDUARDO - GEAP.xlsx")
CACHE = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "processar_comprovantes", "cache.json")
RAIZ = r"C:\Users\Cob_Geap_05082026\Dropbox\COBRANÇA NEGOCIAÇÃO\ADMINISTRATIVO- COBRANÇA"
PASTAS = ["ACOMPANHAMENTO DE ACORDOS AC COBRANÇA", "ACOMPANHAMENTO DE ACORDOS - JURÍDICO"]
EXTENSOES = {".pdf", ".png", ".jpg", ".jpeg", ".jfif", ".html", ".htm"}
IGNORAR = {"DE", "DA", "DO", "DAS", "DOS", "E", "PARCELADO", "PARCELADA", "AGREGADO", "AGREGADA"}
SUFIXOS = {"FILHO", "JUNIOR", "NETO", "SOBRINHO"}
MESES = {"JANEIRO": 1, "JAN": 1, "FEVEREIRO": 2, "FEV": 2, "MARCO": 3, "MAR": 3, "ABRIL": 4, "ABR": 4, "MAIO": 5, "MAI": 5,
         "JUNHO": 6, "JUN": 6, "JULHO": 7, "JUL": 7, "AGOSTO": 8, "AGO": 8, "SETEMBRO": 9, "SET": 9, "OUTUBRO": 10, "OUT": 10,
         "NOVEMBRO": 11, "NOV": 11, "DEZEMBRO": 12, "DEZ": 12}
MES_RE = "|".join(MESES)
# subpastas que nao sao pagamento do cliente: repasse/alvara sao saidas, boletos ainda nao foram pagos, "_files" = anexos de pagina salva
PASTA_IGNORADA = re.compile(r"ALVARA|REPASSE|BOLETO|FILES$")
NAO_COMPROVANTE = re.compile(r"REPASSE|REAPASSE|ALVARA|LEVANTAMENTO|CUSTAS|TERMO|SENTEN|SETEN|DEMONSTRATIVO|PROCURA|AUDIENCIA|CALCULO|PETICAO|"
                             r"ASSINATURA|CARTA|DECLARACAO|CERTIDAO")
AMARELO = PatternFill("solid", fgColor="FFF2CC")
AZUL = PatternFill("solid", fgColor="D9E1F2")
AUTOR = "processar_comprovantes"
MOEDA = '"R$" #,##0.00'
NUM = r"(\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})"
DATA = r"(\d{2})/(\d{2})/(\d{4}|\d{2})(?!\d)"
# limites de plausibilidade: o OCR troca digitos ("2026" vira "2020") e valida codigo de barras por acaso
VALOR_MAX = 250_000.0               # maior acordo da Jaci: R$ 146 mil
DATA_MIN = dt.date(2024, 6, 1)      # primeira entrada de acordo: 08/2024
UFS = set("AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split())
ROT_VALOR = [r"VALOR (?:COBRADO|PAGO|DO PAGAMENTO|TOTAL PAGO|CALCULADO|DEBITADO|TRANSFERIDO|DO DEPOSITO)", r"TOTAL DEPOSITADO",
             r"VALOR DO DOCUMENTO|VALOR NOMINAL DO BOLETO", r"VALOR"]
ROT_DATA = [r"DATA (?:DO|DE) (?:PAGAMENTO|DEPOSITO|DEBITO)", r"DATA E HORA D[OA] (?:LANCAMENTO|TRANSACAO)", r"PAGO EM",
            r"(?:PAGAMENTO|TRANSFERENCIA|DEPOSITO|PIX|OPERACAO) (?:REALIZAD[OA]|EFETUAD[OA]) EM", r"(?:REALIZAD[OA]|EFETUAD[OA]|DEBITAD[OA]) EM",
            r"DATA D[AE] (?:TRANSACAO|EFETIVACAO|OPERACAO)(?: / AGENDAMENTO)?", r"COMPROVANTE D[AE] (?:PAGAMENTO|TRANSFERENCIA|PIX|DEPOSITO)",
            r"DATA"]
# data precedida disto nao e a do pagamento (o BB imprime "Comprovante emitido em: <data de hoje>" em todo comprovante)
NAO_E_PAGAMENTO = re.compile(r"VENCIMENTO|VENCTO|VCTO|VALIDADE|EMISSAO|EMITIDO|GERADO|IMPRESS[AO]|COMPETENCIA|REFERENCIA|REFERENTE|AGENDAMENTO PARA")
# agendamento de pagamento: o comprovante ainda nao confirma o debito
AGENDADO = re.compile(r"AGENDAMENTO BB|COMPROVANTE DE AGENDAMENTO|PAGAMENTO AGENDADO|DEBITO AGENDADO|QUITACAO DEPENDERA DA VALIDACAO|COMPROVANTE DEFINITIVO SOMENTE")
ESCALAS = ((2, 3), (1, 1.5))  # o OCR do Windows acerta campos diferentes em cada escala; a 2a rodada so roda no que nao confirmou
PROCESSOS_OCR = max(1, min(4, os.cpu_count() or 1))
BLOCO = ["SITUAÇÃO DOS PAGAMENTOS", "COMPROVANTES A CONFERIR", "QUANTIDADE DE PARCELAS", "VALOR ORIGINAL PARCELA", "ENTRADA"]
SITUACOES = ["Quitado", "Em andamento", "Não fecha – verificar", "Pago a mais – verificar", "Sem valor de acordo – verificar",
             "Sem comprovantes", "Sem pasta no Dropbox"]
ORDEM_AUDITORIA = ["Divergência de valor", "Valor implausível", "Cliente da planilha sem pasta no Dropbox", "Acordo da Jaci sem pasta no Dropbox",
                   "Cliente sem acordo nas planilhas", "Possível duplicidade – conferir", "Valor diferente entre formatos", "Valor diferente do acordo",
                   "Comprovante de agendamento", "Valor lido por OCR sem confirmação",
                   "Comprovante ilegível", "Conferência manual com valor inválido", "Pagamento de várias parcelas", "Nome do arquivo com data diferente",
                   "Valor Acordo da planilha diferente da Jaci", "Data não identificada", "Parcela duplicada", "Conferido manualmente",
                   "Pasta dentro da pasta de outro cliente", "Cliente repetido na planilha", "Novo cliente adicionado"]

# OCR nativo do Windows 10/11 (Windows.Media.Ocr, idioma do perfil = pt-BR): dispensa instalar Tesseract.
# Cada linha da lista: "imagem<TAB>escala,escala"; a ampliacao e feita pelo proprio Windows (respeitando a rotacao EXIF).
PS_OCR = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$t) { $task = $asTask.MakeGenericMethod($t).Invoke($null, @($op)); $null = $task.Wait(-1); $task.Result }
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($engine -eq $null) { throw 'Nenhum idioma de OCR instalado no Windows' }
$inv = [Globalization.CultureInfo]::InvariantCulture
$saida = @{}
foreach ($linha in [IO.File]::ReadAllLines('__LISTA__')) {
  $p, $escalas = $linha -split "`t"
  try {
    $f = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($p)) ([Windows.Storage.StorageFile])
    $s = Await ($f.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $d = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($s)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $maior = [Math]::Max($d.PixelWidth, $d.PixelHeight)
    foreach ($e in $escalas.Split(',')) {
      $k = [Math]::Min([double]::Parse($e, $inv), 9900 / $maior)
      $t = New-Object Windows.Graphics.Imaging.BitmapTransform
      $t.ScaledWidth = [uint32][Math]::Max(1, [Math]::Round($d.PixelWidth * $k))
      $t.ScaledHeight = [uint32][Math]::Max(1, [Math]::Round($d.PixelHeight * $k))
      $t.InterpolationMode = [Windows.Graphics.Imaging.BitmapInterpolationMode]::Cubic
      $b = Await ($d.GetSoftwareBitmapAsync([Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8, [Windows.Graphics.Imaging.BitmapAlphaMode]::Premultiplied, $t, [Windows.Graphics.Imaging.ExifOrientationMode]::RespectExifOrientation, [Windows.Graphics.Imaging.ColorManagementMode]::DoNotColorManage)) ([Windows.Graphics.Imaging.SoftwareBitmap])
      $r = Await ($engine.RecognizeAsync($b)) ([Windows.Media.Ocr.OcrResult])
      $saida["$p|$e"] = (($r.Lines | ForEach-Object { $_.Text }) -join "`n")
      $b.Dispose()
    }
    $s.Dispose()
  } catch { $saida["$p|erro"] = $_.Exception.Message }
}
[IO.File]::WriteAllText('__SAIDA__', ($saida | ConvertTo-Json), [Text.Encoding]::UTF8)
"""
pymupdf.TOOLS.mupdf_display_errors(False)


def longo(p):
    """prefixo \\?\\ : varios caminhos do Dropbox passam de 260 caracteres"""
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + os.path.abspath(p)


def curto(p):
    return p[4:] if p.startswith("\\\\?\\") else p


# letras cirilicas identicas as latinas (aparecem em nomes da planilha da Jaci, ex.: 'SILVА МАСНADO'): sem isto o NFKD as descarta
HOMOGLIFOS = str.maketrans("АВЕКМНОРСТХаеорсхуіј", "ABEKMHOPCTXaeopcxyij")


def maiusc(s):
    return unicodedata.normalize("NFKD", str(s or "").translate(HOMOGLIFOS)).encode("ascii", "ignore").decode().upper()


def norm(s):
    return " ".join(re.sub(r"[^A-Z0-9 ]", " ", maiusc(s)).split())


def brl(v):
    return f"R$ {v:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def dbr(d):
    return f"{d:%d/%m/%Y}" if d else "sem data"


def numero(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


# ---------------------------------------------------------------- nomes: pastas x acordos x planilha
def _tokens(nome):
    return [t for t in norm(nome).split() if t not in IGNORAR]


def _canon(t):
    """grafias equivalentes: SOUZA/SOUSA, MELLO/MELO, THIAGO/TIAGO, YARA/IARA"""
    return re.sub(r"(.)\1+", r"\1", t.replace("PH", "F").replace("TH", "T").replace("Y", "I").replace("W", "V").replace("Z", "S"))


@functools.lru_cache(maxsize=None)
def _parecido(a, b):
    """1 = mesmo nome (ou grafia equivalente); inicial ('F.') vale 0,9 para nome com a mesma letra; senao a razao do difflib"""
    if a == b or _canon(a) == _canon(b):
        return 1.0
    if len(a) == 1 or len(b) == 1:
        return 0.9 if a[0] == b[0] else 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


@functools.lru_cache(maxsize=None)
def _partes(nome):
    """tokens do nome e, se for 'TITULAR- AGREGADO' ou 'TITULAR/AGREGADO', de cada parte (com 2+ nomes)"""
    out = []
    for p in [nome] + re.split(r"\s*[-/]\s*", str(nome)):
        t = tuple(_tokens(p))
        if len(t) >= 2 and t not in out:
            out.append(t)
    return tuple(out)


def _nota(x, y):
    ux, uy = [t for t in x if t not in SUFIXOS] or x, [t for t in y if t not in SUFIXOS] or y
    if _parecido(x[0], y[0]) < 0.8 or _parecido(ux[-1], uy[-1]) < 0.8:
        return 0.0
    menor, maior = sorted((x, y), key=len)
    melhores = [max(_parecido(t, u) for u in maior) for t in menor]
    if min(melhores) < 0.7:  # nome do menor que nao existe no maior (ex.: GISELE MARIA x GISELE FERNANDA): outra pessoa
        return 0.0
    return sum(melhores) / len(maior)


def casa(a, b):
    """0..1. Regra rigida: primeiro e ultimo nome iguais (ultimo sem FILHO/JUNIOR/NETO/SOBRINHO), todo nome do mais curto
    presente no mais longo (tolera erro de digitacao, inicial e grafia equivalente) e nota = soma das semelhancas / nomes
    do mais longo. Ignora acento, caixa, pontuacao e DE/DA/DOS."""
    return max((_nota(x, y) for x in _partes(a) for y in _partes(b)), default=0.0)


def melhor(nome, candidatos, nomes, minimo=0.75):
    """candidato de maior nota >= minimo; empate no topo entre candidatos diferentes = ambiguo (None)"""
    notas = sorted(((max((casa(nome, n) for n in nomes(c)), default=0.0), k) for k, c in enumerate(candidatos)), reverse=True)
    if not notas or notas[0][0] < minimo or (len(notas) > 1 and notas[1][0] == notas[0][0]):
        return None
    return candidatos[notas[0][1]]


def nome_da_pasta(nome):
    """nome do cliente a partir da pasta: tira 'PROTOCOLADO -', '- 2º ACORDO' e o que estiver entre parenteses"""
    n = re.sub(r"^\s*PROTOCOLADO\s*-\s*", "", nome, flags=re.I)
    n = re.sub(r"-?\s*\d+\s*[ºo°]?\s*ACORDO\s*$", "", n, flags=re.I)
    return re.sub(r"\([^)]*\)?", " ", n).strip(" -")


def carregar_acordos():
    """acordos da planilha de producao da Jaci (Dropbox) + os que so estiverem na do Eduardo. Mesmo CPF com valores
    diferentes = mais de um acordo da mesma pessoa (valores somados); linha repetida igual conta uma vez."""
    acordos, vistos = {}, set()
    for caminho in (JACI, EDUARDO):
        try:
            wb = openpyxl.load_workbook(longo(caminho), read_only=True, data_only=True)
        except Exception as e:
            print(f"  aviso: não consegui ler {os.path.basename(caminho)} ({e.__class__.__name__})")
            continue
        ws = next((w for w in wb.worksheets if norm(w.title) == "FECHADOS"), None)
        linhas = ws.iter_rows(values_only=True) if ws else iter(())
        cab = [norm(c) for c in next(linhas, ())]
        col = {k: next((i for i, c in enumerate(cab) if re.search(p, c)), None) for k, p in dict(
            nome=r"^BENEFICIARIO$", cpf=r"^CPF$", uf=r"^UF$", valor=r"^VALOR INTEGRAL DO ACORDO", cond=r"^CONDICOES DO ACORDO",
            entrada=r"^VALOR DA ENTRADA", qtd=r"^PARCELAS$", parcela=r"^VALOR DA PARCELA$", fim=r"^PAGAMENTO FINAL").items()}
        if col["nome"] is None:
            wb.close()
            continue
        fonte = "Jaci" if caminho == JACI else "Eduardo"
        for r in linhas:
            v = {k: (r[i] if i is not None and i < len(r) else None) for k, i in col.items()}
            nome = str(v["nome"] or "").strip().translate(HOMOGLIFOS)  # a planilha da Jaci tem nomes com letras cirilicas
            if not nome:
                continue
            cpf = re.sub(r"\D", "", str(v["cpf"] or "")).zfill(11)
            chave = cpf if cpf.strip("0") else norm(nome)
            a = acordos.get(chave)
            if a is not None and a["fonte"] != fonte:  # o do Eduardo e copia antiga da Jaci: so vale o que falta nela
                continue
            assinatura = (chave, numero(v["valor"]), str(v["qtd"]), numero(v["parcela"]))
            if assinatura in vistos:
                continue
            vistos.add(assinatura)
            if a is None:
                a = acordos[chave] = dict(nome=nome, cpf=cpf, uf=v["uf"], valor=0.0, sem_valor=False, parcelas=set(), entradas=set(),
                                          fim=None, avista=True, fonte=fonte, acordos=0)
            a["acordos"] += 1
            if numero(v["valor"]) is None:
                a["sem_valor"] = True
            else:
                a["valor"] += numero(v["valor"])
            for campo, conj in (("parcela", "parcelas"), ("entrada", "entradas")):
                if numero(v[campo]):
                    a[conj].add(round(numero(v[campo]), 2))
            fim = para_data(v["fim"])
            a["fim"] = max(filter(None, (a["fim"], fim)), default=None)
            q = re.match(r"\s*(\d+)", str(v["qtd"] or ""))
            a["avista"] = a["avista"] and ((q is not None and int(q.group(1)) == 1) or "VISTA" in norm(v["cond"]))
        wb.close()
    for a in acordos.values():
        if a["sem_valor"] and not a["valor"]:
            a["valor"] = None
        a["parcelas"] = a["parcelas"] - ({a["valor"]} if a["avista"] else set())
    return list(acordos.values())


def outro_cliente(sub, dono, acordos):
    """subpasta com nome de outro cliente da planilha da Jaci (e nao do dono da pasta)"""
    if PASTA_IGNORADA.search(norm(sub)) or casa(sub, dono) >= 0.75:
        return False
    return melhor(sub, acordos, lambda a: [a["nome"]]) is not None


def pastas_de_clientes(acordos):
    """pastas de cliente das duas areas, inclusive as guardadas por engano dentro da pasta de outro cliente
    (copia de 'ACOMPANHAMENTO DE ACORDOS ...' ou pasta com nome de outro cliente da planilha da Jaci)"""
    out = []
    for area in PASTAS:
        base = os.path.join(RAIZ, area)
        for nome in sorted(os.listdir(longo(base))):
            caminho = os.path.join(base, nome)
            if not os.path.isdir(longo(caminho)) or len(_tokens(nome_da_pasta(nome))) < 2 or norm(nome).startswith(("LIVRE", "TESTE")):
                continue  # "LIVRE 1" e "TESTE AUTOMACAO CLIENTE" nao sao clientes
            out.append(dict(nome=nome_da_pasta(nome), pasta=nome, caminho=caminho, area=area, dentro_de=None))
            for sub in sorted(os.listdir(longo(caminho))):
                cs = os.path.join(caminho, sub)
                if not os.path.isdir(longo(cs)):
                    continue
                if norm(sub).startswith("ACOMPANHAMENTO DE ACORDOS"):
                    out += [dict(nome=nome_da_pasta(n), pasta=n, caminho=os.path.join(cs, n), area=area, dentro_de=nome)
                            for n in sorted(os.listdir(longo(cs))) if os.path.isdir(longo(os.path.join(cs, n)))]
                elif outro_cliente(sub, nome, acordos):
                    out.append(dict(nome=nome_da_pasta(sub), pasta=sub, caminho=cs, area=area, dentro_de=nome))
    return out


def agrupar(pastas, acordos):
    """um cliente por pessoa: pastas que casam com o mesmo acordo (ou, sem acordo, com nome equivalente) viram um so"""
    clientes, por_acordo, soltas = [], {}, []
    for p in pastas:
        a = melhor(p["nome"], acordos, lambda x: [x["nome"]])
        if a is None:
            soltas.append(p)
            continue
        if id(a) not in por_acordo:
            por_acordo[id(a)] = dict(nome=a["nome"], acordo=a, pastas=[], linha=None)
            clientes.append(por_acordo[id(a)])
        por_acordo[id(a)]["pastas"].append(p)
    for p in soltas:
        c = next((c for c in clientes if c["acordo"] is None and casa(p["nome"], c["nome"]) >= 0.75), None)
        if c is None:
            c = dict(nome=p["nome"], acordo=None, pastas=[], linha=None)
            clientes.append(c)
        c["pastas"].append(p)
    return clientes


# ---------------------------------------------------------------- leitura dos comprovantes
def eh_comprovante(nome_arquivo):
    n = norm(os.path.splitext(nome_arquivo)[0])
    if NAO_COMPROVANTE.search(n) or n.startswith(("BOLETO", "GUIA")):
        return False
    return bool(re.search(r"\bCOM?P\b|\bCOMP|PAGAMENTO|\bPAG\b|\bPIX\b|DEP(OSITO)? ?JUD|\bPARCELA|\bENTRADA\b|QUITA", n))


def listar_comprovantes(pasta, acordos):
    out = []
    for dp, dns, fns in os.walk(longo(pasta["caminho"])):
        dns[:] = [d for d in dns if not (PASTA_IGNORADA.search(norm(d)) or norm(d).startswith("ACOMPANHAMENTO DE ACORDOS")
                                         or outro_cliente(d, pasta["pasta"], acordos))]
        for nome in sorted(fns):
            ext = os.path.splitext(nome)[1].lower().strip("' ")  # ha arquivos salvos como ".pdf'"
            if ext in EXTENSOES and eh_comprovante(nome):
                out.append(dict(caminho=os.path.join(dp, nome), arquivo=nome, ext=ext))
    return out


def info_do_nome(nome_arquivo):
    """tipo (ENTRADA / A VISTA / PARCELA) e mes de referencia pelo nome do arquivo ('COMP DE PAG- JAN-2026.pdf')"""
    n = norm(os.path.splitext(nome_arquivo)[0])
    n = re.sub(r"([A-Z])(\d)", r"\1 \2", n)
    n = re.sub(r"(\d)([A-Z])", r"\1 \2", n)
    tipo = "ENTRADA" if re.search(r"\bENTRADA\b", n) else "A VISTA" if re.search(r"\bA ?VISTA\b", n) else "PARCELA"
    ref = None
    m = re.search(r"\b(%s)\b\D{0,4}(20\d\d)?" % MES_RE, n)  # 1o mes citado ("REF DEZ 2025 - FOI PAGA ABRIL 2026")
    if m:
        ref = (int(m.group(2)) if m.group(2) else None, MESES[m.group(1)])
    meses = frozenset(MESES[x] for x in re.findall(r"\b(%s)\b" % MES_RE, n))  # todos os meses ("MAI - JUN - JUL 2026")
    return dict(tipo=tipo, ref=ref, meses=meses, quitou=bool(re.search(r"QUIT", n)))


def _data(d, m, a):
    """data plausivel de pagamento (entre DATA_MIN e hoje) ou None: o OCR erra o ano ('2020') e nao existe pagamento futuro"""
    a = int(a) + (2000 if len(a) == 2 else 0)
    try:
        x = dt.date(a, int(m), int(d))
    except ValueError:
        return None
    return x if DATA_MIN <= x <= dt.date.today() else None


def para_data(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    m = re.search(DATA, str(v or ""))
    return _data(*m.groups()) if m else None


def _num(s):
    """'1.234,56' / '661,43' / '278.02' (ponto decimal, de alguns PDFs) -> float"""
    return float(s.replace(".", "").replace(",", ".")) if "," in s else float(s)


def _mod10(s):
    soma = 0
    for i, c in enumerate(reversed(s)):
        n = int(c) * (2 - i % 2)
        soma += n // 10 + n % 10
    return (10 - soma % 10) % 10


def _mod11(s):
    dv = 11 - sum(int(c) * (2 + i % 8) for i, c in enumerate(reversed(s))) % 11
    return 1 if dv in (0, 10, 11) else dv


def codigo_de_barras(T):
    """(valor, digitos) do boleto. Linha digitavel (47 digitos, conferida pelos DVs dos 3 campos) termina com o valor
    em centavos; codigo de barras (44, DV geral na 5a posicao) traz o valor nas posicoes 10-19. Aceita a linha
    partida em pedacos, como o OCR costuma devolver. So vale com moeda 9 (real) na 4a posicao e valor ate VALOR_MAX:
    um DV sozinho passa por acaso (1 em 11 no codigo de barras) e ja gerou 'valores' de R$ 65 milhoes."""
    for m in re.finditer(r"\d[\d. ]*\d", T):
        partes = re.findall(r"\d+", m.group())
        for i in range(len(partes)):
            s = ""
            for p in partes[i:]:
                s += p
                if len(s) > 47:
                    break
                if s[0] == "8" or (len(s) > 3 and s[3] != "9"):  # 8 = boleto de convenio/arrecadacao (outro layout)
                    continue
                if len(s) == 47 and all(_mod10(s[a:b]) == int(s[b]) for a, b in ((0, 9), (10, 20), (21, 31))) and 0 < int(s[-10:]) <= VALOR_MAX * 100:
                    return int(s[-10:]) / 100, s
                if len(s) == 44 and _mod11(s[:4] + s[5:]) == int(s[4]) and 0 < int(s[9:19]) <= VALOR_MAX * 100:
                    return int(s[9:19]) / 100, s
    return None, None


def _mes(token):
    """numero do mes por extenso ou abreviado; tolera '0' no lugar de 'O' ('JUNH0') e ponto final"""
    return MESES.get(token.replace("0", "O").rstrip("."))


def _limpar(texto):
    """maiusculas sem acento, espacos simples e correcao das leituras tortas mais comuns do OCR"""
    T = " ".join(maiusc(texto).split())
    T = re.sub(r"(?<=\d) ,(?=\d{2}\b)", ",", T)                                # "661 ,43"
    T = re.sub(r"(?<=\d), ?(?=\d{3},\d{2}\b)", ".", T)                         # "1, 769,47" e "1,769,47"
    T = re.sub(r"\b(\d{2}) ?/ ?(\d{2}) ?/ ?(\d{4}|\d{2})\b", r"\1/\2/\3", T)  # "01 /06/2026"
    T = re.sub(r"\b(20\d\d)-(\d{2})-(\d{2})\b", r"\3/\2/\1", T)                # "2026-08-19" (ISO, de alguns apps)
    # mes por extenso -> DD/MM/AAAA: "03 AGO 2026", "19 DE SETEMBRO DE 2025", "22/OUT/2025", "23/JUNH0/2026"
    return re.sub(r"\b(\d{1,2}) ?(?:DE )?[/. -]? ?([A-Z0]{3,9}\.?) ?(?:DE )?[/. -]? ?(20\d\d)\b",
                  lambda m: f"{int(m[1]):02d}/{_mes(m[2]):02d}/{m[3]}" if _mes(m[2]) else m[0], T)


def data_em_colunas(T):
    """layout em colunas: rotulos em sequencia e os valores depois, na mesma ordem"""
    m = re.search(r"DATA D[OAE] (?:PAGAM|EFETIVA|DEPOSIT)\S*", T)
    if not m:
        return None
    k = len(re.findall(r"DATA D[EOA] \w+", T[max(0, m.start() - 80): m.start()]))
    datas = [x for x in (_data(*g) for g in re.findall(DATA, T[m.end():])) if x]
    return datas[k] if len(datas) > k else None


def data_do_pagamento(T):
    if AGENDADO.search(T):  # agendamento: vale a data do debito agendado (logo abaixo do valor, ou o vencimento)
        for padrao in (r"R\s?\$\s*" + NUM + r"\s*" + DATA, r"\bDATA DE VENCIMENTO\b[\s:]*" + DATA):
            m = re.search(padrao, T)
            if m and _data(*m.groups()[-3:]):
                return _data(*m.groups()[-3:])
    for rot in ROT_DATA:  # por rotulo
        m = re.search(r"\b(?:%s)\b[\s:]*%s" % (rot, DATA), T)
        if m and _data(*m.groups()[-3:]):
            return _data(*m.groups()[-3:])
    # data com hora ("17/04/2026 as 14:54:16", "16/05/2025 - 16:38:01", "12/02/2026 - 12H53") ou so com "as" quando o OCR perdeu a hora
    for m in re.finditer(DATA + r"\s*(?:AS\b|(?:AS\s*|-\s*|,\s*)?\d{2}[:H]\d{2})", T):
        if _data(*m.groups()) and not NAO_E_PAGAMENTO.search(T[max(0, m.start() - 30): m.start()]):
            return _data(*m.groups())
    if data_em_colunas(T):
        return data_em_colunas(T)
    # uma data so no comprovante, sem contar as de vencimento/validade/emissao
    datas = {_data(*m.groups()) for m in re.finditer(DATA, T) if _data(*m.groups()) and not NAO_E_PAGAMENTO.search(T[max(0, m.start() - 30): m.start()])}
    return datas.pop() if len(datas) == 1 else None


def extrair(texto):
    """valor pago, data do pagamento, valor do codigo de barras, codigo (linha digitavel / id Pix) e 'parcela x/y'.
    fraco=True: valor sem rotulo ou com a virgula perdida pelo OCR; nunca se confirma sozinho."""
    T = _limpar(texto)
    barras, cod = codigo_de_barras(T)
    valor, fraco = None, False
    if "AVISO DE CREDITO" in T and "VALOR DEPOSITADO" in T:  # BB: colunas de rotulos e depois os valores; o do deposito e o ultimo
        nums = re.findall(r"(?<![\d.,])(\d{1,3}(?:\.\d{3})+,\d{2}|\d+[.,]\d{2})(?!\d)", T)
        valor = _num(nums[-1]) if nums else None
    for rot in ROT_VALOR:  # ignora 0,00: em layout de colunas o rotulo pode cair ao lado do valor da multa/juros
        if valor:
            break
        valor = next((v for v in (_num(m[1]) for m in re.finditer(r"\b(?:%s)\b\s*(?:\(R\$\))?\s*:?\s*(?:R\s?\$)?\s*%s" % (rot, NUM), T)) if v >= 1), None)
    if valor is None:
        valor = barras
    if valor is None:  # com R$: "R$ 661,43" ou "R$379.53" (ponto decimal, de alguns apps)
        nums = [v for v in map(_num, re.findall(r"R\s?\$\s*" + NUM, T)) if v >= 1] or \
               [v for v in map(_num, re.findall(r"R\s?\$\s*(\d+\.\d{2})(?!\d)", T)) if v >= 1]
        valor = Counter(nums).most_common(1)[0][0] if nums else None
    if valor is None:  # palpites: "R$ 1.000" (sem centavos), "R$ 96430" (virgula perdida), numero solto (o que mais aparece)
        nums = [float(s.replace(".", "")) for s in re.findall(r"R\s?\$\s*(\d{1,3}(?:\.\d{3})+)(?![\d,.])", T)] or \
               [int(s) / 100 for s in re.findall(r"R\s?\$\s*(\d{4,6})(?![\d,.])", T)] or \
               [v for v in map(_num, re.findall(r"(?<![\d.,])" + NUM + r"(?![\d,])", T)) if v >= 1]
        valor, fraco = (Counter(nums).most_common(1)[0][0], True) if nums else (None, False)
    if valor is not None and valor > VALOR_MAX:
        valor, fraco = None, False
    pix = re.search(r"\bE[0-9A-Z]{31}\b", T)
    p = re.search(r"PARCELA\s*:?\s*(\d{1,2})(?:\s*(?:/|DE)\s*(\d{1,2}))?\b", T)
    return dict(valor=valor, fraco=fraco, data=data_do_pagamento(T), barras=barras, codigo=cod or (pix.group() if pix else None),
                agendado=bool(AGENDADO.search(T)), parcela_txt=(f"{int(p[1])}/{int(p[2])}" if p[2] else str(int(p[1]))) if p else None)


def combinar(leituras):
    """leituras do OCR nas varias escalas -> (valor, data, confirmado). Leitura direta do valor vale se 2+ escalas concordam
    ou se bate com o codigo de barras valido; so codigo de barras, idem; palpite fraco nunca confirma."""
    barras = Counter(e["barras"] for e in leituras if e["barras"])
    firmes = Counter(e["valor"] for e in leituras if e["valor"] and not e["fraco"])
    fracos = Counter(e["valor"] for e in leituras if e["valor"] and e["fraco"])
    datas = Counter(e["data"] for e in leituras if e["data"])
    data = datas.most_common(1)[0][0] if datas else None
    b = barras.most_common(1)[0][0] if barras else None
    if b is not None and (not firmes or b in firmes):
        return b, data, True
    if firmes:  # com codigo diferente: pode ser juros/desconto sobre o valor de face; so confirma se 2+ escalas leram o mesmo
        v, n = firmes.most_common(1)[0]
        return v, data, n >= 2
    if fracos:
        return fracos.most_common(1)[0][0], data, False
    return None, data, False


def texto_do_arquivo(dados, ext):
    if ext == ".pdf":
        with pymupdf.open(stream=dados, filetype="pdf") as doc:
            return "\n".join(pg.get_text() for pg in doc)
    if ext in (".html", ".htm"):
        return html.unescape(re.sub(r"<[^>]+>", " ", dados.decode("utf-8", "ignore")))
    return None  # imagem: so OCR


def imagem_para_ocr(dados, ext, destino):
    """imagem nativa para o OCR: o proprio arquivo, ou a 1a pagina do PDF na resolucao do scan"""
    if ext != ".pdf":
        with open(destino + ext, "wb") as f:
            f.write(dados)
        return destino + ext
    # shortcut: so a 1a pagina do PDF escaneado; ampliar se aparecer comprovante em pagina seguinte
    with pymupdf.open(stream=dados, filetype="pdf") as doc:
        pg = doc[0]
        imgs = pg.get_images(full=True)
        z = max(max(i[2], i[3]) for i in imgs) / max(pg.rect.width, pg.rect.height) if imgs else 200 / 72
        pg.get_pixmap(matrix=pymupdf.Matrix(min(5.0, max(1.0, z)), min(5.0, max(1.0, z)))).save(destino + ".png")
    return destino + ".png"


def ocr_windows(itens, tmp, rodada):
    """itens = [(imagem, [escalas])] -> {(imagem, escala): texto}, em PROCESSOS_OCR processos paralelos"""
    procs = []
    for k in range(PROCESSOS_OCR):
        lote = itens[k::PROCESSOS_OCR]
        if not lote:
            continue
        lista, saida = os.path.join(tmp, f"lista{rodada}_{k}.txt"), os.path.join(tmp, f"ocr{rodada}_{k}.json")
        with open(lista, "w", encoding="utf-8") as f:
            f.write("\n".join(f"{p}\t{','.join(map(str, esc))}" for p, esc in lote))
        script = PS_OCR.replace("__LISTA__", lista).replace("__SAIDA__", saida)
        with open(saida + ".err", "w") as err:  # em arquivo: pipe cheio trava processo paralelo
            procs.append((subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand",
                                            base64.b64encode(script.encode("utf-16-le")).decode()],
                                           stdout=subprocess.DEVNULL, stderr=err), saida))
    textos = {}
    for proc, saida in procs:
        proc.wait()
        if not os.path.exists(saida):
            with open(saida + ".err", encoding="utf-8", errors="replace") as f:
                raise RuntimeError(f.read().strip()[-300:])
        with open(saida, encoding="utf-8-sig") as f:
            for chave, texto in (json.load(f) or {}).items():
                img, esc = chave.rsplit("|", 1)
                textos[(img, esc)] = texto
    return textos


def ler_bytes(caminhos, n=8):
    """le os arquivos em paralelo (o Dropbox baixa na hora os que estao so na nuvem): (caminho, bytes | Exception)"""
    def ler(c):
        try:
            with open(c, "rb") as f:
                return c, f.read()
        except Exception as e:
            return c, e
    with ThreadPoolExecutor(n) as ex:
        for i in range(0, len(caminhos), 4 * n):
            yield from ex.map(ler, caminhos[i:i + 4 * n])


def avaliar(a):
    """registro do comprovante a partir do cache (texto do arquivo + OCR por escala)"""
    c = a["c"]
    r = dict(arquivo=a["arquivo"], caminho=curto(a["caminho"]), **info_do_nome(a["arquivo"]), hash=c.get("hash"), valor=None, fraco=False,
             data=None, barras=None, codigo=None, agendado=False, parcela_txt=None, conf=False, fonte=None, erro=c.get("erro") or a.get("erro"))
    if r["erro"] or not r["hash"]:
        r["erro"] = r["erro"] or "arquivo não pôde ser lido"
        return r
    if c.get("texto"):
        r.update(extrair(c["texto"]))
        if r["valor"] is not None:
            r.update(conf=not r["fraco"], fonte="texto")
    if (r["valor"] is None or r["data"] is None) and c.get("ocr"):
        leituras = [extrair(t) for t in c["ocr"].values()]
        valor, data, conf = combinar(leituras)
        if r["valor"] is None and valor is not None:
            r.update(valor=valor, conf=conf, fonte="ocr")
        r["data"] = r["data"] or data
        r["agendado"] = r["agendado"] or any(e["agendado"] for e in leituras)
    if r["valor"] is None and c.get("ocr_erro"):
        r["erro"] = f"imagem não abre ({c['ocr_erro']})"
    return r


def ler_comprovantes(arquivos, cache, tmp):
    """preenche o cache de cada arquivo (hash, texto, OCR por escala) lendo so o que mudou ou ainda falta"""
    for a in arquivos:
        st = os.stat(a["caminho"])
        a["c"] = cache.setdefault(f"{os.path.relpath(curto(a['caminho']), RAIZ)}|{st.st_size}|{st.st_mtime_ns}", {})

    def faltam(a, escalas):  # escalas de OCR que ainda faltam para o arquivo (nenhuma se o texto ja resolve)
        c = a["c"]
        if c.get("erro") or c.get("ocr_erro") or a["ext"] in (".html", ".htm") or "hash" not in c:
            return []
        r = avaliar(a)
        if r["valor"] is not None and r["data"] is not None and (r["conf"] or len(c.get("ocr", {})) >= 4):
            return []
        return [str(e) for e in escalas if str(e) not in c.get("ocr", {})]

    for rodada, escalas in enumerate(ESCALAS, 1):
        precisa = [a for a in arquivos if "hash" not in a["c"] or (faltam(a, escalas) and not a.get("img"))]
        t0 = time.time()
        for k, (a, (_, dados)) in enumerate(zip(precisa, ler_bytes([a["caminho"] for a in precisa])), 1):  # map mantem a ordem
            if isinstance(dados, Exception):
                a["erro"] = f"não consegui ler o arquivo ({dados.__class__.__name__})"
                continue
            c = a["c"]
            if "hash" not in c:
                c["hash"] = hashlib.sha1(dados).hexdigest()
                try:
                    c["texto"] = texto_do_arquivo(dados, a["ext"])
                except Exception as e:
                    c["erro"] = f"arquivo corrompido ou não abre ({e.__class__.__name__})"
            if faltam(a, escalas):
                try:
                    a["img"] = imagem_para_ocr(dados, a["ext"], os.path.join(tmp, f"i{id(a)}"))
                except Exception as e:
                    c["ocr_erro"] = e.__class__.__name__
            if k % 250 == 0:
                print(f"  rodada {rodada}: {k}/{len(precisa)} arquivos lidos ({time.time() - t0:.0f}s)", flush=True)
        itens = [(a["img"], f) for a in arquivos if a.get("img") for f in [faltam(a, escalas)] if f]
        if itens:
            print(f"  rodada {rodada} de OCR: {len(itens)} imagem(ns) em {PROCESSOS_OCR} processos...", flush=True)
            t0 = time.time()
            try:
                textos = ocr_windows(itens, tmp, rodada)
            except Exception as e:
                print("  OCR indisponível:", e)
                textos = {}
            por_img = {a["img"]: a for a in arquivos if a.get("img")}
            for (img, esc), texto in textos.items():
                if esc == "erro":
                    por_img[img]["c"]["ocr_erro"] = texto[:80]
                else:
                    por_img[img]["c"].setdefault("ocr", {})[esc] = texto
            print(f"  OCR da rodada {rodada}: {time.time() - t0:.0f}s", flush=True)
            salvar_cache(cache, arquivos)
    return [avaliar(a) for a in arquivos]


def carregar_cache():
    try:
        with open(CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def salvar_cache(cache, arquivos):
    usados = {id(a["c"]) for a in arquivos}
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE + ".tmp", "w", encoding="utf-8") as f:
        json.dump({k: v for k, v in cache.items() if id(v) in usados}, f, ensure_ascii=False)
    os.replace(CACHE + ".tmp", CACHE)


# ---------------------------------------------------------------- conferencia manual e consolidacao
CAB_MANUAL = ["CLIENTE", "ARQUIVO", "VALOR", "DATA DO PAGAMENTO", "OBSERVAÇÃO", "LEITURA AUTOMÁTICA", "CAMINHO"]


def carregar_manual():
    """linhas de conferencia_manual.xlsx; as que tem VALOR preenchido valem sobre a leitura automatica"""
    if not os.path.exists(MANUAL):
        return []
    for tentativa in range(8):  # o OneDrive trava o arquivo por alguns segundos depois de cada gravacao
        try:
            wb = openpyxl.load_workbook(MANUAL, read_only=True)
            break
        except PermissionError:
            time.sleep(3)
    else:  # sem ler o que o usuario conferiu, seguir adiante sobrescreveria o arquivo e perderia o trabalho dele
        raise SystemExit(f"Não consegui abrir {MANUAL} (aberto no Excel ou bloqueado pelo OneDrive). Feche-o e rode de novo; nada foi alterado.")
    linhas = [list(r[:7]) + [None] * (7 - len(r[:7])) for r in wb.worksheets[0].iter_rows(min_row=2, values_only=True) if r and r[0] and r[1]]
    wb.close()
    return linhas


def aplicar_manual(cliente, regs, manual, aud):
    for r in regs:
        m = next((x for x in manual if x[2] is not None and norm(x[1]) == norm(r["arquivo"]) and casa(x[0], cliente) >= 0.75), None)
        if not m:
            continue
        valor = numero(m[2])
        if valor is None:  # digitado como texto ("661,43" / "R$ 1.769,47")
            achado = re.search(NUM, str(m[2]))
            if not achado:
                aud(cliente, "Conferência manual com valor inválido", r["arquivo"], f"VALOR '{m[2]}' em conferencia_manual.xlsx")
                continue
            valor = _num(achado.group(1))
        data = para_data(m[3]) or r["data"]
        if r["valor"] is None or abs(r["valor"] - valor) >= 0.01 or not r["conf"] or r["data"] != data:
            lido = f"{brl(r['valor'])}, {dbr(r['data'])}" if r["valor"] else "nada legível"
            aud(cliente, "Conferido manualmente", r["arquivo"], f"leitura automática: {lido}; conferido: {brl(valor)}, {dbr(data)}")
        r.update(valor=valor, data=data, conf=True, fonte="manual", erro=None)


def alimentar_manual(manual, pendentes):
    """reescreve conferencia_manual.xlsx: mantem o que ja foi conferido e lista o que ainda pede conferencia a olho"""
    wb = openpyxl.Workbook()
    w = wb.active
    w.title = "Conferencia"
    w.append(CAB_MANUAL)
    for x in sorted((x for x in manual if x[2] is not None), key=lambda x: norm(x[0])):
        w.append(x)
    for cliente, r, motivo in sorted(pendentes, key=lambda p: (norm(p[0]), p[1]["arquivo"])):
        lido = f"{brl(r['valor'])}, {dbr(r['data'])}" if r["valor"] is not None else "nada legível"
        w.append([cliente, r["arquivo"], None, None, motivo, lido, r["caminho"]])  # caminho como texto: link de 300 caracteres o Excel recusa
    for c in w[1]:
        c.font, c.fill = Font(bold=True), AZUL
    for lin in range(2, w.max_row + 1):
        w.cell(lin, 3).number_format, w.cell(lin, 4).number_format = MOEDA, "dd/mm/yyyy"
    for col, larg in zip("ABCDEFG", (40, 42, 12, 16, 44, 28, 60)):
        w.column_dimensions[col].width = larg
    w.freeze_panes, w.auto_filter.ref = "A2", f"A1:G{w.max_row}"
    for tentativa in range(8):
        try:
            if os.path.exists(MANUAL):  # copia de seguranca do que o usuario conferiu
                shutil.copy2(MANUAL, os.path.splitext(MANUAL)[0] + " (anterior).xlsx")
            wb.save(MANUAL)
            return
        except PermissionError:
            time.sleep(3)
    print("  aviso: conferencia_manual.xlsx está aberto ou bloqueado; não atualizei a lista de pendentes")


def data_ordem(r):
    if r["data"]:
        return r["data"]
    if r["ref"] and r["ref"][0]:
        return dt.date(r["ref"][0], r["ref"][1], 1)
    return dt.date.max


def consolidar(cliente, regs, acordo, aud):
    """-> dict(entrada, parcelas, original, situacao, total, copias, pend). acordo: valor, parcelas, entradas, fim, avista.
    So entra na soma o que esta confirmado e e plausivel; o resto vai em pend = [(registro, motivo)] para conferencia a olho."""
    valor = acordo.get("valor")
    teto = valor * 1.25 + 1 if valor else VALOR_MAX  # nenhum comprovante passa do acordo inteiro
    pend, validos = [], []
    for r in regs:
        if r["erro"] or r["valor"] is None:
            pend.append((r, "ilegível: " + (r["erro"] or "sem valor no texto nem no OCR")))
            aud(cliente, "Comprovante ilegível", r["arquivo"], r["erro"] or "valor não encontrado no texto nem no OCR")
        elif r["valor"] > teto:
            pend.append((r, f"valor implausível ({brl(r['valor'])})"))
            aud(cliente, "Valor implausível", r["arquivo"], f"leu {brl(r['valor'])}, " + (f"mais que o acordo inteiro ({brl(valor)})" if valor else "acima de qualquer acordo") + "; não somado")
        else:
            validos.append(r)
    # mesmo comprovante salvo em dois formatos (PDF e JPEG com o mesmo nome): conta uma vez, pela leitura mais confiavel
    prioridade = lambda r: (not r["conf"], {"manual": 0, "texto": 1, "ocr": 2}.get(r["fonte"], 3))
    por_nome = defaultdict(list)
    for r in validos:
        por_nome[norm(os.path.splitext(r["arquivo"])[0])].append(r)
    for grupo in por_nome.values():
        if len(grupo) > 1 and len({os.path.splitext(r["arquivo"])[1].lower().strip("' ") for r in grupo}) > 1:
            grupo.sort(key=prioridade)
            for r in grupo[1:]:
                validos.remove(r)
                aud(cliente, "Parcela duplicada", r["arquivo"], f"mesmo comprovante de '{grupo[0]['arquivo']}' em outro formato; contado uma vez")
                if abs(r["valor"] - grupo[0]["valor"]) >= 0.01:
                    aud(cliente, "Valor diferente entre formatos", r["arquivo"], f"{brl(r['valor'])} aqui x {brl(grupo[0]['valor'])} em '{grupo[0]['arquivo']}'; usado o segundo")
    unicos, copias = [], 0
    for r in sorted(validos, key=lambda r: (data_ordem(r), r["arquivo"])):
        if any(u["hash"] == r["hash"] for u in unicos):  # o mesmo arquivo guardado mais de uma vez
            copias += 1
            continue
        dup = next((u for u in unicos if r["data"] and r["data"] == u["data"] and abs(r["valor"] - u["valor"]) < 0.005
                    and not (r["codigo"] and u["codigo"] and r["codigo"] != u["codigo"])), None)
        if dup:
            outro_mes = r["meses"] and dup["meses"] and not (r["meses"] & dup["meses"])  # nomes de meses diferentes: pode ser outro pagamento
            if not outro_mes or (r["codigo"] and r["codigo"] == dup["codigo"]):
                aud(cliente, "Parcela duplicada", r["arquivo"], f"mesmo valor e data de '{dup['arquivo']}' ({brl(r['valor'])}); contado uma vez")
                continue
            aud(cliente, "Possível duplicidade – conferir", r["arquivo"], f"mesmo valor e data de '{dup['arquivo']}' ({brl(r['valor'])}), mas o nome indica outro mês; contados os dois")
        if r["agendado"]:
            aud(cliente, "Comprovante de agendamento", r["arquivo"], f"{brl(r['valor'])} agendado para {dbr(r['data'])}: o comprovante não confirma o débito; conferir se foi pago")
        if r["data"] is None:
            aud(cliente, "Data não identificada", r["arquivo"], f"{brl(r['valor'])}; ordenado pelo mês do nome do arquivo")
        elif r["ref"] and r["ref"][0] and r["ref"][0] * 12 + r["ref"][1] - (r["data"].year * 12 + r["data"].month) > 1:
            aud(cliente, "Nome do arquivo com data diferente", r["arquivo"], f"nome indica {r['ref'][1]:02d}/{r['ref'][0]}; comprovante pago em {dbr(r['data'])}")
        unicos.append(r)
    # leitura sem confirmacao (OCR sem voto/codigo, palpite): vale se a soma fecha o acordo ou se repete um valor conhecido do acordo
    total = round(sum(r["valor"] for r in unicos), 2)
    conhecidos = {round(x, 2) for x in (*acordo.get("parcelas", ()), *acordo.get("entradas", ()), valor) if x} | \
                 {round(r["valor"], 2) for r in unicos if r["conf"] and r["tipo"] != "ENTRADA"}
    fecha = valor is not None and abs(total - valor) < 0.01
    for r in [r for r in unicos if not r["conf"]]:
        if fecha or round(r["valor"], 2) in conhecidos:
            r["conf"] = True
        else:
            pend.append((r, f"OCR sem confirmação ({brl(r['valor'])})"))
            aud(cliente, "Valor lido por OCR sem confirmação", r["arquivo"], f"{brl(r['valor'])}: conferir no arquivo (não somado)")
            unicos.remove(r)
    total = round(sum(r["valor"] for r in unicos), 2)
    bate = valor is not None and abs(total - valor) < 0.01
    entrada = next((r for r in unicos if r["tipo"] == "ENTRADA"), None)
    parcelas = [r for r in unicos if r is not entrada]
    original = Counter(round(r["valor"], 2) for r in parcelas).most_common(1)[0][0] if parcelas else None
    aconferir = f" (há {len(pend)} comprovante(s) a conferir)" if pend else ""
    if not unicos:
        sit = "Sem comprovantes"
    elif valor is None:
        sit = "Sem valor de acordo – verificar"
    elif bate:
        sit = "Quitado"
    elif total > valor:
        sit = "Pago a mais – verificar"
        aud(cliente, "Divergência de valor", "", f"comprovantes somam {brl(total)}; acordo {brl(valor)} (pago a mais: {brl(total - valor)})" + aconferir)
    elif any(r["quitou"] for r in unicos) or (acordo.get("fim") and acordo["fim"] + dt.timedelta(days=15) < dt.date.today()):
        sit = "Não fecha – verificar"
        aud(cliente, "Divergência de valor", "", f"comprovantes somam {brl(total)}; acordo {brl(valor)} (faltam "
            f"{brl(valor - total)}{', só centavos' if valor - total < 1 else ''}; acordo já deveria estar quitado)" + aconferir)
    else:
        sit = "Em andamento"
    # parcela a parcela so quando a soma nao fecha: e onde ajuda a achar a diferenca
    esperadas = sorted(acordo.get("parcelas") or ({original} if original else set()))
    if sit != "Quitado" and not acordo.get("avista") and esperadas:
        difere = defaultdict(list)  # (valor pago, parcela do acordo mais proxima) -> [(n da parcela, registro)]: uma linha por diferenca repetida
        for i, r in enumerate(parcelas, 1):
            if all(abs(r["valor"] - e) >= 0.01 for e in esperadas):
                n, e = next(((round(r["valor"] / e), e) for e in esperadas if round(r["valor"] / e) >= 2 and abs(r["valor"] - round(r["valor"] / e) * e) < 0.05), (0, 0))
                if n:
                    aud(cliente, "Pagamento de várias parcelas", r["arquivo"], f"{brl(r['valor'])} = {n} × {brl(e)} (conta como 1 comprovante em QUANTIDADE DE PARCELAS)")
                else:
                    difere[(round(r["valor"], 2), min(esperadas, key=lambda e: abs(r["valor"] - e)))].append((i, r))
        for (v, e), itens in difere.items():
            ordem = ", ".join(f"{i}ª" for i, _ in itens[:6]) + ("…" if len(itens) > 6 else "")
            aud(cliente, "Valor diferente do acordo", itens[0][1]["arquivo"] + (f" e mais {len(itens) - 1}" if len(itens) > 1 else ""),
                f"{len(itens)} parcela(s) ({ordem}) de {brl(v)} x parcela do acordo {brl(e)} ({'+' if v > e else '-'}{brl(abs(v - e))} por parcela)")
        if entrada and acordo.get("entradas") and all(abs(entrada["valor"] - e) >= 0.01 for e in acordo["entradas"]):
            aud(cliente, "Valor diferente do acordo", entrada["arquivo"], f"entrada {brl(entrada['valor'])} x entrada do acordo {' / '.join(map(brl, sorted(acordo['entradas'])))}")
    return dict(entrada=entrada, parcelas=parcelas, original=original, situacao=sit, total=total, copias=copias, pend=pend)


# ---------------------------------------------------------------- planilha
def coluna(ws, padrao):
    return next((c for c in range(1, ws.max_column + 1) if re.search(padrao, norm(ws.cell(1, c).value))), None)


def uf_valida(v):
    """UF de 2 letras ou '?': a planilha da Jaci tem '18' e 'РB' com P cirilico"""
    u = str(v or "").strip().translate(HOMOGLIFOS).upper()
    return u if u in UFS else "?"


def nota(r):
    linhas = [f"Pago em {dbr(r['data'])}" if r["data"] else "Data de pagamento não identificada"]
    if r["tipo"] == "ENTRADA":
        linhas.append("Entrada")
    if r["ref"]:  # so quando difere do mes do pagamento (ex.: parcela de dez/2025 paga em abr/2026)
        ano = r["ref"][0] or (r["data"].year if r["data"] else "")
        if not r["data"] or (ano, r["ref"][1]) != (r["data"].year, r["data"].month):
            linhas.append(f"Ref. no nome do arquivo: {r['ref'][1]:02d}/{ano}")
    if r["quitou"]:
        linhas.append("Quitação do acordo (nome do arquivo)")
    if r["parcela_txt"]:
        linhas.append(f"Parcela {r['parcela_txt']} (no comprovante)")
    if r["agendado"]:
        linhas.append("AGENDAMENTO: o comprovante não confirma o débito")
    linhas.append(f"Arquivo: {r['arquivo']}")
    if r["fonte"] == "ocr":
        linhas.append("Lido por OCR" + ("" if r["conf"] else ": conferir"))
    elif r["fonte"] == "manual":
        linhas.append("Conferido manualmente (conferencia_manual.xlsx)")
    return Comment("\n".join(linhas), AUTOR, width=320, height=120)


def escrever(ws, linha, col, valor, modelo, formato, comentario=None, amarelo=False):
    c = ws.cell(linha, col, valor)
    c.font, c.border, c.alignment, c.fill = copy(modelo.font), copy(modelo.border), copy(modelo.alignment), copy(modelo.fill)
    c.number_format = formato
    c.comment = comentario
    if amarelo:
        c.fill = AMARELO


def preparar_linha(ws, lin, modelo, ultima_col, estilo):
    """linha de cliente novo com as formulas da linha-modelo (ex.: Valor GEAP = Valor Acordo * 90%) onde estiverem vazias;
    estilo=True tambem copia a formatacao (linha criada no fim da planilha)"""
    for col in range(1, ultima_col + 1):
        m, c = ws.cell(modelo, col), ws.cell(lin, col)
        if estilo:
            c.font, c.border, c.alignment, c.fill, c.number_format = copy(m.font), copy(m.border), copy(m.alignment), copy(m.fill), m.number_format
        if isinstance(m.value, str) and m.value.startswith("=") and c.value is None:
            L = get_column_letter(col)
            c.value = Translator(m.value, origin=f"{L}{modelo}").translate_formula(f"{L}{lin}")
    if estilo:
        ws.row_dimensions[lin].height = ws.row_dimensions[modelo].height
    return lin


def relatorio_estatistico(wb, est):
    if "Relatorio_Estatistico" in wb.sheetnames:
        del wb["Relatorio_Estatistico"]
    w = wb.create_sheet("Relatorio_Estatistico")
    w.column_dimensions["A"].width = 58
    for col in "BCDEF":
        w.column_dimensions[col].width = 20
    for titulo, cab, linhas in est:
        w.append([titulo])
        w.cell(w.max_row, 1).font = Font(bold=True, size=12)
        w.append(cab)
        for c in w[w.max_row]:
            c.font, c.fill = Font(bold=True), AZUL
        for linha in linhas:
            w.append(list(linha))
            for c, h in zip(w[w.max_row][1:], cab[1:]):
                if isinstance(c.value, (int, float)):
                    c.number_format = MOEDA if "Valor" in h else "0" if isinstance(c.value, int) else "0.0"
        w.append([])


def main(planilha, saida):
    inicio = time.time()
    auditoria = []

    def aud(cliente, tipo, arquivo, detalhe):
        auditoria.append((cliente, tipo, arquivo, detalhe))

    wb = openpyxl.load_workbook(planilha)
    ws = next(w for w in wb.worksheets if coluna(w, r"^BENEFICIARI"))
    cn, ca, cu = coluna(ws, r"^BENEFICIARI"), coluna(ws, r"^VALOR ACORDO"), coluna(ws, r"^UF$")
    linhas = [(lin, str(ws.cell(lin, cn).value).strip()) for lin in range(2, ws.max_row + 1) if str(ws.cell(lin, cn).value or "").strip()]
    print("Lendo acordos (Jaci e Eduardo)...", flush=True)
    acordos = carregar_acordos()
    print(f"  {len(acordos)} beneficiários com acordo", flush=True)
    print("Varrendo as pastas de clientes do Dropbox...", flush=True)
    pastas = pastas_de_clientes(acordos)
    clientes = agrupar(pastas, acordos)
    print(f"  {len(pastas)} pastas -> {len(clientes)} clientes", flush=True)
    for p in pastas:
        if p["dentro_de"]:
            aud(p["nome"], "Pasta dentro da pasta de outro cliente", "", f"{p['area']}\\{p['dentro_de']}\\...\\{p['pasta']}")

    for lin, nome in linhas:  # linhas que ja estavam na planilha
        c = melhor(nome, clientes, lambda c: [c["nome"]] + [p["nome"] for p in c["pastas"]])
        if c is None:
            a = melhor(nome, acordos, lambda a: [a["nome"]])
            aud(nome, "Cliente da planilha sem pasta no Dropbox", "", "tem acordo na planilha da Jaci, mas não achei a pasta" if a else
                "não achei pasta nem acordo com nome parecido")
            continue
        if c["linha"] is not None:
            aud(nome, "Cliente repetido na planilha", "", f"mesma pasta da linha {c['linha']}")
            continue
        c["linha"] = lin
    com_pasta = {id(c["acordo"]) for c in clientes if c["acordo"]}
    for a in acordos:
        if id(a) not in com_pasta and not any(casa(a["nome"], nome) >= 0.75 for _, nome in linhas):
            aud(a["nome"], "Acordo da Jaci sem pasta no Dropbox", "", f"acordo de {brl(a['valor']) if a['valor'] else 'valor não informado'}")

    print("Lendo os comprovantes...", flush=True)
    arquivos = []
    for c in clientes:
        c["arquivos"] = [a for p in c["pastas"] for a in listar_comprovantes(p, acordos)]
        arquivos += c["arquivos"]
    print(f"  {len(arquivos)} comprovantes em {len(clientes)} clientes", flush=True)
    cache = carregar_cache()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = os.path.realpath(tmp)  # nome longo (sem "~1") para a API de OCR do Windows
        regs = ler_comprovantes(arquivos, cache, tmp)
    salvar_cache(cache, arquivos)
    for a, r in zip(arquivos, regs):
        a["reg"] = r

    # consolidacao por cliente
    manual = carregar_manual()
    pendentes, resultados = [], []
    for c in clientes:
        regs_c = [a["reg"] for a in c["arquivos"]]
        aplicar_manual(c["nome"], regs_c, manual, aud)
        acordo = dict(c["acordo"] or {})
        if c["linha"] is not None and numero(ws.cell(c["linha"], ca).value) is not None:
            v = numero(ws.cell(c["linha"], ca).value)
            if acordo.get("valor") is not None and abs(acordo["valor"] - v) >= 0.01:
                aud(c["nome"], "Valor Acordo da planilha diferente da Jaci", "", f"planilha {brl(v)} x Jaci {brl(acordo['valor'])}")
            acordo["valor"] = v
        c["res"] = consolidar(c["nome"], regs_c, acordo, aud)
        c["valor"] = acordo.get("valor")
        pendentes += [(c["nome"], r, motivo) for r, motivo in c["res"]["pend"]]
        if c["acordo"] is None:
            parecido = max(((difflib.SequenceMatcher(None, norm(c["nome"]), norm(a["nome"])).ratio(), a["nome"]) for a in acordos), default=(0, ""))
            aud(c["nome"], "Cliente sem acordo nas planilhas", "", "a pasta existe no Dropbox, mas não achei o acordo na planilha da Jaci/Eduardo" +
                (f"; nome mais parecido: {parecido[1]} ({parecido[0]:.0%}), pode ser a mesma pessoa" if parecido[0] >= 0.8 else ""))
        resultados.append(c)

    # planilha: linhas novas para clientes do Dropbox que nao estavam nela
    ultima_col = max(c for c in range(1, ws.max_column + 1) if ws.cell(1, c).value not in (None, ""))
    ini = min([c for c in (coluna(ws, r"^SITUACAO DOS PAGAMENTOS$"), coluna(ws, r"^QUANTIDADE DE PARCELAS$")) if c] or [ultima_col + 1])
    ultima_col = min(ultima_col, ini - 1)
    for row in ws.iter_rows(min_col=ini):  # reprocessamento: o bloco e reescrito do zero
        for cel in row:
            cel.value, cel.comment, cel.style = None, None, "Normal"
    ultima_nome = max([lin for lin, _ in linhas] or [1])
    livres = list(range(ultima_nome + 1, ws.max_row + 1))  # linhas ja formatadas e sem nome (preparadas para novos clientes)
    formulas = lambda r: sum(isinstance(ws.cell(r, col).value, str) and ws.cell(r, col).value.startswith("=") for col in range(1, ultima_col + 1))
    modelo = max(range(2, ws.max_row + 1), key=lambda r: (formulas(r), r))  # a ultima linha com o conjunto completo de formulas
    novos = sorted((c for c in clientes if c["linha"] is None), key=lambda c: norm(c["nome"]))
    for c in novos:
        lin = preparar_linha(ws, livres.pop(0), modelo, ultima_col, False) if livres else preparar_linha(ws, ws.max_row + 1, modelo, ultima_col, True)
        c["linha"] = lin
        a = c["acordo"] or {}
        if cu and uf_valida(a.get("uf")) != "?":
            ws.cell(lin, cu, uf_valida(a.get("uf")))
        ws.cell(lin, cn, c["nome"]).comment = Comment(
            "Incluído pelo processar_comprovantes em " + dt.date.today().strftime("%d/%m/%Y") + "\nPasta: " +
            " | ".join(f"{p['area']}\\{p['pasta']}" for p in c["pastas"]) + ("" if c["acordo"] else "\nSem acordo na planilha da Jaci/Eduardo"),
            AUTOR, width=360, height=100)
        if ca:
            ws.cell(lin, ca, a.get("valor"))
        aud(c["nome"], "Novo cliente adicionado", "", f"linha {lin}; " + (f"acordo {brl(a['valor'])} ({a['fonte']})" if a.get("valor") else "sem valor de acordo"))

    n_parc = max([len(c["res"]["parcelas"]) for c in clientes] or [0])
    cab = ws.cell(1, ini - 1)
    for k, t in enumerate(BLOCO + [f"{i} Parcela" for i in range(1, n_parc + 1)]):
        escrever(ws, 1, ini + k, t, cab, cab.number_format)
        ws.column_dimensions[get_column_letter(ini + k)].width = 24 if k == 0 else 15
    ws.cell(1, ini).comment = Comment("Soma dos comprovantes confirmados x Valor Acordo. 'Não fecha' = o acordo já deveria estar quitado "
                                      "(data final passou ou arquivo marcado QUITADO) e a soma não bate.", AUTOR, width=340, height=100)
    ws.cell(1, ini + 1).comment = Comment("Comprovantes ilegíveis, sem confirmação ou com valor implausível: ficaram fora da soma. "
                                          "Lista com o motivo em conferencia_manual.xlsx; preencha VALOR e DATA lá e rode de novo.", AUTOR, width=340, height=100)
    ws.cell(1, ini + 2).comment = Comment("Comprovantes de parcela confirmados no Dropbox (sem a entrada). À vista = 1. "
                                          "Um comprovante de várias parcelas conta como 1.", AUTOR, width=300, height=80)
    ws.cell(1, ini + 5).comment = Comment("Valor pago, em ordem cronológica. Data, arquivo e forma de leitura no comentário de cada célula.", AUTOR, width=300, height=70)
    for c in clientes:
        lin, res = c["linha"], c["res"]
        mod = ws.cell(lin, ini - 1)
        fmt = mod.number_format if "R$" in mod.number_format else MOEDA
        escrever(ws, lin, ini, res["situacao"], mod, "General")
        for col, v in ((ini + 1, len(res["pend"]) or None), (ini + 2, len(res["parcelas"]))):
            escrever(ws, lin, col, v, mod, "0")
            ws.cell(lin, col).alignment = Alignment(horizontal="center", vertical=mod.alignment.vertical)
        escrever(ws, lin, ini + 3, res["original"], mod, fmt)
        for col, r in [(ini + 4, res["entrada"])] + [(ini + 5 + k, r) for k, r in enumerate(res["parcelas"])]:
            if r:
                escrever(ws, lin, col, r["valor"], mod, fmt, nota(r), not r["conf"])
    for lin, nome in linhas:
        if not any(c["linha"] == lin for c in clientes):
            escrever(ws, lin, ini, "Sem pasta no Dropbox", ws.cell(lin, ini - 1), "General")

    # auditoria
    if "Relatorio_Auditoria" in wb.sheetnames:
        del wb["Relatorio_Auditoria"]
    wa = wb.create_sheet("Relatorio_Auditoria")
    wa.append(["CLIENTE", "OCORRÊNCIA", "ARQUIVO", "DETALHE"])
    ordem = {t: i for i, t in enumerate(ORDEM_AUDITORIA)}  # o que pede acao primeiro; os avisos informativos por ultimo
    for a in sorted(auditoria, key=lambda a: (ordem.get(a[1], len(ordem)), norm(a[0]), a[2])) or [("", "Nenhuma ocorrência", "", "")]:
        wa.append(list(a))
    for c in wa[1]:
        c.font, c.fill = Font(bold=True), AZUL
    for col, larg in zip("ABCD", (44, 38, 48, 110)):
        wa.column_dimensions[col].width = larg
    wa.freeze_panes, wa.auto_filter.ref = "A2", f"A1:D{wa.max_row}"

    # estatistica
    todos = [a["reg"] for a in arquivos]
    sit = defaultdict(lambda: [0, 0.0, 0.0])
    uf = defaultdict(lambda: [0, 0, 0.0, 0.0])
    for c in clientes:
        s = sit[c["res"]["situacao"]]
        s[0] += 1; s[1] += c["valor"] or 0.0; s[2] += c["res"]["total"]
        u = uf[uf_valida((c["acordo"] or {}).get("uf") or (ws.cell(c["linha"], cu).value if cu else ""))]
        u[0] += 1; u[1] += c["res"]["situacao"] == "Quitado"; u[2] += c["valor"] or 0.0; u[3] += c["res"]["total"]
    sem_pasta = [lin for lin, _ in linhas if not any(c["linha"] == lin for c in clientes)]
    sit["Sem pasta no Dropbox"][0] += len(sem_pasta)
    oc = Counter(a[1] for a in auditoria)
    fonte = Counter(r["fonte"] for r in todos)
    est = [
        ("Resumo do processamento", ["Indicador", "Resultado"], [
            ("Data do processamento", dt.datetime.now().strftime("%d/%m/%Y %H:%M")),
            ("Tempo de execução (minutos)", round((time.time() - inicio) / 60, 1)),
            ("Clientes que já estavam na planilha", len(linhas)),
            ("Pastas de cliente no Dropbox", len(pastas)),
            ("   guardadas dentro da pasta de outro cliente", sum(1 for p in pastas if p["dentro_de"])),
            ("Clientes distintos no Dropbox (pastas agrupadas por pessoa)", len(clientes)),
            ("Clientes atualizados (já estavam na planilha)", len(clientes) - len(novos)),
            ("Clientes novos incluídos na planilha", len(novos)),
            ("Clientes da planilha sem pasta no Dropbox", len(sem_pasta)),
            ("Clientes com acordo na planilha da Jaci/Eduardo", sum(1 for c in clientes if c["acordo"])),
            ("Clientes sem acordo encontrado", sum(1 for c in clientes if not c["acordo"])),
            ("Acordos da Jaci/Eduardo sem pasta no Dropbox", oc["Acordo da Jaci sem pasta no Dropbox"])]),
        ("Comprovantes", ["Indicador", "Quantidade"], [
            ("Arquivos de comprovante lidos", len(todos)),
            ("   lidos pelo texto do PDF/HTML", fonte["texto"]),
            ("   lidos por OCR e confirmados", sum(1 for r in todos if r["fonte"] == "ocr" and r["conf"])),
            ("   conferidos manualmente", fonte["manual"]),
            ("   a conferir em conferencia_manual.xlsx (fora da soma)", len(pendentes)),
            ("      ilegíveis", sum(1 for p in pendentes if p[2].startswith("ilegível"))),
            ("      lidos por OCR sem confirmação", sum(1 for p in pendentes if p[2].startswith("OCR sem"))),
            ("      com valor implausível", sum(1 for p in pendentes if p[2].startswith("valor implaus"))),
            ("Somados sem data identificada (ordenados pelo mês do nome)", oc["Data não identificada"]),
            ("Comprovantes de agendamento (não confirmam o débito; somados e avisados)", oc["Comprovante de agendamento"]),
            ("Cópias idênticas do mesmo arquivo (contadas uma vez)", sum(c["res"]["copias"] for c in clientes)),
            ("Parcelas duplicadas (mesmo valor e data)", oc["Parcela duplicada"]),
            ("Possíveis duplicidades (nomes de meses diferentes; contadas as duas)", oc["Possível duplicidade – conferir"])]),
        ("Situação dos pagamentos", ["Situação", "Clientes", "Valor dos acordos", "Valor pago (comprovantes)", "% pago"], [
            (s, sit[s][0], round(sit[s][1], 2), round(sit[s][2], 2), round(sit[s][2] / sit[s][1] * 100, 1) if sit[s][1] else None)
            for s in SITUACOES if sit[s][0]] + [("TOTAL", sum(v[0] for v in sit.values()), round(sum(v[1] for v in sit.values()), 2),
                                               round(sum(v[2] for v in sit.values()), 2), None)]),
        ("Ocorrências da auditoria", ["Ocorrência", "Quantidade"], sorted(oc.items(), key=lambda x: -x[1])),
        ("Por UF", ["UF", "Clientes", "Quitados", "Valor dos acordos", "Valor pago (comprovantes)"],
         [(k, v[0], v[1], round(v[2], 2), round(v[3], 2)) for k, v in sorted(uf.items())]),
    ]
    relatorio_estatistico(wb, est)
    try:
        wb.save(saida)
    except PermissionError:  # arquivo aberto no Excel
        saida = os.path.splitext(saida)[0] + " (novo).xlsx"
        wb.save(saida)
    alimentar_manual(manual, pendentes)

    print(f"\nPlanilha gravada em: {saida}  ({(time.time() - inicio) / 60:.1f} min)")
    for titulo, cab_, lins in est:
        print(f"\n== {titulo}")
        for linha in lins:
            print("  " + " | ".join(brl(x) if isinstance(x, float) and "Valor" in h else str(x) for x, h in zip(linha, cab_)))


def autoteste():
    assert casa("LUIZ ANDRE RIBEIRO ZARDO", "LUIZ ANDRE ZARDO") >= 0.75
    assert casa("MARCOS FERNANDES ALBURQUERQUE LIMA", "MARCOS FERNANDES ALBUQUERQUE LIMA") >= 0.95
    assert casa("MARCOS FERNANDES ALBURQUERQUE LIMA", "MARCOS LIMA DA SILVA") == 0
    assert casa("FRANCISCO RICARDO DA SILVA (parcelado)", "FRANCISCO CHAGAS DA SILVA ARAUJO") < 0.75
    assert casa("MARIA DE FATIMA SILVA", "MARIA DE FATIMA SILVA SANTOS") == 0  # ultimo nome diferente: pessoas diferentes
    assert casa("JOSE CARLOS SILVA FILHO", "JOSÉ CARLOS DA SILVA") >= 0.75
    assert casa("MARIANA BRAGA ALMEIDA", "MARIANA BRAGA LMEIDA") >= 0.95
    assert casa("DULCE MARIA DENEOR NUNES DINIZ- FRANCINETE MONTEIRO DA SILVA", "FRANCINETE MONTEIRO DA SILVA") == 1
    assert casa("DULCE MARIA DENEOR NUNES DINIZ- FRANCINETE MONTEIRO DA SILVA", "DULCE MARIA DENEOR NUNES DINIZ/FRANCINETE M") == 1
    assert casa("GISELE MARIA VIEIRA LIMA", "GISELE FERNANDA VIEIRA LIMA") == 0  # nome do meio diferente: outra pessoa
    assert casa("JOSE SILVA FILHO", "JOSE CARLOS SILVA") == 0                    # filho x pai
    assert casa("ELVOMARTON DAMIAI DE ARAUJO LIMA", "ELVOMARTON DAMIAO DE ARAUJO LIMA") >= 0.75
    assert casa("MARIA DO SOCORRO MELO DE SOUSA", "MARIA DO SOCORRO MELLO DE SOUZA") == 1
    assert casa("RODRIGO RABELLO DE FIGUEIREDO CARVALHO E FERREIRA PASSOS", "RODRIGO RABELLO DE F. C. E FERREIRA PASSOS") >= 0.75
    assert nome_da_pasta("LUZIA DE FATIMA GONÇALVES- MARIA VICTORIA (AGREGADA") == "LUZIA DE FATIMA GONÇALVES- MARIA VICTORIA"
    assert nome_da_pasta("PROTOCOLADO - AIRON DARIO DA SILVA") == "AIRON DARIO DA SILVA"
    assert nome_da_pasta("LINALDO ARAUJO- 2º ACORDO") == "LINALDO ARAUJO"
    assert info_do_nome("COMP DE PAG REF  DEZ 2025-FOI PAGA ABRIL 2026.pdf")["ref"] == (2025, 12)
    assert info_do_nome("COMP DE PAG- ENTRADA AGO-2025.pdf")["tipo"] == "ENTRADA"
    assert info_do_nome("COMP DE PAG À VISTA- SET-2025.jpeg")["tipo"] == "A VISTA"
    assert eh_comprovante("COMP DE PAG- JAN-2026.pdf") and not eh_comprovante("COMP DE PAG REPASSE - GEAP.pdf")
    for linha, valor in [("07090020267039366812718614070292811580000099000", 990.0), ("00190000090283658501432645154173812090001500000", 15000.0),
                         ("10499895264830010004600020772513112630000299223", 2992.23), ("07090.02026 70393.668168 79266.070634 7 13030000200689", 2006.89),
                         ("03790000949910915000500021268 5521 12280000066143", 661.43),     # partida pelo OCR
                         ("756914364201 190069201002648600161 14730000066143", 661.43)]:
        assert codigo_de_barras(linha)[0] == valor, linha
    assert codigo_de_barras("17090020267039366812718614070292811580000099000")[0] is None  # digito trocado: DV do 1o campo nao fecha
    e = extrair("DATA DE VENCIMENTO 30/07/2025 DATA DO PAGAMENTO 07/07/2025 VALOR DO DOCUMENTO 990,00 VALOR COBRADO 990,00")
    assert (e["valor"], e["data"]) == (990.0, dt.date(2025, 7, 7))
    e = extrair("Comprovante Boleto Valor Data R$ 2.992,23 11/11/25 13:11 Data de vencimento 12/11/2025")
    assert (e["valor"], e["data"]) == (2992.23, dt.date(2025, 11, 11))
    e = extrair("07090020267039356812729665070768911610001800000 NR. DOCUMENTO DATA DE VENCIMENTO DATA DO PAGAME~rro "  # scan com 1 digito lido errado
                "VALOR DO DOCUMENTO VALOf< COBRADO 780, 114.918 02/08/2025 04/07/2025 18.000,00 18.000J00")
    assert (e["valor"], e["data"], e["barras"]) == (18000.0, dt.date(2025, 7, 4), None)
    e = extrair("Multa (R$) Valor calculado (R$) 0,00 661,43 Data da Efetivação / Agendamento 08/04/2026 Valor nominal do boleto (R$) 661,43")
    assert (e["valor"], e["data"]) == (661.43, dt.date(2026, 4, 8))
    e = extrair("Data do Vencimento: Data de Efetivação / Agendamento: Valor Nominal do Boleto: 10/06/2026 01 /06/2026 661,43")
    assert (e["valor"], e["data"]) == (661.43, dt.date(2026, 6, 1))
    e = extrair("Data do de ósito Forma de recolhimento Valor do de ósito 123.456.789-09 30/09/2025 DINHEIRO 3262,00 Parcela: 1")
    assert (e["valor"], e["data"], e["parcela_txt"]) == (3262.0, dt.date(2025, 9, 30), "1")
    e = extrair("DATA DE PAGAMENTO: 22/OUT/2025 VALOR NOMINAL: 1, 769,47")
    assert (e["valor"], e["data"]) == (1769.47, dt.date(2025, 10, 22))
    assert extrair("sexta-feira, 19 de setembro de 2025, Valor R$ 7.500,00")["data"] == dt.date(2025, 9, 19)
    le = lambda v, d=None, b=None, f=False: dict(valor=v, data=d, barras=b, fraco=f)
    assert combinar([le(7300.0), le(7500.0, dt.date(2025, 9, 19)), le(7500.0)])[::2] == (7500.0, True)
    assert combinar([le(359.36), le(359.36, None, 20119006.92)])[::2] == (359.36, True)   # codigo discorda mas 2 escalas leram o mesmo valor
    assert combinar([le(359.36, None, 400.0)])[::2] == (359.36, False)                    # codigo discorda e so 1 leitura: a conferir
    assert combinar([le(964.3, None, None, True)])[::2] == (964.3, False)                 # palpite fraco nunca confirma
    assert combinar([le(None, None, 661.43), le(661.43)])[::2] == (661.43, True)
    # codigo de barras de 44 digitos construido com DV certo: so vale com moeda 9 e valor plausivel
    def barras44(banco, moeda, valor_centavos):
        s = f"{banco}{moeda}" + "1234" + f"{valor_centavos:010d}" + "1234567890123456789012345"
        return s[:4] + str(_mod11(s)) + s[4:]
    assert codigo_de_barras(barras44("756", "9", 66143))[0] == 661.43
    assert codigo_de_barras(barras44("756", "8", 66143))[0] is None                       # moeda errada: DV por acaso
    assert codigo_de_barras(barras44("756", "9", 2011900692))[0] is None                  # R$ 20 milhoes: impossivel
    # datas e valores dos formatos que antes ficavam sem data
    e = extrair("COMPROVANTE DE PAGAMENTO 03 AGO 2026 - VALOR PAGADOR Fulano DA BANCO SICOOB S.A. 10 AGO 2026 CODIGO DE BARRAS R$ 480,00")
    assert (e["valor"], e["data"]) == (480.0, dt.date(2026, 8, 3)), e
    assert extrair("PAGAMENTO REALIZADO EM 21 ABR 2026 AS 13:26:17 VALOR R$ 465,08")["data"] == dt.date(2026, 4, 21)
    e = extrair("Comprovante de Pix 23/junh0/2026 às 15:47:56. R$ 97152 De Flaviele")
    assert (e["valor"], e["fraco"], e["data"]) == (971.52, True, dt.date(2026, 6, 23)), e
    assert extrair("BOLETO DE COBRANCA 12/02/2026 - 12H53 DATA DO DEBITO: 12/02/2026 DATA DO VENCIMENTO: 13/02/2026 VALOR 1.000,00")["data"] == dt.date(2026, 2, 12)
    assert extrair("DATA DO PAGAMENTO 26/10/2020 VALOR 100,00")["data"] is None            # ano lido errado pelo OCR
    e = extrair("Data 2026-08-19 15:50:10 Concluída Pix Detalhes da transferência R$379.53 R$0")
    assert (e["valor"], e["fraco"], e["data"]) == (379.53, False, dt.date(2026, 8, 19)), e
    e = extrair("BANCO DO BRASIL S.A. AVISO DE CRÉDITO DATA DO DEPÓSITO PROCESSO VALOR DEPOSITADO R$ : : : 06/04/2026 1072190-61.2025.8.11.0041 GEAP 3800102844136 3 278.02")
    assert (e["valor"], e["data"]) == (278.02, dt.date(2026, 4, 6)), e
    assert extrair("Mercado Pago Comprovante de Pix 25/agosto/2026 às 9:15:21. R$ 1.000 Origem")["valor"] == 1000.0
    assert extrair("TOTAL R$ 20.119.006,92 DATA DO PAGAMENTO 05/05/2026")["valor"] is None   # acima de VALOR_MAX
    assert not eh_comprovante("COMPROVANTE ASSINATURAS.pdf") and not eh_comprovante("CARTA DE QUITAÇÃO.pdf")
    assert uf_valida("РB") == "PB" and uf_valida(18) == "?" and uf_valida(" sp ") == "SP"
    assert casa("SHEILA MARIA DA SILVА МАСНADO", "SHEILA MARIA DA SILVA MACHADO") == 1          # letras cirilicas no nome da planilha
    assert norm("GISELE FERNANDA VIEIRA LIMА") == "GISELE FERNANDA VIEIRA LIMA"
    # consolidacao
    e = extrair("COMPROVANTE BB R$ 394,96 09/06/2026 AS PAGAMENTO DE BOLETO BENEFICIARIO AC COBRANCA LTDA DATA DE VENCIMENTO: 10/06/2026 "
                "VALOR COBRADO: R$ 394,96 COMPROVANTE EMITIDO EM: 20/07/2026 AS 15:05:19 DOCUMENTO: 000000000060903")  # OCR sem a hora: nao pode cair na data de emissao
    assert (e["valor"], e["data"], e["agendado"]) == (394.96, dt.date(2026, 6, 9), False), e
    e = extrair("AGENDAMENTO BB PAGAMENTO DE BOLETO R$ 207,19 06/01/2026 DATA DE VENCIMENTO: 06/01/2026 VALOR DO DOCUMENTO: R$ 207,19 VALOR COBRADO: R$ 207,19 "
                "COMPROVANTE EMITIDO EM: 08/12/2025 AS 18:35:10 A QUITACAO DEPENDERA DA VALIDACAO DAS CONDICOES")
    assert (e["valor"], e["data"], e["agendado"]) == (207.19, dt.date(2026, 1, 6), True), e
    assert extrair("COMPROVANTE EMITIDO EM: 20/07/2026 AS 15:05:19 VALOR R$ 100,00")["data"] is None                  # so ha a data de emissao
    r = lambda v, d, arq, **k: dict(dict(arquivo=arq, valor=v, data=d, hash=arq, codigo=None, conf=True, erro=None, fonte="texto", fraco=False,
                                         tipo="PARCELA", ref=None, meses=frozenset(), quitou=False, parcela_txt=None, agendado=False), **k)
    aud = []
    res = consolidar("X", [r(100.0, dt.date(2025, 1, 5), "ENT", tipo="ENTRADA"), r(50.0, dt.date(2025, 2, 5), "P1"), r(50.0, dt.date(2025, 2, 5), "P1b"),
                           r(50.0, dt.date(2025, 3, 5), "P2", hash="P1"), r(100.0, dt.date(2025, 4, 5), "P3")],
                     dict(valor=250.0, parcelas={50.0}, entradas={100.0}, fim=dt.date(2025, 3, 10), avista=False), lambda *a: aud.append(a))
    assert (res["situacao"], len(res["parcelas"]), res["copias"], res["pend"]) == ("Quitado", 2, 1, []), res
    assert [a[1] for a in aud] == ["Parcela duplicada"], aud                              # quitado: sem aviso parcela a parcela
    aud = []
    res = consolidar("Y", [r(100.0, dt.date(2025, 1, 5), "ENT", tipo="ENTRADA"), r(100.0, dt.date(2025, 4, 5), "P3"), r(50.0, dt.date(2025, 5, 5), "P4"),
                           r(20119006.92, dt.date(2025, 6, 5), "BIZARRO"), r(15.59, dt.date(2025, 7, 5), "TINY", conf=False, fonte="ocr"),
                           r(50.0, dt.date(2025, 8, 5), "P5", conf=False, fonte="ocr"),
                           r(50.0, dt.date(2025, 9, 5), "A", meses=frozenset({9})), r(50.0, dt.date(2025, 9, 5), "B", meses=frozenset({10})),
                           r(None, None, "ILEG")],
                     dict(valor=900.0, parcelas={50.0}, entradas={100.0}, fim=dt.date(2099, 12, 31), avista=False), lambda *a: aud.append(a))
    assert [p[0]["arquivo"] for p in res["pend"]] == ["BIZARRO", "ILEG", "TINY"], res["pend"]
    assert len(res["parcelas"]) == 5 and res["total"] == 400.0 and res["situacao"] == "Em andamento"   # P5 repete uma parcela conhecida: confirmada
    assert sorted(a[1] for a in aud) == sorted(["Comprovante ilegível", "Valor implausível", "Valor lido por OCR sem confirmação", "Possível duplicidade – conferir",
                                                 "Pagamento de várias parcelas"]), aud
    # mesmo comprovante em PDF e JPEG com valores lidos diferentes: vale o PDF (texto) e a diferenca e avisada
    aud = []
    res = consolidar("Z", [r(84.27, None, "COMP ENTRADA AGO 2026.jpeg", tipo="ENTRADA", fonte="ocr"), r(1584.27, None, "COMP ENTRADA AGO 2026.pdf", tipo="ENTRADA"),
                           r(300.0, dt.date(2026, 9, 5), "P1.pdf"), r(300.0, dt.date(2026, 10, 5), "P2.pdf"), r(300.0, dt.date(2026, 11, 5), "P3.pdf")],
                     dict(valor=5000.0, parcelas={300.0}, entradas={1584.27}, fim=dt.date(2099, 1, 1), avista=False), lambda *a: aud.append(a))
    assert res["entrada"]["valor"] == 1584.27 and res["total"] == 2484.27 and len(res["parcelas"]) == 3, res
    assert sorted(a[1] for a in aud) == ["Data não identificada", "Parcela duplicada", "Valor diferente entre formatos"], aud
    # a mesma diferenca repetida em varias parcelas vira uma linha so
    aud = []
    consolidar("W", [r(298.82, dt.date(2026, m, 5), f"M{m}.pdf") for m in range(1, 6)] + [r(300.0, dt.date(2026, 6, 5), "M6.pdf")],
               dict(valor=5000.0, parcelas={298.08}, entradas=set(), fim=dt.date(2099, 1, 1), avista=False), lambda *a: aud.append(a))
    assert len(aud) == 2 and aud[0][3].startswith("5 parcela(s)") and "+R$ 0,74 por parcela" in aud[0][3], aud
    print("autoteste ok")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--teste" in sys.argv:
        autoteste()
    else:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        main(args[0] if args else PLANILHA, args[1] if len(args) > 1 else SAIDA)
