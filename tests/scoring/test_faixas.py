from discoveryleads.core.sinais import Signal
from discoveryleads.scoring.elegibilidade import Categoria, Elegibilidade
from discoveryleads.scoring.faixas import calcular_faixa, chave_de_ordenacao

MOMENTO = "2026-09-11T14:02:00+00:00"
PAGOS = ("meta_pixel", "google_ads", "tiktok_pixel")


def _sinais(*pares):
    return {
        tipo: Signal(
            tipo=tipo, valor=valor, fonte="teste", coletor="teste", versao=1, observado_em=MOMENTO
        )
        for tipo, valor in pares
    }


def _elegibilidade(categoria):
    return Elegibilidade(categoria, "motivo de teste", ())


def _faixa(categoria, *pares):
    return calcular_faixa(
        _elegibilidade(categoria),
        _sinais(*pares),
        rastreamento_pago=PAGOS,
        demanda_min_avaliacoes=20,
    )


def test_pixel_dentro_de_agregador_e_t0_com_a_evidencia_do_pixel():
    """O caso maximo da secao 6.2: substituto de landing page com verba provada."""
    faixa, evidencia = _faixa(Categoria.AGREGADOR, ("tracking.meta_pixel", True))

    assert faixa == "T0"
    assert [sinal.tipo for sinal in evidencia] == ["tracking.meta_pixel"]


def test_ga_e_gtm_sozinhos_nao_dao_t0():
    """Invariante da secao 12: T0 exige rastreamento PAGO."""
    faixa, _ = _faixa(
        Categoria.CANVA,
        ("tracking.google_analytics", True),
        ("tracking.gtm", True),
        ("tracking.meta_pixel", False),
    )

    assert faixa == "T1"


def test_site_quebrado_e_subdominio_gratis_sao_t1():
    assert _faixa(Categoria.SITE_QUEBRADO)[0] == "T1"
    assert _faixa(Categoria.SUBDOMINIO_GRATIS)[0] == "T1"


def test_sem_site_com_demanda_cai_em_t3_nesta_fatia():
    """Decisao 6: sem Instagram nao ha como provar intencao comercial de quem
    nao tem site, entao T2 fica vazia ate a E5."""
    faixa, _ = _faixa(Categoria.SEM_SITE, ("places.avaliacoes_total", 150))

    assert faixa == "T3"


def test_regra_do_t2_ja_existe_para_quando_a_intencao_chegar():
    faixa, evidencia = _faixa(
        Categoria.SEM_SITE,
        ("places.avaliacoes_total", 150),
        ("site.whatsapp_link", "https://wa.me/5562999998888"),
    )

    assert faixa == "T2"
    assert len(evidencia) == 2


def test_inelegivel_nao_tem_faixa_nem_com_pixel():
    faixa, evidencia = _faixa(Categoria.TEM_SITE_PROPRIO, ("tracking.meta_pixel", True))

    assert faixa is None
    assert evidencia == ()


def test_ordem_poe_a_faixa_antes_das_avaliacoes():
    t0 = chave_de_ordenacao("T0", _elegibilidade(Categoria.AGREGADOR), 3)
    t1_popular = chave_de_ordenacao("T1", _elegibilidade(Categoria.CANVA), 500)
    t1 = chave_de_ordenacao("T1", _elegibilidade(Categoria.CANVA), 40)
    t3 = chave_de_ordenacao("T3", _elegibilidade(Categoria.SEM_SITE), 900)
    indeterminado = chave_de_ordenacao(None, _elegibilidade(Categoria.INDETERMINADO), 1000)
    inelegivel = chave_de_ordenacao(None, _elegibilidade(Categoria.TEM_SITE_PROPRIO), 5000)

    embaralhado = [inelegivel, t3, t1, indeterminado, t1_popular, t0]

    assert sorted(embaralhado) == [t0, t1_popular, t1, t3, indeterminado, inelegivel]
