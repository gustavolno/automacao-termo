import os
import sys
import subprocess
from pathlib import Path

def matar_processo_antigo():
    """Fecha instâncias anteriores do GeradorTermos.exe que possam estar travando o arquivo em dist."""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/F", "/IM", "GeradorTermos.exe"], capture_output=True)
        except Exception:
            pass

def compilar():
    print("=" * 60)
    print("INICIANDO COMPILACAO DO GERADORTERMOS.EXE")
    print("=" * 60)

    # Garante que qualquer instância anterior aberta em segundo plano seja encerrada
    matar_processo_antigo()

    modulo_dir = Path(__file__).resolve().parent
    raiz_dir = modulo_dir.parent
    modelos_dir = modulo_dir / "modelos"

    if not modelos_dir.exists():
        print(f"[ERRO] Diretorio de modelos nao encontrado: {modelos_dir}")
        sys.exit(1)

    add_data_modelos = f"{modelos_dir};modelos"
    add_data_modulo = f"{modulo_dir};gerador_termos"

    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--noconsole",
        "--onefile",
        "--clean",
        "--name", "GeradorTermos",
        "--distpath", str(raiz_dir / "dist"),
        # Usar TEMP local para evitar lock do OneDrive na pasta build
        "--workpath", str(Path(os.environ.get("TEMP", "C:/Temp")) / "pyi_build_termos"),
        "--specpath", str(modulo_dir),
        "--add-data", add_data_modelos,
        "--add-data", add_data_modulo,
        # interface.py importa logo_b64 (pasta compartilhado/) e parser_acordo (esta pasta)
        # via sys.path; o PyInstaller só os inclui se essas pastas estiverem no caminho de análise.
        "--paths", str(raiz_dir / "compartilhado"),
        "--paths", str(modulo_dir),
        "--hidden-import", "logo_b64",
        "--hidden-import", "parser_acordo",
        "--hidden-import", "num2words",
        "--hidden-import", "docxtpl",
        "--hidden-import", "docx",
        "--hidden-import", "pdfplumber",
        "--hidden-import", "pypdf",
        "--hidden-import", "tkinter",
        "--hidden-import", "ctypes",
        str(modulo_dir / "interface.py")
    ]

    print(f"Executando comando:\n{' '.join(cmd)}\n")
    resultado = subprocess.run(cmd, cwd=str(raiz_dir))

    if resultado.returncode == 0:
        exe_path = raiz_dir / "dist" / "GeradorTermos.exe"
        if exe_path.exists():
            size_mb = round(exe_path.stat().st_size / (1024 * 1024), 2)
            print("=" * 60)
            print(f"[SUCESSO] Executavel compilado com exito!")
            print(f"Caminho: {exe_path.resolve()}")
            print(f"Tamanho: {size_mb} MB")
            print("=" * 60)
        else:
            print("[AVISO] PyInstaller concluiu com codigo 0, mas dist/GeradorTermos.exe nao foi localizado.")
    else:
        print(f"[ERRO] Falha na compilacao. Codigo de saida: {resultado.returncode}")
        sys.exit(resultado.returncode)

if __name__ == "__main__":
    compilar()
