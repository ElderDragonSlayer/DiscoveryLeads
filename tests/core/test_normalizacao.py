import pytest

from discoveryleads.core.normalizacao import ddd, e_movel, telefone_e164


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("(62) 99999-8888", "+5562999998888"),
        ("(62) 3333-4444", "+556233334444"),
        ("+55 62 99999-8888", "+5562999998888"),
        ("062 3333-4444", "+556233334444"),
        # DDD 55 e o Rio Grande do Sul. Tirar "55" do comeco sem olhar o
        # tamanho apaga o DDD e produz um numero de outra cidade.
        ("(55) 99999-8888", "+5555999998888"),
        ("+55 55 99999-8888", "+5555999998888"),
    ],
)
def test_telefone_vira_e164(entrada, esperado):
    assert telefone_e164(entrada) == esperado


@pytest.mark.parametrize("entrada", [None, "", "sem numero", "1234"])
def test_telefone_implausivel_vira_none(entrada):
    assert telefone_e164(entrada) is None


def test_celular_e_reconhecido_pelo_nono_digito():
    assert e_movel("+5562999998888") is True


def test_fixo_nao_e_celular():
    assert e_movel("+556233334444") is False


def test_ddd_sai_do_e164():
    assert ddd("+5562999998888") == "62"
