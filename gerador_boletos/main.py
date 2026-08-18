import sys
import time
import os
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.environ["LOCALAPPDATA"], "ms-playwright")
from gerador_boletos.logger import log
from gerador_boletos.excel_service import ExcelService
from gerador_boletos.globaloffice_service import GlobalOfficeService
from gerador_boletos.validators import formatar_valor_moeda, formatar_data_vencimento

def iniciar_lote(caminho_planilha=None):
    log.info("="*60)
    log.info("INICIANDO PROCESSAMENTO DE BOLETOS GEAP")
    log.info("="*60)

    try:
        # Se nao passar caminho_planilha, o ExcelService vai pegar do .env
        excel = ExcelService(caminho_planilha) if caminho_planilha else ExcelService()
        excel.carregar()
        registros = excel.listar_registros_elegiveis()
        
        if not registros:
            log.info("Nenhum registro elegível encontrado para processamento.")
            return

        log.info(f"Foram encontrados {len(registros)} registros para processar.")
        
        go_service = GlobalOfficeService()
        go_service.iniciar_sessao(visivel=False) # Rodando invisível
        
        for reg in registros:
            linha = reg['_linha_excel']
            status = reg.get('STATUS_BOLETO')
            
            if status == 'PENDENTE':
                log.info(f"Processando linha {linha}: {reg.get('NOME')}")
                
                # Formata os dados
                valor = formatar_valor_moeda(reg.get('VALOR_PARCELA'))
                vencimento = formatar_data_vencimento(reg.get('VENCIMENTO_BOLETO'))
                
                if not valor or not vencimento:
                    log.error(f"Valores inválidos na linha {linha}. Pulando...")
                    excel.atualizar_celula(linha, 'MENSAGEM_ERRO', "Valor ou Data inválida")
                    continue
                
                # Marca como processando para evitar duplicidade manual
                excel.atualizar_celula(linha, 'STATUS_BOLETO', 'PROCESSANDO')
                excel.salvar()
                
                caminho_pdf = go_service.preencher_e_gerar_boleto(
                    cliente=reg.get('NOME'),
                    valor=valor,
                    vencimento=vencimento,
                    num_processo=reg.get('PROCESSO')
                )
                
                if caminho_pdf:
                    excel.atualizar_celula(linha, 'STATUS_BOLETO', 'GERADO')
                    excel.atualizar_celula(linha, 'CAMINHO_PDF', caminho_pdf)
                    excel.atualizar_celula(linha, 'DATA_PROCESSAMENTO', time.strftime("%d/%m/%Y %H:%M:%S"))
                    excel.salvar()
                else:
                    excel.atualizar_celula(linha, 'STATUS_BOLETO', 'ERRO')
                    excel.atualizar_celula(linha, 'MENSAGEM_ERRO', "Falha ao gerar/baixar boleto")
                    excel.salvar()
        
        log.info("Processamento finalizado com sucesso.")
        go_service.fechar_sessao()
        
    except Exception as e:
        log.exception(f"Erro fatal durante a execução do lote: {e}")

if __name__ == "__main__":
    iniciar_lote()
