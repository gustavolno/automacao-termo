import re
import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from docxtpl import DocxTemplate
from num2words import num2words
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import calendar

from parser_acordo import (
    interpretar_mensagem,
    parse_valor_brl,
    formatar_valor_brl,
    calcular_valor_acordo,
    processar_competencias
)

# ============================================================
# CONFIGURAÇÕES
# ============================================================
MODELO_PATH = "MODELO.docx"
MODELO_AVISTA_PATH = "MODELO DE TERMO DE ACORDO-A VISTA.docx"
PASTA_SAIDA = "Termos Gerados"


def valor_por_extenso(valor: float) -> str:
    texto = num2words(valor, lang="pt_BR", to="currency")
    if texto.startswith("mil"):
        texto = "um " + texto
    return texto


def formatar_e_calcular(campos: dict) -> dict:
    MESES = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
             "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    hoje = datetime.now()
    data_hoje = f"{hoje.day} de {MESES[hoje.month]} de {hoje.year}"

    nome = campos.get("nome", "__________").strip() or "__________"
    cpf = campos.get("cpf", "__________").strip() or "__________"
    processo = campos.get("processo", "").strip() or "__________"
    matricula = campos.get("matricula", "__________").strip() or "__________"
    telefone = campos.get("telefone", "__________").strip() or "__________"
    email = campos.get("email", "__________").strip() or "__________"
    endereco = campos.get("endereco", "__________").strip() or "__________"
    cep = campos.get("cep", "__________").strip() or "__________"
    competencias = campos.get("competencias", "__________").strip() or "__________"

    vo = parse_valor_brl(campos.get("valor_original", ""))
    va = parse_valor_brl(campos.get("valor_acordo", ""))
    ve = parse_valor_brl(campos.get("valor_entrada", ""))
    vp = parse_valor_brl(campos.get("valor_parcela", ""))

    qp_raw = campos.get("quantidade_parcelas", "").strip() or campos.get("qtd_parcelas", "").strip()
    try:
        qp = int(qp_raw) if qp_raw else None
    except ValueError:
        qp = None

    venc_entrada = campos.get("vencimento_entrada", "").strip() or campos.get("venc_entrada", "").strip() or "__________"
    inicio_parcelas = campos.get("inicio_parcelas", "").strip() or "__________"
    dia_parcela = campos.get("dia_parcela", "").strip() or "__________"

    fim_parcelas = "__________"
    if inicio_parcelas and inicio_parcelas != "__________" and qp:
        try:
            dt_inicio = datetime.strptime(inicio_parcelas, "%d/%m/%Y")
            mes = dt_inicio.month + qp - 1
            ano = dt_inicio.year + (mes - 1) // 12
            mes = ((mes - 1) % 12) + 1
            ultimo_dia = calendar.monthrange(ano, mes)[1]
            dia = min(dt_inicio.day, ultimo_dia)
            fim_parcelas = datetime(ano, mes, dia).strftime("%d/%m/%Y")
        except Exception:
            fim_parcelas = "__________"

    if vo:
        str_valor_original = f"{formatar_valor_brl(vo)} ({valor_por_extenso(float(vo)).capitalize()})"
    else:
        str_valor_original = "__________"

    if va:
        honorarios = (va * Decimal("0.10")).quantize(Decimal("0.01"))
        valor_geap = va - honorarios
        str_valor_acordo = f"{formatar_valor_brl(va)} ({valor_por_extenso(float(va)).capitalize()})"
        str_honorarios = f"{formatar_valor_brl(honorarios)} ({valor_por_extenso(float(honorarios)).capitalize()})"
        str_valor_geap = f"{formatar_valor_brl(valor_geap)} ({valor_por_extenso(float(valor_geap)).capitalize()})"
    else:
        str_valor_acordo = str_honorarios = str_valor_geap = "__________"

    str_entrada = f"{formatar_valor_brl(ve)} ({valor_por_extenso(float(ve)).capitalize()})" if ve else "__________"
    str_qtd = f"{qp}" if qp else "__________"
    str_parcela = f"{formatar_valor_brl(vp)} ({valor_por_extenso(float(vp)).capitalize()})" if vp else "__________"

    return {
        "nome": nome, "cpf": cpf, "processo": processo, "matricula": matricula,
        "telefone": telefone, "email": email, "endereco": endereco, "cep": cep,
        "valor_original": str_valor_original, "valor_acordo": str_valor_acordo,
        "valor_entrada": str_entrada, "vencimento_entrada": venc_entrada,
        "quantidade_parcelas": str_qtd, "valor_parcela": str_parcela,
        "inicio_parcelas": inicio_parcelas, "dia_parcela": dia_parcela,
        "competencias": competencias,
        "nome_cliente": nome, "cpf_cliente": cpf, "valor_divida": str_valor_original,
        "venc_entrada": venc_entrada, "qtd_parcelas": str_qtd, "fim_parcelas": fim_parcelas,
        "honorarios": str_honorarios, "valor_geap": str_valor_geap, "data": data_hoje,
    }


def gerar_documento(campos_revisados: dict, modelo_path: str = MODELO_PATH):
    dados = formatar_e_calcular(campos_revisados)
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    nome_clean = re.sub(r'[\\/*?:"<>|]', "", dados["nome_cliente"])[:50]
    caminho = os.path.join(PASTA_SAIDA, f"Termo_{nome_clean}.docx")
    doc = DocxTemplate(modelo_path)
    doc.render(dados)
    doc.save(caminho)
    return caminho, dados


# ============================================================
# PALETA MINIMALISTA
# ============================================================
BG = "#FAFAFA"
BG_SURFACE = "#FFFFFF"
BG_INPUT = "#F3F3F5"
BG_INPUT_FOCUS = "#EEEEF2"
BORDER_LIGHT = "#E4E4E7"
BORDER = "#D4D4D8"
ACCENT = "#18181B"
ACCENT_SOFT = "#3F3F46"
ACCENT_HOVER = "#27272A"
TEXT = "#18181B"
TEXT_SEC = "#71717A"
TEXT_MUTED = "#A1A1AA"
TEXT_PLACEHOLDER = "#C4C4CC"
GREEN = "#16A34A"
GREEN_BG = "#F0FDF4"
RED = "#DC2626"
RED_BG = "#FEF2F2"
AMBER = "#D97706"
AMBER_BG = "#FFFBEB"
BLUE = "#2563EB"

CAMPOS_REVISAO = [
    ("Nome", "nome"),
    ("CPF", "cpf"),
    ("Processo", "processo"),
    ("Matrícula", "matricula"),
    ("Telefone", "telefone"),
    ("E-mail", "email"),
    ("Endereço", "endereco"),
    ("CEP", "cep"),
    ("Valor Original", "valor_original"),
    ("Valor do Acordo", "valor_acordo"),
    ("Valor Entrada", "valor_entrada"),
    ("Venc. Entrada", "vencimento_entrada"),
    ("Qtd. Parcelas", "quantidade_parcelas"),
    ("Valor Parcela", "valor_parcela"),
    ("Início Parcelas", "inicio_parcelas"),
    ("Dia Vencimento", "dia_parcela"),
    ("Competências", "competencias"),
]

PLACEHOLDER = "Cole a mensagem aqui..."


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Termos de Acordo — AC Advocacia")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(900, 640)
        self.entries = {}
        self.calc_entries = {}
        self._build_ui()
        self.after(50, self._centralizar)

    def _centralizar(self):
        self.update_idletasks()
        w, h = 1020, 720
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _build_ui(self):
        # ── Barra superior ──
        topbar = tk.Frame(self, bg=BG_SURFACE, height=48)
        topbar.pack(fill="x")
        topbar.pack_propagate(False)

        tk.Label(topbar, text="Termos de Acordo",
                 font=("Segoe UI Semibold", 13), bg=BG_SURFACE, fg=TEXT
                 ).pack(side="left", padx=20, pady=10)

        tk.Label(topbar, text="AC Advocacia",
                 font=("Segoe UI", 9), bg=BG_SURFACE, fg=TEXT_MUTED
                 ).pack(side="left", pady=10)

        # Linha fina
        tk.Frame(self, bg=BORDER_LIGHT, height=1).pack(fill="x")

        # ── Tabs ──
        tab_bar = tk.Frame(self, bg=BG_SURFACE, height=40)
        tab_bar.pack(fill="x")
        tab_bar.pack_propagate(False)

        self._tab_frames = {}
        self._tab_buttons = {}
        self._active_tab = None

        tabs = [
            ("Gerador", "gerador"),
            ("Calculadora", "calculadora"),
        ]

        for label, key in tabs:
            btn = tk.Label(tab_bar, text=label,
                           font=("Segoe UI", 10), bg=BG_SURFACE, fg=TEXT_MUTED,
                           cursor="hand2", padx=16, pady=8)
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda e, k=key: self._switch_tab(k))
            btn.bind("<Enter>", lambda e, b=btn: b.config(fg=TEXT) if b != self._tab_buttons.get(self._active_tab) else None)
            btn.bind("<Leave>", lambda e, b=btn: b.config(fg=TEXT_MUTED) if b != self._tab_buttons.get(self._active_tab) else None)
            self._tab_buttons[key] = btn

        tk.Frame(self, bg=BORDER_LIGHT, height=1).pack(fill="x")

        # Container de conteúdo
        self._content = tk.Frame(self, bg=BG)
        self._content.pack(fill="both", expand=True)

        self._build_tab_gerador()
        self._build_tab_calculadora()
        self._switch_tab("gerador")

    def _switch_tab(self, key):
        if self._active_tab == key:
            return
        self._active_tab = key
        # Esconde todos
        for k, f in self._tab_frames.items():
            f.pack_forget()
        # Mostra o selecionado
        self._tab_frames[key].pack(in_=self._content, fill="both", expand=True)
        # Estiliza tabs
        for k, btn in self._tab_buttons.items():
            if k == key:
                btn.config(fg=TEXT, font=("Segoe UI Semibold", 10))
            else:
                btn.config(fg=TEXT_MUTED, font=("Segoe UI", 10))

    # ============================================================
    # ABA GERADOR
    # ============================================================
    def _build_tab_gerador(self):
        tab = tk.Frame(self._content, bg=BG)
        self._tab_frames["gerador"] = tab

        main = tk.Frame(tab, bg=BG)
        main.pack(fill="both", expand=True, padx=24, pady=16)
        main.columnconfigure(0, weight=2)
        main.columnconfigure(1, weight=3)
        main.rowconfigure(0, weight=1)

        # ── Esquerda: Entrada ──
        esq = tk.Frame(main, bg=BG)
        esq.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        esq.rowconfigure(1, weight=1)
        esq.columnconfigure(0, weight=1)

        tk.Label(esq, text="Mensagem", font=("Segoe UI Semibold", 10),
                 bg=BG, fg=TEXT).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.txt = scrolledtext.ScrolledText(
            esq, wrap=tk.WORD, font=("Consolas", 9),
            bg=BG_SURFACE, fg=TEXT_PLACEHOLDER,
            insertbackground=ACCENT, relief="flat",
            padx=12, pady=10, bd=0,
            highlightthickness=1, highlightbackground=BORDER_LIGHT,
            highlightcolor=BORDER
        )
        self.txt.grid(row=1, column=0, sticky="nsew")
        self.txt.insert("1.0", PLACEHOLDER)
        self.txt.bind("<FocusIn>", self._limpar_ph)
        self.txt.bind("<FocusOut>", self._restaurar_ph)

        btn_interp = tk.Button(
            esq, text="Interpretar",
            font=("Segoe UI Semibold", 10),
            bg=ACCENT, fg="#FFFFFF",
            activebackground=ACCENT_HOVER, activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", pady=8, bd=0,
            command=self._interpretar
        )
        btn_interp.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        btn_interp.bind("<Enter>", lambda e: btn_interp.config(bg=ACCENT_HOVER))
        btn_interp.bind("<Leave>", lambda e: btn_interp.config(bg=ACCENT))

        # ── Direita: Campos ──
        dir_ = tk.Frame(main, bg=BG)
        dir_.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        dir_.columnconfigure(0, weight=1)
        dir_.rowconfigure(1, weight=1)

        tk.Label(dir_, text="Campos extraídos", font=("Segoe UI Semibold", 10),
                 bg=BG, fg=TEXT).grid(row=0, column=0, sticky="w", pady=(0, 6))

        canvas = tk.Canvas(dir_, bg=BG, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(dir_, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=BG)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Ajustar largura do scroll_frame ao canvas
        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")

        scroll_frame.columnconfigure(1, weight=1)

        for i, (label, chave) in enumerate(CAMPOS_REVISAO):
            tk.Label(scroll_frame, text=label, font=("Segoe UI", 8),
                     bg=BG, fg=TEXT_SEC, anchor="e").grid(
                row=i, column=0, sticky="e", padx=(0, 10), pady=3
            )

            ent = tk.Entry(scroll_frame, font=("Segoe UI", 10),
                           bg=BG_INPUT, fg=TEXT,
                           insertbackground=ACCENT,
                           relief="flat", bd=0,
                           highlightthickness=1,
                           highlightbackground=BORDER_LIGHT,
                           highlightcolor=BORDER)
            ent.grid(row=i, column=1, sticky="ew", pady=3, ipady=5)
            self.entries[chave] = ent

        # ── Rodapé ──
        footer = tk.Frame(tab, bg=BG, padx=24, pady=12)
        footer.pack(fill="x")

        self.status_var = tk.StringVar(value="")
        self.status_lbl = tk.Label(footer, textvariable=self.status_var,
                 font=("Segoe UI", 8), bg=BG, fg=TEXT_MUTED, anchor="w")
        self.status_lbl.pack(fill="x", pady=(0, 8))

        btn_row = tk.Frame(footer, bg=BG)
        btn_row.pack(fill="x")

        self.btn_gerar_parcelado = self._make_btn(
            btn_row, "Gerar Parcelado", ACCENT, "#FFF",
            lambda: self._gerar("parcelado"))
        self.btn_gerar_parcelado.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_gerar_avista = self._make_btn(
            btn_row, "Gerar À Vista", ACCENT, "#FFF",
            lambda: self._gerar("avista"))
        self.btn_gerar_avista.pack(side="left", fill="x", expand=True, padx=(4, 4))

        self.btn_reset = self._make_btn(
            btn_row, "Limpar", BG_INPUT, TEXT_SEC,
            self._reset_campos, hover_bg=BORDER_LIGHT)
        self.btn_reset.pack(side="left", fill="x", expand=True, padx=(4, 0))

    def _make_btn(self, parent, text, bg, fg, cmd, hover_bg=None):
        btn = tk.Button(parent, text=text, font=("Segoe UI Semibold", 9),
                        bg=bg, fg=fg, activebackground=hover_bg or ACCENT_HOVER,
                        activeforeground=fg, relief="flat", cursor="hand2",
                        pady=8, bd=0, command=cmd)
        hbg = hover_bg or ACCENT_HOVER
        btn.bind("<Enter>", lambda e: btn.config(bg=hbg))
        btn.bind("<Leave>", lambda e: btn.config(bg=bg))
        return btn

    # ============================================================
    # ABA CALCULADORA
    # ============================================================
    def _build_tab_calculadora(self):
        tab = tk.Frame(self._content, bg=BG)
        self._tab_frames["calculadora"] = tab

        wrapper = tk.Frame(tab, bg=BG, padx=40, pady=24)
        wrapper.pack(fill="both", expand=True)
        wrapper.columnconfigure(0, weight=1)
        wrapper.columnconfigure(1, weight=1)

        # ── Parcelado ──
        self._build_calc_card(wrapper, col=0, title="Cálculo Parcelado",
            fields=[
                ("Valor da Causa", "p_vc"),
                ("Desconto (%)", "p_desc"),
                ("Entrada (%)", "p_ent"),
                ("Nº Parcelas", "p_np"),
            ],
            results=[
                ("Valor desconto", "p_r_desc"),
                ("Saldo após desconto", "p_r_saldo"),
                ("Valor entrada", "p_r_ent"),
                ("Saldo restante", "p_r_rest"),
                ("Parcela mensal", "p_r_parc"),
            ],
            calc_cmd=self._calc_parcelado
        )

        # ── À Vista ──
        self._build_calc_card(wrapper, col=1, title="Cálculo À Vista",
            fields=[
                ("Valor da Causa", "v_vc"),
                ("Desconto (%)", "v_desc"),
            ],
            results=[
                ("Valor desconto", "v_r_desc"),
                ("Saldo restante", "v_r_saldo"),
            ],
            calc_cmd=self._calc_avista
        )

    def _build_calc_card(self, parent, col, title, fields, results, calc_cmd):
        card = tk.Frame(parent, bg=BG_SURFACE, highlightthickness=1,
                        highlightbackground=BORDER_LIGHT, highlightcolor=BORDER_LIGHT)
        card.grid(row=0, column=col, sticky="nsew", padx=8, pady=0)
        parent.rowconfigure(0, weight=1)

        inner = tk.Frame(card, bg=BG_SURFACE, padx=20, pady=20)
        inner.pack(fill="both", expand=True)

        tk.Label(inner, text=title, font=("Segoe UI Semibold", 12),
                 bg=BG_SURFACE, fg=TEXT).pack(anchor="w", pady=(0, 16))

        for label, key in fields:
            tk.Label(inner, text=label, font=("Segoe UI", 8),
                     bg=BG_SURFACE, fg=TEXT_SEC).pack(anchor="w", pady=(0, 2))
            ent = tk.Entry(inner, font=("Segoe UI", 11),
                           bg=BG_INPUT, fg=TEXT, insertbackground=ACCENT,
                           relief="flat", bd=0, highlightthickness=1,
                           highlightbackground=BORDER_LIGHT, highlightcolor=BORDER)
            ent.pack(fill="x", ipady=5, pady=(0, 10))
            self.calc_entries[key] = ent

        btn = tk.Button(inner, text="Calcular", font=("Segoe UI Semibold", 10),
                        bg=ACCENT, fg="#FFF", activebackground=ACCENT_HOVER,
                        activeforeground="#FFF", relief="flat", cursor="hand2",
                        pady=8, bd=0, command=calc_cmd)
        btn.pack(fill="x", pady=(4, 16))
        btn.bind("<Enter>", lambda e: btn.config(bg=ACCENT_HOVER))
        btn.bind("<Leave>", lambda e: btn.config(bg=ACCENT))

        # Linha separadora
        tk.Frame(inner, bg=BORDER_LIGHT, height=1).pack(fill="x", pady=(0, 12))

        self._calc_results = getattr(self, '_calc_results', {})
        for label, key in results:
            row = tk.Frame(inner, bg=BG_SURFACE)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, font=("Segoe UI", 9),
                     bg=BG_SURFACE, fg=TEXT_SEC).pack(side="left")
            lbl = tk.Label(row, text="—", font=("Segoe UI Semibold", 11),
                           bg=BG_SURFACE, fg=TEXT)
            lbl.pack(side="right")
            self._calc_results[key] = lbl

    # ── Lógica da Calculadora ──
    def _parse_num(self, text):
        t = text.strip().replace("R$", "").replace(" ", "")
        if not t:
            return None
        if "," in t and "." in t:
            t = t.replace(".", "").replace(",", ".")
        elif "," in t:
            t = t.replace(",", ".")
        try:
            return Decimal(t)
        except Exception:
            return None

    def _fmt(self, v):
        if v is None:
            return "—"
        return "R$ " + formatar_valor_brl(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def _calc_parcelado(self):
        vc = self._parse_num(self.calc_entries["p_vc"].get())
        pct_d = self._parse_num(self.calc_entries["p_desc"].get())
        pct_e = self._parse_num(self.calc_entries["p_ent"].get())
        np = self._parse_num(self.calc_entries["p_np"].get())
        if not vc or not pct_d:
            messagebox.showwarning("", "Preencha ao menos Valor da Causa e Desconto.")
            return

        desc = (vc * pct_d / 100).quantize(Decimal("0.01"))
        saldo = vc - desc
        ent = (saldo * pct_e / 100).quantize(Decimal("0.01")) if pct_e else Decimal("0")
        rest = saldo - ent
        parc = (rest / np).quantize(Decimal("0.01")) if np and np > 0 else Decimal("0")

        self._calc_results["p_r_desc"].config(text=self._fmt(desc))
        self._calc_results["p_r_saldo"].config(text=self._fmt(saldo))
        self._calc_results["p_r_ent"].config(text=self._fmt(ent))
        self._calc_results["p_r_rest"].config(text=self._fmt(rest), fg=BLUE)
        self._calc_results["p_r_parc"].config(text=self._fmt(parc), fg=GREEN)

    def _calc_avista(self):
        vc = self._parse_num(self.calc_entries["v_vc"].get())
        pct = self._parse_num(self.calc_entries["v_desc"].get())
        if not vc or not pct:
            messagebox.showwarning("", "Preencha Valor da Causa e Desconto.")
            return

        desc = (vc * pct / 100).quantize(Decimal("0.01"))
        saldo = vc - desc

        self._calc_results["v_r_desc"].config(text=self._fmt(desc))
        self._calc_results["v_r_saldo"].config(text=self._fmt(saldo), fg=GREEN)

    # ============================================================
    # EVENTOS
    # ============================================================
    def _limpar_ph(self, _e):
        if self.txt.get("1.0", "end-1c") == PLACEHOLDER:
            self.txt.delete("1.0", "end")
            self.txt.config(fg=TEXT)

    def _restaurar_ph(self, _e):
        if not self.txt.get("1.0", "end-1c").strip():
            self.txt.insert("1.0", PLACEHOLDER)
            self.txt.config(fg=TEXT_PLACEHOLDER)

    def _reset_campos(self):
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", PLACEHOLDER)
        self.txt.config(fg=TEXT_PLACEHOLDER)
        for entry in self.entries.values():
            entry.delete(0, "end")
            entry.config(highlightbackground=BORDER_LIGHT, highlightcolor=BORDER)
        self.status_var.set("")

    def _interpretar(self):
        msg = self.txt.get("1.0", "end-1c").strip()
        if not msg or msg == PLACEHOLDER:
            messagebox.showwarning("", "Cole a mensagem primeiro.")
            return

        campos = interpretar_mensagem(msg)
        for chave, entry in self.entries.items():
            entry.delete(0, "end")
            val = campos.get(chave, "")
            entry.insert(0, val)
            entry.xview_moveto(0)
            if not val and chave in ("nome", "cpf", "valor_acordo"):
                entry.config(highlightbackground=RED, highlightcolor=RED)
            else:
                entry.config(highlightbackground=BORDER_LIGHT, highlightcolor=BORDER)

        vazios = [lab for lab, ch in CAMPOS_REVISAO if not campos.get(ch)]
        if vazios:
            self.status_var.set(f"Campos não identificados: {', '.join(vazios)}")
            self.status_lbl.config(fg=AMBER)
        else:
            self.status_var.set("Todos os campos interpretados com sucesso")
            self.status_lbl.config(fg=GREEN)

    def _gerar(self, tipo="parcelado"):
        modelo = MODELO_AVISTA_PATH if tipo == "avista" else MODELO_PATH
        if not os.path.exists(modelo):
            messagebox.showerror("Erro", f"Modelo não encontrado: {modelo}")
            return

        campos = {ch: entry.get().strip() for ch, entry in self.entries.items()}
        if not campos.get("nome"):
            messagebox.showwarning("", "O campo Nome é obrigatório.")
            return

        self.btn_gerar_parcelado.config(state="disabled")
        self.btn_gerar_avista.config(state="disabled")
        self.update()

        try:
            caminho, dados = gerar_documento(campos, modelo)
            tipo_label = "Parcelado" if tipo == "parcelado" else "À Vista"
            self.status_var.set(f"Documento gerado: {caminho}")
            self.status_lbl.config(fg=GREEN)
            resp = messagebox.askyesno(
                "Documento gerado",
                f"Termo ({tipo_label}) gerado com sucesso.\n\n"
                f"{dados['nome_cliente']}\n{dados['cpf_cliente']}\n\n"
                f"Abrir agora?"
            )
            if resp:
                os.startfile(os.path.abspath(caminho))
            self._reset_campos()
        except Exception as e:
            self.status_var.set(f"Erro: {e}")
            self.status_lbl.config(fg=RED)
            messagebox.showerror("Erro", str(e))
        finally:
            self.btn_gerar_parcelado.config(state="normal")
            self.btn_gerar_avista.config(state="normal")


if __name__ == "__main__":
    app = App()
    app.mainloop()
