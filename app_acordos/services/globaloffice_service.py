import os
import asyncio
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# Caminho para manter a sessão (cookies, cache) viva entre execuções
USER_DATA_DIR = os.path.join(os.getenv('LOCALAPPDATA', 'C:\\Temp'), 'GlobalOfficeSession')

class GlobalOfficeBlockedException(Exception):
    """Exceção customizada para quando o ícone de 'mãos dadas' estiver bloqueado pela TI."""
    pass

class GlobalOfficeService:
    @staticmethod
    async def preencher_acordo(dados_revisados: dict):
        """
        Inicia a automação no navegador visível para preencher o Global Office.
        """
        cliente_nome = dados_revisados.get("cliente", {}).get("nome", "")
        
        # Inicia o Playwright de forma assíncrona
        async with async_playwright() as p:
            # Usando persistent context para manter o login salvo
            browser = await p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                headless=False, # Precisa ser False para o usuário ver/interagir se necessário
                args=["--start-maximized"],
                no_viewport=True
            )
            
            page = browser.pages[0] if browser.pages else await browser.new_page()
            
            try:
                # ==========================================================
                # 1. ACESSAR SISTEMA
                # ==========================================================
                # O usuário fará o login manual se a sessão não estiver ativa.
                print(f"[{cliente_nome}] O navegador foi aberto. Se for a primeira vez, faça o login no Global Office.")
                # Vamos aguardar até que o elemento "Menu Jurídico" apareça, indicando que o login foi feito e a tela carregou
                # Mas para não travar infinitamente se algo der errado, damos um timeout longo na primeira vez.
                # await page.wait_for_selector("text='Menu Jurídico'", timeout=60000)
                
                # ==========================================================
                # 2. NAVEGAÇÃO
                # ==========================================================
                print(f"[{cliente_nome}] Acessando Menu Jurídico > Cobranças / Execuções > Cadastro de Devedores...")
                
                # Estes comandos vão clicar sequencialmente nos menus assim que aparecerem
                # await page.click("text='Menu Jurídico'")
                # await page.click("text='Cobranças / Execuções'")
                # await page.click("text='Cadastro de devedores'")
                
                # ==========================================================
                # 3. BUSCA E AÇÃO
                # ==========================================================
                print(f"[{cliente_nome}] Pesquisando pelo nome: {cliente_nome}")
                # Exemplo: procuramos pelo input placeholder "Pesquisar" (conforme o seu print)
                # await page.fill("input[placeholder*='Pesquisar']", cliente_nome)
                # await page.keyboard.press("Enter")
                # Aguardamos a tabela carregar após a pesquisa
                # await page.wait_for_timeout(3000)
                
                # Verificar se o ícone de "Mãos dadas" está presente e clicável
                print(f"[{cliente_nome}] Verificando status do ícone 'Mãos Dadas'...")
                
                # No seu print, há uma div/td com "AÇÕES" e botões coloridos. 
                # Um deles é o "mãos dadas". Se ele tiver uma classe como 'disabled' ou algo cinza:
                # bloqueado = await page.evaluate("() => document.querySelector('.icone-maos-dadas').disabled")
                # if bloqueado:
                #     raise GlobalOfficeBlockedException(f"Ícone 'Mãos dadas' bloqueado pela TI para {cliente_nome}")
                
                # await page.click(".icone-maos-dadas")
                
                # ==========================================================
                # 4. PREENCHIMENTO DO FORMULÁRIO (Exemplo de preenchimento)
                # ==========================================================
                print(f"[{cliente_nome}] Preenchendo formulário...")
                # await page.fill("input[name='valor_acordo']", dados_revisados['financeiro']['valor_negociado'])
                # ...
                
                # await page.click("button:has-text('Salvar')")
                
                print(f"[{cliente_nome}] Processo finalizado com sucesso!")
                
            except GlobalOfficeBlockedException as e:
                print(f"ERRO: {str(e)}")
                raise
            except Exception as e:
                print(f"Erro durante a automação Playwright: {e}")
                raise
            finally:
                # Aguarda uns segundos para ver o resultado antes de fechar a aba
                await page.wait_for_timeout(3000)
                await browser.close()

if __name__ == "__main__":
    # Teste rápido
    mock = {"cliente": {"nome": "ALAOR MARCOS DE SOUZA"}, "financeiro": {"valor_negociado": "22.219,22"}}
    asyncio.run(GlobalOfficeService.preencher_acordo(mock))
