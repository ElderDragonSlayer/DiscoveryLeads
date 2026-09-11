"""Faixa de prioridade — o ranking da secao 6.2. Faixas discretas, nao soma.

A faixa decide a ordem. Dentro dela, nesta fatia, mais avaliacoes primeiro: o
`valor` da secao 6.3 ainda nao existe.
"""

from collections.abc import Iterable

from discoveryleads.core.sinais import Signal
from discoveryleads.scoring.elegibilidade import Categoria, Elegibilidade

# "Ja foi convencido de que precisa de presenca digital e escolheu a solucao
# pobre" (secao 6.2) — mais SITE_QUEBRADO e SUBDOMINIO_GRATIS (decisoes de
# 2026-09-11) e PERFIL_NO_LUGAR_DO_SITE (achado da primeira busca real).
SUBSTITUTO_IMPROVISADO = frozenset(
    {
        Categoria.CANVA,
        Categoria.AGREGADOR,
        Categoria.GOOGLE_SITES_EXTINTO,
        Categoria.SITE_QUEBRADO,
        Categoria.SUBDOMINIO_GRATIS,
        Categoria.PERFIL_NO_LUGAR_DO_SITE,
    }
)

ORDEM_DAS_FAIXAS = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}
GRUPO_INDETERMINADO = 4  # vale conferir a mao
GRUPO_INELEGIVEL = 5     # fica no CSV para a E4 enxergar falso negativo


def calcular_faixa(
    elegibilidade: Elegibilidade,
    sinais: dict[str, Signal],
    *,
    rastreamento_pago: Iterable[str],
    demanda_min_avaliacoes: int,
) -> tuple[str | None, tuple[Signal, ...]]:
    """Devolve a faixa e os sinais que a justificam. Inelegivel nao tem faixa."""
    if not elegibilidade.elegivel:
        return None, ()

    pagos = tuple(
        sinais[f"tracking.{nome}"]
        for nome in rastreamento_pago
        if f"tracking.{nome}" in sinais and sinais[f"tracking.{nome}"].valor is True
    )
    if pagos:
        return "T0", pagos

    if elegibilidade.categoria in SUBSTITUTO_IMPROVISADO:
        return "T1", ()

    # SEM_SITE. Intencao comercial e bio do Instagram (fora desta fatia) ou
    # WhatsApp no site — e quem nao tem site nao tem nenhum dos dois (decisao 6).
    avaliacoes = sinais.get("places.avaliacoes_total")
    whatsapp = sinais.get("site.whatsapp_link")
    demanda = avaliacoes is not None and (avaliacoes.valor or 0) >= demanda_min_avaliacoes
    intencao = whatsapp is not None and bool(whatsapp.valor)
    if demanda and intencao:
        return "T2", (avaliacoes, whatsapp)
    return "T3", ()


def chave_de_ordenacao(
    faixa: str | None, elegibilidade: Elegibilidade, avaliacoes: int
) -> tuple[int, int]:
    if faixa is not None:
        grupo = ORDEM_DAS_FAIXAS[faixa]
    elif elegibilidade.categoria is Categoria.INDETERMINADO:
        grupo = GRUPO_INDETERMINADO
    else:
        grupo = GRUPO_INELEGIVEL
    return (grupo, -avaliacoes)
