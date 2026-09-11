"""Extrai os sinais `site.*` do HTML ja baixado — defeitos vendaveis e contatos.

Duas tecnicas, cada uma por um motivo medido nas fixtures:

**Arvore** para o que e estrutura (title, meta). Um <title> dentro de <svg> e
indistinguivel do <title> do documento para uma regex, e o parser nao confunde os
dois porque um esta no head e o outro no body.

**Texto cru** para contatos. As paginas de Canva do conjunto tem ZERO <a href> de
WhatsApp: o link mora no JSON do design, em `"link":{"B":"https://wa.me/..."}`.
Um extrator que so leia o DOM nao acha contato nenhum justamente nas paginas de
Canva, que sao o lead T1 que a ferramenta existe para achar.

Ver docs/superpowers/specs/2026-09-10-spike-s4-e-armadilhas.md
"""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from selectolax.lexbor import LexborHTMLParser

HOSTS_WHATSAPP = frozenset({"wa.me", "api.whatsapp.com", "web.whatsapp.com"})

# URL solta em texto cru: termina em espaco, aspas, sinal de tag ou barra invertida.
# Serve tanto para href de HTML quanto para valor dentro de string JSON.
PADRAO_URL = re.compile(r"""https?://[^\s"'<>\\]+""")

_SO_DIGITOS = re.compile(r"\D")


PADRAO_EMAIL = re.compile(r"mailto:([A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,})")

# Perfil, nao publicacao: /p/, /reel/, /explore/ e afins nao sao o @ do negocio.
PADRAO_INSTAGRAM = re.compile(
    r"https?://(?:www\.)?instagram\.com/(?!p/|reel/|reels/|explore/|stories/)"
    r"([A-Za-z0-9_.]{2,30})"
)


@dataclass(frozen=True)
class SinaisDoSite:
    title: str | None = None
    meta_description: str | None = None
    viewport_presente: bool = False
    whatsapp_link: str | None = None
    whatsapp_telefone: str | None = None
    email: str | None = None
    instagram: str | None = None


def _texto_ou_nada(valor: str | None) -> str | None:
    """Vazio e so-espaco viram None.

    Tag presente com content="" e o mesmo defeito vendavel que tag ausente, e
    tratar os dois igual e o que impede o extrator de apagar o argumento de venda.
    """
    if valor is None:
        return None
    return valor.strip() or None


def _whatsapp_de(url: str) -> tuple[str, str | None] | None:
    """Interpreta uma URL como contato de WhatsApp.

    Devolve `(link, telefone_e164_ou_None)`, ou None se a URL nao for um contato
    util. Sao tres formas, e so duas dao numero:

        wa.me/<E164>                        -> link e telefone
        api.whatsapp.com/send?phone=<E164>  -> link e telefone
        wa.me/message/<CODIGO>              -> link, SEM telefone

    E ha a quarta, que nao e contato nenhum: `?phone=` com valor vazio. Aparece
    declarada no JSON-LD da Linktree, antes do link bom, e leva a lugar nenhum.
    """
    partes = urlsplit(url)
    host = (partes.hostname or "").removeprefix("www.")
    if host not in HOSTS_WHATSAPP:
        return None

    if host == "wa.me":
        caminho = partes.path.strip("/")
        if caminho.startswith("message/"):
            codigo = caminho.removeprefix("message/")
            return (url, None) if codigo else None
        digitos = _SO_DIGITOS.sub("", caminho)
        return (url, f"+{digitos}") if digitos else None

    telefone = parse_qs(partes.query).get("phone", [""])[0]
    digitos = _SO_DIGITOS.sub("", telefone)
    return (url, f"+{digitos}") if digitos else None


def _achar_whatsapp(html: str) -> tuple[str | None, str | None]:
    """Primeiro contato de WhatsApp util, na ordem do documento."""
    for encontrada in PADRAO_URL.finditer(html):
        achado = _whatsapp_de(encontrada.group())
        if achado is not None:
            return achado
    return (None, None)


def extrair_sinais(html: str) -> SinaisDoSite:
    arvore = LexborHTMLParser(html)

    no_title = arvore.css_first("head > title")
    title = _texto_ou_nada(no_title.text() if no_title else None)

    no_description = arvore.css_first('meta[name="description"]')
    meta_description = _texto_ou_nada(
        no_description.attributes.get("content") if no_description else None
    )

    whatsapp_link, whatsapp_telefone = _achar_whatsapp(html)

    email = PADRAO_EMAIL.search(html)
    instagram = PADRAO_INSTAGRAM.search(html)

    return SinaisDoSite(
        title=title,
        meta_description=meta_description,
        viewport_presente=arvore.css_first('meta[name="viewport"]') is not None,
        whatsapp_link=whatsapp_link,
        whatsapp_telefone=whatsapp_telefone,
        email=email.group(1) if email else None,
        instagram=instagram.group(1).lower() if instagram else None,
    )
