"""Peca 2 contra respostas gravadas (respx). So o teste `live` toca a rede."""

import json

import httpx
import pytest
import respx

from discoveryleads.collectors.places_discovery import (
    URL_TEXT_SEARCH,
    Lugar,
    descobrir,
    sinais_do_lugar,
)
from discoveryleads.core.configuracao import chave_google
from discoveryleads.core.falhas import MotivoDeFalha
from discoveryleads.core.orcamento import Orcamento

CHAVE = "chave-de-teste"
CENTRO = {"latitude": -16.6869, "longitude": -49.2648}


def _bruto(n: int, **extra) -> dict:
    lugar = {
        "id": f"place-{n}",
        "displayName": {"text": f"Salão {n}", "languageCode": "pt"},
        "formattedAddress": f"Rua {n}, Goiânia - GO",
        "location": {"latitude": -16.70, "longitude": -49.26},
        "types": ["beauty_salon", "point_of_interest"],
        "nationalPhoneNumber": f"(62) 99999-{n:04d}",
        "rating": 4.5,
        "userRatingCount": 10 * n,
        "businessStatus": "OPERATIONAL",
    }
    lugar.update(extra)
    return lugar


class _Google:
    """Imita a Text Search: responde o pedido do centro e depois as paginas, na
    ordem, guardando cada pedido para o teste conferir."""

    def __init__(self, *paginas, centro=None):
        self.paginas = list(paginas)
        self.centro = centro or httpx.Response(200, json={"places": [{"location": CENTRO}]})
        self.pedidos = []

    def __call__(self, request):
        self.pedidos.append((request.headers, json.loads(request.content)))
        if request.headers["X-Goog-FieldMask"] == "places.location":
            return self.centro
        return self.paginas.pop(0)


async def _descobrir(google, *, cidade="Goiânia", raio=5000, orcamento=None):
    respx.post(URL_TEXT_SEARCH).mock(side_effect=google)
    return await descobrir(
        "salão de beleza",
        cidade,
        raio,
        chave=CHAVE,
        orcamento=orcamento or Orcamento(teto=10),
    )


@respx.mock
async def test_pagina_unica_vira_lugares_normalizados():
    google = _Google(
        httpx.Response(
            200,
            json={
                "places": [
                    _bruto(1),
                    _bruto(2, websiteUri="https://salao2.com.br/", priceLevel="PRICE_LEVEL_MODERATE"),
                ]
            },
        )
    )

    resultado = await _descobrir(google)

    primeiro, segundo = resultado.lugares
    assert primeiro.place_id == "place-1"
    assert primeiro.nome == "Salão 1"
    assert primeiro.telefone == "(62) 99999-0001"
    assert primeiro.website is None
    assert segundo.website == "https://salao2.com.br/"
    assert segundo.nivel_preco == 2
    assert resultado.motivo_falha is None


@respx.mock
async def test_busca_usa_centro_raio_e_campos_combinados():
    google = _Google(httpx.Response(200, json={"places": [_bruto(1)]}))

    await _descobrir(google, cidade="Setor Bueno, Goiânia", raio=3000)

    assert google.pedidos[0][1]["textQuery"] == "Setor Bueno, Goiânia"
    cabecalhos, corpo = google.pedidos[1]
    assert corpo["textQuery"] == "salão de beleza em Setor Bueno, Goiânia"
    assert corpo["locationBias"]["circle"] == {"center": CENTRO, "radius": 3000.0}
    campos = cabecalhos["X-Goog-FieldMask"].split(",")
    assert "places.id" in campos
    assert "nextPageToken" in campos
    assert cabecalhos["X-Goog-Api-Key"] == CHAVE


@respx.mock
async def test_segue_o_next_page_token_repetindo_o_resto_do_pedido():
    google = _Google(
        httpx.Response(200, json={"places": [_bruto(1)], "nextPageToken": "tok-2"}),
        httpx.Response(200, json={"places": [_bruto(2)]}),
    )

    resultado = await _descobrir(google)

    assert len(resultado.lugares) == 2
    primeira, segunda = google.pedidos[1][1], google.pedidos[2][1]
    assert segunda["pageToken"] == "tok-2"
    # Qualquer outro parametro diferente e INVALID_ARGUMENT na API.
    assert {k: v for k, v in segunda.items() if k != "pageToken"} == primeira


@respx.mock
async def test_mesmo_place_id_em_duas_paginas_vira_um_lugar():
    google = _Google(
        httpx.Response(200, json={"places": [_bruto(1)], "nextPageToken": "tok-2"}),
        httpx.Response(200, json={"places": [_bruto(1), _bruto(2)]}),
    )

    resultado = await _descobrir(google)

    assert [lugar.place_id for lugar in resultado.lugares] == ["place-1", "place-2"]


@respx.mock
async def test_teto_de_chamadas_interrompe_a_paginacao_e_avisa():
    google = _Google(
        httpx.Response(200, json={"places": [_bruto(1)], "nextPageToken": "tok-2"})
    )
    orcamento = Orcamento(teto=2)  # centro + uma pagina

    resultado = await _descobrir(google, orcamento=orcamento)

    assert orcamento.usadas == 2
    assert len(google.pedidos) == 2
    assert resultado.teto_atingido is True
    assert [lugar.place_id for lugar in resultado.lugares] == ["place-1"]


@respx.mock
async def test_chave_recusada_vira_bloqueado_com_a_mensagem_do_google():
    google = _Google(
        centro=httpx.Response(403, json={"error": {"message": "API key not valid."}})
    )

    resultado = await _descobrir(google)

    assert resultado.motivo_falha is MotivoDeFalha.BLOQUEADO
    assert resultado.detalhe == "API key not valid."
    assert resultado.lugares == []


@respx.mock
async def test_429_vira_cota_estourada():
    google = _Google(centro=httpx.Response(429, json={"error": {"message": "Quota exceeded"}}))

    resultado = await _descobrir(google)

    assert resultado.motivo_falha is MotivoDeFalha.COTA_ESTOURADA


@respx.mock
async def test_falha_no_meio_da_paginacao_guarda_o_que_ja_veio():
    google = _Google(
        httpx.Response(200, json={"places": [_bruto(1)], "nextPageToken": "tok-2"}),
        httpx.Response(500, json={"error": {"message": "Internal error"}}),
    )

    resultado = await _descobrir(google)

    assert [lugar.place_id for lugar in resultado.lugares] == ["place-1"]
    assert resultado.motivo_falha is MotivoDeFalha.RESPOSTA_INVALIDA


@respx.mock
async def test_regiao_que_o_google_nao_acha_nao_gasta_a_busca():
    google = _Google(centro=httpx.Response(200, json={}))
    orcamento = Orcamento(teto=10)

    resultado = await _descobrir(google, cidade="Cidade Inventada", orcamento=orcamento)

    assert resultado.motivo_falha is MotivoDeFalha.NAO_ENCONTRADO
    assert orcamento.usadas == 1


@respx.mock
async def test_timeout_na_rede_vira_motivo_em_enum():
    respx.post(URL_TEXT_SEARCH).mock(side_effect=httpx.ConnectTimeout("lento"))

    resultado = await descobrir(
        "salão de beleza", "Goiânia", 5000, chave=CHAVE, orcamento=Orcamento(teto=10)
    )

    assert resultado.motivo_falha is MotivoDeFalha.TIMEOUT


def test_sinais_do_lugar_sem_site_e_com_celular():
    lugar = Lugar(
        place_id="p1",
        nome="Salão",
        endereco=None,
        lat=None,
        lng=None,
        telefone="(62) 99999-8888",
        website=None,
        nota=4.8,
        avaliacoes=37,
        status="OPERATIONAL",
        tipos=("beauty_salon",),
        nivel_preco=None,
    )

    sinais = {s.tipo: s for s in sinais_do_lugar(lugar, "2026-09-11T14:02:00+00:00")}

    assert sinais["places.sem_site"].valor is True
    assert sinais["places.website_uri"].valor is None
    assert sinais["places.avaliacoes_total"].valor == 37
    assert sinais["telefone.e_movel"].valor is True
    assert sinais["telefone.ddd"].valor == "62"
    assert sinais["places.sem_site"].fonte == "places"
    assert sinais["places.sem_site"].coletor == "places_discovery"


@pytest.mark.live
async def test_live_busca_real_gasta_duas_chamadas():
    """Canario do contrato do Google. GASTA 2 CHAMADAS PAGAS (centro + uma
    pagina). Roda com -m live e exige GOOGLE_API_KEY."""
    chave = chave_google()
    if chave is None:
        pytest.skip("GOOGLE_API_KEY vazia")

    resultado = await descobrir(
        "salão de beleza", "Setor Bueno, Goiânia", 2000, chave=chave, orcamento=Orcamento(teto=2)
    )

    assert resultado.motivo_falha is None, resultado.detalhe
    assert resultado.lugares
    assert all(lugar.place_id for lugar in resultado.lugares)
