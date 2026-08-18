import logging
import os
from datetime import datetime
from pathlib import Path
from gerador_boletos.config import PASTA_LOGS

def configurar_logger():
    # Cria o logger principal
    logger = logging.getLogger("GeradorBoletos")
    logger.setLevel(logging.INFO)

    # Evita adicionar múltiplos handlers se a função for chamada novamente
    if not logger.handlers:
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%d/%m/%Y %H:%M:%S'
        )

        # File Handler (Gera um arquivo por dia)
        hoje = datetime.now().strftime("%Y-%m-%d")
        log_file = Path(PASTA_LOGS) / f"boletos_{hoje}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        import sys
        # Console Handler (Só adiciona se houver um console disponível)
        if sys.stdout is not None and sys.stderr is not None:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

    return logger

log = configurar_logger()
