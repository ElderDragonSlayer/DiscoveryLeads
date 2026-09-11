"""Analise completa do site de um lead: busca, classifica, extrai, rastreia.

Devolve sinais e nunca levanta excecao (principio 1). E a costura da peca 1 com
o resto do sistema: os modulos dela devolvem dataclasses, e daqui para frente
tudo e `Signal`.

Ausencia observada tambem vira sinal (valor None ou False): a visao de sinais
atuais pega a ultima observacao de cada tipo, e sem o "nao tem" explicito ela
continuaria mostrando o que uma coleta antiga viu.
"""

from collections.abc import Awaitable, Callable

from discoveryleads.collectors.site_classifier import classificar_resposta
from discoveryleads.collectors.site_extracao import extrair_sinais
from discoveryleads.collectors.site_fetcher import RespostaDoSite, buscar_site
from discoveryleads.collectors.tracking_detector import detectar_rastreamento
from discoveryleads.core.falhas import MotivoDeFalha
from discoveryleads.core.sinais import Signal

VERSAO = 1

SINAIS_DE_RASTREAMENTO = (
    "meta_pixel",
    "google_ads",
    "google_analytics",
    "gtm",
    "tiktok_pixel",
    "heatmap",
)


def _pagina_lida(resposta: RespostaDoSite) -> bool:
    """So a pagina que respondeu de verdade vale para contato e rastreamento.
    Desafio de anti-bot e pagina de erro nao sao a pagina do lead."""
    return resposta.http_status is not None and 200 <= resposta.http_status < 400


def sinais_da_resposta(
    url: str, resposta: RespostaDoSite, observado_em: str
) -> list[Signal]:
    def sinal(tipo: str, valor: object, coletor: str) -> Signal:
        return Signal(
            tipo=tipo,
            valor=valor,
            fonte="site",
            coletor=coletor,
            versao=VERSAO,
            observado_em=observado_em,
        )

    motivo = resposta.motivo_falha.value if resposta.motivo_falha else None
    sinais = [sinal("collector.site_fetcher.failed", motivo, "site_fetcher")]

    plataforma = classificar_resposta(url, resposta)
    if plataforma is not None:
        sinais.append(sinal("site.plataforma", plataforma.value, "site_classifier"))
    if resposta.url_final is not None:
        sinais.append(sinal("site.url_final", resposta.url_final, "site_fetcher"))
    if resposta.https_valido is not None:
        sinais.append(sinal("site.https_valido", resposta.https_valido, "site_fetcher"))
    if resposta.http_status is not None:
        sinais += [
            sinal("site.http_status", resposta.http_status, "site_fetcher"),
            sinal("site.redirects", resposta.redirects, "site_fetcher"),
            sinal("site.tempo_resposta_ms", resposta.tempo_resposta_ms, "site_fetcher"),
        ]

    if not _pagina_lida(resposta):
        return sinais

    try:
        extraidos = extrair_sinais(resposta.html)
        rastro = detectar_rastreamento(resposta.html)
    except Exception:  # principio 1
        sinais.append(
            sinal(
                "collector.site_classifier.failed",
                MotivoDeFalha.PARSE_FALHOU.value,
                "site_classifier",
            )
        )
        return sinais

    sociais = {"instagram": extraidos.instagram} if extraidos.instagram else {}
    sinais += [
        sinal("site.title", extraidos.title, "site_classifier"),
        sinal("site.meta_description", extraidos.meta_description, "site_classifier"),
        sinal("site.viewport_presente", extraidos.viewport_presente, "site_classifier"),
        sinal("site.whatsapp_link", extraidos.whatsapp_link, "site_classifier"),
        sinal("site.email", extraidos.email, "site_classifier"),
        sinal("site.links_sociais", sociais, "site_classifier"),
    ]
    sinais += [
        sinal(f"tracking.{nome}", getattr(rastro, nome), "tracking_detector")
        for nome in SINAIS_DE_RASTREAMENTO
    ]
    sinais.append(
        sinal("tracking.eventos_conversao", list(rastro.eventos_conversao), "tracking_detector")
    )
    return sinais


async def analisar_site(
    url: str,
    *,
    observado_em: str,
    buscar: Callable[[str], Awaitable[RespostaDoSite]] = buscar_site,
) -> list[Signal]:
    try:
        resposta = await buscar(url)
    except Exception:  # buscar_site nao levanta; um buscador injetado pode
        resposta = RespostaDoSite(motivo_falha=MotivoDeFalha.RESPOSTA_INVALIDA)
    return sinais_da_resposta(url, resposta, observado_em)
