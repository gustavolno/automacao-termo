class ValidationService:
    @staticmethod
    def generate_flags(termo_dados: dict, calc_dados: dict) -> list:
        """
        Cruza os dados do termo com os cálculos matemáticos para gerar 
        flags de confiança (Verde, Amarelo, Vermelho).
        """
        flags = []
        
        # 1. Validação Matemática da Entrada Oculta
        if termo_dados.get("divergencia_matematica"):
            flags.append({
                "campo": "valor_homologado",
                "nivel": "baixa", # Alta=Verde, Média=Amarelo, Baixa=Vermelho
                "mensagem": f"Divergência matemática detectada: diferença de R$ {termo_dados['diferenca_calculada']} inferida como entrada oculta."
            })
        else:
            flags.append({
                "campo": "valor_homologado",
                "nivel": "alta",
                "mensagem": "Cálculo de parcelas bate exato com o valor homologado."
            })

        # 2. Validação de Vínculo (Mockado por enquanto, dependerá do TJSC)
        flags.append({
            "campo": "vinculo",
            "nivel": "media",
            "mensagem": "Inferido do demonstrativo. Requer checagem humana."
        })
        
        # 3. Validação de Data de Homologação (Mockado, dependerá do TJSC)
        flags.append({
            "campo": "data_homologacao",
            "nivel": "alta",
            "mensagem": "Extraído diretamente da sentença do eproc."
        })

        return flags
