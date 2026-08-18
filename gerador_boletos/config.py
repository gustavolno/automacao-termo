import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env localizado na mesma pasta
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

# Credenciais Global Office
GLOBAL_OFFICE_LOGIN = os.getenv('GLOBAL_OFFICE_LOGIN')
GLOBAL_OFFICE_USER = os.getenv('GLOBAL_OFFICE_USER')
GLOBAL_OFFICE_PASS = os.getenv('GLOBAL_OFFICE_PASS')

# Credenciais E-mail
EMAIL_SMTP_HOST = os.getenv('EMAIL_SMTP_HOST', 'email-ssl.com.br')
EMAIL_SMTP_PORT = int(os.getenv('EMAIL_SMTP_PORT', '465'))
EMAIL_USER = os.getenv('EMAIL_USER')
EMAIL_PASS = os.getenv('EMAIL_PASS')

# Configurações do Global Office
GLOBAL_OFFICE_ESCRITORIO = os.getenv('GLOBAL_OFFICE_ESCRITORIO', 'Unidade Brasília')
GLOBAL_OFFICE_MODELO = os.getenv('GLOBAL_OFFICE_MODELO', 'SICOOB-AC')
GLOBAL_OFFICE_PADRAO_RECEITAS = os.getenv('GLOBAL_OFFICE_PADRAO_RECEITAS', 'Honorario_dentro')
GLOBAL_OFFICE_ITEM_VENDA = os.getenv('GLOBAL_OFFICE_ITEM_VENDA', 'Prestação de serviço de cobrança/ tecnológico')

# Caminhos
PLANILHA_ENTRADA = os.getenv('PLANILHA_ENTRADA', 'planilha_teste_automacao_boletos.xlsx')
PASTA_BOLETOS = os.getenv('PASTA_BOLETOS', r'C:\AutomacaoBoletos\BoletosGerados')
PASTA_LOGS = os.getenv('PASTA_LOGS', r'C:\AutomacaoBoletos\Logs')
PASTA_ERROS = os.getenv('PASTA_ERROS', r'C:\AutomacaoBoletos\Erros')

# Garante que os diretórios existam
Path(PASTA_BOLETOS).mkdir(parents=True, exist_ok=True)
Path(PASTA_LOGS).mkdir(parents=True, exist_ok=True)
Path(PASTA_ERROS).mkdir(parents=True, exist_ok=True)
