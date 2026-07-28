"""
Módulo de automação de acordos.
Utiliza parser_acordo.py como único interpretador de dados.
"""

import os
from datetime import datetime
from docxtpl import DocxTemplate
from num2words import num2words
from parser_acordo import (
    interpretar_mensagem,
    parse_valor_brl,
    formatar_valor_brl,
    calcular_valor_acordo
)

def valor_por_extenso(valor: float) -> str:
    """Converte um valor numérico para string monetária por extenso em português."""
    texto = num2words(valor, lang="pt_BR", to="currency")
    if texto.startswith("mil"):
        texto = "um " + texto
    return texto


def formatar_caso(dados_extraidos: dict) -> dict:
    """
    Processa a matemática do acordo e gera os textos formatados para a docxtpl.
    """
    MESES = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
             "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    hoje = datetime.now()
    data_hoje = f"{hoje.day} de {MESES[hoje.month]} de {hoje.year}"

    nome = dados_extraidos.get("nome", "__________") or "__________"
    cpf = dados_extraidos.get("cpf", "__________") or "__________"
    processo = dados_extraidos.get("processo", "__________") or "__________"
    matricula = dados_extraidos.get("matricula", "__________") or "__________"
    telefone = dados_extraidos.get("telefone", "__________") or "__________"
    email = dados_extraidos.get("email", "__________") or "__________"
    endereco = dados_extraidos.get("endereco", "__________") or "__________"
    cep = dados_extraidos.get("cep", "__________") or "__________"
    competencias = dados_extraidos.get("competencias", "__________") or "__________"

    vo = parse_valor_brl(dados_extraidos.get("valor_original", ""))
    va = parse_valor_brl(dados_extraidos.get("valor_acordo", ""))
    ve = parse_valor_brl(dados_extraidos.get("valor_entrada", ""))
    vp = parse_valor_brl(dados_extraidos.get("valor_parcela", ""))

    qp = dados_extraidos.get("quantidade_parcelas", "__________") or "__________"
    venc_entrada = dados_extraidos.get("vencimento_entrada", "__________") or "__________"
    inicio_parcelas = dados_extraidos.get("inicio_parcelas", "__________") or "__________"
    dia_parcela = dados_extraidos.get("dia_parcela", "__________") or "__________"

    if vo:
        str_valor_original = f"{formatar_valor_brl(vo)} ({valor_por_extenso(float(vo)).capitalize()})"
    else:
        str_valor_original = "__________"

    if va:
        honorarios = (va * Decimal("0.10")).quantize(Decimal("0.01"))
        valor_geap = va - honorarios
        str_valor_acordo = f"{formatar_valor_brl(va)} ({valor_por_extenso(float(va)).capitalize()})"
        str_honorarios = f"{formatar_valor_brl(honorarios)} ({valor_por_extenso(float(honorarios)).capitalize()})"
        str_valor_geap = f"{formatar_valor_brl(valor_geap)} ({valor_por_extenso(float(valor_geap)).capitalize()})"
    else:
        str_valor_acordo = str_honorarios = str_valor_geap = "__________"

    str_entrada = f"{formatar_valor_brl(ve)} ({valor_por_extenso(float(ve)).capitalize()})" if ve else "__________"
    str_parcela = f"{formatar_valor_brl(vp)} ({valor_por_extenso(float(vp)).capitalize()})" if vp else "__________"

    return {
        "nome": nome,
        "nome_cliente": nome,
        "cpf": cpf,
        "cpf_cliente": cpf,
        "processo": processo,
        "matricula": matricula,
        "telefone": telefone,
        "email": email,
        "endereco": endereco,
        "cep": cep,
        "valor_original": str_valor_original,
        "valor_divida": str_valor_original,
        "valor_acordo": str_valor_acordo,
        "valor_entrada": str_entrada,
        "vencimento_entrada": venc_entrada,
        "venc_entrada": venc_entrada,
        "quantidade_parcelas": qp,
        "qtd_parcelas": qp,
        "valor_parcela": str_parcela,
        "inicio_parcelas": inicio_parcelas,
        "dia_parcela": dia_parcela,
        "competencias": competencias,
        "honorarios": str_honorarios,
        "valor_geap": str_valor_geap,
        "data": data_hoje,
    }


def preencher_termo_acordo(caminho_modelo: str, caminho_saida: str, dados: dict):
    """Preenche o modelo Word utilizando docxtpl."""
    doc = DocxTemplate(caminho_modelo)
    doc.render(dados)
    doc.save(caminho_saida)
    print(f"Termo gerado com sucesso: {caminho_saida}")


from decimal import Decimal

if __name__ == "__main__":
    mensagem_whatsapp = """
    Nome: CACILDA MARIA FERREIRA DE SANTANA NETO
    CPF: 050.888.364-49
    Matrícula: 232938
    Telefone: 81 99999-0000
    E-mail: cacilda@example.com
    Valor da Causa: R$ 10.309,09
    Entrada de: R$ 1.548,84
    Parcelamento: 24x de R$ 365,70
    Competências: 02/2022, 03/2022, 04/2022, 12/2022, 01/2023
    Endereço: Rua José Braz Moscow, nº 1650, Piedade, Jaboatão dos Guararapes/PE
    """
    dados_extraidos = interpretar_mensagem(mensagem_whatsapp)
    dados_formatados = formatar_caso(dados_extraidos)
    nome_saida = f"Termo_{dados_formatados['nome_cliente'].split()[0]}.docx"
    preencher_termo_acordo("MODELO.docx", nome_saida, dados_formatados)
    print(f"Dados injetados: {dados_formatados}")