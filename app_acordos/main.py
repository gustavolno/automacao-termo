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
from tribunais.orquestrador import consultar_tribunal

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
    
    # 5. Gerar Flags de Validação
    flags_list = ValidationService.generate_flags(termo_dados, calc_dados)
    flags = {f['campo']: f for f in flags_list}
    
    # 6. Montar payload para a tela de revisão
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
        },
        'docs': docs, # Passa os documentos para linkar no front-end
        'flags': flags
    }
    
    return templates.TemplateResponse(request=request, name="review.html", context={'dados': dados_reais})

from fastapi.responses import HTMLResponse, FileResponse
from fastapi.background import BackgroundTasks
from pydantic import BaseModel
import urllib.parse
from services.globaloffice_service import GlobalOfficeService, GlobalOfficeBlockedException
from services.validation_service import ValidationService
from services.audit_service import AuditService

@app.get('/abrir_documento')
async def abrir_documento(caminho: str):
    """
    Serve um documento local diretamente no navegador.
    O caminho deve ser absoluto.
    """
    caminho_decodificado = urllib.parse.unquote(caminho)
    if os.path.exists(caminho_decodificado):
        return FileResponse(caminho_decodificado)
    return HTMLResponse("Arquivo não encontrado no disco local.", status_code=404)


class TribunalPayload(BaseModel):
    numero_processo: str
    pasta_cliente: str

@app.post('/consultar_tj')
async def consultar_tj(payload: TribunalPayload):
    """
    Aciona o robô de busca no Tribunal correspondente ao processo.
    O robô vai abrir o navegador, aguardar o login com Certificado + MFA,
    localizar a sentença de homologação e baixar o PDF na pasta do cliente.
    """
    try:
        AuditService.log_action(payload.numero_processo, "CONSULTA_TJ_INICIADA")
        resultado = await consultar_tribunal(
            numero_processo=payload.numero_processo,
            pasta_cliente=payload.pasta_cliente
        )
        if resultado.get("erro"):
            AuditService.log_action(payload.numero_processo, "CONSULTA_TJ_ERRO", resultado, "ERRO")
        else:
            AuditService.log_action(payload.numero_processo, "CONSULTA_TJ_SUCESSO", resultado)
        return resultado
    except Exception as e:
        AuditService.log_action(payload.numero_processo, "CONSULTA_TJ_EXCECAO", {"erro": str(e)}, "ERRO")
        return {"erro": str(e)}



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
        
        AuditService.log_action(payload.cliente_nome, "INICIANDO_GLOBAL_OFFICE")
        
        # Inicia a automação async no navegador
        await GlobalOfficeService.preencher_acordo(dados)
        
        AuditService.log_action(payload.cliente_nome, "SUCESSO_GLOBAL_OFFICE", dados)
        return {"status": "sucesso", "mensagem": "Robô finalizou o preenchimento no Global Office."}
    except GlobalOfficeBlockedException as e:
        AuditService.log_action(payload.cliente_nome, "ERRO_BLOQUEADO_TI", {"erro": str(e)}, "ERRO")
        return {"status": "erro", "mensagem": str(e)}
    except Exception as e:
        AuditService.log_action(payload.cliente_nome, "ERRO_DESCONHECIDO", {"erro": str(e)}, "ERRO")
        return {"status": "erro", "mensagem": f"Erro interno: {str(e)}"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
