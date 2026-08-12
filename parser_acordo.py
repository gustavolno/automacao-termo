import re
import logging
from dataclasses import dataclass, asdict, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

logger = logging.getLogger("parser_acordo")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


@dataclass
class DadosAcordo:
    nome: str = ""
    cpf: str = ""
    processo: str = ""
    matricula: str = ""
    telefone: str = ""
    email: str = ""
    endereco: str = ""
    cep: str = ""
    valor_original: str = ""
    valor_acordo: str = ""
    valor_entrada: str = ""
    vencimento_entrada: str = ""
    quantidade_parcelas: str = ""
    valor_parcela: str = ""
    inicio_parcelas: str = ""
    dia_parcela: str = ""
    competencias: str = ""
    avisos: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, str]:
        d = asdict(self)
        d.pop("avisos", None)
        return d


# ============================================================
# NORMALIZAÇÃO DE TEXTO
# ============================================================

def normalizar_texto(texto: str) -> str:
    if not texto:
        return ""
    res = texto.replace("\xa0", " ").replace("\u200b", " ").replace("\t", " ")
    res = res.replace("\r\n", "\n").replace("\r", "\n")
    res = re.sub(r"[ \t]+", " ", res)
    res = re.sub(r"\s+:", ":", res)
    return res.strip()


# ============================================================
# PARSER MONETÁRIO E DE DATA
# ============================================================

def parse_valor_brl(texto: str) -> Optional[Decimal]:
    if not texto:
        return None
    match = re.search(r"\b(\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2}|\d+\.\d{2})\b", texto)
    if match:
        t = match.group(1).replace(".", "").replace(",", ".")
    else:
        t = re.sub(r"[^\d.,]", "", texto.strip())
        if not t:
            return None
        if "," in t and "." in t:
            t = t.replace(".", "").replace(",", ".")
        elif "," in t:
            t = t.replace(",", ".")
        elif "." in t:
            parts = t.split(".")
            if len(parts) == 2 and len(parts[1]) == 2:
                pass
            else:
                t = t.replace(".", "")

    try:
        val = Decimal(t)
        return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def formatar_valor_brl(valor: Optional[Decimal]) -> str:
    if valor is None:
        return ""
    formatted = f"{valor:,.2f}"
    return formatted.replace(".", "_").replace(",", ".").replace("_", ",")


def calcular_valor_acordo(entrada: Optional[Decimal], qp: Optional[int], valor_parcela: Optional[Decimal]) -> Optional[Decimal]:
    ent = entrada or Decimal("0.00")
    if qp and qp > 0 and valor_parcela:
        total = ent + (Decimal(qp) * valor_parcela)
        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return None


def processar_competencias(texto: str) -> str:
    if not texto:
        return ""
    texto_clean = texto.strip(" :.,\n\r")
    m = re.search(r"\d{2}(?:/\d{2})?/\d{4}\s+(?:a|at[eé]|-)\s+\d{2}(?:/\d{2})?/\d{4}", texto_clean, re.IGNORECASE)
    if m:
        return m.group(0).strip()

    padrao_data = r"\b(\d{2}/\d{2}/\d{4}|\d{2}/\d{4})\b"
    encontradas = re.findall(padrao_data, texto_clean)
    if not encontradas:
        return texto_clean

    datas_obj = []
    for d in encontradas:
        try:
            if len(d) == 7:
                dt = datetime.strptime(d, "%m/%Y")
            else:
                dt = datetime.strptime(d, "%d/%m/%Y").replace(day=1)
            if dt not in datas_obj:
                datas_obj.append(dt)
        except Exception:
            pass

    datas_obj.sort()
    if not datas_obj:
        return texto_clean

    grupos = []
    grupo_atual = [datas_obj[0]]
    for i in range(1, len(datas_obj)):
        atual = datas_obj[i]
        anterior = datas_obj[i - 1]
        if atual.year == anterior.year and atual.month == anterior.month + 1:
            grupo_atual.append(atual)
        else:
            grupos.append(grupo_atual)
            grupo_atual = [atual]
    grupos.append(grupo_atual)

    partes = []
    for g in grupos:
        if len(g) == 1:
            partes.append(g[0].strftime("%m/%Y"))
        else:
            partes.append(f"{g[0].strftime('%m/%Y')} a {g[-1].strftime('%m/%Y')}")

    if len(partes) > 1:
        return (", ".join(partes[:-1]) + " e " + partes[-1]).strip()
    return partes[0].strip()


def processar_demonstrativo(texto: str) -> dict:
    """
    Processa o texto completo de um Demonstrativo de Valores (colado ou extraído de PDF/TXT).
    Extrai dados cadastrais e agrupa todas as datas de vencimento em sequências de competências.
    """
    res = {
        "nome": "",
        "cpf": "",
        "matricula": "",
        "valor_causa": "",
        "competencias": "",
        "grupos_detalhados": [],
        "total_meses": 0
    }
    if not texto:
        return res

    # 1. Dados cadastrais
    m_nome = re.search(r"(?i)Nome\s*:?\s*([^\n\r]+)", texto)
    if m_nome:
        res["nome"] = m_nome.group(1).strip()

    m_cpf = re.search(r"\b(\d{3}\.\d{3}\.\d{3}-\d{2}|\d{11})\b", texto)
    if m_cpf:
        d = re.sub(r"\D", "", m_cpf.group(1))
        if len(d) == 11:
            res["cpf"] = f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"

    m_mat = re.search(r"(?i)Matr[ií]cula(?:\s+do\s+Titular)?\s*:?\s*([A-Z0-9]+)", texto)
    if m_mat:
        res["matricula"] = m_mat.group(1).strip()

    m_vc = re.search(r"(?i)Valor\s+da\s+causa\s*:?\s*R?\$?\s*([\d\.,]+)", texto)
    if m_vc:
        vc_raw = m_vc.group(1).replace(".", "").replace(",", ".")
        try:
            val = Decimal(vc_raw).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            res["valor_causa"] = formatar_valor_brl(val)
        except Exception:
            pass

    # 2. Datas de vencimento da tabela (linhas que contêm data dd/mm/yyyy acompanhada de valor numérico ou tipo de receita)
    texto_tabela = texto
    m_param = re.search(r"(?i)Par[aâ]metros\s+do\s+c[aá]lculo", texto)
    if m_param:
        texto_tabela = texto[:m_param.start()]

    lines = texto_tabela.splitlines()
    datas_dict = {}

    for line in lines:
        if re.search(r"(?i)Demonstrativo\s+de\s+Valores|PROJUDI|JUNTADA", line):
            continue

        # Procura datas que estejam na mesma linha que valores ou receitas da tabela
        m_row = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", line)
        if m_row:
            # Exige ter valor numérico monetário ou palavras chave de receita na linha para ser considerada vencimento da dívida
            if not re.search(r"(?i)(?:contribui[cç][aã]o|parcelamento|vlr|\d+[\.,]\d{2})", line):
                continue
            dia, mes, ano = m_row.group(1), m_row.group(2), m_row.group(3)
            d_int, m_int, a_int = int(dia), int(mes), int(ano)
            if 1 <= d_int <= 31 and 1 <= m_int <= 12 and 2000 <= a_int <= 2099:
                key = (a_int, m_int)
                dt_str = f"{dia}/{mes}/{ano}"
                dt_obj = datetime(a_int, m_int, d_int)
                if key not in datas_dict:
                    datas_dict[key] = {"primeira": dt_str, "ultima": dt_str, "primeira_dt": dt_obj, "ultima_dt": dt_obj}
                else:
                    if dt_obj < datas_dict[key]["primeira_dt"]:
                        datas_dict[key]["primeira"] = dt_str
                        datas_dict[key]["primeira_dt"] = dt_obj
                    if dt_obj > datas_dict[key]["ultima_dt"]:
                        datas_dict[key]["ultima"] = dt_str
                        datas_dict[key]["ultima_dt"] = dt_obj

    if not datas_dict:
        return res

    keys_ordenadas = sorted(datas_dict.keys())
    res["total_meses"] = len(keys_ordenadas)

    grupos = []
    grupo_atual = [keys_ordenadas[0]]

    for i in range(1, len(keys_ordenadas)):
        curr_y, curr_m = keys_ordenadas[i]
        prev_y, prev_m = keys_ordenadas[i-1]
        
        # Inicia novo grupo se mudar de ano OU se houver lacuna de mês
        if curr_y == prev_y and curr_m == prev_m + 1:
            grupo_atual.append(keys_ordenadas[i])
        else:
            grupos.append(grupo_atual)
            grupo_atual = [keys_ordenadas[i]]
    grupos.append(grupo_atual)

    partes = []
    detalhes = []
    for g in grupos:
        key_ini = g[0]
        key_fim = g[-1]
        dt_ini_str = datas_dict[key_ini]["primeira"]
        dt_fim_str = datas_dict[key_fim]["ultima"]

        if len(g) == 1:
            partes.append(dt_ini_str)
            detalhes.append(f"Mês único ({key_ini[0]}): {dt_ini_str}")
        else:
            partes.append(f"{dt_ini_str} a {dt_fim_str}")
            detalhes.append(f"Ano {key_ini[0]}: {dt_ini_str} a {dt_fim_str} ({len(g)} meses)")

    if len(partes) > 1:
        res["competencias"] = (", ".join(partes[:-1]) + " e " + partes[-1]).strip()
    else:
        res["competencias"] = partes[0].strip()

    res["grupos_detalhados"] = detalhes
    return res


# ============================================================
# MAPA DE RÓTULOS E REGRAS DE FRONTEIRA
# ============================================================


ROTULOS_MAP = [
    ("nome", [
        r"cliente", r"benefici[aá]ri[oa]", r"nome\s+do\s+cliente", r"nome"
    ]),
    ("cpf", [
        r"cpf\s*/\s*cnpj", r"cpf/cnpj", r"cpf", r"cnpj"
    ]),
    ("processo", [
        r"processo\s+judicial", r"processo\s+n[oº°]\.?", r"processo\s+n", r"processo"
    ]),
    ("matricula", [
        r"matr[ií]cula\s+n[oº°]\.?", r"matr[ií]cula"
    ]),
    ("telefone", [
        r"telefone\s*/\s*whatsapp", r"telefone/whatsapp", r"telefones", r"telefone", r"celular", r"whatsapp"
    ]),
    ("email", [
        r"e-mails", r"emails", r"e-mail", r"email"
    ]),
    ("endereco", [
        r"endere[cç]o\s+com\s+cep", r"endere[cç]o\s+residencial", r"endere[cç]o\s+comercial", r"endere[cç]o\s+completo",
        r"endere[cç]o", r"resid[eê]ncia", r"mora\s+na", r"mora\s+no", r"residente\s+na", r"residente\s+no"
    ]),
    ("cep", [
        r"cep"
    ]),
    ("valor_original", [
        r"valor\s+total\s+da\s+d[ií]vida", r"valor\s+da\s+causa", r"valor\s+da\s+d[ií]vida",
        r"valor\s+original", r"valor\s+do\s+d[eé]bito", r"valor\s+devido",
        r"d[eé]bito\s+no\s+valor\s+de", r"a\s+d[ií]vida\s+[eé]\s+de", r"valor\s+atualizado\s+da\s+causa", r"totaliza"
    ]),
    ("valor_acordo", [
        r"valor\s+total\s+negociado", r"valor\s+total\s+acordado", r"valor\s+total\s+do\s+acordo",
        r"valor\s+fechado\s+com\s+o?\s*desconto", r"valor\s+fechado\s+com\s+desconto",
        r"valor\s+para\s+pagamento\s+parcelado\s+com\s+desconto",
        r"valor\s+total\s+para\s+negocia[cç][aã]o", r"valor\s+do\s+acordo", r"valor\s+negociado",
        r"valor\s+acordado", r"valor\s+final", r"valor\s+fechado",
        r"acordo\s+no\s+valor\s+de", r"ficou\s+negociada\s+por", r"resultando\s+no\s+valor\s+total\s+de"
    ]),
    ("condicao", [
        r"condi[cç][oõ]es\s+da\s+negocia[cç][aã]o", r"condi[cç][aã]o\s+da\s+negocia[cç][aã]o",
        r"condi[cç][aã]o\s+de\s+negocia[cç][aã]o", r"condi[cç][oõ]es", r"condi[cç][aã]o"
    ]),
    ("vencimento_entrada", [
        r"vencimento\s+da\s+entrada", r"primeiro\s+vencimento", r"a\s+entrada\s+vence", r"entrada\s+vence"
    ]),
    ("entrada", [
        r"entrada\s+de", r"entrada(?!.*\))", r"sinal\s+de", r"sinal"
    ]),
    ("valor_parcela", [
        r"valor\s+da\s+parcela", r"valor\s+de\s+cada\s+parcela", r"valor\s+por\s+parcela", r"valor\s+da\s+presta[cç][aã]o",
        r"\d{1,2}[aãºoª]?\s+parcela(?:\s*\([^)]+\))?"
    ]),
    ("quantidade_parcelas", [
        r"quantidade\s+de\s+parcelas", r"qtd\.?\s+de\s+parcelas", r"n[uú]mero\s+de\s+parcelas", r"qtd\s+parcelas", r"parcelas"
    ]),
    ("inicio_parcelas", [
        r"in[ií]cio\s+das\s+parcelas", r"iniciando\s+em", r"primeira\s+parcela"
    ]),
    ("dia_parcela", [
        r"vencimento\s+mensal\s+no\s+dia", r"vencimento\s+no\s+dia", r"parcelas\s+todo\s+dia",
        r"vencendo\s+a\s+cada\s+dia", r"todo\s+dia"
    ]),
    ("competencias", [
        r"compet[eê]ncias\s+negociadas", r"compet[eê]ncias", r"per[ií]odo\s+negociado", r"compete\s+de", r"compete"
    ]),
    ("cabeçalho_email", [
        r"data\s*/\s*hora\s+do\s+atendimento", r"tipo\s+do\s+atendimento", r"assunto\s+do\s+atendimento",
        r"forma\s+de\s+atendimento", r"detalhamento", r"atenciosamente", r"analista\s+de\s+testes"
    ]),
]


def localizar_rotulos(texto: str) -> List[Tuple[int, int, str]]:
    ocorrencias = []
    for campo, padroes in ROTULOS_MAP:
        for p in padroes:
            if campo == "quantidade_parcelas" and p == "parcelas":
                regex = r"(?i)\bparcelas\s*:"
            else:
                regex = r"(?i)\b" + p + r"\b\s*:?"
            for match in re.finditer(regex, texto):
                ocorrencias.append((match.start(), match.end(), campo))

    ocorrencias.sort(key=lambda x: x[0])

    filtradas = []
    for match in ocorrencias:
        if not filtradas:
            filtradas.append(match)
        else:
            prev_start, prev_end, _ = filtradas[-1]
            start, end, _ = match
            if start >= prev_end:
                filtradas.append(match)
            elif (end - start) > (prev_end - prev_start):
                filtradas[-1] = match
    return filtradas


def extrair_campos_rotulados(texto: str) -> Dict[str, str]:
    rotulos = localizar_rotulos(texto)
    extraidos = {}
    if not rotulos:
        return extraidos

    for i, (start, end, campo) in enumerate(rotulos):
        if campo == "cabeçalho_email":
            continue
        next_start = rotulos[i + 1][0] if i + 1 < len(rotulos) else len(texto)
        segmento = texto[end:next_start].strip(" :")
        if campo not in extraidos or not extraidos[campo]:
            extraidos[campo] = segmento

    return extraidos


def extrair_cpf(texto: str) -> str:
    m_mascara = re.search(r"\b(\d{3}[\.\s]?\d{3}[\.\s]?\d{3}[-\.\s]?\d{2})\b", texto)
    if m_mascara:
        d = re.sub(r"\D", "", m_mascara.group(1))
        if len(d) == 11:
            return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
        elif len(d) == 14:
            return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"

    match_digits = re.search(r"\b(\d{11}|\d{14})\b", texto)
    if match_digits:
        d = match_digits.group(1)
        if len(d) == 11:
            return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
        elif len(d) == 14:
            return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"

    return ""


def extrair_processo(texto: str) -> str:
    if re.search(r"(?i)\b(?:processo\s+n[aã]o\s+localizado|n[aã]o\s+localizado|sem\s+processo)\b", texto):
        return "Não localizado"

    match_cnj = re.search(r"\b(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\b", texto)
    if match_cnj:
        return match_cnj.group(1)

    match_raw = re.search(r"\b(\d{20})\b", texto)
    if match_raw:
        d = match_raw.group(1)
        return f"{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:]}"

    return ""


def extrair_telefones(texto: str, cpf_cliente: str = "") -> str:
    padrao_tel = r"\(?\d{2}\)?\s*9?\d{4,5}[-\s]?\d{3,4}"
    matches = re.findall(padrao_tel, texto)

    cpf_digs = re.sub(r"\D", "", cpf_cliente)
    unicos = []
    vistos = set()

    for m in matches:
        m_clean = m.strip(" ,.")
        digs = re.sub(r"\D", "", m_clean)
        if digs and digs == cpf_digs:
            continue
        if len(digs) in (10, 11) and digs not in vistos:
            vistos.add(digs)
            unicos.append(m_clean)

    if unicos:
        return " / ".join(unicos)
    return ""


def extrair_emails(texto: str) -> str:
    matches = re.findall(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b", texto)
    if matches:
        vistos = set()
        unicos = []
        for e in matches:
            e_clean = e.rstrip(".")
            if e_clean.lower() not in vistos:
                vistos.add(e_clean.lower())
                unicos.append(e_clean)
        return " / ".join(unicos)
    return ""


def extrair_cep(texto: str) -> str:
    # Tenta formato explícito com separador (XX.XXX-XXX ou XXXXX-XXX)
    match = re.search(r"\b(\d{2}\.?\d{3})[-](\d{3})\b", texto)
    if match:
        return f"{match.group(1).replace('.', '')}-{match.group(2)}"
    # Tenta formato sem separador (8 dígitos seguidos que parecem CEP)
    match2 = re.search(r"\b(\d{5})(\d{3})\b", texto)
    if match2:
        cep_candidate = f"{match2.group(1)}-{match2.group(2)}"
        # Verificar que não é um telefone (telefones têm 10-11 dígitos)
        contexto = texto[max(0, match2.start()-20):match2.end()+5]
        if not re.search(r"\d{10,11}", contexto):
            return cep_candidate
    return ""


def limpar_nome(nome_raw: str) -> str:
    if not nome_raw:
        return ""
    primeira_linha = nome_raw.split("\n")[0].strip()

    prefixos = [
        r"^(?:boa\s+tarde|bom\s+dia|boa\s+noite)\.?",
        r"^prezados?\.?",
        r"^solicito\s+minuta\s+de\s+acordo:?",
        r"^acordo\s+(?:fechado|realizado)\s+para",
        r"^acordo\s+fechado\s+com",
        r"^o\s+cliente",
        r"^cliente",
        r"^benefici[aá]ri[oa]"
    ]
    res = primeira_linha
    for p in prefixos:
        res = re.sub(p, "", res, flags=re.IGNORECASE).strip()

    res = re.split(r"(?i),?\s*(?:cpf|c\.p\.f\.?|cnpj|processo|telefone|e-?mail|mora\s+na|residente|valor|data|\.|$)", res)[0]
    res = re.sub(r"[^\w\s\.\-']", "", res).strip()
    res = re.sub(r"\s+", " ", res)
    return res


def extrair_parcelamento(texto: str) -> Tuple[str, str]:
    match = re.search(r"\b(\d{1,3})\s*(?:x|vezes|parcelas?)(?:\s*(?:de|no\s+valor\s+de)?\s*R?\$?\s*([\d\.,]*\d[\d\.,]*))?", texto, re.IGNORECASE)
    if match:
        qp = match.group(1).strip()
        vp_raw = match.group(2).strip() if match.group(2) else ""
        dec_vp = parse_valor_brl(vp_raw)
        return qp, formatar_valor_brl(dec_vp) if dec_vp else vp_raw
    return "", ""


def extrair_dia_parcela(texto: str) -> str:
    matches = re.findall(r"(?i)\b(?:todo\s+dia|dia|cada\s+dia)\s*(\d{1,2})\b", texto)
    for dia in matches:
        if dia in ["10", "25"]:
            return dia
    return ""


def extrair_vencimento_entrada(texto: str) -> str:
    match = re.search(r"\b(\d{2}[/\.-]\d{2}[/\.-]\d{4})\b", texto)
    if match:
        dt_str = match.group(1).replace(".", "/").replace("-", "/")
        return dt_str
    match_curto = re.search(r"\b(\d{2}[/\.-]\d{2})\b", texto)
    if match_curto:
        dt_str = match_curto.group(1).replace(".", "/").replace("-", "/")
        return f"{dt_str}/{datetime.now().year}"
    return ""


def extrair_inicio_parcelas(texto: str, vencimento_entrada: str = "") -> str:
    matches = re.findall(r"(?i)(?:iniciando\s+em|primeira\s+parcela\s+em|com\s+vencimento\s+em|vencimento\s+para\s+o\s+dia)\s*(\d{2}[/\.-]\d{2}[/\.-]\d{4})", texto)
    for m in matches:
        dt = m.replace(".", "/").replace("-", "/")
        if dt != vencimento_entrada:
            return dt
    if matches:
        return matches[0].replace(".", "/").replace("-", "/")
    return ""


# ============================================================
# FUNÇÃO PRINCIPAL DE INTERPRETAÇÃO
# ============================================================

def interpretar_mensagem(texto_bruto: str) -> Dict[str, str]:
    texto = normalizar_texto(texto_bruto)
    dados = DadosAcordo()
    rotulos_dict = extrair_campos_rotulados(texto)

    # NOME
    if "nome" in rotulos_dict and rotulos_dict["nome"]:
        dados.nome = limpar_nome(rotulos_dict["nome"])
    if not dados.nome:
        match_nome_nat = re.search(r"(?i)(?:acordo\s+fechado\s+para|acordo\s+realizado\s+com|o\s+cliente|cliente:?|benefici[aá]ri[oa]:?)\s+([A-ZÀ-Ÿa-zà-ÿ\s]+?)(?:,?\s*CPF|\.|\n|$)", texto)
        if match_nome_nat:
            dados.nome = limpar_nome(match_nome_nat.group(1))

    # CPF
    if "cpf" in rotulos_dict and rotulos_dict["cpf"]:
        dados.cpf = extrair_cpf(rotulos_dict["cpf"])
    if not dados.cpf:
        dados.cpf = extrair_cpf(texto)

    # PROCESSO
    if "processo" in rotulos_dict and rotulos_dict["processo"]:
        dados.processo = extrair_processo(rotulos_dict["processo"])
    if not dados.processo:
        dados.processo = extrair_processo(texto)

    # MATRÍCULA
    if "matricula" in rotulos_dict and rotulos_dict["matricula"]:
        m_mat = re.search(r"([A-Z0-9]+)", rotulos_dict["matricula"])
        if m_mat:
            dados.matricula = m_mat.group(1).strip()
    if not dados.matricula:
        m_mat_nat = re.search(r"(?i)\bmatr[ií]cula\s*:?\s*n?[oº°]?\s*([A-Z0-9]+)\b", texto)
        if m_mat_nat:
            dados.matricula = m_mat_nat.group(1).strip()

    # TELEFONE
    if "telefone" in rotulos_dict and rotulos_dict["telefone"]:
        dados.telefone = extrair_telefones(rotulos_dict["telefone"], dados.cpf)
    if not dados.telefone:
        dados.telefone = extrair_telefones(texto, dados.cpf)

    # EMAIL
    if "email" in rotulos_dict and rotulos_dict["email"]:
        dados.email = extrair_emails(rotulos_dict["email"])
    if not dados.email:
        dados.email = extrair_emails(texto)

    # CEP
    if "cep" in rotulos_dict and rotulos_dict["cep"]:
        dados.cep = extrair_cep(rotulos_dict["cep"])
    if not dados.cep:
        dados.cep = extrair_cep(texto)

    # ENDEREÇO
    if "endereco" in rotulos_dict and rotulos_dict["endereco"]:
        end_seg = rotulos_dict["endereco"]
        # Cortar antes de campos conhecidos
        end_seg = re.split(r"(?i)\s*(?:valor|d[ií]vida|d[eé]bito|compet[eê]ncias|condi[cç][aã]o|entrada|matr[ií]cula|$)", end_seg)[0]
        # Extrair CEP de dentro do endereço (ex: 'Rua X ... Cep 69309-160')
        cep_dentro = re.search(r"(?i)[,\.\s-]*\s*(?:cep|CEP)[:\s]*\s*(\d{2}\.?\d{3}[-]?\d{3})", end_seg)
        if cep_dentro:
            if not dados.cep:
                cep_raw = cep_dentro.group(1).replace(".", "")
                if "-" not in cep_raw:
                    cep_raw = cep_raw[:5] + "-" + cep_raw[5:]
                dados.cep = cep_raw
            end_seg = end_seg[:cep_dentro.start()]
        dados.endereco = end_seg.strip(" ,.-")

    if not dados.endereco:
        match_end_nat = re.search(r"(?i)\b(?:mora\s+na|mora\s+no|residente\s+na|residente\s+no|resid[eê]ncia:?|endere[cç]o:?)\s+([^.\n]+)", texto)
        if match_end_nat:
            end_candidate = match_end_nat.group(1).strip()
            end_candidate = re.split(r"(?i)\s*(?:a\s+d[ií]vida|valor|compet[eê]ncias|entrada)", end_candidate)[0]
            dados.endereco = end_candidate.strip(" ,.")

    # Se CEP veio do rótulo mas o valor contém endereço (ex: 'Rua X... Cep XXXXX-XXX'),
    # tentar recuperar o CEP correto do texto completo se ainda não encontrado
    if not dados.cep or len(re.sub(r'\D', '', dados.cep)) != 8:
        # Buscar CEP explícito no texto todo (formato com hífen)
        cep_match = re.search(r"(?i)(?:cep|CEP)[:\s]*\s*(\d{2}\.?\d{3}[-]\d{3})", texto)
        if cep_match:
            dados.cep = cep_match.group(1).replace('.', '')
        else:
            cep_match2 = re.search(r"\b(\d{5})[-](\d{3})\b", texto)
            if cep_match2:
                dados.cep = f"{cep_match2.group(1)}-{cep_match2.group(2)}"

    # VALOR ORIGINAL
    dec_original = None
    if "valor_original" in rotulos_dict and rotulos_dict["valor_original"]:
        dec_original = parse_valor_brl(rotulos_dict["valor_original"])
    if dec_original is None:
        m_vo = re.search(r"(?i)\b(?:valor\s+(?:da\s+causa|da\s+d[ií]vida|original|do\s+d[eé]bito|devido)|a\s+d[ií]vida\s+[eé]\s+de|d[eé]bito\s+no\s+valor\s+de)\s*:?\s*R?\$?\s*([\d\.,]+)", texto)
        if m_vo:
            dec_original = parse_valor_brl(m_vo.group(1))

    if dec_original is not None:
        dados.valor_original = formatar_valor_brl(dec_original)

    # VALOR DO ACORDO
    dec_acordo = None
    if "valor_acordo" in rotulos_dict and rotulos_dict["valor_acordo"]:
        dec_acordo = parse_valor_brl(rotulos_dict["valor_acordo"])
    if dec_acordo is None:
        m_va = re.search(r"(?i)\b(?:valor\s+(?:total\s+negociado|total\s+acordado|do\s+acordo|negociado|final|fechado\s+com\s+o?\s*desconto)|ficou\s+negociada\s+por|acordo\s+no\s+valor\s+de|resultando\s+no\s+valor\s+total\s+de)\s*:?\s*R?\$?\s*([\d\.,]+)", texto)
        if m_va:
            dec_acordo = parse_valor_brl(m_va.group(1))

    # ENTRADA E PARCELAS
    dec_entrada = None
    if "entrada" in rotulos_dict and rotulos_dict["entrada"]:
        dec_entrada = parse_valor_brl(rotulos_dict["entrada"])
    if dec_entrada is None:
        m_ent = re.search(r"(?i)\b(?:entrada\)?\s*(?:de|:)?|sinal\s*(?:de|:)?)\s*R?\$?\s*([\d\.,]+)", texto)
        if m_ent:
            dec_entrada = parse_valor_brl(m_ent.group(1))

    if dec_entrada is not None:
        dados.valor_entrada = formatar_valor_brl(dec_entrada)

    # Qtd. de Parcelas
    qp_str = ""
    if "quantidade_parcelas" in rotulos_dict and rotulos_dict["quantidade_parcelas"]:
        m_qp = re.search(r"\b(\d{1,3})\b", rotulos_dict["quantidade_parcelas"])
        if m_qp:
            qp_str = m_qp.group(1)

    # Valor da Parcela
    vp_str = ""
    if "valor_parcela" in rotulos_dict and rotulos_dict["valor_parcela"]:
        dec_vp = parse_valor_brl(rotulos_dict["valor_parcela"])
        if dec_vp is not None:
            vp_str = formatar_valor_brl(dec_vp)

    # Se não capturou via rótulos separados, tenta expressão combinada (ex: '20x de R$ 500,00')
    if not qp_str or not vp_str:
        comb_qp, comb_vp = extrair_parcelamento(texto)
        if not qp_str:
            qp_str = comb_qp
        if not vp_str:
            vp_str = comb_vp

    dados.quantidade_parcelas = qp_str
    dados.valor_parcela = vp_str

    # CÁLCULO AUTOMÁTICO DO VALOR DO ACORDO (Caso não fornecido expressamente)
    dec_vp = parse_valor_brl(vp_str)
    try:
        int_qp = int(qp_str) if qp_str else None
    except ValueError:
        int_qp = None

    if dec_acordo is None:
        dec_calc = calcular_valor_acordo(dec_entrada, int_qp, dec_vp)
        if dec_calc is not None:
            dec_acordo = dec_calc
            dados.avisos.append("Valor do acordo calculado automaticamente")
    else:
        dec_calc = calcular_valor_acordo(dec_entrada, int_qp, dec_vp)
        if dec_calc is not None and abs(dec_acordo - dec_calc) > Decimal("1.00"):
            dados.avisos.append("Valor total informado diverge da soma da entrada e das parcelas")

    if dec_acordo is not None:
        dados.valor_acordo = formatar_valor_brl(dec_acordo)

    # DATAS
    if "vencimento_entrada" in rotulos_dict and rotulos_dict["vencimento_entrada"]:
        dados.vencimento_entrada = extrair_vencimento_entrada(rotulos_dict["vencimento_entrada"])
    if not dados.vencimento_entrada:
        m_ve = re.search(r"(?i)\b(?:vencimento\s+(?:da\s+entrada|em)|entrada(?:.{0,30}?)para(?:\s+o\s+dia)?|primeiro\s+vencimento:?)\s*(\d{2}[/\.-]\d{2}(?:[/\.-]\d{4})?)", texto)
        if m_ve:
            dt = m_ve.group(1).replace(".", "/").replace("-", "/")
            if len(dt) == 5:
                dt = f"{dt}/{datetime.now().year}"
            dados.vencimento_entrada = dt

    if "dia_parcela" in rotulos_dict and rotulos_dict["dia_parcela"]:
        dados.dia_parcela = extrair_dia_parcela(rotulos_dict["dia_parcela"])
    if not dados.dia_parcela:
        dados.dia_parcela = extrair_dia_parcela(texto)

    if "inicio_parcelas" in rotulos_dict and rotulos_dict["inicio_parcelas"]:
        dados.inicio_parcelas = extrair_inicio_parcelas(rotulos_dict["inicio_parcelas"], dados.vencimento_entrada)
    if not dados.inicio_parcelas:
        dados.inicio_parcelas = extrair_inicio_parcelas(texto, dados.vencimento_entrada)
        
    if dados.inicio_parcelas:
        dia_inicio = str(int(dados.inicio_parcelas.split("/")[0]))
        if dia_inicio in ["10", "25"]:
            dados.dia_parcela = dia_inicio

    # COMPETÊNCIAS
    if "competencias" in rotulos_dict and rotulos_dict["competencias"]:
        dados.competencias = processar_competencias(rotulos_dict["competencias"])
    else:
        m_comp = re.search(r"(?i)\bcompet[eê]ncias?\s*:?\s*([^\n]+)", texto)
        if m_comp:
            dados.competencias = processar_competencias(m_comp.group(1))

    # AVISOS DE CAMPOS AUSENTES
    if not dados.telefone:
        dados.avisos.append("Telefone não identificado")
    if not dados.processo:
        dados.avisos.append("Processo não localizado")
    if dados.quantidade_parcelas and not dados.inicio_parcelas and not dados.dia_parcela:
        dados.avisos.append("Data de início das parcelas não informada")

    return dados.to_dict()
