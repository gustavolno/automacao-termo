"""
parser_geap.py — Lê a "Ficha Financeira" (PDF da GEAP/IPASEP) e extrai a lista de
parcelas: (descricao, data_vencimento, valor_cobranca).

Estrutura da tabela identificada:
  Colunas: Comp. | Conveniada | Receita | Tipo | Cobrança | Recebido | Vencimento | Situação | Nro. Cobrança | ...
  Índices:  [0]     [1]          [2]     [3]     [4]        [5]        [6]          [7]         [8]
"""

import re
import pdfplumber
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Parcela:
    descricao: str
    data: str       # formato DD/MM/AAAA (data de vencimento)
    valor: str      # formato 1.241,72 (sem R$, somente os dígitos)


_RE_DATA   = re.compile(r'^\d{2}/\d{2}/\d{4}$')
_RE_COMP   = re.compile(r'^\d{2}/\d{4}$')  # competência MM/AAAA
_RE_VALOR  = re.compile(r'^R\$\s*([\d]{1,3}(?:[.\s]?\d{3})*[,]\d{2})$')


def _limpar_valor(raw: str) -> Optional[str]:
    """Extrai o valor numérico de 'R$ 1.241,72' -> '1.241,72'. Retorna None se zero ou inválido."""
    if not raw:
        return None
    m = _RE_VALOR.match(raw.strip())
    if not m:
        return None
    v = m.group(1)
    # Ignorar valores zero
    if re.match(r'^0[,.]00$|^0$', v):
        return None
    return v


def extrair_parcelas(caminho_pdf: str) -> List[Parcela]:
    """
    Extrai todas as parcelas com vencimento e valor de cobrança da Ficha Financeira.
    Ignora linhas com valor zero (já pagas ou zeradas).
    """
    parcelas: List[Parcela] = []

    with pdfplumber.open(caminho_pdf) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue

                # Detectar cabeçalho para identificar índices das colunas
                header = [str(c or "").strip().lower() for c in table[0]]
                
                # Tentar mapear colunas pelo cabeçalho
                idx_venc   = _find_col(header, ["vencimento", "venc"])
                idx_cobr   = _find_col(header, ["cobrança", "cobranca", "valor"])
                idx_receita = _find_col(header, ["receita", "histórico", "historico", "descrição"])
                idx_comp   = _find_col(header, ["comp.", "comp", "competência", "competencia"])
                idx_sit    = _find_col(header, ["situação", "situacao", "status"])

                # Se não achou pelo cabeçalho, usa as posições conhecidas do PDF da GEAP
                if idx_venc is None:
                    idx_venc    = 6
                    idx_cobr    = 4
                    idx_receita = 2
                    idx_comp    = 0

                for row in table[1:]:
                    if not row or len(row) <= idx_venc:
                        continue

                    venc_raw  = str(row[idx_venc]  or "").strip()
                    cobr_raw  = str(row[idx_cobr]  or "").strip()
                    rec_raw   = str(row[idx_receita] or "").strip()
                    comp_raw  = str(row[idx_comp]  or "").strip()

                    # A data de vencimento deve ser DD/MM/AAAA
                    if not _RE_DATA.match(venc_raw):
                        continue

                    valor = _limpar_valor(cobr_raw)
                    if valor is None:
                        continue

                    # Montar descrição: "Receita (Competência)"
                    descricao = rec_raw or "Parcela"
                    if comp_raw and _RE_COMP.match(comp_raw):
                        descricao = f"{descricao} ({comp_raw})"

                    # Evitar duplicatas exatas
                    if not any(p.data == venc_raw and p.valor == valor for p in parcelas):
                        parcelas.append(Parcela(descricao=descricao, data=venc_raw, valor=valor))

    return parcelas


def _find_col(header: List[str], keys: List[str]) -> Optional[int]:
    """Encontra o índice da coluna cujo nome contém uma das chaves."""
    for i, h in enumerate(header):
        for k in keys:
            if k in h:
                return i
    return None


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python parser_geap.py <caminho_do_pdf>")
        sys.exit(1)

    caminho = sys.argv[1]
    ps = extrair_parcelas(caminho)
    print(f"\n{len(ps)} parcelas encontradas:\n")
    total = 0.0
    for i, p in enumerate(ps, 1):
        v = float(p.valor.replace(".", "").replace(",", "."))
        total += v
        print(f"  {i:2d}. {p.data}  R$ {p.valor:>12}  -- {p.descricao}")
    print(f"\n  TOTAL: R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
