import pytest

from discoveryleads.core.orcamento import Orcamento


def test_orcamento_conta_ate_o_teto():
    orcamento = Orcamento(teto=2)

    orcamento.registrar()
    orcamento.registrar()

    assert orcamento.pode_chamar() is False
    assert orcamento.usadas == 2
    assert orcamento.restantes == 0


def test_registrar_acima_do_teto_e_erro_de_programacao():
    """Quem chama pergunta `pode_chamar()` antes. Passar do teto e defeito do
    codigo, nao falha de coletor — por isso levanta em vez de virar sinal."""
    orcamento = Orcamento(teto=1)
    orcamento.registrar()

    with pytest.raises(RuntimeError):
        orcamento.registrar()


def test_teto_zero_nao_existe():
    with pytest.raises(ValueError):
        Orcamento(teto=0)
