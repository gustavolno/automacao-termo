import re
import os
from datetime import datetime
from docxtpl import DocxTemplate
from num2words import num2words
import tkinter as tk
from tkinter import messagebox, scrolledtext

# ============================================================
# CONFIGURAÇÕES
# ============================================================
MODELO_PATH = "MODELO.docx"
PASTA_SAIDA = "Termos Gerados"

# ============================================================
# LÓGICA DE NEGÓCIO
# ============================================================

def valor_por_extenso(valor):
    texto = num2words(valor, lang="pt_BR", to="currency")
    # Corrige: num2words retorna 'mil' mas o correto jurídico é 'um mil'
    if texto.startswith('mil'):
        texto = 'um ' + texto
    return texto

def parse_monetario(texto):
    if not texto:
        return None
    texto = re.sub(r'[^\d,.]', '', texto)
    texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except:
        return None

def processar_competencias(texto):
    padrao_data = r"\b(\d{2}/\d{2}/\d{4}|\d{2}/\d{4})\b"
    encontradas = re.findall(padrao_data, texto)
    if not encontradas:
        return ""
    datas_obj = []
    for d in encontradas:
        try:
            if len(d) == 7:
                dt = datetime.strptime(d, "%m/%Y")
            else:
                dt = datetime.strptime(d, "%d/%m/%Y").replace(day=1)
            if dt not in datas_obj:
                datas_obj.append(dt)
        except:
            pass
    datas_obj.sort()
    if not datas_obj:
        return ""
    grupos, grupo_atual = [], [datas_obj[0]]
    for i in range(1, len(datas_obj)):
        atual, anterior = datas_obj[i], datas_obj[i-1]
        ano_esp, mes_esp = anterior.year, anterior.month + 1
        if mes_esp > 12:
            mes_esp = 1; ano_esp += 1
        if atual.year == ano_esp and atual.month == mes_esp:
            grupo_atual.append(atual)
        else:
            grupos.append(grupo_atual); grupo_atual = [atual]
    grupos.append(grupo_atual)
    partes = []
    for g in grupos:
        if len(g) == 1:
            partes.append(g[0].strftime("%m/%Y"))
        else:
            partes.append(f"{g[0].strftime('%m/%Y')} a {g[-1].strftime('%m/%Y')}")
    return ", ".join(partes[:-1]) + " e " + partes[-1] if len(partes) > 1 else partes[0]

def parse_whatsapp_message(texto):
    """
    Parser robusto: tenta múltiplos padrões de campo para capturar
    diferentes formatos usados pelos atendentes.
    """
    m = lambda pattern: re.search(pattern, texto, re.IGNORECASE)

    # ── Nome / Cliente ──────────────────────────────
    match_nome = m(r"(?:nome|cliente)\s*:?\s*([A-ZÀ-Ÿa-zà-ÿ\s]+?)(?:\n|CPF|$)")
    nome = match_nome.group(1).strip().upper() if match_nome else ""

    # ── CPF ──────────────────────────────────────
    match_cpf = re.search(r"(\d{3}[\.]?\d{3}[\.]?\d{3}[-]?\d{2})", texto)
    cpf = match_cpf.group(1).strip() if match_cpf else ""

    # ── Processo Judicial ────────────────────────────
    match_proc = m(r"processo\s+(?:judicial|n[\u00ba\u00b0]?\.?)\s*:?\s*([^\n]+)")
    processo = match_proc.group(1).strip() if match_proc else ""

    # ── Matrícula ───────────────────────────────────
    match_mat = m(r"matr[\u00ed\u0069]cula\s*:?\s*n?[\u00ba\u00b0]?\s*([A-Z0-9]+)")
    matricula = match_mat.group(1).strip() if match_mat else ""

    # ── Endereço ────────────────────────────────────
    match_end = m(r"endere[\u00e7c]o\s*(?:residencial|comercial|completo)?\s*:?\s*([^\n]+)")
    endereco = match_end.group(1).strip() if match_end else ""

    # ── Valor ORIGINAL da dívida ──────────────────────────
    # Captura o valor ANTES do desconto (valor devido / original / débito)
    padroes_divida = [
        r"valor\s+(?:do\s+)?d[e\u00e9]bito\s*:?\s*R?\$?\s*([\d\.,]+)",
        r"valor\s+(?:original|devido|da\s+d[\u00edivida])\s*:?\s*R?\$?\s*([\d\.,]+)",
        r"valor\s+devido\s*:?\s*R?\$?\s*([\d\.,]+)",
    ]
    valor_divida = ""
    for p in padroes_divida:
        match_d = m(p)
        if match_d:
            valor_divida = match_d.group(1).strip()
            break

    # ── Valor DO ACORDO (com desconto) ────────────────────
    # Este é o valor sobre o qual se calculam honorários e GEAP
    padroes_acordo = [
        r"valor\s+fechado\s+com\s+o?\s*desconto\s*:?\s*R?\$?\s*([\d\.,]+)",
        r"valor\s+para\s+pagamento\s+parcelado\s+com\s+desconto\s*:?\s*R?\$?\s*([\d\.,]+)",
        r"valor\s+(?:total|do\s+acordo|acordado|a\s+pagar)\s*:?\s*R?\$?\s*([\d\.,]+)",
    ]
    valor_acordo = ""
    for p in padroes_acordo:
        match_v = m(p)
        if match_v:
            valor_acordo = match_v.group(1).strip()
            break
    # Se so veio um valor, ele serve para ambos
    if valor_divida and not valor_acordo:
        valor_acordo = valor_divida
    if valor_acordo and not valor_divida:
        valor_divida = valor_acordo

    # ── Entrada: valor + vencimento ───────────────────────
    # Aceita "Entrada: R$", "Entrada de R$", "Entrada R$"
    match_entrada = m(r"entrada\s*(?:de|:)?\s*R?\$?\s*([\d\.,]+)")
    valor_entrada = match_entrada.group(1).strip() if match_entrada else ""

    # Vencimento da entrada: "para o dia DD/MM/AAAA" ou "vencimento em DD/MM/AAAA"
    match_venc_ent = m(r"entrada[^\n]*?(?:para\s+o\s+dia|vencimento\s+(?:em|para)?)\s*(\d{2}/\d{2}/\d{4})")
    venc_entrada = match_venc_ent.group(1).strip() if match_venc_ent else ""

    # ── Parcelas: qtd, valor, data de início ─────────────────
    match_parc = m(r"[+\s]*(\d+)\s*(?:x|parcelas?)\s*(?:de\s*)?R?\$?\s*([\d\.,]+)")
    if match_parc:
        qtd_parcelas = match_parc.group(1).strip()
        valor_parcela = match_parc.group(2).strip()
    else:
        qtd_parcelas = ""
        valor_parcela = ""

    # Data de início das parcelas: "iniciando em 25/08/2026" ou "iniciando o pagamento em"
    match_inicio = m(r"iniciando\s+(?:em|o\s+pagamento\s+(?:das\s+parcelas\s+)?em)\s*(\d{2}/\d{2}/\d{4})")
    inicio_parcelas = match_inicio.group(1).strip() if match_inicio else ""

    # Dia mensal de vencimento: tirar do início, ou do "dia X de cada mês"
    match_dia_mes = m(r"dia\s+(\d{1,2})\s+de\s+cada\s+m[e\u00ea]s")
    if match_dia_mes:
        dia_parcela = match_dia_mes.group(1).strip()
    elif inicio_parcelas:
        dia_parcela = inicio_parcelas.split("/")[0]  # dia do inicio_parcelas
    else:
        dia_parcela = ""

    # ── Competências ───────────────────────────────────
    # Só extrai competências se houver uma linha explícita de "Competência:"
    match_comp_linha = m(r"compet[\u00ea\u0065]nci[ao][s]?\s*:?\s*([^\n]+)")
    if match_comp_linha:
        competencias = processar_competencias(match_comp_linha.group(1))
    else:
        competencias = ""  # Não tenta adivinhar de datas aleatórias

    return {
        "nome": nome,
        "cpf": cpf,
        "processo": processo,
        "matricula": matricula,
        "endereco": endereco,
        "valor_divida": valor_divida,
        "valor_acordo": valor_acordo,
        "valor_entrada": valor_entrada,
        "venc_entrada": venc_entrada,
        "qtd_parcelas": qtd_parcelas,
        "valor_parcela": valor_parcela,
        "inicio_parcelas": inicio_parcelas,
        "dia_parcela": dia_parcela,
        "competencias": competencias,
    }

def formatar_e_calcular(campos):
    """Recebe os campos revisados (todos strings) e formata para o docxtpl."""
    def parse(v):
        return parse_monetario(v)

    def fmt_brl(v):
        return f"{v:,.2f}".replace(".", "_").replace(",", ".").replace("_", ",")

    MESES = ["","janeiro","fevereiro","março","abril","maio","junho",
             "julho","agosto","setembro","outubro","novembro","dezembro"]
    hoje = datetime.now()
    data_hoje = f"{hoje.day} de {MESES[hoje.month]} de {hoje.year}"

    nome      = campos.get("nome", "__________").strip() or "__________"
    cpf       = campos.get("cpf", "__________").strip() or "__________"
    processo  = campos.get("processo", "").strip() or "__________"
    matricula = campos.get("matricula", "__________").strip() or "__________"
    endereco  = campos.get("endereco", "__________").strip() or "__________"
    competencias = campos.get("competencias", "__________").strip() or "__________"

    # Valor ORIGINAL da dívida (antes do desconto)
    vd = parse(campos.get("valor_divida", ""))
    # Valor DO ACORDO (após desconto) — base para cálculos de honorários
    va = parse(campos.get("valor_acordo", ""))
    # Se só veio um valor, usa o mesmo para os dois
    if vd and not va:
        va = vd
    if va and not vd:
        vd = va

    ve = parse(campos.get("valor_entrada", ""))
    vp = parse(campos.get("valor_parcela", ""))
    qp_raw = campos.get("qtd_parcelas", "").strip()
    try:
        qp = int(qp_raw)
    except:
        qp = None

    # ──────────────────────────────────────────────────────────────
    # Cálculo automático de datas de vencimento
    # ──────────────────────────────────────────────────────────────
    import calendar

    venc_entrada_raw = campos.get("venc_entrada", "").strip()
    inicio_parc_raw  = campos.get("inicio_parcelas", "").strip()
    dia_parcela_raw  = campos.get("dia_parcela", "").strip()

    def parse_data(s):
        try:
            return datetime.strptime(s.strip(), "%d/%m/%Y")
        except:
            return None

    def fmt_data(dt):
        return dt.strftime("%d/%m/%Y")

    def proximo_mes_no_dia(ref_dt, dia):
        """Retorna o primeiro dia 'dia' do mês seguinte ao ref_dt."""
        mes = ref_dt.month + 1
        ano = ref_dt.year
        if mes > 12:
            mes = 1
            ano += 1
        ultimo = calendar.monthrange(ano, mes)[1]
        return datetime(ano, mes, min(dia, ultimo))

    def calcular_fim(inicio_dt, qtd):
        """Calcula a data final: inicio + (qtd-1) meses."""
        try:
            mes = inicio_dt.month + qtd - 1
            ano = inicio_dt.year + (mes - 1) // 12
            mes = ((mes - 1) % 12) + 1
            ultimo = calendar.monthrange(ano, mes)[1]
            return datetime(ano, mes, min(inicio_dt.day, ultimo))
        except:
            return None

    # Dia de vencimento das parcelas (default: 10)
    try:
        dia_parc_int = int(dia_parcela_raw) if dia_parcela_raw else 10
    except:
        dia_parc_int = 10

    # Vencimento da entrada: usa mensagem ou default hoje + 3 dias
    dt_venc_entrada = parse_data(venc_entrada_raw)
    if not dt_venc_entrada:
        dt_venc_entrada = hoje + __import__('datetime').timedelta(days=3)

    # Início das parcelas: usa mensagem ou calcula próximo mês no dia de parcela
    dt_inicio_parc = parse_data(inicio_parc_raw)
    if not dt_inicio_parc:
        dt_inicio_parc = proximo_mes_no_dia(dt_venc_entrada, dia_parc_int)

    # Fim das parcelas
    dt_fim_parc = calcular_fim(dt_inicio_parc, qp) if qp else None

    venc_entrada    = fmt_data(dt_venc_entrada)
    inicio_parcelas = fmt_data(dt_inicio_parc)
    dia_parcela     = str(dt_inicio_parc.day)
    fim_parcelas    = fmt_data(dt_fim_parc) if dt_fim_parc else "__________"


    if vd:
        str_valor_divida = f"{fmt_brl(vd)} ({valor_por_extenso(vd).capitalize()})"
    else:
        str_valor_divida = "__________"

    if va:
        honorarios = va * 0.10
        valor_geap  = va - honorarios
        str_valor_acordo = f"{fmt_brl(va)} ({valor_por_extenso(va).capitalize()})"
        str_honorarios   = f"{fmt_brl(honorarios)} ({valor_por_extenso(honorarios).capitalize()})"
        str_valor_geap   = f"{fmt_brl(valor_geap)} ({valor_por_extenso(valor_geap).capitalize()})"
    else:
        str_valor_acordo = str_honorarios = str_valor_geap = "__________"

    str_entrada  = f"{fmt_brl(ve)} ({valor_por_extenso(ve).capitalize()})" if ve else "__________"
    str_qtd      = f"{qp}" if qp else "__________"
    str_parcela  = f"{fmt_brl(vp)} ({valor_por_extenso(vp).capitalize()})" if vp else "__________"

    return {
        "nome_cliente":   nome,
        "cpf_cliente":    cpf,
        "processo":       processo,
        "matricula":      matricula,
        "endereco":       endereco,
        "valor_divida":   str_valor_divida,
        "valor_acordo":   str_valor_acordo,
        "competencias":   competencias,
        "valor_entrada":  str_entrada,
        "venc_entrada":   venc_entrada,
        "qtd_parcelas":   str_qtd,
        "valor_parcela":  str_parcela,
        "dia_parcela":    dia_parcela,
        "inicio_parcelas": inicio_parcelas,
        "fim_parcelas":   fim_parcelas,
        "honorarios":     str_honorarios,
        "valor_geap":     str_valor_geap,
        "data":           data_hoje,
    }

def gerar_documento(campos_revisados):
    dados = formatar_e_calcular(campos_revisados)
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    nome_arq = re.sub(r'[\\/*?:"<>|]', "", dados["nome_cliente"])[:50]
    caminho = os.path.join(PASTA_SAIDA, f"Termo_{nome_arq}.docx")
    doc = DocxTemplate(MODELO_PATH)
    doc.render(dados)
    doc.save(caminho)
    return caminho, dados

# ============================================================
# INTERFACE GRÁFICA — DOIS PASSOS
# ============================================================

COR_FUNDO     = "#1C1C1E"
COR_PAINEL    = "#2C2C2E"
COR_BORDA     = "#3A3A3C"
COR_OURO      = "#C9A84C"
COR_OURO_ESC  = "#A07830"
COR_TEXTO     = "#F5F5F0"
COR_CINZA     = "#6E6E73"
COR_VERDE     = "#4CAF50"
COR_VERMELHO  = "#F44336"
FONTE_TITULO  = ("Georgia", 14, "bold")
FONTE_LABEL   = ("Segoe UI", 9, "bold")
FONTE_CORPO   = ("Segoe UI", 10)
FONTE_MONO    = ("Consolas", 10)

PLACEHOLDER = (
    "Cole aqui a mensagem do WhatsApp exatamente como chegou...\n\n"
    "O sistema vai interpretar automaticamente e\n"
    "mostrar os campos para você conferir antes de gerar."
)

# Campos que aparecem na tela de revisão (label, chave_interna)
CAMPOS_REVISAO = [
    ("Nome / Cliente",               "nome"),
    ("CPF",                          "cpf"),
    ("Processo Judicial",            "processo"),
    ("Matrícula",                    "matricula"),
    ("Endereço",                     "endereco"),
    ("Valor Original da Dívida",     "valor_divida"),
    ("Valor do Acordo (c/ desconto)", "valor_acordo"),
    ("Valor da Entrada",             "valor_entrada"),
    ("Vencimento da Entrada",        "venc_entrada"),
    ("Qtd. de Parcelas",             "qtd_parcelas"),
    ("Valor da Parcela",             "valor_parcela"),
    ("Início das Parcelas",          "inicio_parcelas"),
    ("Competências",                 "competencias"),
]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gerador de Termos de Acordo — Aldrigues Cândido")
        self.configure(bg=COR_FUNDO)
        self.resizable(True, True)
        self.minsize(760, 580)
        self.entries = {}       # chave → Entry widget
        self._build_ui()
        self.after(50, self._centralizar)

    def _centralizar(self):
        self.update_idletasks()
        w, h = 860, 680
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ── Construção da UI ────────────────────────────────────
    def _build_ui(self):
        # Cabeçalho
        hdr = tk.Frame(self, bg=COR_PAINEL, pady=14)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚖  GERADOR DE TERMOS DE ACORDO",
                 font=FONTE_TITULO, bg=COR_PAINEL, fg=COR_OURO).pack()
        tk.Label(hdr, text="Aldrigues Cândido Advocacia",
                 font=("Segoe UI", 8), bg=COR_PAINEL, fg=COR_CINZA).pack()
        tk.Frame(self, bg=COR_OURO, height=2).pack(fill="x")

        # Container principal (2 colunas)
        main = tk.Frame(self, bg=COR_FUNDO)
        main.pack(fill="both", expand=True, padx=16, pady=12)
        main.columnconfigure(0, weight=2)
        main.columnconfigure(1, weight=3)
        main.rowconfigure(0, weight=1)

        # ── Coluna Esquerda: Colar mensagem ─────────────────
        esq = tk.Frame(main, bg=COR_FUNDO)
        esq.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        esq.rowconfigure(1, weight=1)

        tk.Label(esq, text="① COLE A MENSAGEM", font=FONTE_LABEL,
                 bg=COR_FUNDO, fg=COR_OURO, anchor="w").grid(row=0, column=0, sticky="ew", pady=(0,4))

        frame_txt = tk.Frame(esq, bg=COR_BORDA, padx=1, pady=1)
        frame_txt.grid(row=1, column=0, sticky="nsew")
        esq.columnconfigure(0, weight=1)

        self.txt = scrolledtext.ScrolledText(
            frame_txt, wrap=tk.WORD, font=FONTE_MONO,
            bg=COR_PAINEL, fg=COR_CINZA,
            insertbackground=COR_OURO, relief="flat",
            padx=10, pady=8,
        )
        self.txt.pack(fill="both", expand=True)
        self.txt.insert("1.0", PLACEHOLDER)
        self.txt.bind("<FocusIn>",  self._limpar_ph)
        self.txt.bind("<FocusOut>", self._restaurar_ph)

        self.btn_interpretar = tk.Button(
            esq, text="🔍  INTERPRETAR MENSAGEM",
            font=("Segoe UI", 10, "bold"),
            bg=COR_BORDA, fg=COR_OURO,
            activebackground="#4A4A4C", activeforeground=COR_OURO,
            relief="flat", cursor="hand2", pady=8,
            command=self._interpretar
        )
        self.btn_interpretar.grid(row=2, column=0, sticky="ew", pady=(8,0))

        # ── Coluna Direita: Campos extraídos ────────────────
        dir_ = tk.Frame(main, bg=COR_FUNDO)
        dir_.grid(row=0, column=1, sticky="nsew")
        dir_.columnconfigure(1, weight=1)

        tk.Label(dir_, text="② REVISE E CORRIJA OS CAMPOS", font=FONTE_LABEL,
                 bg=COR_FUNDO, fg=COR_OURO, anchor="w").grid(
                 row=0, column=0, columnspan=2, sticky="ew", pady=(0,6))

        for i, (label, chave) in enumerate(CAMPOS_REVISAO):
            tk.Label(dir_, text=label + ":", font=("Segoe UI", 8, "bold"),
                     bg=COR_FUNDO, fg=COR_CINZA, anchor="w").grid(
                     row=i+1, column=0, sticky="w", padx=(0,6), pady=2)

            ent = tk.Entry(dir_, font=FONTE_CORPO,
                           bg=COR_PAINEL, fg=COR_TEXTO,
                           insertbackground=COR_OURO,
                           relief="flat", bd=0,
                           highlightthickness=1,
                           highlightbackground=COR_BORDA,
                           highlightcolor=COR_OURO)
            ent.grid(row=i+1, column=1, sticky="ew", pady=2, ipady=4)
            self.entries[chave] = ent

        # Nota informativa
        tk.Label(dir_, text="💡 Valores monetários: use vírgula. Ex: 3.500,00",
                 font=("Segoe UI", 8), bg=COR_FUNDO, fg=COR_CINZA,
                 anchor="w").grid(row=len(CAMPOS_REVISAO)+1, column=0,
                 columnspan=2, sticky="w", pady=(6,0))

        # ── Rodapé ──────────────────────────────────────────
        rodape = tk.Frame(self, bg=COR_FUNDO, padx=16, pady=0)
        rodape.pack(fill="x")

        self.status_var = tk.StringVar(value="Aguardando mensagem...")
        tk.Label(rodape, textvariable=self.status_var,
                 font=("Segoe UI", 8), bg=COR_FUNDO, fg=COR_CINZA,
                 anchor="w").pack(fill="x", pady=(0, 4))

        btn_frame = tk.Frame(self, bg=COR_FUNDO, padx=16, pady=10)
        btn_frame.pack(fill="x")

        self.btn_gerar = tk.Button(
            btn_frame, text="⚡  GERAR TERMO DE ACORDO",
            font=("Segoe UI", 11, "bold"),
            bg=COR_OURO, fg="#1C1C1E",
            activebackground=COR_OURO_ESC, activeforeground="#1C1C1E",
            relief="flat", cursor="hand2", padx=20, pady=10,
            command=self._gerar
        )
        self.btn_gerar.pack(fill="x")
        self.btn_gerar.bind("<Enter>", lambda e: self.btn_gerar.config(bg=COR_OURO_ESC))
        self.btn_gerar.bind("<Leave>", lambda e: self.btn_gerar.config(bg=COR_OURO))

    # ── Placeholder ────────────────────────────────────────
    def _limpar_ph(self, _e):
        if self.txt.get("1.0", "end-1c") == PLACEHOLDER:
            self.txt.delete("1.0", "end")
            self.txt.config(fg=COR_TEXTO)

    def _restaurar_ph(self, _e):
        if not self.txt.get("1.0", "end-1c").strip():
            self.txt.insert("1.0", PLACEHOLDER)
            self.txt.config(fg=COR_CINZA)

    # ── Passo 1: Interpretar ───────────────────────────────
    def _interpretar(self):
        mensagem = self.txt.get("1.0", "end-1c").strip()
        if not mensagem or mensagem == PLACEHOLDER.strip():
            messagebox.showwarning("Atenção", "Cole a mensagem do WhatsApp primeiro.")
            return

        campos = parse_whatsapp_message(mensagem)

        # Preenche as entries com o que foi extraído
        for chave, entry in self.entries.items():
            entry.delete(0, "end")
            valor = campos.get(chave, "")
            entry.insert(0, valor)
            # Destaca campos que ficaram vazios em vermelho
            if not valor:
                entry.config(highlightbackground=COR_VERMELHO, highlightcolor=COR_VERMELHO)
            else:
                entry.config(highlightbackground=COR_BORDA, highlightcolor=COR_OURO)

        vazios = [lab for lab, ch in CAMPOS_REVISAO if not campos.get(ch)]
        if vazios:
            self._set_status(
                f"⚠ Não detectado automaticamente (preencha manualmente): {', '.join(vazios)}",
                COR_OURO
            )
        else:
            self._set_status("✅ Todos os campos foram interpretados. Revise e clique em Gerar.", COR_VERDE)

    # ── Passo 2: Gerar ────────────────────────────────────
    def _gerar(self):
        if not os.path.exists(MODELO_PATH):
            messagebox.showerror("Erro", f"Modelo não encontrado: {MODELO_PATH}")
            return

        # Coleta os valores das entries
        campos = {chave: entry.get().strip() for chave, entry in self.entries.items()}

        if not campos.get("nome"):
            messagebox.showwarning("Atenção", "O campo 'Nome / Cliente' é obrigatório.")
            return

        self._set_status("⏳ Gerando documento...", COR_OURO)
        self.btn_gerar.config(state="disabled")
        self.update()

        try:
            caminho, dados = gerar_documento(campos)
            self._set_status(f"✅ Documento gerado: {caminho}", COR_VERDE)
            resp = messagebox.askyesno(
                "Sucesso!",
                f"Termo gerado com sucesso!\n\n"
                f"Cliente: {dados['nome_cliente']}\n"
                f"Competências: {dados['competencias']}\n\n"
                f"Deseja abrir o documento agora?"
            )
            if resp:
                os.startfile(os.path.abspath(caminho))
        except Exception as e:
            self._set_status(f"❌ Erro: {e}", COR_VERMELHO)
            messagebox.showerror("Erro ao gerar", str(e))
        finally:
            self.btn_gerar.config(state="normal")

    def _set_status(self, msg, cor=COR_CINZA):
        self.status_var.set(msg)
        self.update_idletasks()


if __name__ == "__main__":
    app = App()
    app.mainloop()
