"""
Classe base para todos os adaptadores de Tribunal.
Todo adaptador concreto (pje_adapter, eproc_adapter, etc) DEVE herdar desta classe.
"""
from abc import ABC, abstractmethod
import os

class TribunalAdapter(ABC):
    def __init__(self, page, tribunal_info: dict, pasta_cliente: str):
        """
        :param page: Página do Playwright já aberta (logada com o certificado).
        :param tribunal_info: Dicionário com nome, sistema, url_base do tribunal.
        :param pasta_cliente: Pasta local do cliente no Dropbox para salvar os downloads.
        """
        self.page = page
        self.tribunal_info = tribunal_info
        self.pasta_cliente = pasta_cliente

    @abstractmethod
    async def consultar_processo(self, numero_processo: str) -> bool:
        """
        Navega até a tela de consulta e abre o processo.
        Retorna True se encontrou o processo, False se não encontrou.
        """
        pass

    @abstractmethod
    async def encontrar_sentenca_homologacao(self) -> dict:
        """
        Dentro do processo aberto, filtra as movimentações por "sentença"
        ou termos equivalentes e localiza a data de homologação.
        Retorna: {"data": "DD/MM/AAAA", "id_documento": "...", "encontrado": True/False}
        """
        pass

    @abstractmethod
    async def baixar_sentenca(self, id_documento: str, numero_processo: str) -> str:
        """
        Faz download do PDF da sentença e salva na pasta do cliente.
        Retorna o caminho local do arquivo baixado.
        """
        pass

    async def executar_pipeline(self, numero_processo: str) -> dict:
        """
        Executa o pipeline completo: consultar → encontrar sentença → baixar.
        Retorna um dicionário com o resultado completo.
        """
        resultado = {
            "tribunal": self.tribunal_info.get("nome"),
            "numero_processo": numero_processo,
            "encontrou_processo": False,
            "data_homologacao": None,
            "arquivo_baixado": None,
            "erro": None
        }
        try:
            encontrou = await self.consultar_processo(numero_processo)
            resultado["encontrou_processo"] = encontrou
            if not encontrou:
                resultado["erro"] = "Processo não encontrado no tribunal."
                return resultado

            sentenca_info = await self.encontrar_sentenca_homologacao()
            if not sentenca_info.get("encontrado"):
                resultado["erro"] = "Sentença/Homologação não localizada nas movimentações."
                return resultado

            resultado["data_homologacao"] = sentenca_info.get("data")
            caminho_arquivo = await self.baixar_sentenca(
                sentenca_info.get("id_documento"), numero_processo
            )
            resultado["arquivo_baixado"] = caminho_arquivo

        except Exception as e:
            resultado["erro"] = str(e)

        return resultado
