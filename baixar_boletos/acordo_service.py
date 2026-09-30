"""
acordo_service.py
Serviço de automação Playwright para inclusão de Acordos Judiciais e Download no Global Office.
"""

import os
import sys
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Callable

from playwright.sync_api import sync_playwright, Page, BrowserContext, Browser

from baixar_boletos.config import (
    GLOBAL_OFFICE_URL,
    GLOBAL_OFFICE_LOGIN,
    GLOBAL_OFFICE_USER,
    GLOBAL_OFFICE_PASS,
    STATE_FILE,
    USER_AGENT,
    formatar_nome_arquivo_boleto,
    obter_pasta_boletos_cliente
)
from baixar_boletos.acordo_parser import AcordoParser, normalizar_texto


class AcordoService:
    def __init__(self, log_callback: Optional[Callable[[str], None]] = None, progress_callback: Optional[Callable] = None):
        self.log_callback = log_callback or (lambda msg: print(msg, flush=True))
        self.progress_callback = progress_callback
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.parser = AcordoParser()
        self._cancelado = False
        self._clientes_baixados = set()

    def log(self, mensagem: str, nivel: str = "INFO"):
        hora = time.strftime("%H:%M:%S")
        texto = f"{hora} - {nivel} - {mensagem}"
        try:
            self.log_callback(texto)
        except UnicodeEncodeError:
            texto_limpo = texto.encode("ascii", "replace").decode("ascii")
            self.log_callback(texto_limpo)

    def cancelar(self):
        self._cancelado = True
        self.log("Cancelamento solicitado pelo utilizador.", "WARNING")

    def _esperar_login_manual(self):
        self.log("Sessão não autenticada. A preencher credenciais...")
        # Criar playwright proprio se o principal foi fechado por fechar_sessao()
        pw_proprio = False
        pw = self.playwright
        if pw is None:
            pw = sync_playwright().start()
            pw_proprio = True

        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        page.goto(GLOBAL_OFFICE_URL)

        if GLOBAL_OFFICE_LOGIN:
            try: page.locator("#EDTLOGIN").fill(GLOBAL_OFFICE_LOGIN)
            except Exception: pass
        if GLOBAL_OFFICE_USER:
            try: page.locator("#EDTUSUARIO").fill(GLOBAL_OFFICE_USER)
            except Exception: pass
        if GLOBAL_OFFICE_PASS:
            try: page.locator("#EDTSENHA").fill(GLOBAL_OFFICE_PASS)
            except Exception: pass

        self.log("Por favor, resolva o reCAPTCHA na janela aberta do navegador e clique em ENTRAR.")
        try:
            page.locator("#EDTLOGIN").wait_for(state="hidden", timeout=0)
            page.wait_for_timeout(3000)
            context.storage_state(path=str(STATE_FILE))
            self.log("Login efetuado com sucesso!")
        finally:
            browser.close()
            if pw_proprio:
                try: pw.stop()
                except Exception: pass

    def fechar_sessao(self):
        try:
            if self.context: self.context.close()
            if self.browser: self.browser.close()
            if self.playwright: self.playwright.stop()
        except Exception: pass
        self.context = None
        self.browser = None
        self.playwright = None
        self.page = None

    def iniciar_sessao(self, visivel: bool = False):
        if self.page and not self.page.is_closed():
            return

        self.log(f"Iniciando navegador (visível={1 if visivel else 0})...")
        self.playwright = sync_playwright().start()

        state_path = Path(STATE_FILE)
        if not state_path.exists():
            local_state = Path("globaloffice_state.json")
            if local_state.exists():
                state_path = local_state
            else:
                self._esperar_login_manual()
                state_path = Path(STATE_FILE)

        self.browser = self.playwright.chromium.launch(
            headless=not visivel,
            args=["--start-maximized", "--disable-blink-features=AutomationControlled"]
        )
        self.context = self.browser.new_context(
            storage_state=str(state_path),
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
            accept_downloads=True,
            permissions=["geolocation"],
            geolocation={"latitude": -15.7942, "longitude": -47.8822} # Brasília
        )
        self.page = self.context.new_page()
        self.page.on("dialog", lambda dialog: dialog.accept())

        try:
            resp = self.page.goto(GLOBAL_OFFICE_URL, timeout=45000)
            if resp and resp.status >= 400:
                self.log(f"Sessão expirada no servidor (HTTP {resp.status}). Renovando login...", "WARNING")
                self.fechar_sessao()
                if state_path.exists(): state_path.unlink(missing_ok=True)
                self._esperar_login_manual()
                return self.iniciar_sessao(visivel=visivel)
            self.page.wait_for_timeout(2000)
        except Exception as e:
            self.log(f"Falha ao carregar página: {e}. Solicitando novo login...", "WARNING")
            self.fechar_sessao()
            if state_path.exists(): state_path.unlink(missing_ok=True)
            self._esperar_login_manual()
            return self.iniciar_sessao(visivel=visivel)

        # Validacao REAL de sessao: checa se SetaAcao existe E se #EDTLOGIN nao esta visivel
        has_seta = False
        try:
            has_seta = self.page.evaluate("typeof window.SetaAcao !== 'undefined'")
        except Exception: pass

        is_login = False
        try:
            is_login = self.page.locator("#EDTLOGIN").is_visible()
        except Exception: pass

        if is_login or not has_seta:
            self.log("Sessão desautenticada ou inválida no servidor (SetaAcao ausente ou tela de login). Renovando...", "WARNING")
            self.fechar_sessao()
            if state_path.exists(): state_path.unlink(missing_ok=True)
            self._esperar_login_manual()
            return self.iniciar_sessao(visivel=visivel)

        self.log("Sessão validada com sucesso (SetaAcao presente no DOM).")
        self._selecionar_empresa()

    def garantir_sessao_ativa(self, visivel: bool = False):
        """Verifica se a sessão do Global Office continua válida. Se caiu, renova via login manual."""
        if not self.page or self.page.is_closed():
            self.iniciar_sessao(visivel=visivel)
            return

        has_seta = False
        try:
            has_seta = self.page.evaluate("typeof window.SetaAcao !== 'undefined'")
        except Exception: pass

        is_login = False
        try:
            is_login = self.page.locator("#EDTLOGIN").is_visible()
        except Exception: pass

        if is_login or not has_seta:
            self.log("ALERTA: Sessão do Global Office expirou no meio do lote! Abrindo navegador para login...", "WARNING")
            self.fechar_sessao()
            self._esperar_login_manual()
            self.iniciar_sessao(visivel=visivel)
            self._selecionar_empresa()

    def _selecionar_empresa(self):
        self.log("Confirmando seleção da empresa AC COBRANÇA...")
        try:
            grid_visivel = False
            try:
                grid_visivel = self.page.locator("#GRID, table:has-text('Nome da Empresa')").first.is_visible(timeout=2000)
            except Exception: pass

            if not grid_visivel:
                self.log("Navegando para frmEmpresas...")
                try:
                    self.page.evaluate("if (typeof window.SetaAcao === 'function') window.SetaAcao('Menu', 'frmEmpresas');")
                except Exception: pass
                self.page.wait_for_selector("#GRID, tr:has-text('AC COBRANCA')", timeout=15000)
                self.page.wait_for_timeout(1500)

            linha = self.page.locator("#GRID tbody tr:has-text('AC COBRANCA'), tr:has-text('AC COBRANCA')").first
            if linha.is_visible(timeout=6000):
                btn_pri = linha.locator("button[title*='principal'], button.btn-info, button:has(.fa-check)").first
                if btn_pri.is_visible():
                    btn_pri.click(force=True)
                else:
                    self.page.evaluate("if(typeof window.SetaAcao === 'function') window.SetaAcao('Pri', '5');")

                self.page.wait_for_timeout(1500)

                btn_confirma = self.page.locator(
                    "button.confirm, .swal2-confirm, .sweet-alert button:has-text('Sim'), "
                    ".sweet-alert button:has-text('Confirmar'), button:has-text('Sim'), button:has-text('Confirmar')"
                ).first

                if btn_confirma.is_visible(timeout=5000):
                    self.log("Confirmando popup de empresa principal no sistema...")
                    btn_confirma.click(force=True)
                    self.page.wait_for_timeout(3000)

                self.fechar_modais_ou_telas_ativas()
                self.page.wait_for_timeout(1000)

            self.log("Retornando ao Dashboard com a empresa AC COBRANÇA ativa...")
            btn_inicio = self.page.locator(".sidebar-menu a:has-text('Início'), .sidebar a:has(.fa-home), .breadcrumb a:has-text('Início')").first
            if btn_inicio.is_visible(timeout=3000):
                btn_inicio.click(force=True)
                self.page.wait_for_timeout(2000)
            else:
                self.page.evaluate("if (typeof window.SetaAcao === 'function') window.SetaAcao('Menu', 'frmPrincipal');")
                self.page.wait_for_timeout(2000)

            self.log("Empresa AC COBRANÇA confirmada e ativa com sucesso.", "SUCCESS")
        except Exception as e:
            self.log(f"Aviso ao selecionar empresa: {e}", "WARNING")

    def fechar_modais_ou_telas_ativas(self):
        """Destrava qualquer bloqueio de JavaScript do IntraWeb e remove modais residuais."""
        try:
            self.page.evaluate("""() => {
                if (typeof window.ReleaseLock === 'function') window.ReleaseLock();
                window.GActivateLock = false;

                // Fecha botões X se existirem
                document.querySelectorAll('#bx-clg-close-btn, .iw-dlg-close, button.close, [data-dismiss="modal"]').forEach(b => b.click());
                document.querySelectorAll('.sweet-alert button.confirm, .sweet-alert button.cancel').forEach(b => b.click());

                // Remove do DOM todos os overlays que bloqueiam cliques
                const seletores = [
                    '#iw-dlg-overlay',
                    '#iw-dlg-iframe',
                    '#iw-dlg-window',
                    '.iw-dlg-overlayCSS',
                    '.iw-dlg-iframeCSS',
                    'div[id*="iw-dlg"]',
                    '.sweet-overlay',
                    '.sweet-alert',
                    '.modal-backdrop'
                ];
                seletores.forEach(sel => {
                    document.querySelectorAll(sel).forEach(el => {
                        try { el.remove(); } catch(e) {}
                    });
                });
                const lk = document.getElementById('IWLocker');
                if (lk) lk.style.display = 'none';

                if (window.jQuery) {
                    try { window.jQuery('.modal').modal('hide'); } catch(e) {}
                }
                document.body.classList.remove('modal-open', 'stop-scrolling');
            }""")
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(400)
        except Exception: pass

    def dispensar_popup_horario(self):
        try:
            self.page.wait_for_timeout(800)
            sweet_ok = self.page.locator(".sweet-alert.visible button.confirm, .sweet-alert button:has-text('OK')").first
            if sweet_ok.is_visible(timeout=3000):
                self.log("Dispensando popup de registro de horário...", "INFO")
                sweet_ok.click(force=True)
                self.page.wait_for_timeout(1000)
        except Exception:
            pass
        self.fechar_modais_ou_telas_ativas()

    def acessar_cadastro_devedores(self, visivel: bool = False) -> bool:
        self.log("Acessando tela de Cobranças/Execuções > Cadastro de devedores...")

        try:
            # PASSO 1: Destravar interface (ReleaseLock + remover overlays)
            #          Evita encavalamento de requisicoes POST no IWBTNACAO
            self.page.evaluate("""() => {
                if (typeof window.ReleaseLock === 'function') window.ReleaseLock();
                window.GActivateLock = false;
                document.querySelectorAll('.modal-backdrop, .sweet-overlay, .sweet-alert').forEach(el => el.remove()); const lk=document.getElementById('IWLocker'); if(lk) lk.style.display='none';
                document.body.classList.remove('modal-open', 'stop-scrolling');
            }""")
            self.page.wait_for_timeout(500)

            # PASSO 2: Navegar DIRETAMENTE para o Cadastro de Devedores
            self.log("Navegando para Cadastro de devedores via SetaAcao...")
            self.page.evaluate("if (typeof window.SetaAcao === 'function') window.SetaAcao('Menu', 'frmConsultaDevedoresExecucao');")
            self.log("Aguardando grid de Cadastro de devedores carregar...")

            self.page.wait_for_selector(
                "#tabela, #tabela_filter input, #tabela_wrapper",
                state="visible",
                timeout=20000
            )
            self.page.wait_for_timeout(1000)

            # VERIFICACAO: Confirmar que estamos na tela de DEVEDORES, nao de EMPRESAS
            # A tela de Empresas tambem tem #tabela, causando falso positivo
            pagina_texto = ""
            try:
                pagina_texto = self.page.locator("body").inner_text(timeout=2000)
            except Exception: pass

            if "Cadastro de Empresas" in pagina_texto and "devedores" not in pagina_texto.lower():
                self.log("AVISO: Grid pertence a Empresas, nao a Devedores. Retornando ao Início...", "WARNING")
                btn_inicio = self.page.locator(".sidebar-menu a:has-text('Início'), .sidebar a:has(.fa-home)").first
                if btn_inicio.is_visible(timeout=3000):
                    btn_inicio.click(force=True)
                    self.page.wait_for_timeout(2000)
                else:
                    self.page.evaluate("if (typeof window.SetaAcao === 'function') window.SetaAcao('Menu', 'frmPrincipal');")
                    self.page.wait_for_timeout(2000)

                self.page.evaluate("if (typeof window.SetaAcao === 'function') window.SetaAcao('Menu', 'frmConsultaDevedoresExecucao');")
                self.page.wait_for_selector(
                    "#tabela, #tabela_filter input, #tabela_wrapper",
                    state="visible",
                    timeout=20000
                )
                self.page.wait_for_timeout(1000)

            self.log("Tabela de Cadastro de devedores pronta.")
            self.dispensar_popup_horario()
            return True

        except Exception as e:
            self.log(f"SetaAcao direto falhou. Tentando fallback via span.click() no DOM: {e}", "WARNING")

            # FALLBACK: Clica nos <span onclick="SetaAcao(...)"> do menu lateral
            try:
                # Destravar novamente antes do fallback
                self.page.evaluate("""() => {
                    if (typeof window.ReleaseLock === 'function') window.ReleaseLock();
                    window.GActivateLock = false;
                    document.querySelectorAll('.modal-backdrop, .sweet-overlay, .sweet-alert').forEach(el => el.remove()); const lk=document.getElementById('IWLocker'); if(lk) lk.style.display='none';
                    document.body.classList.remove('modal-open', 'stop-scrolling');
                }""")
                self.page.wait_for_timeout(500)

                # 1. Clicar no span do Menu Juridico
                self.log("Fallback: Clicando span do Menu Juridico...")
                self.page.evaluate("(function(){ var s = document.querySelector(\"span[onclick*='ModuloJuridico']\"); if(s) s.click(); })()")
                self.page.wait_for_timeout(1500)

                # 2. Clicar no span de Cobrancas/Execucoes
                self.log("Fallback: Clicando span de Cobrancas/Execucoes...")
                self.page.evaluate("(function(){ var s = document.querySelector(\"span[onclick*='frmMenuExecucoes']\"); if(s) s.click(); })()")
                self.page.wait_for_timeout(1500)

                # 3. Clicar no link/span do Cadastro de devedores
                self.log("Fallback: Clicando Cadastro de devedores...")
                self.page.evaluate("(function(){ var a = document.querySelector(\"span[onclick*='frmConsultaDevedoresExecucao']\"); if(a){ a.click(); return; } if(typeof window.SetaAcao==='function') window.SetaAcao('Menu','frmConsultaDevedoresExecucao'); })()")

                self.page.wait_for_selector(
                    "#tabela, #tabela_filter input, #tabela_wrapper",
                    state="visible",
                    timeout=20000
                )
                self.page.wait_for_timeout(1000)
                self.log("Tabela de Cadastro de devedores pronta (via fallback DOM).")
                self.dispensar_popup_horario()
                return True

            except Exception as err2:
                self.log(f"Falha critica ao aceder ao ecra de devedores: {err2}", "ERROR")
                try:
                    self.page.screenshot(path="debug_erro_devedores.png")
                    self.log("Screenshot salvo: debug_erro_devedores.png")
                except Exception:
                    pass
                return False


    def pesquisar_devedor_no_grid(self, nome_cliente: str, visivel: bool = False) -> bool:
        self.log(f"Pesquisando devedor no grid: '{nome_cliente}'...")
        try:
            self.fechar_modais_ou_telas_ativas()
            campo_busca = self.page.locator("input[type='search'], #tabela_filter input").first
            campo_busca.wait_for(state="visible", timeout=8000)
            campo_busca.scroll_into_view_if_needed()
            campo_busca.click(force=True)
            self.page.keyboard.press("Control+A")
            self.page.keyboard.press("Backspace")
            self.page.wait_for_timeout(400)

            try:
                with self.page.expect_response(lambda r: "callback=tabela" in r.url and r.status == 200, timeout=12000):
                    self.page.keyboard.type(nome_cliente, delay=60)
            except Exception:
                self.page.keyboard.press("Enter")
                self.page.wait_for_timeout(2000)

            try:
                self.page.wait_for_selector("#tabela_processing", state="hidden", timeout=8000)
            except Exception: pass
            self.page.wait_for_timeout(800)

            info_el = self.page.locator("#tabela_info").first
            info_txt = info_el.inner_text() if info_el.is_visible() else ""
            if "0 até 0 de 0" in info_txt or "Mostrando 0" in info_txt:
                self.log(f"Devedor '{nome_cliente}' não encontrado no grid de devedores.", "WARNING")
                return False

            linhas = self.page.locator("#tabela tbody tr").all()
            if not linhas: return False

            txt_primeira = linhas[0].inner_text().strip()
            if not txt_primeira or "nenhum registro" in txt_primeira.lower():
                return False

            # TRAVA RIGOROSA DE NOME: Não aceitar cliente diferente do pesquisado
            norm_cliente = normalizar_texto(nome_cliente)
            norm_linha = normalizar_texto(txt_primeira)
            partes = [p for p in norm_cliente.split() if len(p) > 2]
            if partes and not any(p in norm_linha for p in partes[:2]):
                self.log(f"Linha retornada não confere com '{nome_cliente}': {txt_primeira[:50]}...", "WARNING")
                return False

            self.log(f"Devedor '{nome_cliente}' localizado no grid com sucesso.", "SUCCESS")
            return True

        except Exception as e:
            self.log(f"Erro ao pesquisar devedor: {e}", "ERROR")
            return False

    def abrir_modal_acordo(self, nome_cliente: str = "") -> Optional[bool]:
        self.log("Abrindo formulário de Acordo Judicial (ícone mãos dadas)...")
        try:
            self.fechar_modais_ou_telas_ativas()
            self.dispensar_popup_horario()
            self.page.wait_for_timeout(600)
            linha = self.page.locator("#tabela tbody tr").first
            linha.wait_for(state="visible", timeout=8000)

            texto_linha = linha.inner_text().lower()
            if "já tem acordo" in texto_linha or "ja tem acordo" in texto_linha:
                self.log(f"O devedor '{nome_cliente}' JÁ POSSUI ACORDO CADASTRADO no sistema.", "SUCCESS")
                return None

            btn = linha.locator("button:has(.fa-handshake-o), button[onclick*='Acord'], button[title*='acordo' i]").first
            if not btn.is_visible(timeout=4000):
                self.log("Botão de acordo não encontrado na linha do devedor.", "ERROR")
                return False

            onclick_code = btn.get_attribute("onclick") or ""
            if "SetaAcao" in onclick_code:
                self.page.evaluate(f"() => {{ {onclick_code} }}")
            else:
                btn.evaluate("el => el.click()")

            # TRATA POPUP DE HORÁRIO / ALERTAS DO SISTEMA
            self.page.wait_for_timeout(1500)
            sweet = self.page.locator(".sweet-alert.visible").first
            if sweet.is_visible(timeout=3000):
                txt_alerta = sweet.inner_text()
                self.log(f"Aviso/Popup detectado na tela: {txt_alerta[:80]}...", "WARNING")
                btn_ok = sweet.locator("button.confirm, button:has-text('OK'), button:has-text('Confirmar'), button:has-text('Sim')").first
                if btn_ok.is_visible():
                    btn_ok.click(no_wait_after=True)
                    self.page.wait_for_timeout(2000)

            modal = self.page.locator("#Cadastro, div[role='dialog']").filter(has_text="Acordos Judiciais").first
            modal.wait_for(state="visible", timeout=15000)
            self.log("Formulário 'INCLUSÃO DE ACORDOS JUDICIAIS' aberto com sucesso!", "SUCCESS")
            return True
        except Exception as e:
            self.log(f"Erro ao abrir modal de acordos: {e}", "ERROR")
            return False


    def preencher_e_gravar_acordo(self, dados: Dict[str, Any]) -> bool:
        modal = self.page.locator("#Cadastro, div[role='dialog']").filter(has_text="Acordos Judiciais").first
        try:
            self.page.wait_for_timeout(800)

            # Processo
            input_proc = modal.locator("#EDTPROCESSO").first
            if input_proc.is_visible():
                v = input_proc.input_value().strip()
                if not v and dados.get("processo"):
                    input_proc.fill(dados["processo"])

            # Valores
            if dados.get("valor_inicial"):
                modal.locator("#EDTVALORINICIAL").fill(dados["valor_inicial"])
            if dados.get("valor_limite"):
                modal.locator("#EDTVALORLIMITE").fill(dados["valor_limite"])

            # Sentença
            if dados.get("tem_sentenca") and dados.get("arquivo_sentenca"):
                modal.locator("#IWUPLOADER_INPUT").set_input_files(dados["arquivo_sentenca"])
            else:
                self.page.evaluate("() => { const el = document.getElementById('EDTDATAHOMOLOGACAO'); if (el) el.value = ''; }")

            # Item de venda (Prestação)
            inp_item = modal.locator("#EDTITEM").first
            if inp_item.is_visible():
                inp_item.click()
                inp_item.fill("")
                inp_item.press_sequentially("Prestação", delay=50)
                self.page.wait_for_timeout(800)
                item_linha = self.page.locator("#LISTAITEM tr:has-text('Prestação')").first
                if item_linha.is_visible(): item_linha.click()
                else: self.page.keyboard.press("Enter")
                self.page.evaluate("() => { const el = document.getElementById('LISTAITEM'); if (el) el.style.display = 'none'; }")

            # Forma, Modelo e Escritório
            self.page.evaluate("""() => {
                const f = document.getElementById('CBXFORMASDEPAGAMENTO'); if (f) { f.value = '0'; f.dispatchEvent(new Event('change')); }
                const m = document.getElementById('CBXMODELO'); if (m) { m.value = '0'; m.dispatchEvent(new Event('change')); }
                const e = document.getElementById('CBXESCRITORIOS'); if (e) { e.value = '0'; e.dispatchEvent(new Event('change')); }
            }""")

            # Entrada
            if dados.get("tem_entrada") and dados.get("valor_entrada"):
                self.page.evaluate(f"""() => {{
                    const d = document.getElementById('EDTVENCIMENTODAENTRADA'); if (d) d.value = '{dados["data_entrada"]}';
                    const v = document.getElementById('EDTVALORDAENTRADA'); if (v) v.value = '{dados["valor_entrada"]}';
                }}""")

            # Parcelas
            self.page.evaluate(f"""() => {{
                const q = document.getElementById('EDTQTDPARCELAS1'); if (q) q.value = '{dados["qtd_parcelas"]}';
                const v = document.getElementById('EDTVALORDASPARCELAS1'); if (v) v.value = '{dados["valor_parcela"]}';
                const p = document.getElementById('EDTPRIMEIROVENCIMENTO1'); if (p) p.value = '{dados["primeiro_vencimento"]}';
            }}""")
            self.page.wait_for_timeout(600)

            # Gravar
            btn_gravar = modal.locator("button:has-text('Gravar Dados'), #BTNGRAVAR").first
            btn_gravar.click(no_wait_after=True)
            self.page.wait_for_timeout(3500)

            # Confirma SweetAlerts
            for _ in range(2):
                sweet = self.page.locator(".sweet-alert.visible").first
                if sweet.is_visible(timeout=3000):
                    btn_conf = sweet.locator("button.confirm, button:has-text('Sim'), button:has-text('OK')").first
                    btn_conf.click(no_wait_after=True)
                    self.page.wait_for_timeout(2500)

            self.log(f"Acordo do cliente '{dados['nome_cliente']}' GRAVADO com sucesso!", "SUCCESS")
            return True

        except Exception as e:
            self.log(f"Erro ao gravar acordo: {e}", "ERROR")
            return False

    def baixar_boletos_cliente(self, nome_cliente: str, visivel: bool = False) -> Dict[str, Any]:
        self.log(f"Iniciando download dos boletos de '{nome_cliente}'...")
        pasta_destino = obter_pasta_boletos_cliente(nome_cliente)
        boletos_salvos = []

        try:
            self.fechar_modais_ou_telas_ativas()
            self.page.evaluate("if (typeof window.SetaAcao === 'function') window.SetaAcao('Menu', 'frmBoletoAvulso');")
            self.page.wait_for_timeout(1500)
            self.page.wait_for_selector("#tabela, #tabela_filter input", state="visible", timeout=15000)

            # 1. Ajusta para 100 ANTES de pesquisar para não resetar o filtro
            try:
                select_length = self.page.locator('select[name="tabela_length"]').first
                if select_length.is_visible():
                    select_length.select_option('100')
                    self.page.wait_for_timeout(1000)
                    try: self.page.wait_for_selector('#tabela_processing', state='hidden', timeout=8000)
                    except Exception: pass
            except Exception: pass

            # 2. Pesquisa com Enter
            campo_busca = self.page.locator('#tabela_filter input[type="search"], #tabela_filter input').first
            campo_busca.click(force=True)
            campo_busca.fill("")
            campo_busca.fill(nome_cliente)
            self.page.keyboard.press("Enter")
            self.page.wait_for_timeout(2000)

            try:
                self.page.wait_for_selector("#tabela_processing", state="hidden", timeout=10000)
            except Exception: pass
            self.page.wait_for_timeout(800)

            # 3. TRAVA DE SEGURANÇA: Só pega linhas que tenham o nome deste cliente
            norm_cliente = normalizar_texto(nome_cliente)
            partes_cliente = [p for p in norm_cliente.split() if len(p) > 2]

            linhas = self.page.locator('#tabela tbody tr').all()
            linhas_validas = []
            for r in linhas:
                txt = r.inner_text()
                if "nenhum registro" in txt.lower(): continue
                norm_txt = normalizar_texto(txt)
                # Garante que a linha pertence a este cliente
                if partes_cliente and all(p in norm_txt for p in partes_cliente[:2]):
                    if r.locator("button").count() > 0:
                        linhas_validas.append(r)

            total = len(linhas_validas)
            self.log(f"Encontrados exatamente {total} boletos legítimos para '{nome_cliente}'.")
            if total == 0:
                return {"total_encontrados": 0, "total_baixados": 0}

            itens = []
            for r in linhas_validas:
                txt = r.inner_text()
                datas = re.findall(r'\b\d{2}/\d{2}/\d{4}\b', txt)
                venc = datas[1] if len(datas) >= 2 else (datas[0] if datas else "01/01/2099")
                itens.append({"linha": r, "vencimento": venc, "texto": txt})

            def conv_dt(d):
                try: return datetime.strptime(d, "%d/%m/%Y")
                except Exception: return datetime.max
            itens.sort(key=lambda x: conv_dt(x["vencimento"]))

            for idx, item in enumerate(itens, start=1):
                if self._cancelado: break
                venc = item["vencimento"]
                linha_el = item["linha"]
                eh_ent = "ENTRADA" in item["texto"].upper() or "ENT" in item["texto"].upper() or (idx == 1 and "ENT" in item["texto"].upper())

                nome_arq = formatar_nome_arquivo_boleto(venc, eh_entrada=eh_ent, numero_parcela=idx)
                caminho_final = pasta_destino / nome_arq

                if caminho_final.exists() and caminho_final.stat().st_size > 10000:
                    self.log(f"Boleto já existente na pasta ({round(caminho_final.stat().st_size/1024, 1)} KB): {nome_arq}. Pulando download.")
                    boletos_salvos.append({"arquivo": nome_arq, "caminho": str(caminho_final)})
                    continue

                pdf_url = None
                download_obj = None

                def on_resp(resp):
                    nonlocal pdf_url
                    try:
                        u = resp.url.lower()
                        if (".pdf" in u or "application/pdf" in resp.headers.get("content-type", "")) and "about:blank" not in u:
                            pdf_url = resp.url
                    except Exception: pass

                def on_down(d):
                    nonlocal download_obj
                    download_obj = d

                self.page.on("response", on_resp)
                self.page.on("download", on_down)

                btn_imp = linha_el.locator('button[title*="Imprimir" i], button:has(.fa-print)').first
                btn_imp.click(force=True)

                # Boletos já pagos/liquidados de 2025 não abrem PDF; esperar 4s é suficiente
                for _ in range(4):
                    self.page.wait_for_timeout(1000)
                    if pdf_url or download_obj: break

                self.page.remove_listener("response", on_resp)
                self.page.remove_listener("download", on_down)

                if download_obj:
                    download_obj.save_as(str(caminho_final))
                    self.log(f"Boleto salvo via download direto: {nome_arq}")
                    boletos_salvos.append({"arquivo": nome_arq, "caminho": str(caminho_final)})
                elif pdf_url:
                    if pdf_url.startswith("/"):
                        pdf_url = "https://www.globalofficeweb.com.br" + pdf_url
                    resp_bytes = self.page.request.get(pdf_url).body()
                    with open(caminho_final, "wb") as f:
                        f.write(resp_bytes)
                    self.log(f"Boleto salvo ({round(len(resp_bytes)/1024, 1)} KB): {nome_arq}")
                    boletos_salvos.append({"arquivo": nome_arq, "caminho": str(caminho_final)})
                else:
                    self.log(f"Aviso: Timeout ao gerar PDF para o boleto {idx} ({venc}).", "WARNING")

                # Limpa imediatamente o overlay do PDF recém-gerado
                self.fechar_modais_ou_telas_ativas()

            self.log(f"Concluído: {len(boletos_salvos)} de {total} boletos baixados.")
            return {"total_encontrados": total, "total_baixados": len(boletos_salvos)}

        except Exception as e:
            self.log(f"Erro no download de boletos: {e}", "ERROR")
            return {"total_encontrados": 0, "total_baixados": 0}

    def processar_cliente_completo(self, nome_cliente: str, visivel: bool = False, baixar_boletos: bool = True) -> bool:
        self.log("=" * 60)
        self.log(f"INICIANDO ENVIO DO ACORDO JUDICIAL: {nome_cliente}")
        self.log("=" * 60)

        self.garantir_sessao_ativa(visivel=visivel)

        dados = self.parser.carregar_dados_cliente(nome_cliente)
        if not dados.get("sucesso", True):
            self.log(f"Ignorado: {dados.get('motivo_erro', 'Erro ao carregar dados')}", "WARNING")
            return False

        if not dados.get("eh_parcelado", True):
            self.log(f"Ignorado: {nome_cliente} não é parcelado.", "WARNING")
            return False

        # ETAPA 1: Acordo
        ok_tela = self.acessar_cadastro_devedores(visivel=visivel)
        if not ok_tela:
            return False

        achou = self.pesquisar_devedor_no_grid(nome_cliente, visivel=visivel)
        if not achou:
            return False

        abriu = self.abrir_modal_acordo(nome_cliente)
        if abriu is True:
            gravou = self.preencher_e_gravar_acordo(dados)
            if not gravou: return False

        # ETAPA 2: Download dos boletos (executado no máximo UMA ÚNICA VEZ por cliente)
        if baixar_boletos:
            if nome_cliente not in self._clientes_baixados:
                self._clientes_baixados.add(nome_cliente)
                self.baixar_boletos_cliente(nome_cliente, visivel=visivel)
            else:
                self.log(f"Download de boletos para '{nome_cliente}' já executado nesta sessão. Evitando duplicidade.")

        return True

    # Métodos de compatibilidade com a GUI
    def subir_acordo_completo(self, nome_cliente: str, visivel: bool = False) -> bool:
        # Apenas cadastra/sobe o acordo, evitando duplicar o download que a GUI executa na etapa seguinte
        return self.processar_cliente_completo(nome_cliente, visivel=visivel, baixar_boletos=False)

    def verificar_boletos_completos(self, nome_cliente: str) -> dict:
        if hasattr(self.parser, "verificar_boletos_completos"):
            return self.parser.verificar_boletos_completos(nome_cliente)
        if hasattr(self.parser, "verificar_boletos_cliente"):
            return self.parser.verificar_boletos_cliente(nome_cliente)
        return {"completo": False, "existentes": 0, "esperados": 0}

    def verificar_boletos_cliente(self, nome_cliente: str) -> dict:
        return self.verificar_boletos_completos(nome_cliente)

    def carregar_dados_cliente(self, nome_cliente: str) -> dict:
        return self.parser.carregar_dados_cliente(nome_cliente)

    def lista_parcelados_planilha(self, caminho_planilha: Optional[str] = None) -> list:
        try:
            if caminho_planilha:
                self.parser.caminho_planilha = Path(caminho_planilha)

            ws = self.parser._obter_worksheet()
            if ws is None: return []

            header = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
            col_map = {}
            for idx, h in enumerate(header, 1):
                if h: col_map[normalizar_texto(str(h))] = idx

            idx_nome = col_map.get("BENEFICIARIO", 3)
            idx_cond = col_map.get("CONDICOES DO ACORDO", 7)

            clientes = []
            for r in range(2, ws.max_row + 1):
                val_nome = ws.cell(r, idx_nome).value
                val_cond = str(ws.cell(r, idx_cond).value or "").strip().upper()
                if val_nome and "PARCEL" in val_cond:
                    n = str(val_nome).strip()
                    if n: clientes.append(n)

            self.log(f"Planilha lida com sucesso: {len(clientes)} clientes PARCELADOS encontrados.")
            return clientes
        except Exception as e:
            self.log(f"Erro ao ler planilha: {e}", "ERROR")
            return []