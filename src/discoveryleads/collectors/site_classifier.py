"""Classifica a plataforma de um site a partir da URL e do HTML ja baixado.

Sem rede, sem custo. E o diferencial do produto, e a peca onde falso positivo
custa credibilidade na frente do cliente.

As assinaturas moram em `config/platforms.toml`, fora do codigo. A ordem das
secoes daquele arquivo e a ordem de precedencia — ver o cabecalho de la.
"""

from discoveryleads.core.configuracao import carregar
from discoveryleads.core.normalizacao import dominio_casa, dominio_de
from discoveryleads.core.plataformas import Plataforma


def _tabela() -> dict[Plataforma, dict]:
    """As regras de `platforms.toml`, na ordem em que estao escritas."""
    return {
        Plataforma(nome): regra for nome, regra in carregar("platforms.toml").items()
    }


def classificar_plataforma(url: str, html: str, http_status: int = 200) -> Plataforma:
    """Devolve `site.plataforma` para uma pagina ja baixada.

    A ordem das regras nao e estetica, e o que decide a faixa do lead:

    1. **Dominio antes de assinatura.**
    2. **Assinatura antes de status.** E o que faz um `*.business.site` continuar
       sendo GOOGLE_SITES_EXTINTO (faixa T1) em vez de virar SITE_QUEBRADO (que
       nao tem faixa) so porque respondeu 404, e o que faz uma loja atras de
       anti-bot continuar sendo `loja_integrada` depois de um 403.
    3. **Status por ultimo**, quando nao sobrou mais nada para dizer o que era.
    """
    tabela = _tabela()
    dominio = dominio_de(url)

    for plataforma, regra in tabela.items():
        if any(dominio_casa(dominio, d) for d in regra["dominios"]):
            return plataforma

    for plataforma, regra in tabela.items():
        if any(assinatura in html for assinatura in regra["assinaturas"]):
            return plataforma

    if http_status >= 400:
        return Plataforma.QUEBRADO

    return Plataforma.PROPRIO
