"""
acordo_parser.py
Módulo para leitura e validação dos dados de acordos (apenas PARCELADOS)
cruzando informações da planilha com termos e atas de audiência em PDF no Dropbox.
"""

import os
import sys
import re
import unicodedata
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Dict, Any

import openpyxl
import pymupdf

def normalizar_texto(texto: str) -> str:
    """Remove acentos e espaços extras para comparações seguras."""
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", str(texto)).encode("ASCII", "ignore").decode("utf-8")
    return re.sub(r"\s+", " ", texto).strip().upper()

def limpar_processo(proc_str: Any) -> str:
    """Extrai número CNJ no formato 0000000-00.0000.8.00.0000."""
    if not proc_str:
        return ""
    s = str(proc_str).strip()
    m = re.search(r"(\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})", s)
    if m:
        return m.group(1)
    m2 = re.search(r"(\d{7}\s*\d{2}\s*\d{4}\s*\d\s*\d{2}\s*\d{4})", s)
    if m2:
        return re.sub(r"\s+", ".", m2.group(1))
    return s.split()[0].strip()

def formatar_moeda_br(valor: Any) -> str:
    """Converte valores numéricos para string formatada em Real: 1.234,56."""
    if valor is None:
        return ""
    s = str(valor).strip()
    if not s or s in ("-", "None", "0", "0.0", "0,00"):
        return ""
    try:
        # Se for string com vírgula e ponto: ex 1.234,56
        if "," in s and "." in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")
        f = float(s)
        if f <= 0:
            return ""
        # Formata com separador de milhar ponto e decimal vírgula
        partes = f"{f:,.2f}".split(".")
        inteiro = partes[0].replace(",", ".")
        decimal = partes[1]
        return f"{inteiro},{decimal}"
    except Exception:
        return s

def formatar_data_br(val: Any) -> str:
    """Converte datetime, date ou string para dd/mm/aaaa."""
    if val is None:
        return ""
    if isinstance(val, (datetime, date)):
        return val.strftime("%d/%m/%Y")
    s = str(val).strip()
    if not s or s in ("-", "None"):
        return ""
    # Se já estiver em dd/mm/aaaa
    if re.match(r"^\d{2}/\d{2}/\d{4}$", s):
        return s
    # Se estiver em yyyy-mm-dd...
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        ano, mes, dia = m.group(1), m.group(2), m.group(3)
        return f"{dia}/{mes}/{ano}"
    return s

def extrair_qtd_parcelas(val: Any) -> int:
    """Extrai o número inteiro de parcelas: ex '24x' -> 24."""
    if not val:
        return 0
    m = re.search(r"(\d+)", str(val))
    if m:
        return int(m.group(1))
    return 0

class AcordoParser:
    def __init__(self, caminho_planilha: Optional[str] = None):
        self.caminho_planilha = self._resolver_caminho_planilha(caminho_planilha)
        self.dropbox_base = Path(
            r"C:\Users\Cob_Geap_05082026\Dropbox\COBRANÇA NEGOCIAÇÃO\ADMINISTRATIVO- COBRANÇA\ACOMPANHAMENTO DE ACORDOS AC COBRANÇA"
        )

    def _resolver_caminho_planilha(self, custom_path: Optional[str] = None) -> Path:
        """Busca a planilha jaci em todos os locais possíveis para garantir execução 100% autônoma."""
        if custom_path and Path(custom_path).exists():
            return Path(custom_path)

        candidatos = [
            Path("planilha_jaci.xlsx"),
            Path("devedores_encontrados.xlsx"),
            Path(r"C:\Users\Cob_Geap_05082026\Dropbox\COBRANÇA NEGOCIAÇÃO\GERADOR DE TERMO\planilha_jaci.xlsx"),
            Path(r"C:\Users\Cob_Geap_05082026\Dropbox\COBRANÇA NEGOCIAÇÃO\planilha_jaci.xlsx"),
            Path(r"C:\Users\Cob_Geap_05082026\OneDrive\Documentos\automacao-termo\planilha_jaci.xlsx"),
            Path(r"C:\Users\Cob_Geap_05082026\OneDrive\Documentos\automacao-termo\devedores_encontrados.xlsx"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "BaixarBoletos" / "planilha_jaci.xlsx",
        ]

        # Se executado via PyInstaller, checa a pasta do executável
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            candidatos.insert(0, exe_dir / "planilha_jaci.xlsx")
            candidatos.insert(1, exe_dir / "devedores_encontrados.xlsx")

        for c in candidatos:
            if c.exists():
                return c

        # Fallback: varre a pasta do Dropbox por qualquer arquivo contendo 'jaci' ou 'devedores'
        base_dropbox = Path(r"C:\Users\Cob_Geap_05082026\Dropbox\COBRANÇA NEGOCIAÇÃO")
        if base_dropbox.exists():
            for root, dirs, files in os.walk(base_dropbox):
                for f in files:
                    fn = f.lower()
                    if fn.endswith(".xlsx") and ("jaci" in fn or "devedores" in fn or "fechados" in fn):
                        return Path(root) / f

        return Path("planilha_jaci.xlsx")

    def obter_pasta_cliente_dropbox(self, nome_cliente: str) -> Optional[Path]:
        """Localiza a pasta do cliente no Dropbox."""
        if not self.dropbox_base.exists():
            return None
        norm_alvo = normalizar_texto(nome_cliente)
        # Busca exata
        for p in self.dropbox_base.iterdir():
            if p.is_dir() and normalizar_texto(p.name) == norm_alvo:
                return p
        # Busca aproximada por palavras-chave
        palavras = [w for w in norm_alvo.split() if len(w) > 2]
        for p in self.dropbox_base.iterdir():
            if p.is_dir():
                p_norm = normalizar_texto(p.name)
                if norm_alvo in p_norm or p_norm in norm_alvo:
                    return p
                if len(palavras) >= 2 and palavras[0] in p_norm and palavras[-1] in p_norm:
                    return p
        return None

    def carregar_dados_cliente(self, nome_cliente: str) -> Dict[str, Any]:
        """
        Lê os dados da planilha para o cliente, verifica se é PARCELADO,
        localiza os documentos da pasta do cliente no Dropbox, confere dados com o PDF
        e retorna um dicionário estruturado para preenchimento no formulário.
        """
        resultado = {
            "sucesso": False,
            "motivo_erro": "",
            "eh_parcelado": False,
            "nome_cliente": nome_cliente.strip(),
            "processo": "",
            "cpf": "",
            "data_registro": datetime.now().strftime("%d/%m/%Y"),
            "valor_inicial": "",
            "valor_limite": "",
            "vinculo": "Titular",
            "tem_sentenca": False,
            "arquivo_sentenca": None,
            "data_homologacao": "",
            "valor_homologacao": "",
            "descricao_item": "Prestação de serviço de cobrança/ tecnológico",
            "forma_pagamento": "Boleto bancário",
            "boleto": "SICOOB- AC",
            "escritorio": "Unidade Brasilia",
            "tem_entrada": False,
            "data_entrada": "",
            "valor_entrada": "",
            "qtd_parcelas": 0,
            "valor_parcela": "",
            "primeiro_vencimento": "",
            "pasta_dropbox": None,
            "documentos_encontrados": [],
            "validacao_pdf_notas": []
        }

        # 1. Carregar planilha
        if not self.caminho_planilha.exists():
            resultado["motivo_erro"] = f"Planilha não encontrada: {self.caminho_planilha}"
            return resultado

        wb = openpyxl.load_workbook(self.caminho_planilha, data_only=True)
        ws = wb.active
        for s in wb.sheetnames:
            if "FECHADO" in s.upper() or "ENCONTRADO" in s.upper():
                ws = wb[s]
                break

        # Mapear cabeçalhos
        header = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        col_map = {}
        for idx, h in enumerate(header, 1):
            if h:
                col_map[normalizar_texto(str(h))] = idx

        idx_nome = col_map.get("BENEFICIARIO") or col_map.get("BENEFICIARIO") or 3
        idx_cpf = col_map.get("CPF", 4)
        idx_proc = col_map.get("PROCESSO", 5)
        idx_cond = col_map.get("CONDICOES DO ACORDO", 7)
        idx_vcausa = col_map.get("VALOR DA CAUSA", 8)
        idx_vacordo = col_map.get("VALOR INTEGRAL DO ACORDO", 10)
        idx_dentrada = col_map.get("DATA DA ENTRADA /QUITACAO", 11)
        idx_ventrada = col_map.get("VALOR DA ENTRADA/ QUITACAO", 12)
        idx_parc = col_map.get("PARCELAS", 15)
        idx_vparc = col_map.get("VALOR DA PARCELA", 16)
        idx_dprim_venc = col_map.get("PAGAMENTO INICIAL", 19)

        norm_alvo = normalizar_texto(nome_cliente)
        linha_encontrada = None

        for r in range(2, ws.max_row + 1):
            val_nome = ws.cell(r, idx_nome).value
            if val_nome and normalizar_texto(str(val_nome)) == norm_alvo:
                linha_encontrada = r
                break
            # Aproximação se nome parcial bater
            if val_nome and len(norm_alvo) > 8 and (norm_alvo in normalizar_texto(str(val_nome)) or normalizar_texto(str(val_nome)) in norm_alvo):
                linha_encontrada = r
                break

        if not linha_encontrada:
            resultado["motivo_erro"] = f"Cliente '{nome_cliente}' não localizado na planilha."
            return resultado

        # Extrair dados da linha
        condicao = str(ws.cell(linha_encontrada, idx_cond).value or "").strip().upper()
        if "PARCEL" not in condicao:
            resultado["eh_parcelado"] = False
            resultado["motivo_erro"] = f"Condição do acordo é '{condicao}' (Não é PARCELADO)."
            return resultado

        resultado["eh_parcelado"] = True
        resultado["cpf"] = str(ws.cell(linha_encontrada, idx_cpf).value or "").strip()
        resultado["processo"] = limpar_processo(ws.cell(linha_encontrada, idx_proc).value)
        resultado["valor_inicial"] = formatar_moeda_br(ws.cell(linha_encontrada, idx_vcausa).value)
        valor_acordo_str = formatar_moeda_br(ws.cell(linha_encontrada, idx_vacordo).value)
        resultado["valor_limite"] = valor_acordo_str
        resultado["valor_homologacao"] = valor_acordo_str

        # Entrada
        data_ent = formatar_data_br(ws.cell(linha_encontrada, idx_dentrada).value)
        val_ent = formatar_moeda_br(ws.cell(linha_encontrada, idx_ventrada).value)
        if val_ent and val_ent not in ("0,00", ""):
            resultado["tem_entrada"] = True
            resultado["data_entrada"] = data_ent
            resultado["valor_entrada"] = val_ent
        else:
            resultado["tem_entrada"] = False
            resultado["data_entrada"] = ""
            resultado["valor_entrada"] = ""

        # Parcelas
        resultado["qtd_parcelas"] = extrair_qtd_parcelas(ws.cell(linha_encontrada, idx_parc).value)
        resultado["valor_parcela"] = formatar_moeda_br(ws.cell(linha_encontrada, idx_vparc).value)
        resultado["primeiro_vencimento"] = formatar_data_br(ws.cell(linha_encontrada, idx_dprim_venc).value)

        # 2. Localizar pasta e arquivos no Dropbox
        pasta_cliente = self.obter_pasta_cliente_dropbox(nome_cliente)
        if pasta_cliente and pasta_cliente.exists():
            resultado["pasta_dropbox"] = str(pasta_cliente)
            arquivos_pasta = list(pasta_cliente.iterdir())
            
            # Buscar Sentença de Homologação
            for f in arquivos_pasta:
                if f.is_file() and f.suffix.lower() == ".pdf":
                    fn_norm = normalizar_texto(f.name)
                    if "SENTEN" in fn_norm or "HOMOLOGA" in fn_norm:
                        resultado["tem_sentenca"] = True
                        resultado["arquivo_sentenca"] = str(f.resolve())
                        resultado["documentos_encontrados"].append(f.name)
                        break

            # Buscar Termo / Ata de Audiência
            termo_pdf = None
            for f in arquivos_pasta:
                if f.is_file() and f.suffix.lower() == ".pdf":
                    fn_norm = normalizar_texto(f.name)
                    if any(k in fn_norm for k in ["TERMO", "AUDI", "ACORDO", "ATA"]) and not ("COMP" in fn_norm or "SENTEN" in fn_norm):
                        termo_pdf = f
                        resultado["documentos_encontrados"].append(f.name)
                        break

            # 3. Cruzar informações com o texto do PDF da ata/termo
            if termo_pdf:
                try:
                    doc = pymupdf.open(termo_pdf)
                    texto_completo = ""
                    for p in doc:
                        texto_completo += p.get_text() + "\n"
                    doc.close()

                    # Validação do valor do acordo no texto
                    # Se valor_acordo_str estiver no texto (ex: 22.219,22)
                    if valor_acordo_str and valor_acordo_str in texto_completo:
                        resultado["validacao_pdf_notas"].append(f"Valor do acordo ({valor_acordo_str}) confirmado no PDF.")
                    
                    # Validação de parcelas no texto (ex: '24' junto a prestações/parcelas)
                    qtd = resultado["qtd_parcelas"]
                    if qtd > 0 and (f"{qtd} prestac" in normalizar_texto(texto_completo) or f"{qtd} parcel" in normalizar_texto(texto_completo) or f"{qtd}X" in normalizar_texto(texto_completo)):
                        resultado["validacao_pdf_notas"].append(f"Quantidade de parcelas ({qtd}) confirmada no PDF.")

                    # Validação de valor de parcela no texto
                    vparc = resultado["valor_parcela"]
                    if vparc and vparc in texto_completo:
                        resultado["validacao_pdf_notas"].append(f"Valor da parcela ({vparc}) confirmado no PDF.")

                    # Processo no PDF caso não estivesse na planilha
                    if not resultado["processo"]:
                        proc_extraido = limpar_processo(texto_completo)
                        if proc_extraido:
                            resultado["processo"] = proc_extraido
                            resultado["validacao_pdf_notas"].append(f"Processo extraído do PDF: {proc_extraido}")

                except Exception as e_pdf:
                    resultado["validacao_pdf_notas"].append(f"Erro ao ler PDF do termo: {e_pdf}")

        else:
            resultado["validacao_pdf_notas"].append("Pasta do cliente não encontrada no Dropbox.")

        resultado["sucesso"] = True
        return resultado
