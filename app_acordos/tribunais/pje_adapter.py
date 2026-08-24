"""
Adaptador PJe - Funciona para a maioria dos TJs brasileiros.
Testado e ajustado com base no fluxo do TJDFT (Print fornecido pelo usuário).

Fluxo:
1. Acessa {url_base}/pje/Processo/ConsultaProcesso/listView.seam
2. Pesquisa pelo número do processo
3. Clica no link do processo
4. Filtra movimentações por "sentença" na barra lateral
5. Localiza entrada "HOMOLOGADA A TRANSAÇÃO" ou equivalente
6. Clica no documento e faz download do PDF
"""

import os
import re
from datetime import datetime
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from .base import TribunalAdapter

# Palavras-chave para identificar a movimentação correta de homologação
PALAVRAS_HOMOLOGACAO = [
    "HOMOLOGADA A TRANSAÇÃO",
    "HOMOLOGADO O ACORDO",
    "HOMOLOGA O ACORDO",
    "SENTENÇA HOMOLOGATÓRIA",
    "HOMOLOGAÇÃO DE ACORDO",
    "HOMOLOGA A TRANSAÇÃO",
    "ACORDO HOMOLOGADO",
    "CUMPRIMENTO DE SENTENÇA",  # fallback: sentença de cumprimento de acordo
]

# Palavras de busca na barra de filtro das movimentações
FILTROS_BUSCA = ["sentença", "homologa", "acordo"]


class PjeAdapter(TribunalAdapter):
    
    async def consultar_processo(self, numero_processo: str) -> bool:
        """Navega para a tela de consulta do PJe e busca pelo número do processo."""
        url_consulta = f"{self.tribunal_info['url_base']}/pje/Processo/ConsultaProcesso/listView.seam"
        print(f"[PJe] Acessando: {url_consulta}")
        
        await self.page.goto(url_consulta, wait_until="networkidle", timeout=30000)
        
        # Localiza o campo de número do processo
        # No PJe padrão, o campo tem o ID 'fPP:numProcesso:numProcesso' ou similar
        seletores_campo = [
            "input[id*='numProcesso']",
            "input[name*='numProcesso']",
            "input[placeholder*='número']",
            "input[placeholder*='Processo']",
        ]
        
        campo_numero = None
        for seletor in seletores_campo:
            try:
                campo_numero = await self.page.wait_for_selector(seletor, timeout=5000)
                if campo_numero:
                    break
            except PlaywrightTimeoutError:
                continue
        
        if not campo_numero:
            raise Exception("Campo de número do processo não encontrado na tela de consulta do PJe.")
        
        await campo_numero.fill(numero_processo)
        
        # Clica no botão de busca
        seletores_busca = [
            "input[value*='Pesquisar']",
            "button:has-text('Pesquisar')",
            "input[type='submit']",
            "#fPP\\:btnPesquisar",
        ]
        for seletor in seletores_busca:
            try:
                btn = await self.page.wait_for_selector(seletor, timeout=3000)
                if btn:
                    await btn.click()
                    break
            except PlaywrightTimeoutError:
                continue
        
        await self.page.wait_for_load_state("networkidle", timeout=15000)
        
        # Verifica se há resultados
        try:
            # O PJe geralmente exibe um link com o número do processo na tabela
            link_processo = await self.page.wait_for_selector(
                f"a:has-text('{numero_processo[:7]}')",
                timeout=8000
            )
            await link_processo.click()
            await self.page.wait_for_load_state("networkidle", timeout=20000)
            return True
        except PlaywrightTimeoutError:
            return False

    async def encontrar_sentenca_homologacao(self) -> dict:
        """
        Filtra movimentações por 'sentença' na barra lateral e localiza a homologação.
        Baseado no print do usuário: existe um campo de busca acima da linha do tempo.
        """
        # O print mostra um campo de busca com ícone de funil/filtro
        seletores_busca_mov = [
            "input[id*='ftrMovimentacoes']",
            "input[placeholder*='sentença']",
            "input[placeholder*='filtro']",
            "input[id*='txtFiltro']",
            ".input-filtro-movimentacoes",
        ]
        
        campo_filtro = None
        for seletor in seletores_busca_mov:
            try:
                campo_filtro = await self.page.wait_for_selector(seletor, timeout=5000)
                if campo_filtro:
                    break
            except PlaywrightTimeoutError:
                continue
        
        if campo_filtro:
            await campo_filtro.fill("sentença")
            await self.page.wait_for_timeout(2000)
        
        # Agora procura nas movimentações visíveis por palavras de homologação
        for palavra in PALAVRAS_HOMOLOGACAO:
            try:
                elemento = await self.page.wait_for_selector(
                    f"text='{palavra}'",
                    timeout=3000
                )
                if elemento:
                    # Extrai a data da movimentação (geralmente um elemento próximo com data)
                    data_elemento = await self.page.evaluate("""
                        (el) => {
                            const parent = el.closest('.timeline-item, .mov-item, tr, li, .list-group-item');
                            if (!parent) return null;
                            const dateEl = parent.querySelector('.data-movimentacao, .col-data, td:first-child, .date');
                            return dateEl ? dateEl.textContent.trim() : null;
                        }
                    """, elemento)
                    
                    # Extrai o ID/link do documento associado
                    id_doc = await self.page.evaluate("""
                        (el) => {
                            const parent = el.closest('.timeline-item, .mov-item, tr, li, .list-group-item');
                            if (!parent) return null;
                            const link = parent.querySelector('a[id], a.link-doc');
                            return link ? (link.getAttribute('id') || link.getAttribute('href')) : null;
                        }
                    """, elemento)
                    
                    return {
                        "encontrado": True,
                        "data": self._extrair_data(data_elemento or ""),
                        "palavra_chave": palavra,
                        "id_documento": id_doc
                    }
            except PlaywrightTimeoutError:
                continue
        
        return {"encontrado": False}

    async def baixar_sentenca(self, id_documento: str, numero_processo: str) -> str:
        """
        Clica no documento de sentença e faz download do PDF.
        Salva na pasta do cliente no Dropbox.
        """
        if not os.path.exists(self.pasta_cliente):
            os.makedirs(self.pasta_cliente)
        
        nome_arquivo = f"SENTENCA_HOMOLOGACAO_{numero_processo.replace('-', '').replace('.', '')}.pdf"
        caminho_destino = os.path.join(self.pasta_cliente, nome_arquivo)
        
        # Configura interceptação de download
        async with self.page.expect_download() as download_info:
            if id_documento:
                try:
                    # Tenta clicar no botão de download (ícone ⬇️ no viewer)
                    await self.page.click(f"#{id_documento}", timeout=5000)
                except:
                    # Fallback: clica no ícone de download genérico do visualizador
                    await self.page.click("a[title*='Baixar'], button[title*='Download'], .icone-download", timeout=5000)
        
        download = await download_info.value
        await download.save_as(caminho_destino)
        print(f"[PJe] Arquivo salvo em: {caminho_destino}")
        return caminho_destino

    def _extrair_data(self, texto: str) -> str:
        """Extrai uma data no formato DD/MM/AAAA do texto."""
        match = re.search(r'(\d{2}/\d{2}/\d{4})', texto)
        return match.group(1) if match else "Data não encontrada"
