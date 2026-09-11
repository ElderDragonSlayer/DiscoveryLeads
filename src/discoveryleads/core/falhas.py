"""Motivos de falha de coletor.

Secao 8.3 da spec, e principio 1 do CLAUDE.md: **enum, nunca string livre**.
Enum e agrupavel em SQL — "quantos leads do nicho nao resolvem DNS?" e uma
consulta. String livre e log que ninguem le.
"""

from enum import Enum


class MotivoDeFalha(str, Enum):
    TIMEOUT = "timeout"
    BLOQUEADO = "bloqueado"
    NAO_ENCONTRADO = "nao_encontrado"
    PARSE_FALHOU = "parse_falhou"
    COTA_ESTOURADA = "cota_estourada"
    REDE_INDISPONIVEL = "rede_indisponivel"
    RESPOSTA_INVALIDA = "resposta_invalida"
    DOMINIO_NAO_RESOLVE = "dominio_nao_resolve"
