from discoveryleads.core.sinais import Signal, agora_iso


def test_valor_vira_json_sem_escapar_acento():
    sinal = Signal(
        tipo="site.title",
        valor="Salão da Ana",
        fonte="site",
        coletor="site_classifier",
        versao=1,
        observado_em="2026-09-11T14:02:00+00:00",
    )

    assert sinal.valor_json() == '"Salão da Ana"'


def test_agora_iso_e_utc_com_precisao_de_segundo():
    momento = agora_iso()

    assert momento.endswith("+00:00")
    assert len(momento) == len("2026-09-11T14:02:00+00:00")
