import re
from datetime import datetime

def limpar_cpf(cpf: str) -> str:
    """Remove pontuação do CPF e retorna apenas os dígitos."""
    if not cpf:
        return ""
    return re.sub(r'\D', '', str(cpf))

def validar_cpf(cpf: str) -> bool:
    """Valida se o formato numérico do CPF tem 11 dígitos. (Validação simples)."""
    cpf_limpo = limpar_cpf(cpf)
    return len(cpf_limpo) == 11

def validar_email(email: str) -> bool:
    """Valida o formato do e-mail usando expressão regular."""
    if not email:
        return False
    padrao = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return re.match(padrao, str(email).strip()) is not None

def formatar_data_vencimento(data) -> str:
    """
    Recebe a data do Excel (pode ser objeto datetime ou string) e 
    converte para string obrigatoriamente no formato dd/MM/yyyy.
    Retorna string vazia se falhar.
    """
    if not data:
        return ""
    if isinstance(data, datetime):
        return data.strftime("%d/%m/%Y")
    
    # Se for string, tenta identificar o formato
    data_str = str(data).strip().split(" ")[0] # Tira possível hora se vier string
    if "/" in data_str:
        partes = data_str.split("/")
        # Tenta inferir se é YYYY/MM/DD ou DD/MM/YYYY
        if len(partes[0]) == 4:
            return f"{partes[2].zfill(2)}/{partes[1].zfill(2)}/{partes[0]}"
        return f"{partes[0].zfill(2)}/{partes[1].zfill(2)}/{partes[2]}"
    elif "-" in data_str:
        partes = data_str.split("-")
        if len(partes[0]) == 4:
            return f"{partes[2].zfill(2)}/{partes[1].zfill(2)}/{partes[0]}"
        return f"{partes[0].zfill(2)}/{partes[1].zfill(2)}/{partes[2]}"
    return ""

def formatar_valor_moeda(valor) -> str:
    """
    Recebe o valor numérico do Excel e formata com vírgula para centavos 
    (formato esperado pelo Global Office, sem o R$). Ex: 511,63
    """
    try:
        if isinstance(valor, str):
            valor = float(valor.replace("R$", "").replace(".", "").replace(",", ".").strip())
        
        # Formata com duas casas decimais e vírgula
        return f"{valor:.2f}".replace(".", ",")
    except (ValueError, TypeError):
        return ""
