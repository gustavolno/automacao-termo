import re
import os
from datetime import datetime
from decimal import Decimal
from docxtpl import DocxTemplate
from num2words import num2words
import tkinter as tk
from tkinter import messagebox, scrolledtext

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

    # Cálculo da data de término das parcelas se houver início e quantidade
    fim_parcelas = "__________"
    if inicio_parcelas and inicio_parcelas != "__________" and qp:
        try:
            dt_inicio = datetime.strptime(inicio_parcelas, "%d/%m/%Y")
            import calendar
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
        # Chaves padronizadas novas
        "nome": nome,
        "cpf": cpf,
        "processo": processo,
        "matricula": matricula,
        "telefone": telefone,
        "email": email,
        "endereco": endereco,
        "cep": cep,
        "valor_original": str_valor_original,
        "valor_acordo": str_valor_acordo,
        "valor_entrada": str_entrada,
        "vencimento_entrada": venc_entrada,
        "quantidade_parcelas": str_qtd,
        "valor_parcela": str_parcela,
        "inicio_parcelas": inicio_parcelas,
        "dia_parcela": dia_parcela,
        "competencias": competencias,
        # Chaves compatíveis com modelos anteriores
        "nome_cliente": nome,
        "cpf_cliente": cpf,
        "valor_divida": str_valor_original,
        "venc_entrada": venc_entrada,
        "qtd_parcelas": str_qtd,
        "fim_parcelas": fim_parcelas,
        "honorarios": str_honorarios,
        "valor_geap": str_valor_geap,
        "data": data_hoje,
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
# INTERFACE GRÁFICA (Tkinter)
# ============================================================

COR_FUNDO = "#1C1C1E"
COR_PAINEL = "#2C2C2E"
COR_BORDA = "#3A3A3C"
COR_OURO = "#C9A84C"
COR_OURO_ESC = "#A07830"
COR_TEXTO = "#F5F5F0"
COR_CINZA = "#6E6E73"
COR_VERDE = "#4CAF50"
COR_VERMELHO = "#F44336"
FONTE_TITULO = ("Georgia", 14, "bold")
FONTE_LABEL = ("Segoe UI", 9, "bold")
FONTE_CORPO = ("Segoe UI", 10)
FONTE_MONO = ("Consolas", 10)

PLACEHOLDER = (
    "Cole aqui a mensagem recebida exatamente como chegou...\n\n"
    "O sistema interpretará automaticamente e exibirá\n"
    "todos os campos na área de revisão à direita."
)

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


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gerador de Termos de Acordo — Aldrigues Cândido Advocacia")
        self.configure(bg=COR_FUNDO)
        self.resizable(True, True)
        self.minsize(840, 680)
        self.entries = {}
        self._build_ui()
        self.after(50, self._centralizar)

    def _centralizar(self):
        self.update_idletasks()
        w, h = 920, 740
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _build_ui(self):
        # Cabeçalho
        hdr = tk.Frame(self, bg=COR_PAINEL, pady=12)
        hdr.pack(fill="x")
        tk.Label(hdr, text="⚖  GERADOR DE TERMOS DE ACORDO",
                 font=FONTE_TITULO, bg=COR_PAINEL, fg=COR_OURO).pack()
        tk.Label(hdr, text="Aldrigues Cândido Advocacia — Módulo Único Integrado",
                 font=("Segoe UI", 8), bg=COR_PAINEL, fg=COR_CINZA).pack()
        tk.Frame(self, bg=COR_OURO, height=2).pack(fill="x")

        # Painel principal
        main = tk.Frame(self, bg=COR_FUNDO)
        main.pack(fill="both", expand=True, padx=16, pady=10)
        main.columnconfigure(0, weight=2)
        main.columnconfigure(1, weight=3)
        main.rowconfigure(0, weight=1)

        # Coluna Esquerda: Texto bruto
        esq = tk.Frame(main, bg=COR_FUNDO)
        esq.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        esq.rowconfigure(1, weight=1)
        esq.columnconfigure(0, weight=1)

        tk.Label(esq, text="① COLE A MENSAGEM BRUTA", font=FONTE_LABEL,
                 bg=COR_FUNDO, fg=COR_OURO, anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 4))

        frame_txt = tk.Frame(esq, bg=COR_BORDA, padx=1, pady=1)
        frame_txt.grid(row=1, column=0, sticky="nsew")

        self.txt = scrolledtext.ScrolledText(
            frame_txt, wrap=tk.WORD, font=FONTE_MONO,
            bg=COR_PAINEL, fg=COR_CINZA,
            insertbackground=COR_OURO, relief="flat",
            padx=10, pady=8
        )
        self.txt.pack(fill="both", expand=True)
        self.txt.insert("1.0", PLACEHOLDER)
        self.txt.bind("<FocusIn>", self._limpar_ph)
        self.txt.bind("<FocusOut>", self._restaurar_ph)

        self.btn_interpretar = tk.Button(
            esq, text="🔍  INTERPRETAR MENSAGEM",
            font=("Segoe UI", 10, "bold"),
            bg=COR_BORDA, fg=COR_OURO,
            activebackground="#4A4A4C", activeforeground=COR_OURO,
            relief="flat", cursor="hand2", pady=8,
            command=self._interpretar
        )
        self.btn_interpretar.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        # Coluna Direita: Painel rolável com campos de revisão
        dir_ = tk.Frame(main, bg=COR_FUNDO)
        dir_.grid(row=0, column=1, sticky="nsew")
        dir_.columnconfigure(0, weight=1)
        dir_.rowconfigure(1, weight=1)

        tk.Label(dir_, text="② REVISE OS CAMPOS EXTRAÍDOS", font=FONTE_LABEL,
                 bg=COR_FUNDO, fg=COR_OURO, anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 4))

        # Canvas para rolagem dos campos
        canvas = tk.Canvas(dir_, bg=COR_FUNDO, highlightthickness=0)
        scrollbar = tk.Scrollbar(dir_, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=COR_FUNDO)

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
            tk.Label(scroll_frame, text=label + ":", font=("Segoe UI", 8, "bold"),
                     bg=COR_FUNDO, fg=COR_CINZA, anchor="w").grid(
                row=i, column=0, sticky="w", padx=(0, 6), pady=2
            )

            ent = tk.Entry(scroll_frame, font=FONTE_CORPO,
                           bg=COR_PAINEL, fg=COR_TEXTO,
                           insertbackground=COR_OURO,
                           relief="flat", bd=0,
                           highlightthickness=1,
                           highlightbackground=COR_BORDA,
                           highlightcolor=COR_OURO)
            ent.grid(row=i, column=1, sticky="ew", pady=2, ipady=3)
            self.entries[chave] = ent

        # Rodapé
        rodape = tk.Frame(self, bg=COR_FUNDO, padx=16, pady=4)
        rodape.pack(fill="x")

        self.status_var = tk.StringVar(value="Aguardando mensagem...")
        tk.Label(rodape, textvariable=self.status_var,
                 font=("Segoe UI", 8), bg=COR_FUNDO, fg=COR_CINZA,
                 anchor="w").pack(fill="x", pady=(0, 4))

        btn_frame = tk.Frame(self, bg=COR_FUNDO, padx=16, pady=8)
        btn_frame.pack(fill="x")
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        btn_frame.columnconfigure(2, weight=1)

        self.btn_gerar_parcelado = tk.Button(
            btn_frame, text="GERAR (PARCELADO)",
            font=("Segoe UI", 10, "bold"),
            bg=COR_OURO, fg="#1C1C1E",
            activebackground=COR_OURO_ESC, activeforeground="#1C1C1E",
            relief="flat", cursor="hand2", padx=10, pady=8,
            command=lambda: self._gerar(tipo="parcelado")
        )
        self.btn_gerar_parcelado.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.btn_gerar_parcelado.bind("<Enter>", lambda e: self.btn_gerar_parcelado.config(bg=COR_OURO_ESC))
        self.btn_gerar_parcelado.bind("<Leave>", lambda e: self.btn_gerar_parcelado.config(bg=COR_OURO))
        
        self.btn_gerar_avista = tk.Button(
            btn_frame, text="GERAR (À VISTA)",
            font=("Segoe UI", 10, "bold"),
            bg=COR_OURO, fg="#1C1C1E",
            activebackground=COR_OURO_ESC, activeforeground="#1C1C1E",
            relief="flat", cursor="hand2", padx=10, pady=8,
            command=lambda: self._gerar(tipo="avista")
        )
        self.btn_gerar_avista.grid(row=0, column=1, sticky="ew", padx=(4, 4))
        self.btn_gerar_avista.bind("<Enter>", lambda e: self.btn_gerar_avista.config(bg=COR_OURO_ESC))
        self.btn_gerar_avista.bind("<Leave>", lambda e: self.btn_gerar_avista.config(bg=COR_OURO))

        self.btn_reset = tk.Button(
            btn_frame, text="RESETAR CAMPOS",
            font=("Segoe UI", 10, "bold"),
            bg=COR_BORDA, fg=COR_TEXTO,
            activebackground="#4A4A4C", activeforeground=COR_TEXTO,
            relief="flat", cursor="hand2", padx=10, pady=8,
            command=self._reset_campos
        )
        self.btn_reset.grid(row=0, column=2, sticky="ew", padx=(4, 0))

    def _limpar_ph(self, _e):
        if self.txt.get("1.0", "end-1c") == PLACEHOLDER:
            self.txt.delete("1.0", "end")
            self.txt.config(fg=COR_TEXTO)

    def _restaurar_ph(self, _e):
        if not self.txt.get("1.0", "end-1c").strip():
            self.txt.insert("1.0", PLACEHOLDER)
            self.txt.config(fg=COR_CINZA)

    def _reset_campos(self):
        """Limpa o campo de texto da mensagem e todos os campos extraídos da área de revisão."""
        self.txt.delete("1.0", "end")
        self.txt.insert("1.0", PLACEHOLDER)
        self.txt.config(fg=COR_CINZA)

        for entry in self.entries.values():
            entry.delete(0, "end")
            entry.config(highlightbackground=COR_BORDA, highlightcolor=COR_OURO)

        self._set_status("Aguardando mensagem...", COR_CINZA)

    def _interpretar(self):
        msg = self.txt.get("1.0", "end-1c").strip()
        if not msg or msg == PLACEHOLDER.strip():
            messagebox.showwarning("Atenção", "Cole a mensagem do WhatsApp primeiro.")
            return

        campos = interpretar_mensagem(msg)

        for chave, entry in self.entries.items():
            entry.delete(0, "end")
            val = campos.get(chave, "")
            entry.insert(0, val)
            entry.xview_moveto(0)
            if not val and chave in ("nome", "cpf", "valor_acordo"):
                entry.config(highlightbackground=COR_VERMELHO, highlightcolor=COR_VERMELHO)
            else:
                entry.config(highlightbackground=COR_BORDA, highlightcolor=COR_OURO)

        vazios = [lab for lab, ch in CAMPOS_REVISAO if not campos.get(ch)]
        if vazios:
            self._set_status(f"⚠ Campos não identificados (preencha manualmente se necessário): {', '.join(vazios)}", COR_OURO)
        else:
            self._set_status("✅ Todos os campos foram interpretados com sucesso!", COR_VERDE)

    def _gerar(self, tipo="parcelado"):
        modelo_usado = "MODELO DE TERMO DE ACORDO-A VISTA.docx" if tipo == "avista" else MODELO_PATH
        if not os.path.exists(modelo_usado):
            messagebox.showerror("Erro", f"Arquivo modelo não encontrado: {modelo_usado}")
            return

        campos = {ch: entry.get().strip() for ch, entry in self.entries.items()}

        if not campos.get("nome"):
            messagebox.showwarning("Atenção", "O campo 'Nome / Cliente' é obrigatório.")
            return

        self._set_status(f"📄 Gerando documento ({tipo})...", COR_OURO)
        self.btn_gerar_parcelado.config(state="disabled")
        self.btn_gerar_avista.config(state="disabled")
        self.update()

        try:
            caminho, dados = gerar_documento(campos, modelo_usado)
            self._set_status(f"✓ Documento gerado com sucesso: {caminho}", COR_VERDE)
            resp = messagebox.askyesno(
                "Sucesso!",
                f"Termo de acordo gerado com sucesso!\n\n"
                f"Cliente: {dados['nome_cliente']}\n"
                f"CPF: {dados['cpf_cliente']}\n\n"
                f"Deseja abrir o documento agora?"
            )
            if resp:
                os.startfile(os.path.abspath(caminho))

            # Reseta os campos automaticamente após gerar
            self._reset_campos()

        except Exception as e:
            self._set_status(f"❌ Erro ao gerar: {e}", COR_VERMELHO)
            messagebox.showerror("Erro ao gerar termo", str(e))
        finally:
            self.btn_gerar_parcelado.config(state="normal")
            self.btn_gerar_avista.config(state="normal")

    def _set_status(self, msg, cor=COR_CINZA):
        self.status_var.set(msg)
        self.update_idletasks()


if __name__ == "__main__":
    app = App()
    app.mainloop()
