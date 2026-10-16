"""Cálculo dos boletos de parcela que faltam no Global Office.

Regra (aviso "Ficha financeira não atualizada / Não há valores em aberto"):
o acordo não pode ser subido, então os boletos que faltam são criados em
Boletos > +NOVO. O campo Repetição é o TOTAL de boletos (Repetição 19 cria 19, não 20;
0 cria 1): ver repeticao_para()
e Vencimento = o primeiro vencimento que ainda não existe.

Só parcelas entram na conta (a entrada é ignorada). Boletos em aberto e quitados contam
como existentes; cancelados não.
"""
import calendar
from datetime import date, datetime
from typing import Iterable, List, Optional


def _somar_meses(d: date, meses: int) -> date:
    m = d.month - 1 + meses
    ano, mes = d.year + m // 12, m % 12 + 1
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def _para_data(v) -> Optional[date]:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.strptime(str(v).strip(), "%d/%m/%Y").date()
    except Exception:
        return None


def repeticao_para(qtd_boletos: int) -> int:
    """Valor do campo Repetição para criar qtd_boletos boletos. No Global Office a Repetição
    é o total de boletos (14/10/2026: Repetição 19 criou 19). Um boleto só: 0 (já testado)."""
    return qtd_boletos if qtd_boletos > 1 else 0


def cronograma_parcelas(primeiro_vencimento, qtd_parcelas: int) -> List[date]:
    """Vencimentos esperados das parcelas: o primeiro e os meses seguintes, no mesmo dia."""
    inicio = _para_data(primeiro_vencimento)
    if not inicio or qtd_parcelas <= 0:
        return []
    return [_somar_meses(inicio, k) for k in range(qtd_parcelas)]


def calcular_faltantes(primeiro_vencimento, qtd_parcelas: int, vencimentos_existentes: Iterable,
                       a_partir: Optional[date] = None) -> dict:
    """Compara o cronograma com os vencimentos que já existem no sistema (mês/ano).

    Devolve:
      faltantes:  vencimentos esperados que não existem
      vencimento: primeiro faltante (vai no campo VENCIMENTO)
      repeticao:  repeticao_para(len(faltantes)) (vai no campo REPETIÇÃO)
      seguro:     True só se os faltantes forem meses CONSECUTIVOS. A Repetição gera meses
                  seguidos; com buracos no meio ela recriaria parcelas que já existem.
      vencidos:   parcelas que faltam mas já venceram (antes de `a_partir`). O Global Office
                  não aceita boleto com vencimento no passado (erro 5002), então ficam de fora.
    """
    esperado = cronograma_parcelas(primeiro_vencimento, qtd_parcelas)
    existentes = {(d.year, d.month) for d in (_para_data(v) for v in vencimentos_existentes) if d}
    faltantes = [d for d in esperado if (d.year, d.month) not in existentes]
    vencidos = [d for d in faltantes if a_partir and d < a_partir]
    faltantes = [d for d in faltantes if d not in vencidos]

    seguro = all(_somar_meses(faltantes[0], i) == f for i, f in enumerate(faltantes)) if faltantes else True
    return {
        "esperados": len(esperado),
        "existentes": len(esperado) - len(faltantes) - len(vencidos),
        "faltantes": faltantes,
        "vencidos": vencidos,
        "vencimento": faltantes[0].strftime("%d/%m/%Y") if faltantes else None,
        "repeticao": repeticao_para(len(faltantes)),
        "seguro": seguro,
    }
