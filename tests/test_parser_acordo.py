import pytest
from parser_acordo import interpretar_mensagem, parse_valor_brl, formatar_valor_brl, calcular_valor_acordo
from decimal import Decimal


def test_mensagem_informal_completa():
    """
    Teste principal obrigatório (Seção 21 do prompt).
    """
    mensagem = (
        "Boa tarde. Acordo fechado para Juliana Mendes Costa, CPF 33344455566. "
        "Processo 0700003-45.2026.8.07.0003. Telefone/WhatsApp: 61900000003. Email juliana.costa@example.com. "
        "Mora na Quadra Fictícia 10, Conjunto B, Casa 08, Brasília DF, CEP 72000-003. "
        "A dívida é de R$ 9.850,00 e ficou negociada por R$ 8.865,00. Entrada de R$ 865,00 e o restante "
        "em 16x de R$ 500,00. Vencimento da entrada em 20/08/2026 e parcelas todo dia 20."
    )

    dados = interpretar_mensagem(mensagem)

    assert dados["nome"] == "Juliana Mendes Costa"
    assert dados["cpf"] == "333.444.555-66"
    assert dados["processo"] == "0700003-45.2026.8.07.0003"
    assert dados["telefone"] == "61900000003"
    assert dados["email"] == "juliana.costa@example.com"
    assert "Quadra Fictícia 10" in dados["endereco"]
    assert dados["cep"] == "72000-003"
    assert dados["valor_original"] == "9.850,00"
    assert dados["valor_acordo"] == "8.865,00"
    assert dados["valor_entrada"] == "865,00"
    assert dados["vencimento_entrada"] == "20/08/2026"
    assert dados["quantidade_parcelas"] == "16"
    assert dados["valor_parcela"] == "500,00"
    assert dados["dia_parcela"] == "20"
    assert dados["matricula"] == ""
    assert dados["competencias"] == ""
    assert dados["inicio_parcelas"] == ""


def test_mensagem_em_linhas():
    """
    Teste com mensagem em linhas estruturadas (Seção 22).
    """
    mensagem = """
Cliente: CARLOS EDUARDO PEREIRA
CPF: 222.333.444-55
Processo: 0700002-30.2026.8.07.0002
Telefone: 61 90000-0002
E-mail: carlos.pereira@example.com
Endereço: Avenida Modelo, lote 15, apartamento 203, Cidade Fictícia/DF
CEP: 71000-002
Valor da causa: R$ 12.480,90
Valor do acordo: R$ 11.232,81
Competências: 03/2024 a 08/2024
Entrada: R$ 1.232,81
Saldo: 20 parcelas de R$ 500,00
Primeiro vencimento: 15/08/2026
"""
    dados = interpretar_mensagem(mensagem)

    assert dados["nome"] == "CARLOS EDUARDO PEREIRA"
    assert dados["cpf"] == "222.333.444-55"
    assert dados["processo"] == "0700002-30.2026.8.07.0002"
    assert "61" in dados["telefone"] and "90000-0002" in dados["telefone"]
    assert dados["email"] == "carlos.pereira@example.com"
    assert "Avenida Modelo" in dados["endereco"]
    assert dados["cep"] == "71000-002"
    assert dados["valor_original"] == "12.480,90"
    assert dados["valor_acordo"] == "11.232,81"
    assert dados["competencias"] == "03/2024 a 08/2024"
    assert dados["valor_entrada"] == "1.232,81"
    assert dados["quantidade_parcelas"] == "20"
    assert dados["valor_parcela"] == "500,00"
    assert dados["vencimento_entrada"] == "15/08/2026"


def test_total_calculado():
    """
    Teste de cálculo automático do valor do acordo quando não informado (Seção 22).
    """
    mensagem = """
Processo n° 0700004-50.2026.8.07.0004
Beneficiário: ROBERTO LIMA FERREIRA
CPF: 444.555.666-77
Telefone: (61) 90000-0004
E-mail: roberto.ferreira@example.com
Endereço: Rua de Testes, nº 44, Bairro Simulado, Brasília/DF
CEP: 73000-004
Valor da causa: R$ 15.500,00
Condição de negociação: entrada de R$ 1.500,00 + 28x de R$ 400,00.
"""
    dados = interpretar_mensagem(mensagem)

    assert dados["nome"] == "ROBERTO LIMA FERREIRA"
    assert dados["valor_original"] == "15.500,00"
    assert dados["valor_entrada"] == "1.500,00"
    assert dados["quantidade_parcelas"] == "28"
    assert dados["valor_parcela"] == "400,00"
    # Cálculo: 1.500 + 28 * 400 = 12.700,00
    assert dados["valor_acordo"] == "12.700,00"


def test_delimite_paragrafo_unico():
    """
    Teste de delimitação rigorosa entre campos em parágrafo único (Seção 22).
    """
    mensagem = (
        "Beneficiário: FERNANDO NUNES DA SILVA CPF: 888.999.000-11 Telefone: (61) 90000-0008 "
        "E-mail: fernando.nunes@example.com Endereço: Avenida Campo Longo, nº 800, Casa, Setor de Testes, Brasília/DF "
        "CEP: 77000-008 Valor da causa: R$ 32.800,00 Valor negociado: R$ 29.520,00 Entrada: R$ 2.952,00 "
        "Parcelamento: 24 parcelas de R$ 1.107,00."
    )
    dados = interpretar_mensagem(mensagem)

    assert dados["nome"] == "FERNANDO NUNES DA SILVA"
    assert dados["cpf"] == "888.999.000-11"
    assert "(61) 90000-0008" in dados["telefone"]
    assert dados["email"] == "fernando.nunes@example.com"
    assert "Avenida Campo Longo" in dados["endereco"]
    assert "32.800,00" not in dados["endereco"]
    assert dados["cep"] == "77000-008"
    assert dados["valor_original"] == "32.800,00"
    assert dados["valor_acordo"] == "29.520,00"
    assert dados["valor_entrada"] == "2.952,00"
    assert dados["quantidade_parcelas"] == "24"
    assert dados["valor_parcela"] == "1.107,00"


def test_processo_nao_localizado():
    mensagem = "Cliente: JOAO DA SILVA\nCPF: 111.222.333-44\nProcesso não localizado\nValor devido: R$ 5.000,00"
    dados = interpretar_mensagem(mensagem)

    assert dados["processo"] == "Não localizado"
    assert dados["valor_original"] == "5.000,00"


def test_calculo_decimal_preciso():
    dec_val = parse_valor_brl("R$ 10.244,54")
    assert dec_val == Decimal("10244.54")

    formatted = formatar_valor_brl(dec_val)
    assert formatted == "10.244,54"

    calc = calcular_valor_acordo(Decimal("1024.46"), 24, Decimal("384.17"))
    assert calc == Decimal("10244.54")


def test_multiplos_telefones_e_emails():
    mensagem = (
        "Cliente: MARIA CONCEICAO\n"
        "CPF: 123.456.789-00\n"
        "Telefones: (61) 98888-1111 / (61) 97777-2222\n"
        "E-mails: maria@test.com / conceicao@test.com\n"
        "Valor da causa: 10000,00"
    )
    dados = interpretar_mensagem(mensagem)

    assert "98888-1111" in dados["telefone"]
    assert "97777-2222" in dados["telefone"]
    assert "maria@test.com" in dados["email"]
    assert "conceicao@test.com" in dados["email"]


def test_ordem_alterada_e_sem_cifrao():
    mensagem = (
        "Valor do acordo: 5000,00\n"
        "Entrada: 1000,00\n"
        "10x de 400,00\n"
        "Cliente: ANA BEATRIZ NOGUEIRA\n"
        "CPF: 999.888.777-66\n"
        "Valor original: 6500,00"
    )
    dados = interpretar_mensagem(mensagem)

    assert dados["nome"] == "ANA BEATRIZ NOGUEIRA"
    assert dados["cpf"] == "999.888.777-66"
    assert dados["valor_original"] == "6.500,00"
    assert dados["valor_acordo"] == "5.000,00"
    assert dados["valor_entrada"] == "1.000,00"
    assert dados["quantidade_parcelas"] == "10"
    assert dados["valor_parcela"] == "400,00"
