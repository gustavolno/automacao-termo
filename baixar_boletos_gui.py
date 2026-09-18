import os
import sys
import threading
import queue
import time
import ctypes
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# Configura caminho dos navegadores do Playwright
if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "ms-playwright"
    )

from baixar_boletos.config import (
    obter_pasta_boletos_cliente,
    GLOBAL_OFFICE_LOGIN,
    GLOBAL_OFFICE_USER
)
from baixar_boletos.downloader_service import DownloaderService

# ============================================================
# DESIGN SYSTEM — ALDRIGUES CÂNDIDO ADVOCACIA (DARK EXECUTIVE)
# ============================================================
BG_MAIN = "#0B0F17"        # Dark Midnight Slate Background
BG_NAV = "#111827"         # Executive Header Surface
BG_CARD = "#1E293B"        # Slate Card Container
BG_INPUT = "#0F172A"       # Deep Inset Input Field Background
BORDER_COLOR = "#334155"   # Subtle Legal Slate Border

ACCENT_GOLD = "#C5A059"    # Luxury Law Firm Gold (Primary Brand Accent)
ACCENT_GOLD_HOVER = "#E5C170"
ACCENT_EMERALD = "#10B981" # Legal Mint Green
ACCENT_EMERALD_HOVER = "#34D399"
ACCENT_AMBER = "#F59E0B"
ACCENT_RED = "#EF4444"

TEXT_BRIGHT = "#F8FAFC"    # Crisp White Primary Text
TEXT_MUTED = "#94A3B8"     # Soft Slate Text

FONT_BRAND = ("Georgia", 11, "bold")
FONT_UI = ("Segoe UI", 9)
FONT_UI_BOLD = ("Segoe UI", 9, "bold")
FONT_UI_TITLE = ("Segoe UI", 10, "bold")
FONT_MONO = ("Consolas", 9)

def aplicar_tema_titulo_escuro(window):
    """Aplica o tema escuro nativo na barra de título do Windows (Windows 10/11 DWM)."""
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if not hwnd:
            hwnd = window.winfo_id()
        value = ctypes.c_int(1)
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
        self.minsize(880, 620)

        aplicar_tema_titulo_escuro(self)

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
        w, h = 980, 720
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        aplicar_tema_titulo_escuro(self)

    def _configurar_estilos(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        # Configura Abas (Notebook)
        style.configure("TNotebook", background=BG_MAIN, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_CARD, foreground=TEXT_MUTED,
                        font=FONT_UI_BOLD, padding=[16, 6], borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", BG_NAV), ("active", BORDER_COLOR)],
                  foreground=[("selected", ACCENT_GOLD), ("active", TEXT_BRIGHT)])

        # Configura Treeview
        style.configure("Treeview", background=BG_CARD, foreground=TEXT_BRIGHT,
                        fieldbackground=BG_CARD, font=FONT_UI, rowheight=26, borderwidth=0)
        style.configure("Treeview.Heading", background=BG_NAV, foreground=ACCENT_GOLD,
                        font=FONT_UI_BOLD, relief="flat", padding=[8, 4])
        style.map("Treeview", background=[("selected", BG_INPUT)], foreground=[("selected", ACCENT_GOLD_HOVER)])

        # Configura Progressbar
        style.configure("Custom.Horizontal.TProgressbar",
                        troughcolor=BG_INPUT,
                        background=ACCENT_GOLD,
                        darkcolor=ACCENT_GOLD,
                        lightcolor=ACCENT_GOLD,
                        bordercolor=BORDER_COLOR,
                        thickness=14)

    def _build_ui(self):
        # ── 1. NAV BAR SUPERIOR EXECUTIVE ──
        navbar = tk.Frame(self, bg=BG_NAV, height=62, highlightthickness=1, highlightbackground=BORDER_COLOR)
        navbar.pack(fill="x")
        navbar.pack_propagate(False)

        brand_frame = tk.Frame(navbar, bg=BG_NAV)
        brand_frame.pack(side="left", padx=20)

        lbl_logo = tk.Label(brand_frame, text="⚖", font=("Segoe UI", 16), bg=BG_NAV, fg=ACCENT_GOLD)
        lbl_logo.pack(side="left", padx=(0, 8))

        brand_text_frame = tk.Frame(brand_frame, bg=BG_NAV)
        brand_text_frame.pack(side="left")

        lbl_title = tk.Label(brand_text_frame, text="ALDRIGUES CÂNDIDO ADVOCACIA",
                             font=FONT_BRAND, bg=BG_NAV, fg=ACCENT_GOLD)
        lbl_title.pack(anchor="w")

        lbl_sub = tk.Label(brand_text_frame, text="Central de Download & Organização de Boletos (Global Office / Dropbox)",
                           font=("Segoe UI", 8), bg=BG_NAV, fg=TEXT_MUTED)
        lbl_sub.pack(anchor="w")

        # Badge de Status (canto superior direito)
        self.badge_status = tk.Label(navbar, text="● Sistema Pronto", font=FONT_UI_BOLD,
                                     bg="#064E3B", fg="#34D399", padx=14, pady=5, relief="flat")
        self.badge_status.pack(side="right", padx=20)

        # ── 2. CONTAINER PRINCIPAL ──
        container = tk.Frame(self, bg=BG_MAIN, padx=24, pady=16)
        container.pack(fill="both", expand=True)

        # ── 3. CARD DE BUSCA / COMANDO ──
        card_busca = tk.Frame(container, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR, padx=18, pady=16)
        card_busca.pack(fill="x", pady=(0, 14))

        # Linha 1: Label
        lbl_cliente = tk.Label(card_busca, text="NOME COMPLETO DO CLIENTE:", font=FONT_UI_BOLD, bg=BG_CARD, fg=TEXT_MUTED)
        lbl_cliente.grid(row=0, column=0, sticky="w", pady=(0, 6))

        # Linha 2: Entry de texto do cliente
        self.var_cliente = tk.StringVar()
        self.entry_cliente = tk.Entry(card_busca, textvariable=self.var_cliente, font=("Segoe UI", 11, "bold"),
                                      bg=BG_INPUT, fg=TEXT_BRIGHT, insertbackground=TEXT_BRIGHT,
                                      relief="flat", highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.entry_cliente.grid(row=1, column=0, sticky="ew", padx=(0, 14), ipady=6)
        card_busca.columnconfigure(0, weight=1)

        # Botão BAIXAR BOLETOS
        self.btn_baixar = tk.Button(card_busca, text="⬇ BAIXAR BOLETOS", font=FONT_UI_BOLD,
                                    bg=ACCENT_GOLD, fg="#0B0F17", activebackground=ACCENT_GOLD_HOVER,
                                    relief="flat", cursor="hand2", padx=18, pady=7,
                                    command=self.iniciar_download)
        self.btn_baixar.grid(row=1, column=1, padx=(0, 8))

        # Botão ABRIR NO DROPBOX
        self.btn_dropbox = tk.Button(card_busca, text="📁 ABRIR NO DROPBOX", font=FONT_UI_BOLD,
                                     bg=ACCENT_EMERALD, fg="#FFFFFF", activebackground=ACCENT_EMERALD_HOVER,
                                     relief="flat", cursor="hand2", padx=16, pady=7,
                                     command=self.abrir_pasta_dropbox)
        self.btn_dropbox.grid(row=1, column=2)

        # Linha 3: Checkbox de navegador visível
        self.var_visivel = tk.BooleanVar(value=False)
        self.chk_visivel = tk.Checkbutton(card_busca, text="Exibir janela do navegador durante a captura",
                                          variable=self.var_visivel, font=FONT_UI, bg=BG_CARD, fg=TEXT_MUTED,
                                          selectcolor=BG_INPUT, activebackground=BG_CARD,
                                          activeforeground=TEXT_BRIGHT, highlightthickness=0)
        self.chk_visivel.grid(row=2, column=0, sticky="w", pady=(8, 0))

        # Atalho: Enter no campo inicia o download
        self.entry_cliente.bind("<Return>", lambda event: self.iniciar_download())

        # ── 4. CARD DE PROGRESSO ──
        card_progresso = tk.Frame(container, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR, padx=18, pady=12)
        card_progresso.pack(fill="x", pady=(0, 14))

        prog_topo = tk.Frame(card_progresso, bg=BG_CARD)
        prog_topo.pack(fill="x", pady=(0, 6))

        self.lbl_status_progresso = tk.Label(prog_topo, text="Aguardando comando...", font=FONT_UI_BOLD, bg=BG_CARD, fg=TEXT_BRIGHT)
        self.lbl_status_progresso.pack(side="left")

        self.lbl_porcentagem = tk.Label(prog_topo, text="0%", font=FONT_UI_BOLD, bg=BG_CARD, fg=ACCENT_GOLD)
        self.lbl_porcentagem.pack(side="right")

        self.barra_progresso = ttk.Progressbar(card_progresso, style="Custom.Horizontal.TProgressbar",
                                                orient="horizontal", mode="determinate")
        self.barra_progresso.pack(fill="x", pady=(0, 8))

        self.lbl_meta = tk.Label(card_progresso,
                                 text="Encontrados: 0   |   Baixados: 0   |   Destino: —",
                                 font=("Segoe UI", 8), bg=BG_CARD, fg=TEXT_MUTED)
        self.lbl_meta.pack(anchor="w")

        # ── 5. NOTEBOOK / ABAS (TERMINAL & BOLETOS BAIXADOS) ──
        self.notebook = ttk.Notebook(container)
        self.notebook.pack(fill="both", expand=True)

        # ── ABA 1: TERMINAL EM TEMPO REAL ──
        tab_terminal = tk.Frame(self.notebook, bg=BG_NAV)
        self.notebook.add(tab_terminal, text="Terminal em Tempo Real")

        # Cabeçalho da aba de terminal
        head_term = tk.Frame(tab_terminal, bg=BG_NAV, padx=12, pady=8)
        head_term.pack(fill="x")

        tk.Label(head_term, text="LOGS DETALHADOS DA EXECUÇÃO:", font=("Segoe UI", 8, "bold"),
                 bg=BG_NAV, fg=TEXT_MUTED).pack(side="left")

        btn_limpar = tk.Button(head_term, text="Limpar Log", font=("Segoe UI", 8),
                               bg=BG_CARD, fg=TEXT_MUTED, activebackground=BORDER_COLOR,
                               activeforeground=TEXT_BRIGHT, relief="flat", padx=10, pady=2,
                               cursor="hand2", command=self.limpar_log)
        btn_limpar.pack(side="right")

        # Console de texto
        self.txt_log = scrolledtext.ScrolledText(tab_terminal, bg="#080C13", fg="#E2E8F0",
                                                font=FONT_MONO, relief="flat",
                                                insertbackground=TEXT_BRIGHT,
                                                highlightthickness=1, highlightbackground=BORDER_COLOR)
        self.txt_log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Cores para tags de log
        self.txt_log.tag_config("INFO", foreground="#E2E8F0")
        self.txt_log.tag_config("WARNING", foreground=ACCENT_AMBER)
        self.txt_log.tag_config("ERROR", foreground=ACCENT_RED)
        self.txt_log.tag_config("SUCCESS", foreground=ACCENT_EMERALD)
        self.txt_log.tag_config("TIME", foreground="#64748B")

        # ── ABA 2: BOLETOS BAIXADOS ──
        tab_boletos = tk.Frame(self.notebook, bg=BG_NAV, padx=12, pady=12)
        self.notebook.add(tab_boletos, text="Boletos Baixados (0)")
        self.tab_boletos_index = 1

        # Treeview de boletos
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

    def log(self, mensagem: str):
        self.log_queue.put(mensagem)

    def _processar_fila_logs(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get_nowait()
            self._adicionar_log_formatado(msg)
        self.after(100, self._processar_fila_logs)

    def _adicionar_log_formatado(self, linha: str):
        self.txt_log.config(state="normal")
        tag = "INFO"
        if "ERROR" in linha:
            tag = "ERROR"
        elif "WARNING" in linha:
            tag = "WARNING"
        elif "sucesso" in linha.lower() or "finalizado" in linha.lower():
            tag = "SUCCESS"

        self.txt_log.insert("end", linha + "\n", tag)
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")

    def limpar_log(self):
        self.txt_log.config(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.config(state="disabled")

    def definir_status_badge(self, tipo: str):
        """Atualiza a badge de status no canto superior direito."""
        if tipo == "pronto":
            self.badge_status.config(text="● Sistema Pronto", bg="#064E3B", fg="#34D399")
        elif tipo == "executando":
            self.badge_status.config(text="● Em Execução", bg="#78350F", fg="#F59E0B")
        elif tipo == "sucesso":
            self.badge_status.config(text="● Concluído com Sucesso", bg="#064E3B", fg="#34D399")
        elif tipo == "parcial":
            self.badge_status.config(text="● Concluído Parcialmente", bg="#78350F", fg="#F59E0B")
        elif tipo == "erro":
            self.badge_status.config(text="● Erro na Execução", bg="#7F1D1D", fg="#F87171")

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
        self.btn_baixar.config(state="disabled", bg=BORDER_COLOR, cursor="arrow")
        self.definir_status_badge("executando")
        
        # Limpa lista de boletos baixados da execução anterior
        self.boletos_baixados.clear()
        for item in self.tree_boletos.get_children():
            self.tree_boletos.delete(item)
        self.notebook.tab(self.tab_boletos_index, text="Boletos Baixados (0)")

        visivel = self.var_visivel.get()

        # Inicia em thread separada
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
                self.btn_baixar.config(state="normal", bg=ACCENT_GOLD, cursor="hand2")
            self.after(0, _reset_btn)

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

if __name__ == "__main__":
    app = AppBaixarBoletos()
    app.mainloop()
