"""Descoberta pelo Google Places — Text Search (New), raio unico, paginada.

Peca 2 da Fatia Dia 1. Cada requisicao conta no `Orcamento` antes de ser feita,
inclusive a que falha. Nada levanta excecao: falha volta como `motivo_falha`
do enum da secao 8.3.

So sinais derivados saem daqui; o JSON cru do Google nao e guardado (spike S3).
"""

from dataclasses import dataclass, field

import httpx

from discoveryleads.core.falhas import MotivoDeFalha
from discoveryleads.core.normalizacao import ddd, e_movel, telefone_e164
from discoveryleads.core.orcamento import Orcamento
from discoveryleads.core.sinais import Signal

URL_TEXT_SEARCH = "https://places.googleapis.com/v1/places:searchText"
VERSAO = 1
TIMEOUT_S = 20.0

# `places.id` nao estava na lista da fatia e e o que permite dedupe por
# place_id. E da faixa Essentials IDs Only; a chamada ja e cobrada como
# Enterprise por causa de telefone, site e avaliacoes.
CAMPOS_BUSCA = (
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.types",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
    "places.priceLevel",
    "nextPageToken",
)
CAMPOS_CENTRO = ("places.location",)

# Limite documentado da Text Search (New): 60 resultados, 20 por pagina.
MAX_PAGINAS = 3
TAMANHO_DA_PAGINA = 20

NIVEL_DE_PRECO = {
    "PRICE_LEVEL_FREE": 0,
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}


@dataclass(frozen=True)
class Lugar:
    place_id: str
    nome: str
    endereco: str | None
    lat: float | None
    lng: float | None
    telefone: str | None  # nacional, como o Google manda: "(62) 99999-8888"
    website: str | None
    nota: float | None
    avaliacoes: int
    status: str | None
    tipos: tuple[str, ...]
    nivel_preco: int | None


@dataclass
class ResultadoDaBusca:
    lugares: list[Lugar] = field(default_factory=list)
    teto_atingido: bool = False
    motivo_falha: MotivoDeFalha | None = None
    # Mensagem de erro do Google, so para o terminal. O que se grava e o motivo
    # em enum — principio 1.
    detalhe: str | None = None


def _lugar(bruto: dict) -> Lugar | None:
    place_id = bruto.get("id")
    if not place_id:
        return None
    local = bruto.get("location") or {}
    return Lugar(
        place_id=place_id,
        nome=(bruto.get("displayName") or {}).get("text") or "",
        endereco=bruto.get("formattedAddress"),
        lat=local.get("latitude"),
        lng=local.get("longitude"),
        telefone=bruto.get("nationalPhoneNumber"),
        website=bruto.get("websiteUri") or None,
        nota=bruto.get("rating"),
        avaliacoes=int(bruto.get("userRatingCount") or 0),
        status=bruto.get("businessStatus"),
        tipos=tuple(bruto.get("types") or ()),
        nivel_preco=NIVEL_DE_PRECO.get(bruto.get("priceLevel")),
    )


def _motivo_do_status(status: int) -> MotivoDeFalha:
    if status == 429:
        return MotivoDeFalha.COTA_ESTOURADA
    if status in (401, 403):
        return MotivoDeFalha.BLOQUEADO
    return MotivoDeFalha.RESPOSTA_INVALIDA


async def _chamar(
    cliente: httpx.AsyncClient,
    chave: str,
    corpo: dict,
    campos: tuple[str, ...],
    orcamento: Orcamento,
) -> tuple[dict | None, MotivoDeFalha | None, str | None]:
    """Uma requisicao paga. Devolve (json, motivo_falha, detalhe)."""
    orcamento.registrar()
    try:
        resposta = await cliente.post(
            URL_TEXT_SEARCH,
            json=corpo,
            headers={"X-Goog-Api-Key": chave, "X-Goog-FieldMask": ",".join(campos)},
        )
    except httpx.TimeoutException:
        return None, MotivoDeFalha.TIMEOUT, None
    except httpx.TransportError:
        return None, MotivoDeFalha.REDE_INDISPONIVEL, None
    except httpx.HTTPError:
        return None, MotivoDeFalha.RESPOSTA_INVALIDA, None

    if resposta.status_code != 200:
        try:
            detalhe = (resposta.json().get("error") or {}).get("message")
        except ValueError:
            detalhe = None
        return None, _motivo_do_status(resposta.status_code), detalhe
    try:
        return resposta.json(), None, None
    except ValueError:
        return None, MotivoDeFalha.PARSE_FALHOU, None


async def descobrir(
    nicho: str, cidade: str, raio_m: int, *, chave: str, orcamento: Orcamento
) -> ResultadoDaBusca:
    resultado = ResultadoDaBusca()
    if not orcamento.pode_chamar():
        resultado.teto_atingido = True
        return resultado

    async with httpx.AsyncClient(timeout=TIMEOUT_S) as cliente:
        # Sem centro nao existe locationBias com raio. Uma chamada, contada.
        dados, motivo, detalhe = await _chamar(
            cliente,
            chave,
            {"textQuery": cidade, "pageSize": 1, "languageCode": "pt-BR", "regionCode": "BR"},
            CAMPOS_CENTRO,
            orcamento,
        )
        if motivo is not None:
            resultado.motivo_falha, resultado.detalhe = motivo, detalhe
            return resultado
        achados = dados.get("places") or []
        centro = (achados[0].get("location") if achados else None) or {}
        if "latitude" not in centro or "longitude" not in centro:
            resultado.motivo_falha = MotivoDeFalha.NAO_ENCONTRADO
            resultado.detalhe = f"o Google não achou a região {cidade!r}"
            return resultado

        corpo = {
            "textQuery": f"{nicho} em {cidade}",
            "pageSize": TAMANHO_DA_PAGINA,
            "languageCode": "pt-BR",
            "regionCode": "BR",
            "locationBias": {
                "circle": {
                    "center": {"latitude": centro["latitude"], "longitude": centro["longitude"]},
                    "radius": float(raio_m),
                }
            },
        }
        vistos: dict[str, Lugar] = {}
        for _ in range(MAX_PAGINAS):
            if not orcamento.pode_chamar():
                resultado.teto_atingido = True
                break
            dados, motivo, detalhe = await _chamar(cliente, chave, corpo, CAMPOS_BUSCA, orcamento)
            if motivo is not None:
                resultado.motivo_falha, resultado.detalhe = motivo, detalhe
                break
            for bruto in dados.get("places") or []:
                lugar = _lugar(bruto)
                if lugar is not None:
                    vistos.setdefault(lugar.place_id, lugar)
            token = dados.get("nextPageToken")
            if not token:
                break
            corpo = {**corpo, "pageToken": token}

    resultado.lugares = list(vistos.values())
    return resultado


def sinais_do_lugar(lugar: Lugar, observado_em: str) -> list[Signal]:
    def sinal(tipo: str, valor: object) -> Signal:
        return Signal(
            tipo=tipo,
            valor=valor,
            fonte="places",
            coletor="places_discovery",
            versao=VERSAO,
            observado_em=observado_em,
        )

    sinais = [
        sinal("places.website_uri", lugar.website),
        sinal("places.sem_site", lugar.website is None),
        sinal("places.avaliacoes_total", lugar.avaliacoes),
        sinal("places.nota", lugar.nota),
        sinal("places.status", lugar.status),
        sinal("places.telefone", lugar.telefone),
        sinal("places.tipos", list(lugar.tipos)),
        sinal("places.price_level", lugar.nivel_preco),
    ]
    e164 = telefone_e164(lugar.telefone)
    if e164 is not None:
        sinais += [
            sinal("telefone.e_movel", e_movel(e164)),
            sinal("telefone.ddd", ddd(e164)),
        ]
    return sinais
