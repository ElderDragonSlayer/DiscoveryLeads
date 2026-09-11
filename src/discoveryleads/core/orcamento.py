"""Freio de chamadas pagas (principio 4 do CLAUDE.md).

Nesta fatia substitui o `cost_ledger`: um contador em memoria com teto. Sem
teto configurado, a busca nao roda.
"""

from dataclasses import dataclass


@dataclass
class Orcamento:
    teto: int
    usadas: int = 0

    def __post_init__(self) -> None:
        if self.teto < 1:
            raise ValueError("o teto de chamadas precisa ser pelo menos 1")

    @property
    def restantes(self) -> int:
        return self.teto - self.usadas

    def pode_chamar(self) -> bool:
        return self.usadas < self.teto

    def registrar(self) -> None:
        if not self.pode_chamar():
            raise RuntimeError("chamada acima do teto: pergunte pode_chamar() antes")
        self.usadas += 1
