import os
import time
from pathlib import Path
from playwright.sync_api import sync_playwright
from gerador_boletos.logger import log
from gerador_boletos.config import (
    GLOBAL_OFFICE_LOGIN, 
    GLOBAL_OFFICE_USER, 
    GLOBAL_OFFICE_PASS,
    GLOBAL_OFFICE_ESCRITORIO,
    GLOBAL_OFFICE_MODELO,
    GLOBAL_OFFICE_PADRAO_RECEITAS,
    GLOBAL_OFFICE_ITEM_VENDA,
    PASTA_BOLETOS
)

STATE_FILE = "globaloffice_state.json"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
URL_LOGIN = "https://globalofficeweb.com.br/"

class GlobalOfficeService:
    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def _esperar_login_manual(self):
        log.info("Nenhuma sessão salva encontrada. Solicitando login manual para passar pelo reCAPTCHA.")
        browser = self.playwright.chromium.launch(headless=False)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        page.goto(URL_LOGIN)
        
        if GLOBAL_OFFICE_LOGIN: page.locator("#EDTLOGIN").fill(GLOBAL_OFFICE_LOGIN)
        if GLOBAL_OFFICE_USER: page.locator("#EDTUSUARIO").fill(GLOBAL_OFFICE_USER)
        if GLOBAL_OFFICE_PASS: page.locator("#EDTSENHA").fill(GLOBAL_OFFICE_PASS)
            
        log.info("Por favor, resolva o reCAPTCHA e clique em ENTRAR.")
        page.locator("#EDTLOGIN").wait_for(state="hidden", timeout=0) 
        
        context.storage_state(path=STATE_FILE)
        log.info("Sessão salva com sucesso!")
        browser.close()

    def iniciar_sessao(self, visivel=True):
        self.playwright = sync_playwright().start()
        
        while True:
            if not Path(STATE_FILE).exists():
                self._esperar_login_manual()

            self.browser = self.playwright.chromium.launch(headless=not visivel)
            self.context = self.browser.new_context(storage_state=STATE_FILE, user_agent=USER_AGENT, accept_downloads=True)
            self.page = self.context.new_page()
            self.page.on("dialog", lambda dialog: dialog.accept())
            
            # Validar se a sessão ainda está ativa
            self.page.goto(URL_LOGIN)
            self.page.wait_for_timeout(5000)
            
            is_login_visible = self.page.locator("#EDTLOGIN").is_visible()
            has_seta = self.page.evaluate("typeof window.SetaAcao !== 'undefined'")
            
            if is_login_visible or not has_seta:
                log.warning("Sessão expirada (ou página em branco). Apagando o estado salvo e pedindo novo login...")
                if self.context: self.context.close()
                if self.browser: self.browser.close()
                Path(STATE_FILE).unlink(missing_ok=True)
                continue # Volta para o início do loop (STATE_FILE não existirá, forçando login manual)
            else:
                log.info("Sessão validada com sucesso.")
                self._selecionar_empresa()
                break

    def fechar_sessao(self):
        if self.context: self.context.close()
        if self.browser: self.browser.close()
        if self.playwright: self.playwright.stop()
            
    def _selecionar_empresa(self):
        log.info("Selecionando a empresa AC COBRANÇA...")
        self.page.goto(URL_LOGIN)
        self.page.wait_for_function("typeof window.SetaAcao !== 'undefined'", timeout=15000)
        self.page.evaluate("window.SetaAcao('Menu', 'frmEmpresas');")
        
        # Espera a tabela carregar
        self.page.locator("text='AC COBRANCA'").wait_for(state="visible", timeout=15000)
        
        # Encontra a linha da empresa e clica no botão azul (ícone de check). 
        # Como é o 3º botão, usamos nth(2) ou buscamos pela classe/ícone.
        linha = self.page.locator("tr:has-text('AC COBRANCA')")
        
        # Tenta buscar por um botão/link que tenha classe info ou primary ou o icone de check
        botao_check = linha.locator("a.btn-info, button.btn-info, a:has(.fa-check), button:has(.fa-check), a.btn-primary, button.btn-primary").first
        
        if botao_check.is_visible():
            botao_check.click()
        else:
            # Fallback para o 3º botão
            linha.locator("button, a").nth(2).click()
            
        self.page.wait_for_timeout(3000)

    def _navegar_inclusao_boletos(self):
        self.page.goto(URL_LOGIN)
        self.page.wait_for_function("typeof window.SetaAcao !== 'undefined'", timeout=15000)
        self.page.evaluate("window.SetaAcao('Menu', 'frmBoletoAvulso');")
        
        log.info("Aguardando carregamento da tabela de boletos...")
        self.page.wait_for_timeout(3000)
        
        log.info("Acionando a criação de novo boleto...")
        # Tenta chamar SetaAcao('Inc') várias vezes caso a página esteja recarregando
        for _ in range(15):
            self.page.wait_for_timeout(1000)
            try:
                # Testa se existe e é uma função neste exato frame
                is_fn = self.page.evaluate("typeof window.SetaAcao === 'function'")
                if is_fn:
                    self.page.evaluate("window.SetaAcao('Inc');")
                    break
            except Exception:
                pass
        else:
            raise Exception("Falha ao abrir a tela de Novo Boleto após 15 tentativas.")
        
        # Agora sim o campo EDTCLIENTE deve ficar visível!
        self.page.locator("#EDTCLIENTE").wait_for(state="visible", timeout=15000)
        
    def preencher_e_gerar_boleto(self, cliente: str, valor: str, vencimento: str, num_processo: str, modo_homologacao=True):
        self._navegar_inclusao_boletos()
        log.info(f"Preenchendo boleto para {cliente} | {valor} | {vencimento}...")
        
        # Função auxiliar para seleção parcial ignorando case e espaços complexos
        def selecionar_dropdown(seletor, valor_buscado):
            if not valor_buscado: return
            
            # Pega todas as opções do select
            opcoes = self.page.locator(f"{seletor} option").all_inner_texts()
            
            import unicodedata
            def normalizar(texto):
                texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
                return texto.lower().replace(chr(160), ' ').strip()
                
            valor_norm = normalizar(valor_buscado)
            
            melhor_opcao = None
            for opt in opcoes:
                if valor_norm in normalizar(opt):
                    melhor_opcao = opt
                    break
                    
            if melhor_opcao:
                self.page.locator(seletor).select_option(label=melhor_opcao)
                self.page.wait_for_timeout(1500)
            else:
                from gerador_boletos.logger import log
                log.warning(f"Opção '{valor_buscado}' não encontrada no {seletor}. Opções: {opcoes}")

        if GLOBAL_OFFICE_ESCRITORIO: selecionar_dropdown("#CBXESCRITORIOSINC", GLOBAL_OFFICE_ESCRITORIO)
        
        # Forçando a palavra SICOOB para garantir que bate com o SICOOB ALDRIGUES
        if GLOBAL_OFFICE_MODELO: selecionar_dropdown("#CBXMODELO", "SICOOB")
        
        if GLOBAL_OFFICE_PADRAO_RECEITAS: selecionar_dropdown("#CBXPADRAORECEITA", GLOBAL_OFFICE_PADRAO_RECEITAS)
            
        if modo_homologacao:
            self.page.locator("#CKBHOMOLOGACAO_CHECKBOX").check()
        else:
            self.page.locator("#CKBHOMOLOGACAO_CHECKBOX").uncheck()

                # Preenchimento - Autocomplete do Cliente
        self.page.locator("#EDTCLIENTE").click(force=True)
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Backspace")
        self.page.locator("#EDTCLIENTE").type(cliente, delay=100)
        
        try:
            # Espera a caixinha "Lista de Clientes" aparecer
            self.page.locator("text='Lista de Clientes'").wait_for(state="visible", timeout=10000)
            self.page.wait_for_timeout(1500) # espera a busca via AJAX
            
            # Clica diretamente no TR do modal que contem o cliente
            elemento_cliente = self.page.locator(f".modal-content tr:has-text('{cliente}')").first
            elemento_cliente.click()
            self.page.wait_for_timeout(500)
            if self.page.locator("text='Lista de Clientes'").is_visible():
                elemento_cliente.dblclick()
                self.page.wait_for_timeout(500)
            if self.page.locator("text='Lista de Clientes'").is_visible():
                elemento_cliente.locator("td").first.click()
            
            # Aguarda a lista sumir (garantia de que selecionou)
            self.page.locator("text='Lista de Clientes'").wait_for(state='hidden', timeout=1000)
        except Exception as e:
            log.warning(f"Menu de autocomplete falhou para '{cliente}'. Erro: {e}")
            
            # Se falhou, tenta fechar a lista pra nao travar o proximo campo
            try:
                self.page.keyboard.press("Escape")
                self.page.locator("text='Lista de Clientes'").wait_for(state='hidden', timeout=2000)
            except: pass
            
            self.page.locator("#EDTCLIENTE").press("Tab")
            self.page.wait_for_timeout(1000)

                # Preenchimento - Autocomplete do Item
        self.page.locator("#EDTITEM").click(force=True)
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Backspace")
        
        texto_busca = GLOBAL_OFFICE_ITEM_VENDA[:5]
        self.page.locator("#EDTITEM").type(texto_busca, delay=100)
        
        try:
            self.page.locator("text='Ítens cadastrados'").wait_for(state="visible", timeout=10000)
            self.page.wait_for_timeout(1500)
            
            elemento_item = self.page.locator(f".modal-content tr:has-text('{texto_busca}')").first
            elemento_item.click()
            self.page.wait_for_timeout(500)
            if self.page.locator("text='Ítens cadastrados'").is_visible():
                elemento_item.dblclick()
                self.page.wait_for_timeout(500)
            if self.page.locator("text='Ítens cadastrados'").is_visible():
                elemento_item.locator("td").first.click()
            
            self.page.locator("text='Ítens cadastrados'").wait_for(state='hidden', timeout=1000)
        except Exception as e:
            log.warning(f"Menu de autocomplete falhou para '{GLOBAL_OFFICE_ITEM_VENDA}'. Erro: {e}")
            
            try:
                self.page.keyboard.press("Escape")
                self.page.locator("text='Ítens cadastrados'").wait_for(state='hidden', timeout=2000)
            except: pass
            
            self.page.locator("#EDTITEM").press("Tab")
            self.page.wait_for_timeout(1000)

        self.page.locator("#EDTVALOR").click(force=True)
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Backspace")
        self.page.locator("#EDTVALOR").type(valor, delay=50)

        self.page.locator("#EDTVENCIMENTO").click(force=True)
        self.page.keyboard.press("Control+A")
        self.page.keyboard.press("Backspace")
        self.page.locator("#EDTVENCIMENTO").type(vencimento, delay=50)
        
        instrucoes = f"Referente ao Processo: {num_processo}"
        self.page.locator("#MMINSTRUCOES").fill(instrucoes)

        log.info("Salvando dados...")
        self.page.evaluate("Gravar();")
        
        # Espera ativamente pelo SweetAlert de sucesso por até 10 segundos
        try:
            self.page.locator(".sweet-alert").wait_for(state="visible", timeout=10000)
            self.page.locator("button.confirm").click(force=True)
            self.page.locator(".sweet-alert").wait_for(state="hidden", timeout=3000)
        except:
            pass
        self.page.wait_for_timeout(1000)
            
        # Fecha o modal se ainda estiver aberto
        self.page.evaluate("try { if(typeof HideModal !== 'undefined') HideModal(); else if(typeof $ !== 'undefined' && $('.modal').length && typeof $('.modal').modal === 'function') $('.modal').modal('hide'); } catch(e) {}")
        self.page.wait_for_timeout(2000)
        
        return self._baixar_ultimo_boleto(cliente)

    def _baixar_ultimo_boleto(self, cliente):
        log.info("Baixando PDF do boleto...")
        # Aguarda a tabela recarregar garantindo que a primeira linha contém o cliente que acabamos de criar
        try:
            linha_cliente = self.page.locator(f"tr:has-text('{cliente}')").first
            linha_cliente.wait_for(state='visible', timeout=15000)
            botao_imprimir = linha_cliente.locator("button[title='Imprimir boleto']")
        except Exception:
            # Fallback se demorar muito
            botao_imprimir = self.page.locator("button[title='Imprimir boleto']").first
            
        if not botao_imprimir.is_visible():
            log.error("Botão 'Imprimir boleto' não encontrado após gravação.")
            return None

        try:
            # Vamos tentar interceptar a URL seja por Popup (nova aba) ou por Response (iframe)
            pdf_url = None
            
            def handle_response(response):
                nonlocal pdf_url
                try:
                    if response.status == 200:
                        content_type = response.headers.get("content-type", "").lower()
                        if "application/pdf" in content_type or ".pdf" in response.url.lower():
                            pdf_url = response.url
                            log.info(f"URL do PDF interceptada via rede: {pdf_url}")
                except: pass
                
            def handle_popup(popup):
                nonlocal pdf_url
                try:
                    pdf_url = popup.url
                    log.info(f"Popup detectado. URL: {pdf_url}")
                except: pass
                    
            self.page.on("response", handle_response)
            self.page.on("popup", handle_popup)

            # Clica em Imprimir boleto de forma confiavel para evitar bloqueio de popup
            botao_imprimir.scroll_into_view_if_needed()
            botao_imprimir.click()
            
            # Aguarda a URL ser interceptada
            for _ in range(30):
                self.page.wait_for_timeout(1000)
                if pdf_url and pdf_url != "about:blank":
                    break
                # Verifica se apareceu algum erro na tela (ex: erro 5002)
                try:
                    if self.page.locator(".sweet-alert").is_visible():
                        erro_texto = self.page.locator(".sweet-alert p").inner_text()
                        if erro_texto:
                            self.page.locator("button.confirm").click(force=True)
                            if 'sucesso' not in erro_texto.lower():
                                raise Exception(f"Erro do sistema ao imprimir: {erro_texto}")
                            else:
                                log.info(f"Aviso fechado: {erro_texto}")
                except Exception as e:
                    if 'Erro do sistema' in str(e): raise e
            
                    
            if not pdf_url or pdf_url == "about:blank":
                # Fallback: tentar pegar a URL de qualquer aba nova que tenha aberto
                for page in self.page.context.pages:
                    if page != self.page:
                        pdf_url = page.url
                        break
                        
            if not pdf_url or pdf_url == "about:blank":
                raise Exception("A URL do PDF nunca foi retornada pelo servidor (Timeout 30s).")
                
            self.page.remove_listener("response", handle_response)
            self.page.remove_listener("popup", handle_popup)
                
            # 5. Baixa o PDF
            import time
            nome_arquivo = f"Boleto_{cliente.replace(' ', '_').replace('/', '')}_{time.strftime('%Y%m%d%H%M%S')}.pdf"
            caminho_final = os.path.join(PASTA_BOLETOS, nome_arquivo)
            
            resp_pdf = self.page.request.get(pdf_url)
            with open(caminho_final, 'wb') as f:
                f.write(resp_pdf.body())
                
            log.info(f"Boleto salvo com sucesso em: {caminho_final}")
            
            # Se abriu um modal, tenta fechar
            try:
                self.page.evaluate("if($('.modal').length) $('.modal').modal('hide');")
                self.page.keyboard.press("Escape")
            except: pass
            
            # Fecha abas extras que possam ter sido abertas
            for page in self.page.context.pages:
                if page != self.page:
                    page.close()
            
            return caminho_final
        except Exception as e:
            log.error(f"Falha no download: {e}")
            return None
