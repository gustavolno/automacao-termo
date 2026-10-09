import os
import sys
import subprocess
from pathlib import Path

def matar_processo_antigo():
    """Fecha instâncias anteriores do BaixarBoletos.exe que possam estar travando o arquivo em dist."""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/F", "/IM", "BaixarBoletos.exe"], capture_output=True)
        except Exception:
            pass

def compilar():
    print("=" * 60)
    print("INICIANDO COMPILACAO DO BAIXARBOLETOS.EXE")
    print("=" * 60)

    # Garante que qualquer instância anterior aberta em segundo plano seja encerrada
    matar_processo_antigo()

    modulo_dir = Path(__file__).resolve().parent
    raiz_dir = modulo_dir.parent

    import playwright
    driver_dir = Path(playwright.__file__).parent / "driver"
    
    if not driver_dir.exists():
        print(f"[ERRO] Diretorio do driver do Playwright nao encontrado: {driver_dir}")
        sys.exit(1)

    add_data_playwright = f"{driver_dir};playwright/driver"
    add_data_modulo = f"{modulo_dir};baixar_boletos"

    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--clean",
        "--name", "BaixarBoletos",
        "--distpath", str(raiz_dir / "dist"),
        # Usar TEMP local para evitar lock do OneDrive na pasta build
        "--workpath", str(Path(os.environ.get("TEMP", "C:/Temp")) / "pyi_build_boletos"),
        "--specpath", str(modulo_dir),
        "--add-data", add_data_playwright,
        "--add-data", add_data_modulo,
        "--hidden-import", "playwright",
        "--hidden-import", "dotenv",
        "--hidden-import", "tkinter",
        "--hidden-import", "ctypes",
        "--hidden-import", "pymupdf",
        "--hidden-import", "fitz",
        "--hidden-import", "openpyxl",
        "--hidden-import", "baixar_boletos.email_service",
        "--hidden-import", "baixar_boletos.planilha_sync",
        "--hidden-import", "baixar_boletos.login_helper",
        "--hidden-import", "baixar_boletos.boletos_faltantes",
        str(modulo_dir / "gui.py")
    ]

    print(f"Executando comando:\n{' '.join(cmd)}\n")
    resultado = subprocess.run(cmd, cwd=str(raiz_dir))

    if resultado.returncode == 0:
        exe_path = raiz_dir / "dist" / "BaixarBoletos.exe"
        if exe_path.exists():
            size_mb = round(exe_path.stat().st_size / (1024 * 1024), 2)
            print("=" * 60)
            print(f"[SUCESSO] Executavel compilado com exito!")
            print(f"Caminho: {exe_path.resolve()}")
            print(f"Tamanho: {size_mb} MB")
            print("=" * 60)
        else:
            print("[AVISO] PyInstaller concluiu com codigo 0, mas dist/BaixarBoletos.exe nao foi localizado.")
    else:
        print(f"[ERRO] Falha na compilacao. Codigo de saida: {resultado.returncode}")
        sys.exit(resultado.returncode)

if __name__ == "__main__":
    compilar()
