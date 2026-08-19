import fitz  # PyMuPDF
import re
import os

class DocumentService:
    @staticmethod
    def extract_text_from_pdf(pdf_path: str) -> str:
        """Extrai todo o texto de um PDF usando PyMuPDF."""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {pdf_path}")
            
        text = ""
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                text += page.get_text("text") + "\n"
            doc.close()
        except Exception as e:
            print(f"Erro ao extrair texto do PDF {pdf_path}: {e}")
            
        return text

    @staticmethod
    def parse_termo_acordo(text: str) -> dict:
        """
        Analisa o texto do Termo de Acordo/Audiência e tenta extrair os valores.
        """
        dados = {
            "valor_homologado": None,
            "parcelas_qtd": None,
            "parcelas_valor": None,
            "entrada_valor": None,
            "entrada_conta_como_parcela": False,
            "divergencia_matematica": False,
            "diferenca_calculada": 0.0
        }
        
        text_lower = text.lower()
        
        # 1. Procurar valor homologado (ex: "R$ 22.219,22")
        match_valor = re.search(r"r\$\s*([\d\.]+,\d{2})", text_lower)
        if match_valor:
            val_str = match_valor.group(1).replace(".", "").replace(",", ".")
            dados["valor_homologado"] = float(val_str)
        
        # 2. Procurar parcelas (ex: "24 prestações", "10 parcelas")
        match_qtd = re.search(r"(\d+)\s*(?:prestações|parcelas)", text_lower)
        if match_qtd:
            dados["parcelas_qtd"] = int(match_qtd.group(1))
            
        # 3. Procurar valor da parcela (ex: "valor de R$ R$ 820,41" ou "R$ 820,41")
        # O PDF de exemplo do Alaor tem um erro de digitação duplo: "R$ R$ 820,41"
        match_val_parc = re.search(r"(?:prestações|parcelas)[^\d]*r\$\s*(?:r\$\s*)?([\d\.]+,\d{2})", text_lower)
        if match_val_parc:
            val_parc_str = match_val_parc.group(1).replace(".", "").replace(",", ".")
            dados["parcelas_valor"] = float(val_parc_str)

        # 4. Checagem Matemática de Pegadinha
        if dados["valor_homologado"] and dados["parcelas_qtd"] and dados["parcelas_valor"]:
            total_parcelado = round(dados["parcelas_qtd"] * dados["parcelas_valor"], 2)
            if abs(dados["valor_homologado"] - total_parcelado) > 0.50: # Tolerância de centavos
                dados["divergencia_matematica"] = True
                dados["diferenca_calculada"] = round(dados["valor_homologado"] - total_parcelado, 2)
                # Inferir que a diferença é a entrada que não foi explicitada (caso do Alaor)
                if dados["diferenca_calculada"] > 0:
                    dados["entrada_valor"] = dados["diferenca_calculada"]

        # 5. Detectar pegadinha textual da entrada
        if "entrada" in text_lower and ("parcelas" in text_lower or "prestações" in text_lower):
            if "sendo a primeira" in text_lower or "1ª parcela a título de entrada" in text_lower:
                dados["entrada_conta_como_parcela"] = True

        return dados

# Exemplo de uso local para testes
if __name__ == "__main__":
    # Teste isolado com o texto do Alaor
    sample = "A parte requerida compromete-se ao pagamento da quantia de R$ 22.219,22, dividida em 24 prestações no valor de R$ R$ 820,41 reais."
    print(DocumentService.parse_termo_acordo(sample))
