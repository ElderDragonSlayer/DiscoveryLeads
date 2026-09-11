"""Apoio comum aos testes. Nada aqui toca a rede."""

import tomllib
from pathlib import Path

DIRETORIO_FIXTURES = Path(__file__).parent / "fixtures" / "sites"


def carregar_manifesto() -> list[dict]:
    """As entradas de MANIFESTO.toml — procedencia e resultado esperado de cada
    fixture.

    O manifesto e a tabela de casos do classificador. Fixture que muda sem o
    manifesto mudar e teste mentindo, entao os dois sao lidos juntos.
    """
    caminho = DIRETORIO_FIXTURES / "MANIFESTO.toml"
    return tomllib.loads(caminho.read_text(encoding="utf-8"))["fixture"]


def carregar_fixture(nome: str) -> str:
    """Devolve o HTML de uma fixture real gravada em tests/fixtures/sites/.

    A procedencia de cada arquivo — URL de origem, status HTTP, redirects e o
    resultado esperado — esta em MANIFESTO.toml, no mesmo diretorio.
    """
    caminho = DIRETORIO_FIXTURES / nome
    if not caminho.exists():
        disponiveis = sorted(p.name for p in DIRETORIO_FIXTURES.glob("*.html"))
        raise FileNotFoundError(
            f"fixture {nome!r} nao existe. Disponiveis: {disponiveis}"
        )
    return caminho.read_bytes().decode("utf-8", errors="replace")
