"""Agregadores de link achados na primeira busca real (Setor Bueno, 2026-09-11)
que sairam como TEM_SITE_PROPRIO porque o dominio nao estava em platforms.toml.

taplink.cc/cabeleireira respondeu 200 com o title "Cabeleireira at Taplink".
lojatree.com.br, que parecia outro, e uma loja de verdade ("TREE KIDS & TEENS",
tema UPStore) em dominio proprio — por isso NAO entra aqui.
"""

from discoveryleads.collectors.site_classifier import classificar_plataforma
from discoveryleads.core.plataformas import Plataforma


def test_taplink_e_agregador():
    assert classificar_plataforma("https://taplink.cc/cabeleireira", "") is Plataforma.AGREGADOR
