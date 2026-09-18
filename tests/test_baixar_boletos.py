import pytest
from pathlib import Path
from baixar_boletos.config import (
    formatar_nome_arquivo_boleto,
    obter_pasta_boletos_cliente,
    normalizar_texto,
    MESES_PT
)

def test_formatar_nome_arquivo_parcela():
    assert formatar_nome_arquivo_boleto("10/11/2027", eh_entrada=False) == "BOLETO - NOV 2027.pdf"
    assert formatar_nome_arquivo_boleto("05/05/2026", eh_entrada=False) == "BOLETO - MAI 2026.pdf"
    assert formatar_nome_arquivo_boleto("20/12/2025", eh_entrada=False) == "BOLETO - DEZ 2025.pdf"

def test_formatar_nome_arquivo_entrada():
    assert formatar_nome_arquivo_boleto("15/01/2026", eh_entrada=True) == "BOLETO - ENTRADA - JAN 2026.pdf"
    assert formatar_nome_arquivo_boleto("10/02/2026", eh_entrada=True) == "BOLETO - ENTRADA - FEV 2026.pdf"

def test_todos_meses_mapeados():
    for mes in range(1, 13):
        assert mes in MESES_PT
        assert len(MESES_PT[mes]) == 3

def test_normalizar_texto():
    assert normalizar_texto("Aldrigues Cândido Advocacia") == "ALDRIGUES CANDIDO ADVOCACIA"
    assert normalizar_texto("  joão   da silva  ") == "JOAO DA SILVA"

def test_obter_pasta_boletos_cliente():
    pasta = obter_pasta_boletos_cliente("TESTE AUTOMACAO CLIENTE")
    assert pasta is not None
    assert pasta.name == "BOLETOS DO ACORDO"
    assert "TESTE AUTOMACAO CLIENTE" in str(pasta).upper()
