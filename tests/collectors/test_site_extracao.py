"""Extracao dos sinais `site.*` do HTML — defeitos vendaveis e contatos.

Cada defeito aqui vira argumento de venda na frente do cliente, entao errar para
mais (dizer que tem quando nao tem) apaga um argumento legitimo, e errar para
menos inventa um defeito que nao existe. Os dois custam a mesma credibilidade.
"""

import pytest

from discoveryleads.collectors.site_extracao import extrair_sinais

from tests.conftest import carregar_fixture, carregar_manifesto


def test_title_vem_do_head_e_nao_dos_titulos_dentro_de_svg():
    """hifly.com.br derruba extracao por expressao regular de duas maneiras.

    1. O <title> do documento esta quebrado em tres linhas:

           <title>
                 HIFLY
           </title>

       Regex orientada a linha nao casa.

    2. Tendo perdido esse, a mesma regex encontra os CINCO <title> seguintes —
       todos rotulos de acessibilidade de icone <svg> de bandeira de cartao,
       cada um em linha unica — e devolve "American Express".

    O resultado certo e "HIFLY". Parser de arvore le head > title e nao ve os
    <svg>, que estao no body.
    """
    html = carregar_fixture("shopify_em_dominio_proprio.html")

    assert extrair_sinais(html).title == "HIFLY"


def test_meta_description_vazia_conta_como_ausente():
    """A pagina traz <meta name="description" content="" />.

    Conferir a existencia da tag responde "sim, tem description" enquanto o
    defeito vendavel — meta description ausente, secao 5 — esta la.
    """
    html = carregar_fixture("canva_variante_sem_app_name.html")

    assert extrair_sinais(html).meta_description is None


def test_meta_description_preenchida_e_lida():
    """Par do teste acima: um extrator que devolvesse None sempre passaria la e
    falha aqui."""
    html = carregar_fixture("agregador_linktree.html")

    assert (
        extrair_sinais(html).meta_description
        == "Um novo conceito de alta qualidade de salão de beleza em Aracaju"
    )


def test_link_curto_de_whatsapp_e_contato_mas_nao_da_telefone():
    """wa.me/message/<CODIGO> abre a conversa certa e nao carrega numero nenhum.

    E o formato das DUAS paginas de Canva do conjunto, ou seja, o caso comum
    justamente no perfil de lead que mais interessa. `site.whatsapp_link` e o
    fato — existe caminho ate o WhatsApp — e o telefone derivado dele pode nao
    existir. Sao dois sinais, nao um.
    """
    sinais = extrair_sinais(carregar_fixture("canva_salao.html"))

    assert sinais.whatsapp_link == "https://wa.me/message/VR7BW3RWVSZAE1"
    assert sinais.whatsapp_telefone is None


def test_link_de_whatsapp_com_phone_vazio_e_descartado():
    """Armadilha 4, exercitada pela fixture real.

    O PRIMEIRO link de WhatsApp do documento da Linktree e
    `https://api.whatsapp.com/send?phone=` com o valor vazio. Um extrator que
    pegue o primeiro link que encontrar grava um contato que nao leva a lugar
    nenhum, e o operador descobre isso na frente do cliente.
    """
    sinais = extrair_sinais(carregar_fixture("agregador_linktree.html"))

    assert sinais.whatsapp_link == "https://wa.me/557999015030"
    assert sinais.whatsapp_telefone == "+557999015030"


def test_telefone_do_whatsapp_sai_em_e164():
    """Forma `wa.me/+<numero>`, com o mais ja no caminho. Normalizacao da
    secao 4.2: so digitos, prefixados por `+`."""
    sinais = extrair_sinais(carregar_fixture("wordpress_com_whatsapp.html"))

    assert sinais.whatsapp_telefone == "+5511966072926"


def test_viewport_ausente_e_defeito_vendavel():
    """minhaloja.myshopify.com nao declara meta viewport: nao e responsiva no
    celular, que e onde o cliente do lead abre o link."""
    assert extrair_sinais(carregar_fixture("shopify_ativa.html")).viewport_presente is False


def test_viewport_presente_e_reconhecido():
    """Par do teste acima."""
    assert extrair_sinais(carregar_fixture("canva_salao.html")).viewport_presente is True


def test_email_e_perfil_de_instagram_saem_do_html():
    """`site.links_sociais` acha o Instagram sem gastar uma busca paga — e o que
    liga a pagina ao perfil na etapa E5, de graca."""
    sinais = extrair_sinais(carregar_fixture("proprio_bem_feito.html"))

    assert sinais.email == "imprensa@espacolaser.com.br"
    assert sinais.instagram == "espacolaser"


@pytest.mark.parametrize(
    "entrada", carregar_manifesto(), ids=lambda e: e["arquivo"].removesuffix(".html")
)
def test_extracao_bate_com_o_que_o_manifesto_afirma(entrada):
    """Impede que o manifesto e o codigo divirjam.

    O manifesto e documentacao E tabela de casos ao mesmo tempo. Documentacao que
    ninguem verifica apodrece: as duas primeiras versoes deste arquivo afirmavam
    que hifly.com.br nao tinha titulo (tinha, "HIFLY") e que a pagina 404 do
    Google nao declarava viewport (declara, com o atributo sem aspas). Os dois
    erros vieram de extracao por grep e sobreviveriam para sempre sem este teste.

    Entrada que omite um campo simplesmente nao e cobrada nele.
    """
    sinais = extrair_sinais(carregar_fixture(entrada["arquivo"]))

    if "title" in entrada:
        assert (sinais.title or "") == entrada["title"]
    if "viewport_presente" in entrada:
        assert sinais.viewport_presente is entrada["viewport_presente"]
    if "meta_description_presente" in entrada:
        assert (sinais.meta_description is not None) is entrada[
            "meta_description_presente"
        ]
    if "whatsapp_link" in entrada:
        assert (sinais.whatsapp_link or "") == entrada["whatsapp_link"]
    if "whatsapp_telefone_extraivel" in entrada:
        assert (sinais.whatsapp_telefone is not None) is entrada[
            "whatsapp_telefone_extraivel"
        ]
