"""A resposta do site vira sinais. Nenhum teste toca a rede: o buscador e
injetado e o HTML e das fixtures reais."""

from discoveryleads.collectors.site_analise import analisar_site
from discoveryleads.collectors.site_fetcher import RespostaDoSite
from discoveryleads.core.falhas import MotivoDeFalha

from tests.conftest import carregar_fixture

MOMENTO = "2026-09-11T14:02:00+00:00"


def _buscador(resposta):
    async def buscar(url):
        return resposta

    return buscar


async def _analisar(url, resposta):
    sinais = await analisar_site(url, observado_em=MOMENTO, buscar=_buscador(resposta))
    return {sinal.tipo: sinal for sinal in sinais}


async def test_canva_real_vira_sinais_com_coletor_e_momento():
    resposta = RespostaDoSite(
        url_final="https://vocenosalao.my.canva.site/",
        http_status=200,
        html=carregar_fixture("canva_salao.html"),
        https_valido=True,
    )

    sinais = await _analisar("https://vocenosalao.my.canva.site/", resposta)

    assert sinais["site.plataforma"].valor == "canva"
    assert sinais["site.plataforma"].coletor == "site_classifier"
    assert sinais["site.plataforma"].observado_em == MOMENTO
    assert sinais["site.whatsapp_link"].valor == "https://wa.me/message/VR7BW3RWVSZAE1"
    assert sinais["collector.site_fetcher.failed"].valor is None


async def test_ausencia_observada_vira_sinal_explicito():
    """Site sem WhatsApp grava `site.whatsapp_link = null`. Sem isso, a visao de
    sinais atuais continuaria mostrando o link de uma coleta antiga."""
    resposta = RespostaDoSite(
        url_final="https://vwcabeloeestetica.wixsite.com/barber",
        http_status=200,
        html=carregar_fixture("wix_wixsite.html"),
        https_valido=True,
    )

    sinais = await _analisar("https://vwcabeloeestetica.wixsite.com/barber", resposta)

    assert sinais["site.whatsapp_link"].valor is None
    assert sinais["tracking.meta_pixel"].valor is False


async def test_pixel_do_lojista_vira_sinal_de_rastreamento():
    resposta = RespostaDoSite(
        url_final="https://wernercoiffeur.com.br/",
        http_status=200,
        html=carregar_fixture("wordpress_com_pixel_gtm.html"),
        https_valido=True,
    )

    sinais = await _analisar("https://www.wernercoiffeur.com.br/", resposta)

    assert sinais["tracking.meta_pixel"].valor is True
    assert sinais["tracking.meta_pixel"].coletor == "tracking_detector"
    assert sinais["tracking.gtm"].valor is True
    assert sinais["tracking.eventos_conversao"].valor == []


async def test_bloqueio_grava_falha_e_nao_le_a_pagina():
    """O desafio do Cloudflare nao e a pagina do lead: nem contato nem
    rastreamento saem dele. A plataforma pelo dominio fica."""
    resposta = RespostaDoSite(
        url_final="https://beacons.ai/fornecedoresbrasil2025",
        http_status=403,
        html=carregar_fixture("agregador_beacons_bloqueado_403.html"),
        https_valido=True,
        motivo_falha=MotivoDeFalha.BLOQUEADO,
    )

    sinais = await _analisar("https://beacons.ai/fornecedoresbrasil2025", resposta)

    assert sinais["site.plataforma"].valor == "agregador"
    assert sinais["collector.site_fetcher.failed"].valor == "bloqueado"
    assert "site.whatsapp_link" not in sinais
    assert not any(tipo.startswith("tracking.") for tipo in sinais)


async def test_buscador_que_explode_nao_derruba_a_analise():
    async def buscar(url):
        raise RuntimeError("falha inesperada")

    sinais = {
        sinal.tipo: sinal
        for sinal in await analisar_site(
            "https://salaodaana.com.br/", observado_em=MOMENTO, buscar=buscar
        )
    }

    assert sinais["collector.site_fetcher.failed"].valor == "resposta_invalida"
    assert "site.plataforma" not in sinais
