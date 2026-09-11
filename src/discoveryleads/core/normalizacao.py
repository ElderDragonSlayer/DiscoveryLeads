"""Normalizacoes obrigatorias antes de gravar identidade (secao 4.2 da spec).

Dominio: minusculo, sem `www.`, sem porta, sem caminho.
Telefone: E.164 (`+5562999998888`), descartando formatacao.
"""

import re
from urllib.parse import urlsplit


def dominio_de(url: str) -> str:
    """Extrai o dominio normalizado de uma URL.

    Aceita URL sem esquema (`salao.com.br/precos`), que e como o `websiteUri` do
    Places as vezes chega.
    """
    if "//" not in url:
        url = f"//{url}"
    host = urlsplit(url).hostname or ""   # ja devolve minusculo e sem porta
    return host.removeprefix("www.")


def dominio_casa(dominio: str, alvo: str) -> bool:
    """Verdadeiro se `dominio` e o proprio `alvo` ou um subdominio dele.

    `dominio_casa("vocenosalao.my.canva.site", "my.canva.site")` -> True
    `dominio_casa("naoemycanva.site", "canva.site")` -> False
    """
    return dominio == alvo or dominio.endswith(f".{alvo}")


CODIGO_DO_BRASIL = "55"
_SO_DIGITOS = re.compile(r"\D")


def telefone_e164(telefone: str | None) -> str | None:
    """Telefone brasileiro em E.164: so digitos, prefixados por +55.

    "(62) 99999-8888" -> "+5562999998888". Devolve None quando nao sobra um
    numero nacional plausivel (DDD + 8 ou 9 digitos).

    O "55" do comeco so e codigo do pais quando o numero tem 12 ou 13 digitos.
    Com 10 ou 11, e o DDD do Rio Grande do Sul.
    """
    if not telefone:
        return None
    digitos = _SO_DIGITOS.sub("", telefone)
    if digitos.startswith(CODIGO_DO_BRASIL) and len(digitos) in (12, 13):
        digitos = digitos[len(CODIGO_DO_BRASIL):]
    elif digitos.startswith("0"):
        digitos = digitos[1:]  # zero de discagem interurbana: "062 ..."
    if len(digitos) not in (10, 11):
        return None
    return f"+{CODIGO_DO_BRASIL}{digitos}"


def e_movel(e164: str) -> bool:
    """Inferencia pelo nono digito: celular tem 11 digitos nacionais e comeca
    com 9 depois do DDD.

    Diz se o numero e de celular. NAO diz se tem WhatsApp — isso nao ha como
    verificar de forma limpa, e a secao 5 manda rotular como inferencia.
    """
    nacional = e164.removeprefix(f"+{CODIGO_DO_BRASIL}")
    return len(nacional) == 11 and nacional[2] == "9"


def ddd(e164: str) -> str:
    return e164.removeprefix(f"+{CODIGO_DO_BRASIL}")[:2]
