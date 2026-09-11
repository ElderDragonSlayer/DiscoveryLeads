# DiscoveryLeads

Ferramenta interna da **Vertex Solutions** para encontrar leads que precisam de uma
landing page. Uso local, operador único (Saulo). Responda em português.

## O negócio

A Vertex vende **páginas de vendas (landing pages)** sob demanda. Nesta primeira
temporada é só isso — site institucional, CRUD e hospedagem gerenciada estão fora,
por causa do custo de LGPD, infraestrutura e desenvolvimento.

O lead ideal é quem **já vende e já tenta vender online, mas com ferramenta errada**:
sem site, ou com página feita no Canva, ou com Linktree, ou com Google Sites extinto.

## Leitura obrigatória antes de mexer no código

`docs/superpowers/specs/2026-09-09-discoveryleads-backend-design.md` — o design
completo, 16 seções. Contém taxonomia de sinais, modelo de dados, regras de
pontuação e o dossiê de abordagem. **Não reprojete nada sem ler.**

## Estado atual (2026-09-11)

- Spec aprovada. Plano da fatia: `docs/superpowers/specs/2026-09-10-fatia-dia-1.md`
- **Fatia Dia 1 completa**: as quatro peças e a linha de comando, com testes.
  Decisões da peça 3 na emenda de 2026-09-11 do plano da fatia.
- **Interface adiada** (2026-09-11): o operador recebe os leads pelo CSV até a
  E7. As regras de tela da spec valem no CSV.
- **Primeira busca real feita** (2026-09-11, salão de beleza, Setor Bueno, 4
  chamadas): 60 leads. Revelou que um terço dos salões põe Instagram, WhatsApp
  (direto ou por bit.ly/w.app) ou Trinks no campo "site" do Google — virou
  `PERFIL_NO_LUGAR_DO_SITE`, T1. Código no branch `fatia-dia-1-pecas-2-3-4`,
  ainda fora da `main`.
- Próximo: o Saulo olhar a lista e, se ela convencer, seguir para a E4 — o
  conjunto de referência rotulado à mão.

### Como rodar uma busca

    .venv\Scripts\python.exe -m discoveryleads buscar --nicho "salão de beleza" --cidade "Setor Bueno, Goiânia" --raio 2000 --max-chamadas 4 --saida leads.csv

`--max-chamadas` é obrigatório: cada requisição ao Google conta, e uma busca usa
no máximo 4 (o centro da região mais 3 páginas de 20). Os sinais ficam em
`var/discoveryleads.db`; o CSV sai com `;` e BOM para abrir no Excel.

### Numa segunda máquina

O `.env`, o `.venv/`, o banco (`var/`) e os CSVs não vão para o git, de
propósito: chave, dependências da máquina e dados de terceiros. Numa máquina
nova: clonar, `git switch fatia-dia-1-pecas-2-3-4`, criar o venv com Python
3.13, `pip install -e ".[dev]"` e escrever o `.env` com a `GOOGLE_API_KEY`.

### Ambiente

Python 3.13 em `.venv/`. Não há `python` no PATH da máquina; use o do venv:

```
.venv\Scripts\python.exe -m pytest tests/ -q
```

### Leitura obrigatória antes de mexer no classificador

`docs/superpowers/specs/2026-09-10-spike-s4-e-armadilhas.md` — resposta do spike
S4 e as **seis armadilhas de falso positivo** medidas em HTML real. Cada uma tem
um teste que a trava. Não relaxe nenhuma dessas regras sem ler o porquê: três
delas invertem a faixa de prioridade do lead, e uma delas encheria o topo da
lista de leads sem verba.

As assinaturas de plataforma estão em `config/platforms.toml`, e **a ordem das
seções daquele arquivo é a ordem de precedência**.

O que cada fixture é, de onde veio e o que se espera dela está em
`tests/fixtures/sites/MANIFESTO.toml`, que é a tabela de casos do classificador.

## Decisões travadas (não reabrir sem motivo novo)

| Decisão | Valor |
|---|---|
| Linguagem | Python + FastAPI |
| Banco | SQLite (WAL), arquivo em `var/` |
| Fila | Tabela `jobs` + asyncio no processo. Sem Redis, sem Celery |
| Execução | Local, `127.0.0.1`, **sem autenticação** — operador único |
| Fontes | Google Places (New) + Instagram cruzados |
| Instagram | `og:description` grátis para seguidores/posts/bio; Apify **só** para o link da bio |
| Site | `site_classifier` próprio, local e grátis — é o diferencial do produto |
| PageSpeed | PageSpeed Insights API (grátis) como coletor de segundo estágio |
| Migrações | Alembic |

O detalhe do porquê de cada uma, e das alternativas descartadas, está na seção 2 da spec.

## Princípios que não se negociam

1. **Coletor nunca propaga exceção.** Falha vira sinal `collector.<nome>.failed`
   com motivo em **enum**, nunca string livre. Falha registrada é dado consultável.
2. **`signals` é append-only.** Nunca UPDATE, nunca DELETE. É daí que saem auditoria,
   histórico, detecção de mudança e conformidade LGPD.
3. **Nenhum argumento de venda sem sinal que o sustente.** O operador precisa poder
   ser checado na frente do cliente.
4. **Toda chamada paga tem teto.** Sem freio configurado, não roda.
5. Pesos e textos ficam em `config/*.toml`, fora do código — o operador calibra sozinho.

## Primeira busca real

Nicho **salão de beleza**, cidade **Goiânia**.

## Pendências do Saulo

- [x] **Chave da Places API (New)** — feita. Peças 2, 3 e 4 desbloqueadas.
- [ ] **Conjunto de referência rotulado à mão** (etapa E4): ~30 leads reais que
      ele classifica como valendo ou não uma ligação. É a única fonte de verdade
      sobre a qualidade da lista, e nenhuma heurística substitui o julgamento
      dele ali.

Fixtures do classificador **não dependem do Saulo** e já foram colhidas: treze
páginas reais em `tests/fixtures/sites/`. A assinatura de plataforma independe do
nicho — uma página Canva de padaria tem a mesma impressão digital de uma de salão.

## Convenções

- Português no código, nos commits e nas conversas.
- Segredos em `.env` (já no `.gitignore`). Nunca commitar chave.
- Testes não tocam a rede. Testes com rede levam `@pytest.mark.live`.
