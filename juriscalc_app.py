"""
juriscalc_app.py — Interface gráfica do Robô JurisCalc
Permite selecionar o PDF da GEAP e gerar o PDF de cálculo oficial do TJDFT.
"""

import os
import re
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from logo_b64 import LOGO_B64
import base64


# ============================================================
# DESIGN SYSTEM — ALDRIGUES CÂNDIDO ADVOCACIA (DARK EXECUTIVE)
# ============================================================
BG_MAIN   = "#0B0F17"
BG_NAV    = "#111827"
BG_CARD   = "#1E293B"
BG_INPUT  = "#0F172A"
BORDER    = "#334155"

GOLD      = "#C5A059"
GOLD_H    = "#E5C170"
EMERALD   = "#10B981"
CYAN      = "#38BDF8"
PINK      = "#F43F5E"
RED       = "#EF4444"

TEXT_BRIGHT = "#F8FAFC"
TEXT_MUTED  = "#94A3B8"
TEXT_DIM    = "#64748B"

FONT_BRAND    = ("Georgia", 12, "bold")
FONT_UI       = ("Segoe UI", 9)
FONT_UI_BOLD  = ("Segoe UI", 9, "bold")
FONT_TITLE    = ("Segoe UI", 10, "bold")
FONT_NUM      = ("Segoe UI", 11, "bold")
FONT_SMALL    = ("Segoe UI", 8)


def aplicar_tema_titulo_escuro(window):
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        if hwnd == 0:
            hwnd = window.winfo_id()
        val = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(val), ctypes.sizeof(val))
    except Exception:
        pass


class JurisCalcApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Aldrigues Cândido Advocacia — Robô JurisCalc")
        self.configure(bg=BG_MAIN)
        self.resizable(False, False)

        # Ícone
        try:
            img_data = base64.b64decode(LOGO_B64)
            img = tk.PhotoImage(data=img_data)
            self.iconphoto(True, img)
        except Exception:
            pass

        aplicar_tema_titulo_escuro(self)
        self._build_ui()
        self.update_idletasks()
        # Centralizar
        w, h = 640, 560
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _build_ui(self):
        # ── HEADER ──────────────────────────────────────────────
        header = tk.Frame(self, bg=BG_NAV, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)

        tk.Label(header, text="⚖️", font=("Segoe UI", 18), bg=BG_NAV, fg=GOLD).pack(side="left", padx=(16, 6), pady=8)
        lf = tk.Frame(header, bg=BG_NAV)
        lf.pack(side="left", pady=8)
        tk.Label(lf, text="ALDRIGUES CÂNDIDO", font=FONT_BRAND, bg=BG_NAV, fg=TEXT_BRIGHT).pack(anchor="w")
        tk.Label(lf, text="ADVOCACIA  |  ROBÔ JURISCALC", font=FONT_SMALL, bg=BG_NAV, fg=TEXT_MUTED).pack(anchor="w")

        tk.Label(header, text="🤖  JurisCalc Automático", font=FONT_TITLE, bg=BG_NAV, fg=CYAN).pack(side="right", padx=16)

        # ── CORPO ───────────────────────────────────────────────
        body = tk.Frame(self, bg=BG_MAIN, padx=20, pady=16)
        body.pack(fill="both", expand=True)

        # Card: PDF de entrada
        self._card_entrada(body)

        # Card: Configurações
        self._card_config(body)

        # Card: Progresso
        self._card_progresso(body)

        # Botão principal
        self.btn_gerar = tk.Button(
            body, text="🚀  GERAR PDF DE CÁLCULO JURISCALC",
            font=("Segoe UI", 11, "bold"), bg=GOLD, fg=BG_MAIN,
            activebackground=GOLD_H, activeforeground=BG_MAIN,
            relief="flat", cursor="hand2", pady=12, bd=0,
            command=self._iniciar_automacao,
        )
        self.btn_gerar.pack(fill="x", pady=(12, 4))
        self.btn_gerar.bind("<Enter>", lambda e: self.btn_gerar.config(bg=GOLD_H))
        self.btn_gerar.bind("<Leave>", lambda e: self.btn_gerar.config(bg=GOLD))

        # Rodapé
        tk.Label(body, text="O cálculo é feito diretamente no site oficial do TJDFT — JurisCalc",
                 font=FONT_SMALL, bg=BG_MAIN, fg=TEXT_DIM).pack(pady=(4, 0))

    def _card_entrada(self, parent):
        card = tk.Frame(parent, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", pady=(0, 10))

        bar = tk.Frame(card, bg=BG_NAV, height=36)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="📂  PDF DA FICHA FINANCEIRA (GEAP / IPASEP)", font=FONT_TITLE,
                 bg=BG_NAV, fg=GOLD).pack(side="left", padx=12)

        body = tk.Frame(card, bg=BG_CARD, padx=16, pady=12)
        body.pack(fill="x")

        file_row = tk.Frame(body, bg=BG_CARD)
        file_row.pack(fill="x")

        self.entry_pdf = tk.Entry(
            file_row, font=FONT_UI, bg=BG_INPUT, fg=TEXT_BRIGHT,
            insertbackground=TEXT_BRIGHT, relief="flat", bd=0,
            readonlybackground=BG_INPUT, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=CYAN,
        )
        self.entry_pdf.pack(side="left", fill="x", expand=True, ipady=6)

        btn_browse = tk.Button(
            file_row, text="  Procurar…  ",
            font=FONT_UI_BOLD, bg=BG_NAV, fg=CYAN,
            relief="flat", cursor="hand2", bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            command=self._browse_pdf,
        )
        btn_browse.pack(side="left", padx=(8, 0), ipady=6, ipadx=4)

        self.lbl_parcelas = tk.Label(
            body, text="Nenhum arquivo selecionado",
            font=FONT_SMALL, bg=BG_CARD, fg=TEXT_DIM,
        )
        self.lbl_parcelas.pack(anchor="w", pady=(6, 0))

    def _card_config(self, parent):
        card = tk.Frame(parent, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", pady=(0, 10))

        bar = tk.Frame(card, bg=BG_NAV, height=36)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="⚙️  CONFIGURAÇÕES DE CÁLCULO", font=FONT_TITLE,
                 bg=BG_NAV, fg=GOLD).pack(side="left", padx=12)

        body = tk.Frame(card, bg=BG_CARD, padx=16, pady=12)
        body.pack(fill="x")

        row = tk.Frame(body, bg=BG_CARD)
        row.pack(fill="x")

        # Multa
        m_frame = tk.Frame(row, bg=BG_CARD)
        m_frame.pack(side="left", expand=True, fill="x", padx=(0, 10))
        tk.Label(m_frame, text="🔴 Multa (%)", font=FONT_UI, bg=BG_CARD, fg=TEXT_MUTED).pack(anchor="w")
        self.entry_multa = tk.Entry(
            m_frame, font=FONT_NUM, bg=BG_INPUT, fg=RED,
            insertbackground=TEXT_BRIGHT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=CYAN, justify="center", width=10,
        )
        self.entry_multa.insert(0, "2,00")
        self.entry_multa.pack(fill="x", ipady=6)

        # Honorários
        h_frame = tk.Frame(row, bg=BG_CARD)
        h_frame.pack(side="left", expand=True, fill="x")
        tk.Label(h_frame, text="💼 Honorários (%)", font=FONT_UI, bg=BG_CARD, fg=TEXT_MUTED).pack(anchor="w")
        self.entry_hon = tk.Entry(
            h_frame, font=FONT_NUM, bg=BG_INPUT, fg=CYAN,
            insertbackground=TEXT_BRIGHT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER,
            highlightcolor=CYAN, justify="center", width=10,
        )
        self.entry_hon.insert(0, "10,00")
        self.entry_hon.pack(fill="x", ipady=6)

    def _card_progresso(self, parent):
        card = tk.Frame(parent, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER)
        card.pack(fill="x", pady=(0, 10))

        bar = tk.Frame(card, bg=BG_NAV, height=36)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="📊  PROGRESSO DA AUTOMAÇÃO", font=FONT_TITLE,
                 bg=BG_NAV, fg=GOLD).pack(side="left", padx=12)

        body = tk.Frame(card, bg=BG_CARD, padx=16, pady=12)
        body.pack(fill="x")

        self.lbl_status = tk.Label(
            body, text="Aguardando arquivo PDF...",
            font=FONT_UI, bg=BG_CARD, fg=TEXT_MUTED, anchor="w",
        )
        self.lbl_status.pack(fill="x")

        # Barra de progresso manual com Canvas
        self.canvas_prog = tk.Canvas(body, bg=BORDER, height=8, highlightthickness=0)
        self.canvas_prog.pack(fill="x", pady=(8, 4))
        self.barra = self.canvas_prog.create_rectangle(0, 0, 0, 8, fill=GOLD, outline="")
        self._canvas_width = 0
        self.canvas_prog.bind("<Configure>", self._on_canvas_resize)

    def _on_canvas_resize(self, event):
        self._canvas_width = event.width

    def _browse_pdf(self):
        path = filedialog.askopenfilename(
            title="Selecionar Ficha Financeira (PDF)",
            filetypes=[("PDF", "*.pdf"), ("Todos os arquivos", "*.*")],
        )
        if not path:
            return
        self.entry_pdf.delete(0, tk.END)
        self.entry_pdf.insert(0, path)
        
        # Pré-visualizar parcelas
        self.lbl_parcelas.config(text="Analisando PDF...", fg=TEXT_MUTED)
        self.update()
        
        def contar():
            try:
                from parser_geap import extrair_parcelas
                ps = extrair_parcelas(path)
                msg = f"✅ {len(ps)} parcela(s) encontrada(s) no PDF"
                color = EMERALD
            except Exception as e:
                msg = f"⚠️  Não foi possível ler parcelas: {e}"
                color = PINK
            self.after(0, lambda: self.lbl_parcelas.config(text=msg, fg=color))
        
        threading.Thread(target=contar, daemon=True).start()

    def _set_progresso(self, msg: str, pct: int):
        """Atualiza status e barra de progresso (thread-safe via after)."""
        def _update():
            self.lbl_status.config(text=msg)
            if self._canvas_width > 0:
                w = int(self._canvas_width * pct / 100)
                self.canvas_prog.coords(self.barra, 0, 0, w, 8)
                cor = EMERALD if pct == 100 else GOLD
                self.canvas_prog.itemconfig(self.barra, fill=cor)
        self.after(0, _update)

    def _iniciar_automacao(self):
        caminho_pdf = self.entry_pdf.get().strip()
        if not caminho_pdf or not os.path.exists(caminho_pdf):
            messagebox.showerror("Erro", "Selecione um arquivo PDF válido antes de continuar.")
            return

        # Ler percentuais
        try:
            multa = float(self.entry_multa.get().replace(",", "."))
            hon   = float(self.entry_hon.get().replace(",", "."))
        except ValueError:
            messagebox.showerror("Erro", "Multa e Honorários devem ser números (ex: 2,00).")
            return

        # Caminho de saída — mesma pasta do PDF de entrada
        pasta = os.path.dirname(caminho_pdf)
        nome_base = os.path.splitext(os.path.basename(caminho_pdf))[0]
        from datetime import datetime
        saida = os.path.join(pasta, f"JURISCALC_{nome_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

        self.btn_gerar.config(state="disabled", text="⏳  Processando...")
        self._set_progresso("Iniciando automação...", 0)

        def run():
            try:
                from automacao_juriscalc import rodar_automacao
                rodar_automacao(
                    caminho_pdf=caminho_pdf,
                    caminho_saida=saida,
                    multa_pct=multa,
                    honorarios_pct=hon,
                    visivel=False,
                    callback_progresso=self._set_progresso,
                )
                self.after(0, lambda: self._finalizado(saida, sucesso=True))
            except Exception as e:
                self.after(0, lambda: self._finalizado(str(e), sucesso=False))

        threading.Thread(target=run, daemon=True).start()

    def _finalizado(self, resultado: str, sucesso: bool):
        self.btn_gerar.config(state="normal", text="🚀  GERAR PDF DE CÁLCULO JURISCALC")
        if sucesso:
            self._set_progresso(f"✅ PDF gerado com sucesso!", 100)
            if messagebox.askyesno("Sucesso!", f"PDF gerado com sucesso!\n\nDeseja abrir o arquivo agora?\n{resultado}"):
                os.startfile(os.path.abspath(resultado))
        else:
            self._set_progresso(f"❌ Erro: {resultado}", 0)
            messagebox.showerror("Erro na automação", f"Ocorreu um erro durante o processo:\n\n{resultado}")


if __name__ == "__main__":
    app = JurisCalcApp()
    app.mainloop()
