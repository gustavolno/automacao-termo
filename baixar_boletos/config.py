import os
import re
import unicodedata
from pathlib import Path
from dotenv import load_dotenv

# Diretório de dados local específico do usuário no Windows (isolado por máquina)
USER_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "BaixarBoletos"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Carrega .env do perfil local da máquina prioritariamente
LOCAL_ENV = USER_DATA_DIR / ".env"
if LOCAL_ENV.exists():
    load_dotenv(dotenv_path=LOCAL_ENV, override=True)
else:
    load_dotenv()

GLOBAL_OFFICE_URL = os.getenv("GLOBAL_OFFICE_URL", "https://www.globalofficeweb.com.br/")
GLOBAL_OFFICE_LOGIN = os.getenv("GLOBAL_OFFICE_LOGIN", "")
GLOBAL_OFFICE_USER = os.getenv("GLOBAL_OFFICE_USER", "")
GLOBAL_OFFICE_PASS = os.getenv("GLOBAL_OFFICE_PASS", "")

STATE_FILE = str(USER_DATA_DIR / "globaloffice_state.json")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def salvar_credenciais_locais(login: str, usuario: str, senha: str):
    """Grava as credenciais do usuário exclusivamente na máquina local dele."""
    global GLOBAL_OFFICE_LOGIN, GLOBAL_OFFICE_USER, GLOBAL_OFFICE_PASS
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    conteudo = (
        f"GLOBAL_OFFICE_URL={GLOBAL_OFFICE_URL}\n"
        f"GLOBAL_OFFICE_LOGIN={login.strip()}\n"
        f"GLOBAL_OFFICE_USER={usuario.strip()}\n"
        f"GLOBAL_OFFICE_PASS={senha.strip()}\n"
    )
    with open(LOCAL_ENV, "w", encoding="utf-8") as f:
        f.write(conteudo)
    load_dotenv(dotenv_path=LOCAL_ENV, override=True)
    GLOBAL_OFFICE_LOGIN = login.strip()
    GLOBAL_OFFICE_USER = usuario.strip()
    GLOBAL_OFFICE_PASS = senha.strip()

# Mapeamento de meses em português
MESES_PT = {
    "01": "JAN", "02": "FEV", "03": "MAR", "04": "ABR",
    "05": "MAI", "06": "JUN", "07": "JUL", "08": "AGO",
    "09": "SET", "10": "OUT", "11": "NOV", "12": "DEZ"
}

def normalizar_texto(texto: str) -> str:
    """Remove acentos e espaços extras para comparações seguras."""
    if not texto:
        return ""
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
    return re.sub(r'\s+', ' ', texto).strip().upper()

def formatar_nome_arquivo_boleto(vencimento_str: str, eh_entrada: bool = False, **kwargs) -> str:
    """
    Padrão Cronológico ISO Corporativo:
    - Parcela Comum: BOLETO - 2026-10 (OUT).pdf
    - Parcela Entrada: BOLETO - ENTRADA - 2026-10 (OUT).pdf
    """
    partes = vencimento_str.strip().split("/")
    if len(partes) == 3:
        dia, mes_num, ano = partes[0], partes[1], partes[2]
        mes_txt = MESES_PT.get(mes_num, mes_num)
        sufixo_data = f"{ano}-{mes_num} ({mes_txt})"
    else:
        sufixo_data = vencimento_str.replace("/", "-")

    if eh_entrada:
        return f"BOLETO - ENTRADA - {sufixo_data}.pdf"
    return f"BOLETO - {sufixo_data}.pdf"

def obter_pasta_boletos_cliente(nome_cliente: str) -> Path:
    """
    Localiza ou cria a pasta de destino dos boletos do cliente no Dropbox:
    ...\Dropbox\COBRANÇA NEGOCIAÇÃO\ADMINISTRATIVO- COBRANÇA\ACOMPANHAMENTO DE ACORDOS AC COBRANÇA\<CLIENTE>\BOLETOS DO ACORDO
    """
    nome_norm = normalizar_texto(nome_cliente)
    nome_pasta_cliente = nome_cliente.strip().upper()

    # 1. Caminho direto mais comum para agilidade e precisão
    direto = Path(r"C:\Users\Cob_Geap_05082026\Dropbox\COBRANÇA NEGOCIAÇÃO\ADMINISTRATIVO- COBRANÇA\ACOMPANHAMENTO DE ACORDOS AC COBRANÇA")
    if direto.exists():
        pasta_alvo = None
        for p in direto.iterdir():
            if p.is_dir() and normalizar_texto(p.name) == nome_norm:
                pasta_alvo = p
                break
        if not pasta_alvo:
            pasta_alvo = direto / nome_pasta_cliente
            pasta_alvo.mkdir(parents=True, exist_ok=True)
        dest = pasta_alvo / "BOLETOS DO ACORDO"
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    candidatos_dropbox = []
    custom_dropbox = os.getenv("DROPBOX_PATH")
    if custom_dropbox:
        candidatos_dropbox.append(Path(custom_dropbox))

    user_profile = os.environ.get("USERPROFILE", "")
    if user_profile:
        candidatos_dropbox.append(Path(user_profile) / "Dropbox")
    
    candidatos_dropbox.extend([
        Path("C:/Users/Cob_Geap_05082026/Dropbox"),
        Path("C:/Users/Gustavo/Dropbox"),
        Path.home() / "Dropbox"
    ])

    pasta_acordos = None

    for base in candidatos_dropbox:
        if not base.exists():
            continue
            
        for item_cobranca in base.iterdir():
            if item_cobranca.is_dir() and "COBRAN" in normalizar_texto(item_cobranca.name):
                for item_admin in item_cobranca.iterdir():
                    if item_admin.is_dir() and "ADMINISTRATIVO" in normalizar_texto(item_admin.name):
                        for item_acordos in item_admin.iterdir():
                            if item_acordos.is_dir() and "ACOMPANHAMENTO DE ACORDOS" in normalizar_texto(item_acordos.name):
                                if "AC COBRANCA" in normalizar_texto(item_acordos.name):
                                    pasta_acordos = item_acordos
                                    break
                                elif not pasta_acordos:
                                    pasta_acordos = item_acordos
                        if pasta_acordos and "AC COBRANCA" in normalizar_texto(pasta_acordos.name):
                            break
                    if pasta_acordos and "AC COBRANCA" in normalizar_texto(pasta_acordos.name):
                        break
            if pasta_acordos and "AC COBRANCA" in normalizar_texto(pasta_acordos.name):
                break
        if pasta_acordos:
            break

    if pasta_acordos and pasta_acordos.exists():
        pasta_alvo_cliente = None
        for pasta_existente in pasta_acordos.iterdir():
            if pasta_existente.is_dir() and normalizar_texto(pasta_existente.name) == nome_norm:
                pasta_alvo_cliente = pasta_existente
                break
        
        if not pasta_alvo_cliente:
            pasta_alvo_cliente = pasta_acordos / nome_pasta_cliente
            pasta_alvo_cliente.mkdir(parents=True, exist_ok=True)
            
        destino_boletos = pasta_alvo_cliente / "BOLETOS DO ACORDO"
        destino_boletos.mkdir(parents=True, exist_ok=True)
        return destino_boletos

    # Fallback local se o Dropbox não estiver disponível
    destino_fallback = Path("./downloads_boletos") / nome_pasta_cliente / "BOLETOS DO ACORDO"
    destino_fallback.mkdir(parents=True, exist_ok=True)
    return destino_fallback
