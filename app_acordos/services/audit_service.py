import os
import json
from datetime import datetime

LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "logs")

class AuditService:
    @staticmethod
    def log_action(cliente_nome: str, acao: str, detalhes: dict = None, status: str = "INFO"):
        """
        Registra uma ação no arquivo de log diário.
        status pode ser: INFO, ERRO, ALERTA
        """
        if not os.path.exists(LOGS_DIR):
            os.makedirs(LOGS_DIR)
            
        data_hoje = datetime.now().strftime("%Y-%m-%d")
        arquivo_log = os.path.join(LOGS_DIR, f"audit_{data_hoje}.log")
        
        hora_agora = datetime.now().strftime("%H:%M:%S")
        
        log_entry = {
            "timestamp": f"{data_hoje} {hora_agora}",
            "cliente": cliente_nome,
            "status": status,
            "acao": acao,
            "detalhes": detalhes or {}
        }
        
        try:
            with open(arquivo_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"Erro ao escrever no log de auditoria: {e}")
