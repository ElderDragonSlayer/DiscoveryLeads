"""Linha de comando do DiscoveryLeads.

    python -m discoveryleads buscar --nicho "salão de beleza" --cidade "Goiânia"
        --raio 5000 --max-chamadas 40 --saida leads.csv
"""

import argparse
import asyncio
import sys
from pathlib import Path

from discoveryleads.buscar import executar_busca, formatar_relatorio
from discoveryleads.core.configuracao import RAIZ_DO_PROJETO, chave_google

BANCO_PADRAO = RAIZ_DO_PROJETO / "var" / "discoveryleads.db"
RAIO_MAXIMO_M = 50_000  # limite da Text Search (New)


def _inteiro_positivo(texto: str) -> int:
    try:
        numero = int(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"precisa ser um número inteiro, não {texto!r}")
    if numero < 1:
        raise argparse.ArgumentTypeError("precisa ser pelo menos 1")
    return numero


def _raio(texto: str) -> int:
    numero = _inteiro_positivo(texto)
    if numero > RAIO_MAXIMO_M:
        raise argparse.ArgumentTypeError(f"o Google aceita no máximo {RAIO_MAXIMO_M} metros")
    return numero


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m discoveryleads",
        description="Encontra leads que precisam de uma landing page.",
    )
    comandos = parser.add_subparsers(dest="comando", required=True)
    buscar = comandos.add_parser(
        "buscar", help="busca no Google Places, analisa os sites e grava um CSV ordenado"
    )
    buscar.add_argument("--nicho", required=True, help='ex.: "salão de beleza"')
    buscar.add_argument("--cidade", required=True, help='cidade ou bairro, ex.: "Setor Bueno, Goiânia"')
    buscar.add_argument(
        "--raio", type=_raio, default=5000, help="raio em metros (padrão 5000, máximo 50000)"
    )
    buscar.add_argument(
        "--max-chamadas",
        dest="max_chamadas",
        type=_inteiro_positivo,
        required=True,
        help="teto de chamadas pagas ao Google — obrigatório",
    )
    buscar.add_argument(
        "--saida", type=Path, default=Path("leads.csv"), help="CSV de saída (padrão leads.csv)"
    )
    buscar.add_argument(
        "--banco", type=Path, default=BANCO_PADRAO, help="SQLite (padrão var/discoveryleads.db)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    chave = chave_google()
    if chave is None:
        print(
            "GOOGLE_API_KEY está vazia. Preencha no arquivo .env da raiz do projeto e rode de novo.",
            file=sys.stderr,
        )
        return 2
    relatorio = asyncio.run(
        executar_busca(
            nicho=args.nicho,
            cidade=args.cidade,
            raio_m=args.raio,
            max_chamadas=args.max_chamadas,
            saida=args.saida,
            banco=args.banco,
            chave=chave,
        )
    )
    print(formatar_relatorio(relatorio))
    return 0 if relatorio.saida is not None else 1


if __name__ == "__main__":
    sys.exit(main())
