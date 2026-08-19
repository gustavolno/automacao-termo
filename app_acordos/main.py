from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import os

app = FastAPI(title="Gerador de Acordos Robusto - Aldrigues Cândido Advocacia")

# Configurar diretórios
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
static_dir = os.path.join(BASE_DIR, "ui", "static")
templates_dir = os.path.join(BASE_DIR, "ui", "templates")

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)

import os
from services.excel_service import load_clientes_pendentes

EXCEL_PATH = os.path.abspath(os.path.join(BASE_DIR, "..", "..", "automacoes-aldrigues", "PLANILHA DE CONTROLE - COMISSIONAMENTO.xlsx"))

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    clientes_pendentes = load_clientes_pendentes(EXCEL_PATH)
    return templates.TemplateResponse(request=request, name="dashboard.html", context={"clientes": clientes_pendentes})

from services.dropbox_service import DropboxService
from services.document_service import DocumentService
from services.calculation_service import CalculationService

@app.get('/processar/{cliente_id}', response_class=HTMLResponse)
async def processar_cliente(request: Request, cliente_id: int):
    # 1. Obter os dados do Excel
    clientes = load_clientes_pendentes(EXCEL_PATH)
    cliente = next((c for c in clientes if c["id"] == cliente_id), None)
    if not cliente:
        return HTMLResponse("Cliente não encontrado na planilha.", status_code=404)
        
    # 2. Localizar no Dropbox
    folder_path = DropboxService.locate_client_folder(cliente["nome"], cliente["cpf"])
    docs = DropboxService.list_client_documents(folder_path) if folder_path else {}
    
    # 3. Extrair Termo
    termo_dados = {}
    if docs.get("termo"):
        texto_termo = DocumentService.extract_text_from_pdf(docs["termo"])
        termo_dados = DocumentService.parse_termo_acordo(texto_termo)
        
    # 4. Calcular Saldo
    calc_dados = CalculationService.calculate_balance(termo_dados, docs.get("comprovantes", []))
    
    # 5. Montar payload para a tela de revisão
    dados_reais = {
        'cliente': {
            'nome': cliente["nome"], 
            'cpf': cliente["cpf"], 
            'processo': cliente["processo"], 
            'uf': cliente["uf"]
        },
        'acordo': {
            'valor_homologado': calc_dados.get("valor_homologado", "Não encontrado"), 
            'data_homologacao': 'Pendente (Ainda não conectado ao TJ)'
        },
        'financeiro': {
            'valor_negociado': calc_dados.get("valor_homologado", "R$ 0,00"), 
            'parcelas_originais': calc_dados.get("parcelas_originais", 0), 
            'total_pago': calc_dados.get("total_pago", "R$ 0,00"), 
            'parcelas_pagas': calc_dados.get("parcelas_pagas", 0), 
            'saldo_restante': calc_dados.get("saldo_restante", "R$ 0,00"), 
            'parcelas_restantes': calc_dados.get("parcelas_restantes", 0), 
            'valor_parcela': calc_dados.get("valor_parcela", "R$ 0,00"), 
            'proximo_vencimento': 'A Calcular...'
        }
    }
    
    return templates.TemplateResponse(request=request, name="review.html", context={'dados': dados_reais})

from pydantic import BaseModel
from services.globaloffice_service import GlobalOfficeService, GlobalOfficeBlockedException

class RoboPayload(BaseModel):
    cliente_nome: str
    financeiro: dict

@app.post('/executar_robo')
async def executar_robo(payload: RoboPayload):
    try:
        dados = {
            "cliente": {"nome": payload.cliente_nome},
            "financeiro": payload.financeiro
        }
        # Inicia a automação async no navegador
        await GlobalOfficeService.preencher_acordo(dados)
        return {"status": "sucesso", "mensagem": "Robô finalizou o preenchimento no Global Office."}
    except GlobalOfficeBlockedException as e:
        return {"status": "erro", "mensagem": str(e)}
    except Exception as e:
        return {"status": "erro", "mensagem": f"Erro interno: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
