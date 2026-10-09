"""Login manual (com reCAPTCHA) compartilhado pelos serviços do Global Office.

Para o reCAPTCHA confiar no navegador do robô, a janela de login usa:
  - o Google Chrome instalado na máquina (não o Chromium do Playwright);
  - um perfil PERSISTENTE (cookies/histórico sobrevivem entre logins);
  - sem o sinal de automação (navigator.webdriver / barra "controlado por software");
  - sem User-Agent forçado (o do próprio Chrome, coerente com a versão real).
"""
from pathlib import Path
from typing import Callable

from baixar_boletos.config import (
    USER_DATA_DIR,
    GLOBAL_OFFICE_URL,
    GLOBAL_OFFICE_LOGIN,
    GLOBAL_OFFICE_USER,
    GLOBAL_OFFICE_PASS,
    STATE_FILE,
    USER_AGENT_FILE,
)

PERFIL_CHROME = USER_DATA_DIR / "chrome_profile"

_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--start-maximized",
]


def _abrir_contexto_persistente(pw):
    PERFIL_CHROME.mkdir(parents=True, exist_ok=True)
    kwargs = dict(
        user_data_dir=str(PERFIL_CHROME),
        headless=False,
        chromium_sandbox=True,  # sem isso o Chrome exibe o aviso de "--no-sandbox"
        args=_ARGS,
        ignore_default_args=["--enable-automation"],
        no_viewport=True,
    )
    try:
        return pw.chromium.launch_persistent_context(channel="chrome", **kwargs), "Google Chrome"
    except Exception:
        return pw.chromium.launch_persistent_context(**kwargs), "Chromium do Playwright"


def login_manual(pw, log: Callable[[str], None]) -> None:
    """Abre o login, preenche as credenciais e espera você resolver o reCAPTCHA.
    Ao concluir, grava a sessão em STATE_FILE."""
    context, nome_navegador = _abrir_contexto_persistente(pw)
    log(f"Abrindo {nome_navegador} com perfil persistente para o login...")
    try:
        # Descarta só a sessão antiga do Global Office (pode estar inválida no servidor);
        # cookies do Google (reputação do reCAPTCHA) são mantidos.
        try:
            context.clear_cookies(domain="globalofficeweb.com.br")
        except Exception:
            pass

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(GLOBAL_OFFICE_URL)
        # Só espera "sumir" o login depois de ele ter aparecido (evita falso sucesso)
        page.locator("#EDTLOGIN").wait_for(state="visible", timeout=30000)

        for seletor, valor in (
            ("#EDTLOGIN", GLOBAL_OFFICE_LOGIN),
            ("#EDTUSUARIO", GLOBAL_OFFICE_USER),
            ("#EDTSENHA", GLOBAL_OFFICE_PASS),
        ):
            if valor:
                try:
                    page.locator(seletor).fill(valor)
                except Exception:
                    pass

        log("Por favor, resolva o reCAPTCHA na janela aberta do navegador e clique em ENTRAR.")
        page.locator("#EDTLOGIN").wait_for(state="hidden", timeout=0)
        page.wait_for_timeout(3000)
        context.storage_state(path=STATE_FILE)
        # A sessão só vale com o mesmo User-Agent do login: grava para os serviços reusarem
        USER_AGENT_FILE.write_text(page.evaluate("navigator.userAgent"), encoding="utf-8")
        log("Login efetuado com sucesso!")
        log(f"Sessão salva com sucesso em '{STATE_FILE}'.")
    finally:
        context.close()
