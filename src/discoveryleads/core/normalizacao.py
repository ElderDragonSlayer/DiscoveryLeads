"""Normalizacoes obrigatorias antes de gravar identidade (secao 4.2 da spec).

Dominio: minusculo, sem `www.`, sem porta, sem caminho.
"""

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
