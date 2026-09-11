"""Acesso ao SQLite da fatia.

`signals` so recebe INSERT (principio 2) — e o proprio banco recusa o resto.
`leads` e desnormalizada por conveniencia (secao 4.1) e pode ser atualizada; a
verdade continua em `signals`. Quem chama faz o commit.
"""

import json
import sqlite3
from pathlib import Path

from discoveryleads.core.sinais import Signal

SCHEMA = Path(__file__).with_name("schema.sql")


def abrir(caminho: Path | str) -> sqlite3.Connection:
    if str(caminho) != ":memory:":
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conexao


def lead_por_identidade(conexao: sqlite3.Connection, tipo: str, valor: str) -> int | None:
    linha = conexao.execute(
        "SELECT lead_id FROM lead_identities WHERE tipo = ? AND valor = ?", (tipo, valor)
    ).fetchone()
    return linha["lead_id"] if linha else None


def gravar_lead(
    conexao: sqlite3.Connection,
    *,
    place_id: str,
    nome: str,
    endereco: str | None,
    cidade: str | None,
    lat: float | None,
    lng: float | None,
    telefone_e164: str | None,
    agora: str,
) -> int:
    """Insere o lead ou atualiza o que ja tem o mesmo place_id.

    Nesta fatia a identidade e so place_id (substituicao tatica da fatia).
    Telefone, dominio e Instagram entram com a resolucao completa, na E2.
    """
    existente = lead_por_identidade(conexao, "place_id", place_id)
    if existente is not None:
        conexao.execute(
            "UPDATE leads SET nome = ?, endereco = ?, cidade = ?, lat = ?, lng = ?,"
            " telefone_e164 = ?, atualizado_em = ? WHERE id = ?",
            (nome, endereco, cidade, lat, lng, telefone_e164, agora, existente),
        )
        return existente

    cursor = conexao.execute(
        "INSERT INTO leads (nome, endereco, cidade, lat, lng, telefone_e164,"
        " criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (nome, endereco, cidade, lat, lng, telefone_e164, agora, agora),
    )
    lead_id = cursor.lastrowid
    conexao.execute(
        "INSERT INTO lead_identities (tipo, valor, lead_id) VALUES ('place_id', ?, ?)",
        (place_id, lead_id),
    )
    return lead_id


def registrar_sinais(conexao: sqlite3.Connection, lead_id: int, sinais: list[Signal]) -> None:
    conexao.executemany(
        "INSERT INTO signals (lead_id, tipo, valor, fonte, coletor, versao, confianca,"
        " observado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (lead_id, s.tipo, s.valor_json(), s.fonte, s.coletor, s.versao, s.confianca, s.observado_em)
            for s in sinais
        ],
    )


def sinais_atuais(conexao: sqlite3.Connection, lead_id: int) -> dict[str, Signal]:
    linhas = conexao.execute(
        "SELECT * FROM v_signals_atuais WHERE lead_id = ?", (lead_id,)
    ).fetchall()
    return {
        linha["tipo"]: Signal(
            tipo=linha["tipo"],
            valor=json.loads(linha["valor"]),
            fonte=linha["fonte"],
            coletor=linha["coletor"],
            versao=linha["versao"],
            observado_em=linha["observado_em"],
            confianca=linha["confianca"],
        )
        for linha in linhas
    }
