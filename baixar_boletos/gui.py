from typing import Optional
import os
import re
import sys
import threading
import queue
import time
import ctypes
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog

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
        salvar_credenciais_webmail,
        normalizar_texto,
        USER_DATA_DIR
    )
    from baixar_boletos.downloader_service import DownloaderService
    from baixar_boletos.acordo_service import AcordoService, ProcessamentoCancelado
    from baixar_boletos import email_service
except ImportError:
    from config import (
        obter_pasta_boletos_cliente,
        GLOBAL_OFFICE_LOGIN,
        GLOBAL_OFFICE_USER,
        GLOBAL_OFFICE_PASS,
        salvar_credenciais_locais,
        salvar_credenciais_webmail,
        normalizar_texto,
        USER_DATA_DIR
    )
    from downloader_service import DownloaderService
    from acordo_service import AcordoService, ProcessamentoCancelado
    import email_service

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
        self.geometry("980x720")
        self.minsize(880, 650)

        aplicar_tema_titulo_claro(self)

        self.service = None
        self.log_queue = queue.Queue()
        self.pasta_destino_atual = None
        self.em_execucao = False
        self._cancelado = False
        self._servicos_ativos = []   # serviços em andamento, avisados pelo botão PARAR
        self._log_lock = threading.Lock()
        self.boletos_baixados = []

        self._configurar_estilos()
        self._build_ui()

        self.after(50, self._centralizar)
        self.after(100, self._processar_fila_logs)

    def _centralizar(self):
        self.update_idletasks()
        w, h = 980, 720
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

        # Segunda linha: lote de 5, e-mail e parar
        acoes_frame2 = tk.Frame(card_busca, bg=BG_PANEL)
        acoes_frame2.pack(fill="x", pady=(8, 0))

        # Botão roxo: PROCESSAR 5 CLIENTES (nomes digitados na ordem desejada)
        self.btn_lote5 = tk.Button(
            acoes_frame2, text="📋 PROCESSAR 5 CLIENTES",
            font=FONT_UI_BOLD, bg="#5B4A8A", fg="#FFFFFF",
            activebackground="#483A72", activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", padx=14, pady=7,
            command=self.abrir_dialogo_lote5
        )
        self.btn_lote5.pack(side="left", padx=(0, 8))

        self.btn_email = tk.Button(
            acoes_frame2, text="✉ ENVIAR BOLETOS POR E-MAIL",
            font=FONT_UI_BOLD, bg="#B23A48", fg="#FFFFFF",
            activebackground="#952F3B", activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", padx=14, pady=7,
            command=self.iniciar_envio_email
        )
        self.btn_email.pack(side="left", padx=(0, 8))

        self.var_conferir_email = tk.BooleanVar(value=True)
        tk.Checkbutton(acoes_frame2, text="Conferir cada e-mail antes de enviar",
                       variable=self.var_conferir_email, font=FONT_UI, bg=BG_PANEL, fg=TEXT_MUTED,
                       selectcolor=BG_INPUT, activebackground=BG_PANEL,
                       activeforeground=TEXT_MAIN, highlightthickness=0).pack(side="left")

        self.btn_parar = tk.Button(
            acoes_frame2, text="⏹ PARAR", font=FONT_UI_BOLD, bg="#5A5450", fg="#FFFFFF",
            activebackground="#3F3A37", activeforeground="#FFFFFF", relief="flat",
            cursor="hand2", padx=14, pady=7, state="disabled", command=self.parar_processamento
        )
        self.btn_parar.pack(side="right")

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

        # Painel do lote: um cliente por linha com a etapa atual (aparece só durante o lote)
        self.frm_andamento = tk.Frame(tab_terminal, bg=BG_PANEL, padx=10, pady=6,
                                      highlightthickness=1, highlightbackground=BORDER_COLOR)
        tk.Label(self.frm_andamento, text="ANDAMENTO DO LOTE:", font=("Segoe UI", 8, "bold"),
                 bg=BG_PANEL, fg=TEXT_MUTED).pack(anchor="w")
        self.lbl_andamento = tk.Label(self.frm_andamento, text="", font=FONT_MONO, bg=BG_PANEL,
                                      fg=TEXT_MAIN, justify="left", anchor="w")
        self.lbl_andamento.pack(anchor="w", fill="x")
        self._andamento = []

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
            mensagem = f"[{nivel}] {mensagem}"
        self.log_queue.put(mensagem)
        # cópia em arquivo (um por dia) para conferir execuções depois
        try:
            pasta = Path(USER_DATA_DIR) / "logs"
            pasta.mkdir(parents=True, exist_ok=True)
            with self._log_lock, open(pasta / f"{time.strftime('%Y-%m-%d')}.log", "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} | {mensagem}\n")
        except Exception:
            pass

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

        self._travar_botoes(True)
        self.btn_baixar.config(bg="#DDD7CD", fg=TEXT_MUTED, cursor="arrow")
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
            self.service = self._novo_servico(DownloaderService, progress_callback=self.atualizar_progresso)
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
                self._travar_botoes(False)
                self.btn_baixar.config(bg=ACCENT_AMBER, fg="#FFFFFF", cursor="hand2")
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

        if self.em_execucao:
            messagebox.showwarning("Em Execução", "Já existe um processamento em andamento.")
            return
        visivel = self.var_visivel.get()

        self._travar_botoes(True)
        self.btn_baixar.config(text="AGUARDE...")
        self.btn_subir_acordo.config(text="SUBINDO ACORDO...")
        self.definir_status_badge("executando")
        self.lbl_status_progresso.config(text=f"Processando acordo: {cliente}", fg=TEXT_MAIN)
        self.lbl_porcentagem.config(text="...")
        self.barra_progresso.config(mode="indeterminate")
        self.barra_progresso.start(10)

        threading.Thread(target=self._executar_worker_acordo, args=(cliente, visivel), daemon=True).start()

    def _executar_worker_acordo(self, cliente: str, visivel: bool):
        sucesso = False
        baixados = None
        service = None
        try:
            service = self._novo_servico(AcordoService)
            sucesso = service.subir_acordo_completo(cliente, visivel=visivel)
            if sucesso and self._cancelado:
                self.log(f"PARADO: acordo de '{cliente}' ok, download dos boletos não iniciado.", "WARNING")
                baixados = None
            elif sucesso:
                # Acordo subido: já baixa os boletos na mesma sessão do Global Office
                self.log(f"Acordo de '{cliente}' registrado. Baixando os boletos automaticamente...")

                def _preparar_download():
                    self.barra_progresso.stop()
                    self.barra_progresso.config(mode="determinate", value=0)
                    self.btn_subir_acordo.config(text="BAIXANDO BOLETOS...")
                    self.boletos_baixados.clear()
                    for item in self.tree_boletos.get_children():
                        self.tree_boletos.delete(item)
                    self.notebook.tab(self.tab_boletos_index, text="Boletos Baixados (0)")
                self.after(0, _preparar_download)

                try:
                    baixados = self._baixar_apos_acordo(service, cliente, visivel, self.atualizar_progresso,
                                                        reusar_sessao=not service.gravou_algo)
                    if baixados:
                        self.log(f"SUCESSO COMPLETO: acordo de '{cliente}' cadastrado e {baixados} boletos baixados!", "SUCCESS")
                    else:
                        self.log(f"ATENÇÃO: acordo de '{cliente}' cadastrado, mas NENHUM boleto foi baixado. "
                                 "Confira no Global Office e use BAIXAR BOLETOS.", "WARNING")
                except Exception as ex_dl:
                    self.log(f"Acordo de '{cliente}' foi enviado, mas houve erro ao baixar os boletos: {ex_dl}. "
                             "Use BAIXAR BOLETOS para tentar de novo.", "WARNING")
        except ProcessamentoCancelado:
            self.log(f"Processamento de '{cliente}' PARADO pelo usuário.", "WARNING")
        except Exception as e:
            self.log(f"Erro inesperado no envio do acordo: {e}", "ERROR")
        finally:
            if service:
                try:
                    service.fechar_sessao()
                except Exception:
                    pass

            def _reset():
                self.barra_progresso.stop()
                self.barra_progresso.config(mode="determinate", value=100 if sucesso else 0)
                self.lbl_porcentagem.config(text="100%" if sucesso else "0%")
                if sucesso and baixados is not None:
                    texto = f"Acordo de '{cliente}' enviado e {baixados} boletos baixados!"
                elif sucesso:
                    texto = f"Acordo de '{cliente}' enviado, mas o download dos boletos falhou."
                else:
                    texto = f"Processamento de '{cliente}' finalizado."
                self.lbl_status_progresso.config(text=texto, fg=ACCENT_OLIVE if sucesso else TEXT_TERRA)
                self._travar_botoes(False)
                self.btn_baixar.config(text="⬇ BAIXAR BOLETOS")
                self.btn_subir_acordo.config(text="🤝 SUBIR ACORDO JUDICIAL")
                self.definir_status_badge("sucesso" if sucesso else "pronto")
            self.after(0, _reset)

    def _baixar_apos_acordo(self, service, nome: str, visivel: bool, progresso=None,
                            reusar_sessao: bool = True) -> int:
        """Baixa os boletos do cliente. reusar_sessao=False (logo após GRAVAR um acordo): a tela de
        boletos da mesma sessão fica travada/vazia, então vai direto para sessões novas.
        Até 2 sessões novas, com pausa entre elas."""
        def resultado(res):
            baixados, encontrados = res.get("total_baixados", 0), res.get("total_encontrados", 0)
            if baixados == 0 and encontrados > 0:
                self.log(f"'{nome}': {encontrados} boletos no sistema, todos de meses anteriores. Nada a baixar.")
                return encontrados   # não é falha: só não há boleto do mês vigente em diante
            return baixados

        if reusar_sessao:
            pagina = service.page if service.page and not service.page.is_closed() else None
            try:
                n = resultado(self._novo_servico(DownloaderService, progress_callback=progresso)
                              .baixar_boletos_cliente(nome, visivel=visivel, page_existente=pagina))
                if n:
                    return n
                self.log(f"0 boletos de '{nome}' na mesma sessão.", "WARNING")
            except Exception as e:
                self.log(f"Download na mesma sessão falhou ({e}).", "WARNING")
        else:
            self.log(f"Acordo recém-gravado: baixando os boletos de '{nome}' numa sessão nova "
                     "(a tela de boletos da mesma sessão fica travada após a gravação).")

        service.fechar_sessao()
        for tentativa, pausa in ((1, 3000), (2, 10000)):
            if self._cancelado:
                break
            time.sleep(pausa / 1000)
            dl = self._novo_servico(DownloaderService, progress_callback=progresso)
            try:
                n = resultado(dl.baixar_boletos_cliente(nome, visivel=visivel))
                if n:
                    return n
                self.log(f"Sessão nova {tentativa}/2: 0 boletos de '{nome}'.", "WARNING")
            except Exception as e:
                self.log(f"Sessão nova {tentativa}/2 falhou para '{nome}' ({str(e).splitlines()[0][:120]}).", "WARNING")
            finally:
                try: dl.fechar_sessao()
                except Exception: pass
        return 0

    # ── PARAR / estado ocupado ──
    def parar_processamento(self):
        if not self.em_execucao:
            return
        self._cancelado = True
        for s in list(self._servicos_ativos):
            try:
                s.cancelar()
            except Exception:
                pass
        self.btn_parar.config(state="disabled", text="PARANDO...")
        self.log("PARAR solicitado: o robô para no próximo passo seguro (nada é gravado pela metade).", "WARNING")

    def _novo_servico(self, classe, **kw):
        """Cria um serviço já ligado ao botão PARAR."""
        if classe is DownloaderService:
            kw.setdefault("cancelado", lambda: self._cancelado)
        s = classe(log_callback=self.log, **kw)
        if classe is AcordoService:
            s.confirmar_gravacao = self._confirmar_boletos_novos
            if self._cancelado:
                s.cancelar()
        self._servicos_ativos.append(s)
        return s

    def _travar_botoes(self, travar: bool):
        estado = "disabled" if travar else "normal"
        for b in (self.btn_baixar, self.btn_subir_acordo, self.btn_lote5, self.btn_email, self.btn_dropbox):
            b.config(state=estado)
        self.btn_parar.config(state="normal" if travar else "disabled", text="⏹ PARAR")
        self.em_execucao = travar
        if travar:
            self._cancelado = False
            self._servicos_ativos = []

    def _perguntar(self, titulo: str, mensagem: str) -> Optional[bool]:
        """askyesnocancel chamado da thread de trabalho (espera a resposta na thread da tela)."""
        resposta = {}
        pronto = threading.Event()

        def _mostrar():
            resposta["r"] = messagebox.askyesnocancel(titulo, mensagem, parent=self)
            pronto.set()
        self.after(0, _mostrar)
        pronto.wait()
        return resposta["r"]

    # ── Painel "Andamento do lote" ──
    def _andamento_iniciar(self, nomes: list):
        self._andamento = [[n, "Aguardando"] for n in nomes]

        def _mostrar():
            self.frm_andamento.pack(fill="x", pady=(0, 6), before=self.txt_log)
            self._render_andamento()
        self.after(0, _mostrar)
        self.log("LISTA DO LOTE:\n" + "\n".join(f"{i} - {n} [Aguardando]" for i, n in enumerate(nomes, 1)))

    def _etapa(self, nome: str, texto: str, nivel: Optional[str] = None):
        """Atualiza a etapa do cliente no painel e registra no log ('2 - FULANO [Enviando e-mail]')."""
        for i, item in enumerate(self._andamento, 1):
            if item[0] == nome:
                item[1] = texto
                self.log(f"{i} - {nome} [{texto}]", nivel)
                break
        self.after(0, self._render_andamento)

    def _render_andamento(self):
        largura = max((len(n) for n, _ in self._andamento), default=0)
        self.lbl_andamento.config(text="\n".join(
            f"{i} - {n.ljust(largura)}  [{e}]" for i, (n, e) in enumerate(self._andamento, 1)))

    def _janela_email(self, nome: str, achado: dict) -> Optional[list]:
        """Janela (thread da tela) para confirmar/digitar o e-mail do cliente. None = pular."""
        janela = tk.Toplevel(self)
        janela.title("E-mail do cliente")
        janela.configure(bg=BG_MAIN)
        janela.resizable(False, False)
        janela.transient(self)
        janela.grab_set()
        frame = tk.Frame(janela, bg=BG_MAIN, padx=22, pady=18)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text=nome, font=("Segoe UI", 11, "bold"), bg=BG_MAIN, fg=TEXT_MAIN).pack(anchor="w")
        if achado["emails"]:
            topo = f"E-mail encontrado em: {achado['fonte']}\nConfira (ou corrija) antes de enviar."
        else:
            topo = "Não achei o e-mail deste cliente em lugar nenhum. Digite o e-mail ou pule o cliente."
        tk.Label(frame, text=topo, font=FONT_UI, bg=BG_MAIN, fg=TEXT_MAIN, justify="left").pack(anchor="w", pady=(4, 6))
        suspeitos = [e for e in achado["emails"] if re.search(r"adv|advoc|juridic", e, re.I)]
        if suspeitos:
            tk.Label(frame, text="⚠ Parece e-mail de advogado/escritório, não do cliente: " + ", ".join(suspeitos),
                     font=FONT_UI_BOLD, bg=BG_MAIN, fg=TEXT_TERRA, justify="left").pack(anchor="w", pady=(0, 6))
        if achado.get("motivos"):
            tk.Label(frame, text="Onde procurei:\n" + "\n".join(f"  • {m}" for m in achado["motivos"]),
                     font=("Segoe UI", 8), bg=BG_MAIN, fg=TEXT_MUTED, justify="left").pack(anchor="w", pady=(0, 8))
        tk.Label(frame, text="E-mail(s) — separe vários por ;", font=FONT_UI_BOLD, bg=BG_MAIN,
                 fg=TEXT_MUTED).pack(anchor="w")
        entrada = tk.Entry(frame, width=60, font=("Segoe UI", 10), bg=BG_INPUT, fg=TEXT_MAIN, relief="flat",
                           highlightthickness=1, highlightbackground=BORDER_COLOR)
        entrada.pack(fill="x", ipady=4, pady=(2, 4))
        entrada.insert(0, "; ".join(achado["emails"]))
        entrada.focus_set()
        aviso = tk.Label(frame, text="", font=("Segoe UI", 8), bg=BG_MAIN, fg=TEXT_TERRA)
        aviso.pack(anchor="w")
        resultado = {"emails": None}

        def usar(_evt=None):
            emails = email_service.EMAIL_RE.findall(entrada.get())
            if not emails:
                aviso.config(text="Digite um e-mail válido ou clique em 'Pular este cliente'.")
                return
            resultado["emails"] = list(dict.fromkeys(emails))
            janela.destroy()

        botoes = tk.Frame(frame, bg=BG_MAIN)
        botoes.pack(fill="x", pady=(10, 0))
        tk.Button(botoes, text="Pular este cliente", font=FONT_UI, bg=BG_PANEL, fg=TEXT_MAIN, relief="flat",
                  cursor="hand2", padx=12, pady=6, highlightthickness=1, highlightbackground=BORDER_COLOR,
                  command=janela.destroy).pack(side="left")
        tk.Button(botoes, text="✉ Enviar para este e-mail", font=FONT_UI_BOLD, bg="#B23A48", fg="#FFFFFF",
                  activebackground="#952F3B", activeforeground="#FFFFFF", relief="flat", cursor="hand2",
                  padx=14, pady=6, command=usar).pack(side="right")
        entrada.bind("<Return>", usar)
        janela.update_idletasks()
        w, h = janela.winfo_reqwidth(), janela.winfo_reqheight()
        janela.geometry(f"+{(self.winfo_screenwidth() - w) // 2}+{(self.winfo_screenheight() - h) // 2}")
        janela.wait_window()
        return resultado["emails"]

    def _janela_email_da_thread(self, nome: str, achado: dict) -> Optional[list]:
        """_janela_email chamada da thread do lote (espera a resposta na thread da tela)."""
        resposta, pronto = {}, threading.Event()

        def _mostrar():
            try:
                resposta["r"] = self._janela_email(nome, achado)
            finally:
                pronto.set()
        self.after(0, _mostrar)
        pronto.wait()
        return resposta.get("r")

    def _confirmar_email(self, msg: str) -> str:
        r = self._perguntar("Conferir e-mail",
                            msg + "\n\nConfira a janela do webmail.\n"
                                  "SIM = enviar   |   NÃO = pular este   |   CANCELAR = parar tudo")
        return "enviar" if r else ("parar" if r is None else "pular")

    def _enviar_email_no_lote(self, nome: str, svc, lista_emails: dict, conferir: bool) -> str:
        """Envia os boletos do cliente por e-mail dentro do lote. Devolve o texto do resultado.
        E-mail tirado do termo (fora da lista de envio) sempre pede confirmação."""
        achado = email_service.buscar_email_cliente(nome, lista_emails)
        pasta = email_service.localizar_pasta_boletos(nome, achado.get("pasta", ""))
        arquivos = email_service.boletos_a_enviar(pasta) if pasta else []
        if not arquivos:
            return "e-mail NÃO enviado: nenhum boleto do mês vigente em diante na pasta"
        anterior = email_service.ja_enviado(nome, arquivos)
        if anterior:
            return f"e-mail já tinha sido enviado em {anterior['data']}"
        emails, fonte = achado["emails"], achado["fonte"]
        if fonte != "lista de envio":
            # Fora da lista (termo / LAYNA / nada): janela para confirmar, digitar ou pular
            self.log(f"'{nome}': e-mail " + (f"encontrado em {fonte}: {', '.join(emails)}" if emails
                                             else "não encontrado (" + "; ".join(achado["motivos"]) + ")"))
            emails = self._janela_email_da_thread(nome, achado)
            if not emails:
                return "e-mail NÃO enviado: pulado por você (sem e-mail)"
            fonte = fonte or "digitado por você"
        self.log(f"E-mail de '{nome}' (fonte: {fonte}): {', '.join(emails)}")
        r = svc.enviar_boletos_cliente(email_service.limpar_nome(nome), emails, pasta,
                                       confirmar=self._confirmar_email if conferir else None, visivel=conferir)
        if r["status"] == "enviado":
            return f"e-mail enviado ({r['arquivos']} boletos) para {', '.join(emails)}"
        if r["status"] == "parado":
            self._cancelado = True
            return "e-mail NÃO enviado (parado)"
        return "e-mail pulado na conferência"

    def _mostrar_resultado_lote(self, resultados: list):
        """Janela final com o que aconteceu com cada cliente do lote."""
        if not resultados:
            return
        texto = "\n".join(f"{i}. {n}\n     → {r}" for i, (n, r) in enumerate(resultados, 1))
        self.log("RESULTADO POR CLIENTE:\n" + texto)
        self.after(0, lambda: messagebox.showinfo("Resultado do lote", texto, parent=self))

    def _confirmar_boletos_novos(self, resumo: str) -> bool:
        """Pergunta antes de gravar boletos pelo +NOVO (aviso 'Ficha financeira não atualizada')."""
        return self._perguntar(
            "Gravar boletos novos?",
            "A GEAP não tem valores em aberto para este cliente, então o acordo não pode ser subido.\n"
            "O robô preencheu Boletos > +NOVO com:\n\n" + resumo +
            "\n\nSIM = GRAVAR estes boletos   |   NÃO = cancelar sem gravar") is True

    # ── PROCESSAR 5 CLIENTES ──
    def abrir_dialogo_lote5(self):
        if self.em_execucao:
            messagebox.showwarning("Em Execução", "Já existe um processamento em andamento.")
            return
        janela = tk.Toplevel(self)
        janela.title("Processar 5 clientes")
        janela.configure(bg=BG_MAIN)
        janela.resizable(False, False)
        janela.transient(self)
        janela.grab_set()
        frame = tk.Frame(janela, bg=BG_MAIN, padx=22, pady=18)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Clientes na ordem de processamento", font=("Segoe UI", 11, "bold"),
                 bg=BG_MAIN, fg=TEXT_MAIN).pack(anchor="w")
        tk.Label(frame, text="O que fazer com cada um segue a coluna 'ENVIO DE BOLETOS' da planilha\n"
                             "(vazio = subir acordo + baixar, GERADO = só baixar, demais = pular).",
                 font=("Segoe UI", 8), bg=BG_MAIN, fg=TEXT_MUTED, justify="left").pack(anchor="w", pady=(2, 12))

        entradas = []
        for i in range(5):
            linha = tk.Frame(frame, bg=BG_MAIN)
            linha.pack(fill="x", pady=3)
            tk.Label(linha, text=f"{i + 1}.", width=3, font=FONT_UI_BOLD, bg=BG_MAIN, fg=TEXT_MUTED).pack(side="left")
            e = tk.Entry(linha, width=58, font=("Segoe UI", 10), bg=BG_INPUT, fg=TEXT_MAIN, relief="flat",
                         highlightthickness=1, highlightbackground=BORDER_COLOR)
            e.pack(side="left", fill="x", expand=True, ipady=4)
            entradas.append(e)
        if self.var_cliente.get().strip():
            entradas[0].insert(0, self.var_cliente.get().strip())
        entradas[0].focus_set()

        def preencher_pendentes():
            """Completa os campos vazios com os próximos pendentes da planilha (cópia local)."""
            try:
                todos = AcordoService(log_callback=lambda *a: None).lista_parcelados_com_status()
            except Exception as e:
                messagebox.showerror("Planilha", f"Não consegui ler a planilha:\n{e}", parent=janela)
                return
            ja = {normalizar_texto(e.get()) for e in entradas if e.get().strip()}
            pendentes = [n for n, st in todos if st in ("", "GERADO") and normalizar_texto(n) not in ja]
            vazios = [e for e in entradas if not e.get().strip()]
            for e in vazios:
                if pendentes:
                    e.insert(0, pendentes.pop(0))
            faltaram = sum(1 for e in vazios if not e.get().strip())
            if faltaram:
                messagebox.showinfo("Pendentes", f"A planilha só tem {len(vazios) - faltaram} cliente(s) pendente(s) "
                                    f"(status vazio ou GERADO) para completar a lista.", parent=janela)

        var_email = tk.BooleanVar(value=True)
        tk.Checkbutton(frame, text="Enviar os boletos por e-mail ao terminar cada cliente "
                                   "(segue a opção 'Conferir cada e-mail antes de enviar')",
                       variable=var_email, font=FONT_UI, bg=BG_MAIN, fg=TEXT_MAIN, selectcolor=BG_INPUT,
                       activebackground=BG_MAIN, highlightthickness=0).pack(anchor="w", pady=(10, 0))

        def iniciar():
            nomes = [" ".join(e.get().split()) for e in entradas if e.get().strip()]
            if not nomes:
                messagebox.showwarning("Lista vazia", "Digite pelo menos um nome.", parent=janela)
                return
            enviar = var_email.get()
            if enviar and not self.var_conferir_email.get() and not messagebox.askyesno(
                    "Envio automático",
                    "Os e-mails serão ENVIADOS direto, sem conferência (a opção 'Conferir cada e-mail' "
                    "está desmarcada).\n\nTem certeza?", parent=janela):
                return
            janela.destroy()
            self.iniciar_lote(nomes, enviar_email=enviar)

        botoes = tk.Frame(frame, bg=BG_MAIN)
        botoes.pack(fill="x", pady=(14, 0))
        tk.Button(botoes, text="Preencher com os próximos pendentes da planilha", font=FONT_UI,
                  bg=BG_PANEL, fg=TEXT_MAIN, relief="flat", cursor="hand2", padx=10, pady=6,
                  highlightthickness=1, highlightbackground=BORDER_COLOR,
                  command=preencher_pendentes).pack(side="left")
        tk.Button(botoes, text="▶ INICIAR", font=FONT_UI_BOLD, bg="#5B4A8A", fg="#FFFFFF",
                  activebackground="#483A72", activeforeground="#FFFFFF", relief="flat",
                  cursor="hand2", padx=18, pady=6, command=iniciar).pack(side="right")

        janela.update_idletasks()
        w, h = janela.winfo_reqwidth(), janela.winfo_reqheight()
        janela.geometry(f"+{(self.winfo_screenwidth() - w) // 2}+{(self.winfo_screenheight() - h) // 2}")

    def iniciar_lote(self, nomes: Optional[list] = None, enviar_email: bool = False):
        """Processa os clientes informados, na ordem (nomes=None: todos os parcelados da planilha)."""
        visivel = self.var_visivel.get()
        self._lote_email = (enviar_email, self.var_conferir_email.get())
        self._travar_botoes(True)
        self.btn_lote5.config(text="PROCESSANDO...")
        self.definir_status_badge("executando")
        self.barra_progresso.config(mode="indeterminate")
        self.barra_progresso.start(10)
        self.lbl_status_progresso.config(text="Lendo planilha de parcelados...", fg=TEXT_MAIN)

        threading.Thread(target=self._worker_todos_parcelados, args=(visivel, nomes), daemon=True).start()

    def _worker_todos_parcelados(self, visivel: bool, nomes: Optional[list] = None):
        """Worker thread para processar os parcelados em sequência."""
        from baixar_boletos.planilha_sync import sincronizar_planilha
        service = self._novo_servico(AcordoService)
        resultados = []                 # [(nome, o que aconteceu)] para o resumo final
        todos = []
        try:
            # Baixa a planilha oficial do OneDrive, avisa se estiver velha e lista as alterações
            caminho = sincronizar_planilha(self.log)
            todos = service.lista_parcelados_com_status(str(caminho) if caminho else None)
        except Exception as e:
            self.log(f"Erro ao ler planilha: {e}", "ERROR")

        if nomes is not None:
            # Só os nomes informados, na ordem digitada, com o status que a planilha tiver
            status_de = {normalizar_texto(n): (n, st) for n, st in todos}
            selecionados = []
            for n in nomes:
                if normalizar_texto(n) in status_de:
                    selecionados.append(status_de[normalizar_texto(n)])
                    continue
                # Fora da lista de PARCELADOS: só dá para processar se a planilha tiver os dados
                try:
                    dados = service.parser.carregar_dados_cliente(n)
                except Exception as e:
                    dados = {"sucesso": False, "motivo_erro": str(e)}
                if dados.get("sucesso", True):
                    self.log(f"'{n}' não está entre os PARCELADOS da planilha, mas tem dados: tentando subir acordo + baixar.", "WARNING")
                    selecionados.append((n, ""))
                else:
                    selecionados.append((n, "NAO ENCONTRADO"))
                    resultados.append((n, "PULADO: nome não encontrado na planilha (confira a grafia)"))
                    self.log(f"PULADO '{n}': {dados.get('motivo_erro') or 'não localizado na planilha'}.", "WARNING")
            todos = selecionados

        # Coluna "ENVIO DE BOLETOS" decide o que fazer com cada cliente:
        #   vazio   -> subir acordo + baixar boletos
        #   GERADO  -> acordo já subido: só baixar boletos
        #   ENVIADO / OK / NAO ENVIAR -> nada a fazer
        #   CONFERIR (ou valor desconhecido) -> pula e lista para conferência manual
        PULAR = {"ENVIADO": "boletos já enviados", "OK": "pago à vista", "NAO ENVIAR": "marcado para não enviar"}
        lista = []                      # [(nome, so_baixar)]
        pulados_status = {}
        conferir = []
        for nome, status in todos:
            if nomes is not None:
                # Nomes digitados: o usuário escolheu processar. Só não mexe em quem está
                # marcado para não receber boleto (pago à vista / NÃO ENVIAR).
                if status == "NAO ENCONTRADO":
                    continue   # já registrado acima
                if status in ("OK", "NAO ENVIAR"):
                    pulados_status[status] = pulados_status.get(status, 0) + 1
                    resultados.append((nome, f"PULADO: planilha marca '{status}' ({PULAR[status]})"))
                    self.log(f"PULADO '{nome}': planilha marca '{status}' ({PULAR[status]}).", "WARNING")
                else:
                    lista.append((nome, status in ("GERADO", "ENVIADO")))
                    self.log(f"'{nome}': status '{status or 'vazio'}' -> "
                             + ("só baixar boletos" if status in ("GERADO", "ENVIADO") else "subir acordo + baixar"))
                continue
            if status == "":
                lista.append((nome, False))
            elif status == "GERADO":
                lista.append((nome, True))
            elif status in PULAR:
                pulados_status[status] = pulados_status.get(status, 0) + 1
            else:
                conferir.append(f"{nome} ({status})")

        self.log(
            f"Status 'ENVIO DE BOLETOS': {sum(1 for _, s in lista if not s)} vazios (subir acordo), "
            f"{sum(1 for _, s in lista if s)} GERADO (só baixar), "
            + ", ".join(f"{q} {k}" for k, q in pulados_status.items())
            + f", {len(conferir)} para conferir."
        )
        for item in conferir:
            self.log(f"  PULADO para conferência manual: {item}", "WARNING")

        total = len(lista)
        # Painel de andamento: todos os nomes na ordem (os pulados pela planilha já marcados)
        self._andamento_iniciar([n for n, _ in todos] if nomes is not None else [n for n, _ in lista])
        for n, r in resultados:
            self._etapa(n, r)
        if total == 0:
            self.log("Nenhum cliente PARCELADO pendente na planilha.", "WARNING")
            service.fechar_sessao()
            self._mostrar_resultado_lote(resultados)
            self.after(0, self._reset_btn_lote)
            return

        enviar_email, conferir_email = getattr(self, "_lote_email", (False, True))
        email_svc, lista_emails = None, {}
        if enviar_email:
            try:
                lista_emails = email_service.carregar_lista_emails()
            except Exception as e:
                self.log(f"Lista de e-mails não lida ({e}): os e-mails serão procurados nos termos.", "WARNING")
            email_svc = email_service.EmailService(log_callback=self.log, cancelado=lambda: self._cancelado)
            # O Playwright só permite um navegador por thread: o webmail roda numa thread própria,
            # separada da do Global Office (senão: "Sync API inside the asyncio loop").
            from concurrent.futures import ThreadPoolExecutor
            email_thread = ThreadPoolExecutor(max_workers=1, thread_name_prefix="webmail")

            def no_webmail(fn, *args):
                return email_thread.submit(fn, *args).result()

        self.log(f"Iniciando lote: {total} clientes PARCELADOS para processar"
                 + (" (com envio por e-mail)." if enviar_email else "."))
        sucesso_count = 0
        erro_count = 0
        pulo_count = 0
        sem_boletos = []

        def parar_restantes(a_partir):
            for n, _ in lista[a_partir:]:
                resultados.append((n, "NÃO PROCESSADO (lote parado)"))
                self._etapa(n, "Não processado (lote parado)")

        for i, (nome, so_baixar) in enumerate(lista, 1):
            if self._cancelado:
                self.log(f"Lote PARADO pelo usuário antes de '{nome}'.", "WARNING")
                parar_restantes(i - 1)
                break

            self.after(0, lambda n=nome, idx=i: (
                self.lbl_status_progresso.config(text=f"[{idx}/{total}] {n}", fg=TEXT_MAIN),
                self.barra_progresso.config(mode="determinate", value=int((idx / total) * 100)),
            ))

            resultado, boletos_ok = None, False
            try:
                # 1. Pasta do Dropbox já completa: pula Global Office (o e-mail ainda vai)
                self._etapa(nome, "Conferindo a pasta de boletos")
                status_boletos = service.verificar_boletos_completos(nome)
                if status_boletos["completo"]:
                    pulo_count += 1
                    boletos_ok = True
                    resultado = f"pasta já tinha os {status_boletos['encontrados']} boletos"
                    self.log(f"[{i}/{total}] '{nome}': a pasta já tem todos os boletos. Global Office pulado.")
                else:
                    # 2. Acordo (pulado se GERADO/ENVIADO) e download
                    if so_baixar:
                        self._etapa(nome, "Acordo já no sistema: indo para os boletos")
                        service.garantir_sessao_ativa(visivel=visivel)
                        ok_acordo = True
                    else:
                        self._etapa(nome, "Subindo o acordo no Global Office")
                        ok_acordo = service.subir_acordo_completo(nome, visivel=visivel)

                    if ok_acordo and self._cancelado:
                        resultados.append((nome, "acordo ok, boletos NÃO baixados (lote parado)"))
                        self._etapa(nome, "Acordo ok, parado antes dos boletos", "WARNING")
                        sucesso_count += 1
                        parar_restantes(i)
                        break
                    if ok_acordo:
                        self._etapa(nome, "Baixando os boletos")
                        try:
                            total_baixados = self._baixar_apos_acordo(
                                service, nome, visivel, reusar_sessao=so_baixar or not service.gravou_algo)
                        except Exception as ex_dl:
                            self.log(f"[{i}/{total}] Erro ao baixar boletos de '{nome}': {ex_dl}", "WARNING")
                            total_baixados = 0
                        if total_baixados:
                            sucesso_count += 1
                            boletos_ok = True
                            resultado = f"{total_baixados} boletos baixados"
                        else:
                            sem_boletos.append(nome)
                            resultado = "ATENÇÃO: nenhum boleto baixado"
                    else:
                        erro_count += 1
                        resultado = "FALHOU: acordo e boletos avulsos não criados (ver log)"

                # 3. E-mail (só com boletos na pasta)
                if enviar_email and boletos_ok and not self._cancelado:
                    self._etapa(nome, "Agora enviando os boletos por e-mail")
                    try:
                        resultado += " | " + no_webmail(self._enviar_email_no_lote, nome, email_svc,
                                                        lista_emails, conferir_email)
                    except Exception as ex_mail:
                        resultado += f" | ERRO no e-mail: {str(ex_mail)[:60]}"
                        try: no_webmail(email_svc.descartar)
                        except Exception: no_webmail(email_svc.fechar_sessao)

                completo = boletos_ok and ("e-mail enviado" in resultado or not enviar_email)
                resultados.append((nome, resultado))
                self._etapa(nome, ("Processamento completo: " if completo else "") + resultado,
                            "SUCCESS" if completo else "WARNING")
            except ProcessamentoCancelado:
                resultados.append((nome, "PARADO no meio (confira no Global Office)"))
                self._etapa(nome, "PARADO no meio (confira no Global Office)", "WARNING")
                parar_restantes(i)
                break
            except Exception as ex:
                erro_count += 1
                resultados.append((nome, f"ERRO: {str(ex)[:80]}"))
                self._etapa(nome, f"ERRO: {str(ex)[:80]}", "ERROR")

        service.fechar_sessao()
        if email_svc:
            try:
                no_webmail(email_svc.fechar_sessao)
            finally:
                email_thread.shutdown(wait=False)
        self._mostrar_resultado_lote(resultados)
        resumo = (f"Lote concluído: {sucesso_count} completos (com boletos), {len(sem_boletos)} sem boletos baixados, "
                  f"{pulo_count} pulados (já prontos), {erro_count} com falha, de {total} total.")
        self.log(resumo)
        for n in sem_boletos:
            self.log(f"  SEM BOLETOS (conferir / usar BAIXAR BOLETOS): {n}", "WARNING")
        self.after(0, lambda: self.lbl_status_progresso.config(text=resumo, fg=TEXT_MAIN))
        self.after(0, self._reset_btn_lote)

    def _reset_btn_lote(self):
        self.barra_progresso.stop()
        self.barra_progresso.config(mode="determinate", value=100)
        self._travar_botoes(False)
        self.btn_lote5.config(text="📋 PROCESSAR 5 CLIENTES")
        self.btn_email.config(text="✉ ENVIAR BOLETOS POR E-MAIL")
        self.definir_status_badge("sucesso")

    # ── ENVIAR BOLETOS POR E-MAIL ──
    def iniciar_envio_email(self):
        if self.em_execucao:
            messagebox.showwarning("Em Execução", "Já existe um processamento em andamento.")
            return
        lista_path = email_service.localizar_lista_emails()
        try:
            lista = email_service.carregar_lista_emails(lista_path)
        except Exception as e:
            messagebox.showerror("Lista de e-mails", f"Não consegui ler a lista de envio:\n{e}")
            return

        cliente = self.var_cliente.get().strip()
        if cliente:
            nome = email_service.limpar_nome(cliente)
            item = lista.get(normalizar_texto(nome), {"nome": nome, "emails": [], "pasta": ""})
            if not item["emails"]:
                # Fora da lista: procura no termo e na planilha da LAYNA e pede confirmação
                self.config(cursor="watch"); self.update_idletasks()
                try:
                    achado = email_service.buscar_email_cliente(nome, lista)
                finally:
                    self.config(cursor="")
                if achado["emails"]:
                    self.log(f"E-mail de {nome} encontrado em {achado['fonte']}: {', '.join(achado['emails'])}")
                emails = self._janela_email(nome, achado)
                if not emails:
                    return
                item["emails"] = emails
            alvos = [item]
        else:
            alvos = [x for x in lista.values() if x["emails"]]
            sem = [x["nome"] for x in lista.values() if not x["emails"]]
            if not alvos:
                messagebox.showwarning("Lista de e-mails", "Digite o nome do cliente (nenhuma lista de envio com e-mails foi encontrada).")
                return
            if not messagebox.askyesno(
                    "Enviar para a lista",
                    f"Lista: {lista_path.name if lista_path else '-'}\n\n"
                    f"{len(alvos)} clientes com e-mail ({len(sem)} sem e-mail serão pulados).\n"
                    "Clientes que já receberam estes mesmos boletos também serão pulados.\n\nContinuar?"):
                return

        conferir = self.var_conferir_email.get()
        if not conferir and not messagebox.askyesno(
                "Envio automático",
                f"Os e-mails serão ENVIADOS direto, sem conferência ({len(alvos)} cliente(s)).\n\nTem certeza?"):
            return

        self._travar_botoes(True)
        self.btn_email.config(text="ENVIANDO...")
        self.definir_status_badge("executando")
        visivel = conferir or self.var_visivel.get()
        threading.Thread(target=self._worker_email, args=(alvos, conferir, visivel, bool(cliente)), daemon=True).start()

    def _worker_email(self, alvos: list, conferir: bool, visivel: bool, individual: bool):
        svc = email_service.EmailService(log_callback=self.log, cancelado=lambda: self._cancelado)
        enviados, pulados, falhas = 0, [], []
        total = len(alvos)

        confirmar = self._confirmar_email

        try:
            for i, item in enumerate(alvos, 1):
                nome = item["nome"]
                if self._cancelado:
                    self.log(f"Envio PARADO pelo usuário antes de '{nome}'.", "WARNING")
                    break
                self.after(0, lambda n=nome, idx=i: (
                    self.lbl_status_progresso.config(text=f"[{idx}/{total}] E-mail: {n}", fg=TEXT_MAIN),
                    self.barra_progresso.config(mode="determinate", value=int((idx - 1) / total * 100))))

                pasta = email_service.localizar_pasta_boletos(nome, item.get("pasta", ""))
                if not pasta:
                    falhas.append(f"{nome}: pasta BOLETOS DO ACORDO não encontrada")
                    self.log(f"[{i}/{total}] {falhas[-1]}", "WARNING")
                    continue
                arquivos = email_service.boletos_a_enviar(pasta)
                if not arquivos:
                    pulados.append(f"{nome}: nenhum boleto do mês vigente em diante")
                    self.log(f"[{i}/{total}] {pulados[-1]}", "WARNING")
                    continue
                anterior = email_service.ja_enviado(nome, arquivos)
                if anterior:
                    aviso = f"{nome}: estes boletos já foram enviados em {anterior['data']} para {', '.join(anterior['para'])}"
                    if not individual or not self._perguntar("Já enviado", aviso + "\n\nEnviar de novo?"):
                        pulados.append(aviso)
                        self.log(f"[{i}/{total}] PULADO: {aviso}", "WARNING")
                        continue
                for e in item["emails"]:
                    if ".qov." in e.lower() or e.lower().endswith((".con", ".comm", ".br.br")):
                        self.log(f"[{i}/{total}] Atenção: e-mail possivelmente digitado errado: {e}", "WARNING")
                try:
                    r = svc.enviar_boletos_cliente(nome, item["emails"], pasta,
                                                   confirmar=confirmar if conferir else None, visivel=visivel)
                except Exception as ex:
                    falhas.append(f"{nome}: {ex}")
                    self.log(f"[{i}/{total}] ERRO no e-mail de '{nome}': {ex}", "ERROR")
                    try:
                        svc.descartar()
                    except Exception:
                        svc.fechar_sessao()
                    continue
                if r["status"] == "enviado":
                    enviados += 1
                elif r["status"] == "parado":
                    self._cancelado = True
                    self.log("Envio PARADO pelo usuário.", "WARNING")
                    break
                else:
                    pulados.append(f"{nome}: pulado na conferência")
        finally:
            svc.fechar_sessao()

        resumo = f"E-mails: {enviados} enviados, {len(pulados)} pulados, {len(falhas)} com falha (de {total})."
        self.log(resumo, "SUCCESS" if not falhas else "WARNING")
        for f in falhas:
            self.log(f"  FALHA: {f}", "WARNING")
        self.after(0, lambda: self.lbl_status_progresso.config(text=resumo, fg=TEXT_MAIN))
        self.after(0, self._reset_btn_lote)

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
        janela.geometry("460x520")
        janela.resizable(False, False)
        janela.configure(bg=BG_MAIN)
        janela.transient(self)
        janela.grab_set()

        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        janela.geometry(f"460x520+{(sw-460)//2}+{(sh-520)//2}")

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

        # Webmail Locaweb (envio dos boletos por e-mail)
        tk.Frame(frame, bg=BORDER_COLOR, height=1).pack(fill="x", pady=(16, 10))
        tk.Label(frame, text="Webmail (envio dos boletos por e-mail):", font=FONT_UI_BOLD,
                 bg=BG_MAIN, fg=TEXT_MUTED).pack(anchor="w", pady=(0, 2))
        linha_wm = tk.Frame(frame, bg=BG_MAIN)
        linha_wm.pack(fill="x")
        ent_wm_user = tk.Entry(linha_wm, font=("Segoe UI", 9), bg=BG_INPUT, fg=TEXT_MAIN, relief="flat",
                               highlightthickness=1, highlightbackground=BORDER_COLOR)
        ent_wm_user.pack(side="left", fill="x", expand=True, ipady=3, padx=(0, 6))
        ent_wm_user.insert(0, os.getenv("WEBMAIL_USER", "financeiro.accobranca@aldriguescandido.adv.br"))
        ent_wm_pass = tk.Entry(linha_wm, width=14, font=("Segoe UI", 9), bg=BG_INPUT, fg=TEXT_MAIN, relief="flat",
                               show="*", highlightthickness=1, highlightbackground=BORDER_COLOR)
        ent_wm_pass.pack(side="left", ipady=3, padx=(0, 6))
        ent_wm_pass.insert(0, os.getenv("WEBMAIL_PASS", ""))

        def salvar_webmail():
            if not ent_wm_user.get().strip() or not ent_wm_pass.get().strip():
                messagebox.showwarning("Webmail", "Preencha o e-mail e a senha do webmail.", parent=janela)
                return
            salvar_credenciais_webmail(ent_wm_user.get(), ent_wm_pass.get())
            messagebox.showinfo("Webmail", "Login do webmail salvo neste computador.", parent=janela)

        tk.Button(linha_wm, text="Salvar", font=FONT_UI_BOLD, bg=ACCENT_OLIVE, fg="#FFFFFF",
                  activebackground=ACCENT_OLIVE_HOVER, activeforeground="#FFFFFF", relief="flat",
                  cursor="hand2", padx=10, command=salvar_webmail).pack(side="left")

def main():
    app = AppBaixarBoletos()
    app.mainloop()

if __name__ == "__main__":
    main()
