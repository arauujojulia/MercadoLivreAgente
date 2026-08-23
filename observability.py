"""
Integração com Weights & Biases (W&B) para rastrear:
- Execuções do agente (sync, forecast, chamadas ao LLM).
- Métricas de acurácia do forecast (MAE/RMSE) via backtesting contínuo.
- Erros e tempo de resposta.

Cada usuário final usa a própria WANDB_API_KEY (configurada nas
preferências do app), então cada instalação gera seu próprio histórico de
runs no W&B — não há dado de um usuário misturado com o de outro.
"""

from __future__ import annotations

import functools
import time
from typing import Callable

import wandb

from config.settings import get_secret

_WANDB_PROJECT = "agente-ml-mercadolivre"
_active_run = None


def _ensure_login() -> bool:
    api_key = get_secret("wandb_api_key")
    if not api_key:
        return False
    wandb.login(key=api_key, relogin=False)
    return True


def start_run(run_name: str, config: dict | None = None):
    global _active_run
    if not _ensure_login():
        _active_run = None
        return None
    _active_run = wandb.init(project=_WANDB_PROJECT, name=run_name, config=config or {}, reinit=True)
    return _active_run


def log_metrics(metrics: dict) -> None:
    if _active_run is not None:
        wandb.log(metrics)


def finish_run() -> None:
    global _active_run
    if _active_run is not None:
        _active_run.finish()
        _active_run = None


def track_execution(step_name: str) -> Callable:
    """
    Decorator que envolve uma função do agente (ex: sincronizar, gerar
    forecast, chamar o LLM) e registra tempo de execução + sucesso/erro
    no W&B, sem exigir que cada módulo saiba de W&B internamente.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                log_metrics({f"{step_name}.duration_s": time.time() - start, f"{step_name}.success": 1})
                return result
            except Exception as exc:
                log_metrics({f"{step_name}.duration_s": time.time() - start, f"{step_name}.success": 0})
                wandb.alert(title=f"Erro em {step_name}", text=str(exc)) if _active_run else None
                raise

        return wrapper

    return decorator
