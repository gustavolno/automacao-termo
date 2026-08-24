"""
Orquestrador de Tribunais - A peça principal.

Responsável por:
1. Receber o número do processo CNJ
2. Identificar automaticamente qual tribunal e qual sistema é usado
3. Abrir o navegador com sessão persistente (certificado já salvo)
4. Pausar para o usuário fazer o login/MFA no App Authenticator
5. Executar o pipeline: buscar processo → encontrar sentença → baixar PDF
"""

import os
import asyncio
from playwright.async_api import async_playwright

from .mapa_tribunais import identificar_tribunal
from .pje_adapter import PjeAdapter
from .eproc_adapter import EprocAdapter
from .esaj_adapter import EsajAdapter

# Pasta para salvar a sessão do navegador (manter login entre execuções)
SESSION_DIR = os.path.join(os.getenv('LOCALAPPDATA', 'C:\\Temp'), 'TribunalSession')

# Mapa de sistema → classe adaptadora
ADAPTADORES = {
    "pje":   PjeAdapter,
    "eproc": EprocAdapter,
    "esaj":  EsajAdapter,
}


async def consultar_tribunal(numero_processo: str, pasta_cliente: str) -> dict:
    """
    Função principal chamada pelo FastAPI.
    
    :param numero_processo: Número CNJ completo (ex: "5037068-10.2025.8.24.0023")
    :param pasta_cliente:   Caminho local no Dropbox onde o PDF será salvo
    :return: Dicionário com data_homologacao e arquivo_baixado
    """
    # 1. Identifica o tribunal com base no número CNJ
    tribunal_info = identificar_tribunal(numero_processo)
    if not tribunal_info:
        return {"erro": f"Não foi possível identificar o tribunal pelo número: {numero_processo}"}
    
    sistema = tribunal_info.get("sistema", "desconhecido")
    AdaptadorClass = ADAPTADORES.get(sistema)
    
    if not AdaptadorClass:
        return {
            "erro": f"Sistema '{sistema}' do {tribunal_info.get('nome')} ainda não tem adaptador implementado.",
            "tribunal": tribunal_info
        }
    
    print(f"[TRIBUNAL] {tribunal_info['nome']} ({tribunal_info['estado']}) → Sistema: {sistema.upper()}")
    
    # 2. Abre o navegador com sessão persistente
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=SESSION_DIR,
            headless=False,  # DEVE ser visível para MFA e certificado
            args=["--start-maximized"],
            no_viewport=True
        )
        
        page = browser.pages[0] if browser.pages else await browser.new_page()
        
        # 3. Navega para a URL de login do tribunal
        url_login = f"{tribunal_info['url_base']}/pje/login.seam" if sistema == "pje" else tribunal_info['url_base']
        
        print(f"[TRIBUNAL] Abrindo login em: {url_login}")
        await page.goto(url_login, wait_until="domcontentloaded", timeout=30000)
        
        # 4. Pausa: aguarda o usuário logar com certificado + MFA (App Authenticator)
        # Aguardamos até 2 minutos para o usuário concluir o login
        print("[TRIBUNAL] ⏳ Aguardando login com Certificado Digital e MFA (App Authenticator)...")
        print("[TRIBUNAL] Por favor, selecione seu certificado e insira o código do app no navegador.")
        
        # Detecta que o login foi concluído esperando aparecer o "Painel do Advogado"
        # (Usando as palavras-chave que aparecem APÓS o login bem-sucedido no PJe)
        INDICADORES_LOGIN = [
            "text='Painel do Advogado'",
            "text='CONSULTA PROCESSOS'",
            "text='Meus Processos'",
            "text='Localizador'",
            "text='Bem-vindo'",
        ]
        
        logado = False
        for seletor in INDICADORES_LOGIN:
            try:
                await page.wait_for_selector(seletor, timeout=120000)  # 2 minutos
                logado = True
                print(f"[TRIBUNAL] ✅ Login detectado! Iniciando busca...")
                break
            except:
                continue
        
        if not logado:
            await browser.close()
            return {"erro": "Login não detectado. Tempo limite de 2 minutos esgotado."}
        
        # 5. Executa o pipeline do adaptador
        adaptador = AdaptadorClass(page, tribunal_info, pasta_cliente)
        resultado = await adaptador.executar_pipeline(numero_processo)
        
        await browser.close()
        return resultado
