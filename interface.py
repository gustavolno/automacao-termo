import re
import os
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from docxtpl import DocxTemplate
from num2words import num2words
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import calendar
import pdfplumber

from parser_acordo import (
    interpretar_mensagem,
    parse_valor_brl,
    formatar_valor_brl,
    calcular_valor_acordo,
    processar_competencias,
    processar_demonstrativo
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
# PALETA DE CORES — ALDRIGUES CÂNDIDO ADVOCACIA (DARK GOLD/NEON)
# ============================================================
BG_MAIN = "#0a0d12"        # Dark charcoal navy background
BG_NAV = "#0f1318"         # Dark header navbar
BG_CARD = "#131920"        # Dark card container
BG_INPUT = "#0a0d12"       # Inner input area
BORDER_COLOR = "#1e2a38"   # Subtle border

ACCENT_GOLD = "#D4AF37"    # Luxury Law Firm Gold (Primary Brand)
ACCENT_GOLD_HOVER = "#F0C850"
ACCENT_EMERALD = "#00e5a0" # Neon Mint/Green (Success & Financial)
ACCENT_CYAN = "#0094ff"    # Electric Blue/Cyan
ACCENT_PINK = "#ff70a6"    # Soft Pink/Purple for Saldo Pós Entrada

TEXT_BRIGHT = "#e8f0fe"    # Primary white-blue text
TEXT_MUTED = "#6b7f96"     # Muted slate text
TEXT_DIM = "#41536b"       # Placeholder text

COLOR_RED = "#ff5f56"      # Mac terminal red
COLOR_YELLOW = "#ffbd2e"   # Mac terminal yellow
COLOR_GREEN = "#27c93f"    # Mac terminal green

FONT_MONO = ("Consolas", 10)
FONT_MONO_BOLD = ("Consolas", 10, "bold")

CAMPOS_REVISAO = [
    ("nome", "Nome / Cliente"),
    ("cpf", "CPF"),
    ("processo", "Processo Judicial"),
    ("matricula", "Matrícula"),
    ("telefone", "Telefone / WhatsApp"),
    ("email", "E-mail"),
    ("endereco", "Endereço"),
    ("cep", "CEP"),
    ("valor_original", "Valor Original"),
    ("valor_acordo", "Valor do Acordo"),
    ("valor_entrada", "Valor Entrada"),
    ("vencimento_entrada", "Venc. Entrada"),
    ("quantidade_parcelas", "Qtd. Parcelas"),
    ("valor_parcela", "Valor Parcela"),
    ("inicio_parcelas", "Início Parcelas"),
    ("dia_parcela", "Dia Vencimento"),
    ("competencias", "Competências"),
]

PLACEHOLDER = "// Cole a mensagem do atendimento jurídica/acordo recebida..."
PLACEHOLDER_DEMO = "// Anexe o PDF do Demonstrativo de Valores ou cole a tabela aqui..."


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Aldrigues Cândido Advocacia — Gerador de Termos de Acordo")
        self.configure(bg=BG_MAIN)
        self.resizable(True, True)
        self.minsize(1020, 700)
        self.entries = {}
        self.calc_entries = {}
        self.demo_entries = {}
        self._build_ui()
        self.after(50, self._centralizar)

    def _centralizar(self):
        self.update_idletasks()
        w, h = 1080, 760
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _build_ui(self):
        # ── NAV BAR (Estilo Aldrigues Cândido Advocacia) ──
        navbar = tk.Frame(self, bg=BG_NAV, height=54, highlightthickness=1, highlightbackground=BORDER_COLOR)
        navbar.pack(fill="x")
        navbar.pack_propagate(False)

        # Logotipo / Marca Advocacia
        brand_frame = tk.Frame(navbar, bg=BG_NAV)
        brand_frame.pack(side="left", padx=20)
        
        tk.Label(brand_frame, text="⚖ ", font=("Segoe UI", 12), bg=BG_NAV, fg=ACCENT_GOLD).pack(side="left")
        tk.Label(brand_frame, text="ALDRIGUES CÂNDIDO", font=("Georgia", 11, "bold"), bg=BG_NAV, fg=ACCENT_GOLD).pack(side="left")
        tk.Label(brand_frame, text=" ADVOCACIA", font=("Segoe UI", 9, "bold"), bg=BG_NAV, fg=TEXT_BRIGHT).pack(side="left")
        tk.Label(brand_frame, text=" / modulo-termo", font=FONT_MONO, bg=BG_NAV, fg=TEXT_MUTED).pack(side="left")

        # Tabs no topo direito
        self._tab_frames = {}
        self._tab_buttons = {}
        self._active_tab = None

        tabs_frame = tk.Frame(navbar, bg=BG_NAV)
        tabs_frame.pack(side="right", padx=16)

        tabs = [
            ("gerador", "[ 01. GERADOR DE TERMOS ]"),
            ("calculadora", "[ 02. CALCULADORA DE NEGOCIAÇÃO ]"),
            ("demonstrativo", "[ 03. DEMONSTRATIVO & COMPETÊNCIAS ]"),
        ]

        for key, label in tabs:
            btn = tk.Label(tabs_frame, text=label, font=FONT_MONO_BOLD,
                           bg=BG_NAV, fg=TEXT_MUTED, cursor="hand2", padx=10, pady=14)
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda e, k=key: self._switch_tab(k))
            btn.bind("<Enter>", lambda e, b=btn, k=key: b.config(fg=ACCENT_GOLD) if k != self._active_tab else None)
            btn.bind("<Leave>", lambda e, b=btn, k=key: b.config(fg=TEXT_MUTED) if k != self._active_tab else None)
            self._tab_buttons[key] = btn

        # Container principal
        self._content = tk.Frame(self, bg=BG_MAIN)
        self._content.pack(fill="both", expand=True, padx=16, pady=14)

        self._build_tab_gerador()
        self._build_tab_calculadora()
        self._build_tab_demonstrativo()
        self._switch_tab("gerador")

    def _switch_tab(self, key):
        if self._active_tab == key:
            return
        self._active_tab = key
        for k, f in self._tab_frames.items():
            f.pack_forget()
        self._tab_frames[key].pack(in_=self._content, fill="both", expand=True)

        for k, btn in self._tab_buttons.items():
            if k == key:
                btn.config(fg=ACCENT_GOLD)
            else:
                btn.config(fg=TEXT_MUTED)

    # ============================================================
    # ABA 1 - GERADOR DE TERMOS
    # ============================================================
    def _build_tab_gerador(self):
        tab = tk.Frame(self._content, bg=BG_MAIN)
        self._tab_frames["gerador"] = tab

        grid = tk.Frame(tab, bg=BG_MAIN)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(0, weight=1)

        # ── Card Esquerda (Entrada Bruta) ──
        term_card = tk.Frame(grid, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR)
        term_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        term_card.rowconfigure(1, weight=1)
        term_card.columnconfigure(0, weight=1)

        t_bar = tk.Frame(term_card, bg=BG_NAV, height=36, highlightthickness=1, highlightbackground=BORDER_COLOR)
        t_bar.grid(row=0, column=0, sticky="ew")
        t_bar.pack_propagate(False)

        dots_f = tk.Frame(t_bar, bg=BG_NAV)
        dots_f.pack(side="left", padx=12)
        tk.Canvas(dots_f, width=10, height=10, bg=BG_NAV, highlightthickness=0).pack(side="left", padx=2)
        dots_f.winfo_children()[-1].create_oval(0, 0, 9, 9, fill=COLOR_RED, outline="")
        tk.Canvas(dots_f, width=10, height=10, bg=BG_NAV, highlightthickness=0).pack(side="left", padx=2)
        dots_f.winfo_children()[-1].create_oval(0, 0, 9, 9, fill=COLOR_YELLOW, outline="")
        tk.Canvas(dots_f, width=10, height=10, bg=BG_NAV, highlightthickness=0).pack(side="left", padx=2)
        dots_f.winfo_children()[-1].create_oval(0, 0, 9, 9, fill=COLOR_GREEN, outline="")

        tk.Label(t_bar, text="mensagem_atendimento.txt", font=FONT_MONO, bg=BG_NAV, fg=TEXT_MUTED).pack(side="left", padx=8)

        self.txt = scrolledtext.ScrolledText(
            term_card, wrap=tk.WORD, font=FONT_MONO,
            bg=BG_INPUT, fg=TEXT_DIM,
            insertbackground=ACCENT_GOLD, relief="flat",
            padx=14, pady=12, bd=0,
            selectbackground=BORDER_COLOR, selectforeground=TEXT_BRIGHT
        )
        self.txt.grid(row=1, column=0, sticky="nsew", padx=1, pady=1)
        self.txt.insert("1.0", PLACEHOLDER)
        self.txt.bind("<FocusIn>", self._limpar_ph)
        self.txt.bind("<FocusOut>", self._restaurar_ph)

        btn_interp = tk.Button(
            term_card, text="❯ INTERPRETAR MENSAGEM",
            font=FONT_MONO_BOLD, bg=BG_NAV, fg=ACCENT_GOLD,
            activebackground=BORDER_COLOR, activeforeground=ACCENT_GOLD_HOVER,
            relief="flat", cursor="hand2", pady=10, bd=0,
            command=self._interpretar
        )
        btn_interp.grid(row=2, column=0, sticky="ew")
        btn_interp.bind("<Enter>", lambda e: btn_interp.config(bg=BORDER_COLOR))
        btn_interp.bind("<Leave>", lambda e: btn_interp.config(bg=BG_NAV))

        # ── Card Direita (Revisão de Campos) ──
        fields_card = tk.Frame(grid, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR)
        fields_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        fields_card.rowconfigure(1, weight=1)
        fields_card.columnconfigure(0, weight=1)

        f_bar = tk.Frame(fields_card, bg=BG_NAV, height=36, highlightthickness=1, highlightbackground=BORDER_COLOR)
        f_bar.grid(row=0, column=0, sticky="ew")
        f_bar.pack_propagate(False)
        tk.Label(f_bar, text="campos_minuta.json", font=FONT_MONO, bg=BG_NAV, fg=ACCENT_GOLD).pack(side="left", padx=14)

        canvas = tk.Canvas(fields_card, bg=BG_CARD, highlightthickness=0, bd=0)
        scrollbar = tk.Scrollbar(fields_card, orient="vertical", command=canvas.yview,
                                 bg=BG_CARD, troughcolor=BG_MAIN, activebackground=ACCENT_GOLD)
        scroll_frame = tk.Frame(canvas, bg=BG_CARD)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        canvas.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        scrollbar.grid(row=1, column=1, sticky="ns")

        scroll_frame.columnconfigure(1, weight=1)

        for i, (chave, label) in enumerate(CAMPOS_REVISAO):
            lbl = tk.Label(scroll_frame, text=label, font=FONT_MONO,
                           bg=BG_CARD, fg=TEXT_MUTED, anchor="e")
            lbl.grid(row=i, column=0, sticky="e", padx=(0, 10), pady=4)

            ent = tk.Entry(scroll_frame, font=FONT_MONO,
                           bg=BG_INPUT, fg=TEXT_BRIGHT,
                           insertbackground=ACCENT_GOLD,
                           relief="flat", bd=0,
                           highlightthickness=1,
                           highlightbackground=BORDER_COLOR,
                           highlightcolor=ACCENT_GOLD)
            ent.grid(row=i, column=1, sticky="ew", pady=4, ipady=4)
            self.entries[chave] = ent

        # ── Rodapé de Ações ──
        footer = tk.Frame(tab, bg=BG_MAIN, pady=10)
        footer.pack(fill="x")

        self.status_var = tk.StringVar(value="// Aldrigues Cândido Advocacia — Aguardando mensagem.")
        self.status_lbl = tk.Label(footer, textvariable=self.status_var,
                                   font=FONT_MONO, bg=BG_MAIN, fg=TEXT_MUTED, anchor="w")
        self.status_lbl.pack(fill="x", pady=(0, 8))

        btn_row = tk.Frame(footer, bg=BG_MAIN)
        btn_row.pack(fill="x")

        self.btn_gerar_parcelado = tk.Button(
            btn_row, text="[ ⚖ GERAR TERMO PARCELADO ]",
            font=FONT_MONO_BOLD, bg=ACCENT_GOLD, fg=BG_MAIN,
            activebackground=ACCENT_GOLD_HOVER, activeforeground=BG_MAIN,
            relief="flat", cursor="hand2", pady=10, bd=0,
            command=lambda: self._gerar("parcelado")
        )
        self.btn_gerar_parcelado.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.btn_gerar_parcelado.bind("<Enter>", lambda e: self.btn_gerar_parcelado.config(bg=ACCENT_GOLD_HOVER))
        self.btn_gerar_parcelado.bind("<Leave>", lambda e: self.btn_gerar_parcelado.config(bg=ACCENT_GOLD))

        self.btn_gerar_avista = tk.Button(
            btn_row, text="[ 💰 GERAR TERMO À VISTA ]",
            font=FONT_MONO_BOLD, bg=ACCENT_EMERALD, fg=BG_MAIN,
            activebackground="#00ffb3", activeforeground=BG_MAIN,
            relief="flat", cursor="hand2", pady=10, bd=0,
            command=lambda: self._gerar("avista")
        )
        self.btn_gerar_avista.pack(side="left", fill="x", expand=True, padx=(6, 6))
        self.btn_gerar_avista.bind("<Enter>", lambda e: self.btn_gerar_avista.config(bg="#00ffb3"))
        self.btn_gerar_avista.bind("<Leave>", lambda e: self.btn_gerar_avista.config(bg=ACCENT_EMERALD))

        self.btn_reset = tk.Button(
            btn_row, text="[ RESETAR CAMPOS ]",
            font=FONT_MONO_BOLD, bg=BG_CARD, fg=TEXT_MUTED,
            activebackground=BORDER_COLOR, activeforeground=TEXT_BRIGHT,
            relief="flat", cursor="hand2", pady=10, bd=0,
            command=self._reset_campos
        )
        self.btn_reset.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.btn_reset.bind("<Enter>", lambda e: self.btn_reset.config(bg=BORDER_COLOR, fg=TEXT_BRIGHT))
        self.btn_reset.bind("<Leave>", lambda e: self.btn_reset.config(bg=BG_CARD, fg=TEXT_MUTED))

    # ============================================================
    # ABA 2 - CALCULADORA DE NEGOCIAÇÃO
    # ============================================================
    def _build_tab_calculadora(self):
        tab = tk.Frame(self._content, bg=BG_MAIN)
        self._tab_frames["calculadora"] = tab

        grid = tk.Frame(tab, bg=BG_MAIN)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(0, weight=1)

        # ── Card Parcelado ──
        self._build_calc_card(grid, col=0, title="// Simulação Parcelada (Campos Editáveis)", accent_color=ACCENT_GOLD,
            fields=[
                ("parc_valor_causa", "Valor da Causa (R$)"),
                ("parc_pct_desconto", "% Desconto"),
                ("parc_pct_entrada", "% Entrada"),
                ("parc_num_parcelas", "Parcelas (Nº)"),
            ],
            results=[
                ("parc_res_desconto", "Valor de Desconto", ACCENT_GOLD),
                ("parc_res_saldo_desc", "Saldo Restante (Pós Desconto)", ACCENT_CYAN),
                ("parc_res_entrada", "Valor de Entrada", ACCENT_EMERALD),
                ("parc_res_saldo_rest", "Saldo Restante (Pós Entrada)", ACCENT_PINK),
                ("parc_res_parcela", "Parcela Mensal", ACCENT_EMERALD),
            ],
            calc_cmd=self._calcular_parcelado
        )

        # ── Card À Vista ──
        self._build_calc_card(grid, col=1, title="// Simulação À Vista (Campos Editáveis)", accent_color=ACCENT_EMERALD,
            fields=[
                ("av_valor_causa", "Valor da Causa (R$)"),
                ("av_pct_desconto", "% Desconto"),
            ],
            results=[
                ("av_res_desconto", "Valor de Desconto", ACCENT_GOLD),
                ("av_res_saldo", "Saldo Restante (Quitação)", ACCENT_EMERALD),
            ],
            calc_cmd=self._calcular_avista
        )

    def _build_calc_card(self, parent, col, title, accent_color, fields, results, calc_cmd):
        card = tk.Frame(parent, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR)
        card.grid(row=0, column=col, sticky="nsew", padx=6, pady=0)

        bar = tk.Frame(card, bg=BG_NAV, height=36, highlightthickness=1, highlightbackground=BORDER_COLOR)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text=title, font=FONT_MONO_BOLD, bg=BG_NAV, fg=accent_color).pack(side="left", padx=14)

        body = tk.Frame(card, bg=BG_CARD, padx=18, pady=16)
        body.pack(fill="both", expand=True)

        tk.Label(body, text="📝 [ EDITÁVEIS ] Digite nos campos abaixo:", font=("Consolas", 8), bg=BG_CARD, fg=TEXT_MUTED).pack(anchor="w", pady=(0, 8))

        for key, label in fields:
            lbl_frame = tk.Frame(body, bg=BG_CARD)
            lbl_frame.pack(fill="x")
            tk.Label(lbl_frame, text=label, font=FONT_MONO, bg=BG_CARD, fg=TEXT_BRIGHT).pack(side="left")
            tk.Label(lbl_frame, text=" [EDITÁVEL]", font=("Consolas", 7, "bold"), bg=BG_CARD, fg=ACCENT_GOLD).pack(side="left", padx=4)

            ent = tk.Entry(body, font=FONT_MONO_BOLD, bg=BG_INPUT, fg="#ffffff",
                           insertbackground="#ffffff", relief="flat", bd=0,
                           highlightthickness=1, highlightbackground="#ffffff",
                           highlightcolor=accent_color)
            ent.pack(fill="x", ipady=6, pady=(2, 10))
            ent.bind("<KeyRelease>", lambda e: calc_cmd())
            self.calc_entries[key] = ent

        btn = tk.Button(body, text="⚡ CALCULAR SIMULAÇÃO", font=FONT_MONO_BOLD,
                        bg=BG_NAV, fg=accent_color, activebackground=BORDER_COLOR,
                        activeforeground=accent_color, relief="flat", cursor="hand2",
                        pady=8, bd=0, command=calc_cmd)
        btn.pack(fill="x", pady=(4, 14))
        btn.bind("<Enter>", lambda e: btn.config(bg=BORDER_COLOR))
        btn.bind("<Leave>", lambda e: btn.config(bg=BG_NAV))

        tk.Frame(body, bg=BORDER_COLOR, height=1).pack(fill="x", pady=(0, 12))

        tk.Label(body, text="📊 [ SELECIONÁVEIS ] Clique/arraste para copiar o valor:", font=("Consolas", 8), bg=BG_CARD, fg=TEXT_MUTED).pack(anchor="w", pady=(0, 6))

        self._calc_results = getattr(self, '_calc_results', {})
        for key, label, color in results:
            row = tk.Frame(body, bg=BG_CARD)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=label + ":", font=FONT_MONO, bg=BG_CARD, fg=TEXT_MUTED).pack(side="left")

            ent = tk.Entry(row, font=FONT_MONO_BOLD, bg=BG_CARD, fg=color,
                           readonlybackground=BG_CARD, relief="flat", bd=0,
                           justify="right", width=18,
                           highlightthickness=0,
                           selectbackground=BORDER_COLOR, selectforeground=TEXT_BRIGHT)
            ent.insert(0, "—")
            ent.config(state="readonly")
            ent.pack(side="right")
            self._calc_results[key] = ent

    def _set_res(self, key, text_val):
        ent = self._calc_results[key]
        ent.config(state="normal")
        ent.delete(0, "end")
        ent.insert(0, text_val)
        ent.config(state="readonly")

    # ── Lógica Calculadora ──
    def _parse_input(self, text):
        t = text.strip().replace("R$", "").replace("%", "").replace(" ", "")
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

    def _fmt(self, valor):
        if valor is None:
            return "—"
        return "R$ " + formatar_valor_brl(valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def _calcular_parcelado(self):
        vc = self._parse_input(self.calc_entries["parc_valor_causa"].get())
        pct_d = self._parse_input(self.calc_entries["parc_pct_desconto"].get())
        pct_e = self._parse_input(self.calc_entries["parc_pct_entrada"].get())
        n_parc = self._parse_input(self.calc_entries["parc_num_parcelas"].get())

        if vc is None or pct_d is None:
            for k in ["parc_res_desconto", "parc_res_saldo_desc", "parc_res_entrada", "parc_res_saldo_rest", "parc_res_parcela"]:
                self._set_res(k, "—")
            return

        desc_valor = (vc * pct_d / Decimal("100")).quantize(Decimal("0.01"))
        saldo_desc = vc - desc_valor

        entrada_valor = Decimal("0")
        saldo_rest = saldo_desc
        if pct_e is not None and pct_e > 0:
            entrada_valor = (saldo_desc * pct_e / Decimal("100")).quantize(Decimal("0.01"))
            saldo_rest = saldo_desc - entrada_valor

        parcela = Decimal("0")
        if n_parc is not None and n_parc > 0:
            parcela = (saldo_rest / n_parc).quantize(Decimal("0.01"))

        self._set_res("parc_res_desconto", self._fmt(desc_valor))
        self._set_res("parc_res_saldo_desc", self._fmt(saldo_desc))
        self._set_res("parc_res_entrada", self._fmt(entrada_valor))
        self._set_res("parc_res_saldo_rest", self._fmt(saldo_rest))
        self._set_res("parc_res_parcela", self._fmt(parcela))

    def _calcular_avista(self):
        vc = self._parse_input(self.calc_entries["av_valor_causa"].get())
        pct_d = self._parse_input(self.calc_entries["av_pct_desconto"].get())

        if vc is None or pct_d is None:
            self._set_res("av_res_desconto", "—")
            self._set_res("av_res_saldo", "—")
            return

        desc_valor = (vc * pct_d / Decimal("100")).quantize(Decimal("0.01"))
        saldo = vc - desc_valor

        self._set_res("av_res_desconto", self._fmt(desc_valor))
        self._set_res("av_res_saldo", self._fmt(saldo))

    # ============================================================
    # ABA 3 - DEMONSTRATIVO DE VALORES & COMPETÊNCIAS
    # ============================================================
    def _build_tab_demonstrativo(self):
        tab = tk.Frame(self._content, bg=BG_MAIN)
        self._tab_frames["demonstrativo"] = tab

        grid = tk.Frame(tab, bg=BG_MAIN)
        grid.pack(fill="both", expand=True)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)
        grid.rowconfigure(0, weight=1)

        # ── Card Esquerda (PDF / Texto do Demonstrativo) ──
        d_card = tk.Frame(grid, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR)
        d_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        d_card.rowconfigure(1, weight=1)
        d_card.columnconfigure(0, weight=1)

        d_bar = tk.Frame(d_card, bg=BG_NAV, height=36, highlightthickness=1, highlightbackground=BORDER_COLOR)
        d_bar.grid(row=0, column=0, sticky="ew")
        d_bar.pack_propagate(False)

        tk.Label(d_bar, text="demonstrativo_valores.pdf / txt", font=FONT_MONO, bg=BG_NAV, fg=ACCENT_GOLD).pack(side="left", padx=12)

        # Botão Anexar PDF/TXT
        btn_anexar = tk.Button(
            d_bar, text="📁 ANEXAR ARQUIVO (PDF/TXT)", font=FONT_MONO_BOLD,
            bg=BORDER_COLOR, fg=ACCENT_EMERALD, activebackground=BG_CARD,
            relief="flat", cursor="hand2", padx=10, bd=0, command=self._anexar_demonstrativo
        )
        btn_anexar.pack(side="right", padx=6, pady=4)

        self.txt_demo = scrolledtext.ScrolledText(
            d_card, wrap=tk.WORD, font=FONT_MONO,
            bg=BG_INPUT, fg=TEXT_DIM,
            insertbackground=ACCENT_GOLD, relief="flat",
            padx=14, pady=12, bd=0,
            selectbackground=BORDER_COLOR, selectforeground=TEXT_BRIGHT
        )
        self.txt_demo.grid(row=1, column=0, sticky="nsew", padx=1, pady=1)
        self.txt_demo.insert("1.0", PLACEHOLDER_DEMO)
        self.txt_demo.bind("<FocusIn>", self._limpar_ph_demo)
        self.txt_demo.bind("<FocusOut>", self._restaurar_ph_demo)

        btn_proc_demo = tk.Button(
            d_card, text="❯ CALCULAR SEQUÊNCIA DE COMPETÊNCIAS",
            font=FONT_MONO_BOLD, bg=BG_NAV, fg=ACCENT_GOLD,
            activebackground=BORDER_COLOR, activeforeground=ACCENT_GOLD_HOVER,
            relief="flat", cursor="hand2", pady=10, bd=0,
            command=self._processar_demo
        )
        btn_proc_demo.grid(row=2, column=0, sticky="ew")

        # ── Card Direita (Resultado & Envio para Termos) ──
        res_card = tk.Frame(grid, bg=BG_CARD, highlightthickness=1, highlightbackground=BORDER_COLOR)
        res_card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        res_card.rowconfigure(1, weight=1)
        res_card.columnconfigure(0, weight=1)

        r_bar = tk.Frame(res_card, bg=BG_NAV, height=36, highlightthickness=1, highlightbackground=BORDER_COLOR)
        r_bar.grid(row=0, column=0, sticky="ew")
        r_bar.pack_propagate(False)
        tk.Label(r_bar, text="competencias_calculadas.json", font=FONT_MONO, bg=BG_NAV, fg=ACCENT_EMERALD).pack(side="left", padx=14)

        body_res = tk.Frame(res_card, bg=BG_CARD, padx=16, pady=14)
        body_res.grid(row=1, column=0, sticky="nsew")

        # Campos Cadastrais Extraídos do Demonstrativo
        cad_fields = [
            ("demo_nome", "Nome do Titular"),
            ("demo_cpf", "CPF"),
            ("demo_matricula", "Matrícula"),
            ("demo_valor_causa", "Valor da Causa (R$)"),
            ("demo_total_meses", "Total de Meses/Parcelas"),
        ]

        for key, label in cad_fields:
            rf = tk.Frame(body_res, bg=BG_CARD)
            rf.pack(fill="x", pady=2)
            tk.Label(rf, text=label + ":", font=FONT_MONO, bg=BG_CARD, fg=TEXT_MUTED).pack(side="left")
            ent = tk.Entry(rf, font=FONT_MONO_BOLD, bg=BG_CARD, fg=TEXT_BRIGHT,
                           readonlybackground=BG_CARD, relief="flat", bd=0, justify="right", width=22,
                           highlightthickness=0, selectbackground=BORDER_COLOR)
            ent.insert(0, "—")
            ent.config(state="readonly")
            ent.pack(side="right")
            self.demo_entries[key] = ent

        tk.Frame(body_res, bg=BORDER_COLOR, height=1).pack(fill="x", pady=10)

        # Campo de Resultado Final das Competências
        tk.Label(body_res, text="📌 Competências Negociadas (Formato do Termo):", font=FONT_MONO_BOLD, bg=BG_CARD, fg=ACCENT_GOLD).pack(anchor="w", pady=(0, 4))
        
        self.txt_comp_res = scrolledtext.ScrolledText(
            body_res, wrap=tk.WORD, font=FONT_MONO_BOLD, height=3,
            bg=BG_INPUT, fg=ACCENT_EMERALD, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER_COLOR,
            selectbackground=BORDER_COLOR, selectforeground=TEXT_BRIGHT
        )
        self.txt_comp_res.pack(fill="x", pady=(0, 10))

        tk.Label(body_res, text="📊 Detalhamento das Sequências & Lacunas:", font=FONT_MONO, bg=BG_CARD, fg=TEXT_MUTED).pack(anchor="w", pady=(0, 4))
        
        self.txt_detalhes_comp = scrolledtext.ScrolledText(
            body_res, wrap=tk.WORD, font=FONT_MONO, height=5,
            bg=BG_INPUT, fg=TEXT_BRIGHT, relief="flat", bd=0,
            highlightthickness=1, highlightbackground=BORDER_COLOR,
            selectbackground=BORDER_COLOR
        )
        self.txt_detalhes_comp.pack(fill="both", expand=True)

        # Botão Enviar para Gerador de Termos
        btn_enviar_gerador = tk.Button(
            res_card, text="[ ⚖ ENVIAR DADOS PARA O GERADOR DE TERMOS ]",
            font=FONT_MONO_BOLD, bg=ACCENT_GOLD, fg=BG_MAIN,
            activebackground=ACCENT_GOLD_HOVER, activeforeground=BG_MAIN,
            relief="flat", cursor="hand2", pady=10, bd=0,
            command=self._enviar_demo_para_gerador
        )
        btn_enviar_gerador.grid(row=2, column=0, sticky="ew")

    def _limpar_ph_demo(self, _e):
        if self.txt_demo.get("1.0", "end-1c") == PLACEHOLDER_DEMO:
            self.txt_demo.delete("1.0", "end")
            self.txt_demo.config(fg=TEXT_BRIGHT)

    def _restaurar_ph_demo(self, _e):
        if not self.txt_demo.get("1.0", "end-1c").strip():
            self.txt_demo.insert("1.0", PLACEHOLDER_DEMO)
            self.txt_demo.config(fg=TEXT_DIM)

    def _anexar_demonstrativo(self):
        caminho = filedialog.askopenfilename(
            title="Selecione o Demonstrativo",
            filetypes=[("Arquivos suportados", "*.pdf;*.txt"), ("PDF", "*.pdf"), ("Texto", "*.txt")]
        )
        if not caminho:
            return

        try:
            texto_extraido = ""
            if caminho.lower().endswith(".pdf"):
                with pdfplumber.open(caminho) as pdf:
                    for page in pdf.pages:
                        txt_pag = page.extract_text()
                        if txt_pag:
                            texto_extraido += txt_pag + "\n"
            else:
                with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
                    texto_extraido = f.read()

            if texto_extraido:
                self.txt_demo.delete("1.0", "end")
                self.txt_demo.config(fg=TEXT_BRIGHT)
                self.txt_demo.insert("1.0", texto_extraido)
                self._processar_demo()
                messagebox.showinfo("Sucesso", f"Demonstrativo carregado com sucesso!\n{os.path.basename(caminho)}")
            else:
                messagebox.showwarning("Aviso", "Não foi possível extrair texto do arquivo.")
        except Exception as e:
            messagebox.showerror("Erro ao ler arquivo", str(e))

    def _set_demo_entry(self, key, val):
        ent = self.demo_entries[key]
        ent.config(state="normal")
        ent.delete(0, "end")
        ent.insert(0, val if val else "—")
        ent.config(state="readonly")

    def _processar_demo(self):
        texto = self.txt_demo.get("1.0", "end-1c").strip()
        if not texto or texto == PLACEHOLDER_DEMO:
            messagebox.showwarning("Aviso", "Cole o texto ou anexe o arquivo PDF do Demonstrativo.")
            return

        res = processar_demonstrativo(texto)

        self._set_demo_entry("demo_nome", res.get("nome", ""))
        self._set_demo_entry("demo_cpf", res.get("cpf", ""))
        self._set_demo_entry("demo_matricula", res.get("matricula", ""))
        self._set_demo_entry("demo_valor_causa", res.get("valor_causa", ""))
        self._set_demo_entry("demo_total_meses", str(res.get("total_meses", 0)))

        self.txt_comp_res.config(state="normal")
        self.txt_comp_res.delete("1.0", "end")
        self.txt_comp_res.insert("1.0", res.get("competencias", ""))
        self.txt_comp_res.config(state="normal")

        self.txt_detalhes_comp.config(state="normal")
        self.txt_detalhes_comp.delete("1.0", "end")
        if res.get("grupos_detalhados"):
            self.txt_detalhes_comp.insert("1.0", "\n".join(res["grupos_detalhados"]))
        else:
            self.txt_detalhes_comp.insert("1.0", "Nenhum período identificado.")

        self.dados_demo_atual = res

    def _enviar_demo_para_gerador(self):
        if not hasattr(self, "dados_demo_atual") or not self.dados_demo_atual.get("competencias"):
            self._processar_demo()
            if not hasattr(self, "dados_demo_atual") or not self.dados_demo_atual.get("competencias"):
                messagebox.showwarning("Aviso", "Processe o demonstrativo primeiro.")
                return

        res = self.dados_demo_atual

        # Preenche os campos no Gerador de Termos (Aba 1)
        if res.get("nome"):
            self.entries["nome"].delete(0, "end")
            self.entries["nome"].insert(0, res["nome"])

        if res.get("cpf"):
            self.entries["cpf"].delete(0, "end")
            self.entries["cpf"].insert(0, res["cpf"])

        if res.get("matricula"):
            self.entries["matricula"].delete(0, "end")
            self.entries["matricula"].insert(0, res["matricula"])

        if res.get("valor_causa"):
            self.entries["valor_original"].delete(0, "end")
            self.entries["valor_original"].insert(0, res["valor_causa"])

        if res.get("competencias"):
            self.entries["competencias"].delete(0, "end")
            self.entries["competencias"].insert(0, res["competencias"])

        # Alterna para a Aba 1 Gerador
        self._switch_tab("gerador")
        self.status_var.set("// ✅ Dados do Demonstrativo importados para a revisão do Termo!")
        self.status_lbl.config(fg=ACCENT_EMERALD)
        messagebox.showinfo("Sucesso", "Dados do Demonstrativo (Nome, CPF, Matrícula, Valor e Competências) enviados com sucesso para o Gerador de Termos!")

    # ============================================================
    # EVENTOS DO GERADOR
    # ============================================================
    def _limpar_ph(self, _e):
        if self.txt.get("1.0", "end-1c") == PLACEHOLDER:
            self.txt.delete("1.0", "end")
            self.txt.config(fg=TEXT_BRIGHT)

    def _restaurar_ph(self, _e):
        if not self.txt.get("1.0", "end-1c").strip():
            self.txt.insert("1.0", PLACEHOLDER)
            self.txt.config(fg=TEXT_DIM)

    def _reset_campos(self):
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", PLACEHOLDER)
        self.txt.config(fg=TEXT_DIM)
        for entry in self.entries.values():
            entry.delete(0, "end")
            entry.config(highlightbackground=BORDER_COLOR, highlightcolor=ACCENT_GOLD)
        self.status_var.set("// Aldrigues Cândido Advocacia — Campos limpos.")
        self.status_lbl.config(fg=TEXT_MUTED)

    def _interpretar(self):
        msg = self.txt.get("1.0", "end-1c").strip()
        if not msg or msg == PLACEHOLDER:
            messagebox.showwarning("Aviso", "Cole a mensagem primeiro.")
            return

        campos = interpretar_mensagem(msg)

        for chave, entry in self.entries.items():
            entry.delete(0, "end")
            val = campos.get(chave, "")
            entry.insert(0, val)
            entry.xview_moveto(0)
            if not val and chave in ("nome", "cpf", "valor_acordo"):
                entry.config(highlightbackground=COLOR_RED, highlightcolor=COLOR_RED)
            else:
                entry.config(highlightbackground=BORDER_COLOR, highlightcolor=ACCENT_GOLD)

        vazios = [lab for ch, lab in CAMPOS_REVISAO if not campos.get(ch)]
        if vazios:
            self.status_var.set(f"// ⚠️ Campos ausentes: {', '.join(vazios)}")
            self.status_lbl.config(fg=ACCENT_GOLD)
        else:
            self.status_var.set("// ✅ Sucesso: Todos os campos foram interpretados com sucesso!")
            self.status_lbl.config(fg=ACCENT_EMERALD)

    def _gerar(self, tipo="parcelado"):
        modelo = MODELO_AVISTA_PATH if tipo == "avista" else MODELO_PATH
        if not os.path.exists(modelo):
            messagebox.showerror("Erro", f"Arquivo modelo não encontrado: {modelo}")
            return

        campos = {ch: entry.get().strip() for ch, entry in self.entries.items()}
        if not campos.get("nome"):
            messagebox.showwarning("Aviso", "O campo 'Nome / Cliente' é obrigatório.")
            return

        tipo_label = "PARCELADO" if tipo == "parcelado" else "À VISTA"
        self.status_var.set(f"// Gerando minuta de termo de acordo [{tipo_label}]...")
        self.status_lbl.config(fg=ACCENT_CYAN)
        self.btn_gerar_parcelado.config(state="disabled")
        self.btn_gerar_avista.config(state="disabled")
        self.update()

        try:
            caminho, dados = gerar_documento(campos, modelo)
            self.status_var.set(f"// ✓ Documento jurídico gerado com sucesso: {caminho}")
            self.status_lbl.config(fg=ACCENT_EMERALD)
            resp = messagebox.askyesno(
                "Termo Gerado",
                f"Termo de acordo ({tipo_label}) gerado com sucesso!\n\n"
                f"Cliente: {dados['nome_cliente']}\n"
                f"CPF: {dados['cpf_cliente']}\n\n"
                f"Deseja abrir o arquivo Word agora?"
            )
            if resp:
                os.startfile(os.path.abspath(caminho))
            self._reset_campos()
        except Exception as e:
            self.status_var.set(f"// ❌ Erro ao gerar: {e}")
            self.status_lbl.config(fg=COLOR_RED)
            messagebox.showerror("Erro", str(e))
        finally:
            self.btn_gerar_parcelado.config(state="normal")
            self.btn_gerar_avista.config(state="normal")


if __name__ == "__main__":
    app = App()
    app.mainloop()
