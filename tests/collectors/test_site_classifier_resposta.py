"""classificar_resposta: `site.plataforma` a partir do que o fetcher trouxe,
inclusive quando nao trouxe resposta nenhuma."""

from discoveryleads.collectors.site_classifier import classificar_resposta
from discoveryleads.collectors.site_fetcher import RespostaDoSite
from discoveryleads.core.falhas import MotivoDeFalha
from discoveryleads.core.plataformas import Plataforma

from tests.conftest import carregar_fixture


def test_redirect_para_agregador_e_classificado_pelo_destino():
    """Dominio proprio que redireciona para a Linktree: comum, e e agregador."""
    resposta = RespostaDoSite(
        url_final="https://linktr.ee/FascinoBeleza",
        http_status=200,
        html=carregar_fixture("agregador_linktree.html"),
        https_valido=True,
    )

    assert classificar_resposta("https://salaodaana.com.br/", resposta) is Plataforma.AGREGADOR


def test_dominio_de_origem_de_google_sites_vence_o_redirect():
    """S4: o apex negocio.site redireciona para o perfil do Google, que responde
    200 sem assinatura nenhuma. So o dominio de ORIGEM diz o que era."""
    resposta = RespostaDoSite(
        url_final="https://business.google.com/br/business-profile/",
        http_status=200,
        html="<html>perfil</html>",
        https_valido=True,
    )

    assert (
        classificar_resposta("https://negocio.site/", resposta)
        is Plataforma.GOOGLE_SITES_EXTINTO
    )


def test_dominio_que_nao_resolve_e_quebrado():
    resposta = RespostaDoSite(motivo_falha=MotivoDeFalha.DOMINIO_NAO_RESOLVE)

    assert classificar_resposta("https://salao-que-fechou.com.br/", resposta) is Plataforma.QUEBRADO


def test_certificado_invalido_e_quebrado():
    """Secao 6.1: certificado invalido e SITE_QUEBRADO."""
    resposta = RespostaDoSite(https_valido=False, motivo_falha=MotivoDeFalha.RESPOSTA_INVALIDA)

    assert classificar_resposta("https://vencido.com.br/", resposta) is Plataforma.QUEBRADO


def test_timeout_sem_pista_de_dominio_e_desconhecido():
    """Timeout e falha do coletor, nao prova de que o site caiu."""
    resposta = RespostaDoSite(motivo_falha=MotivoDeFalha.TIMEOUT)

    assert classificar_resposta("https://salaodaana.com.br/", resposta) is None


def test_timeout_em_dominio_de_canva_continua_canva():
    resposta = RespostaDoSite(motivo_falha=MotivoDeFalha.TIMEOUT)

    assert classificar_resposta("https://anastudio.my.canva.site/", resposta) is Plataforma.CANVA
