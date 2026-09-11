"""Export CSV — peca 4, com as regras de tela da emenda de 2026-09-11.

Ate a E7 existir o CSV e o unico lugar onde o operador ve os leads, entao cada
coluna carrega uma regra que a spec pos na tela: motivo em frase, evidencia com
coletor e momento, limites que nunca somem, rastreamento que nunca fica vazio
nem afirma que o negocio "nao anuncia".

Formato: separador `;` e UTF-8 com BOM, o que o Excel em portugues abre com
acentos e colunas certas por clique duplo.
"""

import csv
from datetime import datetime, tzinfo
from pathlib import Path
from urllib.parse import quote

from discoveryleads.collectors.site_analise import SINAIS_DE_RASTREAMENTO
from discoveryleads.collectors.site_extracao import whatsapp_de
from discoveryleads.core.normalizacao import telefone_e164
from discoveryleads.core.sinais import Signal
from discoveryleads.scoring.elegibilidade import Elegibilidade

COLUNAS = (
    "nome",
    "telefone",
    "endereco",
    "faixa",
    "elegibilidade",
    "motivo",
    "evidencia",
    "limites",
    "plataforma",
    "url",
    "rastreamento",
    "avaliacoes",
    "nota",
    "maps",
    "whatsapp_link",
    "whatsapp_origem",
)


def _valor(sinais: dict[str, Signal], tipo: str) -> object:
    sinal = sinais.get(tipo)
    return sinal.valor if sinal is not None else None


def _valor_legivel(valor: object) -> str:
    if valor is None:
        return "nulo"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, list):
        return ",".join(str(item) for item in valor)
    return str(valor)


def formatar_evidencia(sinal: Signal, fuso: tzinfo | None = None) -> str:
    """`site.plataforma=canva · site_classifier · 2026-09-11 11:02`, na hora local."""
    momento = datetime.fromisoformat(sinal.observado_em).astimezone(fuso)
    return f"{sinal.tipo}={_valor_legivel(sinal.valor)} · {sinal.coletor} · {momento:%Y-%m-%d %H:%M}"


def _limites(sinais: dict[str, Signal]) -> str:
    """O que a linha nao sabe. Falha de coletor entra aqui e nunca some."""
    partes = []
    falha = _valor(sinais, "collector.site_fetcher.failed")
    if falha:
        texto = f"site: {falha}"
        status = _valor(sinais, "site.http_status")
        if status is not None:
            texto += f" ({status})"
        plataforma = _valor(sinais, "site.plataforma")
        if plataforma is None:
            texto += ", plataforma desconhecida"
        elif plataforma != "quebrado":
            texto += ", plataforma pelo domínio"
        partes.append(texto)
    falha_de_leitura = _valor(sinais, "collector.site_classifier.failed")
    if falha_de_leitura:
        partes.append(f"leitura do HTML: {falha_de_leitura}")
    return "; ".join(partes)


def _rastreamento(sinais: dict[str, Signal]) -> str:
    if _valor(sinais, "places.sem_site") is True:
        return "sem site"
    perfil = _valor(sinais, "site.perfil_no_lugar_do_site")
    if perfil:
        return f"sem site: {perfil}"
    if not any(f"tracking.{nome}" in sinais for nome in SINAIS_DE_RASTREAMENTO):
        falha = _valor(sinais, "collector.site_fetcher.failed")
        return f"site não lido ({falha})" if falha else "site não lido"

    achados = []
    for nome in SINAIS_DE_RASTREAMENTO:
        if _valor(sinais, f"tracking.{nome}") is not True:
            continue
        if nome == "meta_pixel" and not _valor(sinais, "tracking.eventos_conversao"):
            achados.append("meta_pixel sem evento de conversão")
        else:
            achados.append(nome)
    # Nao achar no HTML sem JavaScript nao prova ausencia de anuncio.
    return ", ".join(achados) if achados else "nenhum visível no HTML cru"


def _whatsapp(sinais: dict[str, Signal]) -> tuple[str, str]:
    do_site = _valor(sinais, "site.whatsapp_link")
    if do_site:
        return str(do_site), "site"
    # O proprio campo "site" do Google pode ser o link — e as vezes e o unico
    # contato do lead (Casa Z, primeira busca real, sem telefone). O destino
    # do redirect vem antes da origem, e whatsapp_de descarta `?phone=` vazio.
    for tipo in ("site.url_final", "places.website_uri"):
        link = _valor(sinais, tipo)
        if link and whatsapp_de(str(link)) is not None:
            return str(link), "link de WhatsApp no Google"
    e164 = telefone_e164(_valor(sinais, "places.telefone"))
    if e164 and _valor(sinais, "telefone.e_movel") is True:
        return f"https://wa.me/{e164.removeprefix('+')}", "telefone do Places, móvel inferido"
    return "", ""


def _numero(valor: object) -> str:
    return "" if valor is None else str(valor).replace(".", ",")


def _link_do_maps(nome: str, place_id: str) -> str:
    return (
        "https://www.google.com/maps/search/?api=1"
        f"&query={quote(nome)}&query_place_id={quote(place_id)}"
    )


def _plataforma(sinais: dict[str, Signal]) -> str:
    plataforma = _valor(sinais, "site.plataforma")
    if plataforma:
        return str(plataforma)
    return "perfil" if _valor(sinais, "site.perfil_no_lugar_do_site") else "desconhecida"


def linha_csv(
    *,
    nome: str,
    endereco: str | None,
    place_id: str,
    sinais: dict[str, Signal],
    elegibilidade: Elegibilidade,
    faixa: str | None,
    evidencia_da_faixa: tuple[Signal, ...] = (),
    fuso: tzinfo | None = None,
) -> dict[str, str]:
    whatsapp_link, whatsapp_origem = _whatsapp(sinais)
    evidencias = elegibilidade.evidencia + evidencia_da_faixa
    return {
        "nome": nome,
        "telefone": str(_valor(sinais, "places.telefone") or ""),
        "endereco": endereco or "",
        "faixa": faixa or "",
        "elegibilidade": elegibilidade.categoria.value,
        "motivo": elegibilidade.motivo,
        "evidencia": " | ".join(formatar_evidencia(sinal, fuso) for sinal in evidencias),
        "limites": _limites(sinais),
        "plataforma": _plataforma(sinais),
        "url": str(_valor(sinais, "site.url_final") or _valor(sinais, "places.website_uri") or ""),
        "rastreamento": _rastreamento(sinais),
        "avaliacoes": str(_valor(sinais, "places.avaliacoes_total") or 0),
        "nota": _numero(_valor(sinais, "places.nota")),
        "maps": _link_do_maps(nome, place_id),
        "whatsapp_link": whatsapp_link,
        "whatsapp_origem": whatsapp_origem,
    }


def escrever_csv(linhas: list[dict[str, str]], caminho: Path) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS, delimiter=";")
        escritor.writeheader()
        escritor.writerows(linhas)
