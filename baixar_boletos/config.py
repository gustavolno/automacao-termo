from typing import Optional
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

# Planilha oficial online (link de compartilhamento da Jaciana) e cópias locais
PLANILHA_ONLINE_URL = os.getenv(
    "PLANILHA_ONLINE_URL",
    "https://1drv.ms/x/c/cf907b88c62f205d/IQBym77qZvWKSpWhxamQ4GWEAQ2yMvH6JDUNIEugFLtNVI8?e=XsIR6a",
)
PLANILHA_ONLINE_FILE = USER_DATA_DIR / "planilha_online.xlsx"
PLANILHA_DROPBOX_FILE = (
    Path(os.environ.get("USERPROFILE", "")) / "Dropbox" / "COBRANÇA NEGOCIAÇÃO" / "JACI"
    / "ACORDOS GEAP" / "JACI-PLANILHA DE PRODUÇÃO DE ACORDOS GEAP.xlsx"
)
PLANILHA_SNAPSHOT_FILE = USER_DATA_DIR / "planilha_snapshot.json"
PLANILHA_HISTORICO_FILE = USER_DATA_DIR / "planilha_atualizacoes.log"
USER_AGENT_PADRAO = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# O Global Office amarra a sessão ao User-Agent: as sessões do robô precisam usar
# exatamente o User-Agent do navegador em que o login foi feito (gravado no login).
USER_AGENT_FILE = USER_DATA_DIR / "user_agent.txt"


def obter_user_agent() -> str:
    try:
        ua = USER_AGENT_FILE.read_text(encoding="utf-8").strip()
        if ua:
            return ua
    except Exception:
        pass
    return USER_AGENT_PADRAO


USER_AGENT = USER_AGENT_PADRAO  # compatibilidade com imports antigos

# Webmail Locaweb (envio dos boletos por e-mail). A senha fica só no .env local da máquina.
WEBMAIL_URL = os.getenv("WEBMAIL_URL", "https://webmail-seguro.com.br/")
WEBMAIL_USER = os.getenv("WEBMAIL_USER", "financeiro.accobranca@aldriguescandido.adv.br")
WEBMAIL_PASS = os.getenv("WEBMAIL_PASS", "")
EMAILS_ENVIADOS_FILE = USER_DATA_DIR / "emails_enviados.json"


def _salvar_env_local(valores: dict):
    """Atualiza as chaves no .env local preservando as demais (ex.: login do webmail)."""
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    atuais = {}
    if LOCAL_ENV.exists():
        for linha in LOCAL_ENV.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                k, v = linha.split("=", 1)
                atuais[k.strip()] = v
    atuais.update({k: str(v).strip() for k, v in valores.items()})
    LOCAL_ENV.write_text("".join(f"{k}={v}\n" for k, v in atuais.items()), encoding="utf-8")
    load_dotenv(dotenv_path=LOCAL_ENV, override=True)


def salvar_credenciais_locais(login: str, usuario: str, senha: str):
    """Grava as credenciais do usuário exclusivamente na máquina local dele."""
    global GLOBAL_OFFICE_LOGIN, GLOBAL_OFFICE_USER, GLOBAL_OFFICE_PASS
    _salvar_env_local({
        "GLOBAL_OFFICE_URL": GLOBAL_OFFICE_URL,
        "GLOBAL_OFFICE_LOGIN": login,
        "GLOBAL_OFFICE_USER": usuario,
        "GLOBAL_OFFICE_PASS": senha,
    })
    GLOBAL_OFFICE_LOGIN = login.strip()
    GLOBAL_OFFICE_USER = usuario.strip()
    GLOBAL_OFFICE_PASS = senha.strip()


def salvar_credenciais_webmail(usuario: str, senha: str):
    global WEBMAIL_USER, WEBMAIL_PASS
    _salvar_env_local({"WEBMAIL_USER": usuario, "WEBMAIL_PASS": senha})
    WEBMAIL_USER, WEBMAIL_PASS = usuario.strip(), senha.strip()

def situacao_empresa(page, espera_ms: int = 10000) -> str:
    """Empresa ativa no Global Office, vista pela lista 'Modelo' (#CBXFILTROMODELO) da tela de
    Boletos: 'AC' (tem 'SICOOB- AC'), 'OUTRA' (lista carregada com outros modelos, ex.
    'BB ALDRIGUES') ou 'INDEFINIDO' (lista ainda vazia). Logo após gravar um acordo a lista
    demora a carregar; vazia NÃO significa empresa errada."""
    import time as _t
    fim = _t.time() + espera_ms / 1000
    while True:
        try:
            textos = [" ".join(t.split()) for t in page.evaluate(
                "[...(document.getElementById('CBXFILTROMODELO')||{options:[]}).options].map(o => o.text)")]
        except Exception:
            textos = []
        if any("SICOOB- AC" in t for t in textos):
            return "AC"
        modelos = [t for t in textos if t and "SELECIONE" not in t.upper()]
        if modelos:
            return "OUTRA"
        if _t.time() >= fim:
            return "INDEFINIDO"
        page.wait_for_timeout(500)


# Boletos de meses que já passaram não são baixados nem enviados. A partir deste dia do
# mês, o mês atual também é considerado encerrado e começa-se pelo mês seguinte.
DIA_VIRADA_MES = int(os.getenv("DIA_VIRADA_MES", "25"))
# Boleto avulso cuja data de vencimento deste mês já passou: criado para daqui a N dias.
DIAS_VENCIMENTO_ATRASADO = int(os.getenv("DIAS_VENCIMENTO_ATRASADO", "2"))


def mes_inicial_boletos(hoje=None):
    """(ano, mês) do primeiro boleto que ainda interessa: o mês atual, ou o próximo
    a partir do dia DIA_VIRADA_MES."""
    from datetime import date
    hoje = hoje or date.today()
    if hoje.day >= DIA_VIRADA_MES:
        return (hoje.year + 1, 1) if hoje.month == 12 else (hoje.year, hoje.month + 1)
    return (hoje.year, hoje.month)


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

PASTA_ACORDOS_PADRAO = Path(r"C:\Users\Cob_Geap_05082026\Dropbox\COBRANÇA NEGOCIAÇÃO\ADMINISTRATIVO- COBRANÇA\ACOMPANHAMENTO DE ACORDOS AC COBRANÇA")
PASTA_ACORDOS_JURIDICO = Path(r"C:\Users\Cob_Geap_05082026\Dropbox\COBRANÇA NEGOCIAÇÃO\ADMINISTRATIVO- COBRANÇA\ACOMPANHAMENTO DE ACORDOS - JURÍDICO")

def obter_pasta_boletos_cliente(nome_cliente: str, eh_audiencia: Optional[bool] = None, eh_juridico: Optional[bool] = None) -> Path:
    """
    Localiza ou cria a pasta de destino dos boletos do cliente no Dropbox:
    - O que não for FECHADO AC COBRANÇA: ...\ACOMPANHAMENTO DE ACORDOS - JURÍDICO\<CLIENTE>\BOLETOS DO ACORDO
    - FECHADO AC COBRANÇA: ...\ACOMPANHAMENTO DE ACORDOS AC COBRANÇA\<CLIENTE>\BOLETOS DO ACORDO
    """
    nome_norm = normalizar_texto(nome_cliente)
    nome_pasta_cliente = nome_cliente.strip().upper()

    if eh_juridico is None:
        eh_juridico = eh_audiencia

    # 1. Se for Acordo Jurídico (não FECHADO AC COBRANÇA)
    if eh_juridico is True and PASTA_ACORDOS_JURIDICO.exists():
        pasta_alvo = None
        for p in PASTA_ACORDOS_JURIDICO.iterdir():
            if p.is_dir() and normalizar_texto(p.name) == nome_norm:
                pasta_alvo = p
                break
        if not pasta_alvo:
            pasta_alvo = PASTA_ACORDOS_JURIDICO / nome_pasta_cliente
            pasta_alvo.mkdir(parents=True, exist_ok=True)
        dest = pasta_alvo / "BOLETOS DO ACORDO"
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    # 2. Se for explicitamente AC COBRANÇA
    if eh_juridico is False and PASTA_ACORDOS_PADRAO.exists():
        pasta_alvo = None
        for p in PASTA_ACORDOS_PADRAO.iterdir():
            if p.is_dir() and normalizar_texto(p.name) == nome_norm:
                pasta_alvo = p
                break
        if not pasta_alvo:
            pasta_alvo = PASTA_ACORDOS_PADRAO / nome_pasta_cliente
            pasta_alvo.mkdir(parents=True, exist_ok=True)
        dest = pasta_alvo / "BOLETOS DO ACORDO"
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    # 3. Se eh_audiencia não informado (None): se já existe no JURÍDICO, direciona para lá
    if PASTA_ACORDOS_JURIDICO.exists():
        for p in PASTA_ACORDOS_JURIDICO.iterdir():
            if p.is_dir() and normalizar_texto(p.name) == nome_norm:
                dest = p / "BOLETOS DO ACORDO"
                dest.mkdir(parents=True, exist_ok=True)
                return dest

    # 4. Caminho direto mais comum para agilidade e precisão
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
