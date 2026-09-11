"""Acesso aos arquivos de config/*.toml.

Principio 5 do CLAUDE.md: pesos e textos ficam fora do codigo, para o operador
calibrar sozinho.
"""

import tomllib
from functools import cache
from pathlib import Path

RAIZ_DO_PROJETO = Path(__file__).resolve().parents[3]
DIRETORIO_CONFIG = RAIZ_DO_PROJETO / "config"


@cache
def carregar(nome: str) -> dict:
    """Le e memoriza um arquivo de config. A memoria dura o processo."""
    caminho = DIRETORIO_CONFIG / nome
    if not caminho.exists():
        raise FileNotFoundError(f"config ausente: {caminho}")
    return tomllib.loads(caminho.read_text(encoding="utf-8"))
