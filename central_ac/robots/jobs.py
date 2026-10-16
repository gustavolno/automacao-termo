"""Gerenciador de robôs: um por vez (o Global Office aceita uma sessão por login)."""
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from typing import Optional

from .. import settings, store
from .protocolo import MARCA

ATIVOS = ("rodando", "aguardando")
ID_JOB = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{4}$")


class Ocupado(Exception):
    def __init__(self, job):
        super().__init__(f"Já existe um robô em andamento: {job.titulo}")
        self.job = job


class Job:
    def __init__(self, tarefa: str, titulo: str, params: dict):
        self.id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.tarefa, self.titulo, self.params = tarefa, titulo, params
        self.estado = "rodando"
        self.inicio = store.agora()
        self.fim: Optional[str] = None
        self.resultado = None
        self.eventos: list = []
        self.pergunta: Optional[dict] = None
        self.proc: Optional[subprocess.Popen] = None
        self.arquivo = settings.JOBS_DIR / f"{self.id}.jsonl"

    def resumo(self) -> dict:
        return {"id": self.id, "tarefa": self.tarefa, "titulo": self.titulo, "estado": self.estado,
                "inicio": self.inicio, "fim": self.fim, "params": self.params,
                "resultado": self.resultado, "pergunta": self.pergunta, "eventos": len(self.eventos)}


class Gerenciador:
    def __init__(self):
        self._lock = threading.RLock()
        self._jobs: dict = {}
        self._escrita = threading.Lock()

    def atual(self) -> Optional[Job]:
        """O robô em andamento. Conta também o processo ainda vivo depois do 'fim': ele ainda está
        fechando o navegador, e um segundo robô agora brigaria pela única sessão do Global Office."""
        with self._lock:
            return next((j for j in self._jobs.values()
                         if j.estado in ATIVOS or (j.proc is not None and j.proc.poll() is None)), None)

    def iniciar(self, tarefa: str, params: dict, titulo: str) -> Job:
        with self._lock:
            if (ativo := self.atual()):
                raise Ocupado(ativo)
            job = Job(tarefa, titulo, params)
            arq_params = settings.JOBS_DIR / f"{job.id}.params.json"
            arq_params.write_text(json.dumps(params, ensure_ascii=False), encoding="utf-8")
            env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
            job.proc = subprocess.Popen(
                [sys.executable, "-u", "-m", "central_ac.robots.worker", tarefa, str(arq_params)],
                cwd=settings.RAIZ, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self._jobs[job.id] = job
        store.salvar_job(job.resumo())
        threading.Thread(target=self._ler, args=(job,), daemon=True, name=f"job-{job.id}").start()
        return job

    # ── leitura da saída do robô ──
    def _ler(self, job: Job):
        for linha in job.proc.stdout:
            linha = linha.rstrip("\n")
            if linha.startswith(MARCA):
                try:
                    self._evento(job, json.loads(linha[len(MARCA):]))
                except json.JSONDecodeError:
                    self._evento(job, {"t": "log", "nivel": "INFO", "msg": linha})
            elif linha.strip():
                self._evento(job, {"t": "log", "nivel": "DEBUG", "msg": linha})
        job.proc.wait()
        if job.estado in ATIVOS:   # o robô morreu sem dizer "fim"
            self._evento(job, {"t": "fim", "estado": "falhou",
                               "resultado": {"erro": f"o robô encerrou de forma inesperada (código {job.proc.returncode})"}})
        # os parâmetros têm nomes e e-mails de clientes: não precisam ficar em disco depois do fim
        (settings.JOBS_DIR / f"{job.id}.params.json").unlink(missing_ok=True)

    def _evento(self, job: Job, ev: dict):
        ev["ts"] = time.strftime("%H:%M:%S")
        with self._lock:
            ev["n"] = len(job.eventos)
            job.eventos.append(ev)
            if ev["t"] == "ask":
                job.estado, job.pergunta = "aguardando", ev
            elif ev["t"] == "fim":
                job.estado, job.resultado, job.fim, job.pergunta = ev["estado"], ev.get("resultado"), store.agora(), None
        with self._escrita, open(job.arquivo, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        if ev["t"] in ("ask", "fim"):
            store.salvar_job(job.resumo())

    # ── comandos para o robô ──
    def _enviar(self, job: Job, msg: dict):
        try:
            job.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            job.proc.stdin.flush()
        except (OSError, ValueError):
            pass

    def responder(self, job_id: str, pergunta_id: str, resp: str):
        job = self.obter(job_id)
        if not job or not job.pergunta or job.pergunta["id"] != pergunta_id:
            raise KeyError("pergunta não está mais pendente")
        self._enviar(job, {"t": "resp", "id": pergunta_id, "resp": resp})
        with self._lock:
            job.estado, job.pergunta = "rodando", None
        self._evento(job, {"t": "resp", "id": pergunta_id, "resp": resp})

    def parar(self, job_id: str):
        job = self.obter(job_id)
        if not job or job.estado not in ATIVOS:
            return
        self._evento(job, {"t": "log", "nivel": "WARNING",
                           "msg": "PARAR solicitado: o robô para no próximo passo seguro (nada é gravado pela metade)."})
        self._enviar(job, {"t": "parar"})
        timer = threading.Timer(120, self._matar, args=(job,))
        timer.daemon = True     # não segura o encerramento da Central
        timer.start()

    def _matar(self, job: Job):
        """Se o robô não parou sozinho: encerra ele e os navegadores filhos (kill() sozinho deixaria o Chromium)."""
        if job.proc and job.proc.poll() is None:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(job.proc.pid), "/T", "/F"], capture_output=True)
            else:
                job.proc.kill()

    # ── consulta ──
    def obter(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def eventos(self, job_id: str, desde: int = 0) -> Optional[list]:
        job = self.obter(job_id)
        if job:
            with self._lock:
                return job.eventos[desde:]
        if not ID_JOB.match(job_id):     # o texto vem da URL: nunca vira caminho de arquivo sem conferir
            return None
        arq = settings.JOBS_DIR / f"{job_id}.jsonl"
        if not arq.exists():
            return None
        eventos = []
        with open(arq, encoding="utf-8") as f:
            for linha in f:
                try:
                    eventos.append(json.loads(linha))
                except json.JSONDecodeError:
                    continue         # linha cortada por uma queda no meio da escrita
        return eventos[desde:]

    def limpar_antigos(self, dias: int = 90):
        """Retenção: registros de execuções (têm nomes e e-mails de clientes) somem depois de `dias`."""
        corte = time.time() - dias * 86400
        for arq in settings.JOBS_DIR.glob("*.jsonl"):
            if arq.stat().st_mtime < corte:
                arq.unlink(missing_ok=True)


gerenciador = Gerenciador()
