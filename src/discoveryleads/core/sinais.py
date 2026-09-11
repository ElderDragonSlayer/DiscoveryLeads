"""O sinal: a unidade de verdade do sistema (secao 4.3 da spec).

Tudo que a ferramenta sabe sobre um lead e uma lista de sinais, cada um com
origem, coletor e momento. Daqui saem a evidencia do CSV, o historico e a
rastreabilidade de origem que a LGPD pede.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Signal:
    tipo: str          # namespace fonte.nome, secao 5
    valor: object      # qualquer coisa que vire JSON
    fonte: str         # places | site
    coletor: str
    versao: int
    observado_em: str  # ISO 8601 em UTC
    confianca: float = 1.0

    def valor_json(self) -> str:
        return json.dumps(self.valor, ensure_ascii=False)


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
