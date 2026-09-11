"""Liga as quatro pecas da Fatia Dia 1: descobre, analisa, grava, avalia, exporta.

Execucao sequencial, com `asyncio.gather` limitado so na analise dos sites —
substituicao tatica da fila `jobs` nesta fatia.

Os sinais vao para o SQLite (historico desde a primeira busca), mas o CSV sai
dos sinais DESTA execucao, para nao misturar observacao velha com nova.
"""

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from datetime import tzinfo
from pathlib import Path

from discoveryleads.collectors.places_discovery import Lugar, descobrir, sinais_do_lugar
from discoveryleads.collectors.site_analise import analisar_site
from discoveryleads.core.configuracao import carregar
from discoveryleads.core.falhas import MotivoDeFalha
from discoveryleads.core.normalizacao import telefone_e164
from discoveryleads.core.orcamento import Orcamento
from discoveryleads.core.sinais import Signal, agora_iso
from discoveryleads.db.repositorio import abrir, gravar_lead, registrar_sinais
from discoveryleads.export.csv_leads import escrever_csv, linha_csv
from discoveryleads.scoring.elegibilidade import (
    Categoria,
    avaliar_elegibilidade,
    identificar_franquias,
)
from discoveryleads.scoring.faixas import calcular_faixa, chave_de_ordenacao

PARALELISMO_DE_SITES = 8


@dataclass
class Relatorio:
    chamadas_usadas: int
    teto: int
    teto_atingido: bool
    total: int = 0
    por_faixa: dict[str, int] = field(default_factory=dict)
    indeterminados: int = 0
    inelegiveis: int = 0
    motivo_falha: MotivoDeFalha | None = None
    detalhe: str | None = None
    saida: Path | None = None
    aviso_nicho: str | None = None


def _plataforma_ausente(observado_em: str) -> Signal:
    """Lugar sem website no Places: `site.plataforma = ausente` (secao 5)."""
    return Signal(
        tipo="site.plataforma",
        valor="ausente",
        fonte="places",
        coletor="site_classifier",
        versao=1,
        observado_em=observado_em,
    )


async def executar_busca(
    *,
    nicho: str,
    cidade: str,
    raio_m: int,
    max_chamadas: int,
    saida: Path,
    banco: Path,
    chave: str,
    descobrir_lugares=descobrir,
    analisar=analisar_site,
    paralelismo: int = PARALELISMO_DE_SITES,
    fuso: tzinfo | None = None,
) -> Relatorio:
    orcamento = Orcamento(teto=max_chamadas)
    busca = await descobrir_lugares(nicho, cidade, raio_m, chave=chave, orcamento=orcamento)
    relatorio = Relatorio(
        chamadas_usadas=orcamento.usadas,
        teto=orcamento.teto,
        teto_atingido=busca.teto_atingido,
        motivo_falha=busca.motivo_falha,
        detalhe=busca.detalhe,
    )
    if not busca.lugares:
        return relatorio

    observado_em = agora_iso()
    sinais_por_lugar = {
        lugar.place_id: sinais_do_lugar(lugar, observado_em) for lugar in busca.lugares
    }

    semaforo = asyncio.Semaphore(paralelismo)

    async def sinais_do_site(lugar: Lugar) -> list[Signal]:
        if lugar.website is None:
            return [_plataforma_ausente(observado_em)]
        async with semaforo:
            return await analisar(lugar.website, observado_em=agora_iso())

    dos_sites = await asyncio.gather(*(sinais_do_site(lugar) for lugar in busca.lugares))
    for lugar, sinais in zip(busca.lugares, dos_sites):
        sinais_por_lugar[lugar.place_id] += sinais

    conexao = abrir(banco)
    try:
        for lugar in busca.lugares:
            lead_id = gravar_lead(
                conexao,
                place_id=lugar.place_id,
                nome=lugar.nome,
                endereco=lugar.endereco,
                cidade=cidade,
                lat=lugar.lat,
                lng=lugar.lng,
                telefone_e164=telefone_e164(lugar.telefone),
                agora=observado_em,
            )
            registrar_sinais(conexao, lead_id, sinais_por_lugar[lugar.place_id])
        conexao.commit()
    finally:
        conexao.close()

    regras = carregar("scoring.toml")
    definicao_do_nicho = carregar("nichos.toml").get(nicho)
    if definicao_do_nicho is None:
        relatorio.aviso_nicho = (
            f'o nicho "{nicho}" não está em config/nichos.toml: nenhum tipo foi excluído'
        )
    tipos_excluir = (definicao_do_nicho or {}).get("tipos_excluir", [])
    franquias = identificar_franquias(
        ((lugar.place_id, lugar.nome, lugar.telefone) for lugar in busca.lugares),
        minimo=regras["elegibilidade"]["franquia_min_ocorrencias"],
    )

    avaliados = []
    for lugar in busca.lugares:
        sinais = {sinal.tipo: sinal for sinal in sinais_por_lugar[lugar.place_id]}
        elegibilidade = avaliar_elegibilidade(
            sinais,
            tipos_excluir=tipos_excluir,
            franquia=franquias.get(lugar.place_id),
            subdominios_gratis=regras["elegibilidade"]["subdominios_gratis"],
        )
        faixa, evidencia_da_faixa = calcular_faixa(
            elegibilidade,
            sinais,
            rastreamento_pago=regras["faixas"]["rastreamento_pago"],
            demanda_min_avaliacoes=regras["faixas"]["demanda_min_avaliacoes"],
        )
        linha = linha_csv(
            nome=lugar.nome,
            endereco=lugar.endereco,
            place_id=lugar.place_id,
            sinais=sinais,
            elegibilidade=elegibilidade,
            faixa=faixa,
            evidencia_da_faixa=evidencia_da_faixa,
            fuso=fuso,
        )
        ordem = chave_de_ordenacao(faixa, elegibilidade, lugar.avaliacoes)
        avaliados.append((ordem, linha, faixa, elegibilidade))

    avaliados.sort(key=lambda item: item[0])  # estavel: empate mantem a ordem do Google
    escrever_csv([linha for _, linha, _, _ in avaliados], saida)

    relatorio.total = len(avaliados)
    relatorio.por_faixa = dict(Counter(faixa for _, _, faixa, _ in avaliados if faixa))
    relatorio.indeterminados = sum(
        1 for _, _, _, e in avaliados if e.categoria is Categoria.INDETERMINADO
    )
    relatorio.inelegiveis = sum(
        1
        for _, _, faixa, e in avaliados
        if faixa is None and e.categoria is not Categoria.INDETERMINADO
    )
    relatorio.saida = saida
    return relatorio


def formatar_relatorio(relatorio: Relatorio) -> str:
    linhas = [f"Chamadas pagas ao Places: {relatorio.chamadas_usadas} de {relatorio.teto}"]
    if relatorio.teto_atingido:
        linhas.append(
            "  atenção: o teto parou a busca antes do fim — aumente --max-chamadas para ver o resto"
        )
    if relatorio.motivo_falha is not None:
        texto = f"  falha do Google: {relatorio.motivo_falha.value}"
        if relatorio.detalhe:
            texto += f" — {relatorio.detalhe}"
        linhas.append(texto)
    if relatorio.aviso_nicho:
        linhas.append(f"  aviso: {relatorio.aviso_nicho}")
    if relatorio.saida is None:
        linhas.append("Nenhum lead encontrado; nenhum CSV gravado.")
        return "\n".join(linhas)

    faixas = "  ".join(f"{f}: {relatorio.por_faixa.get(f, 0)}" for f in ("T0", "T1", "T2", "T3"))
    linhas += [
        f"Leads: {relatorio.total}   {faixas}   indeterminados: {relatorio.indeterminados}"
        f"   inelegíveis: {relatorio.inelegiveis}",
        f"CSV: {relatorio.saida}",
    ]
    return "\n".join(linhas)
