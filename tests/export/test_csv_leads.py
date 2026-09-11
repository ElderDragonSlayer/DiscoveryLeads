from datetime import timedelta, timezone

from discoveryleads.core.sinais import Signal
from discoveryleads.export.csv_leads import COLUNAS, escrever_csv, formatar_evidencia, linha_csv
from discoveryleads.scoring.elegibilidade import Categoria, Elegibilidade

MOMENTO = "2026-09-11T14:02:00+00:00"
BRASILIA = timezone(timedelta(hours=-3))
RASTREAMENTOS = ("meta_pixel", "google_ads", "google_analytics", "gtm", "tiktok_pixel", "heatmap")


def _s(tipo, valor, coletor="site_classifier"):
    return Signal(tipo=tipo, valor=valor, fonte="site", coletor=coletor, versao=1, observado_em=MOMENTO)


def _sinais(*sinais):
    return {sinal.tipo: sinal for sinal in sinais}


def _linha(sinais, *, categoria=Categoria.CANVA, faixa="T1", evidencia=(), evidencia_da_faixa=()):
    return linha_csv(
        nome="Salão da Ana",
        endereco="Rua 1, Goiânia - GO",
        place_id="ChIJ-teste",
        sinais=sinais,
        elegibilidade=Elegibilidade(categoria, "elegível — teste", evidencia),
        faixa=faixa,
        evidencia_da_faixa=evidencia_da_faixa,
        fuso=BRASILIA,
    )


def test_evidencia_no_formato_da_emenda_e_na_hora_local():
    assert (
        formatar_evidencia(_s("site.plataforma", "canva"), BRASILIA)
        == "site.plataforma=canva · site_classifier · 2026-09-11 11:02"
    )


def test_evidencia_junta_a_da_elegibilidade_e_a_da_faixa():
    plataforma = _s("site.plataforma", "agregador")
    pixel = _s("tracking.meta_pixel", True, "tracking_detector")

    linha = _linha(
        _sinais(plataforma, pixel),
        categoria=Categoria.AGREGADOR,
        faixa="T0",
        evidencia=(plataforma,),
        evidencia_da_faixa=(pixel,),
    )

    assert linha["evidencia"] == (
        "site.plataforma=agregador · site_classifier · 2026-09-11 11:02"
        " | tracking.meta_pixel=true · tracking_detector · 2026-09-11 11:02"
    )


def test_bloqueio_aparece_em_limites_e_nao_apaga_a_plataforma():
    linha = _linha(
        _sinais(
            _s("collector.site_fetcher.failed", "bloqueado", "site_fetcher"),
            _s("site.http_status", 403, "site_fetcher"),
            _s("site.plataforma", "agregador"),
        )
    )

    assert linha["limites"] == "site: bloqueado (403), plataforma pelo domínio"
    assert linha["plataforma"] == "agregador"


def test_limites_fica_vazio_quando_nada_falhou():
    linha = _linha(
        _sinais(
            _s("collector.site_fetcher.failed", None, "site_fetcher"),
            _s("site.plataforma", "canva"),
        )
    )

    assert linha["limites"] == ""


def test_rastreamento_nunca_fica_vazio_nem_diz_que_nao_anuncia():
    lido_sem_nada = _linha(
        _sinais(*[_s(f"tracking.{nome}", False, "tracking_detector") for nome in RASTREAMENTOS])
    )
    sem_site = _linha(_sinais(_s("places.sem_site", True, "places_discovery")))
    nao_lido = _linha(_sinais(_s("collector.site_fetcher.failed", "timeout", "site_fetcher")))

    assert lido_sem_nada["rastreamento"] == "nenhum visível no HTML cru"
    assert sem_site["rastreamento"] == "sem site"
    assert nao_lido["rastreamento"] == "site não lido (timeout)"


def test_pixel_sem_evento_de_conversao_vira_argumento_na_coluna():
    """Secao 5: Pixel sem Purchase/Lead e anuncio pago sem medir retorno."""
    linha = _linha(
        _sinais(
            _s("tracking.meta_pixel", True, "tracking_detector"),
            _s("tracking.gtm", True, "tracking_detector"),
            _s("tracking.eventos_conversao", [], "tracking_detector"),
        )
    )

    assert linha["rastreamento"] == "meta_pixel sem evento de conversão, gtm"


def test_whatsapp_do_site_e_fato_mesmo_sem_telefone():
    """wa.me/message/<codigo> abre a conversa sem expor o numero (armadilha 4)."""
    linha = _linha(_sinais(_s("site.whatsapp_link", "https://wa.me/message/VR7BW3RWVSZAE1")))

    assert linha["whatsapp_link"] == "https://wa.me/message/VR7BW3RWVSZAE1"
    assert linha["whatsapp_origem"] == "site"
    assert linha["telefone"] == ""


def test_whatsapp_montado_do_celular_do_places_e_inferencia():
    linha = _linha(
        _sinais(
            _s("places.telefone", "(62) 99999-8888", "places_discovery"),
            _s("telefone.e_movel", True, "places_discovery"),
        )
    )

    assert linha["whatsapp_link"] == "https://wa.me/5562999998888"
    assert linha["whatsapp_origem"] == "telefone do Places, móvel inferido"


def test_telefone_fixo_nao_vira_whatsapp():
    linha = _linha(
        _sinais(
            _s("places.telefone", "(62) 3333-4444", "places_discovery"),
            _s("telefone.e_movel", False, "places_discovery"),
        )
    )

    assert (linha["whatsapp_link"], linha["whatsapp_origem"]) == ("", "")


def test_nota_sai_com_virgula_e_o_maps_usa_o_place_id():
    linha = _linha(_sinais(_s("places.nota", 4.8, "places_discovery")))

    assert linha["nota"] == "4,8"
    assert linha["maps"] == (
        "https://www.google.com/maps/search/?api=1"
        "&query=Sal%C3%A3o%20da%20Ana&query_place_id=ChIJ-teste"
    )


def test_arquivo_abre_no_excel_em_portugues(tmp_path):
    caminho = tmp_path / "saida" / "leads.csv"

    escrever_csv([_linha(_sinais(_s("site.plataforma", "canva")))], caminho)

    bruto = caminho.read_bytes()
    assert bruto.startswith(b"\xef\xbb\xbf")  # BOM: sem ele o Excel quebra os acentos
    texto = bruto.decode("utf-8-sig")
    assert texto.splitlines()[0] == ";".join(COLUNAS)
    assert "Salão da Ana" in texto
