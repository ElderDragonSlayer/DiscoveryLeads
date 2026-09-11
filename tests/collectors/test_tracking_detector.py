"""Testes do tracking_detector contra HTML real.

Esta e a peca de maior peso do sistema: pela secao 6.2, "elegivel + qualquer sinal
`tracking.*` pago" e a faixa T0, o topo da lista. Falso positivo aqui nao produz
um lead ruim no meio do CSV — produz um lead ruim na PRIMEIRA linha.
"""

import pytest

from discoveryleads.collectors.tracking_detector import detectar_rastreamento

from tests.conftest import carregar_fixture, carregar_manifesto

SINAIS = (
    "meta_pixel",
    "google_ads",
    "google_analytics",
    "gtm",
    "tiktok_pixel",
    "heatmap",
)


def test_detecta_meta_pixel_e_gtm_na_mesma_pagina():
    """wernercoiffeur.com.br tem fbq( + connect.facebook.net + gtm.js."""
    rastreamento = detectar_rastreamento(carregar_fixture("wordpress_com_pixel_gtm.html"))

    assert rastreamento.meta_pixel is True
    assert rastreamento.gtm is True


def test_consent_id_da_linktree_nao_e_pixel_do_lojista():
    """A armadilha mais cara do sistema.

    A pagina real tem, no __NEXT_DATA__, os campos do lojista vazios —
    facebookPixelId, googleAnalyticsId e tiktokPixelId todos null — e, ao lado,
    metaPixelConsentId e tiktokPixelConsentId com valor preenchido. Esses dois
    ultimos vieram IDENTICOS nas tres paginas de Linktree inspecionadas: sao do
    fornecedor de consentimento da propria Linktree, nao do lojista.

    Um detector que case a substring "pixel" marca toda pagina de Linktree como
    tendo rastreamento pago, e a secao 6.2 promove todas para T0. O topo da lista
    inteiro viraria lead sem verba nenhuma.
    """
    rastreamento = detectar_rastreamento(carregar_fixture("agregador_linktree.html"))

    assert rastreamento.meta_pixel is False
    assert rastreamento.tiktok_pixel is False


def test_pixel_do_lojista_na_linktree_e_detectado():
    """Par do teste acima, na fixture derivada.

    Um detector que simplesmente devolvesse False para agregador — a maneira
    preguicosa de fugir da armadilha — passa la e falha aqui. E o caso maximo da
    secao 6.2: Pixel dentro de um agregador, verba comprovada e funil furado.
    """
    rastreamento = detectar_rastreamento(
        carregar_fixture("agregador_linktree_com_pixel.html")
    )

    assert rastreamento.meta_pixel is True


def test_classe_css_comecada_com_g_nao_e_id_de_medicao_do_ga4():
    """Casar `G-` sem distinguir maiuscula de minuscula produziu, ao montar as
    fixtures, oito "ids" falsos em seis das treze paginas: g-generator,
    g-animation, g-recaptcha, g-calculated, g-frontend, g-function, g-progress e
    g-profileBackground. Todos nome de classe CSS ou de identificador JavaScript.

    Esta pagina tem g-animation e g-recaptcha, e GA4 nenhum.
    """
    rastreamento = detectar_rastreamento(carregar_fixture("shopify_ativa.html"))

    assert rastreamento.google_analytics is False


def test_ga4_de_verdade_e_detectado():
    """G-C2BKCGLQ6T, o unico id de GA4 real das treze fixtures. Aparece nas duas
    formas ancoradas: `gtag/js?id=G-...` e `gtag('config', 'G-...')`."""
    rastreamento = detectar_rastreamento(
        carregar_fixture("wordpress_com_whatsapp.html")
    )

    assert rastreamento.google_analytics is True


def test_gtm_sozinho_nao_conta_como_google_analytics():
    """wernercoiffeur carrega gtm.js e nao traz id de GA4 no HTML cru — o GTM
    carrega o GA depois, no navegador.

    `tracking.gtm` verdadeiro com `tracking.google_analytics` falso e o resultado
    correto para HTML cru, nao um defeito. Inferir GA a partir de GTM inventaria
    um sinal que ninguem consegue mostrar na tela do lead.
    """
    rastreamento = detectar_rastreamento(
        carregar_fixture("wordpress_com_pixel_gtm.html")
    )

    assert rastreamento.gtm is True
    assert rastreamento.google_analytics is False


def test_google_ads_usa_a_mesma_ancora_do_ga4():
    """HTML SINTETICO, escrito a mao — nao e fixture colhida.

    Nenhuma das treze paginas reais tem Google Ads. E lacuna conhecida, registrada
    no manifesto, e incomoda: `AW-` e o sinal de maior peso da faixa T0, e nasce
    sem um caso positivo do mundo real para confirma-lo. O trecho abaixo e o
    minimo que o gtag gera.
    """
    html = "<script>gtag('config', 'AW-123456789');</script>"

    assert detectar_rastreamento(html).google_ads is True


def test_ga4_e_google_ads_nao_se_confundem():
    """Os dois prefixos passam pela mesma ancora. Se um pegasse o outro, um lead
    que so mede viraria um lead que paga — e T0 e a faixa de quem paga."""
    rastreamento = detectar_rastreamento(
        "<script>gtag('config', 'G-C2BKCGLQ6T');</script>"
    )

    assert rastreamento.google_analytics is True
    assert rastreamento.google_ads is False


def test_evento_de_conversao_e_lido_do_fbq():
    """HTML SINTETICO — nenhuma fixture real tem evento de conversao."""
    html = "<script>fbq('track', 'Purchase');</script>"

    assert detectar_rastreamento(html).eventos_conversao == ["Purchase"]


def test_pixel_que_so_dispara_pageview_nao_tem_evento_de_conversao():
    """wernercoiffeur.com.br: `fbq('track', 'PageView', [])`, e nada mais.

    E o caso descrito na secao 5 da spec — Pixel presente com
    `eventos_conversao` vazio significa que o negocio paga anuncio e nao mede
    retorno. Vira argumento de venda direto, entao contar PageView como conversao
    apagaria justamente o argumento.
    """
    rastreamento = detectar_rastreamento(
        carregar_fixture("wordpress_com_pixel_gtm.html")
    )

    assert rastreamento.meta_pixel is True
    assert rastreamento.eventos_conversao == []


def test_heatmap_detecta_hotjar_e_clarity():
    """HTML SINTETICO — nenhuma fixture real tem heatmap.

    Heatmap nao e trafego pago e nao promove para T0. Vale como sinal de que o
    negocio se importa com conversao, pela secao 5.
    """
    hotjar = "<script src='https://static.hotjar.com/c/hotjar-1234567.js'></script>"
    clarity = "<script src='https://www.clarity.ms/tag/abcdef'></script>"

    assert detectar_rastreamento(hotjar).heatmap is True
    assert detectar_rastreamento(clarity).heatmap is True


def test_pagina_sem_heatmap_nao_reporta_heatmap():
    """Guarda contra detector que devolva True sempre."""
    assert detectar_rastreamento(carregar_fixture("proprio_bem_feito.html")).heatmap is False


@pytest.mark.parametrize(
    "entrada", carregar_manifesto(), ids=lambda e: e["arquivo"].removesuffix(".html")
)
def test_rastreamento_bate_exatamente_com_o_manifesto(entrada):
    """A guarda global contra falso positivo.

    Compara o conjunto INTEIRO de sinais ligados com o que o manifesto declara,
    em todas as paginas reais de uma vez. Nao verifica so que o rastreamento
    declarado foi achado — verifica que NADA ALEM dele disparou.

    E aqui que uma assinatura nova, acrescentada com boa intencao, denuncia que
    encheu de T0 falso as onze paginas que nao tem rastreamento nenhum.

    Toda entrada e OBRIGADA a declarar `rastreamento`, mesmo vazio. A primeira
    versao deste teste filtrava quem nao declarava, e tres paginas escaparam da
    guarda em silencio — justamente as tres de erro (402, 403 e 404).
    """
    assert "rastreamento" in entrada, (
        f"{entrada['arquivo']} nao declara `rastreamento` no MANIFESTO.toml"
    )

    rastreamento = detectar_rastreamento(carregar_fixture(entrada["arquivo"]))

    ligados = sorted(nome for nome in SINAIS if getattr(rastreamento, nome))

    assert ligados == sorted(entrada["rastreamento"])
