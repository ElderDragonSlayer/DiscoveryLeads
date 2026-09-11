"""Testes do site_classifier contra HTML real.

Cada caso aqui corresponde a uma entrada de tests/fixtures/sites/MANIFESTO.toml.
"""

import pytest

from discoveryleads.collectors.site_classifier import classificar_plataforma
from discoveryleads.core.plataformas import Plataforma

from tests.conftest import carregar_fixture, carregar_manifesto


def test_canva_em_dominio_proprio_e_reconhecido_pela_assinatura_do_html():
    """A assinatura do HTML tem que bastar, sem ajuda do dominio.

    O Canva permite dominio proprio. Se a deteccao dependesse de *.my.canva.site,
    todo lead T1 que apontou o proprio dominio para o Canva sumiria da lista.
    """
    html = carregar_fixture("canva_variante_sem_app_name.html")

    assert classificar_plataforma("https://salaodaana.com.br/", html) is Plataforma.CANVA


def test_linktree_e_agregador():
    html = carregar_fixture("agregador_linktree.html")

    assert (
        classificar_plataforma("https://linktr.ee/FascinoBeleza", html)
        is Plataforma.AGREGADOR
    )


def test_google_sites_extinto_vence_o_status_404():
    """Resposta do spike S4, e a regra mais cara de errar do classificador.

    O corpo e o 404 generico do Google, sem uma unica pista de que ali existiu um
    site. So o dominio diz. E a ordem importa: se o status 4xx fosse avaliado
    antes do dominio, o lead viraria SITE_QUEBRADO — que nao aparece em nenhuma
    faixa da secao 6.2 — em vez de GOOGLE_SITES_EXTINTO, que e T1.
    """
    html = carregar_fixture("google_sites_extinto_404.html")

    assert (
        classificar_plataforma(
            "https://barbearia.business.site/", html, http_status=404
        )
        is Plataforma.GOOGLE_SITES_EXTINTO
    )


def test_dominio_proprio_que_responde_5xx_e_quebrado():
    """Sem assinatura e sem corpo, sobra o status."""
    assert (
        classificar_plataforma("https://salaodaana.com.br/", "", http_status=500)
        is Plataforma.QUEBRADO
    )


@pytest.mark.parametrize(
    "entrada", carregar_manifesto(), ids=lambda e: e["arquivo"].removesuffix(".html")
)
def test_toda_fixture_do_manifesto_e_classificada_como_o_manifesto_diz(entrada):
    """A tabela de casos e o proprio MANIFESTO.toml.

    Cobre as 13 paginas reais de uma vez, usando a URL e o status HTTP com que
    cada uma foi baixada de verdade. Se alguem trocar uma fixture sem atualizar o
    manifesto, ou acrescentar assinatura em platforms.toml que pegue a pagina
    errada, e aqui que quebra.
    """
    html = carregar_fixture(entrada["arquivo"])

    plataforma = classificar_plataforma(
        entrada["origem"], html, http_status=entrada["http_status"]
    )

    assert plataforma is Plataforma(entrada["plataforma_esperada"])


def test_site_proprio_bem_feito_nao_dispara_nenhuma_assinatura():
    """O caso negativo que da o custo do falso positivo.

    Se qualquer assinatura de construtor pegar esta pagina, a ferramenta manda o
    operador ligar para quem ja tem site — e queima credibilidade na primeira
    ligacao. E o teste que fica mais valioso a cada assinatura nova.
    """
    html = carregar_fixture("proprio_bem_feito.html")

    assert (
        classificar_plataforma("https://espacolaser.com.br/", html) is Plataforma.PROPRIO
    )


def test_construtor_vence_dominio_proprio():
    """Dominio .com.br proprio NAO implica `proprio`.

    hifly.com.br e uma loja Shopify em dominio proprio. Sem esta regra, toda loja
    de construtor que apontou o proprio dominio seria classificada como site
    proprio e sairia da lista.
    """
    html = carregar_fixture("shopify_em_dominio_proprio.html")

    assert classificar_plataforma("https://hifly.com.br/", html) is Plataforma.SHOPIFY


def test_agregador_atras_de_anti_bot_continua_agregador():
    """403 do Cloudflare nao entregou corpo nenhum. O dominio sozinho tem que
    sustentar a classificacao — senao um lead T1 legitimo vira `quebrado`."""
    html = carregar_fixture("agregador_beacons_bloqueado_403.html")

    assert (
        classificar_plataforma(
            "https://beacons.ai/fornecedoresbrasil2025", html, http_status=403
        )
        is Plataforma.AGREGADOR
    )


def test_bloqueio_sem_pista_de_plataforma_nao_e_quebrado():
    """O corpo da fixture da Beacons e o desafio do Cloudflare. Num dominio que
    nao diz nada, a resposta honesta e "nao sei". `quebrado` mandaria o
    operador ligar para quem tem site funcionando."""
    html = carregar_fixture("agregador_beacons_bloqueado_403.html")

    assert classificar_plataforma("https://salaodaana.com.br/", html, http_status=403) is None
