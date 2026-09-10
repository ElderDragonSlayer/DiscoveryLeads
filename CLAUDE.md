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

## Estado atual (2026-09-10)

- Spec aprovada. **Nenhum código escrito ainda.**
- Trabalho imediato: `docs/superpowers/specs/2026-09-10-fatia-dia-1.md`

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

- [ ] **Chave da Places API (New)** no Google Cloud, com faturamento ativo.
      Bloqueia as peças 2, 3 e 4 da Fatia Dia 1. A peça 1 anda sem ela.

Fixtures do classificador **não dependem do Saulo**: a assinatura de plataforma
independe do nicho — uma página Canva de padaria tem a mesma impressão digital de
uma de salão. Qualquer página Canva/Linktree real serve, e podem ser obtidas sem
ajuda dele.

O que só o Saulo pode dar vem depois, na etapa E4: o **conjunto de referência
rotulado à mão** (~30 leads reais que ele classifica como valendo ou não uma
ligação). É a única fonte de verdade sobre a qualidade da lista, e nenhuma
heurística substitui o julgamento dele ali.

## Convenções

- Português no código, nos commits e nas conversas.
- Segredos em `.env` (já no `.gitignore`). Nunca commitar chave.
- Testes não tocam a rede. Testes com rede levam `@pytest.mark.live`.
