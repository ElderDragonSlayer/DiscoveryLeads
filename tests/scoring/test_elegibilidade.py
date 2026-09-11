"""Secao 6.1 sobre sinais de verdade: o HTML das fixtures reais passa pela
analise do site e chega aqui como Signal."""

import pytest

from discoveryleads.collectors.site_analise import sinais_da_resposta
from discoveryleads.collectors.site_fetcher import RespostaDoSite
from discoveryleads.core.configuracao import carregar
from discoveryleads.core.falhas import MotivoDeFalha
from discoveryleads.core.sinais import Signal
from discoveryleads.scoring.elegibilidade import (
    Categoria,
    avaliar_elegibilidade,
    identificar_franquias,
)

from tests.conftest import carregar_fixture

MOMENTO = "2026-09-11T14:02:00+00:00"
SUBDOMINIOS = ("wixsite.com", "myshopify.com", "lojaintegrada.com.br")


def _places(website, *, status="OPERATIONAL", tipos=("beauty_salon",), telefone="(62) 99999-8888"):
    def sinal(tipo, valor):
        return Signal(
            tipo=tipo,
            valor=valor,
            fonte="places",
            coletor="places_discovery",
            versao=1,
            observado_em=MOMENTO,
        )

    return [
        sinal("places.website_uri", website),
        sinal("places.sem_site", website is None),
        sinal("places.status", status),
        sinal("places.tipos", list(tipos)),
        sinal("places.telefone", telefone),
        sinal("places.avaliacoes_total", 30),
    ]


def _lead(website, resposta=None, **places):
    sinais = _places(website, **places)
    if resposta is not None:
        sinais += sinais_da_resposta(website, resposta, MOMENTO)
    return {sinal.tipo: sinal for sinal in sinais}


def _pagina(fixture, url_final, status=200, motivo=None):
    return RespostaDoSite(
        url_final=url_final,
        http_status=status,
        html=carregar_fixture(fixture),
        https_valido=url_final.startswith("https://"),
        motivo_falha=motivo,
    )


def _avaliar(sinais, **extra):
    return avaliar_elegibilidade(sinais, subdominios_gratis=SUBDOMINIOS, **extra)


def _canva():
    url = "https://vocenosalao.my.canva.site/"
    return _lead(url, _pagina("canva_salao.html", url))


def test_sem_site_e_elegivel_com_evidencia_do_google():
    elegibilidade = _avaliar(_lead(None))

    assert elegibilidade.categoria is Categoria.SEM_SITE
    assert elegibilidade.motivo == "elegível — não tem site no Google"
    assert elegibilidade.evidencia[0].tipo == "places.sem_site"


def test_canva_real_e_elegivel_e_o_motivo_diz_onde_esta_a_pagina():
    elegibilidade = _avaliar(_canva())

    assert elegibilidade.categoria is Categoria.CANVA
    assert elegibilidade.motivo == (
        "elegível — a página está em vocenosalao.my.canva.site, feita no Canva"
    )
    assert elegibilidade.evidencia[0].tipo == "site.plataforma"
    assert elegibilidade.evidencia[0].coletor == "site_classifier"


def test_google_sites_extinto_com_404_e_elegivel():
    url = "https://barbearia.business.site/"
    sinais = _lead(url, _pagina("google_sites_extinto_404.html", url, 404, MotivoDeFalha.NAO_ENCONTRADO))

    assert _avaliar(sinais).categoria is Categoria.GOOGLE_SITES_EXTINTO


def test_wix_em_subdominio_gratis_e_elegivel():
    url = "https://vwcabeloeestetica.wixsite.com/barber"
    elegibilidade = _avaliar(_lead(url, _pagina("wix_wixsite.html", url)))

    assert elegibilidade.categoria is Categoria.SUBDOMINIO_GRATIS
    assert "vwcabeloeestetica.wixsite.com" in elegibilidade.motivo


def test_shopify_em_dominio_proprio_tem_site_proprio():
    sinais = _lead(
        "https://www.hifly.com.br/",
        _pagina("shopify_em_dominio_proprio.html", "https://hifly.com.br/"),
    )

    elegibilidade = _avaliar(sinais)

    assert elegibilidade.categoria is Categoria.TEM_SITE_PROPRIO
    assert elegibilidade.elegivel is False


def test_subdominio_gratis_que_redireciona_para_dominio_proprio_tem_site_proprio():
    """Decisao 1: vale o dominio FINAL, onde o cliente do lead cai."""
    sinais = _lead(
        "https://minhaloja.myshopify.com/",
        _pagina("shopify_ativa.html", "https://minhaloja.com.br/"),
    )

    assert _avaliar(sinais).categoria is Categoria.TEM_SITE_PROPRIO


def test_loja_suspensa_402_e_site_quebrado():
    url = "https://u10pfz-mz.myshopify.com/"
    sinais = _lead(url, _pagina("shopify_suspensa_402.html", url, 402, MotivoDeFalha.RESPOSTA_INVALIDA))

    elegibilidade = _avaliar(sinais)

    assert elegibilidade.categoria is Categoria.SITE_QUEBRADO
    assert "402" in elegibilidade.motivo


def test_loja_integrada_atras_de_anti_bot_continua_elegivel_pelo_subdominio():
    """Bloqueio nao e quebra, e o dominio ainda diz o que e (armadilha 7)."""
    url = "https://petprodutos.lojaintegrada.com.br/"
    sinais = _lead(url, _pagina("loja_integrada_bloqueada_403.html", url, 403, MotivoDeFalha.BLOQUEADO))

    assert _avaliar(sinais).categoria is Categoria.SUBDOMINIO_GRATIS


def test_site_proprio_bloqueado_sem_pista_e_indeterminado():
    url = "https://salaodaana.com.br/"
    sinais = _lead(url, _pagina("agregador_beacons_bloqueado_403.html", url, 403, MotivoDeFalha.BLOQUEADO))

    elegibilidade = _avaliar(sinais)

    assert elegibilidade.categoria is Categoria.INDETERMINADO
    assert elegibilidade.elegivel is False
    assert "bloqueado" in elegibilidade.motivo


def test_site_proprio_bem_feito_nao_e_elegivel():
    """O falso positivo mais caro: ligar para quem ja tem site bom."""
    sinais = _lead(
        "https://www.espacolaser.com.br/",
        _pagina("proprio_bem_feito.html", "https://espacolaser.com.br/"),
    )

    assert _avaliar(sinais).categoria is Categoria.TEM_SITE_PROPRIO


def test_dominio_que_nao_resolve_e_site_quebrado():
    sinais = _lead(
        "https://salao-que-fechou.com.br/",
        RespostaDoSite(motivo_falha=MotivoDeFalha.DOMINIO_NAO_RESOLVE),
    )

    elegibilidade = _avaliar(sinais)

    assert elegibilidade.categoria is Categoria.SITE_QUEBRADO
    assert "domínio não resolve" in elegibilidade.motivo


def test_certificado_invalido_e_site_quebrado():
    sinais = _lead(
        "https://vencido.com.br/",
        RespostaDoSite(https_valido=False, motivo_falha=MotivoDeFalha.RESPOSTA_INVALIDA),
    )

    elegibilidade = _avaliar(sinais)

    assert elegibilidade.categoria is Categoria.SITE_QUEBRADO
    assert "certificado" in elegibilidade.motivo


def test_fechado_vence_canva():
    sinais = _canva()
    sinais["places.status"] = Signal(
        tipo="places.status",
        valor="CLOSED_PERMANENTLY",
        fonte="places",
        coletor="places_discovery",
        versao=1,
        observado_em=MOMENTO,
    )

    elegibilidade = _avaliar(sinais)

    assert elegibilidade.categoria is Categoria.FECHADO
    assert "fechado de vez" in elegibilidade.motivo


def test_tipo_excluido_e_fora_do_icp():
    sinais = _lead(None, tipos=("lawyer", "point_of_interest"))

    elegibilidade = _avaliar(sinais, tipos_excluir=("lawyer", "accounting"))

    assert elegibilidade.categoria is Categoria.FORA_DO_ICP
    assert "lawyer" in elegibilidade.motivo


def test_franquia_vence_sem_site():
    elegibilidade = _avaliar(
        _lead(None), franquia="o telefone +556233334444 aparece em 3 unidades da busca"
    )

    assert elegibilidade.categoria is Categoria.REDE_FRANQUIA
    assert "3 unidades" in elegibilidade.motivo


def test_lead_sem_sinal_nunca_e_elegivel():
    """Invariante da secao 12."""
    assert _avaliar({}).elegivel is False


@pytest.mark.parametrize(
    "fabrica",
    [
        lambda: _lead(None),
        _canva,
        lambda: _lead(
            "https://vwcabeloeestetica.wixsite.com/barber",
            _pagina("wix_wixsite.html", "https://vwcabeloeestetica.wixsite.com/barber"),
        ),
        lambda: _lead(
            "https://salao-que-fechou.com.br/",
            RespostaDoSite(motivo_falha=MotivoDeFalha.DOMINIO_NAO_RESOLVE),
        ),
    ],
    ids=["sem_site", "canva", "subdominio_gratis", "site_quebrado"],
)
def test_todo_elegivel_traz_evidencia(fabrica):
    """Nenhum argumento de venda sem sinal que o sustente (principio 3)."""
    elegibilidade = _avaliar(fabrica())

    assert elegibilidade.elegivel is True
    assert elegibilidade.evidencia


def test_mesmo_telefone_com_grafias_diferentes_em_tres_unidades_e_franquia():
    franquias = identificar_franquias(
        [
            ("a", "Unidade Centro", "(62) 3333-4444"),
            ("b", "Unidade Bueno", "+55 62 3333-4444"),
            ("c", "Unidade Oeste", "062 3333-4444"),
            ("d", "Salão da Ana", "(62) 99999-8888"),
        ],
        minimo=3,
    )

    assert set(franquias) == {"a", "b", "c"}
    assert "3 unidades" in franquias["a"]


def test_duas_unidades_nao_bastam_para_franquia():
    franquias = identificar_franquias(
        [("a", "Studio Ana", "(62) 3333-4444"), ("b", "Studio Ana", "(62) 3333-4444")],
        minimo=3,
    )

    assert franquias == {}


def test_mesmo_nome_com_caixa_acento_e_espaco_diferentes_e_franquia():
    franquias = identificar_franquias(
        [("a", "Studio Ana", None), ("b", "STUDIO  ANA", None), ("c", "Stúdio Ana", None)],
        minimo=3,
    )

    assert set(franquias) == {"a", "b", "c"}


def test_config_so_aceita_subdominios_confirmados_em_fixture():
    """Principio 5 com trava: mudar esta lista e decisao, nao ajuste casual."""
    config = carregar("scoring.toml")

    assert config["elegibilidade"]["subdominios_gratis"] == list(SUBDOMINIOS)
