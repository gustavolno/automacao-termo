"""
Adaptador eSAJ - Usado pelo TJSP (São Paulo) e alguns outros TJs da Softplan.
O eSAJ tem fluxo diferente do PJe: usa consulta via CPF ou número de processo,
e as movimentações ficam em uma aba específica.
"""
import os
import re
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from .base import TribunalAdapter

PALAVRAS_HOMOLOGACAO = [
    "Homologado o acordo",
    "Homologada a transação",
    "Sentença - Homologação",
    "Sentença homologatória",
    "Julgado procedente - Homologação",
]


class EsajAdapter(TribunalAdapter):
    
    async def consultar_processo(self, numero_processo: str) -> bool:
        # eSAJ TJSP usa URL de consulta pública
        url_consulta = f"{self.tribunal_info['url_base']}/cpo/sg/open.do"
        print(f"[eSAJ] Acessando: {url_consulta}")
        
        await self.page.goto(url_consulta, wait_until="networkidle", timeout=30000)
        
        # Campo de número do processo no eSAJ
        seletores_campo = [
            "input[name='numeroDigitoAnoUnificado']",
            "input[id*='numeroProcesso']",
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
            raise Exception("Campo de busca não encontrado no eSAJ/TJSP.")
        
        # O eSAJ divide o número em campos separados, então preenchemos o principal
        await campo.fill(numero_processo.split("-")[0])  # primeiros 7 dígitos
        
        # Botão de pesquisa
        try:
            btn = await self.page.wait_for_selector(
                "button:has-text('Pesquisar'), input[value='Pesquisar']", timeout=5000
            )
            await btn.click()
        except PlaywrightTimeoutError:
            await self.page.keyboard.press("Enter")
        
        await self.page.wait_for_load_state("networkidle", timeout=20000)
        
        try:
            # No eSAJ, o processo aparece como link clicável
            link = await self.page.wait_for_selector("a.linkProcesso, a[class*='processo']", timeout=8000)
            await link.click()
            await self.page.wait_for_load_state("networkidle", timeout=20000)
            return True
        except PlaywrightTimeoutError:
            return False

    async def encontrar_sentenca_homologacao(self) -> dict:
        """O eSAJ exibe movimentações numa lista com datas e títulos."""
        # Tenta acessar aba de movimentações
        try:
            aba_mov = await self.page.wait_for_selector(
                "a:has-text('Movimentações'), a:has-text('Andamentos'), a[id*='movimentacoes']",
                timeout=5000
            )
            await aba_mov.click()
            await self.page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            pass
        
        for palavra in PALAVRAS_HOMOLOGACAO:
            try:
                el = await self.page.wait_for_selector(f"text='{palavra}'", timeout=3000)
                if el:
                    data_texto = await self.page.evaluate("""
                        (el) => {
                            const row = el.closest('tr, .movimentacao');
                            if (!row) return null;
                            const data_el = row.querySelector('.dataMovimento, td:first-child');
                            return data_el ? data_el.textContent.trim() : null;
                        }
                    """, el)
                    
                    return {
                        "encontrado": True,
                        "data": self._extrair_data(data_texto or ""),
                        "palavra_chave": palavra,
                        "id_documento": None  # eSAJ raramente tem PDF direto na movimentação
                    }
            except PlaywrightTimeoutError:
                continue
        
        return {"encontrado": False}

    async def baixar_sentenca(self, id_documento: str, numero_processo: str) -> str:
        """No eSAJ o PDF geralmente fica na aba 'Documentos' ou 'Petições'."""
        if not os.path.exists(self.pasta_cliente):
            os.makedirs(self.pasta_cliente)
        
        nome_arquivo = f"SENTENCA_HOMOLOGACAO_{numero_processo.replace('-', '').replace('.', '')}.pdf"
        caminho_destino = os.path.join(self.pasta_cliente, nome_arquivo)
        
        # Navega para a aba de documentos
        try:
            aba_docs = await self.page.wait_for_selector(
                "a:has-text('Documentos'), a:has-text('Petições')", timeout=5000
            )
            await aba_docs.click()
            await self.page.wait_for_timeout(2000)
        except PlaywrightTimeoutError:
            pass
        
        # Busca pelo link de sentença na lista de documentos
        try:
            async with self.page.expect_download() as download_info:
                sentenca_link = await self.page.wait_for_selector(
                    "a:has-text('Sentença'), a:has-text('Homolog')", timeout=5000
                )
                await sentenca_link.click()
            
            download = await download_info.value
            await download.save_as(caminho_destino)
            print(f"[eSAJ] Arquivo salvo em: {caminho_destino}")
            return caminho_destino
        except Exception as e:
            raise Exception(f"Não foi possível fazer download no eSAJ: {e}")

    def _extrair_data(self, texto: str) -> str:
        match = re.search(r'(\d{2}/\d{2}/\d{4})', texto)
        return match.group(1) if match else "Data não encontrada"
