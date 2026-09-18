import os
import sys
import subprocess
from pathlib import Path

def compilar():
    print("=" * 60)
    print("INICIANDO COMPILAÇÃO DO BAIXARBOLETOS.EXE")
    print("=" * 60)

    import playwright
    driver_dir = Path(playwright.__file__).parent / "driver"
    
    if not driver_dir.exists():
        print(f"[ERRO] Diretório do driver do Playwright não encontrado: {driver_dir}")
        sys.exit(1)

    add_data_playwright = f"{driver_dir};playwright/driver"
    add_data_modulo = "baixar_boletos;baixar_boletos"

    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--clean",
        "--name", "BaixarBoletos",
        "--add-data", add_data_playwright,
        "--add-data", add_data_modulo,
        "--hidden-import", "playwright",
        "--hidden-import", "dotenv",
        "--hidden-import", "tkinter",
        "--hidden-import", "ctypes",
        "baixar_boletos_gui.py"
    ]

    print(f"Executando comando:\n{' '.join(cmd)}\n")
    resultado = subprocess.run(cmd)

    if resultado.returncode == 0:
        exe_path = Path("dist") / "BaixarBoletos.exe"
        if exe_path.exists():
            size_mb = round(exe_path.stat().st_size / (1024 * 1024), 2)
            print("=" * 60)
            print(f"[SUCESSO] Executável compilado com êxito!")
            print(f"Caminho: {exe_path.resolve()}")
            print(f"Tamanho: {size_mb} MB")
            print("=" * 60)
        else:
            print("[AVISO] PyInstaller concluiu com código 0, mas dist/BaixarBoletos.exe não foi localizado.")
    else:
        print(f"[ERRO] Falha na compilação. Código de saída: {resultado.returncode}")
        sys.exit(resultado.returncode)

if __name__ == "__main__":
    compilar()
