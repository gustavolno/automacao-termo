import re
import ctypes
import tkinter as tk
from tkinter import ttk, messagebox
from decimal import Decimal, ROUND_HALF_UP

from parser_acordo import formatar_valor_brl, parse_valor_brl

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
ACCENT_CYAN = "#38BDF8"    # Executive Sky Blue
ACCENT_PINK = "#F43F5E"    # Elegant Rose

TEXT_BRIGHT = "#F8FAFC"    # Crisp White Primary Text
TEXT_MUTED = "#94A3B8"     # Soft Slate Text
TEXT_DIM = "#64748B"       # Subtle Placeholder Text

FONT_BRAND = ("Georgia", 11, "bold")
FONT_UI = ("Segoe UI", 9)
FONT_UI_BOLD = ("Segoe UI", 9, "bold")
FONT_UI_TITLE = ("Segoe UI", 10, "bold")
FONT_MONO = ("Consolas", 10)
FONT_MONO_BOLD = ("Consolas", 10, "bold")


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


class CalculadoraVendas(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Aldrigues Cândido Advocacia — Calculadora de Vendas & Negociação")
        self.configure(bg=BG_MAIN)
        self.resizable(True, True)
        self.minsize(920, 680)
        
        # Aplica barra de título escura nativa no Windows
        aplicar_tema_titulo_escuro(self)
        
        self.calc_entries = {}
        self._calc_state = {"updating": False}
        self._build_ui()
        self.after(50, self._centralizar)

    def _centralizar(self):
        self.update_idletasks()
        w, h = 980, 720
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        aplicar_tema_titulo_escuro(self)

    def _build_ui(self):
        # ── NAV BAR SUPERIOR ──
        navbar = tk.Frame(self, bg=BG_NAV, height=58, highlightthickness=1, highlightbackground=BORDER_COLOR)
        navbar.pack(fill="x")
        navbar.pack_propagate(False)

        brand_frame = tk.Frame(navbar, bg=BG_NAV)
        brand_frame.pack(side="left", padx=20)
        
        tk.Label(brand_frame, text="⚖", font=("Segoe UI", 14), bg=BG_NAV, fg=ACCENT_GOLD).pack(side="left", padx=(0, 6))
        tk.Label(brand_frame, text="ALDRIGUES CÂNDIDO", font=FONT_BRAND, bg=BG_NAV, fg=ACCENT_GOLD).pack(side="left")
        tk.Label(brand_frame, text=" ADVOCACIA", font=FONT_UI_BOLD, bg=BG_NAV, fg=TEXT_BRIGHT).pack(side="left")
        tk.Label(brand_frame, text="  |  CALCULADORA DE VENDAS", font=FONT_UI, bg=BG_NAV, fg=TEXT_MUTED).pack(side="left")

        # Container Principal
        content = tk.Frame(self, bg=BG_MAIN)
        content.pack(fill="both", expand=True, padx=20, pady=18)

        grid = tk.Frame(content, bg=BG_MAIN)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(0, weight=1)

        # ── Coluna Esquerda: Parâmetros da Causa & Entrada ──
        card_inputs = tk.Frame(grid, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR)
        card_inputs.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        card_inputs.rowconfigure(1, weight=1)
        card_inputs.columnconfigure(0, weight=1)

        i_bar = tk.Frame(card_inputs, bg=BG_NAV, height=38, highlightthickness=1, highlightbackground=BORDER_COLOR)
        i_bar.grid(row=0, column=0, sticky="ew")
        i_bar.pack_propagate(False)
        tk.Label(i_bar, text="📝  PARÂMETROS DA NEGOCIAÇÃO", font=FONT_UI_TITLE, bg=BG_NAV, fg=ACCENT_GOLD).pack(side="left", padx=14)

        i_body = tk.Frame(card_inputs, bg=BG_CARD, padx=18, pady=16)
        i_body.grid(row=1, column=0, sticky="nsew")

        campos = [
            ("vo", "Valor Original da Causa (R$)", TEXT_BRIGHT, "vc"),
            ("pct_desc", "% Desconto Aplicado", ACCENT_GOLD, "pct_desc"),
            ("va", "Valor do Acordo em Reais (R$)", ACCENT_EMERALD, "va_reais"),
            ("pct_ent", "% Valor da Entrada", ACCENT_CYAN, "pct_ent"),
            ("ve", "Valor da Entrada em Reais (R$)", ACCENT_EMERALD, "ve_reais"),
            ("qp", "Quantidade de Parcelas (Nº)", TEXT_BRIGHT, "qp"),
            ("vp_input", "Valor da Parcela Mensal (R$)", ACCENT_CYAN, "vp_input"),
        ]

        for i, (chave, label, cor, evento) in enumerate(campos):
            rf = tk.Frame(i_body, bg=BG_CARD)
            rf.pack(fill="x", pady=2)
            tk.Label(rf, text=label + ":", font=FONT_UI_BOLD, bg=BG_CARD, fg=cor).pack(anchor="w")
            
            ent = tk.Entry(rf, font=FONT_MONO_BOLD, bg=BG_INPUT, fg=TEXT_BRIGHT,
                           insertbackground=ACCENT_GOLD, relief="flat", bd=0,
                           highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT_GOLD)
            ent.pack(fill="x", ipady=4, pady=(2, 6))
            ent.bind("<KeyRelease>", lambda e, ev=evento: self._recalcular(ev))
            self.calc_entries[chave] = ent

        # ── Coluna Direita: Resumo do Acordo & Repasses ──
        card_outs = tk.Frame(grid, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR)
        card_outs.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        card_outs.rowconfigure(1, weight=1)
        card_outs.columnconfigure(0, weight=1)

        o_bar = tk.Frame(card_outs, bg=BG_NAV, height=38, highlightthickness=1, highlightbackground=BORDER_COLOR)
        o_bar.grid(row=0, column=0, sticky="ew")
        o_bar.pack_propagate(False)
        tk.Label(o_bar, text="📊  DEMONSTRATIVO DOS VALORES", font=FONT_UI_TITLE, bg=BG_NAV, fg=ACCENT_EMERALD).pack(side="left", padx=14)

        o_body = tk.Frame(card_outs, bg=BG_CARD, padx=18, pady=16)
        o_body.grid(row=1, column=0, sticky="nsew")

        self.lbl_resultados = {}
        resultados = [
            ("v_desconto", "Valor do Desconto Concedido", ACCENT_GOLD),
            ("quitação", "Valor Total da Quitação (À Vista)", ACCENT_CYAN),
            ("saldo", "Saldo Restante Pós-Entrada", ACCENT_PINK),
            ("vp", "Valor da Parcela Mensal (Parcelado)", ACCENT_EMERALD),
            ("hon", "Honorários Advocatícios (10%)", ACCENT_GOLD),
            ("geap", "Valor Líquido do Repasse (GEAP)", ACCENT_EMERALD),
        ]

        for i, (chave, titulo, cor) in enumerate(resultados):
            tk.Label(o_body, text=titulo + ":", font=FONT_UI, bg=BG_CARD, fg=TEXT_MUTED, anchor="w").pack(fill="x", pady=(8 if i > 0 else 0, 2))
            
            ent_out = tk.Entry(o_body, font=FONT_MONO_BOLD, bg=BG_CARD, fg=cor,
                               readonlybackground=BG_CARD, relief="flat", bd=0,
                               justify="left", highlightthickness=0,
                               selectbackground=BORDER_COLOR, selectforeground=TEXT_BRIGHT)
            ent_out.insert(0, "R$ 0,00")
            ent_out.config(state="readonly")
            ent_out.pack(fill="x", pady=(0, 4))
            self.lbl_resultados[chave] = ent_out

            if i < len(resultados) - 1:
                tk.Frame(o_body, bg=BORDER_COLOR, height=1).pack(fill="x", pady=4)

        # ── Rodapé de Ações ──
        footer = tk.Frame(content, bg=BG_MAIN, pady=12)
        footer.pack(fill="x")

        btn_reset = tk.Button(
            footer, text="🔄  LIMPAR TODOS OS CAMPOS",
            font=FONT_UI_BOLD, bg=BG_CARD, fg=TEXT_MUTED,
            activebackground=BORDER_COLOR, activeforeground=TEXT_BRIGHT,
            relief="flat", cursor="hand2", pady=10, bd=0,
            command=self._reset_calc
        )
        btn_reset.pack(fill="x")
        btn_reset.bind("<Enter>", lambda e: btn_reset.config(bg=BORDER_COLOR, fg=TEXT_BRIGHT))
        btn_reset.bind("<Leave>", lambda e: btn_reset.config(bg=BG_CARD, fg=TEXT_MUTED))

    def _parse_num(self, txt):
        if not txt: return None
        t = txt.strip().replace("R$", "").replace("%", "").replace(" ", "")
        if not t: return None
        if "," in t and "." in t: t = t.replace(".", "").replace(",", ".")
        elif "," in t: t = t.replace(",", ".")
        try: return Decimal(t)
        except Exception: return None

    def _set_out(self, key, text_val):
        ent = self.lbl_resultados[key]
        ent.config(state="normal")
        ent.delete(0, "end")
        ent.insert(0, text_val)
        ent.config(state="readonly")

    def _recalcular(self, origem="vc"):
        if self._calc_state["updating"]:
            return
        self._calc_state["updating"] = True

        try:
            vc = self._parse_num(self.calc_entries["vo"].get())
            if vc is None or vc <= 0:
                for k in self.lbl_resultados:
                    self._set_out(k, "R$ 0,00")
                return

            # 1. Ajuste do Valor do Acordo & % Desconto (Bidirecional)
            if origem == "va_reais":
                va = self._parse_num(self.calc_entries["va"].get())
                if va is not None and va >= 0 and vc > 0:
                    pct_d = ((vc - va) / vc * Decimal("100")).quantize(Decimal("0.01"))
                    self.calc_entries["pct_desc"].delete(0, "end")
                    self.calc_entries["pct_desc"].insert(0, f"{pct_d}")
                else:
                    va = vc
            elif origem == "pct_desc":
                pct_d = self._parse_num(self.calc_entries["pct_desc"].get()) or Decimal("0")
                va = (vc * (Decimal("100") - pct_d) / Decimal("100")).quantize(Decimal("0.01"))
                self.calc_entries["va"].delete(0, "end")
                self.calc_entries["va"].insert(0, formatar_valor_brl(va))
            else:
                va = self._parse_num(self.calc_entries["va"].get())
                if va is None:
                    pct_d = self._parse_num(self.calc_entries["pct_desc"].get()) or Decimal("0")
                    va = (vc * (Decimal("100") - pct_d) / Decimal("100")).quantize(Decimal("0.01"))
                    self.calc_entries["va"].delete(0, "end")
                    self.calc_entries["va"].insert(0, formatar_valor_brl(va))

            # 2. Ajuste do Valor da Entrada & % Entrada (Bidirecional)
            if origem == "ve_reais":
                ve = self._parse_num(self.calc_entries["ve"].get())
                if ve is not None and va > 0:
                    pct_e = (ve / va * Decimal("100")).quantize(Decimal("0.01"))
                    self.calc_entries["pct_ent"].delete(0, "end")
                    self.calc_entries["pct_ent"].insert(0, f"{pct_e}")
                else:
                    ve = Decimal("0")
            elif origem == "pct_ent":
                pct_e = self._parse_num(self.calc_entries["pct_ent"].get()) or Decimal("0")
                ve = (va * pct_e / Decimal("100")).quantize(Decimal("0.01"))
                self.calc_entries["ve"].delete(0, "end")
                self.calc_entries["ve"].insert(0, formatar_valor_brl(ve))
            else:
                ve = self._parse_num(self.calc_entries["ve"].get())
                if ve is None:
                    pct_e = self._parse_num(self.calc_entries["pct_ent"].get()) or Decimal("0")
                    ve = (va * pct_e / Decimal("100")).quantize(Decimal("0.01"))
                    self.calc_entries["ve"].delete(0, "end")
                    self.calc_entries["ve"].insert(0, formatar_valor_brl(ve))

            # 3. Saldo Restante Pós Entrada & Desconto Concedido
            saldo = max(Decimal("0"), va - ve)
            v_desconto = max(Decimal("0"), vc - va)

            # 4. Parcelamento (Qtd vs Valor da Parcela - Bidirecional)
            if origem == "vp_input":
                vp_val = self._parse_num(self.calc_entries["vp_input"].get())
                if vp_val and vp_val > 0 and saldo > 0:
                    qp_calc = int((saldo / vp_val).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                    self.calc_entries["qp"].delete(0, "end")
                    self.calc_entries["qp"].insert(0, str(qp_calc))
                    vp = vp_val
                else:
                    vp = Decimal("0")
            else:
                qp_num = self._parse_num(self.calc_entries["qp"].get())
                try:
                    qp_int = int(qp_num) if qp_num else 0
                except Exception:
                    qp_int = 0

                if qp_int > 0 and saldo > 0:
                    vp = (saldo / Decimal(qp_int)).quantize(Decimal("0.01"))
                    if origem != "vp_input":
                        self.calc_entries["vp_input"].delete(0, "end")
                        self.calc_entries["vp_input"].insert(0, formatar_valor_brl(vp))
                else:
                    vp = Decimal("0")
                    if origem != "vp_input":
                        self.calc_entries["vp_input"].delete(0, "end")
                        self.calc_entries["vp_input"].insert(0, "0,00")

            # 5. Honorários (10%) e Repasse GEAP
            hon = (va * Decimal("0.10")).quantize(Decimal("0.01")) if va > 0 else Decimal("0")
            geap = va - hon if va > 0 else Decimal("0")

            # Atualiza Outputs
            self._set_out("v_desconto", f"R$ {formatar_valor_brl(v_desconto)}")
            self._set_out("quitação", f"R$ {formatar_valor_brl(va)}")
            self._set_out("saldo", f"R$ {formatar_valor_brl(saldo)}")
            self._set_out("vp", f"R$ {formatar_valor_brl(vp)}")
            self._set_out("hon", f"R$ {formatar_valor_brl(hon)}")
            self._set_out("geap", f"R$ {formatar_valor_brl(geap)}")

        finally:
            self._calc_state["updating"] = False

    def _reset_calc(self):
        for k in self.calc_entries:
            self.calc_entries[k].delete(0, tk.END)
        self._recalcular()


if __name__ == "__main__":
    app = CalculadoraVendas()
    app.mainloop()
