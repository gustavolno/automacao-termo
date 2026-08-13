"""
automacao_juriscalc.py — Robô que preenche o site JurisCalc (TJDFT) automaticamente
com as parcelas lidas de um PDF da GEAP/IPASEP e gera o PDF de cálculo oficial.

Fluxo:
  1. Lê o PDF da GEAP com o parser_geap
  2. Abre Chromium (invisível por padrão)
  3. Navega até https://juriscalc.tjdft.jus.br/publico/calculos
  4. Adiciona cada parcela (valor, data, descrição)
  5. Adiciona Multa de 2%
  6. Adiciona Honorários de 10%
  7. Clica em Calcular
  8. Usa a API do Playwright para salvar o resultado como PDF
"""

import os
import sys
import time
from datetime import datetime
from parser_geap import extrair_parcelas, Parcela
from typing import List, Callable, Optional

URL_JURISCALC = "https://juriscalc.tjdft.jus.br/publico/calculos"


def _configurar_playwright_path():
    """
    Garante que o Playwright encontre o Chromium mesmo quando rodando
    como executável PyInstaller (.exe).
    Aponta PLAYWRIGHT_BROWSERS_PATH para a pasta instalada em AppData.
    """
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    browsers_path = os.path.join(local_appdata, "ms-playwright")
    if os.path.isdir(browsers_path):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path
    # Evita que o Playwright tente baixar o browser ao não encontrá-lo
    os.environ.setdefault("PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS", "1")


def rodar_automacao(
    caminho_pdf: str,
    caminho_saida: str,
    multa_pct: float = 2.0,
    honorarios_pct: float = 10.0,
    visivel: bool = False,
    callback_progresso: Optional[Callable[[str, int], None]] = None,
) -> str:
    """
    Executa a automação completa e retorna o caminho do PDF gerado.
    
    Args:
        caminho_pdf: Caminho para o PDF da GEAP/IPASEP
        caminho_saida: Caminho onde o PDF resultado será salvo
        multa_pct: Percentual de multa (padrão: 2.0%)
        honorarios_pct: Percentual de honorários (padrão: 10.0%)
        visivel: Se True, abre o navegador visível (para depuração)
        callback_progresso: Função (mensagem, porcentagem) para atualizar progresso na UI
    
    Returns:
        Caminho do PDF gerado
    """
    from playwright.sync_api import sync_playwright
    
    def prog(msg: str, pct: int = 0):
        if callback_progresso:
            callback_progresso(msg, pct)
        print(f"[{pct:3d}%] {msg}")
    
    # --- ETAPA 1: Ler o PDF ---
    prog("📄 Lendo parcelas do PDF...", 5)
    parcelas = extrair_parcelas(caminho_pdf)
    if not parcelas:
        raise ValueError("Nenhuma parcela encontrada no PDF. Verifique se é uma Ficha Financeira da GEAP/IPASEP.")
    prog(f"✅ {len(parcelas)} parcelas encontradas.", 10)
    
    _configurar_playwright_path()
    
    with sync_playwright() as p:
        # --- ETAPA 2: Abrir navegador ---
        prog("Abrindo navegador...", 12)
        try:
            browser = p.chromium.launch(
                headless=not visivel,
                timeout=60000,  # 60s para abrir
            )
        except Exception as e:
            raise RuntimeError(
                f"Nao foi possivel abrir o navegador Chromium.\n"
                f"Verifique se o Playwright esta instalado corretamente.\n\n"
                f"Solucao: abra o PowerShell na pasta do projeto e execute:\n"
                f"  .\\venv\\Scripts\\playwright install chromium\n\n"
                f"Detalhes do erro: {e}"
            ) from e
        context = browser.new_context(
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
        )
        page = context.new_page()
        
        # --- ETAPA 3: Navegar ---
        prog("🔗 Acessando JurisCalc (TJDFT)...", 15)
        page.goto(URL_JURISCALC, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        
        # Clicar em "Novo cálculo" se existir
        novo_calc = page.locator("button:has-text('Novo cálculo')")
        if novo_calc.count() > 0:
            novo_calc.first.click()
            page.wait_for_timeout(1000)
        
        # --- ETAPA 4: Adicionar parcelas ---
        total = len(parcelas)
        for idx, parcela in enumerate(parcelas):
            pct = 15 + int((idx / total) * 55)
            prog(f"➕ Adicionando parcela {idx + 1}/{total}: R$ {parcela.valor} em {parcela.data}", pct)
            _adicionar_valor(page, parcela)
            page.wait_for_timeout(400)
        
        prog("✅ Todas as parcelas adicionadas.", 72)
        
        # --- ETAPA 5: Adicionar Multa ---
        prog(f"⚖️  Configurando Multa de {multa_pct:.2f}%...", 75)
        _adicionar_multa(page, multa_pct)
        page.wait_for_timeout(600)
        
        # --- ETAPA 6: Adicionar Honorários ---
        prog(f"💼 Configurando Honorários de {honorarios_pct:.2f}%...", 80)
        _adicionar_honorarios(page, honorarios_pct)
        page.wait_for_timeout(600)
        
        # --- ETAPA 7: Calcular ---
        prog("🧮 Clicando em Calcular...", 85)
        page.locator("button:has-text('Calcular')").first.click()
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle", timeout=15000)
        
        # --- ETAPA 8: Salvar PDF ---
        prog("💾 Salvando PDF do resultado...", 92)
        os.makedirs(os.path.dirname(caminho_saida) or ".", exist_ok=True)
        page.pdf(
            path=caminho_saida,
            format="A4",
            print_background=True,
            margin={"top": "15mm", "bottom": "15mm", "left": "10mm", "right": "10mm"},
        )
        
        browser.close()
    
    prog(f"✅ PDF gerado com sucesso!", 100)
    return caminho_saida


def _adicionar_valor(page, parcela: Parcela):
    """Preenche e adiciona um valor no formulário do JurisCalc."""
    # Campo Valor (placeholder "R$")
    valor_input = page.locator("input[placeholder='R$']").first
    valor_input.click()
    valor_input.fill(parcela.valor)
    
    # Campo Data
    data_input = page.locator("input[placeholder='Data do valor']").first
    data_input.click()
    data_input.fill("")
    data_input.type(parcela.data)
    
    # Campo Descrição
    desc_input = page.locator("input[placeholder='Descrição (opcional)']").first
    desc_input.click()
    desc_input.fill(parcela.descricao)
    
    # Botão Adicionar
    page.locator("button:has-text('Adicionar valor')").first.click()


def _adicionar_multa(page, pct: float):
    """Configura e adiciona a multa percentual."""
    # Rolar até a seção de Multa
    multa_btn_add = page.locator("button:has-text('Adicionar multa')").first
    multa_btn_add.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    
    # Selecionar o radio "Percentual" (tipoDeMulta0) se não estiver selecionado
    radio = page.locator("#tipoDeMulta0")
    if radio.count() > 0 and not radio.is_checked():
        radio.click()
        page.wait_for_timeout(200)
    
    # Preencher o percentual
    pct_str = f"{pct:.2f}".replace(".", ",")
    pct_input = page.locator("input[placeholder='0,00%']").first
    pct_input.click()
    pct_input.triple_click()
    pct_input.fill(pct_str)
    
    # Clicar em Adicionar multa
    multa_btn_add.click()


def _adicionar_honorarios(page, pct: float):
    """Configura e adiciona os honorários percentuais."""
    # Rolar até a seção de Honorários
    hon_btn_add = page.locator("button:has-text('Adicionar honorários')").first
    hon_btn_add.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    
    # Selecionar radio "Honorário percentual" (tipoHonorarios0)
    radio = page.locator("#tipoHonorarios0")
    if radio.count() > 0 and not radio.is_checked():
        radio.click()
        page.wait_for_timeout(200)
    
    # Preencher o percentual (segundo campo placeholder='0,00%' após o de multa)
    pct_str = f"{pct:.2f}".replace(".", ",")
    pct_inputs = page.locator("input[placeholder='0,00%']")
    # O campo de honorários é o segundo (índice 1)
    if pct_inputs.count() > 1:
        campo = pct_inputs.nth(1)
    else:
        campo = pct_inputs.first
    campo.click()
    campo.triple_click()
    campo.fill(pct_str)
    
    # Clicar em Adicionar honorários
    hon_btn_add.click()


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso: python automacao_juriscalc.py <caminho_pdf_geap> [caminho_saida.pdf]")
        sys.exit(1)
    
    entrada = sys.argv[1]
    saida = sys.argv[2] if len(sys.argv) > 2 else "Calculo_JurisCalc.pdf"
    
    rodar_automacao(entrada, saida, visivel=True)
    print(f"\n✅ Arquivo salvo em: {saida}")
