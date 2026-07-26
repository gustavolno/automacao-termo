import re
from datetime import datetime
from docxtpl import DocxTemplate
from num2words import num2words

def valor_por_extenso(valor):
    """Converte um valor float para string monetária por extenso em português."""
    return num2words(valor, lang="pt_BR", to="currency")

def parse_monetario(texto):
    """Converte string '1.548,84' ou '1548.84' para float 1548.84"""
    if not texto: return None
    texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except:
        return None

def processar_competencias(texto):
    """Extrai, normaliza e agrupa competências da mensagem."""
    padrao_data = r"\b(\d{2}/\d{2}/\d{4}|\d{2}/\d{4})\b"
    encontradas = re.findall(padrao_data, texto)
    
    if not encontradas:
        return "__________"
        
    datas_obj = []
    for d in encontradas:
        if len(d) == 7: # MM/AAAA
            dt = datetime.strptime(d, "%m/%Y")
        else: # DD/MM/AAAA
            dt = datetime.strptime(d, "%d/%m/%Y")
            dt = dt.replace(day=1) # normaliza para o mês/ano
        if dt not in datas_obj:
            datas_obj.append(dt)
            
    datas_obj.sort()
    if not datas_obj:
        return "__________"
        
    grupos = []
    grupo_atual = [datas_obj[0]]
    
    for i in range(1, len(datas_obj)):
        atual = datas_obj[i]
        anterior = datas_obj[i-1]
        
        ano_esp, mes_esp = anterior.year, anterior.month + 1
        if mes_esp > 12:
            mes_esp = 1
            ano_esp += 1
            
        if atual.year == ano_esp and atual.month == mes_esp:
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
        return ", ".join(partes[:-1]) + " e " + partes[-1]
    return partes[0]

def parse_whatsapp_message(texto):
    """Extrai os dados da mensagem bruta do WhatsApp usando Regex."""
    match_nome = re.search(r"(?i)nome[:\s-]*([^\n]+)", texto)
    nome = match_nome.group(1).strip() if match_nome else "__________"
    
    match_cpf = re.search(r"(\d{3}\.\d{3}\.\d{3}-\d{2})", texto)
    cpf = match_cpf.group(1) if match_cpf else "__________"
    
    match_valor = re.search(r"(?i)(?:valor|total|causa|acordo).*?R\$\s*([\d\.,]+)", texto)
    valor_causa = parse_monetario(match_valor.group(1)) if match_valor else "__________"
    
    match_entrada = re.search(r"(?i)entrada.*?R\$\s*([\d\.,]+)", texto)
    valor_entrada = parse_monetario(match_entrada.group(1)) if match_entrada else "__________"
    
    match_parcelas = re.search(r"(?i)(\d+)\s*(?:x|vezes|parcelas).*?R\$\s*([\d\.,]+)", texto)
    if match_parcelas:
        qtd_parcelas = int(match_parcelas.group(1))
        valor_parcela = parse_monetario(match_parcelas.group(2))
    else:
        qtd_parcelas = "__________"
        valor_parcela = "__________"
    
    match_matricula = re.search(r"(?i)matr[íi]cula[:\s#nº°]*([\d]+)", texto)
    matricula = match_matricula.group(1).strip() if match_matricula else "__________"
    
    match_endereco = re.search(r"(?i)endere[çc]o[:\s-]*([^\n]+)", texto)
    endereco = match_endereco.group(1).strip() if match_endereco else "__________"
        
    competencias = processar_competencias(texto)
    
    return {
        "nome": nome,
        "cpf": cpf,
        "valor_causa": valor_causa,
        "valor_entrada": valor_entrada,
        "qtd_parcelas": qtd_parcelas,
        "valor_parcela": valor_parcela,
        "competencias": competencias,
        "matricula": matricula,
        "endereco": endereco,
    }


def formatar_caso(dados_extraidos):
    """Processa a matemática do acordo e gera os textos formatados. Resiliente a dados faltantes."""
    nome = dados_extraidos["nome"]
    cpf = dados_extraidos["cpf"]
    valor_causa = dados_extraidos["valor_causa"]
    competencias = dados_extraidos["competencias"]
    valor_entrada = dados_extraidos["valor_entrada"]
    qtd_parcelas = dados_extraidos["qtd_parcelas"]
    valor_parcela = dados_extraidos["valor_parcela"]
    matricula = dados_extraidos.get("matricula", "__________")
    endereco = dados_extraidos.get("endereco", "__________")
    
    # Data de hoje formatada em português
    MESES = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
             "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    hoje = datetime.now()
    data_hoje = f"{hoje.day} de {MESES[hoje.month]} de {hoje.year}"
    
    def fmt_brl(v):
        """Formata float para padrão monetário brasileiro: 1.548,84"""
        return f"{v:,.2f}".replace(".", "_").replace(",", ".").replace("_", ",")
    
    # Tratamento matemático resiliente
    if valor_causa != "__________":
        honorarios = valor_causa * 0.10
        valor_geap = valor_causa - honorarios
        str_valor_total = f"{fmt_brl(valor_causa)} ({valor_por_extenso(valor_causa).capitalize()})"
        str_honorarios = f"{fmt_brl(honorarios)} ({valor_por_extenso(honorarios).capitalize()})"
        str_valor_geap = f"{fmt_brl(valor_geap)} ({valor_por_extenso(valor_geap).capitalize()})"
    else:
        str_valor_total = "__________"
        str_honorarios = "__________"
        str_valor_geap = "__________"
        
    if valor_entrada != "__________":
        str_entrada = f"{fmt_brl(valor_entrada)} ({valor_por_extenso(valor_entrada).capitalize()})"
    else:
        str_entrada = "__________"
        
    str_qtd_parcelas = f"{qtd_parcelas:02d}" if qtd_parcelas != "__________" else "__________"
    
    if valor_parcela != "__________":
        str_valor_parcela = f"{fmt_brl(valor_parcela)} ({valor_por_extenso(valor_parcela).capitalize()})"
    else:
        str_valor_parcela = "__________"
    
    dados = {
        "nome_cliente": nome,
        "cpf_cliente": cpf,
        "valor_total": str_valor_total,
        "competencias": competencias,
        "valor_entrada": str_entrada,
        "qtd_parcelas": str_qtd_parcelas,
        "valor_parcela": str_valor_parcela,
        "honorarios": str_honorarios,
        "valor_geap": str_valor_geap,
        "matricula": matricula,
        "endereco": endereco,
        "data": data_hoje,
    }

    return dados


def preencher_termo_acordo(caminho_modelo, caminho_saida, dados):
    """Lê o modelo Word oficial e substitui as tags mantendo 100% da formatação (negrito, fontes, logos)."""
    doc = DocxTemplate(caminho_modelo)
    doc.render(dados)
    doc.save(caminho_saida)
    print(f"Termo gerado com sucesso: {caminho_saida}")


# === Ponto de Entrada (Exemplo de uso) ===
if __name__ == "__main__":
    mensagem_whatsapp = """
    Nome: CACILDA MARIA FERREIRA DE SANTANA NETO
    CPF: 050.888.364-49
    Matrícula: 232938
    Valor Total: R$ 10.309,09
    Entrada de: R$ 1.548,84
    Parcelamento: 24x de R$ 365,70
    Competências: 02/2022, 03/2022, 04/2022, 12/2022, 01/2023
    Endereço: Rua José Braz Moscow, nº 1650, Piedade, Jaboatão dos Guararapes/PE
    """
    
    # 1. Analisa o texto bruto
    dados_extraidos = parse_whatsapp_message(mensagem_whatsapp)
    
    # 2. Faz as continhas e formata (inclusive por extenso)
    dados_formatados = formatar_caso(dados_extraidos)
    
    # 3. Injeta no modelo real do escritório e salva
    nome_saida = f"Termo_{dados_formatados['nome_cliente'].split()[0]}.docx"
    preencher_termo_acordo("MODELO.docx", nome_saida, dados_formatados)
    print(f"Dados injetados: {dados_formatados}")