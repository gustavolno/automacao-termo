import os
import glob
from pathlib import Path

# Caminho base do Dropbox (pode ser movido para .env futuramente)
DROPBOX_BASE_PATH = r"C:\Users\Gustavo\Dropbox\COBRANÇA NEGOCIAÇÃO\ADMINISTRATIVO- COBRANÇA\ACOMPANHAMENTO DE ACORDOS FECHADOS"

class DropboxService:
    @staticmethod
    def locate_client_folder(nome_cliente: str, cpf: str = None) -> str:
        """
        Busca a pasta do cliente no Dropbox baseando-se no nome ou CPF.
        Retorna o caminho absoluto da pasta, ou None se não encontrar.
        """
        if not os.path.exists(DROPBOX_BASE_PATH):
            print("Aviso: Caminho base do Dropbox não existe na máquina local.")
            return None
            
        nome_busca = nome_cliente.strip().upper()
        
        # Estratégia simples: iterar sobre as pastas e verificar se o nome do cliente está contido no nome da pasta
        for item in os.listdir(DROPBOX_BASE_PATH):
            item_path = os.path.join(DROPBOX_BASE_PATH, item)
            if os.path.isdir(item_path):
                nome_pasta = item.upper()
                if nome_busca in nome_pasta or (cpf and cpf in nome_pasta):
                    return item_path
                    
        return None

    @staticmethod
    def list_client_documents(folder_path: str) -> dict:
        """
        Lista e categoriza os documentos encontrados na pasta do cliente.
        """
        documentos = {
            "termo": None,
            "demonstrativo": None,
            "comprovantes": [],
            "homologacao": None,
            "outros": []
        }
        
        if not folder_path or not os.path.exists(folder_path):
            return documentos
            
        # Busca recursivamente todos os PDFs na pasta do cliente
        pdfs = glob.glob(os.path.join(folder_path, "**", "*.pdf"), recursive=True)
        
        for pdf in pdfs:
            nome_arquivo = os.path.basename(pdf).upper()
            
            if "TERMO DE AUDIÊNCIA" in nome_arquivo or "TERMO DE ACORDO" in nome_arquivo or "TERMO DE COMPROMISSO" in nome_arquivo:
                documentos["termo"] = pdf
            elif "DEMONSTRATIVO" in nome_arquivo or "CÁLCULO" in nome_arquivo:
                documentos["demonstrativo"] = pdf
            elif "COMP" in nome_arquivo or "PAG" in nome_arquivo or "BOLETO" in nome_arquivo or "RECIBO" in nome_arquivo:
                documentos["comprovantes"].append(pdf)
            elif "HOMOLOG" in nome_arquivo or "SENTENÇA" in nome_arquivo:
                documentos["homologacao"] = pdf
            else:
                documentos["outros"].append(pdf)
                
        return documentos

if __name__ == "__main__":
    # Teste isolado local
    folder = DropboxService.locate_client_folder("ALAOR MARCOS DE SOUZA")
    if folder:
        print(f"Pasta encontrada: {folder}")
        docs = DropboxService.list_client_documents(folder)
        print("Documentos Categorizados:")
        for k, v in docs.items():
            if isinstance(v, list):
                print(f" - {k.upper()}: {len(v)} arquivo(s)")
            else:
                print(f" - {k.upper()}: {v}")
    else:
        print("Pasta não encontrada.")
