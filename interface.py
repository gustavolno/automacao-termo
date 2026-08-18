import os
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = os.path.join(os.environ["LOCALAPPDATA"], "ms-playwright")
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import sys
import queue
import os
import logging
import ctypes

from gerador_boletos.logger import log
from gerador_boletos.main import iniciar_lote

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
ACCENT_EMERALD = "#10B981" # Legal Mint Green (À Vista & Success)
TEXT_BRIGHT = "#F8FAFC"    # Crisp White Primary Text
TEXT_MUTED = "#94A3B8"     # Soft Slate Text

FONT_BRAND = ("Georgia", 11, "bold")
FONT_UI = ("Segoe UI", 9)
FONT_UI_BOLD = ("Segoe UI", 9, "bold")
FONT_UI_TITLE = ("Segoe UI", 10, "bold")
FONT_MONO = ("Consolas", 10)

def aplicar_tema_titulo_escuro(window):
    """
    Aplica o tema escuro nativo na barra de título do Windows (Windows 10/11 DWM).
    """
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

class GUIQueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_queue.put(msg + "\n")
        except Exception:
            self.handleError(record)

class StdoutRedirector:
    def __init__(self, log_queue):
        self.log_queue = log_queue

    def write(self, message):
        if message.strip():
            self.log_queue.put(message + "\n")

    def flush(self):
        pass

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gerador de Boletos GEAP — Aldrigues Cândido Advocacia")
        self.configure(bg=BG_MAIN)
        self.geometry("900x650")
        self.minsize(800, 600)
        
        aplicar_tema_titulo_escuro(self)
        
        self.caminho_planilha = None
        self.log_queue = queue.Queue()
        
        self._build_ui()
        self.setup_logging()
        
        self.after(50, self._centralizar)
        self.after(100, self.verificar_logs)

    def _centralizar(self):
        self.update_idletasks()
        w, h = 900, 650
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        aplicar_tema_titulo_escuro(self)

    def _build_ui(self):
        # ── NAV BAR SUPERIOR EXECUTIVE ──
        navbar = tk.Frame(self, bg=BG_NAV, height=58, highlightthickness=1, highlightbackground=BORDER_COLOR)
        navbar.pack(fill="x")
        navbar.pack_propagate(False)

        brand_frame = tk.Frame(navbar, bg=BG_NAV)
        brand_frame.pack(side="left", padx=20)
        
        tk.Label(brand_frame, text="⚖", font=("Segoe UI", 14), bg=BG_NAV, fg=ACCENT_GOLD).pack(side="left", padx=(0, 6))
        tk.Label(brand_frame, text="ALDRIGUES CÂNDIDO", font=FONT_BRAND, bg=BG_NAV, fg=ACCENT_GOLD).pack(side="left")
        tk.Label(brand_frame, text=" ADVOCACIA", font=FONT_UI_BOLD, bg=BG_NAV, fg=TEXT_BRIGHT).pack(side="left")
        tk.Label(brand_frame, text="  |  GERADOR DE BOLETOS", font=FONT_UI, bg=BG_NAV, fg=TEXT_MUTED).pack(side="left")

        # ── CONTEÚDO PRINCIPAL ──
        content = tk.Frame(self, bg=BG_MAIN, padx=30, pady=20)
        content.pack(fill="both", expand=True)
        
        tk.Label(content, text="Automação de Boletos GEAP", font=("Segoe UI", 16, "bold"), bg=BG_MAIN, fg=TEXT_BRIGHT).pack(anchor="w")
        tk.Label(content, text="Selecione a planilha Excel para processamento em lote no Global Office.", font=FONT_UI, bg=BG_MAIN, fg=TEXT_MUTED).pack(anchor="w", pady=(0, 20))

        # ── CARD DE ARQUIVO ──
        card = tk.Frame(content, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR, padx=20, pady=20)
        card.pack(fill="x", pady=(0, 20))
        
        row1 = tk.Frame(card, bg=BG_CARD)
        row1.pack(fill="x")
        
        self.btn_select = tk.Button(row1, text="SELECIONAR PLANILHA", font=FONT_UI_BOLD, bg=BG_INPUT, fg=TEXT_BRIGHT, 
                                    activebackground=BORDER_COLOR, activeforeground=TEXT_BRIGHT,
                                    relief="flat", cursor="hand2", padx=15, pady=8, command=self.selecionar_arquivo)
        self.btn_select.pack(side="left")
        
        self.lbl_arquivo = tk.Label(row1, text="Nenhum arquivo selecionado...", font=FONT_UI, bg=BG_CARD, fg=TEXT_MUTED)
        self.lbl_arquivo.pack(side="left", padx=15)

        # ── BOTÃO INICIAR ──
        self.btn_start = tk.Button(content, text="▶ INICIAR PROCESSAMENTO EM LOTE", font=FONT_UI_TITLE, 
                                   bg=BORDER_COLOR, fg=TEXT_MUTED,  # Inicialmente desativado (cinza)
                                   relief="flat", pady=12, command=self.iniciar_automacao, state=tk.DISABLED)
        self.btn_start.pack(fill="x", pady=(0, 20))

        # ── TERMINAL DE LOGS ──
        log_container = tk.Frame(content, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR)
        log_container.pack(fill="both", expand=True)
        
        log_header = tk.Frame(log_container, bg=BG_NAV, height=30)
        log_header.pack(fill="x")
        log_header.pack_propagate(False)
        tk.Label(log_header, text="  TERMINAL DE EXECUÇÃO", font=FONT_UI_BOLD, bg=BG_NAV, fg=TEXT_MUTED).pack(side="left")
        
        self.text_log = tk.Text(log_container, bg=BG_INPUT, fg=ACCENT_EMERALD, font=FONT_MONO, 
                                relief="flat", padx=10, pady=10, wrap="word", insertbackground=TEXT_BRIGHT)
        self.text_log.pack(side="left", fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(log_container, command=self.text_log.yview)
        scrollbar.pack(side="right", fill="y")
        self.text_log.configure(yscrollcommand=scrollbar.set)
        
        self.text_log.config(state=tk.DISABLED)

    def setup_logging(self):
        handler = GUIQueueHandler(self.log_queue)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%d/%m/%Y %H:%M:%S')
        handler.setFormatter(formatter)
        log.addHandler(handler)
        
        redirector = StdoutRedirector(self.log_queue)
        sys.stdout = redirector
        sys.stderr = redirector

    def verificar_logs(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.text_log.config(state=tk.NORMAL)
            self.text_log.insert(tk.END, msg)
            self.text_log.see(tk.END)
            self.text_log.config(state=tk.DISABLED)
        self.after(100, self.verificar_logs)

    def selecionar_arquivo(self):
        filepath = filedialog.askopenfilename(
            title="Selecione a planilha de boletos",
            filetypes=(("Planilhas Excel", "*.xlsx"), ("Todos os arquivos", "*.*"))
        )
        if filepath:
            self.caminho_planilha = filepath
            self.lbl_arquivo.config(text=filepath, fg=TEXT_BRIGHT)
            
            # Ativa o botão e muda cor para GOLD
            self.btn_start.config(state=tk.NORMAL, bg=ACCENT_GOLD, fg=BG_MAIN, cursor="hand2", activebackground=ACCENT_GOLD_HOVER)

    def iniciar_automacao(self):
        if not self.caminho_planilha:
            return

        self.btn_start.config(state=tk.DISABLED, text="PROCESSANDO...", bg=BORDER_COLOR, fg=TEXT_MUTED, cursor="arrow")
        self.btn_select.config(state=tk.DISABLED, cursor="arrow")
        
        self.text_log.config(state=tk.NORMAL)
        self.text_log.delete(1.0, tk.END)
        self.text_log.config(state=tk.DISABLED)

        threading.Thread(target=self.run_worker, daemon=True).start()

    def run_worker(self):
        try:
            iniciar_lote(self.caminho_planilha)
        except Exception as e:
            self.log_queue.put(f"\\nERRO FATAL: {str(e)}\\n")
        finally:
            self.after(0, self.finalizar_automacao)

    def finalizar_automacao(self):
        self.btn_start.config(state=tk.NORMAL, text="▶ INICIAR PROCESSAMENTO EM LOTE", bg=ACCENT_GOLD, fg=BG_MAIN, cursor="hand2")
        self.btn_select.config(state=tk.NORMAL, cursor="hand2")
        messagebox.showinfo("Concluído", "O processo de automação foi finalizado. Verifique os logs para detalhes.")

if __name__ == "__main__":
    app = App()
    app.mainloop()
