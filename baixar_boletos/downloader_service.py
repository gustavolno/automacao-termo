import os
import sys
import re
import time
from datetime import datetime
from urllib.parse import urljoin
from pathlib import Path
from playwright.sync_api import sync_playwright

if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "ms-playwright"
    )

from baixar_boletos.config import (
    GLOBAL_OFFICE_URL,
    GLOBAL_OFFICE_LOGIN,
    GLOBAL_OFFICE_USER,
    GLOBAL_OFFICE_PASS,
    STATE_FILE,
    USER_AGENT,
    formatar_nome_arquivo_boleto,
    obter_pasta_boletos_cliente,
    normalizar_texto
)

class DownloaderService:
    def __init__(self, log_callback=None, progress_callback=None):
        self.log_callback = log_callback or (lambda msg: print(msg))
        self.progress_callback = progress_callback
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self._cancelado = False

    def log(self, mensagem: str, nivel: str = "INFO"):
        hora = time.strftime("%H:%M:%S")
        texto = f"{hora} - {nivel} - {mensagem}"
        self.log_callback(texto)

    def cancelar(self):
        self._cancelado = True

    def _esperar_login_manual(self):
        self.log("Sessão não autenticada. Preenchendo credenciais...")
        browser = self.playwright.chromium.launch(headless=False)
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
            context.storage_state(path=STATE_FILE)
            self.log("Login efetuado com sucesso!")
            self.log(f"Sessão salva com sucesso em '{STATE_FILE}'.")
        finally:
            browser.close()

    def _testar_sessao_ativa(self) -> bool:
        """Verifica ativamente se o backend do servidor reconhece a sessão."""
        try:
            if self.page.locator("#EDTLOGIN").is_visible():
                return False

            has_seta = self.page.evaluate("typeof window.SetaAcao !== 'undefined'")
            if not has_seta:
                return False

            # Testa se o servidor responde ao formulário de empresas
            self.page.evaluate("if (typeof window.SetaAcao === 'function') window.SetaAcao('Menu', 'frmEmpresas');")
            self.page.wait_for_timeout(2500)

            # Se a linha de empresas apareceu, a sessão está 100% ativa no servidor
            linha = self.page.locator("tr:has-text('AC COBRANCA')").first
            if linha.is_visible(timeout=4000):
                return True

            return False
        except Exception:
            return False

    def iniciar_sessao(self, visivel: bool = False):
        self.log(f"Iniciando navegador (visivel={1 if visivel else 0})...")
        self.playwright = sync_playwright().start()

        while True:
            # Verifica existência do STATE_FILE no caminho configurado ou local
            state_file_path = Path(STATE_FILE)
            if not state_file_path.exists():
                local_state = Path("globaloffice_state.json")
                if local_state.exists():
                    state_file_path = local_state

            if not state_file_path.exists():
                self._esperar_login_manual()
                state_file_path = Path(STATE_FILE)

            launch_args = [
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1920,1080"
            ]

            self.browser = self.playwright.chromium.launch(
                headless=not visivel,
                args=launch_args
            )
            self.context = self.browser.new_context(
                storage_state=str(state_file_path),
                user_agent=USER_AGENT,
                accept_downloads=True,
                viewport={"width": 1920, "height": 1080}
            )
            self.page = self.context.new_page()
            self.page.on("dialog", lambda dialog: dialog.accept())

            try:
                resp = self.page.goto(GLOBAL_OFFICE_URL, timeout=60000)
                if resp and resp.status >= 400:
                    self.log(f"Sessão expirada no servidor (HTTP {resp.status}). Solicitando novo login...", "WARNING")
                    if self.context: self.context.close()
                    if self.browser: self.browser.close()
                    Path(STATE_FILE).unlink(missing_ok=True)
                    Path("globaloffice_state.json").unlink(missing_ok=True)
                    continue
                self.page.wait_for_timeout(3000)
            except Exception as e_nav:
                self.log(f"Falha de navegação na sessão salva: {e_nav}. Renovando login...", "WARNING")
                if self.context: self.context.close()
                if self.browser: self.browser.close()
                Path(STATE_FILE).unlink(missing_ok=True)
                Path("globaloffice_state.json").unlink(missing_ok=True)
                continue

            # TESTE ATIVO: Confirma se a sessão está realmente válida no servidor
            if not self._testar_sessao_ativa():
                self.log("Sessão expirada ou desincronizada no servidor. Solicitando novo login...", "WARNING")
                if self.context: self.context.close()
                if self.browser: self.browser.close()
                Path(STATE_FILE).unlink(missing_ok=True)
                Path("globaloffice_state.json").unlink(missing_ok=True)
                continue
            else:
                self.log("Sessão validada com sucesso.")
                self._selecionar_empresa()
                break

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

                btn_confirma_sweet = self.page.locator(
                    "button.confirm, .swal2-confirm, .sweet-alert button:has-text('Sim'), "
                    ".sweet-alert button:has-text('Confirmar'), button:has-text('Sim'), button:has-text('Confirmar')"
                ).first

                if btn_confirma_sweet.is_visible(timeout=5000):
                    self.log("Confirmando popup de empresa principal no sistema...")
                    btn_confirma_sweet.click(force=True)
                    self.page.wait_for_timeout(3000)

                try:
                    self.page.evaluate("""() => {
                        if (typeof window.ReleaseLock === 'function') window.ReleaseLock();
                        window.GActivateLock = false;
                        document.querySelectorAll('.sweet-overlay, .sweet-alert, .modal-backdrop').forEach(el => el.remove());
                        const lk = document.getElementById('IWLocker'); if(lk) lk.style.display='none';
                        document.body.classList.remove('modal-open', 'stop-scrolling');
                    }""")
                except Exception: pass
                self.page.wait_for_timeout(1000)

            self.log("Retornando ao Dashboard com a empresa AC COBRANÇA ativa...")
            btn_inicio = self.page.locator(".sidebar-menu a:has-text('Início'), .sidebar a:has(.fa-home), .breadcrumb a:has-text('Início')").first
            if btn_inicio.is_visible(timeout=3000):
                btn_inicio.click(force=True)
                self.page.wait_for_timeout(2000)
            else:
                self.page.evaluate("if (typeof window.SetaAcao === 'function') window.SetaAcao('Menu', 'frmPrincipal');")
                self.page.wait_for_timeout(2000)

            self.log("Empresa AC COBRANÇA selecionada e ativa com sucesso.")
        except Exception as e:
            self.log(f"Aviso ao selecionar empresa: {e}", "WARNING")

    def _acessar_cadastro_boletos(self):
        self.log("Acessando tela de Cadastro de Boletos (frmBoletoAvulso)...")
        try:
            self.page.evaluate("if (typeof window.SetaAcao === 'function') { window.SetaAcao('Menu', 'frmBoletoAvulso'); }")
            self.log("Aguardando carregamento da tabela (#tabela)...")
            self.page.wait_for_selector('#tabela, #tabela_filter input', state='visible', timeout=35000)
            self.page.wait_for_timeout(1500)
            try:
                self.page.wait_for_selector('#tabela_processing', state='hidden', timeout=10000)
            except Exception: pass
            
            self.log("Tabela de boletos (#tabela) pronta.")
        except Exception as e:
            self.log(f"Aviso na primeira tentativa: {e}. Tentando via menu lateral...", "WARNING")
            try:
                menu_fin = self.page.locator("span:has-text('Menu Financeiro')").first
                if menu_fin.is_visible(timeout=3000):
                    menu_fin.click(force=True)
                    self.page.wait_for_timeout(1000)

                link_boletos = self.page.locator("em:has-text('Cadastro de boletos'), a:has-text('Cadastro de boletos')").first
                if link_boletos.is_visible(timeout=3000):
                    link_boletos.click(force=True)

                self.page.wait_for_selector('#tabela, #tabela_filter input', state='visible', timeout=25000)
                self.log("Tabela de boletos (#tabela) pronta via menu lateral.")
            except Exception as e2:
                self.log(f"Erro ao acessar tela de boletos: {e2}", "ERROR")
                raise e2

    def _pesquisar_cliente_no_grid(self, nome_cliente: str):
        self.log(f"Iniciando busca automática no grid para: '{nome_cliente}'...")
        try:
            campo_busca = self.page.locator('#tabela_filter input[type="search"]')
            campo_busca.wait_for(state="visible", timeout=10000)
            campo_busca.scroll_into_view_if_needed()
            campo_busca.click()

            self.page.keyboard.press("Control+A")
            self.page.keyboard.press("Backspace")
            self.page.wait_for_timeout(500)

            self.log(f"Digitando '{nome_cliente}' no campo de pesquisa da tabela...")
            try:
                with self.page.expect_response(lambda r: "callback=tabela" in r.url and r.status == 200, timeout=15000):
                    self.page.keyboard.type(nome_cliente, delay=60)
            except Exception:
                with self.page.expect_response(lambda r: "callback=tabela" in r.url and r.status == 200, timeout=15000):
                    self.page.keyboard.press("Enter")

            self.log("Resposta do servidor recebida. Aguardando estabilização...")
            self.page.wait_for_timeout(2000)
            try:
                self.page.wait_for_selector('#tabela_processing', state='hidden', timeout=10000)
            except Exception: pass

            info = ""
            try: info = self.page.locator("#tabela_info").inner_text().strip()
            except Exception: pass
            self.log(f"Status do grid após busca: {info}")

        except Exception as e:
            self.log(f"Erro na digitação da busca: {e}", "WARNING")

    def _ajustar_paginacao_para_100(self):
        try:
            self.log("Ajustando paginação para 100 registros para capturar todas as parcelas...")
            with self.page.expect_response(lambda r: "callback=tabela" in r.url and r.status == 200, timeout=15000):
                self.page.evaluate("""() => {
                    if (window.jQuery && window.jQuery.fn.dataTable) {
                        window.jQuery('#tabela').DataTable().page.len(100).draw();
                    }
                }""")
            self.page.wait_for_timeout(2000)
            try:
                self.page.wait_for_selector('#tabela_processing', state='hidden', timeout=10000)
            except Exception: pass
            self.log("Paginação atualizada para 100.")
        except Exception as e:
            self.log(f"Aviso ao ajustar paginação para 100: {e}", "WARNING")

    def fechar_janela_impressao(self):
        """Fecha o modal de visualização do boleto sem quebrar o estado interno do IntraWeb"""
        try:
            btn_x = self.page.locator("#bx-clg-close-btn, button#bx-clg-close-btn, .modal.in button.close, .modal.show button.close").first
            if btn_x.is_visible():
                btn_x.click(force=True)
                self.page.wait_for_timeout(1000)
                return True

            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(1000)
            return True
        except Exception:
            pass
        return False

    def _resolver_pasta_destino(self, nome_cliente: str) -> Path:
        pasta = Path(obter_pasta_boletos_cliente(nome_cliente))
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta

    def _obter_indices_colunas(self):
        idx_cliente = 1
        idx_valor = 2
        idx_vencimento = 3
        try:
            headers = self.page.locator('#tabela thead th').all()
            for idx, th in enumerate(headers):
                texto = th.inner_text().strip().upper()
                if "CLIENTE" in texto:
                    idx_cliente = idx
                elif "VALOR" in texto:
                    idx_valor = idx
                elif "VENCIMENTO" in texto:
                    idx_vencimento = idx
            self.log(f"Colunas mapeadas: Cliente={idx_cliente}, Valor={idx_valor}, Vencimento={idx_vencimento}")
        except Exception: pass
        return idx_cliente, idx_valor, idx_vencimento

    def baixar_boletos_cliente(self, nome_cliente: str, visivel: bool = False, page_existente=None):
        self._cancelado = False
        boletos_salvos = []
        usou_sessao_propria = False
        
        try:
            if page_existente and not page_existente.is_closed():
                self.page = page_existente
                self.context = page_existente.context
            else:
                usou_sessao_propria = True
                self.iniciar_sessao(visivel=visivel)
            self._acessar_cadastro_boletos()

            # 1. Pesquisa o cliente no grid
            self._pesquisar_cliente_no_grid(nome_cliente)

            # 2. Ajusta para 100 registros
            self._ajustar_paginacao_para_100()

            pasta_destino = self._resolver_pasta_destino(nome_cliente)
            self.log(f"Pasta de destino garantida: {pasta_destino}")

            # 3. Mapeia colunas
            idx_cliente, idx_valor, idx_vencimento = self._obter_indices_colunas()

            self.page.wait_for_timeout(2000)
            todas_linhas = self.page.locator('#tabela tbody tr').all()
            self.log(f"Total de linhas brutas encontradas no grid: {len(todas_linhas)}")

            partes_cliente = [p.upper() for p in nome_cliente.strip().split() if len(p) > 2 and p.upper() not in ["DE", "DA", "DO", "DOS", "DAS"]]

            # Pré-coleta dos boletos para ordenação cronológica universal
            lista_boletos = []
            for i, linha in enumerate(todas_linhas):
                texto_linha = linha.inner_text().strip()
                if not texto_linha or "Nenhum registro" in texto_linha or "Aguarde" in texto_linha:
                    continue

                colunas = linha.locator("td").all()
                if len(colunas) <= max(idx_cliente, idx_valor, idx_vencimento):
                    continue

                nome_na_linha = colunas[idx_cliente].inner_text().strip().upper()
                matches = sum(1 for p in partes_cliente if p in nome_na_linha)
                if matches < min(2, len(partes_cliente)):
                    continue

                if linha.locator("button").count() == 0:
                    continue

                # Extrai Vencimento
                vencimento = ""
                try:
                    texto_venc = colunas[idx_vencimento].inner_text().strip()
                    m = re.search(r'\b\d{2}/\d{2}/\d{4}\b', texto_venc)
                    if m:
                        vencimento = m.group(0)
                except Exception: pass

                if not vencimento:
                    datas = re.findall(r'\b\d{2}/\d{2}/\d{4}\b', texto_linha)
                    vencimento = datas[1] if len(datas) >= 2 else (datas[0] if datas else "01/01/2099")

                # Converte para datetime para ordenação cronológica precisa
                try:
                    dt_venc = datetime.strptime(vencimento, "%d/%m/%Y")
                except Exception:
                    dt_venc = datetime.max

                # Extrai Valor
                valor = 0.0
                try:
                    texto_val = colunas[idx_valor].inner_text().replace(".", "").replace(",", ".").strip()
                    valor = float(re.sub(r'[^\d.]', '', texto_val))
                except Exception: pass

                lista_boletos.append({
                    "linha": linha,
                    "texto_linha": texto_linha,
                    "vencimento": vencimento,
                    "dt_venc": dt_venc,
                    "valor": valor
                })

            total_encontrados = len(lista_boletos)
            self.log(f"Encontrados exatamente {total_encontrados} boletos legítimos para '{nome_cliente}'.")

            if self.progress_callback:
                self.progress_callback(
                    encontrados=total_encontrados,
                    baixados=0,
                    percentual=0,
                    status=f"Encontrados {total_encontrados} boletos para '{nome_cliente}'",
                    destino=str(pasta_destino)
                )

            if total_encontrados == 0:
                self.log(f"Nenhum boleto confirmado para '{nome_cliente}'.", "WARNING")
                return {
                    "total_encontrados": 0,
                    "total_baixados": 0,
                    "boletos": [],
                    "destino": str(pasta_destino)
                }

            # ORDENAÇÃO CRONOLÓGICA UNIVERSAL: do vencimento mais próximo para o mais futuro
            lista_boletos.sort(key=lambda item: item["dt_venc"])
            self.log("Boletos ordenados cronologicamente (da 1ª parcela até a última).")

            # Identificação do valor padrão das parcelas (o que mais se repete)
            valores_validos = [b["valor"] for b in lista_boletos if b["valor"] > 0]
            valor_padrao = max(set(valores_validos), key=valores_validos.count) if valores_validos else 0

            # 4. Itera e baixa os boletos com nomenclatura cronológica por data (ISO)
            for idx, item in enumerate(lista_boletos, start=1):
                if self._cancelado:
                    self.log("Operação cancelada pelo usuário.", "WARNING")
                    break

                linha = item["linha"]
                texto_linha = item["texto_linha"]
                vencimento = item["vencimento"]

                # Entrada é exclusivamente a 1ª parcela se tiver a palavra ENTRADA ou valor diferenciado
                palavras_linha = set(re.findall(r'\b[A-Za-z]+\b', texto_linha.upper()))
                eh_entrada = (
                    idx == 1 and (
                        "ENTRADA" in palavras_linha
                        or (item["valor"] > 0 and valor_padrao > 0 and item["valor"] != valor_padrao)
                    )
                )
                tipo_str = "ENTRADA" if eh_entrada else "PARCELA"

                self.log(f"--- Processando boleto {idx} de {total_encontrados} [{tipo_str}] ---")
                self.log(f"Vencimento: {vencimento} | Valor: R$ {item['valor']:.2f}")

                # Formata no padrão ISO por Ano e Mês (sem números de parcela na frente)
                nome_arquivo = formatar_nome_arquivo_boleto(vencimento, eh_entrada=eh_entrada)
                caminho_final = pasta_destino / nome_arquivo

                # Se o arquivo já existe no destino com tamanho válido, pula para a próxima parcela
                if caminho_final.exists() and caminho_final.stat().st_size > 1024:
                    t_kb = round(caminho_final.stat().st_size / 1024, 1)
                    self.log(f"Boleto já existente na pasta ({t_kb} KB): {nome_arquivo}. Pulando download.")
                    boletos_salvos.append({
                        "arquivo": nome_arquivo,
                        "vencimento": vencimento,
                        "tipo": tipo_str,
                        "tamanho": f"{t_kb} KB",
                        "caminho": str(caminho_final)
                    })
                    continue

                # Localiza o botão de impressão da linha atual
                botao_imprimir = linha.locator('button[title="Imprimir boleto"], button[title*="Imprimir"], button:has(.fa-print)').first
                onclick_attr = botao_imprimir.get_attribute("onclick") or ""
                self.log(f"Ação de impressão da linha {idx}: {onclick_attr}")

                # Extrai o ID do boleto esperado no SetaAcao (ex: '26493')
                id_boleto_esperado = ""
                m_id = re.search(r"SetaAcao\('ImpBl',\s*'(\d+)'\)", onclick_attr)
                if m_id:
                    id_boleto_esperado = m_id.group(1)

                # Limpa iframes residuais anteriores do DOM para não pegar boleto em cache
                try:
                    self.page.evaluate("""() => {
                        document.querySelectorAll('iframe').forEach(el => {
                            if (el.src && el.src.includes('.pdf')) {
                                el.src = 'about:blank';
                            }
                        });
                    }""")
                except Exception:
                    pass

                pdf_url = None

                def on_response(resp):
                    nonlocal pdf_url
                    try:
                        u = resp.url
                        ct = resp.headers.get("content-type", "").lower()
                        # Rejeita URLs relativas residuais e páginas em branco
                        if not u.startswith("http") or "about:blank" in u:
                            return
                        if ".pdf" in u.lower() or "application/pdf" in ct:
                            # Se temos o ID esperado, valida que a URL corresponde a este boleto
                            if id_boleto_esperado and (f"Boleto_{id_boleto_esperado}" not in u and id_boleto_esperado not in u):
                                return
                            pdf_url = u
                    except Exception:
                        pass

                self.page.on("response", on_response)

                # Dispara a impressão da linha atual
                try:
                    if "SetaAcao" in onclick_attr:
                        self.page.evaluate(f"() => {{ {onclick_attr} }}")
                    else:
                        botao_imprimir.scroll_into_view_if_needed()
                        botao_imprimir.click(force=True)
                except Exception as e_click:
                    self.log(f"Erro ao disparar impressão na linha {idx}: {e_click}", "ERROR")

                # Aguarda detecção do PDF legítimo (pela rede ou iframe) com resiliência estendida
                for seg in range(25):
                    self.page.wait_for_timeout(1000)
                    if pdf_url:
                        break

                    # Se após 5 segundos ainda não capturou, tenta acionar o botão diretamente
                    if seg == 5 and not pdf_url:
                        try:
                            botao_imprimir.scroll_into_view_if_needed()
                            botao_imprimir.click(force=True)
                        except Exception:
                            pass

                    try:
                        for ifr in self.page.locator("iframe").all():
                            src = ifr.get_attribute("src") or ""
                            if not src or "about:blank" in src:
                                continue
                            if ".pdf" in src.lower():
                                if id_boleto_esperado and (f"Boleto_{id_boleto_esperado}" not in src and id_boleto_esperado not in src):
                                    continue
                                pdf_url = src
                                break
                        if pdf_url:
                            break
                    except Exception:
                        pass

                self.page.remove_listener("response", on_response)

                conteudo_pdf = None
                if pdf_url:
                    self.log(f"URL do PDF capturada para boleto {idx}: {pdf_url}")
                    try:
                        pdf_url_completa = urljoin(self.page.url, pdf_url)
                        resp = self.page.request.get(pdf_url_completa)
                        conteudo_pdf = resp.body()
                    except Exception as e_req:
                        self.log(f"Erro na requisição do PDF ({idx}): {e_req}", "ERROR")
                else:
                    self.log(f"Aviso: Timeout ao aguardar geração do PDF do boleto {idx}.", "WARNING")

                # Fecha o modal de visualização
                self.fechar_janela_impressao()
                self.page.wait_for_timeout(1000)

                if conteudo_pdf and len(conteudo_pdf) > 1024:
                    with open(caminho_final, "wb") as f:
                        f.write(conteudo_pdf)

                    tamanho_kb = round(len(conteudo_pdf) / 1024, 1)
                    self.log(f"Boleto salvo com sucesso ({tamanho_kb} KB): {nome_arquivo}")

                    boletos_salvos.append({
                        "arquivo": nome_arquivo,
                        "vencimento": vencimento,
                        "tipo": tipo_str,
                        "tamanho": f"{tamanho_kb} KB",
                        "caminho": str(caminho_final)
                    })
                else:
                    self.log(f"Falha ao obter dados válidos para {nome_arquivo}.", "ERROR")

                pct = int((idx / total_encontrados) * 100)
                if self.progress_callback:
                    self.progress_callback(
                        encontrados=total_encontrados,
                        baixados=len(boletos_salvos),
                        percentual=pct,
                        status=f"Processado boleto {idx} de {total_encontrados} ({vencimento})",
                        destino=str(pasta_destino),
                        item_recente=boletos_salvos[-1] if boletos_salvos else None
                    )

            final_status = f"Concluído: {len(boletos_salvos)} de {total_encontrados} boletos baixados."
            self.log(final_status)
            if self.progress_callback:
                self.progress_callback(
                    encontrados=total_encontrados,
                    baixados=len(boletos_salvos),
                    percentual=100,
                    status=final_status,
                    destino=str(pasta_destino)
                )

            return {
                "total_encontrados": total_encontrados,
                "total_baixados": len(boletos_salvos),
                "boletos": boletos_salvos,
                "destino": str(pasta_destino)
            }

        except Exception as e:
            self.log(f"Erro fatal na execução: {e}", "ERROR")
            raise e
        finally:
            if usou_sessao_propria:
                self.fechar_sessao()

    def fechar_sessao(self):
        try:
            if self.context: self.context.close()
            if self.browser: self.browser.close()
            if self.playwright: self.playwright.stop()
        except Exception: pass
