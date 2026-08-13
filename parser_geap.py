"""
parser_geap.py — Lê a "Ficha Financeira" (PDF da GEAP/IPASEP) e extrai a lista de
parcelas: (descricao, data_vencimento, valor).

Formato esperado de linhas na tabela:
  Parcelamento (1/12)  10/01/2020  R$ 1.241,72
  Parcelamento (2/12)  10/02/2020  R$ 1.241,72
  ...
"""

import re
import pdfplumber
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Parcela:
    descricao: str
    data: str       # formato DD/MM/AAAA
    valor: str      # formato 1.241,72 (sem R$)


# Padrão: Data no formato DD/MM/AAAA e valor monetário (com ou sem R$)
_RE_DATA = re.compile(r'\b(\d{2}/\d{2}/\d{4})\b')
_RE_VALOR = re.compile(r'R?\$?\s*([\d]{1,3}(?:[.\s]?\d{3})*[,]\d{2})\b')


def _normalizar_valor(raw: str) -> str:
    """Remove espaços internos e garante formato 1.241,72"""
    v = re.sub(r'\s', '', raw)
    return v


def extrair_parcelas(caminho_pdf: str) -> List[Parcela]:
    """Extrai todas as parcelas da Ficha Financeira em PDF."""
    parcelas: List[Parcela] = []
    
    with pdfplumber.open(caminho_pdf) as pdf:
        for page in pdf.pages:
            # Primeiro tenta extração de tabela estruturada
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        if not row:
                            continue
                        # Concatena células da linha para análise
                        row_text = " | ".join(str(c or "").strip() for c in row)
                        _processar_linha(row_text, row, parcelas)
            else:
                # Fallback: texto puro linha por linha
                text = page.extract_text() or ""
                for linha in text.splitlines():
                    _processar_linha_texto(linha, parcelas)

    return parcelas


def _processar_linha(row_text: str, row: list, parcelas: List[Parcela]):
    """Processa uma linha de tabela extraída pelo pdfplumber."""
    # Precisa ter pelo menos uma data e um valor monetário
    datas = _RE_DATA.findall(row_text)
    valores = _RE_VALOR.findall(row_text)
    
    if not datas or not valores:
        return
    
    data = datas[0]
    valor = _normalizar_valor(valores[-1])  # último valor da linha = valor da parcela
    
    # Descrição: primeira célula não-vazia que não seja data nem valor
    descricao = ""
    for celula in row:
        celula = str(celula or "").strip()
        if celula and not _RE_DATA.match(celula) and not _RE_VALOR.match(celula):
            descricao = celula
            break
    
    if not descricao:
        descricao = "Parcela"
    
    # Evita duplicatas
    if not any(p.data == data and p.valor == valor for p in parcelas):
        parcelas.append(Parcela(descricao=descricao, data=data, valor=valor))


def _processar_linha_texto(linha: str, parcelas: List[Parcela]):
    """Fallback: processa linha de texto puro."""
    datas = _RE_DATA.findall(linha)
    valores = _RE_VALOR.findall(linha)
    
    if not datas or not valores:
        return
    
    data = datas[0]
    valor = _normalizar_valor(valores[-1])
    
    # Remove datas e valores para extrair a descrição
    descricao = linha
    descricao = _RE_DATA.sub("", descricao)
    descricao = _RE_VALOR.sub("", descricao)
    descricao = re.sub(r'[R$]', '', descricao)
    descricao = re.sub(r'\s+', ' ', descricao).strip(" |-.,")
    
    if not descricao:
        descricao = "Parcela"
    
    if not any(p.data == data and p.valor == valor for p in parcelas):
        parcelas.append(Parcela(descricao=descricao, data=data, valor=valor))


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python parser_geap.py <caminho_do_pdf>")
        sys.exit(1)
    
    caminho = sys.argv[1]
    parcelas = extrair_parcelas(caminho)
    print(f"\n✅ {len(parcelas)} parcelas encontradas:\n")
    for i, p in enumerate(parcelas, 1):
        print(f"  {i:2d}. {p.data}  R$ {p.valor}  — {p.descricao}")
