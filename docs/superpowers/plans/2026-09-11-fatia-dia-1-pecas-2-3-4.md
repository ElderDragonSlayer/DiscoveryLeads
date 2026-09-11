# Fatia Dia 1 — Peças 2, 3 e 4 — Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fazer `python -m discoveryleads buscar --nicho ... --cidade ... --max-chamadas N --saida leads.csv` produzir um CSV real, ordenado por faixa T0–T3, com motivo, evidência e limites em cada linha.

**Architecture:** o Places descobre os lugares (peça 2), a peça 1 já existente analisa o site de cada um, e tudo vira `Signal` (seção 4.3 da spec). Os sinais são gravados append-only num SQLite (histórico desde a primeira busca) e, em memória, alimentam elegibilidade e faixa (peça 3), que alimentam o CSV (peça 4). Uma linha de comando liga as quatro peças.

**Tech Stack:** Python 3.13, httpx, selectolax, sqlite3 (stdlib), pytest + pytest-asyncio + respx. Nenhuma dependência nova.

**Spec:** `docs/superpowers/specs/2026-09-10-fatia-dia-1.md` (plano da fatia, com a emenda da peça 4), que depende de `docs/superpowers/specs/2026-09-09-discoveryleads-backend-design.md` (seções 4, 5, 6, 8.3). Leia também `docs/superpowers/specs/2026-09-10-spike-s4-e-armadilhas.md` antes de tocar no classificador.

## Global Constraints

- Python `>=3.13`, ambiente em `.venv/`. Não há `python` no PATH: rode sempre `.venv/Scripts/python.exe -m pytest tests/ -q`.
- Português no código, nos commits e nas mensagens ao operador.
- **Coletor nunca propaga exceção.** Falha vira sinal `collector.<nome>.failed` com motivo do enum, nunca string livre: `timeout` · `bloqueado` · `nao_encontrado` · `parse_falhou` · `cota_estourada` · `rede_indisponivel` · `resposta_invalida` · `dominio_nao_resolve`.
- **`signals` é append-only.** Nunca UPDATE, nunca DELETE.
- **Nenhum argumento de venda sem sinal que o sustente.** Todo motivo de elegibilidade traz a evidência: `tipo=valor · coletor · AAAA-MM-DD HH:MM`.
- **Toda chamada paga tem teto.** `--max-chamadas` é obrigatório; cada requisição ao Places conta uma chamada, inclusive as que falham.
- Pesos, limiares e listas ficam em `config/*.toml`, fora do código.
- Testes não tocam a rede. Teste com rede leva `@pytest.mark.live` e só roda com `-m live`.
- Segredos só em `.env`. **Nunca imprimir, logar nem commitar a chave.**
- CSV: separador `;`, **UTF-8 com BOM** (`utf-8-sig`), uma linha por lead.
- As seis armadilhas do spike S4 continuam valendo. Nenhum teste existente pode ser afrouxado.

## Decisões que este plano implementa

Do Saulo, em 2026-09-11:

1. **Construtor com site de pé** (Wix, Shopify, Loja Integrada, WordPress): elegível só em **subdomínio grátis** — categoria nova `SUBDOMINIO_GRATIS`, faixa T1. Com domínio próprio é `TEM_SITE_PROPRIO`. Subdomínios aceitos, todos confirmados em fixture real: `wixsite.com`, `myshopify.com`, `lojaintegrada.com.br`. A checagem usa o domínio **final** (depois dos redirects), porque é onde o cliente do lead cai.
2. **`SITE_QUEBRADO` vai para T1.** A seção 6.2 não o punha em faixa nenhuma.

Tomadas neste plano, pela leitura literal da seção 6 ou pelos princípios já escritos:

3. **Bloqueio não é quebra.** 401, 403 e 429 são o servidor recusando o coletor. Sem domínio ou assinatura que diga a plataforma, o resultado é "não sei" (`None`), e a elegibilidade é `INDETERMINADO`. Quebra é: domínio que não resolve, certificado inválido, 402, 404, 410 e 5xx.
4. **Status de erro só torna elegível, nunca inelegível.** Site de construtor que responde 402/404/5xx vira `SITE_QUEBRADO`. Canva, agregador e Google Sites com erro continuam na própria categoria (todos T1).
5. **`INDETERMINADO`** é categoria nova: o site não pôde ser lido e o domínio não diz o que é. Fica depois dos elegíveis e antes dos inelegíveis no CSV, porque vale conferir à mão. É o "elegibilidade pendente" que o plano da fatia já pede para a E7.
6. **T2 fica vazia nesta fatia.** A seção 6.2 exige intenção comercial (bio do Instagram ou WhatsApp no site), e quem não tem site não tem nenhum dos dois enquanto o Instagram não entra (E5). O código implementa a regra literal, e todo `SEM_SITE` cai em T3. Na ordem do CSV isso quase não muda nada: dentro de T3 quem tem mais avaliações vem primeiro.
7. **Ordem dentro da faixa, provisória:** mais avaliações primeiro. O `valor` da seção 6.3 não existe nesta fatia.
8. **Inelegíveis ficam no CSV**, no fim, com o motivo. A etapa E4 precisa enxergar falso negativo.
9. **T0 exige rastreamento pago:** `meta_pixel`, `google_ads` ou `tiktok_pixel`. GA, GTM e heatmap medem, não provam verba.
10. **Field mask ganha `places.id`.** A lista da fatia não o incluía, e sem ele não há dedupe por `place_id`. É da faixa mais barata (Essentials IDs Only); a chamada já é cobrada como Enterprise por causa de telefone, site e avaliações.
11. **Centro da busca por uma chamada extra** à própria Text Search (`textQuery` = cidade, `pageSize` 1, campo `places.location`). Conta no `--max-chamadas`. Sem centro não existe `locationBias` com raio.
12. **Sinal novo `site.url_final`** (aditivo, seção 3: "fonte nova é aditiva"). É o domínio onde o cliente cai, e é o que decide `SUBDOMINIO_GRATIS`.
13. **`REDE_FRANQUIA`**: mesmo telefone E.164 ou mesmo nome normalizado em pelo menos 3 `place_id` da busca (`config/scoring.toml`).
14. **SQLite desde a primeira busca**, com o `schema.sql` que a fatia já previa no lugar do Alembic. O motivo é o histórico: "trocou Linktree por Canva há 12 dias" só existe se o sinal de hoje foi gravado hoje. O CSV sai dos sinais **desta** execução, não da view, para não misturar observação velha com nova.

## Mapa de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `src/discoveryleads/collectors/site_fetcher.py` | *modificar*: `https_valido` e detecção de certificado inválido |
| `src/discoveryleads/collectors/site_classifier.py` | *modificar*: bloqueio ≠ quebra; `classificar_resposta` |
| `src/discoveryleads/core/sinais.py` | *criar*: `Signal`, `agora_iso` |
| `src/discoveryleads/collectors/site_analise.py` | *criar*: resposta do site → lista de `Signal` |
| `src/discoveryleads/core/normalizacao.py` | *modificar*: telefone E.164, `e_movel`, `ddd` |
| `src/discoveryleads/core/configuracao.py` | *modificar*: leitura do `.env` e `chave_google()` |
| `src/discoveryleads/core/orcamento.py` | *criar*: teto de chamadas |
| `src/discoveryleads/collectors/places_discovery.py` | *criar*: Text Search paginada, `Lugar`, sinais `places.*` |
| `src/discoveryleads/db/schema.sql`, `db/repositorio.py` | *criar*: leads, identidades, signals append-only |
| `config/scoring.toml`, `config/nichos.toml` | *criar*: limiares, listas, tipos excluídos |
| `src/discoveryleads/scoring/elegibilidade.py` | *criar*: categorias, motivo, evidência, franquias |
| `src/discoveryleads/scoring/faixas.py` | *criar*: T0–T3 e ordenação |
| `src/discoveryleads/export/csv_leads.py` | *criar*: linha do CSV e escrita |
| `src/discoveryleads/buscar.py`, `src/discoveryleads/__main__.py` | *criar*: orquestração e linha de comando |

Pacotes novos precisam de `__init__.py` vazio: `src/discoveryleads/{scoring,db,export}/` e `tests/{core,scoring,db,export}/`.

---

### Task 1: HTTPS válido e certificado inválido no fetcher

A seção 6.1 põe "certificado inválido" em `SITE_QUEBRADO`, e a peça 1 ainda não detecta isso. Medido em 2026-09-11 contra `https://expired.badssl.com/`: a cadeia real é `httpx.ConnectError` ← `httpcore.ConnectError` ← `ssl.SSLCertVerificationError`, e toda mensagem contém `[SSL: CERTIFICATE_VERIFY_FAILED]`. Sob respx a cadeia se perde (o `__cause__` vira `SideEffectError`), então a detecção olha **o tipo na cadeia e também a mensagem**.

**Files:**
- Modify: `src/discoveryleads/collectors/site_fetcher.py`
- Test: `tests/collectors/test_site_fetcher.py`

**Interfaces:**
- Produces: `RespostaDoSite.https_valido: bool | None` (None = não chegou a negociar TLS); `certificado_invalido(erro: BaseException) -> bool`.

- [ ] **Step 1: Escrever os testes que falham** — acrescentar ao fim de `tests/collectors/test_site_fetcher.py` (e `import ssl` no topo; `certificado_invalido` no import de `site_fetcher`):

```python
def test_certificado_invalido_reconhece_a_causa_real_do_ssl():
    """Formato medido em expired.badssl.com: ConnectError <- ConnectError <-
    ssl.SSLCertVerificationError."""
    raiz = ssl.SSLCertVerificationError("certificate verify failed: certificate has expired")
    meio = httpx.ConnectError("falhou")
    meio.__cause__ = raiz
    topo = httpx.ConnectError("falhou")
    topo.__cause__ = meio

    assert certificado_invalido(topo) is True


def test_certificado_invalido_reconhece_pela_mensagem_do_openssl():
    """Sob respx a cadeia de causas se perde; a mensagem do OpenSSL fica."""
    erro = httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

    assert certificado_invalido(erro) is True


def test_erro_de_conexao_comum_nao_e_certificado():
    assert certificado_invalido(httpx.ConnectError("connection refused")) is False


@respx.mock
async def test_certificado_invalido_vira_https_invalido_sem_status():
    respx.get("https://vencido.com.br/").mock(
        side_effect=httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    )

    resultado = await buscar_site("https://vencido.com.br/", resolve_dns=_dns_que_resolve)

    assert resultado.https_valido is False
    assert resultado.http_status is None
    assert resultado.motivo_falha is MotivoDeFalha.RESPOSTA_INVALIDA


@respx.mock
async def test_site_que_responde_em_https_tem_https_valido():
    respx.get("https://salao.com.br/").mock(return_value=httpx.Response(200, html="<html></html>"))

    resultado = await buscar_site("https://salao.com.br/", resolve_dns=_dns_que_resolve)

    assert resultado.https_valido is True


@respx.mock
async def test_site_so_em_http_nao_tem_https_valido():
    """Sem HTTPS o navegador mostra "Não seguro": defeito vendável, não quebra."""
    respx.get("http://salao.com.br/").mock(return_value=httpx.Response(200, html="<html></html>"))

    resultado = await buscar_site("http://salao.com.br/", resolve_dns=_dns_que_resolve)

    assert resultado.https_valido is False
    assert resultado.motivo_falha is None


@pytest.mark.live
async def test_live_certificado_vencido_de_verdade():
    """Canário da cadeia real de exceções do httpx. Roda com -m live."""
    resultado = await buscar_site("https://expired.badssl.com/")

    assert resultado.https_valido is False
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest tests/collectors/test_site_fetcher.py -q`
Expected: erro de coleta — `ImportError: cannot import name 'certificado_invalido'`.

- [ ] **Step 3: Implementar** — em `src/discoveryleads/collectors/site_fetcher.py`:

Acrescentar `import ssl` junto dos imports. Em `RespostaDoSite`, acrescentar o campo **antes** de `motivo_falha`:

```python
    https_valido: bool | None = None
```

Acrescentar a função, logo depois de `_motivo_da_excecao`:

```python
def certificado_invalido(erro: BaseException) -> bool:
    """Procura falha de verificacao de certificado na cadeia de excecoes.

    Duas pistas, porque cada uma some num contexto diferente: o tipo
    `ssl.SSLCertVerificationError` aparece na cadeia real do httpx, e a mensagem
    do OpenSSL `CERTIFICATE_VERIFY_FAILED` sobrevive quando a cadeia se perde.
    """
    vistos: set[int] = set()
    atual: BaseException | None = erro
    while atual is not None and id(atual) not in vistos:
        if isinstance(atual, ssl.SSLCertVerificationError):
            return True
        if "CERTIFICATE_VERIFY_FAILED" in str(atual):
            return True
        vistos.add(id(atual))
        atual = atual.__cause__ or atual.__context__
    return False
```

Trocar o bloco `except` de `buscar_site` por:

```python
    except Exception as erro:  # principio 1: nada escapa daqui
        tempo = int((time.monotonic() - comeco) * 1000)
        if certificado_invalido(erro):
            return RespostaDoSite(
                tempo_resposta_ms=tempo,
                https_valido=False,
                motivo_falha=MotivoDeFalha.RESPOSTA_INVALIDA,
            )
        return RespostaDoSite(tempo_resposta_ms=tempo, motivo_falha=_motivo_da_excecao(erro))
```

E, no `return` de sucesso, acrescentar:

```python
        https_valido=str(resposta.url).startswith("https://"),
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: todos passam (78 anteriores + 6 novos; o live fica de fora).

- [ ] **Step 5: Canário ao vivo (opcional, toca a rede)**

Run: `.venv/Scripts/python.exe -m pytest tests/collectors/test_site_fetcher.py -m live -q`
Expected: `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add src/discoveryleads/collectors/site_fetcher.py tests/collectors/test_site_fetcher.py
git commit -m "Fetcher detecta HTTPS valido e certificado invalido"
```

### Task 2: Bloqueio não é quebra, e classificação a partir da resposta do fetcher

Hoje `classificar_plataforma` devolve `QUEBRADO` para um site próprio atrás de anti-bot (403 sem assinatura) — o oposto da armadilha 7 do spike, e um falso positivo que manda ligar para quem tem site funcionando. E ninguém classifica o caso em que o fetcher nem recebeu resposta (DNS, certificado, timeout).

**Files:**
- Modify: `src/discoveryleads/collectors/site_classifier.py`
- Test: `tests/collectors/test_site_classifier.py`

**Interfaces:**
- Consumes: `RespostaDoSite` (com `https_valido`, Task 1).
- Produces: `classificar_plataforma(url, html, http_status=200) -> Plataforma | None`; `plataforma_pelo_dominio(url) -> Plataforma | None`; `plataforma_pela_assinatura(html) -> Plataforma | None`; `classificar_resposta(url: str, resposta: RespostaDoSite) -> Plataforma | None`; `STATUS_DE_BLOQUEIO = frozenset({401, 403, 429})`.

- [ ] **Step 1: Teste do bloqueio** — acrescentar a `tests/collectors/test_site_classifier.py`:

```python
def test_bloqueio_sem_pista_de_plataforma_nao_e_quebrado():
    """O corpo da fixture da Beacons e o desafio do Cloudflare. Num dominio que
    nao diz nada, a resposta honesta e "nao sei". `quebrado` mandaria o
    operador ligar para quem tem site funcionando."""
    html = carregar_fixture("agregador_beacons_bloqueado_403.html")

    assert classificar_plataforma("https://salaodaana.com.br/", html, http_status=403) is None
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest tests/collectors/test_site_classifier.py -q`
Expected: FAIL — `assert <Plataforma.QUEBRADO: 'quebrado'> is None`.

- [ ] **Step 3: Implementar o bloqueio** — substituir o corpo de `site_classifier.py` a partir de `def _tabela` por:

```python
# O servidor recusando o coletor, nao o site fora do ar (armadilha 7 do spike).
STATUS_DE_BLOQUEIO = frozenset({401, 403, 429})


def _tabela() -> dict[Plataforma, dict]:
    """As regras de `platforms.toml`, na ordem em que estao escritas."""
    return {
        Plataforma(nome): regra for nome, regra in carregar("platforms.toml").items()
    }


def plataforma_pelo_dominio(url: str) -> Plataforma | None:
    dominio = dominio_de(url)
    for plataforma, regra in _tabela().items():
        if any(dominio_casa(dominio, d) for d in regra["dominios"]):
            return plataforma
    return None


def plataforma_pela_assinatura(html: str) -> Plataforma | None:
    for plataforma, regra in _tabela().items():
        if any(assinatura in html for assinatura in regra["assinaturas"]):
            return plataforma
    return None


def classificar_plataforma(
    url: str, html: str, http_status: int = 200
) -> Plataforma | None:
    """Devolve `site.plataforma` para uma pagina ja baixada, ou None se nao da
    para saber.

    A ordem das regras e o que decide a faixa do lead:

    1. **Dominio antes de assinatura.**
    2. **Assinatura antes de status.** E o que faz um `*.business.site`
       continuar GOOGLE_SITES_EXTINTO depois de um 404, e uma loja atras de
       anti-bot continuar `loja_integrada` depois de um 403.
    3. **Bloqueio nao e quebra.** 401, 403 e 429 sem dominio nem assinatura
       devolvem None.
    4. **Status por ultimo**, quando nao sobrou mais nada para dizer o que era.
    """
    encontrada = plataforma_pelo_dominio(url) or plataforma_pela_assinatura(html)
    if encontrada is not None:
        return encontrada
    if http_status in STATUS_DE_BLOQUEIO:
        return None
    if http_status >= 400:
        return Plataforma.QUEBRADO
    return Plataforma.PROPRIO
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: todos passam. O teste do manifesto continua verde: as três fixtures com 403/404 são reconhecidas pelo domínio antes do status.

- [ ] **Step 5: Testes de `classificar_resposta`** — no topo do arquivo de teste, trocar o import do classificador e acrescentar:

```python
from discoveryleads.collectors.site_classifier import (
    classificar_plataforma,
    classificar_resposta,
)
from discoveryleads.collectors.site_fetcher import RespostaDoSite
from discoveryleads.core.falhas import MotivoDeFalha
```

E, no fim do arquivo:

```python
def test_redirect_para_agregador_e_classificado_pelo_destino():
    """Dominio proprio que redireciona para a Linktree: comum, e e agregador."""
    resposta = RespostaDoSite(
        url_final="https://linktr.ee/FascinoBeleza",
        http_status=200,
        html=carregar_fixture("agregador_linktree.html"),
        https_valido=True,
    )

    assert classificar_resposta("https://salaodaana.com.br/", resposta) is Plataforma.AGREGADOR


def test_dominio_de_origem_de_google_sites_vence_o_redirect():
    """S4: o apex negocio.site redireciona para o perfil do Google, que responde
    200 sem assinatura nenhuma. So o dominio de ORIGEM diz o que era."""
    resposta = RespostaDoSite(
        url_final="https://business.google.com/br/business-profile/",
        http_status=200,
        html="<html>perfil</html>",
        https_valido=True,
    )

    assert (
        classificar_resposta("https://negocio.site/", resposta)
        is Plataforma.GOOGLE_SITES_EXTINTO
    )


def test_dominio_que_nao_resolve_e_quebrado():
    resposta = RespostaDoSite(motivo_falha=MotivoDeFalha.DOMINIO_NAO_RESOLVE)

    assert classificar_resposta("https://salao-que-fechou.com.br/", resposta) is Plataforma.QUEBRADO


def test_certificado_invalido_e_quebrado():
    """Secao 6.1: certificado invalido e SITE_QUEBRADO."""
    resposta = RespostaDoSite(https_valido=False, motivo_falha=MotivoDeFalha.RESPOSTA_INVALIDA)

    assert classificar_resposta("https://vencido.com.br/", resposta) is Plataforma.QUEBRADO


def test_timeout_sem_pista_de_dominio_e_desconhecido():
    """Timeout e falha do coletor, nao prova de que o site caiu."""
    resposta = RespostaDoSite(motivo_falha=MotivoDeFalha.TIMEOUT)

    assert classificar_resposta("https://salaodaana.com.br/", resposta) is None


def test_timeout_em_dominio_de_canva_continua_canva():
    resposta = RespostaDoSite(motivo_falha=MotivoDeFalha.TIMEOUT)

    assert classificar_resposta("https://anastudio.my.canva.site/", resposta) is Plataforma.CANVA
```

- [ ] **Step 6: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest tests/collectors/test_site_classifier.py -q`
Expected: erro de coleta — `ImportError: cannot import name 'classificar_resposta'`.

- [ ] **Step 7: Implementar `classificar_resposta`** — em `site_classifier.py`, acrescentar aos imports:

```python
from discoveryleads.collectors.site_fetcher import RespostaDoSite
from discoveryleads.core.falhas import MotivoDeFalha
```

E, no fim do arquivo:

```python
def classificar_resposta(url: str, resposta: RespostaDoSite) -> Plataforma | None:
    """`site.plataforma` a partir do que o fetcher trouxe — inclusive quando nao
    trouxe resposta nenhuma.

    O dominio de ORIGEM vem antes do de destino: `negocio.site` redireciona para
    o perfil do Google, e so a origem diz que era Google Sites (spike S4).
    """
    por_dominio = plataforma_pelo_dominio(url)
    if por_dominio is None and resposta.url_final:
        por_dominio = plataforma_pelo_dominio(resposta.url_final)
    if por_dominio is not None:
        return por_dominio

    if resposta.http_status is not None:
        return classificar_plataforma(
            resposta.url_final or url, resposta.html, resposta.http_status
        )

    # Sem resposta HTTP. So duas falhas provam que o site esta fora do ar para o
    # cliente do lead; timeout e rede sao problema do coletor.
    if resposta.motivo_falha is MotivoDeFalha.DOMINIO_NAO_RESOLVE:
        return Plataforma.QUEBRADO
    if resposta.https_valido is False:
        return Plataforma.QUEBRADO
    return None
```

- [ ] **Step 8: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: todos passam.

- [ ] **Step 9: Commit**

```bash
git add src/discoveryleads/collectors/site_classifier.py tests/collectors/test_site_classifier.py
git commit -m "Classificador: bloqueio nao e quebra; classifica a partir da resposta do fetcher"
```

### Task 3: `Signal` e a análise do site como lista de sinais

A coluna `evidencia` do CSV exige coletor e momento em cada fato, e os módulos da peça 1 devolvem dataclasses sem isso. Esta task cria o `Signal` da seção 4.3 e o módulo que transforma a resposta do site em sinais.

**Files:**
- Create: `src/discoveryleads/core/sinais.py`, `src/discoveryleads/collectors/site_analise.py`, `tests/core/__init__.py`, `tests/core/test_sinais.py`, `tests/collectors/test_site_analise.py`

**Interfaces:**
- Consumes: `classificar_resposta` (Task 2), `extrair_sinais`, `detectar_rastreamento`, `buscar_site`, `RespostaDoSite`.
- Produces:
  - `Signal(tipo: str, valor: object, fonte: str, coletor: str, versao: int, observado_em: str, confianca: float = 1.0)` com `valor_json() -> str`; `agora_iso() -> str`.
  - `sinais_da_resposta(url: str, resposta: RespostaDoSite, observado_em: str) -> list[Signal]`
  - `async analisar_site(url: str, *, observado_em: str, buscar=buscar_site) -> list[Signal]`
  - Tipos emitidos: `collector.site_fetcher.failed` (sempre; valor = motivo ou `None`), `site.plataforma`, `site.url_final`, `site.https_valido`, `site.http_status`, `site.redirects`, `site.tempo_resposta_ms`; e, só com página lida (status 200–399): `site.title`, `site.meta_description`, `site.viewport_presente`, `site.whatsapp_link`, `site.email`, `site.links_sociais`, `tracking.<nome>` para os seis nomes de `SINAIS_DE_RASTREAMENTO`, `tracking.eventos_conversao`. Falha de parse: `collector.site_classifier.failed = "parse_falhou"`.

- [ ] **Step 1: Testes do `Signal`** — criar `tests/core/__init__.py` vazio e `tests/core/test_sinais.py`:

```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest tests/core/test_sinais.py -q`
Expected: `ModuleNotFoundError: No module named 'discoveryleads.core.sinais'`.

- [ ] **Step 3: Implementar** — criar `src/discoveryleads/core/sinais.py`:

```python
"""O sinal: a unidade de verdade do sistema (secao 4.3 da spec).

Tudo que a ferramenta sabe sobre um lead e uma lista de sinais, cada um com
origem, coletor e momento. Daqui saem a evidencia do CSV, o historico e a
rastreabilidade de origem que a LGPD pede.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Signal:
    tipo: str          # namespace fonte.nome, secao 5
    valor: object      # qualquer coisa que vire JSON
    fonte: str         # places | site
    coletor: str
    versao: int
    observado_em: str  # ISO 8601 em UTC
    confianca: float = 1.0

    def valor_json(self) -> str:
        return json.dumps(self.valor, ensure_ascii=False)


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest tests/core/test_sinais.py -q`
Expected: `2 passed`.

- [ ] **Step 5: Testes da análise** — criar `tests/collectors/test_site_analise.py`:

```python
"""A resposta do site vira sinais. Nenhum teste toca a rede: o buscador e
injetado e o HTML e das fixtures reais."""

from discoveryleads.collectors.site_analise import analisar_site
from discoveryleads.collectors.site_fetcher import RespostaDoSite
from discoveryleads.core.falhas import MotivoDeFalha

from tests.conftest import carregar_fixture

MOMENTO = "2026-09-11T14:02:00+00:00"


def _buscador(resposta):
    async def buscar(url):
        return resposta

    return buscar


async def _analisar(url, resposta):
    sinais = await analisar_site(url, observado_em=MOMENTO, buscar=_buscador(resposta))
    return {sinal.tipo: sinal for sinal in sinais}


async def test_canva_real_vira_sinais_com_coletor_e_momento():
    resposta = RespostaDoSite(
        url_final="https://vocenosalao.my.canva.site/",
        http_status=200,
        html=carregar_fixture("canva_salao.html"),
        https_valido=True,
    )

    sinais = await _analisar("https://vocenosalao.my.canva.site/", resposta)

    assert sinais["site.plataforma"].valor == "canva"
    assert sinais["site.plataforma"].coletor == "site_classifier"
    assert sinais["site.plataforma"].observado_em == MOMENTO
    assert sinais["site.whatsapp_link"].valor == "https://wa.me/message/VR7BW3RWVSZAE1"
    assert sinais["collector.site_fetcher.failed"].valor is None


async def test_ausencia_observada_vira_sinal_explicito():
    """Site sem WhatsApp grava `site.whatsapp_link = null`. Sem isso, a visao de
    sinais atuais continuaria mostrando o link de uma coleta antiga."""
    resposta = RespostaDoSite(
        url_final="https://vwcabeloeestetica.wixsite.com/barber",
        http_status=200,
        html=carregar_fixture("wix_wixsite.html"),
        https_valido=True,
    )

    sinais = await _analisar("https://vwcabeloeestetica.wixsite.com/barber", resposta)

    assert sinais["site.whatsapp_link"].valor is None
    assert sinais["tracking.meta_pixel"].valor is False


async def test_pixel_do_lojista_vira_sinal_de_rastreamento():
    resposta = RespostaDoSite(
        url_final="https://wernercoiffeur.com.br/",
        http_status=200,
        html=carregar_fixture("wordpress_com_pixel_gtm.html"),
        https_valido=True,
    )

    sinais = await _analisar("https://www.wernercoiffeur.com.br/", resposta)

    assert sinais["tracking.meta_pixel"].valor is True
    assert sinais["tracking.meta_pixel"].coletor == "tracking_detector"
    assert sinais["tracking.gtm"].valor is True
    assert sinais["tracking.eventos_conversao"].valor == []


async def test_bloqueio_grava_falha_e_nao_le_a_pagina():
    """O desafio do Cloudflare nao e a pagina do lead: nem contato nem
    rastreamento saem dele. A plataforma pelo dominio fica."""
    resposta = RespostaDoSite(
        url_final="https://beacons.ai/fornecedoresbrasil2025",
        http_status=403,
        html=carregar_fixture("agregador_beacons_bloqueado_403.html"),
        https_valido=True,
        motivo_falha=MotivoDeFalha.BLOQUEADO,
    )

    sinais = await _analisar("https://beacons.ai/fornecedoresbrasil2025", resposta)

    assert sinais["site.plataforma"].valor == "agregador"
    assert sinais["collector.site_fetcher.failed"].valor == "bloqueado"
    assert "site.whatsapp_link" not in sinais
    assert not any(tipo.startswith("tracking.") for tipo in sinais)


async def test_buscador_que_explode_nao_derruba_a_analise():
    async def buscar(url):
        raise RuntimeError("falha inesperada")

    sinais = {
        sinal.tipo: sinal
        for sinal in await analisar_site(
            "https://salaodaana.com.br/", observado_em=MOMENTO, buscar=buscar
        )
    }

    assert sinais["collector.site_fetcher.failed"].valor == "resposta_invalida"
    assert "site.plataforma" not in sinais
```

- [ ] **Step 6: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest tests/collectors/test_site_analise.py -q`
Expected: `ModuleNotFoundError: No module named 'discoveryleads.collectors.site_analise'`.

- [ ] **Step 7: Implementar** — criar `src/discoveryleads/collectors/site_analise.py`:

```python
"""Analise completa do site de um lead: busca, classifica, extrai, rastreia.

Devolve sinais e nunca levanta excecao (principio 1). E a costura da peca 1 com
o resto do sistema: os modulos dela devolvem dataclasses, e daqui para frente
tudo e `Signal`.

Ausencia observada tambem vira sinal (valor None ou False): a visao de sinais
atuais pega a ultima observacao de cada tipo, e sem o "nao tem" explicito ela
continuaria mostrando o que uma coleta antiga viu.
"""

from collections.abc import Awaitable, Callable

from discoveryleads.collectors.site_classifier import classificar_resposta
from discoveryleads.collectors.site_extracao import extrair_sinais
from discoveryleads.collectors.site_fetcher import RespostaDoSite, buscar_site
from discoveryleads.collectors.tracking_detector import detectar_rastreamento
from discoveryleads.core.falhas import MotivoDeFalha
from discoveryleads.core.sinais import Signal

VERSAO = 1

SINAIS_DE_RASTREAMENTO = (
    "meta_pixel",
    "google_ads",
    "google_analytics",
    "gtm",
    "tiktok_pixel",
    "heatmap",
)


def _pagina_lida(resposta: RespostaDoSite) -> bool:
    """So a pagina que respondeu de verdade vale para contato e rastreamento.
    Desafio de anti-bot e pagina de erro nao sao a pagina do lead."""
    return resposta.http_status is not None and 200 <= resposta.http_status < 400


def sinais_da_resposta(
    url: str, resposta: RespostaDoSite, observado_em: str
) -> list[Signal]:
    def sinal(tipo: str, valor: object, coletor: str) -> Signal:
        return Signal(
            tipo=tipo,
            valor=valor,
            fonte="site",
            coletor=coletor,
            versao=VERSAO,
            observado_em=observado_em,
        )

    motivo = resposta.motivo_falha.value if resposta.motivo_falha else None
    sinais = [sinal("collector.site_fetcher.failed", motivo, "site_fetcher")]

    plataforma = classificar_resposta(url, resposta)
    if plataforma is not None:
        sinais.append(sinal("site.plataforma", plataforma.value, "site_classifier"))
    if resposta.url_final is not None:
        sinais.append(sinal("site.url_final", resposta.url_final, "site_fetcher"))
    if resposta.https_valido is not None:
        sinais.append(sinal("site.https_valido", resposta.https_valido, "site_fetcher"))
    if resposta.http_status is not None:
        sinais += [
            sinal("site.http_status", resposta.http_status, "site_fetcher"),
            sinal("site.redirects", resposta.redirects, "site_fetcher"),
            sinal("site.tempo_resposta_ms", resposta.tempo_resposta_ms, "site_fetcher"),
        ]

    if not _pagina_lida(resposta):
        return sinais

    try:
        extraidos = extrair_sinais(resposta.html)
        rastro = detectar_rastreamento(resposta.html)
    except Exception:  # principio 1
        sinais.append(
            sinal(
                "collector.site_classifier.failed",
                MotivoDeFalha.PARSE_FALHOU.value,
                "site_classifier",
            )
        )
        return sinais

    sociais = {"instagram": extraidos.instagram} if extraidos.instagram else {}
    sinais += [
        sinal("site.title", extraidos.title, "site_classifier"),
        sinal("site.meta_description", extraidos.meta_description, "site_classifier"),
        sinal("site.viewport_presente", extraidos.viewport_presente, "site_classifier"),
        sinal("site.whatsapp_link", extraidos.whatsapp_link, "site_classifier"),
        sinal("site.email", extraidos.email, "site_classifier"),
        sinal("site.links_sociais", sociais, "site_classifier"),
    ]
    sinais += [
        sinal(f"tracking.{nome}", getattr(rastro, nome), "tracking_detector")
        for nome in SINAIS_DE_RASTREAMENTO
    ]
    sinais.append(
        sinal("tracking.eventos_conversao", list(rastro.eventos_conversao), "tracking_detector")
    )
    return sinais


async def analisar_site(
    url: str,
    *,
    observado_em: str,
    buscar: Callable[[str], Awaitable[RespostaDoSite]] = buscar_site,
) -> list[Signal]:
    try:
        resposta = await buscar(url)
    except Exception:  # buscar_site nao levanta; um buscador injetado pode
        resposta = RespostaDoSite(motivo_falha=MotivoDeFalha.RESPOSTA_INVALIDA)
    return sinais_da_resposta(url, resposta, observado_em)
```

- [ ] **Step 8: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: todos passam.

- [ ] **Step 9: Commit**

```bash
git add src/discoveryleads/core/sinais.py src/discoveryleads/collectors/site_analise.py tests/core tests/collectors/test_site_analise.py
git commit -m "Signal da secao 4.3 e analise do site como lista de sinais"
```

### Task 4: Telefone brasileiro — E.164, celular e DDD

A seção 4.2 manda normalizar telefone para E.164 antes de usar como identidade, e a seção 5 deriva `telefone.e_movel` e `telefone.ddd`. Franquia (Task 7) e o link de WhatsApp montado (Task 9) dependem disso.

**Files:**
- Modify: `src/discoveryleads/core/normalizacao.py`
- Test: `tests/core/test_normalizacao.py`

**Interfaces:**
- Produces: `telefone_e164(telefone: str | None) -> str | None`; `e_movel(e164: str) -> bool`; `ddd(e164: str) -> str`.

- [ ] **Step 1: Escrever os testes** — criar `tests/core/test_normalizacao.py`:

```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest tests/core/test_normalizacao.py -q`
Expected: `ImportError: cannot import name 'ddd'`.

- [ ] **Step 3: Implementar** — em `src/discoveryleads/core/normalizacao.py`, acrescentar `import re` aos imports e, no fim do arquivo:

```python
CODIGO_DO_BRASIL = "55"
_SO_DIGITOS = re.compile(r"\D")


def telefone_e164(telefone: str | None) -> str | None:
    """Telefone brasileiro em E.164: so digitos, prefixados por +55.

    "(62) 99999-8888" -> "+5562999998888". Devolve None quando nao sobra um
    numero nacional plausivel (DDD + 8 ou 9 digitos).

    O "55" do comeco so e codigo do pais quando o numero tem 12 ou 13 digitos.
    Com 10 ou 11, e o DDD do Rio Grande do Sul.
    """
    if not telefone:
        return None
    digitos = _SO_DIGITOS.sub("", telefone)
    if digitos.startswith(CODIGO_DO_BRASIL) and len(digitos) in (12, 13):
        digitos = digitos[len(CODIGO_DO_BRASIL):]
    elif digitos.startswith("0"):
        digitos = digitos[1:]  # zero de discagem interurbana: "062 ..."
    if len(digitos) not in (10, 11):
        return None
    return f"+{CODIGO_DO_BRASIL}{digitos}"


def e_movel(e164: str) -> bool:
    """Inferencia pelo nono digito: celular tem 11 digitos nacionais e comeca
    com 9 depois do DDD.

    Diz se o numero e de celular. NAO diz se tem WhatsApp — isso nao ha como
    verificar de forma limpa, e a secao 5 manda rotular como inferencia.
    """
    nacional = e164.removeprefix(f"+{CODIGO_DO_BRASIL}")
    return len(nacional) == 11 and nacional[2] == "9"


def ddd(e164: str) -> str:
    return e164.removeprefix(f"+{CODIGO_DO_BRASIL}")[:2]
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add src/discoveryleads/core/normalizacao.py tests/core/test_normalizacao.py
git commit -m "Normalizacao de telefone brasileiro: E.164, celular e DDD"
```

### Task 5: Chave do `.env` e teto de chamadas

Duas coisas que a peça 2 precisa antes da primeira requisição paga: ler a chave sem derrubar o programa, e contar chamadas com teto (princípio 4).

O `.env` real deste projeto tem um travessão gravado fora de UTF-8 num comentário (linha 3). Leitura estrita levanta `UnicodeDecodeError` antes da primeira chamada — por isso a leitura é tolerante, e há teste para isso.

**Files:**
- Modify: `src/discoveryleads/core/configuracao.py`
- Create: `src/discoveryleads/core/orcamento.py`, `tests/core/test_configuracao.py`, `tests/core/test_orcamento.py`

**Interfaces:**
- Produces: `ler_env(caminho: Path | None = None) -> dict[str, str]`; `chave_google() -> str | None`; `Orcamento(teto: int)` com `usadas: int`, `restantes: int`, `pode_chamar() -> bool`, `registrar() -> None`.

- [ ] **Step 1: Testes da configuração** — criar `tests/core/test_configuracao.py`:

```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest tests/core/test_configuracao.py -q`
Expected: `ImportError: cannot import name 'chave_google'`.

- [ ] **Step 3: Implementar** — em `src/discoveryleads/core/configuracao.py`, acrescentar `import os` aos imports e, no fim:

```python
def ler_env(caminho: Path | None = None) -> dict[str, str]:
    """Le pares NOME=valor do .env da raiz do projeto.

    Linha vazia e comentario (#) sao ignorados; aspas em volta do valor saem.
    Decodifica UTF-8 tolerante: o .env real tem um travessao gravado fora de
    UTF-8 num comentario, e leitura estrita derrubaria a busca antes da primeira
    chamada.
    """
    caminho = caminho or RAIZ_DO_PROJETO / ".env"
    if not caminho.exists():
        return {}
    valores: dict[str, str] = {}
    for linha in caminho.read_bytes().decode("utf-8", errors="replace").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, _, valor = linha.partition("=")
        valores[nome.strip()] = valor.strip().strip('"').strip("'")
    return valores


def chave_google() -> str | None:
    """Variavel de ambiente primeiro, depois o .env. O valor nunca e impresso."""
    return os.environ.get("GOOGLE_API_KEY") or ler_env().get("GOOGLE_API_KEY") or None
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest tests/core/test_configuracao.py -q`
Expected: `5 passed`.

- [ ] **Step 5: Testes do orçamento** — criar `tests/core/test_orcamento.py`:

```python
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
```

- [ ] **Step 6: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest tests/core/test_orcamento.py -q`
Expected: `ModuleNotFoundError: No module named 'discoveryleads.core.orcamento'`.

- [ ] **Step 7: Implementar** — criar `src/discoveryleads/core/orcamento.py`:

```python
"""Freio de chamadas pagas (principio 4 do CLAUDE.md).

Nesta fatia substitui o `cost_ledger`: um contador em memoria com teto. Sem
teto configurado, a busca nao roda.
"""

from dataclasses import dataclass


@dataclass
class Orcamento:
    teto: int
    usadas: int = 0

    def __post_init__(self) -> None:
        if self.teto < 1:
            raise ValueError("o teto de chamadas precisa ser pelo menos 1")

    @property
    def restantes(self) -> int:
        return self.teto - self.usadas

    def pode_chamar(self) -> bool:
        return self.usadas < self.teto

    def registrar(self) -> None:
        if not self.pode_chamar():
            raise RuntimeError("chamada acima do teto: pergunte pode_chamar() antes")
        self.usadas += 1
```

- [ ] **Step 8: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: todos passam.

- [ ] **Step 9: Commit**

```bash
git add src/discoveryleads/core/configuracao.py src/discoveryleads/core/orcamento.py tests/core/test_configuracao.py tests/core/test_orcamento.py
git commit -m "Leitura tolerante do .env e teto de chamadas pagas"
```

### Task 6: `places_discovery` — Text Search paginada com teto

Peça 2. Formato conferido na documentação oficial em 2026-09-11: `POST https://places.googleapis.com/v1/places:searchText`, cabeçalhos `X-Goog-Api-Key` e `X-Goog-FieldMask` (obrigatório; `nextPageToken` precisa estar nele para paginar), `pageSize` de 1 a 20, no máximo 60 resultados, `locationBias.circle` com raio até 50.000 m, e **todo parâmetro além de `pageSize`/`pageToken` tem que se repetir igual** entre páginas, senão `INVALID_ARGUMENT`.

**Files:**
- Create: `src/discoveryleads/collectors/places_discovery.py`, `tests/collectors/test_places_discovery.py`

**Interfaces:**
- Consumes: `Orcamento` e `chave_google` (Task 5), `telefone_e164`/`e_movel`/`ddd` (Task 4), `Signal` (Task 3), `MotivoDeFalha`.
- Produces:
  - `Lugar(place_id, nome, endereco, lat, lng, telefone, website, nota, avaliacoes, status, tipos: tuple[str, ...], nivel_preco)` — `telefone` no formato nacional do Google; `website` é `None` quando o lugar não tem site.
  - `ResultadoDaBusca(lugares: list[Lugar], teto_atingido: bool, motivo_falha: MotivoDeFalha | None, detalhe: str | None)` — `detalhe` é a mensagem do Google, só para o terminal, nunca gravada.
  - `async descobrir(nicho: str, cidade: str, raio_m: int, *, chave: str, orcamento: Orcamento) -> ResultadoDaBusca`
  - `sinais_do_lugar(lugar: Lugar, observado_em: str) -> list[Signal]` — tipos `places.website_uri`, `places.sem_site`, `places.avaliacoes_total`, `places.nota`, `places.status`, `places.telefone`, `places.tipos`, `places.price_level`, e, com telefone válido, `telefone.e_movel` e `telefone.ddd`. Fonte `places`, coletor `places_discovery`.
  - `URL_TEXT_SEARCH`.

- [ ] **Step 1: Escrever os testes** — criar `tests/collectors/test_places_discovery.py`:

```python
"""Peca 2 contra respostas gravadas (respx). So o teste `live` toca a rede."""

import json

import httpx
import pytest
import respx

from discoveryleads.collectors.places_discovery import (
    URL_TEXT_SEARCH,
    Lugar,
    descobrir,
    sinais_do_lugar,
)
from discoveryleads.core.configuracao import chave_google
from discoveryleads.core.falhas import MotivoDeFalha
from discoveryleads.core.orcamento import Orcamento

CHAVE = "chave-de-teste"
CENTRO = {"latitude": -16.6869, "longitude": -49.2648}


def _bruto(n: int, **extra) -> dict:
    lugar = {
        "id": f"place-{n}",
        "displayName": {"text": f"Salão {n}", "languageCode": "pt"},
        "formattedAddress": f"Rua {n}, Goiânia - GO",
        "location": {"latitude": -16.70, "longitude": -49.26},
        "types": ["beauty_salon", "point_of_interest"],
        "nationalPhoneNumber": f"(62) 99999-{n:04d}",
        "rating": 4.5,
        "userRatingCount": 10 * n,
        "businessStatus": "OPERATIONAL",
    }
    lugar.update(extra)
    return lugar


class _Google:
    """Imita a Text Search: responde o pedido do centro e depois as paginas, na
    ordem, guardando cada pedido para o teste conferir."""

    def __init__(self, *paginas, centro=None):
        self.paginas = list(paginas)
        self.centro = centro or httpx.Response(200, json={"places": [{"location": CENTRO}]})
        self.pedidos = []

    def __call__(self, request):
        self.pedidos.append((request.headers, json.loads(request.content)))
        if request.headers["X-Goog-FieldMask"] == "places.location":
            return self.centro
        return self.paginas.pop(0)


async def _descobrir(google, *, cidade="Goiânia", raio=5000, orcamento=None):
    respx.post(URL_TEXT_SEARCH).mock(side_effect=google)
    return await descobrir(
        "salão de beleza",
        cidade,
        raio,
        chave=CHAVE,
        orcamento=orcamento or Orcamento(teto=10),
    )


@respx.mock
async def test_pagina_unica_vira_lugares_normalizados():
    google = _Google(
        httpx.Response(
            200,
            json={
                "places": [
                    _bruto(1),
                    _bruto(2, websiteUri="https://salao2.com.br/", priceLevel="PRICE_LEVEL_MODERATE"),
                ]
            },
        )
    )

    resultado = await _descobrir(google)

    primeiro, segundo = resultado.lugares
    assert primeiro.place_id == "place-1"
    assert primeiro.nome == "Salão 1"
    assert primeiro.telefone == "(62) 99999-0001"
    assert primeiro.website is None
    assert segundo.website == "https://salao2.com.br/"
    assert segundo.nivel_preco == 2
    assert resultado.motivo_falha is None


@respx.mock
async def test_busca_usa_centro_raio_e_campos_combinados():
    google = _Google(httpx.Response(200, json={"places": [_bruto(1)]}))

    await _descobrir(google, cidade="Setor Bueno, Goiânia", raio=3000)

    assert google.pedidos[0][1]["textQuery"] == "Setor Bueno, Goiânia"
    cabecalhos, corpo = google.pedidos[1]
    assert corpo["textQuery"] == "salão de beleza em Setor Bueno, Goiânia"
    assert corpo["locationBias"]["circle"] == {"center": CENTRO, "radius": 3000.0}
    campos = cabecalhos["X-Goog-FieldMask"].split(",")
    assert "places.id" in campos
    assert "nextPageToken" in campos
    assert cabecalhos["X-Goog-Api-Key"] == CHAVE


@respx.mock
async def test_segue_o_next_page_token_repetindo_o_resto_do_pedido():
    google = _Google(
        httpx.Response(200, json={"places": [_bruto(1)], "nextPageToken": "tok-2"}),
        httpx.Response(200, json={"places": [_bruto(2)]}),
    )

    resultado = await _descobrir(google)

    assert len(resultado.lugares) == 2
    primeira, segunda = google.pedidos[1][1], google.pedidos[2][1]
    assert segunda["pageToken"] == "tok-2"
    # Qualquer outro parametro diferente e INVALID_ARGUMENT na API.
    assert {k: v for k, v in segunda.items() if k != "pageToken"} == primeira


@respx.mock
async def test_mesmo_place_id_em_duas_paginas_vira_um_lugar():
    google = _Google(
        httpx.Response(200, json={"places": [_bruto(1)], "nextPageToken": "tok-2"}),
        httpx.Response(200, json={"places": [_bruto(1), _bruto(2)]}),
    )

    resultado = await _descobrir(google)

    assert [lugar.place_id for lugar in resultado.lugares] == ["place-1", "place-2"]


@respx.mock
async def test_teto_de_chamadas_interrompe_a_paginacao_e_avisa():
    google = _Google(
        httpx.Response(200, json={"places": [_bruto(1)], "nextPageToken": "tok-2"})
    )
    orcamento = Orcamento(teto=2)  # centro + uma pagina

    resultado = await _descobrir(google, orcamento=orcamento)

    assert orcamento.usadas == 2
    assert len(google.pedidos) == 2
    assert resultado.teto_atingido is True
    assert [lugar.place_id for lugar in resultado.lugares] == ["place-1"]


@respx.mock
async def test_chave_recusada_vira_bloqueado_com_a_mensagem_do_google():
    google = _Google(
        centro=httpx.Response(403, json={"error": {"message": "API key not valid."}})
    )

    resultado = await _descobrir(google)

    assert resultado.motivo_falha is MotivoDeFalha.BLOQUEADO
    assert resultado.detalhe == "API key not valid."
    assert resultado.lugares == []


@respx.mock
async def test_429_vira_cota_estourada():
    google = _Google(centro=httpx.Response(429, json={"error": {"message": "Quota exceeded"}}))

    resultado = await _descobrir(google)

    assert resultado.motivo_falha is MotivoDeFalha.COTA_ESTOURADA


@respx.mock
async def test_falha_no_meio_da_paginacao_guarda_o_que_ja_veio():
    google = _Google(
        httpx.Response(200, json={"places": [_bruto(1)], "nextPageToken": "tok-2"}),
        httpx.Response(500, json={"error": {"message": "Internal error"}}),
    )

    resultado = await _descobrir(google)

    assert [lugar.place_id for lugar in resultado.lugares] == ["place-1"]
    assert resultado.motivo_falha is MotivoDeFalha.RESPOSTA_INVALIDA


@respx.mock
async def test_regiao_que_o_google_nao_acha_nao_gasta_a_busca():
    google = _Google(centro=httpx.Response(200, json={}))
    orcamento = Orcamento(teto=10)

    resultado = await _descobrir(google, cidade="Cidade Inventada", orcamento=orcamento)

    assert resultado.motivo_falha is MotivoDeFalha.NAO_ENCONTRADO
    assert orcamento.usadas == 1


@respx.mock
async def test_timeout_na_rede_vira_motivo_em_enum():
    respx.post(URL_TEXT_SEARCH).mock(side_effect=httpx.ConnectTimeout("lento"))

    resultado = await descobrir(
        "salão de beleza", "Goiânia", 5000, chave=CHAVE, orcamento=Orcamento(teto=10)
    )

    assert resultado.motivo_falha is MotivoDeFalha.TIMEOUT


def test_sinais_do_lugar_sem_site_e_com_celular():
    lugar = Lugar(
        place_id="p1",
        nome="Salão",
        endereco=None,
        lat=None,
        lng=None,
        telefone="(62) 99999-8888",
        website=None,
        nota=4.8,
        avaliacoes=37,
        status="OPERATIONAL",
        tipos=("beauty_salon",),
        nivel_preco=None,
    )

    sinais = {s.tipo: s for s in sinais_do_lugar(lugar, "2026-09-11T14:02:00+00:00")}

    assert sinais["places.sem_site"].valor is True
    assert sinais["places.website_uri"].valor is None
    assert sinais["places.avaliacoes_total"].valor == 37
    assert sinais["telefone.e_movel"].valor is True
    assert sinais["telefone.ddd"].valor == "62"
    assert sinais["places.sem_site"].fonte == "places"
    assert sinais["places.sem_site"].coletor == "places_discovery"


@pytest.mark.live
async def test_live_busca_real_gasta_duas_chamadas():
    """Canario do contrato do Google. GASTA 2 CHAMADAS PAGAS (centro + uma
    pagina). Roda com -m live e exige GOOGLE_API_KEY."""
    chave = chave_google()
    if chave is None:
        pytest.skip("GOOGLE_API_KEY vazia")

    resultado = await descobrir(
        "salão de beleza", "Setor Bueno, Goiânia", 2000, chave=chave, orcamento=Orcamento(teto=2)
    )

    assert resultado.motivo_falha is None, resultado.detalhe
    assert resultado.lugares
    assert all(lugar.place_id for lugar in resultado.lugares)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest tests/collectors/test_places_discovery.py -q`
Expected: `ModuleNotFoundError: No module named 'discoveryleads.collectors.places_discovery'`.

- [ ] **Step 3: Implementar** — criar `src/discoveryleads/collectors/places_discovery.py`:

```python
"""Descoberta pelo Google Places — Text Search (New), raio unico, paginada.

Peca 2 da Fatia Dia 1. Cada requisicao conta no `Orcamento` antes de ser feita,
inclusive a que falha. Nada levanta excecao: falha volta como `motivo_falha`
do enum da secao 8.3.

So sinais derivados saem daqui; o JSON cru do Google nao e guardado (spike S3).
"""

from dataclasses import dataclass, field

import httpx

from discoveryleads.core.falhas import MotivoDeFalha
from discoveryleads.core.normalizacao import ddd, e_movel, telefone_e164
from discoveryleads.core.orcamento import Orcamento
from discoveryleads.core.sinais import Signal

URL_TEXT_SEARCH = "https://places.googleapis.com/v1/places:searchText"
VERSAO = 1
TIMEOUT_S = 20.0

# `places.id` nao estava na lista da fatia e e o que permite dedupe por
# place_id. E da faixa Essentials IDs Only; a chamada ja e cobrada como
# Enterprise por causa de telefone, site e avaliacoes.
CAMPOS_BUSCA = (
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.location",
    "places.types",
    "places.nationalPhoneNumber",
    "places.websiteUri",
    "places.rating",
    "places.userRatingCount",
    "places.businessStatus",
    "places.priceLevel",
    "nextPageToken",
)
CAMPOS_CENTRO = ("places.location",)

# Limite documentado da Text Search (New): 60 resultados, 20 por pagina.
MAX_PAGINAS = 3
TAMANHO_DA_PAGINA = 20

NIVEL_DE_PRECO = {
    "PRICE_LEVEL_FREE": 0,
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}


@dataclass(frozen=True)
class Lugar:
    place_id: str
    nome: str
    endereco: str | None
    lat: float | None
    lng: float | None
    telefone: str | None  # nacional, como o Google manda: "(62) 99999-8888"
    website: str | None
    nota: float | None
    avaliacoes: int
    status: str | None
    tipos: tuple[str, ...]
    nivel_preco: int | None


@dataclass
class ResultadoDaBusca:
    lugares: list[Lugar] = field(default_factory=list)
    teto_atingido: bool = False
    motivo_falha: MotivoDeFalha | None = None
    # Mensagem de erro do Google, so para o terminal. O que se grava e o motivo
    # em enum — principio 1.
    detalhe: str | None = None


def _lugar(bruto: dict) -> Lugar | None:
    place_id = bruto.get("id")
    if not place_id:
        return None
    local = bruto.get("location") or {}
    return Lugar(
        place_id=place_id,
        nome=(bruto.get("displayName") or {}).get("text") or "",
        endereco=bruto.get("formattedAddress"),
        lat=local.get("latitude"),
        lng=local.get("longitude"),
        telefone=bruto.get("nationalPhoneNumber"),
        website=bruto.get("websiteUri") or None,
        nota=bruto.get("rating"),
        avaliacoes=int(bruto.get("userRatingCount") or 0),
        status=bruto.get("businessStatus"),
        tipos=tuple(bruto.get("types") or ()),
        nivel_preco=NIVEL_DE_PRECO.get(bruto.get("priceLevel")),
    )


def _motivo_do_status(status: int) -> MotivoDeFalha:
    if status == 429:
        return MotivoDeFalha.COTA_ESTOURADA
    if status in (401, 403):
        return MotivoDeFalha.BLOQUEADO
    return MotivoDeFalha.RESPOSTA_INVALIDA


async def _chamar(
    cliente: httpx.AsyncClient,
    chave: str,
    corpo: dict,
    campos: tuple[str, ...],
    orcamento: Orcamento,
) -> tuple[dict | None, MotivoDeFalha | None, str | None]:
    """Uma requisicao paga. Devolve (json, motivo_falha, detalhe)."""
    orcamento.registrar()
    try:
        resposta = await cliente.post(
            URL_TEXT_SEARCH,
            json=corpo,
            headers={"X-Goog-Api-Key": chave, "X-Goog-FieldMask": ",".join(campos)},
        )
    except httpx.TimeoutException:
        return None, MotivoDeFalha.TIMEOUT, None
    except httpx.TransportError:
        return None, MotivoDeFalha.REDE_INDISPONIVEL, None
    except httpx.HTTPError:
        return None, MotivoDeFalha.RESPOSTA_INVALIDA, None

    if resposta.status_code != 200:
        try:
            detalhe = (resposta.json().get("error") or {}).get("message")
        except ValueError:
            detalhe = None
        return None, _motivo_do_status(resposta.status_code), detalhe
    try:
        return resposta.json(), None, None
    except ValueError:
        return None, MotivoDeFalha.PARSE_FALHOU, None


async def descobrir(
    nicho: str, cidade: str, raio_m: int, *, chave: str, orcamento: Orcamento
) -> ResultadoDaBusca:
    resultado = ResultadoDaBusca()
    if not orcamento.pode_chamar():
        resultado.teto_atingido = True
        return resultado

    async with httpx.AsyncClient(timeout=TIMEOUT_S) as cliente:
        # Sem centro nao existe locationBias com raio. Uma chamada, contada.
        dados, motivo, detalhe = await _chamar(
            cliente,
            chave,
            {"textQuery": cidade, "pageSize": 1, "languageCode": "pt-BR", "regionCode": "BR"},
            CAMPOS_CENTRO,
            orcamento,
        )
        if motivo is not None:
            resultado.motivo_falha, resultado.detalhe = motivo, detalhe
            return resultado
        achados = dados.get("places") or []
        centro = (achados[0].get("location") if achados else None) or {}
        if "latitude" not in centro or "longitude" not in centro:
            resultado.motivo_falha = MotivoDeFalha.NAO_ENCONTRADO
            resultado.detalhe = f"o Google não achou a região {cidade!r}"
            return resultado

        corpo = {
            "textQuery": f"{nicho} em {cidade}",
            "pageSize": TAMANHO_DA_PAGINA,
            "languageCode": "pt-BR",
            "regionCode": "BR",
            "locationBias": {
                "circle": {
                    "center": {"latitude": centro["latitude"], "longitude": centro["longitude"]},
                    "radius": float(raio_m),
                }
            },
        }
        vistos: dict[str, Lugar] = {}
        for _ in range(MAX_PAGINAS):
            if not orcamento.pode_chamar():
                resultado.teto_atingido = True
                break
            dados, motivo, detalhe = await _chamar(cliente, chave, corpo, CAMPOS_BUSCA, orcamento)
            if motivo is not None:
                resultado.motivo_falha, resultado.detalhe = motivo, detalhe
                break
            for bruto in dados.get("places") or []:
                lugar = _lugar(bruto)
                if lugar is not None:
                    vistos.setdefault(lugar.place_id, lugar)
            token = dados.get("nextPageToken")
            if not token:
                break
            corpo = {**corpo, "pageToken": token}

    resultado.lugares = list(vistos.values())
    return resultado


def sinais_do_lugar(lugar: Lugar, observado_em: str) -> list[Signal]:
    def sinal(tipo: str, valor: object) -> Signal:
        return Signal(
            tipo=tipo,
            valor=valor,
            fonte="places",
            coletor="places_discovery",
            versao=VERSAO,
            observado_em=observado_em,
        )

    sinais = [
        sinal("places.website_uri", lugar.website),
        sinal("places.sem_site", lugar.website is None),
        sinal("places.avaliacoes_total", lugar.avaliacoes),
        sinal("places.nota", lugar.nota),
        sinal("places.status", lugar.status),
        sinal("places.telefone", lugar.telefone),
        sinal("places.tipos", list(lugar.tipos)),
        sinal("places.price_level", lugar.nivel_preco),
    ]
    e164 = telefone_e164(lugar.telefone)
    if e164 is not None:
        sinais += [
            sinal("telefone.e_movel", e_movel(e164)),
            sinal("telefone.ddd", ddd(e164)),
        ]
    return sinais
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: todos passam (o live fica de fora).

- [ ] **Step 5: Canário ao vivo (opcional — GASTA 2 CHAMADAS PAGAS)**

Run: `.venv/Scripts/python.exe -m pytest tests/collectors/test_places_discovery.py -m live -q`
Expected: `1 passed`. Se falhar com `BLOQUEADO`, a mensagem do Google no `assert` diz o que falta (API não habilitada, chave restrita, faturamento).

- [ ] **Step 6: Commit**

```bash
git add src/discoveryleads/collectors/places_discovery.py tests/collectors/test_places_discovery.py
git commit -m "Peca 2: places_discovery com Text Search paginada, dedupe e teto de chamadas"
```

### Task 7: SQLite com `signals` append-only

O `schema.sql` que a fatia pôs no lugar do Alembic. Grava desde a primeira busca porque histórico não se recupera depois: "trocou Linktree por Canva há 12 dias" (seção 4.3) só existe se a observação de hoje foi gravada hoje. O próprio banco recusa UPDATE e DELETE em `signals`, em vez de depender de todo mundo lembrar do princípio 2.

A exclusão por LGPD (seção 11, `DELETE /leads/{id}`) vai precisar de um caminho deliberado que passe por esse gatilho. É proposital: a exclusão tem que ser projetada, não feita às pressas.

**Files:**
- Create: `src/discoveryleads/db/__init__.py`, `src/discoveryleads/db/schema.sql`, `src/discoveryleads/db/repositorio.py`, `tests/db/__init__.py`, `tests/db/test_repositorio.py`
- Modify: `pyproject.toml` (incluir o `.sql` no pacote)

**Interfaces:**
- Consumes: `Signal` (Task 3).
- Produces: `abrir(caminho: Path | str) -> sqlite3.Connection`; `gravar_lead(conexao, *, place_id, nome, endereco, cidade, lat, lng, telefone_e164, agora) -> int`; `registrar_sinais(conexao, lead_id: int, sinais: list[Signal]) -> None`; `sinais_atuais(conexao, lead_id: int) -> dict[str, Signal]`. Quem chama faz o `commit()`.

- [ ] **Step 1: Escrever os testes** — criar `tests/db/__init__.py` vazio e `tests/db/test_repositorio.py`:

```python
import sqlite3

import pytest

from discoveryleads.core.sinais import Signal
from discoveryleads.db.repositorio import abrir, gravar_lead, registrar_sinais, sinais_atuais

AGORA = "2026-09-11T14:02:00+00:00"
DEPOIS = "2026-09-25T09:00:00+00:00"


def _sinal(tipo, valor, observado_em=AGORA):
    return Signal(
        tipo=tipo,
        valor=valor,
        fonte="site",
        coletor="site_classifier",
        versao=1,
        observado_em=observado_em,
    )


def _lead(conexao, place_id="place-1"):
    return gravar_lead(
        conexao,
        place_id=place_id,
        nome="Salão da Ana",
        endereco="Rua 1, Goiânia - GO",
        cidade="Goiânia",
        lat=-16.7,
        lng=-49.26,
        telefone_e164="+5562999998888",
        agora=AGORA,
    )


def test_mesmo_place_id_em_duas_buscas_e_o_mesmo_lead(tmp_path):
    conexao = abrir(tmp_path / "var" / "discoveryleads.db")

    primeiro = _lead(conexao)
    segundo = _lead(conexao)

    assert primeiro == segundo
    assert conexao.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 1


def test_signals_recusa_update(tmp_path):
    conexao = abrir(tmp_path / "leads.db")
    registrar_sinais(conexao, _lead(conexao), [_sinal("site.plataforma", "canva")])

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conexao.execute("UPDATE signals SET valor = '\"wix\"'")


def test_signals_recusa_delete(tmp_path):
    conexao = abrir(tmp_path / "leads.db")
    registrar_sinais(conexao, _lead(conexao), [_sinal("site.plataforma", "canva")])

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conexao.execute("DELETE FROM signals")


def test_sinal_atual_e_a_observacao_mais_recente_e_a_antiga_fica(tmp_path):
    """"Trocou Linktree por Canva" so existe porque as duas observacoes ficam."""
    conexao = abrir(tmp_path / "leads.db")
    lead_id = _lead(conexao)

    registrar_sinais(conexao, lead_id, [_sinal("site.plataforma", "agregador")])
    registrar_sinais(conexao, lead_id, [_sinal("site.plataforma", "canva", DEPOIS)])

    assert sinais_atuais(conexao, lead_id)["site.plataforma"].valor == "canva"
    assert conexao.execute("SELECT COUNT(*) FROM signals").fetchone()[0] == 2


def test_valor_volta_do_banco_com_o_tipo_certo(tmp_path):
    conexao = abrir(tmp_path / "leads.db")
    lead_id = _lead(conexao)

    registrar_sinais(
        conexao,
        lead_id,
        [
            _sinal("tracking.meta_pixel", True),
            _sinal("tracking.eventos_conversao", []),
            _sinal("site.whatsapp_link", None),
            _sinal("site.http_status", 403),
        ],
    )
    atuais = sinais_atuais(conexao, lead_id)

    assert atuais["tracking.meta_pixel"].valor is True
    assert atuais["tracking.eventos_conversao"].valor == []
    assert atuais["site.whatsapp_link"].valor is None
    assert atuais["site.http_status"].valor == 403
    assert atuais["site.http_status"].coletor == "site_classifier"
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest tests/db -q`
Expected: `ModuleNotFoundError: No module named 'discoveryleads.db'`.

- [ ] **Step 3: Criar o schema** — `src/discoveryleads/db/__init__.py` vazio e `src/discoveryleads/db/schema.sql`:

```sql
-- Primeira migracao do DiscoveryLeads. Na Fatia Dia 1 substitui o Alembic, e
-- amanha vira a migracao 0001 sem mudar nada. Subconjunto das secoes 4.1, 4.2
-- e 4.3 da spec, com os nomes de la.
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY,
    nome            TEXT NOT NULL,
    endereco        TEXT,
    cidade          TEXT,
    uf              TEXT,
    lat             REAL,
    lng             REAL,
    telefone_e164   TEXT,
    categoria       TEXT,
    criado_em       TEXT NOT NULL,
    atualizado_em   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lead_identities (
    tipo     TEXT NOT NULL,
    valor    TEXT NOT NULL,
    lead_id  INTEGER NOT NULL REFERENCES leads(id),
    PRIMARY KEY (tipo, valor)
);

CREATE TABLE IF NOT EXISTS signals (
    id           INTEGER PRIMARY KEY,
    lead_id      INTEGER NOT NULL REFERENCES leads(id),
    tipo         TEXT NOT NULL,
    valor        TEXT,
    fonte        TEXT NOT NULL,
    coletor      TEXT NOT NULL,
    versao       INTEGER NOT NULL,
    confianca    REAL NOT NULL,
    observado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_signals_lead_tipo
    ON signals(lead_id, tipo, observado_em DESC);

-- Principio 2: signals e append-only, e o banco garante sozinho.
CREATE TRIGGER IF NOT EXISTS signals_sem_update BEFORE UPDATE ON signals
BEGIN
    SELECT RAISE(ABORT, 'signals e append-only: UPDATE proibido');
END;
CREATE TRIGGER IF NOT EXISTS signals_sem_delete BEFORE DELETE ON signals
BEGIN
    SELECT RAISE(ABORT, 'signals e append-only: DELETE proibido');
END;

-- A visao atual de um lead: a ultima observacao de cada tipo.
CREATE VIEW IF NOT EXISTS v_signals_atuais AS
SELECT s.*
FROM signals s
WHERE s.id = (
    SELECT s2.id
    FROM signals s2
    WHERE s2.lead_id = s.lead_id AND s2.tipo = s.tipo
    ORDER BY s2.observado_em DESC, s2.id DESC
    LIMIT 1
);
```

- [ ] **Step 4: Implementar o repositório** — criar `src/discoveryleads/db/repositorio.py`:

```python
"""Acesso ao SQLite da fatia.

`signals` so recebe INSERT (principio 2) — e o proprio banco recusa o resto.
`leads` e desnormalizada por conveniencia (secao 4.1) e pode ser atualizada; a
verdade continua em `signals`. Quem chama faz o commit.
"""

import json
import sqlite3
from pathlib import Path

from discoveryleads.core.sinais import Signal

SCHEMA = Path(__file__).with_name("schema.sql")


def abrir(caminho: Path | str) -> sqlite3.Connection:
    if str(caminho) != ":memory:":
        Path(caminho).parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    conexao.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conexao


def lead_por_identidade(conexao: sqlite3.Connection, tipo: str, valor: str) -> int | None:
    linha = conexao.execute(
        "SELECT lead_id FROM lead_identities WHERE tipo = ? AND valor = ?", (tipo, valor)
    ).fetchone()
    return linha["lead_id"] if linha else None


def gravar_lead(
    conexao: sqlite3.Connection,
    *,
    place_id: str,
    nome: str,
    endereco: str | None,
    cidade: str | None,
    lat: float | None,
    lng: float | None,
    telefone_e164: str | None,
    agora: str,
) -> int:
    """Insere o lead ou atualiza o que ja tem o mesmo place_id.

    Nesta fatia a identidade e so place_id (substituicao tatica da fatia).
    Telefone, dominio e Instagram entram com a resolucao completa, na E2.
    """
    existente = lead_por_identidade(conexao, "place_id", place_id)
    if existente is not None:
        conexao.execute(
            "UPDATE leads SET nome = ?, endereco = ?, cidade = ?, lat = ?, lng = ?,"
            " telefone_e164 = ?, atualizado_em = ? WHERE id = ?",
            (nome, endereco, cidade, lat, lng, telefone_e164, agora, existente),
        )
        return existente

    cursor = conexao.execute(
        "INSERT INTO leads (nome, endereco, cidade, lat, lng, telefone_e164,"
        " criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (nome, endereco, cidade, lat, lng, telefone_e164, agora, agora),
    )
    lead_id = cursor.lastrowid
    conexao.execute(
        "INSERT INTO lead_identities (tipo, valor, lead_id) VALUES ('place_id', ?, ?)",
        (place_id, lead_id),
    )
    return lead_id


def registrar_sinais(conexao: sqlite3.Connection, lead_id: int, sinais: list[Signal]) -> None:
    conexao.executemany(
        "INSERT INTO signals (lead_id, tipo, valor, fonte, coletor, versao, confianca,"
        " observado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (lead_id, s.tipo, s.valor_json(), s.fonte, s.coletor, s.versao, s.confianca, s.observado_em)
            for s in sinais
        ],
    )


def sinais_atuais(conexao: sqlite3.Connection, lead_id: int) -> dict[str, Signal]:
    linhas = conexao.execute(
        "SELECT * FROM v_signals_atuais WHERE lead_id = ?", (lead_id,)
    ).fetchall()
    return {
        linha["tipo"]: Signal(
            tipo=linha["tipo"],
            valor=json.loads(linha["valor"]),
            fonte=linha["fonte"],
            coletor=linha["coletor"],
            versao=linha["versao"],
            observado_em=linha["observado_em"],
            confianca=linha["confianca"],
        )
        for linha in linhas
    }
```

- [ ] **Step 5: Incluir o `.sql` no pacote** — em `pyproject.toml`, depois de `[tool.setuptools.packages.find]`:

```toml
[tool.setuptools.package-data]
discoveryleads = ["db/schema.sql"]
```

(Na instalação editável atual não muda nada. Numa instalação normal, sem isso o `schema.sql` fica de fora.)

- [ ] **Step 6: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: todos passam.

- [ ] **Step 7: Commit**

```bash
git add src/discoveryleads/db tests/db pyproject.toml
git commit -m "SQLite da fatia: leads, identidades e signals append-only garantido pelo banco"
```

### Task 8: Elegibilidade com motivo e evidência

Peça 3, primeira metade. Seção 6.1 da spec mais as decisões 1 a 5 e 13 do topo deste plano. O resultado nunca é número: é categoria, frase e os sinais que a sustentam.

Os testes usam as **fixtures reais** passando pela análise da Task 3. É assim que a garantia contra falso positivo da peça 1 chega até a lista final.

**Files:**
- Create: `config/scoring.toml`, `config/nichos.toml`, `src/discoveryleads/scoring/__init__.py`, `src/discoveryleads/scoring/elegibilidade.py`, `tests/scoring/__init__.py`, `tests/scoring/test_elegibilidade.py`

**Interfaces:**
- Consumes: `Signal`, `sinais_da_resposta` (Task 3), `telefone_e164` (Task 4), `dominio_de`, `dominio_casa`.
- Produces:
  - `Categoria` (enum de texto): `SEM_SITE`, `CANVA`, `AGREGADOR`, `GOOGLE_SITES_EXTINTO`, `SITE_QUEBRADO`, `SUBDOMINIO_GRATIS` (elegíveis); `TEM_SITE_PROPRIO`, `FECHADO`, `REDE_FRANQUIA`, `FORA_DO_ICP` (inelegíveis); `INDETERMINADO`.
  - `Elegibilidade(categoria: Categoria, motivo: str, evidencia: tuple[Signal, ...])` com a propriedade `elegivel: bool`.
  - `avaliar_elegibilidade(sinais: dict[str, Signal], *, tipos_excluir=(), franquia: str | None = None, subdominios_gratis=()) -> Elegibilidade`
  - `identificar_franquias(lugares: Iterable[tuple[str, str, str | None]], minimo: int) -> dict[str, str]` — de `(place_id, nome, telefone)` para `place_id -> descrição`.

- [ ] **Step 1: Criar as configurações** — `config/scoring.toml`:

```toml
# Regras de elegibilidade e faixas (secao 6 da spec), com as decisoes de
# 2026-09-11. Fora do codigo para o operador calibrar sem reprogramar.

[elegibilidade]
# Construtor em subdominio gratis e "substituto improvisado": a pessoa nem
# comprou dominio (decisao do Saulo, 2026-09-11). Com dominio proprio e
# TEM_SITE_PROPRIO. So entram subdominios confirmados em fixture real.
subdominios_gratis = ["wixsite.com", "myshopify.com", "lojaintegrada.com.br"]

# REDE_FRANQUIA: mesmo telefone ou mesmo nome em pelo menos N place_id da busca.
franquia_min_ocorrencias = 3

[faixas]
# Demanda comprovada (secao 6.2).
demanda_min_avaliacoes = 20

# T0 exige rastreamento PAGO. GA, GTM e heatmap medem, nao provam verba.
rastreamento_pago = ["meta_pixel", "google_ads", "tiktok_pixel"]
```

E `config/nichos.toml`:

```toml
# Definicao de nicho enquanto a tabela `niches` (secao 4.6) nao existe.
# A chave e o texto exato passado em --nicho.

["salão de beleza"]
# FORA_DO_ICP (secao 6.1): quem precisa de site institucional com varias paginas
# nao e cliente de landing page nesta temporada. Tipos da Tabela A do Places.
tipos_excluir = ["lawyer", "accounting", "doctor", "hospital"]
```

- [ ] **Step 2: Escrever os testes** — criar `tests/scoring/__init__.py` vazio e `tests/scoring/test_elegibilidade.py`:

```python
"""Secao 6.1 sobre sinais de verdade: o HTML das fixtures reais passa pela
analise do site e chega aqui como Signal."""

import pytest

from discoveryleads.collectors.site_analise import sinais_da_resposta
from discoveryleads.collectors.site_fetcher import RespostaDoSite
from discoveryleads.core.configuracao import carregar
from discoveryleads.core.falhas import MotivoDeFalha
from discoveryleads.core.sinais import Signal
from discoveryleads.scoring.elegibilidade import (
    Categoria,
    avaliar_elegibilidade,
    identificar_franquias,
)

from tests.conftest import carregar_fixture

MOMENTO = "2026-09-11T14:02:00+00:00"
SUBDOMINIOS = ("wixsite.com", "myshopify.com", "lojaintegrada.com.br")


def _places(website, *, status="OPERATIONAL", tipos=("beauty_salon",), telefone="(62) 99999-8888"):
    def sinal(tipo, valor):
        return Signal(
            tipo=tipo,
            valor=valor,
            fonte="places",
            coletor="places_discovery",
            versao=1,
            observado_em=MOMENTO,
        )

    return [
        sinal("places.website_uri", website),
        sinal("places.sem_site", website is None),
        sinal("places.status", status),
        sinal("places.tipos", list(tipos)),
        sinal("places.telefone", telefone),
        sinal("places.avaliacoes_total", 30),
    ]


def _lead(website, resposta=None, **places):
    sinais = _places(website, **places)
    if resposta is not None:
        sinais += sinais_da_resposta(website, resposta, MOMENTO)
    return {sinal.tipo: sinal for sinal in sinais}


def _pagina(fixture, url_final, status=200, motivo=None):
    return RespostaDoSite(
        url_final=url_final,
        http_status=status,
        html=carregar_fixture(fixture),
        https_valido=url_final.startswith("https://"),
        motivo_falha=motivo,
    )


def _avaliar(sinais, **extra):
    return avaliar_elegibilidade(sinais, subdominios_gratis=SUBDOMINIOS, **extra)


def _canva():
    url = "https://vocenosalao.my.canva.site/"
    return _lead(url, _pagina("canva_salao.html", url))


def test_sem_site_e_elegivel_com_evidencia_do_google():
    elegibilidade = _avaliar(_lead(None))

    assert elegibilidade.categoria is Categoria.SEM_SITE
    assert elegibilidade.motivo == "elegível — não tem site no Google"
    assert elegibilidade.evidencia[0].tipo == "places.sem_site"


def test_canva_real_e_elegivel_e_o_motivo_diz_onde_esta_a_pagina():
    elegibilidade = _avaliar(_canva())

    assert elegibilidade.categoria is Categoria.CANVA
    assert elegibilidade.motivo == (
        "elegível — a página está em vocenosalao.my.canva.site, feita no Canva"
    )
    assert elegibilidade.evidencia[0].tipo == "site.plataforma"
    assert elegibilidade.evidencia[0].coletor == "site_classifier"


def test_google_sites_extinto_com_404_e_elegivel():
    url = "https://barbearia.business.site/"
    sinais = _lead(url, _pagina("google_sites_extinto_404.html", url, 404, MotivoDeFalha.NAO_ENCONTRADO))

    assert _avaliar(sinais).categoria is Categoria.GOOGLE_SITES_EXTINTO


def test_wix_em_subdominio_gratis_e_elegivel():
    url = "https://vwcabeloeestetica.wixsite.com/barber"
    elegibilidade = _avaliar(_lead(url, _pagina("wix_wixsite.html", url)))

    assert elegibilidade.categoria is Categoria.SUBDOMINIO_GRATIS
    assert "vwcabeloeestetica.wixsite.com" in elegibilidade.motivo


def test_shopify_em_dominio_proprio_tem_site_proprio():
    sinais = _lead(
        "https://www.hifly.com.br/",
        _pagina("shopify_em_dominio_proprio.html", "https://hifly.com.br/"),
    )

    elegibilidade = _avaliar(sinais)

    assert elegibilidade.categoria is Categoria.TEM_SITE_PROPRIO
    assert elegibilidade.elegivel is False


def test_subdominio_gratis_que_redireciona_para_dominio_proprio_tem_site_proprio():
    """Decisao 1: vale o dominio FINAL, onde o cliente do lead cai."""
    sinais = _lead(
        "https://minhaloja.myshopify.com/",
        _pagina("shopify_ativa.html", "https://minhaloja.com.br/"),
    )

    assert _avaliar(sinais).categoria is Categoria.TEM_SITE_PROPRIO


def test_loja_suspensa_402_e_site_quebrado():
    url = "https://u10pfz-mz.myshopify.com/"
    sinais = _lead(url, _pagina("shopify_suspensa_402.html", url, 402, MotivoDeFalha.RESPOSTA_INVALIDA))

    elegibilidade = _avaliar(sinais)

    assert elegibilidade.categoria is Categoria.SITE_QUEBRADO
    assert "402" in elegibilidade.motivo


def test_loja_integrada_atras_de_anti_bot_continua_elegivel_pelo_subdominio():
    """Bloqueio nao e quebra, e o dominio ainda diz o que e (armadilha 7)."""
    url = "https://petprodutos.lojaintegrada.com.br/"
    sinais = _lead(url, _pagina("loja_integrada_bloqueada_403.html", url, 403, MotivoDeFalha.BLOQUEADO))

    assert _avaliar(sinais).categoria is Categoria.SUBDOMINIO_GRATIS


def test_site_proprio_bloqueado_sem_pista_e_indeterminado():
    url = "https://salaodaana.com.br/"
    sinais = _lead(url, _pagina("agregador_beacons_bloqueado_403.html", url, 403, MotivoDeFalha.BLOQUEADO))

    elegibilidade = _avaliar(sinais)

    assert elegibilidade.categoria is Categoria.INDETERMINADO
    assert elegibilidade.elegivel is False
    assert "bloqueado" in elegibilidade.motivo


def test_site_proprio_bem_feito_nao_e_elegivel():
    """O falso positivo mais caro: ligar para quem ja tem site bom."""
    sinais = _lead(
        "https://www.espacolaser.com.br/",
        _pagina("proprio_bem_feito.html", "https://espacolaser.com.br/"),
    )

    assert _avaliar(sinais).categoria is Categoria.TEM_SITE_PROPRIO


def test_dominio_que_nao_resolve_e_site_quebrado():
    sinais = _lead(
        "https://salao-que-fechou.com.br/",
        RespostaDoSite(motivo_falha=MotivoDeFalha.DOMINIO_NAO_RESOLVE),
    )

    elegibilidade = _avaliar(sinais)

    assert elegibilidade.categoria is Categoria.SITE_QUEBRADO
    assert "domínio não resolve" in elegibilidade.motivo


def test_certificado_invalido_e_site_quebrado():
    sinais = _lead(
        "https://vencido.com.br/",
        RespostaDoSite(https_valido=False, motivo_falha=MotivoDeFalha.RESPOSTA_INVALIDA),
    )

    elegibilidade = _avaliar(sinais)

    assert elegibilidade.categoria is Categoria.SITE_QUEBRADO
    assert "certificado" in elegibilidade.motivo


def test_fechado_vence_canva():
    sinais = _canva()
    sinais["places.status"] = Signal(
        tipo="places.status",
        valor="CLOSED_PERMANENTLY",
        fonte="places",
        coletor="places_discovery",
        versao=1,
        observado_em=MOMENTO,
    )

    elegibilidade = _avaliar(sinais)

    assert elegibilidade.categoria is Categoria.FECHADO
    assert "fechado de vez" in elegibilidade.motivo


def test_tipo_excluido_e_fora_do_icp():
    sinais = _lead(None, tipos=("lawyer", "point_of_interest"))

    elegibilidade = _avaliar(sinais, tipos_excluir=("lawyer", "accounting"))

    assert elegibilidade.categoria is Categoria.FORA_DO_ICP
    assert "lawyer" in elegibilidade.motivo


def test_franquia_vence_sem_site():
    elegibilidade = _avaliar(
        _lead(None), franquia="o telefone +556233334444 aparece em 3 unidades da busca"
    )

    assert elegibilidade.categoria is Categoria.REDE_FRANQUIA
    assert "3 unidades" in elegibilidade.motivo


def test_lead_sem_sinal_nunca_e_elegivel():
    """Invariante da secao 12."""
    assert _avaliar({}).elegivel is False


@pytest.mark.parametrize(
    "fabrica",
    [
        lambda: _lead(None),
        _canva,
        lambda: _lead(
            "https://vwcabeloeestetica.wixsite.com/barber",
            _pagina("wix_wixsite.html", "https://vwcabeloeestetica.wixsite.com/barber"),
        ),
        lambda: _lead(
            "https://salao-que-fechou.com.br/",
            RespostaDoSite(motivo_falha=MotivoDeFalha.DOMINIO_NAO_RESOLVE),
        ),
    ],
    ids=["sem_site", "canva", "subdominio_gratis", "site_quebrado"],
)
def test_todo_elegivel_traz_evidencia(fabrica):
    """Nenhum argumento de venda sem sinal que o sustente (principio 3)."""
    elegibilidade = _avaliar(fabrica())

    assert elegibilidade.elegivel is True
    assert elegibilidade.evidencia


def test_mesmo_telefone_com_grafias_diferentes_em_tres_unidades_e_franquia():
    franquias = identificar_franquias(
        [
            ("a", "Unidade Centro", "(62) 3333-4444"),
            ("b", "Unidade Bueno", "+55 62 3333-4444"),
            ("c", "Unidade Oeste", "062 3333-4444"),
            ("d", "Salão da Ana", "(62) 99999-8888"),
        ],
        minimo=3,
    )

    assert set(franquias) == {"a", "b", "c"}
    assert "3 unidades" in franquias["a"]


def test_duas_unidades_nao_bastam_para_franquia():
    franquias = identificar_franquias(
        [("a", "Studio Ana", "(62) 3333-4444"), ("b", "Studio Ana", "(62) 3333-4444")],
        minimo=3,
    )

    assert franquias == {}


def test_mesmo_nome_com_caixa_acento_e_espaco_diferentes_e_franquia():
    franquias = identificar_franquias(
        [("a", "Studio Ana", None), ("b", "STUDIO  ANA", None), ("c", "Stúdio Ana", None)],
        minimo=3,
    )

    assert set(franquias) == {"a", "b", "c"}


def test_config_so_aceita_subdominios_confirmados_em_fixture():
    """Principio 5 com trava: mudar esta lista e decisao, nao ajuste casual."""
    config = carregar("scoring.toml")

    assert config["elegibilidade"]["subdominios_gratis"] == list(SUBDOMINIOS)
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest tests/scoring -q`
Expected: `ModuleNotFoundError: No module named 'discoveryleads.scoring'`.

- [ ] **Step 4: Implementar** — criar `src/discoveryleads/scoring/__init__.py` vazio e `src/discoveryleads/scoring/elegibilidade.py`:

```python
"""Elegibilidade — a porta de entrada da secao 6.1, sempre com motivo.

O resultado nunca e um numero. E uma categoria, uma frase e os sinais que a
sustentam, porque o operador tem que poder ser checado na frente do cliente.

A ordem das regras e a ordem de precedencia: fechado, fora do nicho e franquia
vencem qualquer site; depois vem a falta de site; depois o que o site e.
"""

import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from discoveryleads.core.normalizacao import dominio_casa, dominio_de, telefone_e164
from discoveryleads.core.sinais import Signal

# Status que prova site fora do ar para o cliente do lead, alem de todo 5xx.
# 401, 403 e 429 ficam de fora: e o servidor recusando o coletor.
STATUS_DE_QUEBRA = frozenset({402, 404, 410})

CONSTRUTORES = frozenset({"wix", "wordpress", "shopify", "loja_integrada"})

STATUS_DO_GOOGLE = {
    "CLOSED_TEMPORARILY": "fechado temporariamente",
    "CLOSED_PERMANENTLY": "fechado de vez",
    "FUTURE_OPENING": "ainda não inaugurado",
}


class Categoria(str, Enum):
    # elegiveis — secao 6.1, mais SUBDOMINIO_GRATIS (decisao de 2026-09-11)
    SEM_SITE = "SEM_SITE"
    CANVA = "CANVA"
    AGREGADOR = "AGREGADOR"
    GOOGLE_SITES_EXTINTO = "GOOGLE_SITES_EXTINTO"
    SITE_QUEBRADO = "SITE_QUEBRADO"
    SUBDOMINIO_GRATIS = "SUBDOMINIO_GRATIS"
    # inelegiveis
    TEM_SITE_PROPRIO = "TEM_SITE_PROPRIO"
    FECHADO = "FECHADO"
    REDE_FRANQUIA = "REDE_FRANQUIA"
    FORA_DO_ICP = "FORA_DO_ICP"
    # o site nao foi lido e o dominio nao diz o que e
    INDETERMINADO = "INDETERMINADO"


ELEGIVEIS = frozenset(
    {
        Categoria.SEM_SITE,
        Categoria.CANVA,
        Categoria.AGREGADOR,
        Categoria.GOOGLE_SITES_EXTINTO,
        Categoria.SITE_QUEBRADO,
        Categoria.SUBDOMINIO_GRATIS,
    }
)


@dataclass(frozen=True)
class Elegibilidade:
    categoria: Categoria
    motivo: str
    evidencia: tuple[Signal, ...]

    @property
    def elegivel(self) -> bool:
        return self.categoria in ELEGIVEIS


def _valor(sinais: dict[str, Signal], tipo: str) -> object:
    sinal = sinais.get(tipo)
    return sinal.valor if sinal is not None else None


def _presentes(sinais: dict[str, Signal], *tipos: str) -> tuple[Signal, ...]:
    return tuple(sinais[tipo] for tipo in tipos if tipo in sinais)


def _endereco_curto(url: str) -> str:
    """"https://www.linktr.ee/Fascino/" -> "linktr.ee/Fascino"."""
    return url.split("://", 1)[-1].removeprefix("www.").rstrip("/")


def _e_quebra(status: object) -> bool:
    return isinstance(status, int) and (status in STATUS_DE_QUEBRA or status >= 500)


def _motivo_da_quebra(endereco: str, falha: object, status: object, https_valido: object) -> str:
    if falha == "dominio_nao_resolve":
        return f"elegível — o site {endereco} não existe mais (domínio não resolve)"
    if https_valido is False and status is None:
        return f"elegível — o site {endereco} tem certificado de segurança inválido"
    if status is not None:
        return f"elegível — o site {endereco} responde {status}"
    return f"elegível — o site {endereco} está fora do ar"


def avaliar_elegibilidade(
    sinais: dict[str, Signal],
    *,
    tipos_excluir: Iterable[str] = (),
    franquia: str | None = None,
    subdominios_gratis: Iterable[str] = (),
) -> Elegibilidade:
    status_google = _valor(sinais, "places.status")
    if status_google is not None and status_google != "OPERATIONAL":
        descricao = STATUS_DO_GOOGLE.get(status_google, status_google)
        return Elegibilidade(
            Categoria.FECHADO,
            f"inelegível — o Google marca o negócio como {descricao}",
            _presentes(sinais, "places.status"),
        )

    fora = sorted(set(_valor(sinais, "places.tipos") or ()) & set(tipos_excluir))
    if fora:
        return Elegibilidade(
            Categoria.FORA_DO_ICP,
            f"inelegível — tipo fora do nicho ({', '.join(fora)})",
            _presentes(sinais, "places.tipos"),
        )

    if franquia is not None:
        return Elegibilidade(
            Categoria.REDE_FRANQUIA,
            f"inelegível — rede ou franquia: {franquia}",
            _presentes(sinais, "places.telefone"),
        )

    if _valor(sinais, "places.sem_site") is True:
        return Elegibilidade(
            Categoria.SEM_SITE,
            "elegível — não tem site no Google",
            _presentes(sinais, "places.sem_site"),
        )

    url = _valor(sinais, "site.url_final") or _valor(sinais, "places.website_uri") or ""
    if not url:
        return Elegibilidade(
            Categoria.INDETERMINADO, "indeterminado — sem dados de site nem do Google", ()
        )

    endereco = _endereco_curto(url)
    dominio = dominio_de(url)
    plataforma = _valor(sinais, "site.plataforma")
    status = _valor(sinais, "site.http_status")
    falha = _valor(sinais, "collector.site_fetcher.failed")

    if plataforma is None:
        return Elegibilidade(
            Categoria.INDETERMINADO,
            f"indeterminado — o site {endereco} não pôde ser lido ({falha or 'sem resposta'})",
            _presentes(sinais, "collector.site_fetcher.failed"),
        )
    if plataforma == "google_sites_extinto":
        return Elegibilidade(
            Categoria.GOOGLE_SITES_EXTINTO,
            f"elegível — o site era do Google Sites, encerrado em 2024 ({endereco})",
            _presentes(sinais, "site.plataforma"),
        )
    if plataforma == "canva":
        return Elegibilidade(
            Categoria.CANVA,
            f"elegível — a página está em {endereco}, feita no Canva",
            _presentes(sinais, "site.plataforma"),
        )
    if plataforma == "agregador":
        return Elegibilidade(
            Categoria.AGREGADOR,
            f"elegível — o site é um agregador de links ({endereco})",
            _presentes(sinais, "site.plataforma"),
        )
    if plataforma == "quebrado":
        return Elegibilidade(
            Categoria.SITE_QUEBRADO,
            _motivo_da_quebra(endereco, falha, status, _valor(sinais, "site.https_valido")),
            _presentes(
                sinais,
                "site.plataforma",
                "site.http_status",
                "collector.site_fetcher.failed",
                "site.https_valido",
            ),
        )

    # Construtor ou site proprio. Status de erro so torna elegivel (decisao 4).
    if _e_quebra(status):
        return Elegibilidade(
            Categoria.SITE_QUEBRADO,
            f"elegível — o site {endereco} ({plataforma}) responde {status}",
            _presentes(sinais, "site.plataforma", "site.http_status"),
        )
    if plataforma in CONSTRUTORES and any(dominio_casa(dominio, d) for d in subdominios_gratis):
        return Elegibilidade(
            Categoria.SUBDOMINIO_GRATIS,
            f"elegível — o site está no subdomínio grátis {dominio} ({plataforma})",
            _presentes(sinais, "site.plataforma", "site.url_final"),
        )
    return Elegibilidade(
        Categoria.TEM_SITE_PROPRIO,
        f"inelegível — tem site próprio em {dominio} ({plataforma})",
        _presentes(sinais, "site.plataforma", "site.http_status"),
    )


def _nome_normalizado(nome: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.casefold().split())


def identificar_franquias(
    lugares: Iterable[tuple[str, str, str | None]], minimo: int
) -> dict[str, str]:
    """`place_id -> descricao` de quem divide telefone ou nome com pelo menos
    `minimo` place_id da mesma busca (secao 6.1, REDE_FRANQUIA)."""
    por_telefone: dict[str, list[str]] = defaultdict(list)
    por_nome: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for place_id, nome, telefone in lugares:
        e164 = telefone_e164(telefone)
        if e164:
            por_telefone[e164].append(place_id)
        chave = _nome_normalizado(nome)
        if chave:
            por_nome[chave].append((place_id, nome))

    resultado: dict[str, str] = {}
    for e164, ids in por_telefone.items():
        if len(ids) >= minimo:
            for place_id in ids:
                resultado.setdefault(
                    place_id, f"o telefone {e164} aparece em {len(ids)} unidades da busca"
                )
    for itens in por_nome.values():
        if len(itens) >= minimo:
            exibido = itens[0][1]
            for place_id, _ in itens:
                resultado.setdefault(
                    place_id, f'o nome "{exibido}" aparece em {len(itens)} unidades da busca'
                )
    return resultado
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: todos passam.

- [ ] **Step 6: Commit**

```bash
git add config/scoring.toml config/nichos.toml src/discoveryleads/scoring tests/scoring
git commit -m "Peca 3: elegibilidade com motivo e evidencia, sobre sinais das fixtures reais"
```

### Task 9: Faixas T0–T3 e ordem da lista

Peça 3, segunda metade. Seção 6.2 mais as decisões 2, 6, 7, 8 e 9. Faixa é discreta, nunca soma de pesos. A faixa devolve também os sinais que a justificam, porque T0 é a promessa mais forte da lista e precisa aparecer na coluna `evidencia`.

**Files:**
- Create: `src/discoveryleads/scoring/faixas.py`, `tests/scoring/test_faixas.py`

**Interfaces:**
- Consumes: `Categoria`, `Elegibilidade` (Task 8), `Signal`.
- Produces:
  - `calcular_faixa(elegibilidade: Elegibilidade, sinais: dict[str, Signal], *, rastreamento_pago: Iterable[str], demanda_min_avaliacoes: int) -> tuple[str | None, tuple[Signal, ...]]` — `("T0", sinais do pixel)`, `("T1", ())`, `("T2", (avaliações, whatsapp))`, `("T3", ())` ou `(None, ())` para quem não é elegível.
  - `chave_de_ordenacao(faixa: str | None, elegibilidade: Elegibilidade, avaliacoes: int) -> tuple[int, int]` — T0, T1, T2, T3, depois `INDETERMINADO`, depois inelegíveis; dentro de cada grupo, mais avaliações primeiro.

- [ ] **Step 1: Escrever os testes** — criar `tests/scoring/test_faixas.py`:

```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest tests/scoring/test_faixas.py -q`
Expected: `ModuleNotFoundError: No module named 'discoveryleads.scoring.faixas'`.

- [ ] **Step 3: Implementar** — criar `src/discoveryleads/scoring/faixas.py`:

```python
"""Faixa de prioridade — o ranking da secao 6.2. Faixas discretas, nao soma.

A faixa decide a ordem. Dentro dela, nesta fatia, mais avaliacoes primeiro: o
`valor` da secao 6.3 ainda nao existe.
"""

from collections.abc import Iterable

from discoveryleads.core.sinais import Signal
from discoveryleads.scoring.elegibilidade import Categoria, Elegibilidade

# "Ja foi convencido de que precisa de presenca digital e escolheu a solucao
# pobre" (secao 6.2) — mais SITE_QUEBRADO e SUBDOMINIO_GRATIS (decisoes de
# 2026-09-11).
SUBSTITUTO_IMPROVISADO = frozenset(
    {
        Categoria.CANVA,
        Categoria.AGREGADOR,
        Categoria.GOOGLE_SITES_EXTINTO,
        Categoria.SITE_QUEBRADO,
        Categoria.SUBDOMINIO_GRATIS,
    }
)

ORDEM_DAS_FAIXAS = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}
GRUPO_INDETERMINADO = 4  # vale conferir a mao
GRUPO_INELEGIVEL = 5     # fica no CSV para a E4 enxergar falso negativo


def calcular_faixa(
    elegibilidade: Elegibilidade,
    sinais: dict[str, Signal],
    *,
    rastreamento_pago: Iterable[str],
    demanda_min_avaliacoes: int,
) -> tuple[str | None, tuple[Signal, ...]]:
    """Devolve a faixa e os sinais que a justificam. Inelegivel nao tem faixa."""
    if not elegibilidade.elegivel:
        return None, ()

    pagos = tuple(
        sinais[f"tracking.{nome}"]
        for nome in rastreamento_pago
        if f"tracking.{nome}" in sinais and sinais[f"tracking.{nome}"].valor is True
    )
    if pagos:
        return "T0", pagos

    if elegibilidade.categoria in SUBSTITUTO_IMPROVISADO:
        return "T1", ()

    # SEM_SITE. Intencao comercial e bio do Instagram (fora desta fatia) ou
    # WhatsApp no site — e quem nao tem site nao tem nenhum dos dois (decisao 6).
    avaliacoes = sinais.get("places.avaliacoes_total")
    whatsapp = sinais.get("site.whatsapp_link")
    demanda = avaliacoes is not None and (avaliacoes.valor or 0) >= demanda_min_avaliacoes
    intencao = whatsapp is not None and bool(whatsapp.valor)
    if demanda and intencao:
        return "T2", (avaliacoes, whatsapp)
    return "T3", ()


def chave_de_ordenacao(
    faixa: str | None, elegibilidade: Elegibilidade, avaliacoes: int
) -> tuple[int, int]:
    if faixa is not None:
        grupo = ORDEM_DAS_FAIXAS[faixa]
    elif elegibilidade.categoria is Categoria.INDETERMINADO:
        grupo = GRUPO_INDETERMINADO
    else:
        grupo = GRUPO_INELEGIVEL
    return (grupo, -avaliacoes)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add src/discoveryleads/scoring/faixas.py tests/scoring/test_faixas.py
git commit -m "Peca 3: faixas T0-T3 com evidencia do T0 e ordem da lista"
```

### Task 10: Export CSV com as regras de tela

Peça 4. Implementa coluna a coluna a emenda de 2026-09-11 do plano da fatia: até a E7 existir, o CSV é o único lugar onde o operador vê os leads, então as regras de tela da spec valem aqui.

O link do Maps segue o formato documentado das Maps URLs (conferido em 2026-09-11): `https://www.google.com/maps/search/?api=1&query=<nome>&query_place_id=<id>`. O `query` é obrigatório; com os dois, o Google usa o `place_id`. É link montado por nós a partir do `place_id` — nenhum conteúdo do Google é guardado para isso.

**Files:**
- Create: `src/discoveryleads/export/__init__.py`, `src/discoveryleads/export/csv_leads.py`, `tests/export/__init__.py`, `tests/export/test_csv_leads.py`

**Interfaces:**
- Consumes: `Signal`, `Elegibilidade` (Task 8), `telefone_e164` (Task 4), `SINAIS_DE_RASTREAMENTO` (Task 3).
- Produces:
  - `COLUNAS = ("nome", "telefone", "endereco", "faixa", "elegibilidade", "motivo", "evidencia", "limites", "plataforma", "url", "rastreamento", "avaliacoes", "nota", "maps", "whatsapp_link", "whatsapp_origem")`
  - `formatar_evidencia(sinal: Signal, fuso: tzinfo | None = None) -> str` — `fuso=None` usa o fuso da máquina.
  - `linha_csv(*, nome, endereco, place_id, sinais: dict[str, Signal], elegibilidade: Elegibilidade, faixa: str | None, evidencia_da_faixa: tuple[Signal, ...] = (), fuso: tzinfo | None = None) -> dict[str, str]`
  - `escrever_csv(linhas: list[dict[str, str]], caminho: Path) -> None`

- [ ] **Step 1: Escrever os testes** — criar `tests/export/__init__.py` vazio e `tests/export/test_csv_leads.py`:

```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest tests/export -q`
Expected: `ModuleNotFoundError: No module named 'discoveryleads.export'`.

- [ ] **Step 3: Implementar** — criar `src/discoveryleads/export/__init__.py` vazio e `src/discoveryleads/export/csv_leads.py`:

```python
"""Export CSV — peca 4, com as regras de tela da emenda de 2026-09-11.

Ate a E7 existir o CSV e o unico lugar onde o operador ve os leads, entao cada
coluna carrega uma regra que a spec pos na tela: motivo em frase, evidencia com
coletor e momento, limites que nunca somem, rastreamento que nunca fica vazio
nem afirma que o negocio "nao anuncia".

Formato: separador `;` e UTF-8 com BOM, o que o Excel em portugues abre com
acentos e colunas certas por clique duplo.
"""

import csv
from datetime import datetime, tzinfo
from pathlib import Path
from urllib.parse import quote

from discoveryleads.collectors.site_analise import SINAIS_DE_RASTREAMENTO
from discoveryleads.core.normalizacao import telefone_e164
from discoveryleads.core.sinais import Signal
from discoveryleads.scoring.elegibilidade import Elegibilidade

COLUNAS = (
    "nome",
    "telefone",
    "endereco",
    "faixa",
    "elegibilidade",
    "motivo",
    "evidencia",
    "limites",
    "plataforma",
    "url",
    "rastreamento",
    "avaliacoes",
    "nota",
    "maps",
    "whatsapp_link",
    "whatsapp_origem",
)


def _valor(sinais: dict[str, Signal], tipo: str) -> object:
    sinal = sinais.get(tipo)
    return sinal.valor if sinal is not None else None


def _valor_legivel(valor: object) -> str:
    if valor is None:
        return "nulo"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, list):
        return ",".join(str(item) for item in valor)
    return str(valor)


def formatar_evidencia(sinal: Signal, fuso: tzinfo | None = None) -> str:
    """`site.plataforma=canva · site_classifier · 2026-09-11 11:02`, na hora local."""
    momento = datetime.fromisoformat(sinal.observado_em).astimezone(fuso)
    return f"{sinal.tipo}={_valor_legivel(sinal.valor)} · {sinal.coletor} · {momento:%Y-%m-%d %H:%M}"


def _limites(sinais: dict[str, Signal]) -> str:
    """O que a linha nao sabe. Falha de coletor entra aqui e nunca some."""
    partes = []
    falha = _valor(sinais, "collector.site_fetcher.failed")
    if falha:
        texto = f"site: {falha}"
        status = _valor(sinais, "site.http_status")
        if status is not None:
            texto += f" ({status})"
        plataforma = _valor(sinais, "site.plataforma")
        if plataforma is None:
            texto += ", plataforma desconhecida"
        elif plataforma != "quebrado":
            texto += ", plataforma pelo domínio"
        partes.append(texto)
    falha_de_leitura = _valor(sinais, "collector.site_classifier.failed")
    if falha_de_leitura:
        partes.append(f"leitura do HTML: {falha_de_leitura}")
    return "; ".join(partes)


def _rastreamento(sinais: dict[str, Signal]) -> str:
    if _valor(sinais, "places.sem_site") is True:
        return "sem site"
    if not any(f"tracking.{nome}" in sinais for nome in SINAIS_DE_RASTREAMENTO):
        falha = _valor(sinais, "collector.site_fetcher.failed")
        return f"site não lido ({falha})" if falha else "site não lido"

    achados = []
    for nome in SINAIS_DE_RASTREAMENTO:
        if _valor(sinais, f"tracking.{nome}") is not True:
            continue
        if nome == "meta_pixel" and not _valor(sinais, "tracking.eventos_conversao"):
            achados.append("meta_pixel sem evento de conversão")
        else:
            achados.append(nome)
    # Nao achar no HTML sem JavaScript nao prova ausencia de anuncio.
    return ", ".join(achados) if achados else "nenhum visível no HTML cru"


def _whatsapp(sinais: dict[str, Signal]) -> tuple[str, str]:
    do_site = _valor(sinais, "site.whatsapp_link")
    if do_site:
        return str(do_site), "site"
    e164 = telefone_e164(_valor(sinais, "places.telefone"))
    if e164 and _valor(sinais, "telefone.e_movel") is True:
        return f"https://wa.me/{e164.removeprefix('+')}", "telefone do Places, móvel inferido"
    return "", ""


def _numero(valor: object) -> str:
    return "" if valor is None else str(valor).replace(".", ",")


def _link_do_maps(nome: str, place_id: str) -> str:
    return (
        "https://www.google.com/maps/search/?api=1"
        f"&query={quote(nome)}&query_place_id={quote(place_id)}"
    )


def linha_csv(
    *,
    nome: str,
    endereco: str | None,
    place_id: str,
    sinais: dict[str, Signal],
    elegibilidade: Elegibilidade,
    faixa: str | None,
    evidencia_da_faixa: tuple[Signal, ...] = (),
    fuso: tzinfo | None = None,
) -> dict[str, str]:
    whatsapp_link, whatsapp_origem = _whatsapp(sinais)
    evidencias = elegibilidade.evidencia + evidencia_da_faixa
    return {
        "nome": nome,
        "telefone": str(_valor(sinais, "places.telefone") or ""),
        "endereco": endereco or "",
        "faixa": faixa or "",
        "elegibilidade": elegibilidade.categoria.value,
        "motivo": elegibilidade.motivo,
        "evidencia": " | ".join(formatar_evidencia(sinal, fuso) for sinal in evidencias),
        "limites": _limites(sinais),
        "plataforma": str(_valor(sinais, "site.plataforma") or "desconhecida"),
        "url": str(_valor(sinais, "site.url_final") or _valor(sinais, "places.website_uri") or ""),
        "rastreamento": _rastreamento(sinais),
        "avaliacoes": str(_valor(sinais, "places.avaliacoes_total") or 0),
        "nota": _numero(_valor(sinais, "places.nota")),
        "maps": _link_do_maps(nome, place_id),
        "whatsapp_link": whatsapp_link,
        "whatsapp_origem": whatsapp_origem,
    }


def escrever_csv(linhas: list[dict[str, str]], caminho: Path) -> None:
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=COLUNAS, delimiter=";")
        escritor.writeheader()
        escritor.writerows(linhas)
```

- [ ] **Step 4: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add src/discoveryleads/export tests/export
git commit -m "Peca 4: CSV com motivo, evidencia, limites e origem do WhatsApp"
```

### Task 11: `python -m discoveryleads buscar` — ligando as quatro peças

O entregável da fatia. Execução sequencial, com `asyncio.gather` limitado só na análise dos sites (substituição tática da fila `jobs`). O teste de ponta a ponta injeta um Places falso e um analisador que devolve o HTML das fixtures reais: sem rede, mas com o classificador de verdade.

**Files:**
- Create: `src/discoveryleads/buscar.py`, `src/discoveryleads/__main__.py`, `tests/test_buscar.py`

**Interfaces:**
- Consumes: tudo das Tasks 3 a 10.
- Produces:
  - `Relatorio(chamadas_usadas, teto, teto_atingido, total, por_faixa: dict[str, int], indeterminados, inelegiveis, motivo_falha, detalhe, saida: Path | None, aviso_nicho: str | None)` — `saida` é `None` quando nenhum CSV foi gravado.
  - `async executar_busca(*, nicho, cidade, raio_m, max_chamadas, saida: Path, banco: Path, chave: str, descobrir_lugares=descobrir, analisar=analisar_site, paralelismo=8, fuso=None) -> Relatorio`
  - `formatar_relatorio(relatorio: Relatorio) -> str`
  - `__main__.main(argv: list[str] | None = None) -> int` — 0 com CSV gravado, 1 sem lead, 2 sem chave ou argumento inválido.

- [ ] **Step 1: Escrever os testes** — criar `tests/test_buscar.py`:

```python
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
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `.venv/Scripts/python.exe -m pytest tests/test_buscar.py -q`
Expected: `ImportError: cannot import name '__main__' from 'discoveryleads'` ou `ModuleNotFoundError: No module named 'discoveryleads.buscar'`.

- [ ] **Step 3: Implementar a orquestração** — criar `src/discoveryleads/buscar.py`:

```python
"""Liga as quatro pecas da Fatia Dia 1: descobre, analisa, grava, avalia, exporta.

Execucao sequencial, com `asyncio.gather` limitado so na analise dos sites —
substituicao tatica da fila `jobs` nesta fatia.

Os sinais vao para o SQLite (historico desde a primeira busca), mas o CSV sai
dos sinais DESTA execucao, para nao misturar observacao velha com nova.
"""

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from datetime import tzinfo
from pathlib import Path

from discoveryleads.collectors.places_discovery import Lugar, descobrir, sinais_do_lugar
from discoveryleads.collectors.site_analise import analisar_site
from discoveryleads.core.configuracao import carregar
from discoveryleads.core.falhas import MotivoDeFalha
from discoveryleads.core.normalizacao import telefone_e164
from discoveryleads.core.orcamento import Orcamento
from discoveryleads.core.sinais import Signal, agora_iso
from discoveryleads.db.repositorio import abrir, gravar_lead, registrar_sinais
from discoveryleads.export.csv_leads import escrever_csv, linha_csv
from discoveryleads.scoring.elegibilidade import (
    Categoria,
    avaliar_elegibilidade,
    identificar_franquias,
)
from discoveryleads.scoring.faixas import calcular_faixa, chave_de_ordenacao

PARALELISMO_DE_SITES = 8


@dataclass
class Relatorio:
    chamadas_usadas: int
    teto: int
    teto_atingido: bool
    total: int = 0
    por_faixa: dict[str, int] = field(default_factory=dict)
    indeterminados: int = 0
    inelegiveis: int = 0
    motivo_falha: MotivoDeFalha | None = None
    detalhe: str | None = None
    saida: Path | None = None
    aviso_nicho: str | None = None


def _plataforma_ausente(observado_em: str) -> Signal:
    """Lugar sem website no Places: `site.plataforma = ausente` (secao 5)."""
    return Signal(
        tipo="site.plataforma",
        valor="ausente",
        fonte="places",
        coletor="site_classifier",
        versao=1,
        observado_em=observado_em,
    )


async def executar_busca(
    *,
    nicho: str,
    cidade: str,
    raio_m: int,
    max_chamadas: int,
    saida: Path,
    banco: Path,
    chave: str,
    descobrir_lugares=descobrir,
    analisar=analisar_site,
    paralelismo: int = PARALELISMO_DE_SITES,
    fuso: tzinfo | None = None,
) -> Relatorio:
    orcamento = Orcamento(teto=max_chamadas)
    busca = await descobrir_lugares(nicho, cidade, raio_m, chave=chave, orcamento=orcamento)
    relatorio = Relatorio(
        chamadas_usadas=orcamento.usadas,
        teto=orcamento.teto,
        teto_atingido=busca.teto_atingido,
        motivo_falha=busca.motivo_falha,
        detalhe=busca.detalhe,
    )
    if not busca.lugares:
        return relatorio

    observado_em = agora_iso()
    sinais_por_lugar = {
        lugar.place_id: sinais_do_lugar(lugar, observado_em) for lugar in busca.lugares
    }

    semaforo = asyncio.Semaphore(paralelismo)

    async def sinais_do_site(lugar: Lugar) -> list[Signal]:
        if lugar.website is None:
            return [_plataforma_ausente(observado_em)]
        async with semaforo:
            return await analisar(lugar.website, observado_em=agora_iso())

    dos_sites = await asyncio.gather(*(sinais_do_site(lugar) for lugar in busca.lugares))
    for lugar, sinais in zip(busca.lugares, dos_sites):
        sinais_por_lugar[lugar.place_id] += sinais

    conexao = abrir(banco)
    try:
        for lugar in busca.lugares:
            lead_id = gravar_lead(
                conexao,
                place_id=lugar.place_id,
                nome=lugar.nome,
                endereco=lugar.endereco,
                cidade=cidade,
                lat=lugar.lat,
                lng=lugar.lng,
                telefone_e164=telefone_e164(lugar.telefone),
                agora=observado_em,
            )
            registrar_sinais(conexao, lead_id, sinais_por_lugar[lugar.place_id])
        conexao.commit()
    finally:
        conexao.close()

    regras = carregar("scoring.toml")
    definicao_do_nicho = carregar("nichos.toml").get(nicho)
    if definicao_do_nicho is None:
        relatorio.aviso_nicho = (
            f'o nicho "{nicho}" não está em config/nichos.toml: nenhum tipo foi excluído'
        )
    tipos_excluir = (definicao_do_nicho or {}).get("tipos_excluir", [])
    franquias = identificar_franquias(
        ((lugar.place_id, lugar.nome, lugar.telefone) for lugar in busca.lugares),
        minimo=regras["elegibilidade"]["franquia_min_ocorrencias"],
    )

    avaliados = []
    for lugar in busca.lugares:
        sinais = {sinal.tipo: sinal for sinal in sinais_por_lugar[lugar.place_id]}
        elegibilidade = avaliar_elegibilidade(
            sinais,
            tipos_excluir=tipos_excluir,
            franquia=franquias.get(lugar.place_id),
            subdominios_gratis=regras["elegibilidade"]["subdominios_gratis"],
        )
        faixa, evidencia_da_faixa = calcular_faixa(
            elegibilidade,
            sinais,
            rastreamento_pago=regras["faixas"]["rastreamento_pago"],
            demanda_min_avaliacoes=regras["faixas"]["demanda_min_avaliacoes"],
        )
        linha = linha_csv(
            nome=lugar.nome,
            endereco=lugar.endereco,
            place_id=lugar.place_id,
            sinais=sinais,
            elegibilidade=elegibilidade,
            faixa=faixa,
            evidencia_da_faixa=evidencia_da_faixa,
            fuso=fuso,
        )
        ordem = chave_de_ordenacao(faixa, elegibilidade, lugar.avaliacoes)
        avaliados.append((ordem, linha, faixa, elegibilidade))

    avaliados.sort(key=lambda item: item[0])  # estavel: empate mantem a ordem do Google
    escrever_csv([linha for _, linha, _, _ in avaliados], saida)

    relatorio.total = len(avaliados)
    relatorio.por_faixa = dict(Counter(faixa for _, _, faixa, _ in avaliados if faixa))
    relatorio.indeterminados = sum(
        1 for _, _, _, e in avaliados if e.categoria is Categoria.INDETERMINADO
    )
    relatorio.inelegiveis = sum(
        1
        for _, _, faixa, e in avaliados
        if faixa is None and e.categoria is not Categoria.INDETERMINADO
    )
    relatorio.saida = saida
    return relatorio


def formatar_relatorio(relatorio: Relatorio) -> str:
    linhas = [f"Chamadas pagas ao Places: {relatorio.chamadas_usadas} de {relatorio.teto}"]
    if relatorio.teto_atingido:
        linhas.append(
            "  atenção: o teto parou a busca antes do fim — aumente --max-chamadas para ver o resto"
        )
    if relatorio.motivo_falha is not None:
        texto = f"  falha do Google: {relatorio.motivo_falha.value}"
        if relatorio.detalhe:
            texto += f" — {relatorio.detalhe}"
        linhas.append(texto)
    if relatorio.aviso_nicho:
        linhas.append(f"  aviso: {relatorio.aviso_nicho}")
    if relatorio.saida is None:
        linhas.append("Nenhum lead encontrado; nenhum CSV gravado.")
        return "\n".join(linhas)

    faixas = "  ".join(f"{f}: {relatorio.por_faixa.get(f, 0)}" for f in ("T0", "T1", "T2", "T3"))
    linhas += [
        f"Leads: {relatorio.total}   {faixas}   indeterminados: {relatorio.indeterminados}"
        f"   inelegíveis: {relatorio.inelegiveis}",
        f"CSV: {relatorio.saida}",
    ]
    return "\n".join(linhas)
```

- [ ] **Step 4: Implementar a linha de comando** — criar `src/discoveryleads/__main__.py`:

```python
"""Linha de comando do DiscoveryLeads.

    python -m discoveryleads buscar --nicho "salão de beleza" --cidade "Goiânia"
        --raio 5000 --max-chamadas 40 --saida leads.csv
"""

import argparse
import asyncio
import sys
from pathlib import Path

from discoveryleads.buscar import executar_busca, formatar_relatorio
from discoveryleads.core.configuracao import RAIZ_DO_PROJETO, chave_google

BANCO_PADRAO = RAIZ_DO_PROJETO / "var" / "discoveryleads.db"
RAIO_MAXIMO_M = 50_000  # limite da Text Search (New)


def _inteiro_positivo(texto: str) -> int:
    try:
        numero = int(texto)
    except ValueError:
        raise argparse.ArgumentTypeError(f"precisa ser um número inteiro, não {texto!r}")
    if numero < 1:
        raise argparse.ArgumentTypeError("precisa ser pelo menos 1")
    return numero


def _raio(texto: str) -> int:
    numero = _inteiro_positivo(texto)
    if numero > RAIO_MAXIMO_M:
        raise argparse.ArgumentTypeError(f"o Google aceita no máximo {RAIO_MAXIMO_M} metros")
    return numero


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m discoveryleads",
        description="Encontra leads que precisam de uma landing page.",
    )
    comandos = parser.add_subparsers(dest="comando", required=True)
    buscar = comandos.add_parser(
        "buscar", help="busca no Google Places, analisa os sites e grava um CSV ordenado"
    )
    buscar.add_argument("--nicho", required=True, help='ex.: "salão de beleza"')
    buscar.add_argument("--cidade", required=True, help='cidade ou bairro, ex.: "Setor Bueno, Goiânia"')
    buscar.add_argument(
        "--raio", type=_raio, default=5000, help="raio em metros (padrão 5000, máximo 50000)"
    )
    buscar.add_argument(
        "--max-chamadas",
        dest="max_chamadas",
        type=_inteiro_positivo,
        required=True,
        help="teto de chamadas pagas ao Google — obrigatório",
    )
    buscar.add_argument(
        "--saida", type=Path, default=Path("leads.csv"), help="CSV de saída (padrão leads.csv)"
    )
    buscar.add_argument(
        "--banco", type=Path, default=BANCO_PADRAO, help="SQLite (padrão var/discoveryleads.db)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    chave = chave_google()
    if chave is None:
        print(
            "GOOGLE_API_KEY está vazia. Preencha no arquivo .env da raiz do projeto e rode de novo.",
            file=sys.stderr,
        )
        return 2
    relatorio = asyncio.run(
        executar_busca(
            nicho=args.nicho,
            cidade=args.cidade,
            raio_m=args.raio,
            max_chamadas=args.max_chamadas,
            saida=args.saida,
            banco=args.banco,
            chave=chave,
        )
    )
    print(formatar_relatorio(relatorio))
    return 0 if relatorio.saida is not None else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Rodar e ver passar**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: todos passam.

- [ ] **Step 6: Conferir a ajuda no terminal**

Run: `.venv/Scripts/python.exe -m discoveryleads buscar --help`
Expected: a ajuda lista `--nicho`, `--cidade`, `--raio`, `--max-chamadas`, `--saida`, `--banco`, com acentos legíveis.

- [ ] **Step 7: Commit**

```bash
git add src/discoveryleads/buscar.py src/discoveryleads/__main__.py tests/test_buscar.py
git commit -m "Fatia Dia 1: python -m discoveryleads buscar liga as quatro pecas"
```

### Task 12: Registrar as decisões e fazer a primeira busca real

Decisão que não fica escrita é reaberta na próxima sessão. Esta task grava as decisões nos documentos que as próximas sessões leem, e fecha com a **definição de pronto** da fatia, que só uma busca real verifica.

**Files:**
- Modify: `docs/superpowers/specs/2026-09-10-fatia-dia-1.md`, `docs/superpowers/specs/2026-09-10-spike-s4-e-armadilhas.md`, `CLAUDE.md`

- [ ] **Step 1: Emenda da peça 3 no plano da fatia** — em `docs/superpowers/specs/2026-09-10-fatia-dia-1.md`, logo depois do parágrafo que termina em "sem cálculo de valor nem de confiança ainda.", acrescentar:

```markdown
**Emenda de 2026-09-11 — decisões da peça 3.** Regras que a seção 6 da spec não
decidia, tomadas ao planejar as peças 2 a 4
(`docs/superpowers/plans/2026-09-11-fatia-dia-1-pecas-2-3-4.md`):

- **Construtor em subdomínio grátis é elegível** (`SUBDOMINIO_GRATIS`, T1):
  `*.wixsite.com`, `*.myshopify.com`, `*.lojaintegrada.com.br`. Com domínio
  próprio é `TEM_SITE_PROPRIO`. Vale o domínio final, depois dos redirects.
  Decisão do Saulo.
- **`SITE_QUEBRADO` entra em T1.** Decisão do Saulo.
- **Bloqueio não é quebra.** 401, 403 e 429 sem pista de plataforma viram
  `INDETERMINADO`, categoria nova, listada entre os elegíveis e os inelegíveis.
- **Status de erro só torna elegível, nunca inelegível.** Construtor que responde
  402, 404, 410 ou 5xx vira `SITE_QUEBRADO`.
- **T2 fica vazia até o Instagram (E5).** Sem site e sem bio não há como provar
  intenção comercial; todo `SEM_SITE` cai em T3.
- **Dentro da faixa, mais avaliações primeiro**, até o `valor` da seção 6.3 existir.
- **Field mask ganha `places.id`**, e o centro da busca custa uma chamada extra,
  contada no `--max-chamadas`.
- **Sinal novo `site.url_final`**, que decide o subdomínio grátis.
```

- [ ] **Step 2: Fechar as perguntas no spike** — em `docs/superpowers/specs/2026-09-10-spike-s4-e-armadilhas.md`, trocar a frase logo abaixo de `## Perguntas que ficam para a Peça 3 (elegibilidade)`:

de:
```markdown
Não são da Peça 1 — o classificador só emite sinal. Registradas para não se
perderem.
```
para:
```markdown
**Respondidas em 2026-09-11** — ver a emenda da peça 3 no plano da fatia.
Resumo: (1) construtor só é elegível em subdomínio grátis; (2) a loja suspensa
é `SITE_QUEBRADO`, porque status de erro só torna elegível; (3) a coluna
`rastreamento` do CSV diz "nenhum visível no HTML cru", nunca "não anuncia".
```

- [ ] **Step 3: Atualizar o `CLAUDE.md`** — na seção `## Estado atual`, trocar as linhas que começam em `- **Peça 1 da Fatia Dia 1 pronta e commitada**` até `(\`places_discovery\`) já pode andar — a chave existe.` por:

```markdown
- **Fatia Dia 1 completa**: as quatro peças e a linha de comando, com testes.
  Decisões da peça 3 na emenda de 2026-09-11 do plano da fatia.
- **Interface adiada** (2026-09-11): o operador recebe os leads pelo CSV até a
  E7. As regras de tela da spec valem no CSV.
- Próximo: olhar a primeira lista real (definição de pronto da fatia) e, se ela
  convencer, seguir para a E4 — o conjunto de referência rotulado à mão.

### Como rodar uma busca

    .venv\Scripts\python.exe -m discoveryleads buscar --nicho "salão de beleza" --cidade "Setor Bueno, Goiânia" --raio 2000 --max-chamadas 4 --saida leads.csv

`--max-chamadas` é obrigatório: cada requisição ao Google conta, e uma busca usa
no máximo 4 (o centro da região mais 3 páginas de 20). Os sinais ficam em
`var/discoveryleads.db`; o CSV sai com `;` e BOM para abrir no Excel.
```

- [ ] **Step 4: Rodar a suíte inteira**

Run: `.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: todos passam.

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-09-10-fatia-dia-1.md docs/superpowers/specs/2026-09-10-spike-s4-e-armadilhas.md CLAUDE.md
git commit -m "Registra as decisoes da peca 3 e como rodar a busca"
```

- [ ] **Step 6 (Saulo — gasta até 4 chamadas pagas): primeira busca real**

Run: `.venv/Scripts/python.exe -m discoveryleads buscar --nicho "salão de beleza" --cidade "Setor Bueno, Goiânia" --raio 2000 --max-chamadas 4 --saida leads.csv`
Expected: `Chamadas pagas ao Places: 4 de 4` (ou menos, se houver menos de 60 salões), a contagem por faixa, e `leads.csv` na raiz. **Definição de pronto:** abrir o CSV no Excel e reconhecer, nas dez primeiras linhas, leads que valem uma ligação. Se não reconhecer, o ajuste é na classificação ou nas faixas, antes da E4.

---

## Fora deste plano

- **Da peça 1, ainda pendentes:** `site.placeholder_detectado` e `site.cta_presente`. Nenhum dos dois entra no CSV desta fatia; voltam com o dossiê (E6).
- Tudo que o plano da fatia já põe fora: fila e workers, API, SSE, interface, ladrilhamento adaptativo, Alembic, identidade além do `place_id`, Instagram, PageSpeed, dossiê, confiança e valor.
- `cost_ledger` persistente: o teto desta fatia é um contador em memória, por execução.

## Riscos conhecidos

- **Google Ads (`AW-`), heatmap e TikTok Pixel não têm caso positivo real** nas fixtures. T0 por Google Ads nasce sem confirmação no mundo real.
- **Retenção de conteúdo do Google.** O banco e o CSV guardam nome, endereço, telefone e nota vindos do Places. A spec trata sinais como obra própria (seção 4.4). Se isso for questionado, o spike S3 volta a importar.
- **Custo.** Cada busca faz até 4 chamadas cobradas como Text Search Enterprise. O custo real sai da primeira busca, não de estimativa.
