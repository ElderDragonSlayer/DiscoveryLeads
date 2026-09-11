"""Acesso aos arquivos de config/*.toml e ao .env.

Principio 5 do CLAUDE.md: pesos e textos ficam fora do codigo, para o operador
calibrar sozinho.
"""

import os
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


def ler_env(caminho: Path | None = None) -> dict[str, str]:
    """Le pares NOME=valor do .env da raiz do projeto.

    Linha vazia e comentario (#) sao ignorados; aspas em volta do valor saem.
    Decodifica UTF-8 tolerante: o .env real tem um travessao gravado fora de
    UTF-8 num comentario, e leitura estrita derrubaria a busca antes da primeira
    chamada.
    """
    caminho = caminho or RAIZ_DO_PROJETO / ".env"
    if not caminho.exists():
        return {}
    valores: dict[str, str] = {}
    for linha in caminho.read_bytes().decode("utf-8", errors="replace").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, _, valor = linha.partition("=")
        valores[nome.strip()] = valor.strip().strip('"').strip("'")
    return valores


def chave_google() -> str | None:
    """Variavel de ambiente primeiro, depois o .env. O valor nunca e impresso."""
    return os.environ.get("GOOGLE_API_KEY") or ler_env().get("GOOGLE_API_KEY") or None
