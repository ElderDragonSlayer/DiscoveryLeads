"""Classifica a plataforma de um site a partir da URL e do HTML ja baixado.

Sem rede, sem custo. E o diferencial do produto, e a peca onde falso positivo
custa credibilidade na frente do cliente.

As assinaturas moram em `config/platforms.toml`, fora do codigo. A ordem das
secoes daquele arquivo e a ordem de precedencia — ver o cabecalho de la.
"""

from discoveryleads.collectors.site_fetcher import RespostaDoSite
from discoveryleads.core.configuracao import carregar
from discoveryleads.core.falhas import MotivoDeFalha
from discoveryleads.core.normalizacao import dominio_casa, dominio_de
from discoveryleads.core.plataformas import Plataforma

# O servidor recusando o coletor, nao o site fora do ar (armadilha 7 do spike).
STATUS_DE_BLOQUEIO = frozenset({401, 403, 429})


def _tabela() -> dict[Plataforma, dict]:
    """As regras de `platforms.toml`, na ordem em que estao escritas."""
    return {
        Plataforma(nome): regra for nome, regra in carregar("platforms.toml").items()
    }


def plataforma_pelo_dominio(url: str) -> Plataforma | None:
    dominio = dominio_de(url)
    for plataforma, regra in _tabela().items():
        if any(dominio_casa(dominio, d) for d in regra["dominios"]):
            return plataforma
    return None


def plataforma_pela_assinatura(html: str) -> Plataforma | None:
    for plataforma, regra in _tabela().items():
        if any(assinatura in html for assinatura in regra["assinaturas"]):
            return plataforma
    return None


def classificar_plataforma(
    url: str, html: str, http_status: int = 200
) -> Plataforma | None:
    """Devolve `site.plataforma` para uma pagina ja baixada, ou None se nao da
    para saber.

    A ordem das regras e o que decide a faixa do lead:

    1. **Dominio antes de assinatura.**
    2. **Assinatura antes de status.** E o que faz um `*.business.site`
       continuar GOOGLE_SITES_EXTINTO depois de um 404, e uma loja atras de
       anti-bot continuar `loja_integrada` depois de um 403.
    3. **Bloqueio nao e quebra.** 401, 403 e 429 sem dominio nem assinatura
       devolvem None.
    4. **Status por ultimo**, quando nao sobrou mais nada para dizer o que era.
    """
    encontrada = plataforma_pelo_dominio(url) or plataforma_pela_assinatura(html)
    if encontrada is not None:
        return encontrada
    if http_status in STATUS_DE_BLOQUEIO:
        return None
    if http_status >= 400:
        return Plataforma.QUEBRADO
    return Plataforma.PROPRIO


def classificar_resposta(url: str, resposta: RespostaDoSite) -> Plataforma | None:
    """`site.plataforma` a partir do que o fetcher trouxe — inclusive quando nao
    trouxe resposta nenhuma.

    O dominio de ORIGEM vem antes do de destino: `negocio.site` redireciona para
    o perfil do Google, e so a origem diz que era Google Sites (spike S4).
    """
    por_dominio = plataforma_pelo_dominio(url)
    if por_dominio is None and resposta.url_final:
        por_dominio = plataforma_pelo_dominio(resposta.url_final)
    if por_dominio is not None:
        return por_dominio

    if resposta.http_status is not None:
        return classificar_plataforma(
            resposta.url_final or url, resposta.html, resposta.http_status
        )

    # Sem resposta HTTP. So duas falhas provam que o site esta fora do ar para o
    # cliente do lead; timeout e rede sao problema do coletor.
    if resposta.motivo_falha is MotivoDeFalha.DOMINIO_NAO_RESOLVE:
        return Plataforma.QUEBRADO
    if resposta.https_valido is False:
        return Plataforma.QUEBRADO
    return None
