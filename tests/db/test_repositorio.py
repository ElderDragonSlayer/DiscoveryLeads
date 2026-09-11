import sqlite3

import pytest

from discoveryleads.core.sinais import Signal
from discoveryleads.db.repositorio import abrir, gravar_lead, registrar_sinais, sinais_atuais

AGORA = "2026-09-11T14:02:00+00:00"
DEPOIS = "2026-09-25T09:00:00+00:00"


def _sinal(tipo, valor, observado_em=AGORA):
    return Signal(
        tipo=tipo,
        valor=valor,
        fonte="site",
        coletor="site_classifier",
        versao=1,
        observado_em=observado_em,
    )


def _lead(conexao, place_id="place-1"):
    return gravar_lead(
        conexao,
        place_id=place_id,
        nome="Salão da Ana",
        endereco="Rua 1, Goiânia - GO",
        cidade="Goiânia",
        lat=-16.7,
        lng=-49.26,
        telefone_e164="+5562999998888",
        agora=AGORA,
    )


def test_mesmo_place_id_em_duas_buscas_e_o_mesmo_lead(tmp_path):
    conexao = abrir(tmp_path / "var" / "discoveryleads.db")

    primeiro = _lead(conexao)
    segundo = _lead(conexao)

    assert primeiro == segundo
    assert conexao.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 1


def test_signals_recusa_update(tmp_path):
    conexao = abrir(tmp_path / "leads.db")
    registrar_sinais(conexao, _lead(conexao), [_sinal("site.plataforma", "canva")])

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conexao.execute("UPDATE signals SET valor = '\"wix\"'")


def test_signals_recusa_delete(tmp_path):
    conexao = abrir(tmp_path / "leads.db")
    registrar_sinais(conexao, _lead(conexao), [_sinal("site.plataforma", "canva")])

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conexao.execute("DELETE FROM signals")


def test_sinal_atual_e_a_observacao_mais_recente_e_a_antiga_fica(tmp_path):
    """"Trocou Linktree por Canva" so existe porque as duas observacoes ficam."""
    conexao = abrir(tmp_path / "leads.db")
    lead_id = _lead(conexao)

    registrar_sinais(conexao, lead_id, [_sinal("site.plataforma", "agregador")])
    registrar_sinais(conexao, lead_id, [_sinal("site.plataforma", "canva", DEPOIS)])

    assert sinais_atuais(conexao, lead_id)["site.plataforma"].valor == "canva"
    assert conexao.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 2


def test_valor_volta_do_banco_com_o_tipo_certo(tmp_path):
    conexao = abrir(tmp_path / "leads.db")
    lead_id = _lead(conexao)

    registrar_sinais(
        conexao,
        lead_id,
        [
            _sinal("tracking.meta_pixel", True),
            _sinal("tracking.eventos_conversao", []),
            _sinal("site.whatsapp_link", None),
            _sinal("site.http_status", 403),
        ],
    )
    atuais = sinais_atuais(conexao, lead_id)

    assert atuais["tracking.meta_pixel"].valor is True
    assert atuais["tracking.eventos_conversao"].valor == []
    assert atuais["site.whatsapp_link"].valor is None
    assert atuais["site.http_status"].valor == 403
    assert atuais["site.http_status"].coletor == "site_classifier"
