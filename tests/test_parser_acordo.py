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


def test_screenshot_1_marina_alves():
    """
    Teste com a mensagem do Screenshot 1 (Valor total negociado, Parcelas, Valor da parcela em linhas separadas).
    """
    mensagem = """Processo: 0700001-25.2026.8.07.0001
Nome: MARINA ALVES DE OLIVEIRA
CPF: 111.222.333-44
Telefone: (61) 90000-0001
E-mail: marina.oliveira@example.com
Endereço: Rua Exemplo, nº 120, Casa 02, Bairro Teste, Brasília/DF
CEP: 70000-001
Valor da causa: R$ 18.750,40
Valor total negociado: R$ 17.812,88
Entrada: R$ 1.781,28
Parcelas: 20
Valor da parcela: R$ 801,58"""

    dados = interpretar_mensagem(mensagem)

    assert dados["nome"] == "MARINA ALVES DE OLIVEIRA"
    assert dados["cpf"] == "111.222.333-44"
    assert dados["processo"] == "0700001-25.2026.8.07.0001"
    assert "(61) 90000-0001" in dados["telefone"]
    assert dados["email"] == "marina.oliveira@example.com"
    assert "Rua Exemplo" in dados["endereco"]
    assert dados["cep"] == "70000-001"
    assert dados["valor_original"] == "18.750,40"
    assert dados["valor_acordo"] == "17.812,88"
    assert dados["valor_entrada"] == "1.781,28"
    assert dados["quantidade_parcelas"] == "20"
    assert dados["valor_parcela"] == "801,58"


def test_screenshot_2_camila_rodrigues_email_header():
    """
    Teste com o cabeçalho de e-mail do Screenshot 2 (Evita vazamento do nome para Data/Hora do atendimento).
    """
    mensagem = """Prezado(a) Sr(a).

Conforme registro de atendimento de clientes, encaminhamos a notificação abaixo:

Cliente: CAMILA RODRIGUES MORAES
Data / Hora do atendimento: 28/07/2026 14:35
Tipo do atendimento: Atendimento
Assunto do atendimento: Acordo fechado
Forma de atendimento: WhatsApp

Detalhamento

Processo nº: 0700009-10.2026.8.07.0009 Beneficiário: CAMILA RODRIGUES MORAES CPF: 999.000.111-22 Telefone: (61) 90000-0009 E-mail: camila.moraes@example.com Endereço: Quadra Modelo 09, Conjunto A, Casa 09, Brasília/DF CEP: 78000-009 Valor da causa: R$ 11.257,83 Competências negociadas: 10/03/2023 a 11/09/2023 Condição de negociação: entrada de R$ 1.024,46 + 24x de R$ 384,17."""

    dados = interpretar_mensagem(mensagem)

    assert dados["nome"] == "CAMILA RODRIGUES MORAES"
    assert dados["cpf"] == "999.000.111-22"
    assert dados["processo"] == "0700009-10.2026.8.07.0009"
    assert "(61) 90000-0009" in dados["telefone"]
    assert dados["email"] == "camila.moraes@example.com"
    assert "Quadra Modelo 09" in dados["endereco"]
    assert dados["cep"] == "78000-009"
    assert dados["valor_original"] == "11.257,83"
    assert dados["valor_entrada"] == "1.024,46"
    assert dados["quantidade_parcelas"] == "24"
    assert dados["valor_parcela"] == "384,17"
    assert dados["valor_acordo"] == "10.244,54"
    assert dados["competencias"] == "10/03/2023 a 11/09/2023"

def test_screenshot_3_dados_acordo():
    """
    Teste com a mensagem do Screenshot 3 (texto corrido DADOS DO ACORDO).
    """
    mensagem = "DADOS DO ACORDO Processo: 6053087-91.2026.8.03.0001 Beneficiária: Mary Gonçalves Pimentel CPF: 123.253.092-15 Telefone: (96) 91732-598 E-mail: pimentel.marygoncalves36@gmail.com Endereço: Av. Severino G. de Almeida, até 2549/2550, nº 2199 Jardim Felicidade Macapá/AP - CEP: 68.909-012 Valor atualizado da causa: R$ 6.170,70 Competências negociadas: 10/12/2020 a 10/03/2021 Com a finalidade de promover a composição amigável e o encerramento do processo, foi concedido um desconto de 20%, resultando no valor negociado de R$ 4.936,56, com pagamento parcelado em 02 vezes. Condições de pagamento: 1ª parcela (entrada): R$ 2.468,28, com vencimento em 03/08/2026; 2ª parcela: R$ 2.468,28, com vencimento em 10/09/2026."

    dados = interpretar_mensagem(mensagem)

    assert dados["nome"] == "Mary Gonçalves Pimentel"
    assert dados["processo"] == "6053087-91.2026.8.03.0001"
    assert "(96) 91732-598" in dados["telefone"]
    assert dados["cep"] == "68909-012"
    assert dados["valor_original"] == "6.170,70"
    assert dados["competencias"] == "10/12/2020 a 10/03/2021"
    assert dados["valor_acordo"] == "4.936,56"
    assert dados["quantidade_parcelas"] == "02"
    assert dados["valor_parcela"] == "2.468,28"
    assert dados["valor_entrada"] == "2.468,28"
    assert dados["vencimento_entrada"] == "03/08/2026"
    assert dados["inicio_parcelas"] == "10/09/2026"
    assert dados["dia_parcela"] == "10"
