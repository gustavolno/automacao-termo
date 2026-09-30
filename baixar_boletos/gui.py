from typing import Optional
import os
import sys
import threading
import queue
import time
import ctypes
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "ms-playwright"
    )

# Garante que tanto a raiz quanto a pasta do módulo estejam no sys.path
_BASE_DIR = Path(__file__).resolve().parent
_ROOT_DIR = _BASE_DIR.parent
for _p in [str(_ROOT_DIR), str(_BASE_DIR)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    from baixar_boletos.config import (
        obter_pasta_boletos_cliente,
        GLOBAL_OFFICE_LOGIN,
        GLOBAL_OFFICE_USER,
        GLOBAL_OFFICE_PASS,
        salvar_credenciais_locais,
        USER_DATA_DIR
    )
    from baixar_boletos.downloader_service import DownloaderService
    from baixar_boletos.acordo_service import AcordoService
except ImportError:
    from config import (
        obter_pasta_boletos_cliente,
        GLOBAL_OFFICE_LOGIN,
        GLOBAL_OFFICE_USER,
        GLOBAL_OFFICE_PASS,
        salvar_credenciais_locais,
        USER_DATA_DIR
    )
    from downloader_service import DownloaderService
    from acordo_service import AcordoService

# ============================================================
# DESIGN SYSTEM — CLEAN / MINIMALISTA WARM (PERGAMINHO & ÂMBAR)
# ============================================================
# Paleta de Cores
BG_MAIN = "#F6F4EE"        # Bege suave / Pergaminho claro (Main Surface)
BG_PANEL = "#ECE9DF"       # Bege acinzentado sutil (Painéis, Header e Cards)
BG_INPUT = "#FFFFFF"       # Fundo limpo dos campos de entrada
BORDER_COLOR = "#DDD7CD"   # Bordas e linhas finas de separação (1px)

TEXT_MAIN = "#2C2825"      # Marrom-escuro / Carvão quente (Reduz fadiga ocular)
TEXT_MUTED = "#78716C"     # Cinza quente para labels secundárias
TEXT_TERRA = "#A44332"     # Terracota para destaques/erros

ACCENT_AMBER = "#C97A1E"   # Laranja âmbar suave para ação primária e alertas
ACCENT_AMBER_HOVER = "#B06815"
ACCENT_OLIVE = "#2F7C5A"   # Verde oliva/menta suave para ações positivas e Dropbox
ACCENT_OLIVE_HOVER = "#246347"
ACCENT_NAVY = "#1F4E79"        # Azul corporativo elegante para Acordo Judicial
ACCENT_NAVY_HOVER = "#163A5C"

BG_TERMINAL = "#FAF8F5"    # Pergaminho ultraclaro para console de alta legibilidade
SELECT_BG = "#E5DFD3"      # Seleção suave sem azul neon

# Tipografia
FONT_BRAND = ("Georgia", 11, "bold")
FONT_UI = ("Segoe UI", 9)
FONT_UI_BOLD = ("Segoe UI", 9, "bold")
FONT_UI_TITLE = ("Segoe UI", 10, "bold")
FONT_MONO = ("Consolas", 9)

def aplicar_tema_titulo_claro(window):
    """Aplica o tema claro nativo na barra de título do Windows (Windows 10/11 DWM)."""
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()
        value = ctypes.c_int(0) # 0 = Light Title Bar
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass

class AppBaixarBoletos(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Central de Download & Organização de Boletos (Global Office / Dropbox) — Aldrigues Cândido Advocacia")
        self.configure(bg=BG_MAIN)
        self.geometry("980x670")
        self.minsize(880, 600)

        aplicar_tema_titulo_claro(self)

        self.service = None
        self.log_queue = queue.Queue()
        self.pasta_destino_atual = None
        self.em_execucao = False
        self.boletos_baixados = []

        self._configurar_estilos()
        self._build_ui()

        self.after(50, self._centralizar)
        self.after(100, self._processar_fila_logs)

    def _centralizar(self):
        self.update_idletasks()
        w, h = 980, 670
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        aplicar_tema_titulo_claro(self)

    def _configurar_estilos(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        # Abas Warm Minimalistas
        style.configure("TNotebook", background=BG_MAIN, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_PANEL, foreground=TEXT_MUTED,
                        font=FONT_UI_BOLD, padding=[18, 7], borderwidth=1, bordercolor=BORDER_COLOR)
        style.map("TNotebook.Tab",
                  background=[("selected", BG_MAIN), ("active", "#F0EDE4")],
                  foreground=[("selected", TEXT_MAIN), ("active", ACCENT_AMBER)])

        # Treeview Warm
        style.configure("Treeview", background="#FFFFFF", foreground=TEXT_MAIN,
                        fieldbackground="#FFFFFF", font=FONT_UI, rowheight=26, borderwidth=1, bordercolor=BORDER_COLOR)
        style.configure("Treeview.Heading", background=BG_PANEL, foreground=TEXT_MAIN,
                        font=FONT_UI_BOLD, relief="flat", padding=[8, 5])
        style.map("Treeview", background=[("selected", SELECT_BG)], foreground=[("selected", TEXT_MAIN)])

        # Progressbar Âmbar Suave
        style.configure("Custom.Horizontal.TProgressbar",
                        troughcolor="#E5DFD3",
                        background=ACCENT_AMBER,
                        darkcolor=ACCENT_AMBER,
                        lightcolor=ACCENT_AMBER_HOVER,
                        bordercolor=BORDER_COLOR,
                        thickness=12)

    def _build_ui(self):
        # ── 1. HEADER WARM MINIMALISTA ──
        navbar = tk.Frame(self, bg=BG_PANEL, height=64, highlightthickness=1, highlightbackground=BORDER_COLOR)
        navbar.pack(fill="x")
        navbar.pack_propagate(False)

        brand_frame = tk.Frame(navbar, bg=BG_PANEL)
        brand_frame.pack(side="left", padx=22)

        lbl_logo = tk.Label(brand_frame, text="⚖", font=("Segoe UI", 16), bg=BG_PANEL, fg=ACCENT_AMBER)
        lbl_logo.pack(side="left", padx=(0, 10))

        brand_text_frame = tk.Frame(brand_frame, bg=BG_PANEL)
        brand_text_frame.pack(side="left")

        lbl_title = tk.Label(brand_text_frame, text="ALDRIGUES CÂNDIDO ADVOCACIA",
                             font=FONT_BRAND, bg=BG_PANEL, fg=TEXT_MAIN)
        lbl_title.pack(anchor="w")

        lbl_sub = tk.Label(brand_text_frame, text="Central de Download & Organização de Boletos (Global Office / Dropbox)",
                           font=("Segoe UI", 8), bg=BG_PANEL, fg=TEXT_MUTED)
        lbl_sub.pack(anchor="w")

        # Badge de Status Suave
        self.badge_status = tk.Label(navbar, text="● Sistema Pronto", font=FONT_UI_BOLD,
                                     bg="#E6F0EB", fg=ACCENT_OLIVE, padx=14, pady=4,
                                     highlightthickness=1, highlightbackground="#C2DFD2", relief="flat")
        
        # Botão discreto de configurações de credenciais locais
        self.btn_cred = tk.Button(navbar, text="⚙️ Meu Login", font=FONT_UI_BOLD,
                                  bg=BG_PANEL, fg=TEXT_MUTED, activebackground="#E0DCD3",
                                  activeforeground=TEXT_MAIN, relief="flat", cursor="hand2",
                                  padx=10, pady=4, highlightthickness=1, highlightbackground=BORDER_COLOR,
                                  command=self._abrir_modal_credenciais)
        self.btn_cred.pack(side="right", padx=(0, 10))
        self.badge_status.pack(side="right", padx=22)

        # ── 2. CONTAINER PRINCIPAL ──
        container = tk.Frame(self, bg=BG_MAIN, padx=22, pady=16)
        container.pack(fill="both", expand=True)

        # ── 3. CARD DE BUSCA DO CLIENTE ──
        card_busca = tk.Frame(container, bg=BG_PANEL, highlightthickness=1, highlightbackground=BORDER_COLOR, padx=18, pady=14)
        card_busca.pack(fill="x", pady=(0, 14))

        # Cabeçalho da busca: Rótulo à esquerda e Checkbox à direita
        header_busca = tk.Frame(card_busca, bg=BG_PANEL)
        header_busca.pack(fill="x", pady=(0, 6))

        lbl_cliente = tk.Label(header_busca, text="NOME COMPLETO DO CLIENTE:", font=FONT_UI_BOLD, bg=BG_PANEL, fg=TEXT_MUTED)
        lbl_cliente.pack(side="left")

        self.var_visivel = tk.BooleanVar(value=False)
        self.chk_visivel = tk.Checkbutton(header_busca, text="Exibir janela do navegador durante a captura",
                                          variable=self.var_visivel, font=FONT_UI, bg=BG_PANEL, fg=TEXT_MUTED,
                                          selectcolor=BG_INPUT, activebackground=BG_PANEL,
                                          activeforeground=TEXT_MAIN, highlightthickness=0)
        self.chk_visivel.pack(side="right")

        # Campo de entrada: Ocupa toda a largura do Card
        self.var_cliente = tk.StringVar()
        self.entry_cliente = tk.Entry(card_busca, textvariable=self.var_cliente, font=("Segoe UI", 11),
                                      bg=BG_INPUT, fg=TEXT_MAIN, insertbackground=TEXT_MAIN,
                                      relief="flat", highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.entry_cliente.pack(fill="x", ipady=6, pady=(0, 12))

        # Barra de Botões de Ação
        acoes_frame = tk.Frame(card_busca, bg=BG_PANEL)
        acoes_frame.pack(fill="x")

        # Botão Âmbar Suave: BAIXAR BOLETOS
        self.btn_baixar = tk.Button(acoes_frame, text="⬇ BAIXAR BOLETOS", font=FONT_UI_BOLD,
                                    bg=ACCENT_AMBER, fg="#FFFFFF", activebackground=ACCENT_AMBER_HOVER,
                                    activeforeground="#FFFFFF", relief="flat", cursor="hand2", padx=16, pady=7,
                                    command=self.iniciar_download)
        self.btn_baixar.pack(side="left", padx=(0, 8))

        # Botão Azul Corporativo: SUBIR ACORDO JUDICIAL (Apenas Parcelados)
        self.btn_subir_acordo = tk.Button(acoes_frame, text="🤝 SUBIR ACORDO JUDICIAL", font=FONT_UI_BOLD,
                                          bg=ACCENT_NAVY, fg="#FFFFFF", activebackground=ACCENT_NAVY_HOVER,
                                          activeforeground="#FFFFFF", relief="flat", cursor="hand2", padx=16, pady=7,
                                          command=self.iniciar_subir_acordo)
        self.btn_subir_acordo.pack(side="left", padx=(0, 8))

        # Botão Verde Oliva: ABRIR NO DROPBOX
        self.btn_dropbox = tk.Button(acoes_frame, text="📁 ABRIR NO DROPBOX", font=FONT_UI_BOLD,
                                     bg=ACCENT_OLIVE, fg="#FFFFFF", activebackground=ACCENT_OLIVE_HOVER,
                                     activeforeground="#FFFFFF", relief="flat", cursor="hand2", padx=14, pady=7,
                                     command=self.abrir_pasta_dropbox)
        self.btn_dropbox.pack(side="left", padx=(0, 8))

        # Botão roxo: PROCESSAR TODOS OS PARCELADOS
        self.btn_todos_parcelados = tk.Button(
            acoes_frame, text="📋 PROCESSAR TODOS OS PARCELADOS",
            font=FONT_UI_BOLD, bg="#5B4A8A", fg="#FFFFFF",
            activebackground="#483A72", activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", padx=14, pady=7,
            command=self.iniciar_todos_parcelados
        )
        self.btn_todos_parcelados.pack(side="right")

        # self.entry_cliente.bind("<Return>", lambda event: self.iniciar_download()) # Evita acionamento acidental

        # ── 4. CARD DE PROGRESSO ──
        card_progresso = tk.Frame(container, bg=BG_PANEL, highlightthickness=1, highlightbackground=BORDER_COLOR, padx=18, pady=12)
        card_progresso.pack(fill="x", pady=(0, 14))

        prog_topo = tk.Frame(card_progresso, bg=BG_PANEL)
        prog_topo.pack(fill="x", pady=(0, 5))

        self.lbl_status_progresso = tk.Label(prog_topo, text="Aguardando comando...", font=FONT_UI_BOLD, bg=BG_PANEL, fg=TEXT_MAIN)
        self.lbl_status_progresso.pack(side="left")

        self.lbl_porcentagem = tk.Label(prog_topo, text="0%", font=FONT_UI_BOLD, bg=BG_PANEL, fg=ACCENT_AMBER)
        self.lbl_porcentagem.pack(side="right")

        self.barra_progresso = ttk.Progressbar(card_progresso, style="Custom.Horizontal.TProgressbar",
                                                orient="horizontal", mode="determinate")
        self.barra_progresso.pack(fill="x", pady=(0, 6))

        self.lbl_meta = tk.Label(card_progresso,
                                 text="Encontrados: 0   |   Baixados: 0   |   Destino: —",
                                 font=("Segoe UI", 8), bg=BG_PANEL, fg=TEXT_MUTED)
        self.lbl_meta.pack(anchor="w")

        # ── 5. NOTEBOOK / ABAS ──
        self.notebook = ttk.Notebook(container)
        self.notebook.pack(fill="both", expand=True)

        # ── ABA 1: TERMINAL ──
        tab_terminal = tk.Frame(self.notebook, bg=BG_MAIN)
        self.notebook.add(tab_terminal, text="Terminal em Tempo Real")

        head_term = tk.Frame(tab_terminal, bg=BG_MAIN, padx=4, pady=6)
        head_term.pack(fill="x")

        tk.Label(head_term, text="LOGS DETALHADOS DA EXECUÇÃO:", font=("Segoe UI", 8, "bold"),
                 bg=BG_MAIN, fg=TEXT_MUTED).pack(side="left")

        btn_limpar = tk.Button(head_term, text="Limpar Log", font=("Segoe UI", 8),
                               bg=BG_PANEL, fg=TEXT_MUTED, activebackground=BORDER_COLOR,
                               activeforeground=TEXT_MAIN, relief="flat", padx=10, pady=2,
                               highlightthickness=1, highlightbackground=BORDER_COLOR,
                               cursor="hand2", command=self.limpar_log)
        btn_limpar.pack(side="right")

        # ScrolledText com fundo limpo pergaminho e seleção suave
        self.txt_log = scrolledtext.ScrolledText(tab_terminal, bg=BG_TERMINAL, fg=TEXT_MAIN,
                                                font=FONT_MONO, relief="flat",
                                                insertbackground=TEXT_MAIN,
                                                exportselection=False,
                                                selectbackground=SELECT_BG,
                                                selectforeground=TEXT_MAIN,
                                                inactiveselectbackground=SELECT_BG,
                                                highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.txt_log.pack(fill="both", expand=True, pady=(0, 4))

        self.txt_log.tag_config("INFO", foreground=TEXT_MAIN)
        self.txt_log.tag_config("WARNING", foreground=ACCENT_AMBER)
        self.txt_log.tag_config("ERROR", foreground=TEXT_TERRA)
        self.txt_log.tag_config("SUCCESS", foreground=ACCENT_OLIVE)

        # ── ABA 2: BOLETOS BAIXADOS ──
        tab_boletos = tk.Frame(self.notebook, bg=BG_MAIN, padx=4, pady=10)
        self.notebook.add(tab_boletos, text="Boletos Baixados (0)")
        self.tab_boletos_index = 1

        colunas = ("arquivo", "vencimento", "tipo", "tamanho", "status")
        self.tree_boletos = ttk.Treeview(tab_boletos, columns=colunas, show="headings")
        self.tree_boletos.heading("arquivo", text="Nome do Arquivo")
        self.tree_boletos.heading("vencimento", text="Vencimento")
        self.tree_boletos.heading("tipo", text="Tipo")
        self.tree_boletos.heading("tamanho", text="Tamanho")
        self.tree_boletos.heading("status", text="Status")

        self.tree_boletos.column("arquivo", width=340, anchor="w")
        self.tree_boletos.column("vencimento", width=120, anchor="center")
        self.tree_boletos.column("tipo", width=110, anchor="center")
        self.tree_boletos.column("tamanho", width=100, anchor="center")
        self.tree_boletos.column("status", width=100, anchor="center")

        scroll_tree = ttk.Scrollbar(tab_boletos, orient="vertical", command=self.tree_boletos.yview)
        self.tree_boletos.configure(yscrollcommand=scroll_tree.set)

        self.tree_boletos.pack(side="left", fill="both", expand=True)
        scroll_tree.pack(side="right", fill="y")

        self.tree_boletos.bind("<Double-1>", self._abrir_boleto_selecionado)

    def log(self, mensagem: str, nivel: Optional[str] = None):
        if nivel and nivel != "INFO" and not mensagem.startswith(f"[{nivel}]"):
            self.log_queue.put(f"[{nivel}] {mensagem}")
        else:
            self.log_queue.put(mensagem)

    def _processar_fila_logs(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self._adicionar_log_formatado(msg)
        self.after(100, self._processar_fila_logs)

    def _adicionar_log_formatado(self, linha: str):
        self.txt_log.config(state="normal")
        tag = "INFO"
        if "ERROR" in linha or "erro" in linha.lower():
            tag = "ERROR"
        elif "WARNING" in linha:
            tag = "WARNING"
        elif "sucesso" in linha.lower() or "finalizado" in linha.lower() or "salvo" in linha.lower():
            tag = "SUCCESS"

        self.txt_log.insert("end", linha + "\n", tag)
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")

    def limpar_log(self):
        self.txt_log.config(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.config(state="disabled")

    def definir_status_badge(self, tipo: str):
        if tipo == "pronto":
            self.badge_status.config(text="● Sistema Pronto", bg="#E6F0EB", fg=ACCENT_OLIVE, highlightbackground="#C2DFD2")
        elif tipo == "executando":
            self.badge_status.config(text="● Em Execução", bg="#FBF2E5", fg=ACCENT_AMBER, highlightbackground="#F2D8B3")
        elif tipo == "sucesso":
            self.badge_status.config(text="● Concluído com Sucesso", bg="#E6F0EB", fg=ACCENT_OLIVE, highlightbackground="#C2DFD2")
        elif tipo == "parcial":
            self.badge_status.config(text="● Concluído Parcialmente", bg="#FBF2E5", fg=ACCENT_AMBER, highlightbackground="#F2D8B3")
        elif tipo == "erro":
            self.badge_status.config(text="● Erro na Execução", bg="#FDE8E8", fg=TEXT_TERRA, highlightbackground="#F8B4B4")

    def atualizar_progresso(self, encontrados: int, baixados: int, percentual: int,
                            status: str, destino: str, item_recente: dict = None):
        def _atualizar():
            self.barra_progresso["value"] = percentual
            self.lbl_porcentagem.config(text=f"{percentual}% ({baixados}/{encontrados})" if encontrados > 0 else f"{percentual}%")
            self.lbl_status_progresso.config(text=status)
            self.pasta_destino_atual = destino
            self.lbl_meta.config(text=f"Encontrados: {encontrados}   |   Baixados: {baixados}   |   Destino: {destino}")

            if item_recente:
                self.boletos_baixados.append(item_recente)
                self.tree_boletos.insert("", "end", values=(
                    item_recente["arquivo"],
                    item_recente["vencimento"],
                    item_recente["tipo"],
                    item_recente["tamanho"],
                    "Salvo"
                ))
                self.notebook.tab(self.tab_boletos_index, text=f"Boletos Baixados ({len(self.boletos_baixados)})")
        self.after(0, _atualizar)

    def iniciar_download(self):
        if self.em_execucao:
            messagebox.showwarning("Em Execução", "A automação já está em andamento. Aguarde a conclusão.")
            return

        cliente = self.var_cliente.get().strip().upper()
        if not cliente:
            messagebox.showwarning("Campo Obrigatório", "Por favor, digite o nome completo do cliente.")
            self.entry_cliente.focus_set()
            return

        self.em_execucao = True
        self.btn_baixar.config(state="disabled", bg="#DDD7CD", fg=TEXT_MUTED, cursor="arrow")
        self.definir_status_badge("executando")
        
        self.boletos_baixados.clear()
        for item in self.tree_boletos.get_children():
            self.tree_boletos.delete(item)
        self.notebook.tab(self.tab_boletos_index, text="Boletos Baixados (0)")

        visivel = self.var_visivel.get()
        thread = threading.Thread(target=self._executar_worker, args=(cliente, visivel), daemon=True)
        thread.start()

    def _executar_worker(self, cliente: str, visivel: bool):
        try:
            self.log(f"Iniciando para: {cliente}...")
            self.service = DownloaderService(
                log_callback=self.log,
                progress_callback=self.atualizar_progresso
            )
            resultado = self.service.baixar_boletos_cliente(cliente, visivel=visivel)

            total_enc = resultado["total_encontrados"]
            total_baix = resultado["total_baixados"]

            if total_baix == total_enc and total_enc > 0:
                self.after(0, lambda: self.definir_status_badge("sucesso"))
            elif total_baix > 0:
                self.after(0, lambda: self.definir_status_badge("parcial"))
            else:
                self.after(0, lambda: self.definir_status_badge("parcial"))

        except Exception as e:
            self.log(f"Falha durante a execução: {e}")
            self.after(0, lambda: self.definir_status_badge("erro"))
        finally:
            def _reset_btn():
                self.em_execucao = False
                self.btn_baixar.config(state="normal", bg=ACCENT_AMBER, fg="#FFFFFF", cursor="hand2")
            self.after(0, _reset_btn)


    def iniciar_subir_acordo(self):
        cliente = self.entry_cliente.get().strip()
        if not cliente:
            messagebox.showwarning(
                "Nome do Devedor Necessário",
                "Por favor, digite ou cole o nome do devedor no campo de pesquisa acima para subir o acordo judicial."
            )
            self.entry_cliente.focus_set()
            return

        visivel = self.var_visivel.get()

        self.btn_baixar.config(state="disabled", text="AGUARDE...")
        self.btn_subir_acordo.config(state="disabled", text="SUBINDO ACORDO...")
        if hasattr(self, "btn_todos_parcelados"): self.btn_todos_parcelados.config(state="disabled")
        self.btn_dropbox.config(state="disabled")
        self.definir_status_badge("SUBINDO ACORDO")
        self.lbl_status_progresso.config(text=f"Processando acordo: {cliente}", fg=TEXT_MAIN)
        self.lbl_porcentagem.config(text="...")
        self.barra_progresso.config(mode="indeterminate")
        self.barra_progresso.start(10)

        threading.Thread(target=self._executar_worker_acordo, args=(cliente, visivel), daemon=True).start()

    def _executar_worker_acordo(self, cliente: str, visivel: bool):
        sucesso = False
        try:
            service = AcordoService(log_callback=self.log)
            sucesso = service.subir_acordo_completo(cliente, visivel=visivel)
        except Exception as e:
            self.log(f"Erro inesperado no envio do acordo: {e}", "ERROR")
        finally:
            def _reset():
                self.barra_progresso.stop()
                self.barra_progresso.config(mode="determinate", value=100 if sucesso else 0)
                self.lbl_porcentagem.config(text="100%" if sucesso else "0%")
                self.lbl_status_progresso.config(
                    text=f"Acordo de '{cliente}' enviado com sucesso!" if sucesso else f"Processamento de '{cliente}' finalizado.",
                    fg=ACCENT_OLIVE if sucesso else TEXT_TERRA
                )
                self.btn_baixar.config(state="normal", text="BAIXAR BOLETOS")
                self.btn_subir_acordo.config(state="normal", text="🤝 SUBIR ACORDO JUDICIAL")
                if hasattr(self, 'btn_todos_parcelados'):
                    self.btn_todos_parcelados.config(state="normal")
                self.btn_dropbox.config(state="normal")
                self.definir_status_badge("CONCLUÍDO" if sucesso else "PRONTO")
            self.after(0, _reset)

    def iniciar_todos_parcelados(self):
        """Inicia o processamento em lote de todos os parcelados da planilha."""
        from tkinter import messagebox
        resposta = messagebox.askyesno(
            "Processar Todos os Parcelados",
            "Isso irá processar TODOS os clientes PARCELADOS da planilha devedores_encontrados.\n\n"
            "O robô abrirá um por um e subirá o acordo no sistema.\n\n"
            "Deseja continuar?",
            parent=self
        )
        if not resposta:
            return

        visivel = self.var_visivel.get()

        self.btn_baixar.config(state="disabled")
        self.btn_subir_acordo.config(state="disabled")
        self.btn_todos_parcelados.config(state="disabled", text="PROCESSANDO...")
        self.btn_dropbox.config(state="disabled")
        self.definir_status_badge("PROCESSANDO LOTE")
        self.barra_progresso.config(mode="indeterminate")
        self.barra_progresso.start(10)
        self.lbl_status_progresso.config(text="Lendo planilha de parcelados...", fg=TEXT_MAIN)

        threading.Thread(target=self._worker_todos_parcelados, args=(visivel,), daemon=True).start()

    def _worker_todos_parcelados(self, visivel: bool):
        """Worker thread para processar todos os parcelados em sequência."""
        from baixar_boletos.acordo_service import AcordoService
        service = AcordoService(log_callback=self.log)
        lista = []
        try:
            lista = service.lista_parcelados_planilha()
        except Exception as e:
            self.log(f"Erro ao ler planilha: {e}", "ERROR")

        total = len(lista)
        if total == 0:
            self.log("Nenhum cliente PARCELADO encontrado na planilha.", "WARNING")
            self.after(0, self._reset_btn_lote)
            return

        self.log(f"Iniciando lote: {total} clientes PARCELADOS para processar.")
        sucesso_count = 0
        erro_count = 0
        pulo_count = 0

        for i, nome in enumerate(lista, 1):
            if self._cancelado if hasattr(self, '_cancelado') else False:
                self.log("Lote cancelado pelo usuário.", "WARNING")
                break

            self.after(0, lambda n=nome, idx=i: (
                self.lbl_status_progresso.config(text=f"[{idx}/{total}] {n}", fg=TEXT_MAIN),
                self.barra_progresso.config(mode="determinate", value=int((idx / total) * 100)),
            ))

            # 1. Validação de boletos na pasta do Dropbox antes de abrir navegador
            status_boletos = service.verificar_boletos_completos(nome)
            if status_boletos["completo"]:
                pulo_count += 1
                self.log(
                    f"[{i}/{total}] PULANDO '{nome}': Já contém todos os {status_boletos['encontrados']}/{status_boletos['esperados']} "
                    f"boletos correspondentes às parcelas da planilha.",
                    "INFO"
                )
                continue

            # 2. Se faltar algum boleto ou a pasta estiver vazia, executa normalmente
            if status_boletos.get("esperados", 0) > 0 and status_boletos.get("encontrados", 0) > 0:
                self.log(f"[{i}/{total}] '{nome}' possui {status_boletos['encontrados']}/{status_boletos['esperados']} boletos (incompleto). Processando...")
            else:
                self.log(f"--- [{i}/{total}] Iniciando: {nome} ---")

            try:
                # ETAPA 1: Subir Acordo Judicial no sistema
                self.log(f"[{i}/{total}] Etapa 1/2: Subindo acordo de '{nome}'...")
                ok_acordo = service.subir_acordo_completo(nome, visivel=visivel)
                
                if ok_acordo:
                    self.log(f"[{i}/{total}] Acordo de '{nome}' registrado com sucesso! Iniciando download dos boletos...")
                    
                    # ETAPA 2: Baixar boletos do cliente recém-cadastrado
                    self.log(f"[{i}/{total}] Etapa 2/2: Baixando boletos de '{nome}'...")
                    from baixar_boletos.downloader_service import DownloaderService
                    dl_service = DownloaderService(log_callback=self.log)
                    
                    try:
                        # Reutiliza a mesma página do Playwright se estiver aberta para máxima agilidade
                        res_dl = dl_service.baixar_boletos_cliente(
                            nome,
                            visivel=visivel,
                            page_existente=service.page if service.page and not service.page.is_closed() else None
                        )
                        total_baixados = res_dl.get("total_baixados", 0)
                        self.log(f"[{i}/{total}] SUCESSO COMPLETO: '{nome}' teve o acordo cadastrado e {total_baixados} boletos baixados!", "SUCCESS")
                        sucesso_count += 1
                    except Exception as ex_dl:
                        self.log(f"[{i}/{total}] Acordo de '{nome}' foi enviado, mas houve erro ao baixar boletos: {ex_dl}", "WARNING")
                        sucesso_count += 1
                else:
                    erro_count += 1
                    self.log(f"[{i}/{total}] FALHOU ao subir acordo de: {nome}", "WARNING")
            except Exception as ex:
                erro_count += 1
                self.log(f"[{i}/{total}] ERRO inesperado em '{nome}': {ex}", "ERROR")

        service.fechar_sessao()
        resumo = f"Lote concluído: {sucesso_count} processados, {pulo_count} pulados (já prontos), {erro_count} com falha, de {total} total."
        self.log(resumo)
        self.after(0, lambda: self.lbl_status_progresso.config(text=resumo, fg=TEXT_MAIN))
        self.after(0, self._reset_btn_lote)

    def _reset_btn_lote(self):
        self.barra_progresso.stop()
        self.barra_progresso.config(mode="determinate", value=100)
        self.btn_baixar.config(state="normal")
        self.btn_subir_acordo.config(state="normal")
        self.btn_todos_parcelados.config(state="normal", text="📋 PROCESSAR TODOS OS PARCELADOS")
        self.btn_dropbox.config(state="normal")
        self.definir_status_badge("CONCLUÍDO")

    def abrir_pasta_dropbox(self):
        cliente = self.var_cliente.get().strip().upper()
        caminho = None
        if self.pasta_destino_atual and Path(self.pasta_destino_atual).exists():
            caminho = self.pasta_destino_atual
        elif cliente:
            caminho = obter_pasta_boletos_cliente(cliente)

        if caminho and Path(caminho).exists():
            try:
                os.startfile(str(caminho))
            except Exception as e:
                messagebox.showerror("Erro ao Abrir", f"Não foi possível abrir a pasta:\n{e}")
        else:
            messagebox.showinfo("Pasta Não Encontrada",
                                f"A pasta de boletos ainda não existe ou não foi localizada para este cliente:\n{caminho}")

    def _abrir_boleto_selecionado(self, event):
        item_selecionado = self.tree_boletos.selection()
        if not item_selecionado:
            return
        valores = self.tree_boletos.item(item_selecionado[0], "values")
        if not valores:
            return
        nome_arquivo = valores[0]
        if self.pasta_destino_atual:
            caminho_completo = Path(self.pasta_destino_atual) / nome_arquivo
            if caminho_completo.exists():
                try:
                    os.startfile(str(caminho_completo))
                except Exception as e:
                    messagebox.showerror("Erro ao Abrir Arquivo", f"Não foi possível abrir o PDF:\n{e}")


    def _abrir_modal_credenciais(self):
        """Abre modal seguro para gerenciar o login exclusivo desta máquina."""
        janela = tk.Toplevel(self)
        janela.title("Configurar Meu Login - Global Office")
        janela.geometry("460x420")
        janela.resizable(False, False)
        janela.configure(bg=BG_MAIN)
        janela.transient(self)
        janela.grab_set()

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        janela.geometry(f"460x420+{(sw-460)//2}+{(sh-420)//2}")

        frame = tk.Frame(janela, bg=BG_MAIN, padx=24, pady=20)
        frame.pack(fill="both", expand=True)

        lbl_tit = tk.Label(frame, text="Minhas Credenciais do Global Office", font=("Segoe UI", 12, "bold"),
                           bg=BG_MAIN, fg=TEXT_MAIN)
        lbl_tit.pack(anchor="w", pady=(0, 4))

        lbl_desc = tk.Label(frame, text="Seus dados ficam salvos com total privacidade apenas neste computador,\ne nunca são compartilhados no Dropbox com o restante da equipe.",
                            font=("Segoe UI", 8), bg=BG_MAIN, fg=TEXT_MUTED, justify="left")
        lbl_desc.pack(anchor="w", pady=(0, 16))

        # Campo Login
        tk.Label(frame, text="Login (Empresa / CNPJ):", font=FONT_UI_BOLD, bg=BG_MAIN, fg=TEXT_MUTED).pack(anchor="w", pady=(0, 2))
        ent_login = tk.Entry(frame, font=("Segoe UI", 10), bg=BG_INPUT, fg=TEXT_MAIN, relief="flat",
                             highlightthickness=1, highlightbackground=BORDER_COLOR)
        ent_login.pack(fill="x", pady=(0, 10), ipady=4)
        ent_login.insert(0, os.getenv("GLOBAL_OFFICE_LOGIN", ""))

        # Campo Usuário
        tk.Label(frame, text="Nome de Usuário:", font=FONT_UI_BOLD, bg=BG_MAIN, fg=TEXT_MUTED).pack(anchor="w", pady=(0, 2))
        ent_user = tk.Entry(frame, font=("Segoe UI", 10), bg=BG_INPUT, fg=TEXT_MAIN, relief="flat",
                            highlightthickness=1, highlightbackground=BORDER_COLOR)
        ent_user.pack(fill="x", pady=(0, 10), ipady=4)
        ent_user.insert(0, os.getenv("GLOBAL_OFFICE_USER", ""))

        # Campo Senha
        tk.Label(frame, text="Senha:", font=FONT_UI_BOLD, bg=BG_MAIN, fg=TEXT_MUTED).pack(anchor="w", pady=(0, 2))
        ent_pass = tk.Entry(frame, font=("Segoe UI", 10), bg=BG_INPUT, fg=TEXT_MAIN, relief="flat",
                            show="*", highlightthickness=1, highlightbackground=BORDER_COLOR)
        ent_pass.pack(fill="x", pady=(0, 18), ipady=4)
        ent_pass.insert(0, os.getenv("GLOBAL_OFFICE_PASS", ""))

        def salvar():
            log_val = ent_login.get().strip()
            usr_val = ent_user.get().strip()
            pas_val = ent_pass.get().strip()

            if not log_val or not usr_val:
                messagebox.showwarning("Campos Obrigatórios", "Por favor, preencha o Login e o Usuário.", parent=janela)
                return

            salvar_credenciais_locais(log_val, usr_val, pas_val)
            messagebox.showinfo("Sucesso", "Credenciais salvas com segurança no seu perfil local!\nO robô já utilizará esses dados nos próximos downloads.", parent=janela)
            janela.destroy()

        btn_salvar = tk.Button(frame, text="💾 Salvar no Meu Computador", font=FONT_UI_BOLD,
                               bg=ACCENT_AMBER, fg="#FFFFFF", activebackground=ACCENT_AMBER_HOVER,
                               activeforeground="#FFFFFF", relief="flat", cursor="hand2", padx=16, pady=8,
                               command=salvar)
        btn_salvar.pack(fill="x", pady=(0, 10))

        def encerrar_sessao():
            from pathlib import Path
            from baixar_boletos.config import STATE_FILE
            Path(STATE_FILE).unlink(missing_ok=True)
            Path('globaloffice_state.json').unlink(missing_ok=True)
            if hasattr(self, 'service') and self.service:
                try:
                    self.service.fechar_sessao()
                except Exception: pass
            messagebox.showinfo(
                "Sessão Encerrada",
                "A sessão do Global Office foi encerrada com sucesso!\n\n"
                "Na próxima pesquisa, a automação iniciará uma nova sessão do zero.",
                parent=janela
            )
            janela.destroy()

        btn_encerrar = tk.Button(frame, text="🔴 Encerrar Sessão Ativa / Novo Login", font=("Segoe UI", 9, "bold"),
                                 bg="#DC3545", fg="#FFFFFF", activebackground="#C82333",
                                 activeforeground="#FFFFFF", relief="flat", cursor="hand2", padx=16, pady=6,
                                 command=encerrar_sessao)
        btn_encerrar.pack(fill="x")

def main():
    app = AppBaixarBoletos()
    app.mainloop()

if __name__ == "__main__":
    main()
