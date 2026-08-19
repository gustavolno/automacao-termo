from decimal import Decimal, ROUND_HALF_UP

class CalculationService:
    @staticmethod
    def calculate_balance(termo_dados: dict, comprovantes_paths: list) -> dict:
        """
        Recebe os dados extraídos do Termo e a lista de comprovantes.
        Retorna um dicionário com o financeiro consolidado em Decimal.
        """
        if not termo_dados:
            return {}
            
        valor_homologado = Decimal(str(termo_dados.get("valor_homologado") or 0.0))
        parcelas_qtd_original = int(termo_dados.get("parcelas_qtd") or 0)
        valor_parcela = Decimal(str(termo_dados.get("parcelas_valor") or 0.0))
        valor_entrada = Decimal(str(termo_dados.get("entrada_valor") or 0.0))
        
        # Heurística para contar comprovantes pagos
        qtd_comprovantes_entrada = 0
        qtd_comprovantes_parcelas = 0
        
        for path in comprovantes_paths:
            nome = path.upper()
            if "ENTRADA" in nome:
                qtd_comprovantes_entrada += 1
            elif "BOLETO" not in nome: # Se tem BOLETO no nome e não tem RECIBO/COMPROVANTE, pode ser só emissão. Assumindo COMP DE PAG como pago.
                qtd_comprovantes_parcelas += 1
                
        # Total pago
        total_pago = Decimal("0.00")
        total_pago += Decimal(qtd_comprovantes_entrada) * valor_entrada
        total_pago += Decimal(qtd_comprovantes_parcelas) * valor_parcela
        
        # Saldo Restante
        saldo_restante = valor_homologado - total_pago
        
        # Parcelas Restantes
        # Se a entrada contava como parcela, a qtd original de parcelas normais é qtd_original - 1
        parcelas_normais_originais = parcelas_qtd_original
        if termo_dados.get("entrada_conta_como_parcela"):
            parcelas_normais_originais -= 1
            
        parcelas_restantes = parcelas_normais_originais - qtd_comprovantes_parcelas
        
        # Prevê erros onde o saldo fica negativo
        if saldo_restante < 0:
            saldo_restante = Decimal("0.00")
        if parcelas_restantes < 0:
            parcelas_restantes = 0
            
        return {
            "valor_homologado": f"R$ {valor_homologado:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "parcelas_originais": parcelas_qtd_original,
            "total_pago": f"R$ {total_pago:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "parcelas_pagas": qtd_comprovantes_parcelas,
            "saldo_restante": f"R$ {saldo_restante:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            "parcelas_restantes": parcelas_restantes,
            "valor_parcela": f"R$ {valor_parcela:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
            # Formatação raw (float) caso precise jogar no input do browser no playwright
            "raw_saldo_restante": float(saldo_restante),
            "raw_parcelas_restantes": int(parcelas_restantes),
            "raw_valor_parcela": float(valor_parcela)
        }

if __name__ == "__main__":
    # Teste mock com dados do Alaor
    mock_termo = {
        'valor_homologado': 22219.22, 
        'parcelas_qtd': 24, 
        'parcelas_valor': 820.41, 
        'entrada_valor': 2529.38, 
        'entrada_conta_como_parcela': False, 
        'divergencia_matematica': True, 
        'diferenca_calculada': 2529.38
    }
    
    # Simula 10 comprovantes de parcela e 1 de entrada encontrados no Dropbox
    mock_comprovantes = ["COMP PAG ENTRADA.pdf"] + [f"COMP PAG MÊS {i}.pdf" for i in range(1, 11)]
    
    calc = CalculationService.calculate_balance(mock_termo, mock_comprovantes)
    print("Resultado Calculado:")
    for k, v in calc.items():
        print(f"{k}: {v}")
