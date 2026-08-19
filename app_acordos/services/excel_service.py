import openpyxl
import os

def load_clientes_pendentes(excel_path: str):
    """Lê a planilha de controle e retorna uma lista de dicionários de clientes pendentes."""
    if not os.path.exists(excel_path):
        print(f"Erro: Arquivo {excel_path} não encontrado.")
        return []

    try:
        wb = openpyxl.load_workbook(excel_path, data_only=True)
        sheet = wb.active
        
        # Mapeando cabeçalhos para encontrar os índices
        headers = [str(cell.value).strip() if cell.value else "" for cell in sheet[1]]
        
        colunas = {
            "UF": headers.index("UF") if "UF" in headers else -1,
            "NOME": headers.index("BENEFICIÁRIO") if "BENEFICIÁRIO" in headers else -1,
            "CPF": headers.index("CPF") if "CPF" in headers else -1,
            "PROCESSO": headers.index("PROCESSO") if "PROCESSO" in headers else -1,
            "ACORDO": headers.index("VALOR INTEGRAL DO ACORDO") if "VALOR INTEGRAL DO ACORDO" in headers else -1
        }
        
        clientes = []
        for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            nome = row[colunas["NOME"]] if colunas["NOME"] != -1 else None
            
            # Se não tem nome, ignora
            if not nome:
                continue
                
            cpf = row[colunas["CPF"]] if colunas["CPF"] != -1 else ""
            processo = row[colunas["PROCESSO"]] if colunas["PROCESSO"] != -1 else ""
            uf = row[colunas["UF"]] if colunas["UF"] != -1 else ""
            
            # Formatação básica de strings
            nome = str(nome).strip().upper()
            cpf = str(cpf).strip() if cpf else "NÃO INFORMADO"
            processo = str(processo).strip() if processo else "NÃO INFORMADO"
            uf = str(uf).strip().upper() if uf else ""
            
            clientes.append({
                "id": row_idx,
                "nome": nome,
                "cpf": cpf,
                "processo": processo,
                "uf": uf,
                "status": "PENDENTE"
            })
            
        return clientes
    except Exception as e:
        print(f"Erro ao ler planilha: {e}")
        return []

if __name__ == "__main__":
    c = load_clientes_pendentes("../PLANILHA DE CONTROLE - COMISSIONAMENTO.xlsx")
    print(f"Carregados {len(c)} clientes.")
