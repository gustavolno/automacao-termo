import re
import ctypes
import tkinter as tk
from tkinter import ttk, messagebox
from decimal import Decimal, ROUND_HALF_UP
from logo_b64 import LOGO_B64

# ============================================================
# DESIGN SYSTEM — ALDRIGUES CÂNDIDO ADVOCACIA (EXECUTIVE LAW FIRM)
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
ACCENT_RED = "#EF4444"     # Alert Red
ACCENT_PURPLE = "#A855F7"  # Vibrant Purple
ACCENT_ORANGE = "#F97316"  # Orange

TEXT_BRIGHT = "#F8FAFC"    # Crisp White Primary Text
TEXT_MUTED = "#94A3B8"     # Soft Slate Text
TEXT_DIM = "#64748B"       # Subtle Placeholder Text

FONT_BRAND = ("Georgia", 12, "bold")
FONT_UI = ("Segoe UI", 9)
FONT_UI_BOLD = ("Segoe UI", 9, "bold")
FONT_UI_TITLE = ("Segoe UI", 10, "bold")
FONT_NUM = ("Segoe UI", 11, "bold")
FONT_NUM_LARGE = ("Segoe UI", 15, "bold")


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


def formatar_brl(val):
    if val is None:
        return "0,00"
    try:
        v = Decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return f"{v:,.2f}".replace(".", "_").replace(",", ".").replace("_", ",")
    except Exception:
        return "0,00"


class CalculadoraVendas(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Aldrigues Cândido Advocacia — Simulação & Calculadora de Acordo")
        self.configure(bg=BG_MAIN)
        self.resizable(True, True)
        self.minsize(920, 640)
        
        # Aplica a barra de título escura nativa no Windows
        aplicar_tema_titulo_escuro(self)
        
        try:
            img = tk.PhotoImage(data=LOGO_B64)
            self.iconphoto(False, img)
        except Exception:
            pass
        
        self.calc_entries = {}
        self._calc_state = {"updating": False}
        self._build_ui()
        self.after(50, self._centralizar)

    def _centralizar(self):
        self.update_idletasks()
        w, h = 960, 680
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")
        aplicar_tema_titulo_escuro(self)

    def _build_ui(self):
        # ── CABEÇALHO DA MARCA ──
        navbar = tk.Frame(self, bg=BG_NAV, height=60, highlightthickness=1, highlightbackground=BORDER_COLOR)
        navbar.pack(fill="x")
        navbar.pack_propagate(False)

        brand_frame = tk.Frame(navbar, bg=BG_NAV)
        brand_frame.pack(side="left", padx=22)
        
        tk.Label(brand_frame, text="⚖", font=("Segoe UI", 15), bg=BG_NAV, fg=ACCENT_GOLD).pack(side="left", padx=(0, 8))
        tk.Label(brand_frame, text="ALDRIGUES CÂNDIDO", font=FONT_BRAND, bg=BG_NAV, fg=ACCENT_GOLD).pack(side="left")
        tk.Label(brand_frame, text=" ADVOCACIA", font=FONT_UI_BOLD, bg=BG_NAV, fg=TEXT_BRIGHT).pack(side="left")
        tk.Label(brand_frame, text="  |  PLANILHA DE CÁLCULO & NEGOCIAÇÃO", font=FONT_UI, bg=BG_NAV, fg=TEXT_MUTED).pack(side="left")

        # Container Principal
        content = tk.Frame(self, bg=BG_MAIN)
        content.pack(fill="both", expand=True, padx=20, pady=18)

        grid = tk.Frame(content, bg=BG_MAIN)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(0, weight=1)

        # ── PAINEL ESQUERDO: PARÂMETROS DA CÁLCULO (INPUTS) ──
        card_inputs = tk.Frame(grid, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR)
        card_inputs.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        i_bar = tk.Frame(card_inputs, bg=BG_NAV, height=40, highlightthickness=1, highlightbackground=BORDER_COLOR)
        i_bar.pack(fill="x")
        i_bar.pack_propagate(False)
        tk.Label(i_bar, text="📋  DADOS DO ACORDO (EDITÁVEIS)", font=FONT_UI_TITLE, bg=BG_NAV, fg=ACCENT_GOLD).pack(side="left", padx=16)

        i_body = tk.Frame(card_inputs, bg=BG_CARD, padx=18, pady=18)
        i_body.pack(fill="both", expand=True)

        # 1. Valor da causa (Valor Original)
        tk.Label(i_body, text="Valor da causa (R$):", font=FONT_UI_BOLD, bg=BG_CARD, fg=TEXT_BRIGHT).pack(anchor="w", pady=(0, 3))
        ent_vc = tk.Entry(i_body, font=FONT_NUM, bg=BG_INPUT, fg=TEXT_BRIGHT, insertbackground=ACCENT_GOLD, relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT_GOLD)
        ent_vc.pack(fill="x", ipady=6, pady=(0, 14))
        ent_vc.bind("<KeyRelease>", lambda e: self._aplicar_mascara_moeda(e, ent_vc, "vc"))
        self.calc_entries["vo"] = ent_vc

        # 2. Valor negociado (R$) + Desconto (%) LADO A LADO
        lbl_f1 = tk.Frame(i_body, bg=BG_CARD)
        lbl_f1.pack(fill="x", pady=(0, 3))
        tk.Label(lbl_f1, text="Valor negociado (R$):", font=FONT_UI_BOLD, bg=BG_CARD, fg=ACCENT_EMERALD).pack(side="left")
        tk.Label(lbl_f1, text="Desconto (%):", font=FONT_UI_BOLD, bg=BG_CARD, fg=ACCENT_GOLD).pack(side="right")

        row1 = tk.Frame(i_body, bg=BG_CARD)
        row1.pack(fill="x", pady=(0, 14))

        ent_va = tk.Entry(row1, font=FONT_NUM, bg=BG_INPUT, fg=ACCENT_EMERALD, insertbackground=ACCENT_GOLD, relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT_EMERALD)
        ent_va.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        ent_va.bind("<KeyRelease>", lambda e: self._aplicar_mascara_moeda(e, ent_va, "va_reais"))
        self.calc_entries["va"] = ent_va

        ent_desc = tk.Entry(row1, font=FONT_NUM, bg=BG_INPUT, fg=ACCENT_GOLD, justify="center", width=8, insertbackground=ACCENT_GOLD, relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT_GOLD)
        ent_desc.pack(side="right", ipady=6)
        ent_desc.bind("<KeyRelease>", lambda e: self._recalcular("pct_desc"))
        self.calc_entries["pct_desc"] = ent_desc

        # 3. Valor da entrada (R$) + Entrada (%) LADO A LADO COM QUADRADO PEQUENO
        lbl_f2 = tk.Frame(i_body, bg=BG_CARD)
        lbl_f2.pack(fill="x", pady=(0, 3))
        tk.Label(lbl_f2, text="Valor da entrada (R$):", font=FONT_UI_BOLD, bg=BG_CARD, fg=ACCENT_EMERALD).pack(side="left")
        tk.Label(lbl_f2, text="Entrada (%):", font=FONT_UI_BOLD, bg=BG_CARD, fg=ACCENT_CYAN).pack(side="right")

        row2 = tk.Frame(i_body, bg=BG_CARD)
        row2.pack(fill="x", pady=(0, 14))

        ent_ve = tk.Entry(row2, font=FONT_NUM, bg=BG_INPUT, fg=ACCENT_EMERALD, insertbackground=ACCENT_GOLD, relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT_EMERALD)
        ent_ve.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        ent_ve.bind("<KeyRelease>", lambda e: self._aplicar_mascara_moeda(e, ent_ve, "ve_reais"))
        self.calc_entries["ve"] = ent_ve

        ent_pct_ent = tk.Entry(row2, font=FONT_NUM, bg=BG_INPUT, fg=ACCENT_CYAN, justify="center", width=8, insertbackground=ACCENT_GOLD, relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT_CYAN)
        ent_pct_ent.pack(side="right", ipady=6)
        ent_pct_ent.bind("<KeyRelease>", lambda e: self._recalcular("pct_ent"))
        self.calc_entries["pct_ent"] = ent_pct_ent

        # 4. Quantidade de parcelas + Valor da parcela LADO A LADO
        lbl_f3 = tk.Frame(i_body, bg=BG_CARD)
        lbl_f3.pack(fill="x", pady=(0, 3))
        tk.Label(lbl_f3, text="Qtd. Parcelas:", font=FONT_UI_BOLD, bg=BG_CARD, fg=TEXT_BRIGHT).pack(side="left")
        tk.Label(lbl_f3, text="Valor da parcela (R$):", font=FONT_UI_BOLD, bg=BG_CARD, fg=ACCENT_CYAN).pack(side="right")

        row3 = tk.Frame(i_body, bg=BG_CARD)
        row3.pack(fill="x", pady=(0, 10))

        ent_qp = tk.Entry(row3, font=FONT_NUM, bg=BG_INPUT, fg=TEXT_BRIGHT, justify="center", width=8, insertbackground=ACCENT_GOLD, relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT_GOLD)
        ent_qp.pack(side="left", ipady=6, padx=(0, 8))
        ent_qp.bind("<KeyRelease>", lambda e: self._recalcular("qp"))
        self.calc_entries["qp"] = ent_qp

        ent_vp = tk.Entry(row3, font=FONT_NUM, bg=BG_INPUT, fg=ACCENT_CYAN, insertbackground=ACCENT_GOLD, relief="flat", bd=0, highlightthickness=1, highlightbackground=BORDER_COLOR, highlightcolor=ACCENT_CYAN)
        ent_vp.pack(side="right", fill="x", expand=True, ipady=6)
        ent_vp.bind("<KeyRelease>", lambda e: self._aplicar_mascara_moeda(e, ent_vp, "vp_input"))
        self.calc_entries["vp_input"] = ent_vp

        # ── PAINEL DIREITO: DEMONSTRATIVO DE VALORES (PLANILHA) ──
        card_outs = tk.Frame(grid, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR)
        card_outs.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        o_bar = tk.Frame(card_outs, bg=BG_NAV, height=40, highlightthickness=1, highlightbackground=BORDER_COLOR)
        o_bar.pack(fill="x")
        o_bar.pack_propagate(False)
        tk.Label(o_bar, text="📊  DEMONSTRATIVO DE VALORES", font=FONT_UI_TITLE, bg=BG_NAV, fg=ACCENT_EMERALD).pack(side="left", padx=16)

        o_body = tk.Frame(card_outs, bg=BG_CARD, padx=20, pady=18)
        o_body.pack(fill="both", expand=True)

        self.lbl_resultados = {}
        # Nomes exatos conforme demonstrativo e planilha de cálculo do escritório:
        resultados = [
            ("v_desconto", "Valor do desconto", ACCENT_GOLD),
            ("saldo_desc", "Total atualizado / Subtotal", ACCENT_CYAN),
            ("ve_res", "Valor da entrada", ACCENT_EMERALD),
            ("saldo", "Saldo restante", ACCENT_PINK),
            ("vp", "Valor da parcela", ACCENT_PURPLE),
            ("hon", "🔴 Honorários 10%", ACCENT_RED),
            ("geap", "Valor GEAP", ACCENT_ORANGE),
        ]

        for i, (chave, titulo, cor) in enumerate(resultados):
            rf = tk.Frame(o_body, bg=BG_CARD)
            rf.pack(fill="x", pady=4)

            tk.Label(rf, text=titulo + ":", font=FONT_UI, bg=BG_CARD, fg=TEXT_MUTED).pack(side="left")

            ent_out = tk.Entry(rf, font=FONT_NUM, bg=BG_CARD, fg=cor,
                               readonlybackground=BG_CARD, relief="flat", bd=0,
                               justify="right", width=18, highlightthickness=0,
                               selectbackground=BORDER_COLOR, selectforeground=TEXT_BRIGHT)
            ent_out.insert(0, "R$ 0,00")
            ent_out.config(state="readonly")
            ent_out.pack(side="right")
            self.lbl_resultados[chave] = ent_out

            if i < len(resultados) - 1:
                tk.Frame(o_body, bg=BORDER_COLOR, height=1).pack(fill="x", pady=3)

        # Rodapé com botão de reset limpo
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

    def _aplicar_mascara_moeda(self, event, widget, origem):
        if event.keysym in ('Left', 'Right', 'Up', 'Down', 'Tab'):
            return
        
        texto = widget.get()
        if not texto:
            self._recalcular(origem)
            return

        # Pega apenas números
        numeros = re.sub(r'\D', '', texto)
        
        if not numeros:
            widget.delete(0, tk.END)
        else:
            # Converte para decimal movendo a vírgula 2 casas (ex: 211047 -> 2110.47)
            valor = Decimal(numeros) / Decimal("100")
            formatado = formatar_brl(valor)
            
            # Atualiza no Entry evitando loop
            widget.delete(0, tk.END)
            widget.insert(0, formatado)
            
        self._recalcular(origem)

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

            # 1. Ajuste do Valor negociado & Desconto (%) (Bidirecional)
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
                self.calc_entries["va"].insert(0, formatar_brl(va))
            else:
                va = self._parse_num(self.calc_entries["va"].get())
                if va is None:
                    pct_d = self._parse_num(self.calc_entries["pct_desc"].get()) or Decimal("0")
                    va = (vc * (Decimal("100") - pct_d) / Decimal("100")).quantize(Decimal("0.01"))
                    self.calc_entries["va"].delete(0, "end")
                    self.calc_entries["va"].insert(0, formatar_brl(va))

            # 2. Ajuste do Valor da entrada & Entrada (%) (Bidirecional)
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
                self.calc_entries["ve"].insert(0, formatar_brl(ve))
            else:
                ve = self._parse_num(self.calc_entries["ve"].get())
                if ve is None:
                    pct_e = self._parse_num(self.calc_entries["pct_ent"].get()) or Decimal("0")
                    ve = (va * pct_e / Decimal("100")).quantize(Decimal("0.01"))
                    self.calc_entries["ve"].delete(0, "end")
                    self.calc_entries["ve"].insert(0, formatar_brl(ve))

            # 3. Saldo restante & Valor do desconto
            saldo = max(Decimal("0"), va - ve)
            v_desconto = max(Decimal("0"), vc - va)

            # 4. Parcelas (Qtd x Valor da parcela - Bidirecional)
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
                        self.calc_entries["vp_input"].insert(0, formatar_brl(vp))
                else:
                    vp = Decimal("0")
                    if origem != "vp_input":
                        self.calc_entries["vp_input"].delete(0, "end")
                        self.calc_entries["vp_input"].insert(0, "0,00")

            # 5. Honorários 10% e Valor GEAP
            hon = (va * Decimal("0.10")).quantize(Decimal("0.01")) if va > 0 else Decimal("0")
            geap = va - hon if va > 0 else Decimal("0")

            # Atualiza Demonstrativo com rótulos da planilha
            self._set_out("v_desconto", f"R$ {formatar_brl(v_desconto)}")
            self._set_out("saldo_desc", f"R$ {formatar_brl(va)}")
            self._set_out("ve_res", f"R$ {formatar_brl(ve)}")
            self._set_out("saldo", f"R$ {formatar_brl(saldo)}")
            self._set_out("vp", f"R$ {formatar_brl(vp)}")
            self._set_out("hon", f"R$ {formatar_brl(hon)}")
            self._set_out("geap", f"R$ {formatar_brl(geap)}")

        finally:
            self._calc_state["updating"] = False

    def _reset_calc(self):
        for k in self.calc_entries:
            self.calc_entries[k].delete(0, tk.END)
        self._recalcular()


if __name__ == "__main__":
    app = CalculadoraVendas()
    app.mainloop()
