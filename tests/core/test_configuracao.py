from discoveryleads.core.configuracao import chave_google, ler_env


def test_ler_env_aguenta_comentario_gravado_fora_de_utf8(tmp_path):
    """O .env real do projeto tem um travessao em cp1252 num comentario."""
    caminho = tmp_path / ".env"
    caminho.write_bytes("# Google Cloud — Places\nGOOGLE_API_KEY=abc123\n".encode("cp1252"))

    assert ler_env(caminho)["GOOGLE_API_KEY"] == "abc123"


def test_ler_env_ignora_comentario_e_linha_vazia_e_tira_aspas(tmp_path):
    caminho = tmp_path / ".env"
    caminho.write_text('# comentario\n\nAPIFY_TOKEN="xyz"\nVAZIA=\n', encoding="utf-8")

    assert ler_env(caminho) == {"APIFY_TOKEN": "xyz", "VAZIA": ""}


def test_ler_env_sem_arquivo_devolve_vazio(tmp_path):
    assert ler_env(tmp_path / "nao_existe") == {}


def test_variavel_de_ambiente_vence_o_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "da-variavel")

    assert chave_google() == "da-variavel"


def test_chave_vazia_vira_none(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(
        "discoveryleads.core.configuracao.ler_env",
        lambda caminho=None: {"GOOGLE_API_KEY": ""},
    )

    assert chave_google() is None
