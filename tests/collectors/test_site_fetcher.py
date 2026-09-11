"""Testes do fetcher. Nenhum toca a rede: httpx e servido por respx, e a
resolucao de DNS e injetada.

O principio 1 do CLAUDE.md manda que coletor nunca propague excecao. Todo teste
aqui, no fundo, verifica a mesma coisa: qualquer que seja o desastre, sai um
resultado com motivo em enum, e o programa segue.
"""

import ssl

import httpx
import pytest
import respx

from discoveryleads.collectors.site_fetcher import buscar_site, certificado_invalido
from discoveryleads.core.falhas import MotivoDeFalha


def _dns_que_falha(host: str) -> bool:
    return False


def _dns_que_resolve(host: str) -> bool:
    return True


async def test_dominio_que_nao_resolve_nao_levanta_excecao():
    """Dois dominios do conjunto de fixtures morreram de verdade —
    www.neuroaplicativos.com.br e o salao inventado — e a resposta do sistema
    operacional foi "Could not resolve host".

    O coletor tem que devolver isso como dado, nao como excecao: e assim que
    "o lead X nao tem site de pe" vira consulta SQL.
    """
    resultado = await buscar_site(
        "https://salao-que-nao-existe-xyz9271.com.br/", resolve_dns=_dns_que_falha
    )

    assert resultado.motivo_falha is MotivoDeFalha.DOMINIO_NAO_RESOLVE
    assert resultado.http_status is None
    assert resultado.html == ""


@respx.mock
async def test_timeout_vira_motivo_em_enum():
    respx.get("https://lenta.com.br/").mock(
        side_effect=httpx.ConnectTimeout("demorou demais")
    )

    resultado = await buscar_site(
        "https://lenta.com.br/", resolve_dns=_dns_que_resolve
    )

    assert resultado.motivo_falha is MotivoDeFalha.TIMEOUT


@respx.mock
async def test_pagina_de_pe_devolve_status_html_e_tempo():
    respx.get("https://salao.com.br/").mock(
        return_value=httpx.Response(200, html="<html><head><title>Oi</title></head></html>")
    )

    resultado = await buscar_site("https://salao.com.br/", resolve_dns=_dns_que_resolve)

    assert resultado.motivo_falha is None
    assert resultado.http_status == 200
    assert "<title>Oi</title>" in resultado.html
    assert resultado.tempo_resposta_ms >= 0
    assert resultado.redirects == 0


@respx.mock
async def test_conta_os_redirects_e_guarda_a_url_final():
    """www -> apex aconteceu em tres das treze fixtures. `site.redirects` e sinal
    da secao 5, e a url final e o que vale como dominio do lead."""
    respx.get("https://www.salao.com.br/").mock(
        return_value=httpx.Response(301, headers={"Location": "https://salao.com.br/"})
    )
    respx.get("https://salao.com.br/").mock(return_value=httpx.Response(200, html="<html></html>"))

    resultado = await buscar_site(
        "https://www.salao.com.br/", resolve_dns=_dns_que_resolve
    )

    assert resultado.http_status == 200
    assert resultado.redirects == 1
    assert resultado.url_final == "https://salao.com.br/"


@respx.mock
async def test_cadeia_de_redirect_sem_fim_para_no_teto_e_nao_levanta():
    """O teto de 5 e da spec. Sem ele, uma armadilha de redirect trava o
    coletor num lead so e a campanha inteira espera."""
    respx.get("https://loop.com.br/").mock(
        return_value=httpx.Response(302, headers={"Location": "https://loop.com.br/"})
    )

    resultado = await buscar_site("https://loop.com.br/", resolve_dns=_dns_que_resolve)

    assert resultado.motivo_falha is MotivoDeFalha.RESPOSTA_INVALIDA


@respx.mock
@pytest.mark.parametrize(
    ("status", "motivo"),
    [
        (403, MotivoDeFalha.BLOQUEADO),
        (404, MotivoDeFalha.NAO_ENCONTRADO),
        (500, MotivoDeFalha.RESPOSTA_INVALIDA),
    ],
)
async def test_status_de_erro_vira_motivo_mas_o_html_continua_disponivel(status, motivo):
    """Duas fixtures reais sao 403 e uma e 404, e as tres ainda trazem corpo que
    permite classificar a plataforma. O motivo da falha e gravado AO LADO do
    html, nunca no lugar dele — senao o lead T1 atras de anti-bot some da lista.
    """
    respx.get("https://loja.com.br/").mock(
        return_value=httpx.Response(status, html="<html>cdn.awsli.com.br</html>")
    )

    resultado = await buscar_site("https://loja.com.br/", resolve_dns=_dns_que_resolve)

    assert resultado.motivo_falha is motivo
    assert resultado.http_status == status
    assert "awsli" in resultado.html


def test_certificado_invalido_reconhece_a_causa_real_do_ssl():
    """Formato medido em expired.badssl.com: ConnectError <- ConnectError <-
    ssl.SSLCertVerificationError."""
    raiz = ssl.SSLCertVerificationError("certificate verify failed: certificate has expired")
    meio = httpx.ConnectError("falhou")
    meio.__cause__ = raiz
    topo = httpx.ConnectError("falhou")
    topo.__cause__ = meio

    assert certificado_invalido(topo) is True


def test_certificado_invalido_reconhece_pela_mensagem_do_openssl():
    """Sob respx a cadeia de causas se perde; a mensagem do OpenSSL fica."""
    erro = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

    assert certificado_invalido(erro) is True


def test_erro_de_conexao_comum_nao_e_certificado():
    assert certificado_invalido(httpx.ConnectError("connection refused")) is False


@respx.mock
async def test_certificado_invalido_vira_https_invalido_sem_status():
    respx.get("https://vencido.com.br/").mock(
        side_effect=httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    )

    resultado = await buscar_site("https://vencido.com.br/", resolve_dns=_dns_que_resolve)

    assert resultado.https_valido is False
    assert resultado.http_status is None
    assert resultado.motivo_falha is MotivoDeFalha.RESPOSTA_INVALIDA


@respx.mock
async def test_site_que_responde_em_https_tem_https_valido():
    respx.get("https://salao.com.br/").mock(return_value=httpx.Response(200, html="<html></html>"))

    resultado = await buscar_site("https://salao.com.br/", resolve_dns=_dns_que_resolve)

    assert resultado.https_valido is True


@respx.mock
async def test_site_so_em_http_nao_tem_https_valido():
    """Sem HTTPS o navegador mostra "Não seguro": defeito vendável, não quebra."""
    respx.get("http://salao.com.br/").mock(return_value=httpx.Response(200, html="<html></html>"))

    resultado = await buscar_site("http://salao.com.br/", resolve_dns=_dns_que_resolve)

    assert resultado.https_valido is False
    assert resultado.motivo_falha is None


@pytest.mark.live
async def test_live_certificado_vencido_de_verdade():
    """Canário da cadeia real de exceções do httpx. Roda com -m live."""
    resultado = await buscar_site("https://expired.badssl.com/")

    assert resultado.https_valido is False
