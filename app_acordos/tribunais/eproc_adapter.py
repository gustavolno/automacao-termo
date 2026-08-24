"""
Adaptador eProc - Usado por TJSC, TJMG, TJRS e TRFs.
Fluxo eProc é diferente do PJe: tem busca por localizadores e interface própria.
"""
import os
import re
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from .base import TribunalAdapter

PALAVRAS_HOMOLOGACAO = [
    "Homologada a Transação",
    "Homologado o Acordo",
    "Sentença Homologatória",
    "Homologação de Acordo",
    "Acordo Homologado",
]


class EprocAdapter(TribunalAdapter):
    
    async def consultar_processo(self, numero_processo: str) -> bool:
        url_busca = f"{self.tribunal_info['url_base']}/eproc/externo_controlador.php?acao=processo_selecionar"
        print(f"[eProc] Acessando: {url_busca}")
        
        await self.page.goto(url_busca, wait_until="networkidle", timeout=30000)
        
        # O eProc tem um campo de busca no topo
        seletores_campo = [
            "input[name='txtNumProcesso']",
            "input[id='txtNumProcesso']",
            "input[placeholder*='processo']",
        ]
        
        campo = None
        for seletor in seletores_campo:
            try:
                campo = await self.page.wait_for_selector(seletor, timeout=5000)
                if campo:
                    break
            except PlaywrightTimeoutError:
                continue
        
        if not campo:
            raise Exception("Campo de número do processo não encontrado no eProc.")
        
        await campo.fill(numero_processo)
        await self.page.keyboard.press("Enter")
        await self.page.wait_for_load_state("networkidle", timeout=20000)
        
        # Verifica se o processo foi aberto (eProc mostra o cabeçalho do processo)
        try:
            await self.page.wait_for_selector("span[class*='processo-numero'], #divCabecalhoProcesso", timeout=8000)
            return True
        except PlaywrightTimeoutError:
            return False

    async def encontrar_sentenca_homologacao(self) -> dict:
        """No eProc, a linha do tempo fica em uma aba 'Eventos' ou 'Movimentações'."""
        # Clica na aba de eventos/movimentações se existir
        try:
            aba_eventos = await self.page.wait_for_selector(
                "a:has-text('Eventos'), a:has-text('Movimentações'), a[id*='eventos']",
                timeout=5000
            )
            await aba_eventos.click()
            await self.page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            pass  # Pode já estar visível
        
        # Procura pelas palavras de homologação
        for palavra in PALAVRAS_HOMOLOGACAO:
            try:
                elemento = await self.page.wait_for_selector(f"text='{palavra}'", timeout=3000)
                if elemento:
                    # No eProc a data fica na coluna anterior
                    data_texto = await self.page.evaluate("""
                        (el) => {
                            const linha = el.closest('tr');
                            if (!linha) return null;
                            const cells = linha.querySelectorAll('td');
                            return cells[0] ? cells[0].textContent.trim() : null;
                        }
                    """, elemento)
                    
                    link_doc = await self.page.evaluate("""
                        (el) => {
                            const linha = el.closest('tr');
                            if (!linha) return null;
                            const link = linha.querySelector('a');
                            return link ? link.getAttribute('href') : null;
                        }
                    """, elemento)
                    
                    return {
                        "encontrado": True,
                        "data": self._extrair_data(data_texto or ""),
                        "palavra_chave": palavra,
                        "id_documento": link_doc
                    }
            except PlaywrightTimeoutError:
                continue
        
        return {"encontrado": False}

    async def baixar_sentenca(self, id_documento: str, numero_processo: str) -> str:
        if not os.path.exists(self.pasta_cliente):
            os.makedirs(self.pasta_cliente)
        
        nome_arquivo = f"SENTENCA_HOMOLOGACAO_{numero_processo.replace('-', '').replace('.', '')}.pdf"
        caminho_destino = os.path.join(self.pasta_cliente, nome_arquivo)
        
        async with self.page.expect_download() as download_info:
            if id_documento:
                await self.page.goto(id_documento, timeout=15000)
        
        download = await download_info.value
        await download.save_as(caminho_destino)
        print(f"[eProc] Arquivo salvo em: {caminho_destino}")
        return caminho_destino

    def _extrair_data(self, texto: str) -> str:
        match = re.search(r'(\d{2}/\d{2}/\d{4})', texto)
        return match.group(1) if match else "Data não encontrada"
