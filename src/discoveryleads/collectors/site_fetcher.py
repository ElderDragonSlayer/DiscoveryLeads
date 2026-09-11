"""Busca a pagina do lead: resolve DNS, segue redirects, mede status e tempo.

Principio 1 do CLAUDE.md: **coletor nunca propaga excecao para fora**. Toda falha
sai daqui como `RespostaDoSite` com `motivo_falha` no enum da secao 8.3. Falha
registrada e dado consultavel em SQL; falha como excecao e log que ninguem le.

E o motivo da falha vem SEMPRE ao lado do html, nunca no lugar dele: duas das
treze fixtures reais responderam 403 e uma respondeu 404, e as tres ainda trazem
corpo suficiente para classificar a plataforma. Descartar o corpo por causa do
status tiraria da lista leads T1 legitimos.
"""

import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

from discoveryleads.core.falhas import MotivoDeFalha

MAX_REDIRECTS = 5
TIMEOUT_S = 10.0

# User-Agent de navegador. Nao e disfarce: e o que faz a pagina entregar o mesmo
# HTML que o operador ve quando abre o link para conferir o lead na frente do
# cliente. Coletor que ve conteudo diferente do operador produz argumento que nao
# se sustenta.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


@dataclass(frozen=True)
class RespostaDoSite:
    url_final: str | None = None
    http_status: int | None = None
    redirects: int = 0
    tempo_resposta_ms: int = 0
    html: str = ""
    motivo_falha: MotivoDeFalha | None = None


def _motivo_do_status(status: int) -> MotivoDeFalha | None:
    if status < 400:
        return None
    if status in (401, 403, 429):
        return MotivoDeFalha.BLOQUEADO
    if status in (404, 410):
        return MotivoDeFalha.NAO_ENCONTRADO
    return MotivoDeFalha.RESPOSTA_INVALIDA


def _motivo_da_excecao(erro: Exception) -> MotivoDeFalha:
    if isinstance(erro, httpx.TimeoutException):
        return MotivoDeFalha.TIMEOUT
    if isinstance(erro, httpx.TooManyRedirects):
        return MotivoDeFalha.RESPOSTA_INVALIDA
    if isinstance(erro, httpx.TransportError):
        return MotivoDeFalha.REDE_INDISPONIVEL
    return MotivoDeFalha.RESPOSTA_INVALIDA


def _resolver_dns_de_verdade(host: str) -> bool:
    """Passo separado de proposito.

    Distinguir "o dominio nao existe" de "a rede falhou" e o que separa um lead
    cujo site morreu — sinal forte, elegivel por SITE_QUEBRADO — de um problema
    passageiro da maquina do operador, que so deveria reduzir a confianca.
    """
    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    return True


async def buscar_site(
    url: str,
    *,
    resolve_dns: Callable[[str], bool] = _resolver_dns_de_verdade,
    timeout_s: float = TIMEOUT_S,
) -> RespostaDoSite:
    host = urlsplit(url).hostname or ""
    if not host or not resolve_dns(host):
        return RespostaDoSite(motivo_falha=MotivoDeFalha.DOMINIO_NAO_RESOLVE)

    comeco = time.monotonic()
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            timeout=timeout_s,
            headers={"User-Agent": USER_AGENT},
        ) as cliente:
            resposta = await cliente.get(url)
    except Exception as erro:  # principio 1: nada escapa daqui
        return RespostaDoSite(
            tempo_resposta_ms=int((time.monotonic() - comeco) * 1000),
            motivo_falha=_motivo_da_excecao(erro),
        )

    return RespostaDoSite(
        url_final=str(resposta.url),
        http_status=resposta.status_code,
        redirects=len(resposta.history),
        tempo_resposta_ms=int((time.monotonic() - comeco) * 1000),
        html=resposta.text,
        motivo_falha=_motivo_do_status(resposta.status_code),
    )
