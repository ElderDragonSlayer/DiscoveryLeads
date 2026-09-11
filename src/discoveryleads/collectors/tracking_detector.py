"""Detecta rastreamento no HTML ja baixado. Sem rede, sem custo.

Peso maximo, pela secao 6.2 da spec: rastreamento pago presente e o que promove um
lead elegivel para a faixa T0, o topo da lista. Por isso as regras aqui sao
deliberadamente estreitas — em toda duvida, o detector diz "nao".

Duas fontes de evidencia, e nunca substring solta:

**Assinatura de script**, para site que carrega a tag por conta propria
(`fbq(`, `gtm.js`).

**Campo nomeado do lojista**, para agregador que hospeda a tag em nome dele. A
Linktree guarda o pixel do lojista em `"facebookPixelId"` e, ao lado, mantem
`"metaPixelConsentId"` com um valor constante que e DELA, identico em toda pagina
da plataforma. Casar "pixel" por substring marca todo Linktree como T0.
Ver docs/superpowers/specs/2026-09-10-spike-s4-e-armadilhas.md
"""

import re
from dataclasses import dataclass, field

ASSINATURAS_META_PIXEL = ("fbq(", "connect.facebook.net")
ASSINATURAS_GTM = ("googletagmanager.com/gtm.js",)
ASSINATURAS_TIKTOK_PIXEL = ("analytics.tiktok.com",)
ASSINATURAS_HEATMAP = ("static.hotjar.com", "hotjar.com/c/hotjar", "clarity.ms")

# Campos que o agregador preenche com o identificador DO LOJISTA. Os campos
# vizinhos terminados em `ConsentId` sao da plataforma e nao entram aqui.
CAMPO_META_PIXEL = "facebookPixelId"
CAMPO_TIKTOK_PIXEL = "tiktokPixelId"

# Secao 5 da spec nomeia Purchase e Lead. PageView nao entra: e o evento que o
# Pixel dispara sozinho ao carregar, e conta-lo como conversao apagaria o
# argumento de venda de "paga anuncio e nao mede retorno".
EVENTOS_DE_CONVERSAO = ("Purchase", "Lead")

PADRAO_EVENTO_FBQ = re.compile(r"""fbq\(\s*['"]track['"]\s*,\s*['"]([A-Za-z]+)['"]""")


@dataclass(frozen=True)
class Rastreamento:
    meta_pixel: bool = False
    gtm: bool = False
    tiktok_pixel: bool = False
    google_analytics: bool = False
    google_ads: bool = False
    heatmap: bool = False
    eventos_conversao: list[str] = field(default_factory=list)


def _id_de_medicao(html: str, prefixo: str) -> bool:
    """Procura um id de medicao do Google ancorado em contexto de verdade.

    Duas ancoras, as unicas duas formas em que o id realmente aparece:

        googletagmanager.com/gtag/js?id=G-XXXXXXXXXX
        gtag('config', 'G-XXXXXXXXXX')

    SENSIVEL A MAIUSCULA, de proposito. Casar `G-` solto e sem distinguir caixa
    devolveu, nas fixtures, oito falsos positivos que eram nome de classe CSS —
    g-animation, g-recaptcha, g-progress. Ancorar e distinguir caixa derruba os
    oito e mantem o unico id verdadeiro.
    """
    padrao = re.compile(
        rf"gtag/js\?id={prefixo}-[A-Z0-9]{{6,}}"
        rf"""|gtag\(\s*['"]config['"]\s*,\s*['"]{prefixo}-[A-Z0-9]{{6,}}['"]"""
    )
    return padrao.search(html) is not None


def _campo_json_preenchido(html: str, campo: str) -> bool:
    """Verdadeiro so quando o campo tem valor de texto nao vazio.

    `"facebookPixelId":null` e `"facebookPixelId":""` sao ambos falso — que e o
    estado de toda conta de Linktree em plano gratuito.
    """
    padrao = re.compile(rf'"{re.escape(campo)}"\s*:\s*"([^"]+)"')
    return padrao.search(html) is not None


def _eventos_de_conversao(html: str) -> list[str]:
    """Eventos de conversao disparados pelo Pixel, na ordem, sem repetir."""
    vistos: dict[str, None] = {}
    for encontrado in PADRAO_EVENTO_FBQ.finditer(html):
        evento = encontrado.group(1)
        if evento in EVENTOS_DE_CONVERSAO:
            vistos[evento] = None
    return list(vistos)


def detectar_rastreamento(html: str) -> Rastreamento:
    return Rastreamento(
        meta_pixel=(
            any(a in html for a in ASSINATURAS_META_PIXEL)
            or _campo_json_preenchido(html, CAMPO_META_PIXEL)
        ),
        gtm=any(a in html for a in ASSINATURAS_GTM),
        tiktok_pixel=(
            any(a in html for a in ASSINATURAS_TIKTOK_PIXEL)
            or _campo_json_preenchido(html, CAMPO_TIKTOK_PIXEL)
        ),
        google_analytics=_id_de_medicao(html, "G"),
        google_ads=_id_de_medicao(html, "AW"),
        heatmap=any(a in html for a in ASSINATURAS_HEATMAP),
        eventos_conversao=_eventos_de_conversao(html),
    )
