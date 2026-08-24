"""
Mapa de Tribunais Brasileiros - Baseado na Numeração Única CNJ
Formato: NNNNNNN-DD.AAAA.J.TR.OOOO
 - J=8 → Justiça Estadual (TJs)
 - TR = Código do Tribunal (01=TJAC, 02=TJAL, etc)
 - J=4 → Justiça Federal
 - J=5 → Justiça do Trabalho
"""

# Mapa: (J, TR) → informações do tribunal
# J=8 = Justiça Estadual (TJs)
TRIBUNAIS = {
    # ─── TJs Estaduais (J=8) ───────────────────────────────────
    ("8", "01"): {"nome": "TJAC", "estado": "Acre",          "sistema": "pje",   "url_base": "https://pje.tjac.jus.br"},
    ("8", "02"): {"nome": "TJAL", "estado": "Alagoas",       "sistema": "pje",   "url_base": "https://pje1g.tjal.jus.br"},
    ("8", "03"): {"nome": "TJAP", "estado": "Amapá",         "sistema": "pje",   "url_base": "https://pje.tjap.jus.br"},
    ("8", "04"): {"nome": "TJAM", "estado": "Amazonas",      "sistema": "pje",   "url_base": "https://pje.tjam.jus.br"},
    ("8", "05"): {"nome": "TJBA", "estado": "Bahia",         "sistema": "pje",   "url_base": "https://pje.tjba.jus.br"},
    ("8", "06"): {"nome": "TJCE", "estado": "Ceará",         "sistema": "pje",   "url_base": "https://pje.tjce.jus.br"},
    ("8", "07"): {"nome": "TJDF", "estado": "Dist. Federal", "sistema": "pje",   "url_base": "https://pje.tjdft.jus.br"},
    ("8", "08"): {"nome": "TJES", "estado": "Espírito Santo","sistema": "pje",   "url_base": "https://pje.tjes.jus.br"},
    ("8", "09"): {"nome": "TJGO", "estado": "Goiás",         "sistema": "pje",   "url_base": "https://pje.tjgo.jus.br"},
    ("8", "10"): {"nome": "TJMA", "estado": "Maranhão",      "sistema": "pje",   "url_base": "https://pje.tjma.jus.br"},
    ("8", "11"): {"nome": "TJMT", "estado": "Mato Grosso",   "sistema": "pje",   "url_base": "https://pje.tjmt.jus.br"},
    ("8", "12"): {"nome": "TJMS", "estado": "Mato Grosso Sul","sistema": "pje",  "url_base": "https://pje.tjms.jus.br"},
    ("8", "13"): {"nome": "TJMG", "estado": "Minas Gerais",  "sistema": "eproc", "url_base": "https://eproc.tjmg.jus.br"},
    ("8", "14"): {"nome": "TJPA", "estado": "Pará",          "sistema": "pje",   "url_base": "https://pje.tjpa.jus.br"},
    ("8", "15"): {"nome": "TJPB", "estado": "Paraíba",       "sistema": "pje",   "url_base": "https://pje.tjpb.jus.br"},
    ("8", "16"): {"nome": "TJPR", "estado": "Paraná",        "sistema": "pje",   "url_base": "https://projudi.tjpr.jus.br"},
    ("8", "17"): {"nome": "TJPE", "estado": "Pernambuco",    "sistema": "pje",   "url_base": "https://pje.tjpe.jus.br"},
    ("8", "18"): {"nome": "TJPI", "estado": "Piauí",         "sistema": "pje",   "url_base": "https://pje.tjpi.jus.br"},
    ("8", "19"): {"nome": "TJRJ", "estado": "Rio de Janeiro","sistema": "pje",   "url_base": "https://pje.tjrj.jus.br"},
    ("8", "20"): {"nome": "TJRN", "estado": "Rio Grande Norte","sistema": "pje", "url_base": "https://pje.tjrn.jus.br"},
    ("8", "21"): {"nome": "TJRS", "estado": "Rio Grande Sul", "sistema": "eproc","url_base": "https://eproc.tjrs.jus.br"},
    ("8", "22"): {"nome": "TJRO", "estado": "Rondônia",      "sistema": "pje",   "url_base": "https://pje.tjro.jus.br"},
    ("8", "23"): {"nome": "TJRR", "estado": "Roraima",       "sistema": "pje",   "url_base": "https://pje.tjrr.jus.br"},
    ("8", "24"): {"nome": "TJSC", "estado": "Santa Catarina","sistema": "eproc", "url_base": "https://eproc1g.tjsc.jus.br"},
    ("8", "26"): {"nome": "TJSP", "estado": "São Paulo",     "sistema": "esaj",  "url_base": "https://esaj.tjsp.jus.br"},
    ("8", "25"): {"nome": "TJSE", "estado": "Sergipe",       "sistema": "pje",   "url_base": "https://pje.tjse.jus.br"},
    ("8", "27"): {"nome": "TJTO", "estado": "Tocantins",     "sistema": "pje",   "url_base": "https://pje.tjto.jus.br"},
}


def identificar_tribunal(numero_processo: str) -> dict:
    """
    Recebe o número CNJ do processo e retorna o tribunal correspondente.
    Ex: "5037068-10.2025.8.24.0023" → TJSC (J=8, TR=24)
    """
    import re
    # Remove pontos e traços e extrai os campos J e TR
    match = re.match(r'(\d{7})-(\d{2})\.(\d{4})\.(\d)\.(\d{2})\.(\d{4})', numero_processo.strip())
    if not match:
        return None
    
    j = match.group(4)
    tr = match.group(5)
    
    info = TRIBUNAIS.get((j, tr))
    if info:
        return {**info, "codigo_j": j, "codigo_tr": tr}
    
    return {
        "nome": f"Tribunal desconhecido (J={j}, TR={tr})",
        "sistema": "desconhecido",
        "url_base": None
    }
