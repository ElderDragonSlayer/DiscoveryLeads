"""O enum central do sistema.

Definido na secao 5 da spec do backend (`site.plataforma`). Toda a elegibilidade
da secao 6.1 e derivada daqui, entao acrescentar valor sem atualizar a spec quebra
o contrato entre coletor e pontuador.
"""

from enum import Enum


class Plataforma(str, Enum):
    CANVA = "canva"
    AGREGADOR = "agregador"
    GOOGLE_SITES_EXTINTO = "google_sites_extinto"
    WIX = "wix"
    WORDPRESS = "wordpress"
    SHOPIFY = "shopify"
    LOJA_INTEGRADA = "loja_integrada"
    PROPRIO = "proprio"
    QUEBRADO = "quebrado"
    AUSENTE = "ausente"
