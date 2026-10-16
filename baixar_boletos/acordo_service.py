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
    obter_user_agent,
    formatar_nome_arquivo_boleto,
    obter_pasta_boletos_cliente,
    mes_inicial_boletos,
    DIAS_VENCIMENTO_ATRASADO,
    situacao_empresa
)
from baixar_boletos.acordo_parser import AcordoParser, normalizar_texto
from baixar_boletos.login_helper import login_manual


SEM_VALORES_GEAP = "SEM_VALORES_GEAP"  # retorno de abrir_modal_acordo para o aviso da GEAP


class ProcessamentoCancelado(Exception):
    """Botão PARAR: interrompe o cliente atual no próximo passo seguro."""


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
        # confirmar_gravacao(resumo) -> bool: pergunta antes de gravar boletos novos.
        # Sem ela (None) o robô preenche, confere e CANCELA, sem gravar.
        self.confirmar_gravacao: Optional[Callable[[str], bool]] = None
        # True quando o último processar_cliente_completo gravou algo (acordo ou boletos avulsos):
        # depois de gravar, a tela de boletos da mesma sessão fica travada.
        self.gravou_algo = False

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

    def _parar_se_cancelado(self):
        if self._cancelado:
            raise ProcessamentoCancelado("processamento parado pelo usuário")

    def _esperar_login_manual(self):
        self.log("Sessão não autenticada. A preencher credenciais...")
        # Criar playwright proprio se o principal foi fechado por fechar_sessao()
        pw_proprio = False
        pw = self.playwright
        if pw is None:
            pw = sync_playwright().start()
            pw_proprio = True

        try:
            login_manual(pw, self.log)
        finally:
            if pw_proprio:
                try: pw.stop()
                except Exception: pass

    def fechar_sessao(self):
        # Cada passo isolado: um close() com erro (navegador já fechado) não pode impedir o
        # stop(), senão a próxima sessão falha com "Sync API inside the asyncio loop".
        for passo in (lambda: self.context and self.context.close(),
                      lambda: self.browser and self.browser.close(),
                      lambda: self.playwright and self.playwright.stop()):
            try:
                passo()
            except Exception:
                pass
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
            user_agent=obter_user_agent(),
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

                # O botão de confirmar é obrigatório para a empresa ficar ativa. Espera o
                # popup aparecer (até 10s) e confirma via JS (o IWLocker bloqueia clique real).
                # Se vier mais de um popup em sequência, confirma cada um.
                confirmou = False
                for _ in range(3):
                    sweet = self.page.locator(".sweet-alert.visible, .swal2-popup").first
                    try:
                        sweet.wait_for(state="visible", timeout=10000 if not confirmou else 3000)
                    except Exception:
                        break
                    txt = " ".join(sweet.inner_text().split())[:80]
                    self.log(f"Confirmando popup de empresa principal: '{txt}'")
                    sweet.locator("button.confirm, .swal2-confirm").first.evaluate("el => el.click()")
                    confirmou = True
                    self.page.wait_for_timeout(2500)
                    try:
                        self.page.wait_for_load_state("load", timeout=10000)
                    except Exception:
                        pass
                if not confirmou:
                    self.log("Popup de confirmação da empresa NÃO apareceu; empresa pode não ter sido selecionada.", "WARNING")

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

                // NÃO clica em nenhum botão (cliques cegos disparavam ações do sistema,
                // como o registro de horário): só remove overlays do DOM.

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


    def pesquisar_devedor_no_grid(self, nome_cliente: str, visivel: bool = False, cpf: str = "") -> bool:
        self.log(f"Pesquisando devedor no grid: '{nome_cliente}'...")
        cpf = re.sub(r"\D", "", str(cpf or "")).zfill(11) if re.sub(r"\D", "", str(cpf or "")) else ""

        def tem_cpf(txt):
            dig = re.sub(r"\D", "", txt)
            return bool(cpf) and (cpf in dig or (len(cpf.lstrip("0")) >= 8 and cpf.lstrip("0") in dig))
        try:
            # Busca flexível: nome completo -> primeiro + último -> primeiro + segundo.
            # Com CPF: também pesquisa pelo CPF (homônimos: dois devedores com o mesmo nome).
            nome_limpo = " ".join(nome_cliente.split())
            partes_nome = nome_limpo.split()
            termos_busca = [nome_limpo]
            if cpf:
                termos_busca += [f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}", cpf]
            if len(partes_nome) > 2:
                termos_busca.append(f"{partes_nome[0]} {partes_nome[-1]}")
                termos_busca.append(f"{partes_nome[0]} {partes_nome[1]}")
            homonimos = []

            norm_cliente = normalizar_texto(nome_limpo)
            partes = [p for p in norm_cliente.split() if len(p) > 2]

            for termo in termos_busca:
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
                        self.page.keyboard.type(termo, delay=60)
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
                    self.log(f"Sem resultados para '{termo}'.", "INFO")
                    continue

                linhas = self.page.locator("#tabela tbody tr").all()
                if not linhas:
                    continue

                # TRAVA DE NOME: só aceita a linha cujo nome tenha o primeiro E o último
                # nome (palavras inteiras) do cliente pesquisado. Nunca "qualquer linha".
                candidatas = []          # (índice, texto) das linhas com o nome do cliente
                for i, ln in enumerate(linhas):
                    try:
                        txt = ln.inner_text().strip()
                    except Exception:
                        continue
                    if not txt or "nenhum registro" in txt.lower():
                        continue
                    celula_nome = normalizar_texto(re.split(r"[\t\n]", txt)[0])
                    palavras = set(celula_nome.split())
                    if partes and partes[0] in palavras and partes[-1] in palavras:
                        candidatas.append((i, txt))
                    else:
                        self.log(f"Linha {i + 1} não confere com '{nome_cliente}': {txt[:50]}...", "WARNING")

                if not candidatas:
                    continue
                com_cpf = [c for c in candidatas if tem_cpf(c[1])]
                exatas = [c for c in candidatas
                          if normalizar_texto(re.split(r"[\t\n]", c[1])[0]) == norm_cliente]
                if com_cpf:
                    idx_ok = com_cpf[0][0]
                    self.log(f"Devedor conferido pelo CPF {cpf}.")
                elif cpf and len(candidatas) > 1:
                    # Mais de um devedor com o nome e o grid não mostra o CPF: não escolhe às cegas
                    homonimos = [c[1].replace("\t", " | ")[:90] for c in candidatas]
                    self.log(f"{len(candidatas)} devedor(es) com o nome '{nome_cliente}' na busca '{termo}' "
                             f"e nenhum com o CPF {cpf} visível: {homonimos}", "WARNING")
                    continue
                else:
                    idx_ok = (exatas or candidatas)[0][0]

                self._linha_devedor = idx_ok
                self.log(f"Devedor '{nome_cliente}' localizado no grid (linha {idx_ok + 1}) com a busca '{termo}'.", "SUCCESS")
                return True

            if homonimos:
                self.log(f"HOMÔNIMOS: há mais de um '{nome_cliente}' no Cadastro de devedores e não consegui "
                         f"confirmar qual é o do CPF {cpf}. O acordo NÃO será subido no devedor errado.", "ERROR")
            self.log(f"Devedor '{nome_cliente}' NÃO foi localizado no grid após {len(termos_busca)} tentativa(s).", "WARNING")
            return False

        except Exception as e:
            self.log(f"Erro ao pesquisar devedor: {e}", "ERROR")
            return False

    def abrir_modal_acordo(self, nome_cliente: str = "") -> Optional[bool]:
        self.log("Abrindo formulário de Acordo Judicial (ícone mãos dadas)...")
        try:
            self.fechar_modais_ou_telas_ativas()
            self.dispensar_popup_horario()
            self.page.wait_for_timeout(600)
            linha = self.page.locator("#tabela tbody tr").nth(getattr(self, "_linha_devedor", 0))
            linha.wait_for(state="visible", timeout=8000)

            texto_linha = linha.inner_text().lower()
            if "já tem acordo" in texto_linha or "ja tem acordo" in texto_linha:
                self.log(f"O devedor '{nome_cliente}' JÁ POSSUI ACORDO CADASTRADO no sistema.", "SUCCESS")
                return None

            # Caminho único: somente o ícone de mãos dadas. Sem "chutes" por onclick/title,
            # que podiam clicar em outro botão da linha.
            btn = linha.locator("button:has(.fa-handshake-o), button:has(.fa-handshake), a:has(.fa-handshake-o), a:has(.fa-handshake)").first
            if not btn.is_visible(timeout=4000):
                acoes = linha.locator("td").last.inner_html()
                self.log(f"Ícone de mãos dadas não encontrado. HTML das ações da linha: {acoes[:1500]}", "ERROR")
                return False

            onclick_code = btn.get_attribute("onclick") or ""
            if "SetaAcao" in onclick_code:
                self.page.evaluate(f"() => {{ {onclick_code} }}")
            else:
                btn.evaluate("el => el.click()")

            # Espera o formulário OU um aviso do sistema (o aviso da GEAP pode demorar a vir)
            modal = self.page.locator("#Cadastro, div[role='dialog']").filter(has_text="Acordos Judiciais").first
            sweet = self.page.locator(".sweet-alert.visible").first
            for _ in range(60):
                self.page.wait_for_timeout(500)
                if modal.is_visible() or sweet.is_visible():
                    break
            if not modal.is_visible() and not sweet.is_visible():
                try:
                    from baixar_boletos.config import USER_DATA_DIR
                    self.page.screenshot(path=str(Path(USER_DATA_DIR) / "ultimo_acordo_nao_abriu.png"))
                except Exception:
                    pass
                self.log("O formulário do acordo não abriu em 30 s e nenhum aviso apareceu "
                         "(print salvo em ultimo_acordo_nao_abriu.png).", "ERROR")
                return False
            if sweet.is_visible():
                txt_alerta = sweet.inner_text()
                self.log(f"Aviso/Popup detectado na tela: {txt_alerta[:80]}...", "WARNING")
                # Nova regra: sem valores em aberto na GEAP o acordo não é subido;
                # os boletos que faltam são criados manualmente em Boletos > +NOVO.
                if "FICHA FINANCEIRA NAO ATUALIZADA" in normalizar_texto(txt_alerta):
                    sweet.locator("button.confirm").first.evaluate("el => el.click()")
                    self.log("GEAP sem valores em aberto: o acordo não será subido; seguir pela criação de boletos.", "WARNING")
                    return SEM_VALORES_GEAP
                btn_ok = sweet.locator("button.confirm, button:has-text('OK'), button:has-text('Confirmar'), button:has-text('Sim')").first
                if btn_ok.is_visible():
                    # IWLocker intercepta cliques reais: clica via JS e libera o lock
                    btn_ok.evaluate("el => el.click()")
                    self.page.wait_for_timeout(1500)
                    try:
                        self.page.wait_for_load_state("load", timeout=10000)
                    except Exception:
                        pass
                    # O popup recarrega a página e fecha o formulário: força nova tentativa
                    if not self.page.locator("#tabela tbody tr").first.is_visible():
                        self.log("Página recarregada pelo popup de horário; reiniciando o fluxo.", "WARNING")
                        return False
                    self.page.evaluate("""() => {
                        if (typeof window.ReleaseLock === 'function') window.ReleaseLock();
                        window.GActivateLock = false;
                        const lk = document.getElementById('IWLocker');
                        if (lk) lk.style.display = 'none';
                    }""")

            modal.wait_for(state="visible", timeout=15000)
            self.log("Formulário 'INCLUSÃO DE ACORDOS JUDICIAIS' aberto com sucesso!", "SUCCESS")
            return True
        except Exception as e:
            self.log(f"Erro ao abrir modal de acordos: {e}", "ERROR")
            return False


    # ── Boletos > +NOVO (aviso "Ficha financeira não atualizada") ──
    def _abrir_tela_boletos(self) -> bool:
        self.fechar_modais_ou_telas_ativas()
        for _ in range(2):
            try:
                self.page.evaluate("if (typeof window.SetaAcao === 'function') window.SetaAcao('Menu', 'frmBoletoAvulso');")
                self.page.wait_for_selector("#tabela_filter input", state="visible", timeout=25000)
                self.page.wait_for_timeout(1500)
                return True
            except Exception as e:
                self.log(f"Tela de boletos não abriu ({e}). Tentando de novo...", "WARNING")
                self.page.wait_for_timeout(2000)
        return False

    def _empresa_ac_ativa(self, estrito: bool = False) -> bool:
        """Na tela de Boletos, o Modelo 'SICOOB- AC' só existe com a empresa AC COBRANÇA ativa
        (em outra empresa aparecem 'BB ALDRIGUES' / 'SICOOB ALDRIGUES'). Lista ainda vazia
        (comum logo após gravar um acordo) só reprova no modo estrito (antes de gravar)."""
        situacao = situacao_empresa(self.page)
        if situacao == "INDEFINIDO":
            self.log("Lista de modelos da tela de boletos não carregou: empresa não confirmada.", "WARNING")
            return not estrito
        return situacao == "AC"

    def _garantir_empresa_ac_na_tela_boletos(self, estrito: bool = True) -> bool:
        if not self._abrir_tela_boletos():
            return False
        situacao = situacao_empresa(self.page)
        if situacao == "AC" or (situacao == "INDEFINIDO" and not estrito):
            return True
        if situacao == "INDEFINIDO":
            # Antes de gravar: reabre a tela e confere de novo, sem trocar de empresa à toa
            if self._abrir_tela_boletos():
                situacao = situacao_empresa(self.page)
                if situacao == "AC":
                    return True
            if situacao == "INDEFINIDO":
                # O filtro de modelos às vezes não carrega. A trava passa a ser o formulário
                # +NOVO: o Modelo 'SICOOB- AC' só aparece lá com a AC COBRANÇA ativa.
                self.log("Filtro de modelos vazio; a empresa será conferida pelo Modelo 'SICOOB- AC' do formulário.", "WARNING")
                return True
        self.log("A empresa ativa NÃO é a AC COBRANÇA (alguém trocou a empresa neste login?). Selecionando de novo...", "WARNING")
        self._selecionar_empresa()
        if self._abrir_tela_boletos() and situacao_empresa(self.page) == "AC":
            return True
        self.log("Não consegui ativar a empresa AC COBRANÇA. Nada será gravado.", "ERROR")
        return False

    def _marcar_situacao(self, radio_id: str):
        """O filtro Situação recarrega a tela: marca o rádio e espera a tabela voltar."""
        pg = self.page
        if pg.evaluate(f"(document.getElementById('{radio_id}')||{{}}).checked === true"):
            return
        try:
            pg.evaluate(f"document.getElementById('{radio_id}').click()")
        except Exception:
            pass  # a própria recarga pode derrubar o evaluate
        pg.wait_for_timeout(1500)
        for _ in range(3):
            try:
                pg.wait_for_load_state("domcontentloaded", timeout=15000)
                pg.wait_for_selector("#tabela_filter input", state="visible", timeout=20000)
                pg.wait_for_selector("#tabela_processing", state="hidden", timeout=15000)
                pg.wait_for_timeout(1000)
                if pg.evaluate(f"(document.getElementById('{radio_id}')||{{}}).checked === true"):
                    return
            except Exception:
                pg.wait_for_timeout(1500)

    def _listar_boletos_cliente(self, nome_cliente: str, tentativas: int = 3) -> Optional[list]:
        """Boletos do cliente na tela de Boletos com Situação = Todos: [{venc, valor, status}].
        None se a lista não pôde ser lida com segurança."""
        for t in range(1, tentativas + 1):
            r = self._listar_boletos_cliente_uma_vez(nome_cliente)
            if r is not None:
                return r
            if t < tentativas:
                self.log(f"Releitura da lista de boletos ({t + 1}/{tentativas})...", "WARNING")
                self.page.wait_for_timeout(2000)
        return None

    def _listar_boletos_cliente_uma_vez(self, nome_cliente: str) -> Optional[list]:
        pg = self.page
        try:
            self._marcar_situacao("RDBTNTODOS_INPUT")
            pg.evaluate("window.jQuery('#tabela').DataTable().page.len(100)")
            pg.evaluate("""(nome) => { const i = document.querySelector('#tabela_filter input'); if (i) i.value = nome;
                window.jQuery('#tabela').DataTable().search(nome).draw(); }""", nome_cliente)
            pg.wait_for_timeout(3000)
            try:
                pg.wait_for_selector("#tabela_processing", state="hidden", timeout=15000)
            except Exception:
                pass
            if (pg.evaluate("(document.querySelector('input[name=situacao]:checked')||{}).id") != "RDBTNTODOS_INPUT"
                    or pg.evaluate("(document.querySelector('#tabela_filter input')||{}).value") != nome_cliente):
                self.log("Filtro da tela de boletos não ficou como esperado (Todos + nome).", "WARNING")
                return None
            cab = [normalizar_texto(th.inner_text()) for th in pg.locator("#tabela thead th").all()]
            ic = next(i for i, h in enumerate(cab) if "CLIENTE" in h)
            iv = next(i for i, h in enumerate(cab) if h == "VALOR")
            ivc = next(i for i, h in enumerate(cab) if "VENCIMENTO" in h)
            ist = next(i for i, h in enumerate(cab) if "STATUS" in h)
            alvo = normalizar_texto(nome_cliente)
            boletos = []
            for tr in pg.locator("#tabela tbody tr").all():
                tds = [td.inner_text().strip() for td in tr.locator("td").all()]
                if len(tds) <= max(ic, iv, ivc, ist) or normalizar_texto(tds[ic]) != alvo:
                    continue
                boletos.append({"venc": tds[ivc], "valor": tds[iv], "status": normalizar_texto(tds[ist])})
            self.log(f"Boletos de '{nome_cliente}' no sistema (todas as situações): {len(boletos)} "
                     f"| {pg.locator('#tabela_info').inner_text().strip()}")
            return boletos
        except Exception as e:
            self.log(f"Não consegui ler os boletos de '{nome_cliente}': {e}", "WARNING")
            return None

    def _escolher_na_lista(self, campo_id: str, busca: str, prefixo: str, casa_linha) -> Optional[str]:
        """Digita a busca no campo (Cliente/Item), espera a lista do sistema e clica na linha
        aprovada por casa_linha(texto). Devolve o texto da linha escolhida."""
        pg = self.page
        campo = pg.locator(f"#{campo_id}")
        campo.focus()
        campo.press("Control+A")
        campo.press("Backspace")
        campo.press_sequentially(busca, delay=80)
        # A lista vai filtrando enquanto o servidor responde: espera ela mostrar só linhas
        # com o texto completo da busca e parar de mudar (antes pegava 'Abadia Jose...').
        alvo = normalizar_texto(busca)
        linhas, anterior = [], None
        for _ in range(40):
            pg.wait_for_timeout(500)
            linhas = pg.evaluate("""(pfx) => [...document.querySelectorAll('tr')]
                .filter(t => t.offsetParent !== null && (t.getAttribute('onclick')||'').includes("SetaAcao('" + pfx + "'"))
                .map(t => t.innerText.replace(/\\s+/g, ' ').trim())""", prefixo)
            filtrada = linhas and all(alvo in normalizar_texto(t) for t in linhas)
            if filtrada and linhas == anterior:
                break
            anterior = linhas
        escolhidas = [i for i, t in enumerate(linhas) if casa_linha(t)]
        if len(escolhidas) != 1:
            self.log(f"Lista de '{campo_id}': {len(escolhidas)} linha(s) compatíveis em {linhas}. Não vou escolher às cegas.", "WARNING")
            return None
        pg.evaluate("""([pfx, idx]) => { const ts = [...document.querySelectorAll('tr')]
            .filter(t => t.offsetParent !== null && (t.getAttribute('onclick')||'').includes("SetaAcao('" + pfx + "'"));
            ts[idx].click(); }""", [prefixo, escolhidas[0]])
        # o sistema preenche o campo após ida ao servidor: espera o valor mudar
        for _ in range(20):
            pg.wait_for_timeout(500)
            if normalizar_texto(campo.input_value()) != normalizar_texto(busca):
                break
        self.log(f"{campo_id}: escolhida '{linhas[escolhidas[0]]}' -> campo '{campo.input_value()}'")
        # a lista continua aberta por cima do formulário depois da escolha
        pg.evaluate("['LISTACLIENTE', 'LISTAITEM'].forEach(id => { const e = document.getElementById(id); if (e) e.style.display = 'none'; })")
        return linhas[escolhidas[0]]

    def _selecionar_opcao(self, sel_id: str, rotulo: str) -> bool:
        pg = self.page
        for _ in range(20):  # as opções do Modelo recarregam depois do Escritório
            val = pg.evaluate("""([id, r]) => { const s = document.getElementById(id); if (!s) return null;
                const o = [...s.options].find(o => o.text.replace(/\\s+/g, ' ').trim() === r); return o ? o.value : null; }""",
                              [sel_id, rotulo])
            if val is not None:
                pg.select_option(f"#{sel_id}", val)
                pg.wait_for_timeout(1500)
                atual = pg.evaluate(f"((document.getElementById('{sel_id}').selectedOptions[0])||{{}}).text || ''")
                if " ".join(atual.split()) == rotulo:
                    return True
            pg.wait_for_timeout(500)
        self.log(f"Não consegui selecionar '{rotulo}' em {sel_id}.", "ERROR")
        return False

    def _cancelar_inclusao(self):
        try:
            self.page.evaluate("""() => { const b = [...document.querySelectorAll('button')]
                .find(b => b.offsetParent !== null && b.innerText.trim().toUpperCase() === 'CANCELAR'); if (b) b.click(); }""")
            self.page.wait_for_timeout(1500)
        except Exception:
            pass

    def criar_boletos_faltantes(self, nome_cliente: str, dados: Dict[str, Any],
                                motivo: str = "aviso da GEAP (sem valores em aberto)") -> bool:
        try:
            return self._criar_boletos_faltantes(nome_cliente, dados, motivo)
        finally:
            # o download seguinte espera a lista no filtro padrão (Em aberto)
            try:
                if self.page and not self.page.is_closed() and self.page.locator("#RDBTNEMABERTO_INPUT").count():
                    self._marcar_situacao("RDBTNEMABERTO_INPUT")
            except Exception:
                pass

    def _criar_boletos_faltantes(self, nome_cliente: str, dados: Dict[str, Any], motivo: str) -> bool:
        """Boletos > +NOVO para as parcelas que faltam (aviso 'Ficha financeira não atualizada').
        Vencimento = primeiro boleto que falta; Repetição = total de boletos. Só grava se:
        empresa AC COBRANÇA ativa, lista lida com segurança, faltantes em meses seguidos,
        cliente achado pelo CPF, todos os campos conferidos e confirmar_gravacao aprovar."""
        try:
            from baixar_boletos.boletos_faltantes import calcular_faltantes, repeticao_para
        except ImportError:
            from boletos_faltantes import calcular_faltantes, repeticao_para
        pg = self.page
        self.log(f"'{nome_cliente}': {motivo}. Indo criar os boletos pela tela de Boletos.")

        valor = str(dados.get("valor_parcela_boleto") or dados.get("valor_parcela") or "")
        qtd = int(dados.get("qtd_parcelas") or 0)
        primeiro = dados.get("primeiro_vencimento") or ""
        cpf = re.sub(r"\D", "", str(dados.get("cpf") or ""))
        if not (valor and qtd and primeiro and cpf):
            self.log(f"Dados incompletos para criar boletos (valor={valor!r}, parcelas={qtd}, "
                     f"1º venc={primeiro!r}, cpf={cpf!r}). Fazer manualmente.", "ERROR")
            return False

        if not self._garantir_empresa_ac_na_tela_boletos():
            return False
        boletos = self._listar_boletos_cliente(nome_cliente)
        if boletos is None:
            return False

        def centavos(v):
            d = re.sub(r"\D", "", str(v))
            return int(d) if d else -1
        # Só parcelas (mesmo valor da parcela) e não canceladas; a entrada fica de fora
        existentes = [b["venc"] for b in boletos
                      if "CANCEL" not in b["status"] and abs(centavos(b["valor"]) - centavos(valor)) <= 5]
        # Regra do mês vigente (dia 25 em diante = mês seguinte): meses anteriores ficam de fora.
        # O Global Office recusa vencimento no passado (erro 5002): a parcela deste mês cujo dia
        # já passou é criada para daqui a DIAS_VENCIMENTO_ATRASADO dias; as demais nas datas normais.
        from datetime import date as _date, timedelta as _td
        hoje = _date.today()
        ano_ini, mes_ini = mes_inicial_boletos()
        a_partir = _date(ano_ini, mes_ini, 1)
        calc = calcular_faltantes(primeiro, qtd, existentes, a_partir=a_partir)
        self.log(f"Parcelas: {calc['esperados']} esperadas, {calc['existentes']} já no sistema, "
                 f"{len(calc['faltantes'])} a criar (a partir de {a_partir:%m/%Y}).")
        if calc["vencidos"]:
            self.log(f"{len(calc['vencidos'])} parcela(s) de meses anteriores sem boleto ("
                     + ", ".join(d.strftime("%m/%Y") for d in calc["vencidos"])
                     + "): ficam de fora pela regra do mês vigente.", "WARNING")
        if not calc["faltantes"]:
            self.log(f"'{nome_cliente}' já tem todos os boletos das parcelas que ainda vão vencer. Nada a gerar.", "SUCCESS")
            return True
        if not calc["seguro"]:
            self.log("Os boletos que faltam NÃO são meses seguidos ("
                     + ", ".join(d.strftime("%m/%Y") for d in calc["faltantes"])
                     + "). A Repetição recriaria parcelas existentes: fazer manualmente.", "WARNING")
            return False

        # Lotes de gravação: (vencimento, repetição, descrição)
        novo_venc = hoje + _td(days=DIAS_VENCIMENTO_ATRASADO)
        atrasados = [d for d in calc["faltantes"] if d < hoje]
        normais = [d for d in calc["faltantes"] if d >= hoje]
        lotes = [(novo_venc.strftime("%d/%m/%Y"), 0,
                  f"1 boleto: parcela de {d:%d/%m/%Y} (dia já passou) com vencimento em {novo_venc:%d/%m/%Y}")
                 for d in atrasados]
        if normais:
            lotes.append((normais[0].strftime("%d/%m/%Y"), repeticao_para(len(normais)),
                          f"{len(normais)} boleto(s), de {normais[0]:%d/%m/%Y} até {normais[-1]:%d/%m/%Y}"))
        for n, (venc_lote, rep_lote, desc) in enumerate(lotes, 1):
            if len(lotes) > 1:
                desc += f"  [gravação {n} de {len(lotes)}]"
            if n > 1:
                pg.wait_for_timeout(3000)
                if not self._abrir_tela_boletos():
                    self.log("Tela de boletos não reabriu para a próxima gravação. Confira no sistema.", "ERROR")
                    return False
            if not self._gravar_boleto_novo(nome_cliente, dados, cpf, valor, venc_lote, rep_lote,
                                            motivo, desc, calc):
                return False

        # Confere que os boletos apareceram
        pg.wait_for_timeout(3000)
        if not self._abrir_tela_boletos():
            self.log("Gravado, mas não consegui reabrir a tela para conferir. Confira no sistema.", "WARNING")
            return True
        depois = self._listar_boletos_cliente(nome_cliente) or []
        novos = calcular_faltantes(primeiro, qtd, [b["venc"] for b in depois
                                                   if "CANCEL" not in b["status"] and abs(centavos(b["valor"]) - centavos(valor)) <= 5],
                                   a_partir=a_partir)
        if novos["faltantes"]:
            self.log(f"Depois de gravar ainda faltam {len(novos['faltantes'])} boleto(s) de '{nome_cliente}'. Confira no sistema.", "WARNING")
            return False
        self.log(f"Boletos de '{nome_cliente}' criados e conferidos: {novos['existentes']}/{novos['esperados']} parcelas no sistema.", "SUCCESS")
        return True

    def reemitir_boleto_vencido_mes(self, nome_cliente: str, visivel: bool = False) -> Optional[list]:
        try:
            return self._reemitir_boleto_vencido_mes(nome_cliente, visivel)
        finally:
            try:
                if self.page and not self.page.is_closed() and self.page.locator("#RDBTNEMABERTO_INPUT").count():
                    self._marcar_situacao("RDBTNEMABERTO_INPUT")
            except Exception:
                pass

    def _reemitir_boleto_vencido_mes(self, nome_cliente: str, visivel: bool = False) -> Optional[list]:
        """Boleto do mês vigente que venceu sem ter sido enviado: cria um avulso igual (mesmo
        valor) com vencimento daqui a DIAS_VENCIMENTO_ATRASADO dias. O vencido continua no
        sistema (o download passa a pegar o novo). Devolve os novos vencimentos ([] = nada
        a fazer) ou None se não deu para conferir/gravar."""
        from datetime import date as _date, timedelta as _td
        hoje = _date.today()
        if mes_inicial_boletos(hoje) != (hoje.year, hoje.month):
            return []   # a partir do dia 25 o mês atual já não é enviado
        dados = self.parser.carregar_dados_cliente(nome_cliente)
        # Pelo termo: se nenhum vencimento deste mês já passou, nem abre o Global Office
        try:
            from baixar_boletos.boletos_faltantes import cronograma_parcelas, _para_data
            datas = cronograma_parcelas(dados.get("primeiro_vencimento"), int(dados.get("qtd_parcelas") or 0))
            if dados.get("data_entrada"):
                datas.append(_para_data(dados["data_entrada"]) or hoje.replace(day=1))
            if datas and not any((d.year, d.month) == (hoje.year, hoje.month) and d < hoje for d in datas):
                return []
        except Exception:
            pass   # termo ilegível: confere direto no sistema
        self.garantir_sessao_ativa(visivel=visivel)
        cpf = re.sub(r"\D", "", str(dados.get("cpf") or ""))
        if not cpf:
            self.log(f"'{nome_cliente}': sem CPF na planilha, não dá para reemitir o boleto vencido.", "WARNING")
            return None
        if not self._garantir_empresa_ac_na_tela_boletos():
            return None
        boletos = self._listar_boletos_cliente(nome_cliente)
        if boletos is None:
            return None

        def data(v):
            try:
                return datetime.strptime(v.strip()[:10], "%d/%m/%Y").date()
            except Exception:
                return None
        pago = ("PAGO", "QUITAD", "LIQUIDAD", "BAIXAD")
        do_mes = [(data(b["venc"]), b) for b in boletos]
        do_mes = [(d, b) for d, b in do_mes if d and (d.year, d.month) == (hoje.year, hoje.month)]
        if any(any(s in b["status"] for s in pago) for _, b in do_mes):
            return []   # o deste mês já foi pago
        abertos = [(d, b) for d, b in do_mes if "CANCEL" not in b["status"]]
        vencidos = [(d, b) for d, b in abertos if d < hoje]
        if not vencidos:
            return []
        if any(d >= hoje for d, _ in abertos):
            self.log(f"'{nome_cliente}': o boleto vencido deste mês já foi reemitido antes.")
            return []

        novo = hoje + _td(days=DIAS_VENCIMENTO_ATRASADO)
        feitos = []
        for n, (d, b) in enumerate(vencidos, 1):
            valor = re.sub(r"[^\d.,]", "", b["valor"])
            if n > 1:
                self.page.wait_for_timeout(3000)
                if not self._abrir_tela_boletos():
                    return None
            ok = self._gravar_boleto_novo(
                nome_cliente, dados, cpf, valor, novo.strftime("%d/%m/%Y"), 0,
                f"boleto de {d:%d/%m/%Y} venceu sem ter sido enviado",
                f"1 boleto novo (R$ {valor}) com vencimento em {novo:%d/%m/%Y}, no lugar do vencido em {d:%d/%m/%Y}",
                None)
            if not ok:
                return None
            self.gravou_algo = True
            feitos.append(novo.strftime("%d/%m/%Y"))
            self.log(f"'{nome_cliente}': boleto vencido em {d:%d/%m/%Y} reemitido para {novo:%d/%m/%Y}.", "SUCCESS")
        return feitos

    def _gravar_boleto_novo(self, nome_cliente: str, dados: Dict[str, Any], cpf: str, valor: str,
                            vencimento: str, repeticao: int, motivo: str, descricao: str,
                            calc: Optional[dict]) -> bool:
        """Boletos > +NOVO: preenche, confere, pede confirmação e grava UM lançamento
        (Vencimento + Repetição). True só se o sistema não recusar."""
        pg = self.page

        def centavos(v):
            d = re.sub(r"\D", "", str(v))
            return int(d) if d else -1

        # +Novo
        try:
            self.fechar_modais_ou_telas_ativas()
            pg.evaluate("SetaAcao('Inc')")
            pg.wait_for_selector("#EDTCLIENTE", state="visible", timeout=20000)
            pg.wait_for_timeout(1500)
            ok = (self._selecionar_opcao("CBXESCRITORIOSINC", "Unidade Brasilia")
                  and self._selecionar_opcao("CBXMODELO", "SICOOB- AC")
                  and self._selecionar_opcao("CBXPADRAORECEITA", "Honorario_dentro"))
            if not ok:
                self.log("Formulário +NOVO não aceitou Escritório/Modelo 'SICOOB- AC'/Receita: a empresa "
                         "ativa pode não ser a AC COBRANÇA. Nada gravado.", "ERROR")
                self._cancelar_inclusao()
                return False

            # Cliente pelo CPF (a lista mostra o CPF sem zeros à esquerda)
            cpf_sem_zero = cpf.lstrip("0")
            partes = normalizar_texto(nome_cliente).split()
            def casa_cpf(t):
                return re.sub(r"\D", "", t).lstrip("0") == cpf_sem_zero
            linha_cli = self._escolher_na_lista("EDTCLIENTE", " ".join(partes[:3]), "CLIEN", casa_cpf)
            if not linha_cli and len(partes) > 3:
                # A lista mostra no máximo 50 nomes: com o nome completo ela fica bem menor
                linha_cli = self._escolher_na_lista("EDTCLIENTE", " ".join(partes), "CLIEN", casa_cpf)
            if not linha_cli or normalizar_texto(pg.locator("#EDTCLIENTE").input_value()) != normalizar_texto(nome_cliente):
                self.log(f"Cliente com CPF {dados.get('cpf')} não confirmado na lista do sistema "
                         f"(linha={linha_cli!r}, campo={pg.locator('#EDTCLIENTE').input_value()!r}). Nada gravado.", "ERROR")
                self._cancelar_inclusao()
                return False

            linha_item = self._escolher_na_lista(
                "EDTITEM", "Presta", "ITEM", lambda t: "SERVICO DE COBRANCA" in normalizar_texto(t))
            if not linha_item:
                self._cancelar_inclusao()
                return False

            campo_valor = pg.locator("#EDTVALOR")
            if not self._preencher_valor(campo_valor, valor):
                self.log(f"Valor {valor} não ficou no campo. Nada gravado.", "ERROR")
                self._cancelar_inclusao()
                return False
            venc = pg.locator("#EDTVENCIMENTO")
            venc.focus(); venc.press("Control+A"); venc.press("Backspace")
            venc.press_sequentially(re.sub(r"\D", "", vencimento), delay=60)
            rep = pg.locator("#EDTREPETICAO")
            rep.focus(); rep.press("Control+A"); rep.press("Backspace")
            rep.press_sequentially(str(repeticao), delay=60)
            pg.locator("#MMINSTRUCOES").focus()
            pg.wait_for_timeout(1000)

            lido = {
                "cliente": pg.locator("#EDTCLIENTE").input_value(),
                "item": pg.locator("#EDTITEM").input_value(),
                "valor": campo_valor.input_value(),
                "vencimento": venc.input_value(),
                "repeticao": rep.input_value(),
            }
            conferido = (normalizar_texto(lido["cliente"]) == normalizar_texto(nome_cliente)
                         and "SERVICO DE COBRANCA" in normalizar_texto(lido["item"])
                         and centavos(lido["valor"]) == centavos(valor)
                         and lido["vencimento"] == vencimento
                         and lido["repeticao"].strip() == str(repeticao))
            if pg.locator("#CKBEMAIL_CHECKBOX").is_checked() or pg.locator("#CKBREPLICAR_CHECKBOX").is_checked():
                conferido = False
            # fecha listas de busca e calendário que ficam por cima do formulário
            pg.evaluate("""() => {
                ['LISTACLIENTE', 'LISTAITEM'].forEach(id => { const e = document.getElementById(id);
                    if (e) e.style.display = 'none'; });
                try { window.jQuery('#EDTVENCIMENTO').datepicker('hide'); } catch (e) {}
                document.querySelectorAll('.datepicker.dropdown-menu').forEach(d => d.style.display = 'none');
                if (document.activeElement) document.activeElement.blur(); }""")
            pg.wait_for_timeout(500)
            try:
                from baixar_boletos.config import USER_DATA_DIR
                pg.screenshot(path=str(Path(USER_DATA_DIR) / "ultimo_boleto_novo.png"))
            except Exception:
                pass
            if not conferido:
                self.log(f"Conferência do formulário falhou: {lido}. Nada gravado.", "ERROR")
                self._cancelar_inclusao()
                return False

            cpf_m = re.sub(r"\D", "", str(dados.get("cpf") or ""))
            cpf_m = f"***.{cpf_m[3:6]}.***-{cpf_m[-2:]}" if len(cpf_m) == 11 else "sem CPF"   # log/diálogo não guardam o CPF inteiro
            resumo = (f"Motivo: {motivo}\n\n{nome_cliente} (CPF {cpf_m})\n"
                      f"Item: {lido['item']}\nValor: R$ {lido['valor']}\n"
                      f"Vencimento: {lido['vencimento']}  |  Repetição: {lido['repeticao']}\n"
                      f"= {descricao}"
                      + (f"\n(já existem {calc['existentes']} de {calc['esperados']} parcelas)" if calc else "")
                      + (f"\n\nFICAM DE FORA {len(calc['vencidos'])} parcela(s) de meses anteriores: "
                         + ", ".join(d.strftime("%m/%Y") for d in calc["vencidos"]) if calc and calc["vencidos"] else ""))
            self.log("Formulário conferido:\n" + resumo)
            if (self._cancelado or not self.confirmar_gravacao or not self.confirmar_gravacao(resumo)
                    or self._cancelado):
                self.log("Gravação NÃO confirmada: formulário cancelado, nada gravado.", "WARNING")
                self._cancelar_inclusao()
                return False

            pg.evaluate("""() => { const b = [...document.querySelectorAll('button')]
                .find(b => b.offsetParent !== null && (b.getAttribute('onclick')||'').includes('Gravar()')); if (b) b.click(); }""")
            pg.wait_for_timeout(5000)
            msg = ""
            try:
                msg = " ".join(pg.locator(".sweet-alert.visible, .sweet-alert.showSweetAlert").first
                               .inner_text(timeout=8000).split())
                self.log(f"Mensagem do sistema: {msg[:200]}")
                pg.evaluate("() => { const b = document.querySelector('.sweet-alert.visible button.confirm'); if (b) b.click(); }")
                pg.wait_for_timeout(2000)
            except Exception:
                pass
            if "ERRO" in normalizar_texto(msg):
                self.log(f"O Global Office RECUSOU os boletos de '{nome_cliente}': {msg[:200]}. Nada foi gravado.", "ERROR")
                self._cancelar_inclusao()
                return False
        except Exception as e:
            self.log(f"Erro no formulário de novo boleto: {e}", "ERROR")
            self._cancelar_inclusao()
            return False
        return True

    def _preencher_valor(self, campo, valor_br: str) -> bool:
        """Apaga o conteúdo do campo de moeda e digita `valor_br` (ex.: '9.825,76').
        Confere o resultado pelos dígitos; se a máscara do campo atrapalhar, grava via JS."""
        alvo = re.sub(r"\D", "", valor_br)
        try:
            campo.click(force=True)
            campo.press("Control+A")
            campo.press("Delete")
            campo.press_sequentially(valor_br, delay=40)
            campo.press("Tab")
            self.page.wait_for_timeout(300)
            if re.sub(r"\D", "", campo.input_value()) == alvo:
                return True

            campo.evaluate("""(el, v) => {
                el.value = v;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.dispatchEvent(new Event('blur'));
            }""", valor_br)
            self.page.wait_for_timeout(300)
            return re.sub(r"\D", "", campo.input_value()) == alvo
        except Exception as e:
            self.log(f"Erro ao preencher valor: {e}", "ERROR")
            return False

    def selecionar_processo_pela_lupa(self, processo: str) -> bool:
        """Lupa (Localizar processo) > pesquisa pelo número > botão azul 'Selecionar' da linha
        cujo número confere. Ao selecionar, o sistema volta ao formulário do acordo."""
        self.log(f"Localizando processo '{processo}' pela lupa...")
        digitos = re.sub(r"\D", "", processo)
        try:
            modal = self.page.locator("#Cadastro, div[role='dialog']").filter(has_text="Acordos Judiciais").first
            modal.locator("button[title='Localizar processo']").first.evaluate("el => el.click()")
            self.page.wait_for_selector("#tabela_filter input", state="visible", timeout=25000)
            self.page.wait_for_timeout(2000)

            for termo in (processo, digitos):
                campo = self.page.locator("#tabela_filter input").first
                campo.click(force=True)
                self.page.keyboard.press("Control+A")
                self.page.keyboard.press("Backspace")
                self.page.wait_for_timeout(1500)
                campo.press_sequentially(termo, delay=90)

                # espera o grid filtrar (o grid tem ~41 mil registros e demora)
                self.page.wait_for_timeout(1500)
                for _ in range(40):
                    info = self.page.locator("#tabela_info").inner_text()
                    if re.search(r"de [\d.]{1,3}\.\d{3} registros", info) is None and "Mostrando" in info:
                        break
                    self.page.wait_for_timeout(1000)
                self.page.wait_for_timeout(1500)

                linhas = self.page.locator("#tabela tbody tr")
                for i in range(linhas.count()):
                    txt = linhas.nth(i).inner_text()
                    if digitos and digitos in re.sub(r"\D", "", txt):
                        self.log(f"Processo localizado no grid (linha {i + 1}). Selecionando...")
                        linhas.nth(i).locator("button[title='Selecionar']").first.evaluate("el => el.click()")
                        modal.wait_for(state="visible", timeout=40000)
                        self.page.wait_for_timeout(1500)
                        valor = self.page.locator("#EDTPROCESSO").first.input_value().strip()
                        if re.sub(r"\D", "", valor) == digitos:
                            self.log(f"Processo '{valor}' selecionado no formulário.", "SUCCESS")
                            return True
                        self.log(f"Processo no formulário ('{valor}') diferente do esperado.", "ERROR")
                        return False
                self.log(f"Processo não encontrado pesquisando por '{termo}'.", "WARNING")

            return False
        except Exception as e:
            self.log(f"Erro ao selecionar processo pela lupa: {e}", "ERROR")
            return False

    def _conferir_valores(self, dados: Dict[str, Any]) -> bool:
        """Antes de subir o acordo: o termo manda (o parser já trocou os valores da planilha
        pelos do termo). Pede confirmação quando o termo não pôde ser lido ou quando a conta
        do próprio termo não fecha (entrada + parcelas ≠ valor do acordo)."""
        def centavos(v):
            d = re.sub(r"\D", "", str(v or ""))
            return int(d) if d else 0
        rotulos = {"valor_entrada": "Entrada", "data_entrada": "Data da entrada", "qtd_parcelas": "Parcelas",
                   "valor_parcela": "Valor da parcela", "primeiro_vencimento": "1º vencimento"}
        linhas = [f"{r}: {dados.get(k) or '-'}  ({dados.get('origem_' + k, 'planilha')})" for k, r in rotulos.items()]
        linhas.append(f"Valor do acordo: R$ {dados.get('valor_limite') or '-'}  ({dados.get('origem_valor_limite', 'planilha')})")
        self.log("Conferência dos valores (vale o termo):\n  " + "\n  ".join(linhas))
        for chave, v_termo, v_plan in dados.get("divergencias", []):
            self.log(f"DIVERGÊNCIA {rotulos.get(chave, chave)}: termo {v_termo} × planilha {v_plan}. Usando o do termo.", "WARNING")

        alertas = []
        if not dados.get("termo_lido"):
            alertas.append("O termo não pôde ser lido (escaneado ou não encontrado): os valores vêm só da planilha.")
        else:
            soma = (centavos(dados.get("valor_entrada")) if dados.get("tem_entrada") else 0) \
                + int(dados.get("qtd_parcelas") or 0) * centavos(dados.get("valor_parcela"))
            total = centavos(dados.get("valor_limite"))
            if total and abs(soma - total) > 100:   # tolerância de R$ 1,00 (arredondamentos)
                def brl(c):
                    return f"{c / 100:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                alertas.append(f"A conta não fecha: entrada + parcelas = R$ {brl(soma)} e o valor do acordo é R$ {brl(total)}.")
        if not alertas:
            self.log("Valores conferidos com o termo.", "SUCCESS")
            return True

        resumo = ("CONFERIR ANTES DE SUBIR O ACORDO\n\n" + "\n".join(alertas) + "\n\n"
                  + dados.get("nome_cliente", "") + "\n" + "\n".join(linhas) + "\n\nSubir o acordo com estes valores?")
        for a in alertas:
            self.log(a, "WARNING")
        if self.confirmar_gravacao and self.confirmar_gravacao(resumo) and not self._cancelado:
            self.log("Valores confirmados pelo usuário.")
            return True
        self.log(f"Acordo de '{dados.get('nome_cliente')}' NÃO subido: valores não confirmados.", "ERROR")
        return False

    def preencher_e_gravar_acordo(self, dados: Dict[str, Any]) -> bool:
        modal = self.page.locator("#Cadastro, div[role='dialog']").filter(has_text="Acordos Judiciais").first
        try:
            self.page.wait_for_timeout(800)

            # Processo: o campo é somente leitura. Caminho único: lupa > pesquisar pelo
            # número do processo (planilha) > Selecionar (ícone azul).
            input_proc = modal.locator("#EDTPROCESSO").first
            if input_proc.is_visible():
                v = input_proc.input_value().strip()
                if not v and dados.get("processo") and not dados.get("_sem_processo"):
                    if not self.selecionar_processo_pela_lupa(dados["processo"]):
                        # Processo não encontrado após as pesquisas: a lupa tira o usuário do
                        # formulário, então marca e reinicia o fluxo para subir SEM o processo.
                        self.log(f"Processo '{dados['processo']}' não encontrado. O acordo será enviado SEM número de processo.", "WARNING")
                        dados["_sem_processo"] = True
                        return False
                    modal = self.page.locator("#Cadastro, div[role='dialog']").filter(has_text="Acordos Judiciais").first

            # Valores: inicial = valor original da causa; limite = valor acordado no termo.
            # O sistema já traz um valor pré-preenchido: apaga e digita o correto.
            for campo, chave, rotulo in (("#EDTVALORINICIAL", "valor_inicial", "Valor inicial"),
                                         ("#EDTVALORLIMITE", "valor_limite", "Valor limite")):
                if not dados.get(chave):
                    self.log(f"{rotulo} não encontrado no termo nem na planilha. Campo mantido como está.", "WARNING")
                    continue
                origem = dados.get(f"origem_{chave}", "planilha")
                if not self._preencher_valor(modal.locator(campo).first, dados[chave]):
                    self.log(f"{rotulo} não ficou com R$ {dados[chave]}. Acordo NÃO será gravado.", "ERROR")
                    return False
                self.log(f"{rotulo} preenchido: R$ {dados[chave]} (origem: {origem}).")

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

            # Confirma SweetAlerts (clique via JS: o IWLocker bloqueia clique real).
            # Se a página navegar (gravação concluída), o loop termina sem erro.
            for _ in range(2):
                try:
                    sweet = self.page.locator(".sweet-alert.visible").first
                    sweet.wait_for(state="visible", timeout=4000)
                    sweet.locator("button.confirm").first.evaluate("el => el.click()")
                    self.page.wait_for_timeout(2500)
                except Exception:
                    break

            self.log(f"Acordo do cliente '{dados['nome_cliente']}' GRAVADO com sucesso!", "SUCCESS")
            return True

        except Exception as e:
            self.log(f"Erro ao gravar acordo: {e}", "ERROR")
            return False

    def acordo_ja_existe(self, nome_cliente: str, qtd_esperada: int = 0) -> Optional[bool]:
        """Um acordo gravado gera os boletos do cliente em Cadastro de Boletos (frmBoletoAvulso).
        O acordo só é considerado existente se o sistema tiver pelo menos `qtd_esperada`
        vencimentos distintos (parcelas do termo/planilha). Poucos boletos = acordo incompleto
        ou outro acordo, e o envio segue."""
        try:
            self.fechar_modais_ou_telas_ativas()
            self.page.evaluate("if (typeof window.SetaAcao === 'function') window.SetaAcao('Menu', 'frmBoletoAvulso');")
            self.page.wait_for_selector("#tabela_filter input", state="visible", timeout=20000)
            self.page.wait_for_timeout(1500)
            if not self._empresa_ac_ativa() and not self._garantir_empresa_ac_na_tela_boletos():
                return None  # não dá para afirmar nada fora da empresa AC COBRANÇA

            # 100 por página: o grid mostra 10 por padrão e subcontaria as parcelas
            try:
                sel = self.page.locator('select[name="tabela_length"]').first
                if sel.is_visible():
                    sel.select_option('100')
                    self.page.wait_for_timeout(1000)
            except Exception:
                pass

            campo = self.page.locator("#tabela_filter input").first
            campo.click(force=True)
            campo.fill("")
            campo.fill(nome_cliente)
            self.page.keyboard.press("Enter")
            self.page.wait_for_timeout(2000)
            try:
                self.page.wait_for_selector("#tabela_processing", state="hidden", timeout=10000)
            except Exception:
                pass
            self.page.wait_for_timeout(800)

            partes = [p for p in normalizar_texto(nome_cliente).split() if len(p) > 2]
            vencimentos = set()
            for r in self.page.locator("#tabela tbody tr").all():
                txt = r.inner_text()
                if "nenhum registro" in txt.lower():
                    continue
                palavras = set(normalizar_texto(txt).split())
                if partes and partes[0] in palavras and partes[-1] in palavras:
                    datas = re.findall(r'\b\d{2}/\d{2}/\d{4}\b', txt)
                    vencimentos.add(datas[1] if len(datas) >= 2 else (datas[0] if datas else txt))
            total = len(vencimentos)
            self.log(f"Verificação de acordo: {total} vencimento(s) distintos de '{nome_cliente}' no sistema; esperado pelo termo/planilha: {qtd_esperada}.")
            if total == 0:
                return False
            if total < qtd_esperada:
                self.log(f"Acordo INCOMPLETO no sistema ({total}/{qtd_esperada}). O acordo será enviado.", "WARNING")
                return False
            return True
        except Exception as e:
            # Sem conseguir ver a tela de boletos não dá para afirmar que o acordo não existe:
            # subir "às cegas" pode duplicar. Tenta mais uma vez; se falhar, não processa.
            if not getattr(self, "_verificando_de_novo", False):
                self.log(f"Não consegui verificar se o acordo já existe ({str(e).splitlines()[0][:100]}). "
                         "Tentando de novo...", "WARNING")
                self._verificando_de_novo = True
                try:
                    self.page.wait_for_timeout(3000)
                    return self.acordo_ja_existe(nome_cliente, qtd_esperada)
                finally:
                    self._verificando_de_novo = False
            self.log("Não consegui verificar se o acordo já existe. Para não duplicar, o acordo NÃO será subido.", "ERROR")
            return None

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

        self.gravou_algo = False
        self.garantir_sessao_ativa(visivel=visivel)

        dados = self.parser.carregar_dados_cliente(nome_cliente)
        if not dados.get("sucesso", True):
            self.log(f"Ignorado: {dados.get('motivo_erro', 'Erro ao carregar dados')}", "WARNING")
            return False

        if not dados.get("eh_parcelado", True):
            self.log(f"Ignorado: {nome_cliente} não é parcelado.", "WARNING")
            return False

        if not self._conferir_valores(dados):
            return False

        # ETAPA 1: Acordo
        # O popup "Horário registrado com sucesso" faz o sistema recarregar a página e
        # derruba o formulário aberto. Se isso acontecer, refaz o caminho (o horário já
        # estará registrado). Se o acordo chegou a ser gravado, abrir_modal_acordo
        # detecta "já tem acordo" e devolve None, evitando duplicidade.
        max_tentativas = 3
        for tentativa in range(1, max_tentativas + 1):
            self._parar_se_cancelado()
            if tentativa > 1:
                self.log(f"Tentativa {tentativa}/{max_tentativas} de subir o acordo de '{nome_cliente}'...", "WARNING")
                self.page.wait_for_timeout(2000)

            # Reconhece acordo já subido (evita duplicar) antes de qualquer tentativa
            existe = self.acordo_ja_existe(nome_cliente, int(dados.get("qtd_parcelas") or 0))
            if existe is None:
                # Não deu para conferir (tela de boletos/empresa): não sobe às cegas, tenta de novo
                self.log(f"Acordo de '{nome_cliente}' não conferido nesta tentativa: não será subido agora.", "WARNING")
                continue
            if existe:
                self.log(f"'{nome_cliente}' JÁ POSSUI ACORDO no sistema. Pulando o envio.", "SUCCESS")
                break

            self._parar_se_cancelado()
            if not self.acessar_cadastro_devedores(visivel=visivel):
                continue
            self._parar_se_cancelado()
            if not self.pesquisar_devedor_no_grid(nome_cliente, visivel=visivel, cpf=dados.get("cpf", "")):
                continue
            self._parar_se_cancelado()

            abriu = self.abrir_modal_acordo(nome_cliente)
            if abriu == SEM_VALORES_GEAP:
                if not self.criar_boletos_faltantes(nome_cliente, dados):
                    return False
                self.gravou_algo = True
                break
            if abriu is None:
                break
            if abriu is False:
                continue
            self._parar_se_cancelado()
            if self.preencher_e_gravar_acordo(dados):
                self.gravou_algo = True
                break
        else:
            # Acordo não subiu: cria as parcelas que faltam como boletos avulsos (+NOVO).
            # É seguro mesmo se o devedor não foi achado pelo nome: o cliente do boleto é
            # escolhido pelo CPF da planilha, e boletos que já existem não são recriados.
            self._parar_se_cancelado()
            self.log(f"Não foi possível subir o acordo de '{nome_cliente}' após {max_tentativas} tentativas. "
                     "Indo criar as parcelas como boletos avulsos.", "WARNING")
            if not self.criar_boletos_faltantes(nome_cliente, dados,
                                                motivo=f"acordo não subiu após {max_tentativas} tentativas"):
                return False
            self.gravou_algo = True

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

    def lista_parcelados_com_status(self, caminho_planilha: Optional[str] = None) -> list:
        """[(nome, status)] dos PARCELADOS, com o status da coluna 'ENVIO DE BOLETOS'
        normalizado (sem acento, maiúsculo; vazio = "")."""
        if caminho_planilha:
            self.parser.caminho_planilha = Path(caminho_planilha)
            self.parser._cached_ws = None
        ws = self.parser._obter_worksheet()
        if ws is None:
            return []

        col_map = {}
        for c in range(1, ws.max_column + 1):
            h = ws.cell(1, c).value
            if h:
                col_map[normalizar_texto(str(h))] = c
        idx_nome = col_map.get("BENEFICIARIO", 4)
        idx_cond = col_map.get("CONDICOES DO ACORDO", 8)
        idx_envio = col_map.get("ENVIO DE BOLETOS", 1)

        clientes = []
        for r in range(2, ws.max_row + 1):
            nome = str(ws.cell(r, idx_nome).value or "").strip()
            cond = str(ws.cell(r, idx_cond).value or "").upper()
            if nome and "PARCEL" in cond:
                status = normalizar_texto(str(ws.cell(r, idx_envio).value or ""))
                clientes.append((nome, status))
        return clientes