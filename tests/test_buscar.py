"""A linha de comando de ponta a ponta, sem rede: o Places e os sites sao
injetados, e o HTML e das fixtures reais."""

import csv
import sqlite3

import pytest

from discoveryleads import __main__ as cli
from discoveryleads.buscar import executar_busca, formatar_relatorio
from discoveryleads.collectors.places_discovery import Lugar, ResultadoDaBusca
from discoveryleads.collectors.site_analise import sinais_da_resposta
from discoveryleads.collectors.site_fetcher import RespostaDoSite
from discoveryleads.core.falhas import MotivoDeFalha

from tests.conftest import carregar_fixture

PAGINAS = {
    "https://vocenosalao.my.canva.site/": "canva_salao.html",
    "https://linktr.ee/salaocompixel": "agregador_linktree_com_pixel.html",
    "https://www.espacolaser.com.br/": "proprio_bem_feito.html",
}


def _lugar(n, nome, website=None, avaliacoes=30):
    return Lugar(
        place_id=f"place-{n}",
        nome=nome,
        endereco=f"Rua {n}, Goiânia - GO",
        lat=-16.7,
        lng=-49.26,
        telefone=f"(62) 99999-{n:04d}",
        website=website,
        nota=4.7,
        avaliacoes=avaliacoes,
        status="OPERATIONAL",
        tipos=("beauty_salon",),
        nivel_preco=None,
    )


LUGARES = [
    _lugar(1, "Salão Sem Site Popular", avaliacoes=300),
    _lugar(2, "Espaço Laser", website="https://www.espacolaser.com.br/", avaliacoes=900),
    _lugar(3, "Você no Salão", website="https://vocenosalao.my.canva.site/", avaliacoes=40),
    _lugar(4, "Salão com Pixel", website="https://linktr.ee/salaocompixel", avaliacoes=5),
]


async def _descobrir_falso(nicho, cidade, raio_m, *, chave, orcamento):
    orcamento.registrar()  # centro
    orcamento.registrar()  # uma pagina
    return ResultadoDaBusca(lugares=list(LUGARES))


async def _analisar_falso(url, *, observado_em):
    resposta = RespostaDoSite(
        url_final=url,
        http_status=200,
        html=carregar_fixture(PAGINAS[url]),
        https_valido=True,
    )
    return sinais_da_resposta(url, resposta, observado_em)


async def _executar(tmp_path, descobrir_lugares=_descobrir_falso):
    return await executar_busca(
        nicho="salão de beleza",
        cidade="Goiânia",
        raio_m=5000,
        max_chamadas=10,
        saida=tmp_path / "leads.csv",
        banco=tmp_path / "var" / "leads.db",
        chave="chave-de-teste",
        descobrir_lugares=descobrir_lugares,
        analisar=_analisar_falso,
    )


def _ler_csv(caminho):
    with caminho.open(encoding="utf-8-sig", newline="") as arquivo:
        return list(csv.DictReader(arquivo, delimiter=";"))


async def test_csv_sai_ordenado_por_faixa_com_o_inelegivel_no_fim(tmp_path):
    await _executar(tmp_path)

    linhas = _ler_csv(tmp_path / "leads.csv")

    assert [(linha["nome"], linha["faixa"]) for linha in linhas] == [
        ("Salão com Pixel", "T0"),
        ("Você no Salão", "T1"),
        ("Salão Sem Site Popular", "T3"),
        ("Espaço Laser", ""),
    ]


async def test_linha_do_t0_traz_motivo_evidencia_e_rastreamento(tmp_path):
    """Pixel dentro de agregador: o caso maximo da secao 6.2, com a prova."""
    await _executar(tmp_path)

    t0 = _ler_csv(tmp_path / "leads.csv")[0]

    assert t0["elegibilidade"] == "AGREGADOR"
    assert t0["motivo"] == "elegível — o site é um agregador de links (linktr.ee/salaocompixel)"
    assert "site.plataforma=agregador · site_classifier" in t0["evidencia"]
    assert "tracking.meta_pixel=true · tracking_detector" in t0["evidencia"]
    assert t0["rastreamento"] == "meta_pixel sem evento de conversão"
    assert t0["whatsapp_origem"] == "site"


async def test_sem_site_ganha_whatsapp_inferido_do_celular(tmp_path):
    await _executar(tmp_path)

    sem_site = next(
        linha for linha in _ler_csv(tmp_path / "leads.csv") if linha["nome"] == "Salão Sem Site Popular"
    )

    assert sem_site["plataforma"] == "ausente"
    assert sem_site["rastreamento"] == "sem site"
    assert sem_site["whatsapp_link"] == "https://wa.me/5562999990001"
    assert sem_site["whatsapp_origem"] == "telefone do Places, móvel inferido"


async def test_sinais_ficam_gravados_e_rodar_de_novo_nao_duplica_lead(tmp_path):
    await _executar(tmp_path)
    await _executar(tmp_path)

    conexao = sqlite3.connect(tmp_path / "var" / "leads.db")

    assert conexao.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 4
    # append-only: a segunda busca soma observacoes, nao substitui
    assert (
        conexao.execute("SELECT COUNT(*) FROM signals WHERE tipo = 'site.plataforma'").fetchone()[0]
        == 8
    )


async def test_relatorio_conta_chamadas_e_faixas(tmp_path):
    relatorio = await _executar(tmp_path)

    assert relatorio.chamadas_usadas == 2
    assert relatorio.por_faixa == {"T0": 1, "T1": 1, "T3": 1}
    assert relatorio.inelegiveis == 1
    assert relatorio.indeterminados == 0


async def test_falha_do_google_sem_lugares_nao_grava_csv_e_mostra_a_mensagem(tmp_path):
    async def descobrir_recusado(nicho, cidade, raio_m, *, chave, orcamento):
        orcamento.registrar()
        return ResultadoDaBusca(motivo_falha=MotivoDeFalha.BLOQUEADO, detalhe="API key not valid.")

    relatorio = await _executar(tmp_path, descobrir_lugares=descobrir_recusado)

    assert relatorio.saida is None
    assert not (tmp_path / "leads.csv").exists()
    assert "API key not valid." in formatar_relatorio(relatorio)


def test_cli_exige_max_chamadas(capsys):
    with pytest.raises(SystemExit) as saida:
        cli.main(["buscar", "--nicho", "salão de beleza", "--cidade", "Goiânia"])

    assert saida.value.code == 2
    assert "--max-chamadas" in capsys.readouterr().err


def test_cli_recusa_raio_acima_do_limite_do_google(capsys):
    with pytest.raises(SystemExit):
        cli.main(
            ["buscar", "--nicho", "x", "--cidade", "Goiânia", "--raio", "60000", "--max-chamadas", "5"]
        )

    assert "50000" in capsys.readouterr().err


def test_cli_sem_chave_avisa_e_nao_chama_o_google(monkeypatch, capsys):
    monkeypatch.setattr(cli, "chave_google", lambda: None)
    chamadas = []
    monkeypatch.setattr(cli, "executar_busca", lambda **kwargs: chamadas.append(kwargs))

    codigo = cli.main(["buscar", "--nicho", "x", "--cidade", "Goiânia", "--max-chamadas", "5"])

    assert codigo == 2
    assert chamadas == []
    assert "GOOGLE_API_KEY" in capsys.readouterr().err


def test_cli_roda_de_ponta_a_ponta_e_imprime_o_relatorio(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "chave_google", lambda: "chave-de-teste")
    original = cli.executar_busca
    monkeypatch.setattr(
        cli,
        "executar_busca",
        lambda **kwargs: original(
            **kwargs, descobrir_lugares=_descobrir_falso, analisar=_analisar_falso
        ),
    )

    codigo = cli.main(
        [
            "buscar",
            "--nicho", "salão de beleza",
            "--cidade", "Goiânia",
            "--max-chamadas", "5",
            "--saida", str(tmp_path / "leads.csv"),
            "--banco", str(tmp_path / "leads.db"),
        ]
    )

    impresso = capsys.readouterr().out
    assert codigo == 0
    assert "Chamadas pagas ao Places: 2 de 5" in impresso
    assert "T0: 1" in impresso
    assert "leads.csv" in impresso
