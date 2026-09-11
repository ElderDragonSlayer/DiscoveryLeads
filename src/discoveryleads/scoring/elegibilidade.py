"""Elegibilidade — a porta de entrada da secao 6.1, sempre com motivo.

O resultado nunca e um numero. E uma categoria, uma frase e os sinais que a
sustentam, porque o operador tem que poder ser checado na frente do cliente.

A ordem das regras e a ordem de precedencia: fechado, fora do nicho e franquia
vencem qualquer site; depois vem a falta de site; depois o que o site e.
"""

import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from discoveryleads.core.normalizacao import dominio_casa, dominio_de, telefone_e164
from discoveryleads.core.sinais import Signal

# Status que prova site fora do ar para o cliente do lead, alem de todo 5xx.
# 401, 403 e 429 ficam de fora: e o servidor recusando o coletor.
STATUS_DE_QUEBRA = frozenset({402, 404, 410})

CONSTRUTORES = frozenset({"wix", "wordpress", "shopify", "loja_integrada"})

STATUS_DO_GOOGLE = {
    "CLOSED_TEMPORARILY": "fechado temporariamente",
    "CLOSED_PERMANENTLY": "fechado de vez",
    "FUTURE_OPENING": "ainda não inaugurado",
}


class Categoria(str, Enum):
    # elegiveis — secao 6.1, mais SUBDOMINIO_GRATIS (decisao de 2026-09-11)
    SEM_SITE = "SEM_SITE"
    CANVA = "CANVA"
    AGREGADOR = "AGREGADOR"
    GOOGLE_SITES_EXTINTO = "GOOGLE_SITES_EXTINTO"
    SITE_QUEBRADO = "SITE_QUEBRADO"
    SUBDOMINIO_GRATIS = "SUBDOMINIO_GRATIS"
    # inelegiveis
    TEM_SITE_PROPRIO = "TEM_SITE_PROPRIO"
    FECHADO = "FECHADO"
    REDE_FRANQUIA = "REDE_FRANQUIA"
    FORA_DO_ICP = "FORA_DO_ICP"
    # o site nao foi lido e o dominio nao diz o que e
    INDETERMINADO = "INDETERMINADO"


ELEGIVEIS = frozenset(
    {
        Categoria.SEM_SITE,
        Categoria.CANVA,
        Categoria.AGREGADOR,
        Categoria.GOOGLE_SITES_EXTINTO,
        Categoria.SITE_QUEBRADO,
        Categoria.SUBDOMINIO_GRATIS,
    }
)


@dataclass(frozen=True)
class Elegibilidade:
    categoria: Categoria
    motivo: str
    evidencia: tuple[Signal, ...]

    @property
    def elegivel(self) -> bool:
        return self.categoria in ELEGIVEIS


def _valor(sinais: dict[str, Signal], tipo: str) -> object:
    sinal = sinais.get(tipo)
    return sinal.valor if sinal is not None else None


def _presentes(sinais: dict[str, Signal], *tipos: str) -> tuple[Signal, ...]:
    return tuple(sinais[tipo] for tipo in tipos if tipo in sinais)


def _endereco_curto(url: str) -> str:
    """"https://www.linktr.ee/Fascino/" -> "linktr.ee/Fascino"."""
    return url.split("://", 1)[-1].removeprefix("www.").rstrip("/")


def _e_quebra(status: object) -> bool:
    return isinstance(status, int) and (status in STATUS_DE_QUEBRA or status >= 500)


def _motivo_da_quebra(endereco: str, falha: object, status: object, https_valido: object) -> str:
    if falha == "dominio_nao_resolve":
        return f"elegível — o site {endereco} não existe mais (domínio não resolve)"
    if https_valido is False and status is None:
        return f"elegível — o site {endereco} tem certificado de segurança inválido"
    if status is not None:
        return f"elegível — o site {endereco} responde {status}"
    return f"elegível — o site {endereco} está fora do ar"


def avaliar_elegibilidade(
    sinais: dict[str, Signal],
    *,
    tipos_excluir: Iterable[str] = (),
    franquia: str | None = None,
    subdominios_gratis: Iterable[str] = (),
) -> Elegibilidade:
    status_google = _valor(sinais, "places.status")
    if status_google is not None and status_google != "OPERATIONAL":
        descricao = STATUS_DO_GOOGLE.get(status_google, status_google)
        return Elegibilidade(
            Categoria.FECHADO,
            f"inelegível — o Google marca o negócio como {descricao}",
            _presentes(sinais, "places.status"),
        )

    fora = sorted(set(_valor(sinais, "places.tipos") or ()) & set(tipos_excluir))
    if fora:
        return Elegibilidade(
            Categoria.FORA_DO_ICP,
            f"inelegível — tipo fora do nicho ({', '.join(fora)})",
            _presentes(sinais, "places.tipos"),
        )

    if franquia is not None:
        return Elegibilidade(
            Categoria.REDE_FRANQUIA,
            f"inelegível — rede ou franquia: {franquia}",
            _presentes(sinais, "places.telefone"),
        )

    if _valor(sinais, "places.sem_site") is True:
        return Elegibilidade(
            Categoria.SEM_SITE,
            "elegível — não tem site no Google",
            _presentes(sinais, "places.sem_site"),
        )

    url = _valor(sinais, "site.url_final") or _valor(sinais, "places.website_uri") or ""
    if not url:
        return Elegibilidade(
            Categoria.INDETERMINADO, "indeterminado — sem dados de site nem do Google", ()
        )

    endereco = _endereco_curto(url)
    dominio = dominio_de(url)
    plataforma = _valor(sinais, "site.plataforma")
    status = _valor(sinais, "site.http_status")
    falha = _valor(sinais, "collector.site_fetcher.failed")

    if plataforma is None:
        return Elegibilidade(
            Categoria.INDETERMINADO,
            f"indeterminado — o site {endereco} não pôde ser lido ({falha or 'sem resposta'})",
            _presentes(sinais, "collector.site_fetcher.failed"),
        )
    if plataforma == "google_sites_extinto":
        return Elegibilidade(
            Categoria.GOOGLE_SITES_EXTINTO,
            f"elegível — o site era do Google Sites, encerrado em 2024 ({endereco})",
            _presentes(sinais, "site.plataforma"),
        )
    if plataforma == "canva":
        return Elegibilidade(
            Categoria.CANVA,
            f"elegível — a página está em {endereco}, feita no Canva",
            _presentes(sinais, "site.plataforma"),
        )
    if plataforma == "agregador":
        return Elegibilidade(
            Categoria.AGREGADOR,
            f"elegível — o site é um agregador de links ({endereco})",
            _presentes(sinais, "site.plataforma"),
        )
    if plataforma == "quebrado":
        return Elegibilidade(
            Categoria.SITE_QUEBRADO,
            _motivo_da_quebra(endereco, falha, status, _valor(sinais, "site.https_valido")),
            _presentes(
                sinais,
                "site.plataforma",
                "site.http_status",
                "collector.site_fetcher.failed",
                "site.https_valido",
            ),
        )

    # Construtor ou site proprio. Status de erro so torna elegivel (decisao 4).
    if _e_quebra(status):
        return Elegibilidade(
            Categoria.SITE_QUEBRADO,
            f"elegível — o site {endereco} ({plataforma}) responde {status}",
            _presentes(sinais, "site.plataforma", "site.http_status"),
        )
    if plataforma in CONSTRUTORES and any(dominio_casa(dominio, d) for d in subdominios_gratis):
        return Elegibilidade(
            Categoria.SUBDOMINIO_GRATIS,
            f"elegível — o site está no subdomínio grátis {dominio} ({plataforma})",
            _presentes(sinais, "site.plataforma", "site.url_final"),
        )
    return Elegibilidade(
        Categoria.TEM_SITE_PROPRIO,
        f"inelegível — tem site próprio em {dominio} ({plataforma})",
        _presentes(sinais, "site.plataforma", "site.http_status"),
    )


def _nome_normalizado(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.casefold().split())


def identificar_franquias(
    lugares: Iterable[tuple[str, str, str | None]], minimo: int
) -> dict[str, str]:
    """`place_id -> descricao` de quem divide telefone ou nome com pelo menos
    `minimo` place_id da mesma busca (secao 6.1, REDE_FRANQUIA)."""
    por_telefone: dict[str, list[str]] = defaultdict(list)
    por_nome: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for place_id, nome, telefone in lugares:
        e164 = telefone_e164(telefone)
        if e164:
            por_telefone[e164].append(place_id)
        chave = _nome_normalizado(nome)
        if chave:
            por_nome[chave].append((place_id, nome))

    resultado: dict[str, str] = {}
    for e164, ids in por_telefone.items():
        if len(ids) >= minimo:
            for place_id in ids:
                resultado.setdefault(
                    place_id, f"o telefone {e164} aparece em {len(ids)} unidades da busca"
                )
    for itens in por_nome.values():
        if len(itens) >= minimo:
            exibido = itens[0][1]
            for place_id, _ in itens:
                resultado.setdefault(
                    place_id, f'o nome "{exibido}" aparece em {len(itens)} unidades da busca'
                )
    return resultado
