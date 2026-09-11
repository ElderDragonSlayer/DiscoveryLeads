"""O "site" no Google que nao e site: perfil do Instagram, link de WhatsApp,
pagina de agendamento.

Achado na primeira busca real (Setor Bueno, Goiania, 2026-09-11): 22 dos 60
saloes tinham um desses no campo "site" do Google, e todos sairam como
TEM_SITE_PROPRIO — inelegiveis, no fim da lista. E o cliente ideal do
CLAUDE.md: ja tenta vender online, com a ferramenta errada.

E o coletor nao deve nem buscar esses enderecos: buscar perfil do Instagram do
IP de casa e o risco da secao 14 da spec.
"""

import pytest

from discoveryleads.collectors.site_analise import analisar_site
from discoveryleads.core.sinais import Signal
from discoveryleads.export.csv_leads import linha_csv
from discoveryleads.scoring.elegibilidade import Categoria, avaliar_elegibilidade
from discoveryleads.scoring.faixas import calcular_faixa

MOMENTO = "2026-09-11T14:02:00+00:00"
INSTAGRAM = "https://www.instagram.com/fastescovabueno/"


def _sinal(tipo, valor, coletor="teste"):
    return Signal(tipo=tipo, valor=valor, fonte="teste", coletor=coletor, versao=1, observado_em=MOMENTO)


async def _analisar_sem_rede(url):
    chamados = []

    async def buscar(endereco):
        chamados.append(endereco)
        raise AssertionError(f"nao devia buscar {endereco}")

    sinais = await analisar_site(url, observado_em=MOMENTO, buscar=buscar)
    return chamados, {sinal.tipo: sinal for sinal in sinais}


async def test_perfil_do_instagram_nao_e_buscado():
    chamados, sinais = await _analisar_sem_rede(INSTAGRAM)

    assert chamados == []
    assert sinais["site.perfil_no_lugar_do_site"].valor == "o perfil do Instagram"
    assert sinais["site.perfil_no_lugar_do_site"].coletor == "site_classifier"


@pytest.mark.parametrize(
    ("url", "descricao"),
    [
        ("https://api.whatsapp.com/send?phone=5562999998888", "um link de WhatsApp"),
        ("https://wa.me/5562999998888", "um link de WhatsApp"),
        ("https://www.trinks.com/tuta-hair-kids", "a página de agendamento no Trinks"),
        ("https://m.facebook.com/salaodaana", "a página do Facebook"),
    ],
)
async def test_outros_enderecos_que_nao_sao_site(url, descricao):
    chamados, sinais = await _analisar_sem_rede(url)

    assert chamados == []
    assert sinais["site.perfil_no_lugar_do_site"].valor == descricao


def _lead_com_perfil():
    return {
        "places.website_uri": _sinal("places.website_uri", INSTAGRAM, "places_discovery"),
        "places.sem_site": _sinal("places.sem_site", False, "places_discovery"),
        "places.status": _sinal("places.status", "OPERATIONAL", "places_discovery"),
        "site.perfil_no_lugar_do_site": _sinal(
            "site.perfil_no_lugar_do_site", "o perfil do Instagram", "site_classifier"
        ),
    }


def test_perfil_no_lugar_do_site_e_elegivel_com_o_motivo_certo():
    elegibilidade = avaliar_elegibilidade(_lead_com_perfil())

    assert elegibilidade.categoria is Categoria.PERFIL_NO_LUGAR_DO_SITE
    assert elegibilidade.elegivel is True
    assert elegibilidade.motivo == (
        "elegível — o site no Google é o perfil do Instagram (instagram.com/fastescovabueno)"
    )
    assert [sinal.tipo for sinal in elegibilidade.evidencia] == [
        "site.perfil_no_lugar_do_site",
        "places.website_uri",
    ]


def test_perfil_no_lugar_do_site_e_substituto_improvisado_t1():
    """Secao 6.2: "ja foi convencido de que precisa de presenca digital e
    escolheu a solucao pobre". Por o Instagram no campo site do Google e isso."""
    sinais = _lead_com_perfil()

    faixa, _ = calcular_faixa(
        avaliar_elegibilidade(sinais),
        sinais,
        rastreamento_pago=("meta_pixel",),
        demanda_min_avaliacoes=20,
    )

    assert faixa == "T1"


def test_csv_mostra_o_perfil_em_vez_de_site_nao_lido():
    sinais = _lead_com_perfil()

    linha = linha_csv(
        nome="Fast Escova - Bueno",
        endereco=None,
        place_id="p1",
        sinais=sinais,
        elegibilidade=avaliar_elegibilidade(sinais),
        faixa="T1",
    )

    assert linha["plataforma"] == "perfil"
    assert linha["rastreamento"] == "sem site: o perfil do Instagram"
    assert linha["url"] == INSTAGRAM


def test_motivo_nao_carrega_parametro_de_rastreio_da_url():
    """Na busca real o motivo saiu como
    "linktr.ee/Reconceptsalaofast?utm_source=linktree_profile_share&lts...".
    O parametro nao diz nada ao operador e empurra o resto da frase para fora."""
    url = "https://linktr.ee/Reconceptsalaofast?utm_source=linktree_profile_share&ltsid=abc"
    sinais = {
        "places.website_uri": _sinal("places.website_uri", url, "places_discovery"),
        "places.sem_site": _sinal("places.sem_site", False, "places_discovery"),
        "site.plataforma": _sinal("site.plataforma", "agregador", "site_classifier"),
    }

    elegibilidade = avaliar_elegibilidade(sinais)

    assert elegibilidade.motivo == (
        "elegível — o site é um agregador de links (linktr.ee/Reconceptsalaofast)"
    )
