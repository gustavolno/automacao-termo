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
    """Converte um valor numérico para string monetária por extenso em português."""
    texto = num2words(valor, lang="pt_BR", to="currency")
    if texto.startswith("mil"):
        texto = "um " + texto
    return texto


def formatar_e_calcular(campos: dict) -> dict:
    """
    Recebe os campos da interface de revisão (todos strings) e formata para o docxtpl.
    """
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
# PALETA DE CORES
# ============================================================
BG_DARK = "#0F0F12"
BG_CARD = "#1A1A22"
BG_CARD_ALT = "#20202A"
BG_INPUT = "#16161E"
BORDER = "#2A2A35"
ACCENT = "#D4AF37"
ACCENT_HOVER = "#E8C84A"
ACCENT_DIM = "#8B7530"
TEXT_PRIMARY = "#F0EDE6"
TEXT_SECONDARY = "#8A8A96"
TEXT_MUTED = "#5A5A66"
GREEN = "#3DDC84"
RED = "#FF5252"
ORANGE = "#FF9800"
BLUE_ACCENT = "#5B9BD5"

CAMPOS_REVISAO = [
    ("Nome / Cliente", "nome"),
    ("CPF", "cpf"),
    ("Processo Judicial", "processo"),
    ("Matrícula", "matricula"),
    ("Telefone / WhatsApp", "telefone"),
    ("E-mail", "email"),
    ("Endereço", "endereco"),
    ("CEP", "cep"),
    ("Valor Original da Dívida", "valor_original"),
    ("Valor do Acordo (c/ desconto)", "valor_acordo"),
    ("Valor da Entrada", "valor_entrada"),
    ("Vencimento da Entrada", "vencimento_entrada"),
    ("Qtd. de Parcelas", "quantidade_parcelas"),
    ("Valor da Parcela", "valor_parcela"),
    ("Início das Parcelas", "inicio_parcelas"),
    ("Dia de Vencimento Mensal", "dia_parcela"),
    ("Competências", "competencias"),
]

PLACEHOLDER = (
    "Cole aqui a mensagem recebida exatamente como chegou...\n\n"
    "O sistema interpretará automaticamente e exibirá\n"
    "todos os campos na área de revisão à direita."
)


# ============================================================
# CLASSE PRINCIPAL
# ============================================================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gerador de Termos de Acordo — Aldrigues Cândido Advocacia")
        self.configure(bg=BG_DARK)
        self.resizable(True, True)
        self.minsize(960, 720)
        self.entries = {}
        self.calc_entries = {}

        # Estilo ttk
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self._configure_styles()
        self._build_ui()
        self.after(50, self._centralizar)

    def _centralizar(self):
        self.update_idletasks()
        w, h = 1050, 780
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _configure_styles(self):
        s = self.style
        s.configure("TNotebook", background=BG_DARK, borderwidth=0)
        s.configure("TNotebook.Tab", background=BG_CARD, foreground=TEXT_SECONDARY,
                     padding=[18, 8], font=("Segoe UI", 10, "bold"))
        s.map("TNotebook.Tab",
              background=[("selected", BG_DARK)],
              foreground=[("selected", ACCENT)])
        s.configure("TFrame", background=BG_DARK)
        s.configure("Card.TFrame", background=BG_CARD)
        s.configure("TLabel", background=BG_DARK, foreground=TEXT_PRIMARY, font=("Segoe UI", 9))
        s.configure("Header.TLabel", background=BG_DARK, foreground=ACCENT, font=("Segoe UI", 10, "bold"))
        s.configure("Muted.TLabel", background=BG_DARK, foreground=TEXT_MUTED, font=("Segoe UI", 8))
        s.configure("Title.TLabel", background=BG_CARD, foreground=ACCENT, font=("Georgia", 16, "bold"))
        s.configure("Subtitle.TLabel", background=BG_CARD, foreground=TEXT_MUTED, font=("Segoe UI", 8))
        s.configure("CalcCard.TLabel", background=BG_CARD, foreground=TEXT_PRIMARY, font=("Segoe UI", 9))
        s.configure("CalcHeader.TLabel", background=BG_CARD, foreground=ACCENT, font=("Segoe UI", 11, "bold"))
        s.configure("CalcResult.TLabel", background=BG_CARD, foreground=GREEN, font=("Consolas", 12, "bold"))
        s.configure("CalcResultAlt.TLabel", background=BG_CARD, foreground=BLUE_ACCENT, font=("Consolas", 11, "bold"))

    def _build_ui(self):
        # ── CABEÇALHO ──
        hdr = tk.Frame(self, bg=BG_CARD, pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚖  GERADOR DE TERMOS DE ACORDO",
                 font=("Georgia", 16, "bold"), bg=BG_CARD, fg=ACCENT).pack()
        tk.Label(hdr, text="Aldrigues Cândido Advocacia — Sistema Integrado",
                 font=("Segoe UI", 8), bg=BG_CARD, fg=TEXT_MUTED).pack()

        # Linha dourada
        accent_line = tk.Canvas(self, height=3, bg=BG_DARK, highlightthickness=0)
        accent_line.pack(fill="x")
        accent_line.create_rectangle(0, 0, 2000, 3, fill=ACCENT, outline="")

        # ── NOTEBOOK (ABAS) ──
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=0, pady=0)

        # Aba 1: Gerador de Termos
        self.tab_gerador = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(self.tab_gerador, text="  📄  GERADOR DE TERMOS  ")

        # Aba 2: Calculadora
        self.tab_calculadora = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(self.tab_calculadora, text="  🧮  CALCULADORA DE NEGOCIAÇÃO  ")

        self._build_tab_gerador()
        self._build_tab_calculadora()

    # ============================================================
    # ABA 1 - GERADOR DE TERMOS
    # ============================================================
    def _build_tab_gerador(self):
        tab = self.tab_gerador

        main = tk.Frame(tab, bg=BG_DARK)
        main.pack(fill="both", expand=True, padx=16, pady=10)
        main.columnconfigure(0, weight=2)
        main.columnconfigure(1, weight=3)
        main.rowconfigure(0, weight=1)

        # ── Coluna Esquerda: Texto bruto ──
        esq = tk.Frame(main, bg=BG_DARK)
        esq.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        esq.rowconfigure(1, weight=1)
        esq.columnconfigure(0, weight=1)

        ttk.Label(esq, text="① COLE A MENSAGEM BRUTA", style="Header.TLabel").grid(
            row=0, column=0, sticky="ew", pady=(0, 6))

        frame_txt = tk.Frame(esq, bg=BORDER, padx=1, pady=1)
        frame_txt.grid(row=1, column=0, sticky="nsew")

        self.txt = scrolledtext.ScrolledText(
            frame_txt, wrap=tk.WORD, font=("Consolas", 10),
            bg=BG_INPUT, fg=TEXT_MUTED,
            insertbackground=ACCENT, relief="flat",
            padx=12, pady=10, selectbackground=ACCENT_DIM,
            selectforeground=TEXT_PRIMARY
        )
        self.txt.pack(fill="both", expand=True)
        self.txt.insert("1.0", PLACEHOLDER)
        self.txt.bind("<FocusIn>", self._limpar_ph)
        self.txt.bind("<FocusOut>", self._restaurar_ph)

        self.btn_interpretar = tk.Button(
            esq, text="🔍  INTERPRETAR MENSAGEM",
            font=("Segoe UI", 10, "bold"),
            bg=BORDER, fg=ACCENT,
            activebackground="#3A3A45", activeforeground=ACCENT_HOVER,
            relief="flat", cursor="hand2", pady=10,
            command=self._interpretar
        )
        self.btn_interpretar.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.btn_interpretar.bind("<Enter>", lambda e: self.btn_interpretar.config(bg="#3A3A45"))
        self.btn_interpretar.bind("<Leave>", lambda e: self.btn_interpretar.config(bg=BORDER))

        # ── Coluna Direita: Campos de revisão ──
        dir_ = tk.Frame(main, bg=BG_DARK)
        dir_.grid(row=0, column=1, sticky="nsew")
        dir_.columnconfigure(0, weight=1)
        dir_.rowconfigure(1, weight=1)

        ttk.Label(dir_, text="② REVISE OS CAMPOS EXTRAÍDOS", style="Header.TLabel").grid(
            row=0, column=0, sticky="ew", pady=(0, 6))

        canvas = tk.Canvas(dir_, bg=BG_DARK, highlightthickness=0)
        scrollbar = tk.Scrollbar(dir_, orient="vertical", command=canvas.yview,
                                 bg=BG_DARK, troughcolor=BG_CARD, activebackground=ACCENT)
        scroll_frame = tk.Frame(canvas, bg=BG_DARK)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.grid(row=1, column=0, sticky="nsew")
        scrollbar.grid(row=1, column=1, sticky="ns")

        scroll_frame.columnconfigure(1, weight=1)

        for i, (label, chave) in enumerate(CAMPOS_REVISAO):
            lbl = tk.Label(scroll_frame, text=label + ":", font=("Segoe UI", 8, "bold"),
                           bg=BG_DARK, fg=TEXT_SECONDARY, anchor="e")
            lbl.grid(row=i, column=0, sticky="e", padx=(0, 8), pady=3)

            ent = tk.Entry(scroll_frame, font=("Segoe UI", 10),
                           bg=BG_INPUT, fg=TEXT_PRIMARY,
                           insertbackground=ACCENT,
                           relief="flat", bd=0,
                           highlightthickness=1,
                           highlightbackground=BORDER,
                           highlightcolor=ACCENT)
            ent.grid(row=i, column=1, sticky="ew", pady=3, ipady=4)
            self.entries[chave] = ent

        # ── Rodapé com status e botões ──
        rodape = tk.Frame(tab, bg=BG_DARK, padx=16, pady=4)
        rodape.pack(fill="x")

        self.status_var = tk.StringVar(value="Aguardando mensagem...")
        tk.Label(rodape, textvariable=self.status_var,
                 font=("Segoe UI", 8), bg=BG_DARK, fg=TEXT_MUTED,
                 anchor="w").pack(fill="x", pady=(0, 4))

        btn_frame = tk.Frame(tab, bg=BG_DARK, padx=16, pady=8)
        btn_frame.pack(fill="x")
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=1)

        self.btn_gerar_parcelado = tk.Button(
            btn_frame, text="📋  GERAR PARCELADO",
            font=("Segoe UI", 10, "bold"),
            bg=ACCENT, fg="#0F0F12",
            activebackground=ACCENT_HOVER, activeforeground="#0F0F12",
            relief="flat", cursor="hand2", padx=12, pady=10,
            command=lambda: self._gerar(tipo="parcelado")
        )
        self.btn_gerar_parcelado.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.btn_gerar_parcelado.bind("<Enter>", lambda e: self.btn_gerar_parcelado.config(bg=ACCENT_HOVER))
        self.btn_gerar_parcelado.bind("<Leave>", lambda e: self.btn_gerar_parcelado.config(bg=ACCENT))

        self.btn_gerar_avista = tk.Button(
            btn_frame, text="💰  GERAR À VISTA",
            font=("Segoe UI", 10, "bold"),
            bg=ACCENT, fg="#0F0F12",
            activebackground=ACCENT_HOVER, activeforeground="#0F0F12",
            relief="flat", cursor="hand2", padx=12, pady=10,
            command=lambda: self._gerar(tipo="avista")
        )
        self.btn_gerar_avista.grid(row=0, column=1, sticky="ew", padx=(4, 4))
        self.btn_gerar_avista.bind("<Enter>", lambda e: self.btn_gerar_avista.config(bg=ACCENT_HOVER))
        self.btn_gerar_avista.bind("<Leave>", lambda e: self.btn_gerar_avista.config(bg=ACCENT))

        self.btn_reset = tk.Button(
            btn_frame, text="🔄  RESETAR",
            font=("Segoe UI", 10, "bold"),
            bg=BORDER, fg=TEXT_SECONDARY,
            activebackground="#4A4A55", activeforeground=TEXT_PRIMARY,
            relief="flat", cursor="hand2", padx=12, pady=10,
            command=self._reset_campos
        )
        self.btn_reset.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        self.btn_reset.bind("<Enter>", lambda e: self.btn_reset.config(bg="#4A4A55"))
        self.btn_reset.bind("<Leave>", lambda e: self.btn_reset.config(bg=BORDER))

    # ============================================================
    # ABA 2 - CALCULADORA DE NEGOCIAÇÃO
    # ============================================================
    def _build_tab_calculadora(self):
        tab = self.tab_calculadora

        # Frame rolável
        canvas = tk.Canvas(tab, bg=BG_DARK, highlightthickness=0)
        scrollbar = tk.Scrollbar(tab, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=BG_DARK)
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Vincular scroll do mouse
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        container = tk.Frame(scroll_frame, bg=BG_DARK, padx=30, pady=20)
        container.pack(fill="both", expand=True)

        # ── CÁLCULO PARCELADO ──
        self._build_calc_parcelado(container)

        # Separador
        tk.Frame(container, bg=BORDER, height=1).pack(fill="x", pady=20)

        # ── CÁLCULO À VISTA ──
        self._build_calc_avista(container)

    def _build_calc_parcelado(self, parent):
        card = tk.Frame(parent, bg=BG_CARD, padx=20, pady=16)
        card.pack(fill="x", pady=(0, 5))

        # Header
        header = tk.Frame(card, bg=BG_CARD)
        header.pack(fill="x", pady=(0, 14))
        tk.Label(header, text="📊  CÁLCULO PARCELADO", font=("Segoe UI", 13, "bold"),
                 bg=BG_CARD, fg=ACCENT).pack(side="left")

        # Grid de inputs
        grid = tk.Frame(card, bg=BG_CARD)
        grid.pack(fill="x")

        campos_parc = [
            ("Valor da Causa:", "parc_valor_causa"),
            ("% Desconto:", "parc_pct_desconto"),
            ("% Entrada:", "parc_pct_entrada"),
            ("Nº de Parcelas:", "parc_num_parcelas"),
        ]

        for i, (label, key) in enumerate(campos_parc):
            col = i % 4
            row = i // 4
            f = tk.Frame(grid, bg=BG_CARD)
            f.grid(row=row, column=col, padx=6, pady=4, sticky="ew")
            grid.columnconfigure(col, weight=1)

            tk.Label(f, text=label, font=("Segoe UI", 8, "bold"),
                     bg=BG_CARD, fg=TEXT_SECONDARY).pack(anchor="w")
            ent = tk.Entry(f, font=("Segoe UI", 11), bg=BG_INPUT, fg=TEXT_PRIMARY,
                           insertbackground=ACCENT, relief="flat", bd=0,
                           highlightthickness=1, highlightbackground=BORDER,
                           highlightcolor=ACCENT)
            ent.pack(fill="x", ipady=5)
            self.calc_entries[key] = ent

        # Botão calcular
        btn_calc = tk.Button(card, text="⚡  CALCULAR",
                             font=("Segoe UI", 10, "bold"),
                             bg=ACCENT, fg="#0F0F12",
                             activebackground=ACCENT_HOVER,
                             relief="flat", cursor="hand2", pady=8,
                             command=self._calcular_parcelado)
        btn_calc.pack(fill="x", pady=(12, 8))
        btn_calc.bind("<Enter>", lambda e: btn_calc.config(bg=ACCENT_HOVER))
        btn_calc.bind("<Leave>", lambda e: btn_calc.config(bg=ACCENT))

        # Resultados
        self.parc_result_frame = tk.Frame(card, bg=BG_CARD)
        self.parc_result_frame.pack(fill="x")

        self.parc_results = {}
        result_items = [
            ("Valor de Desconto:", "parc_res_desconto", GREEN),
            ("Saldo Após Desconto:", "parc_res_saldo_desc", TEXT_PRIMARY),
            ("Valor da Entrada:", "parc_res_entrada", ORANGE),
            ("Saldo Restante:", "parc_res_saldo_rest", BLUE_ACCENT),
            ("Parcela Mensal:", "parc_res_parcela", GREEN),
        ]
        for label, key, color in result_items:
            rf = tk.Frame(self.parc_result_frame, bg=BG_CARD)
            rf.pack(fill="x", pady=2)
            tk.Label(rf, text=label, font=("Segoe UI", 9),
                     bg=BG_CARD, fg=TEXT_SECONDARY).pack(side="left")
            lbl = tk.Label(rf, text="—", font=("Consolas", 11, "bold"),
                           bg=BG_CARD, fg=color)
            lbl.pack(side="right")
            self.parc_results[key] = lbl

    def _build_calc_avista(self, parent):
        card = tk.Frame(parent, bg=BG_CARD, padx=20, pady=16)
        card.pack(fill="x", pady=(5, 0))

        header = tk.Frame(card, bg=BG_CARD)
        header.pack(fill="x", pady=(0, 14))
        tk.Label(header, text="💵  CÁLCULO À VISTA", font=("Segoe UI", 13, "bold"),
                 bg=BG_CARD, fg=ACCENT).pack(side="left")

        grid = tk.Frame(card, bg=BG_CARD)
        grid.pack(fill="x")

        campos_av = [
            ("Valor da Causa:", "av_valor_causa"),
            ("% Desconto:", "av_pct_desconto"),
        ]

        for i, (label, key) in enumerate(campos_av):
            f = tk.Frame(grid, bg=BG_CARD)
            f.grid(row=0, column=i, padx=6, pady=4, sticky="ew")
            grid.columnconfigure(i, weight=1)

            tk.Label(f, text=label, font=("Segoe UI", 8, "bold"),
                     bg=BG_CARD, fg=TEXT_SECONDARY).pack(anchor="w")
            ent = tk.Entry(f, font=("Segoe UI", 11), bg=BG_INPUT, fg=TEXT_PRIMARY,
                           insertbackground=ACCENT, relief="flat", bd=0,
                           highlightthickness=1, highlightbackground=BORDER,
                           highlightcolor=ACCENT)
            ent.pack(fill="x", ipady=5)
            self.calc_entries[key] = ent

        btn_calc = tk.Button(card, text="⚡  CALCULAR",
                             font=("Segoe UI", 10, "bold"),
                             bg=ACCENT, fg="#0F0F12",
                             activebackground=ACCENT_HOVER,
                             relief="flat", cursor="hand2", pady=8,
                             command=self._calcular_avista)
        btn_calc.pack(fill="x", pady=(12, 8))
        btn_calc.bind("<Enter>", lambda e: btn_calc.config(bg=ACCENT_HOVER))
        btn_calc.bind("<Leave>", lambda e: btn_calc.config(bg=ACCENT))

        self.av_result_frame = tk.Frame(card, bg=BG_CARD)
        self.av_result_frame.pack(fill="x")

        self.av_results = {}
        result_items = [
            ("Valor de Desconto:", "av_res_desconto", GREEN),
            ("Saldo Restante:", "av_res_saldo", BLUE_ACCENT),
        ]
        for label, key, color in result_items:
            rf = tk.Frame(self.av_result_frame, bg=BG_CARD)
            rf.pack(fill="x", pady=2)
            tk.Label(rf, text=label, font=("Segoe UI", 9),
                     bg=BG_CARD, fg=TEXT_SECONDARY).pack(side="left")
            lbl = tk.Label(rf, text="—", font=("Consolas", 11, "bold"),
                           bg=BG_CARD, fg=color)
            lbl.pack(side="right")
            self.av_results[key] = lbl

    # ============================================================
    # LÓGICA DA CALCULADORA
    # ============================================================
    def _parse_input(self, text):
        """Parse um valor de entrada (aceita R$ 1.234,56 ou 1234.56 ou 15 etc)."""
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

    def _fmt(self, valor):
        """Formata Decimal para R$ X.XXX,XX"""
        if valor is None:
            return "—"
        return "R$ " + formatar_valor_brl(valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    def _calcular_parcelado(self):
        vc = self._parse_input(self.calc_entries["parc_valor_causa"].get())
        pct_d = self._parse_input(self.calc_entries["parc_pct_desconto"].get())
        pct_e = self._parse_input(self.calc_entries["parc_pct_entrada"].get())
        n_parc = self._parse_input(self.calc_entries["parc_num_parcelas"].get())

        if vc is None or pct_d is None:
            messagebox.showwarning("Atenção", "Preencha ao menos Valor da Causa e % Desconto.")
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

        self.parc_results["parc_res_desconto"].config(text=self._fmt(desc_valor))
        self.parc_results["parc_res_saldo_desc"].config(text=self._fmt(saldo_desc))
        self.parc_results["parc_res_entrada"].config(text=self._fmt(entrada_valor))
        self.parc_results["parc_res_saldo_rest"].config(text=self._fmt(saldo_rest))
        self.parc_results["parc_res_parcela"].config(text=self._fmt(parcela))

    def _calcular_avista(self):
        vc = self._parse_input(self.calc_entries["av_valor_causa"].get())
        pct_d = self._parse_input(self.calc_entries["av_pct_desconto"].get())

        if vc is None or pct_d is None:
            messagebox.showwarning("Atenção", "Preencha Valor da Causa e % Desconto.")
            return

        desc_valor = (vc * pct_d / Decimal("100")).quantize(Decimal("0.01"))
        saldo = vc - desc_valor

        self.av_results["av_res_desconto"].config(text=self._fmt(desc_valor))
        self.av_results["av_res_saldo"].config(text=self._fmt(saldo))

    # ============================================================
    # EVENTOS DO GERADOR
    # ============================================================
    def _limpar_ph(self, _e):
        if self.txt.get("1.0", "end-1c") == PLACEHOLDER:
            self.txt.delete("1.0", "end")
            self.txt.config(fg=TEXT_PRIMARY)

    def _restaurar_ph(self, _e):
        if not self.txt.get("1.0", "end-1c").strip():
            self.txt.insert("1.0", PLACEHOLDER)
            self.txt.config(fg=TEXT_MUTED)

    def _reset_campos(self):
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", PLACEHOLDER)
        self.txt.config(fg=TEXT_MUTED)
        for entry in self.entries.values():
            entry.delete(0, "end")
            entry.config(highlightbackground=BORDER, highlightcolor=ACCENT)
        self._set_status("Aguardando mensagem...", TEXT_MUTED)

    def _interpretar(self):
        msg = self.txt.get("1.0", "end-1c").strip()
        if not msg or msg == PLACEHOLDER.strip():
            messagebox.showwarning("Atenção", "Cole a mensagem primeiro.")
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
                entry.config(highlightbackground=BORDER, highlightcolor=ACCENT)

        vazios = [lab for lab, ch in CAMPOS_REVISAO if not campos.get(ch)]
        if vazios:
            self._set_status(f"⚠ Campos não identificados: {', '.join(vazios)}", ORANGE)
        else:
            self._set_status("✅ Todos os campos foram interpretados com sucesso!", GREEN)

    def _gerar(self, tipo="parcelado"):
        modelo_usado = MODELO_AVISTA_PATH if tipo == "avista" else MODELO_PATH
        if not os.path.exists(modelo_usado):
            messagebox.showerror("Erro", f"Arquivo modelo não encontrado: {modelo_usado}")
            return

        campos = {ch: entry.get().strip() for ch, entry in self.entries.items()}

        if not campos.get("nome"):
            messagebox.showwarning("Atenção", "O campo 'Nome / Cliente' é obrigatório.")
            return

        tipo_label = "Parcelado" if tipo == "parcelado" else "À Vista"
        self._set_status(f"📄 Gerando documento ({tipo_label})...", ACCENT)
        self.btn_gerar_parcelado.config(state="disabled")
        self.btn_gerar_avista.config(state="disabled")
        self.update()

        try:
            caminho, dados = gerar_documento(campos, modelo_usado)
            self._set_status(f"✓ Documento gerado: {caminho}", GREEN)
            resp = messagebox.askyesno(
                "Sucesso!",
                f"Termo de acordo ({tipo_label}) gerado com sucesso!\n\n"
                f"Cliente: {dados['nome_cliente']}\n"
                f"CPF: {dados['cpf_cliente']}\n\n"
                f"Deseja abrir o documento agora?"
            )
            if resp:
                os.startfile(os.path.abspath(caminho))
            self._reset_campos()
        except Exception as e:
            self._set_status(f"❌ Erro ao gerar: {e}", RED)
            messagebox.showerror("Erro ao gerar termo", str(e))
        finally:
            self.btn_gerar_parcelado.config(state="normal")
            self.btn_gerar_avista.config(state="normal")

    def _set_status(self, msg, cor=TEXT_MUTED):
        self.status_var.set(msg)
        self.update_idletasks()


if __name__ == "__main__":
    app = App()
    app.mainloop()
