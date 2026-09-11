"""Dois furos da versao 2 da primeira busca real (Setor Bueno, 2026-09-11).

1. "Blush Beauty Studio" e "DOM. Beaute" sairam como TEM_SITE_PROPRIO com url
   final em api.whatsapp.com: o "site" no Google era um endereco que
   REDIRECIONA para o WhatsApp, entao o dominio de origem nao batia com
   config/perfis.toml. O destino tambem tem que valer.

2. "Casa Z Exclusive Salon" (T1, 141 avaliacoes) nao tem telefone no Google. O
   unico contato e o link de WhatsApp no campo site, e ele nao ia para a coluna
   whatsapp_link do CSV.
"""

from discoveryleads.collectors.site_analise import analisar_site
from discoveryleads.collectors.site_fetcher import RespostaDoSite
from discoveryleads.core.sinais import Signal
from discoveryleads.export.csv_leads import linha_csv
from discoveryleads.scoring.elegibilidade import avaliar_elegibilidade

MOMENTO = "2026-09-11T14:02:00+00:00"
DESTINO = "https://api.whatsapp.com/send?phone=5562999998888"


def _sinal(tipo, valor, coletor="teste"):
    return Signal(tipo=tipo, valor=valor, fonte="teste", coletor=coletor, versao=1, observado_em=MOMENTO)


def _linha(sinais, nome="Casa Z Exclusive Salon"):
    return linha_csv(
        nome=nome,
        endereco=None,
        place_id="p1",
        sinais=sinais,
        elegibilidade=avaliar_elegibilidade(sinais),
        faixa="T1",
    )


def _perfil_whatsapp(website, url_final=None, telefone=None):
    sinais = {
        "places.website_uri": _sinal("places.website_uri", website, "places_discovery"),
        "places.sem_site": _sinal("places.sem_site", False, "places_discovery"),
        "site.perfil_no_lugar_do_site": _sinal(
            "site.perfil_no_lugar_do_site", "um link de WhatsApp", "site_classifier"
        ),
    }
    if url_final:
        sinais["site.url_final"] = _sinal("site.url_final", url_final, "site_fetcher")
    if telefone:
        sinais["places.telefone"] = _sinal("places.telefone", telefone, "places_discovery")
        sinais["telefone.e_movel"] = _sinal("telefone.e_movel", True, "places_discovery")
    return sinais


async def test_endereco_que_redireciona_para_o_whatsapp_e_perfil_no_lugar_do_site():
    resposta = RespostaDoSite(
        url_final=DESTINO,
        http_status=200,
        redirects=1,
        html="<html><head><title>WhatsApp</title></head></html>",
        https_valido=True,
    )

    async def buscar(url):
        return resposta

    sinais = {
        s.tipo: s
        for s in await analisar_site("https://wa.link/abc123", observado_em=MOMENTO, buscar=buscar)
    }

    assert sinais["site.perfil_no_lugar_do_site"].valor == "um link de WhatsApp"
    assert sinais["site.url_final"].valor == DESTINO
    assert "site.plataforma" not in sinais


def test_link_de_whatsapp_no_campo_site_vai_para_a_coluna_do_whatsapp():
    link = "https://wa.me/5562984527240"

    linha = _linha(_perfil_whatsapp(link))

    assert linha["whatsapp_link"] == link
    assert linha["whatsapp_origem"] == "link de WhatsApp no Google"
    assert linha["telefone"] == ""


def test_whatsapp_de_endereco_que_redireciona_usa_o_destino():
    linha = _linha(_perfil_whatsapp("https://wa.link/abc123", url_final=DESTINO))

    assert linha["whatsapp_link"] == DESTINO
    assert linha["whatsapp_origem"] == "link de WhatsApp no Google"


def test_link_de_whatsapp_com_phone_vazio_no_campo_site_nao_conta():
    """Armadilha 4 do spike, agora no campo site: `?phone=` vazio nao leva a
    lugar nenhum. Cai para o celular do Places, que e inferencia rotulada."""
    linha = _linha(
        _perfil_whatsapp("https://api.whatsapp.com/send?phone=", telefone="(62) 99999-8888")
    )

    assert linha["whatsapp_link"] == "https://wa.me/5562999998888"
    assert linha["whatsapp_origem"] == "telefone do Places, móvel inferido"
