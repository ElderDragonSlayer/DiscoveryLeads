# DiscoveryLeads — Design do Backend

**Data:** 2026-09-09
**Autor:** Saulo (Vertex Solutions) + Claude
**Status:** aprovado para plano de implementação

---

## 1. Contexto

A Vertex Solutions vende **páginas de vendas (landing pages)** sob demanda. Nesta
primeira temporada o produto é exclusivamente landing page — sites institucionais
completos, CRUDs elaborados e hospedagem gerenciada ficam fora, por causa do custo
de LGPD, infraestrutura e desenvolvimento de features que trariam.

O gargalo do negócio é **encontrar quem precisa de uma landing page e ainda não tem
uma**. Isso hoje é feito à mão, e à mão não escala.

O DiscoveryLeads é a ferramenta interna que resolve esse gargalo: descobre negócios
por nicho e região, cruza Google Places com Instagram e com a análise da própria
página do lead, e devolve uma lista **ordenada por probabilidade de fechar**, com a
evidência de cada decisão e um dossiê de abordagem pronto.

### Objetivo

Entregar listas de leads em que cada linha responde três perguntas sem que o
operador precise abrir nada:

1. **Por que este negócio precisa de uma landing page?** (elegibilidade, com motivo)
2. **Por que vale abordar este antes dos outros?** (valor, com ranking)
3. **O que eu digo quando ele objetar?** (dossiê de abordagem, com evidência)

### Não-objetivos

Explicitamente fora do escopo desta versão:

- Gestão de leads (status, notas, funil de vendas). A ferramenta encontra e exporta;
  o trabalho de venda acontece fora dela.
- Envio de mensagens, integração com WhatsApp Business API, e-mail ou CRM externo.
- Geração de texto por LLM. Todo dossiê de abordagem é montado por template.
- Multiusuário, autenticação, hospedagem. A ferramenta roda local, para um operador.

---

## 2. Decisões e justificativas

Registro das escolhas feitas no brainstorming, para que a revisão futura saiba o
que foi considerado e descartado.

| # | Decisão | Alternativas descartadas | Motivo |
|---|---|---|---|
| D1 | Fontes: Google Places + Instagram, cruzados | só Places; só Instagram | Places dá estrutura e alcance; Instagram dá a linguagem do negócio e o link da bio. Um sozinho não qualifica. |
| D2 | Modo híbrido: cache + coleta sob demanda | sob demanda pura; índice pré-coletado | Resposta imediata com o que já existe, completada em segundo plano. Evita pagar duas vezes pelo mesmo lead. |
| D3 | Escopo: busca + qualificação + export | mini-CRM; geração com IA; envio | YAGNI. O valor está na qualificação, não no acompanhamento. |
| D4 | Python + FastAPI | Node/TypeScript; Supabase | Melhor ferramental para parsing de HTML, normalização de telefone/endereço e dedupe por similaridade. |
| D5 | Execução local, `127.0.0.1`, operador único | LAN com token; costura para hospedagem futura | Decisão final do operador. Elimina auth, tenancy e deploy inteiros. |
| D6 | SQLite (WAL) + fila em tabela | PostgreSQL + Redis + Celery | Local e single-user. Banco é um arquivo; workers são I/O de rede, não CPU. Zero daemon. |
| D7 | Alembic desde o início | schema.sql fixo | A ferramenta será aperfeiçoada continuamente pelo próprio operador; o esquema vai mudar. |
| D8 | Sem FTS5 | FTS5 para palavras-chave | Casamento de palavra-chave roda em Python na pontuação, sobre poucos campos. Menos código. |
| D9 | Sinais append-only, nunca UPDATE | colunas mutáveis no lead | Dá auditoria, histórico, detecção de mudança e conformidade LGPD de graça. |
| D10 | Instagram: og:description grátis + Apify só para o link da bio | Apify para tudo; raspagem própria com login | O `og:description` entrega seguidores, posts e bio sem login. Apify fica restrito ao que vaza. Raspagem com login arrisca conta e IP residencial. |
| D11 | PageSpeed Insights API como coletor de segundo estágio | só verificações caseiras | Veredito oficial do Google é argumento sem contra-argumento. Grátis. Lento, logo seletivo. |
| D12 | Leads e sinais são globais; sem `owner_id` | escopo por dono | Operador único (D5). |

---

## 3. Arquitetura

```
Campanha (nicho + área + teto de custo)
   │
   ▼
[1] Ladrilhamento          área → células; célula saturada subdivide e re-enfileira
   │
   ▼
[2] Descoberta             Places por célula → upsert de leads + sinais básicos
   │
   ▼
[3] Coletores de sinal     ── fan-out paralelo, um job por (lead, coletor) ──
   │   ├─ site_classifier        (local, grátis)      plataforma + defeitos + contatos
   │   ├─ tracking_detector      (local, grátis)      Pixel / Ads / GA / GTM
   │   ├─ instagram_og           (local, grátis)      seguidores, posts, bio
   │   ├─ instagram_bio_link     (Apify, seletivo)    o link da bio
   │   ├─ dominio_rdap           (público, grátis)    idade do domínio
   │   └─ pagespeed              (Google, grátis)     Lighthouse + captura de tela
   │
   ▼
[4] Pontuação              elegibilidade + faixa + valor + confiança
   │
   ▼
[5] Dossiê de abordagem    objeção → contra-argumento com evidência
   │
   ▼
[6] Busca, diagnóstico e export
```

### Princípios estruturantes

**Coletor não levanta exceção para fora.** Toda falha vira um sinal
`collector.<nome>.failed` com motivo em enum. Falha registrada é dado consultável
em SQL; falha como exceção é log que ninguém lê.

**Descobrir é separado de provar.** O estágio 2 cria o lead visível e utilizável
imediatamente, com confiança baixa. Os coletores do estágio 3 rodam em paralelo e
independentes: nenhum bloqueia o outro, e a falha de qualquer um reduz a confiança
do lead sem travar a fila.

**A pontuação é reativa.** O pontuador roda quando chega sinal novo e recalcula.
Não é um estágio terminal do pipeline — é um observador da tabela de sinais.

**Fonte nova é aditiva.** Um coletor novo emite sinais novos; o pontuador consome
os sinais que existirem. Adicionar Facebook, iFood ou GetNinjas amanhã não toca
em nada do que já existe.

**Versão de coletor dispara reprocessamento.** A chave de job é
`(lead_id, coletor, versao)`. Subir a versão do `site_classifier` reprocessa os
leads antigos com a lógica nova, sem repetir a coleta paga do Places.

---

## 4. Modelo de dados

SQLite em modo WAL. Um arquivo, `discoveryleads.db`. Migrações via Alembic.

### 4.1 `leads` — o negócio canônico

```sql
CREATE TABLE leads (
    id              INTEGER PRIMARY KEY,
    nome            TEXT NOT NULL,
    endereco        TEXT,
    cidade          TEXT,
    uf              TEXT,
    lat             REAL,
    lng             REAL,
    telefone_e164   TEXT,
    categoria       TEXT,              -- primaryType do Places
    criado_em       TEXT NOT NULL,
    atualizado_em   TEXT NOT NULL
);
```

Campos denormalizados por conveniência de busca. A verdade sempre está em `signals`.

### 4.2 `lead_identities` — resolução de identidade

A tabela que impede lista duplicada. Duplicata destrói a confiança do operador na
ferramenta mais rápido que qualquer outro defeito.

```sql
CREATE TABLE lead_identities (
    tipo     TEXT NOT NULL,   -- place_id | phone_e164 | instagram_username | website_domain
    valor    TEXT NOT NULL,
    lead_id  INTEGER NOT NULL REFERENCES leads(id),
    PRIMARY KEY (tipo, valor)
);
```

Ao inserir um lead novo, procura-se por cada identidade conhecida. Se qualquer uma
já aponta para um lead existente, o registro converge nele em vez de criar outro.
O mesmo salão encontrado hoje pelo Places e amanhã pelo Instagram vira um só lead
porque o telefone normalizado bate.

Normalizações obrigatórias antes de gravar identidade:

- **telefone** para E.164 (`+5562999998888`), descartando formatação
- **domínio** para minúsculo, sem `www.`, sem porta, sem caminho
- **instagram_username** para minúsculo, sem arroba, sem query string

### 4.3 `signals` — append-only, o coração do sistema

```sql
CREATE TABLE signals (
    id           INTEGER PRIMARY KEY,
    lead_id      INTEGER NOT NULL REFERENCES leads(id),
    tipo         TEXT NOT NULL,        -- ver taxonomia, seção 5
    valor        TEXT,                 -- JSON
    fonte        TEXT NOT NULL,        -- places | site | instagram_og | apify | pagespeed | rdap
    coletor      TEXT NOT NULL,
    versao       INTEGER NOT NULL,
    confianca    REAL NOT NULL,        -- 0.0 a 1.0
    observado_em TEXT NOT NULL
);
CREATE INDEX ix_signals_lead_tipo ON signals(lead_id, tipo, observado_em DESC);
```

**Nunca sofre UPDATE nem DELETE.** A visão atual de um lead é a última observação
por `(lead_id, tipo)`, exposta como view `v_signals_atuais`.

Três coisas saem de graça dessa escolha:

- **Auditoria** — cada dado carrega origem, coletor e momento. É o que atende à
  exigência de rastreabilidade de origem sob a LGPD.
- **Histórico** — "tinha site em março, não tem mais".
- **Detecção de mudança** — "trocou Linktree por Canva há 12 dias", "ganhou 400
  seguidores em 60 dias". Quem mexeu na presença digital recentemente está pensando
  no assunto agora. É o gatilho de abordagem mais quente que existe, e vem de uma
  view sobre uma tabela que já existe.

### 4.4 `google_place_cache` — conteúdo bruto com prazo

```sql
CREATE TABLE google_place_cache (
    place_id      TEXT PRIMARY KEY,
    payload       TEXT NOT NULL,     -- JSON cru da resposta
    buscado_em    TEXT NOT NULL,
    expira_em     TEXT NOT NULL
);
```

Separada de propósito. Os Termos da Google Maps Platform restringem a retenção de
conteúdo do Places: o `place_id` pode ser guardado indefinidamente, os demais
campos não. Esta tabela pode ser **esvaziada por inteiro** sem perda: os sinais
derivados em `signals` são obra própria e sobrevivem. "O `place_id` X não tinha
site em 09/09/2026" é um fato do DiscoveryLeads, não conteúdo do Google.

Job de manutenção `purge_place_cache` roda no início de cada campanha.

> **Pendência de verificação (spike S3):** confirmar a redação vigente da cláusula
> de retenção e ajustar `expira_em`. É o tipo de termo que muda.

### 4.5 `snapshots` — HTML e imagens em disco

```sql
CREATE TABLE snapshots (
    id           INTEGER PRIMARY KEY,
    lead_id      INTEGER NOT NULL REFERENCES leads(id),
    tipo         TEXT NOT NULL,       -- html | screenshot_mobile
    caminho      TEXT NOT NULL,       -- relativo a var/snapshots/
    sha256       TEXT NOT NULL,
    capturado_em TEXT NOT NULL
);
```

O arquivo fica em disco, não no banco. Paga em quatro coisas:

1. **Prova** do que foi visto no momento da coleta.
2. **Reprocessamento** com um classificador melhor sem rebaixar nada da rede — é o
   que torna barato aperfeiçoar o `site_classifier` continuamente.
3. **Material de venda** — a captura de tela do PageSpeed vai direto para a proposta.
4. **Fixtures de teste que crescem sozinhas** conforme a ferramenta é usada.

Deduplicação por `sha256`: página que não mudou não gera arquivo novo.

### 4.6 Tabelas de apoio

```sql
CREATE TABLE niches (
    id                INTEGER PRIMARY KEY,
    nome              TEXT NOT NULL,
    versao            INTEGER NOT NULL DEFAULT 1,
    tipos_places      TEXT NOT NULL,   -- JSON array
    palavras_incluir  TEXT,            -- JSON array
    palavras_excluir  TEXT,            -- JSON array
    tipos_excluir     TEXT             -- JSON array, ICP negativo
);

CREATE TABLE campaigns (
    id            INTEGER PRIMARY KEY,
    niche_id      INTEGER NOT NULL REFERENCES niches(id),
    niche_versao  INTEGER NOT NULL,
    area          TEXT NOT NULL,       -- JSON: centro+raio ou polígono
    max_custo_brl REAL NOT NULL,
    estado        TEXT NOT NULL,       -- rascunho|rodando|pausada|concluida|estourou_orcamento
    criada_em     TEXT NOT NULL
);

CREATE TABLE campaign_leads (
    campaign_id INTEGER NOT NULL REFERENCES campaigns(id),
    lead_id     INTEGER NOT NULL REFERENCES leads(id),
    PRIMARY KEY (campaign_id, lead_id)
);

CREATE TABLE jobs (
    id           INTEGER PRIMARY KEY,
    chave        TEXT NOT NULL UNIQUE,   -- lead_id:coletor:versao, idempotência
    campaign_id  INTEGER REFERENCES campaigns(id),
    tipo         TEXT NOT NULL,
    payload      TEXT,
    estado       TEXT NOT NULL,          -- pendente|executando|ok|falhou|desistiu
    tentativas   INTEGER NOT NULL DEFAULT 0,
    proxima_em   TEXT,
    erro_motivo  TEXT,                   -- enum, ver 8.3
    criado_em    TEXT NOT NULL
);
CREATE INDEX ix_jobs_fila ON jobs(estado, proxima_em);

CREATE TABLE cost_ledger (
    id          INTEGER PRIMARY KEY,
    campaign_id INTEGER REFERENCES campaigns(id),
    coletor     TEXT NOT NULL,
    unidades    INTEGER NOT NULL DEFAULT 1,
    custo_brl   REAL NOT NULL,
    ocorrido_em TEXT NOT NULL
);
```

`niche_versao` gravada na campanha significa que um lead antigo sempre lembra com
qual definição de nicho foi encontrado — mudar o nicho não reescreve o passado.

`jobs.chave` única é o que garante idempotência: reexecutar o mesmo job não duplica
sinal nem debita custo duas vezes. É o mecanismo que protege a fatura.

---

## 5. Taxonomia de sinais

Namespace `fonte.nome`. Esta lista é o contrato entre coletores e pontuador.

### `places.*` — tudo vem na mesma resposta, custo zero adicional

| Sinal | Tipo | Uso |
|---|---|---|
| `places.website_uri` | string ou nulo | insumo do `site_classifier` |
| `places.sem_site` | bool | elegibilidade |
| `places.avaliacoes_total` | int | demanda comprovada |
| `places.nota` | float | qualidade percebida |
| `places.status` | enum | exclusão se fechado |
| `places.telefone` | string | contato |
| `places.tipos` | array | casamento de nicho |
| `places.price_level` | int ou nulo | proxy de capacidade de pagar |
| `places.tem_horarios` | bool | negócio operando |
| `places.fotos_total` | int | quanto cuida da própria presença |
| `places.reviews_texto` | array até 5 | dor documentada pelo cliente do lead |
| `places.avaliacoes_delta` | int | crescimento entre duas coletas |

`places.reviews_texto` merece nota: são até cinco avaliações em texto livre que já
vêm na resposta. Menções a "não achei o site", "como faço para agendar?", "não tem
preço em lugar nenhum" são a dor descrita pelo próprio cliente do lead — o argumento
de venda mais forte possível, porque não é opinião do vendedor.

### `site.*` — do HTML já baixado, custo zero

`site.plataforma` é o enum central do sistema, e assume exatamente um destes valores:

`canva` · `agregador` · `google_sites_extinto` · `wix` · `wordpress` · `shopify` ·
`loja_integrada` · `proprio` · `quebrado` · `ausente`

| Sinal | Tipo | Uso |
|---|---|---|
| `site.plataforma` | enum acima | **elegibilidade**, ver 6.1 |
| `site.http_status` | int | site quebrado |
| `site.redirects` | int | |
| `site.tempo_resposta_ms` | int | argumento de venda |
| `site.https_valido` | bool | argumento de venda |
| `site.viewport_presente` | bool | argumento de venda: não é responsivo |
| `site.title` | string ou nulo | argumento de venda: SEO |
| `site.meta_description` | string ou nulo | argumento de venda: SEO |
| `site.placeholder_detectado` | array | argumento: texto de exemplo do modelo |
| `site.whatsapp_link` | string ou nulo | **contato melhor que o do Places** |
| `site.email` | string ou nulo | contato |
| `site.links_sociais` | object | acha o Instagram sem gastar busca |
| `site.cta_presente` | bool | argumento: não há caminho até a venda |

### `tracking.*` — do mesmo HTML, custo zero, peso máximo

| Sinal | Assinatura procurada | Significado |
|---|---|---|
| `tracking.meta_pixel` | `fbq(`, `connect.facebook.net` | anuncia no Instagram/Facebook |
| `tracking.google_ads` | `gtag` com `AW-` | paga tráfego no Google |
| `tracking.google_analytics` | `gtag` com `G-` | mede, talvez não pague |
| `tracking.gtm` | `googletagmanager.com/gtm.js` | tem apoio técnico |
| `tracking.heatmap` | `hotjar`, `clarity.ms` | se importa com conversão |
| `tracking.tiktok_pixel` | `analytics.tiktok.com` | tráfego pago fora do eixo Meta |
| `tracking.eventos_conversao` | eventos `Purchase` / `Lead` | se ausente com Pixel presente: paga anúncio e não mede retorno |

### `instagram.*`

| Sinal | Fonte | Custo |
|---|---|---|
| `instagram.seguidores` | og:description | **grátis** |
| `instagram.seguindo` | og:description | **grátis** |
| `instagram.posts_total` | og:description | **grátis**, zero posts = conta morta |
| `instagram.bio_texto` | meta description | **grátis** |
| `instagram.bio_intencao_comercial` | derivado da bio | **grátis** |
| `instagram.link_bio` | Apify | pago, seletivo |
| `instagram.link_bio_plataforma` | derivado | — |

`instagram.bio_intencao_comercial` é a lista de gatilhos encontrados na bio: agende,
agendamento, encomendas, pedidos, orçamento, delivery, consulta, promoção, link
abaixo, compre, whatsapp. É o que separa quem tem uma **oferta** de quem só tem
presença.

### `pagespeed.*` — Lighthouse oficial do Google, grátis

| Sinal | Uso |
|---|---|
| `pagespeed.performance_mobile` | 0 a 100, **o argumento central** |
| `pagespeed.seo` | 0 a 100 |
| `pagespeed.acessibilidade` | 0 a 100 |
| `pagespeed.lcp_ms` | tempo até o conteúdo principal aparecer |
| `pagespeed.cls` | estabilidade visual |
| `pagespeed.oportunidades` | array de diagnósticos item a item |
| `pagespeed.screenshot` | referência ao snapshot da renderização em celular |

### `dominio.*` e `telefone.*`

| Sinal | Fonte | Uso |
|---|---|---|
| `dominio.idade_dias` | RDAP, público e grátis | já investiu em presença |
| `dominio.registrado_em` | RDAP | |
| `telefone.e_movel` | derivado do formato | inferência, **não fato verificado** |
| `telefone.ddd` | derivado | |

Sobre WhatsApp: não existe forma limpa e confiável de verificar se um número tem
conta. `telefone.e_movel` é derivado do nono dígito e do DDD — bom proxy no Brasil,
e rotulado como inferência na interface. `site.whatsapp_link` extraído do HTML,
esse sim, é fato.

### `collector.*`

`collector.<nome>.failed` com motivo no enum de 8.3. Falha é dado.

---

## 6. Pontuação

Deliberadamente **não** existe um número único. São quatro saídas separadas, porque
misturá-las destrói a explicabilidade que é o valor da ferramenta.

### 6.1 Elegibilidade — porta de entrada, com motivo

Derivada de `site.plataforma` e `places.sem_site`.

**Elegível:**

| Categoria | Condição |
|---|---|
| `SEM_SITE` | `places.sem_site` verdadeiro e nenhum site achado por outra via |
| `CANVA` | domínio `*.my.canva.site` ou assinatura do Canva no HTML |
| `AGREGADOR` | `linktr.ee`, `beacons.ai`, `bio.link`, `linkbio`, similares |
| `GOOGLE_SITES_EXTINTO` | domínio `*.negocio.site` ou `*.business.site` |
| `SITE_QUEBRADO` | não resolve DNS, 4xx/5xx, ou certificado inválido |

**Inelegível, com motivo:**

| Categoria | Condição |
|---|---|
| `TEM_SITE_PROPRIO` | domínio próprio, responde 200, e não é construtor de página única |
| `FECHADO` | `places.status` diferente de operacional |
| `REDE_FRANQUIA` | mesma identidade de telefone ou nome em muitos `place_id` |
| `FORA_DO_ICP` | tipo do Places na lista `tipos_excluir` do nicho |

O resultado nunca é um número. É uma frase: *"elegível — a página está em
anastudio.my.canva.site"*.

`FORA_DO_ICP` implementa a decisão de escopo desta temporada: quem precisa de site
institucional com várias páginas (escritório de advocacia, contabilidade, clínica
com convênios) não é cliente de landing page agora.

### 6.2 Faixa de prioridade — o ranking que importa

Faixas discretas, não soma de pesos. A faixa decide a ordem; o valor ordena dentro
dela.

| Faixa | Definição | Racional |
|---|---|---|
| **T0 — Tráfego pago sem destino** | elegível **e** qualquer sinal `tracking.*` pago presente | Está pagando por clique e não tem para onde mandar. Orçamento comprovado, oferta existente, funil furado. Não precisa ser convencido de nada. |
| **T1 — Substituto improvisado** | elegível por `CANVA`, `AGREGADOR` ou `GOOGLE_SITES_EXTINTO` | Já foi convencido de que precisa de presença digital e escolheu a solução pobre. Não há etapa de educação: só a demonstração de que dá para ser melhor. |
| **T2 — Sem nada, com demanda** | `SEM_SITE` **e** demanda comprovada **e** intenção comercial | Tem clientes e tem oferta, mas ainda não entrou no digital. Exige uma etapa de educação antes do preço. |
| **T3 — Sem nada, demanda fraca** | `SEM_SITE` e o resto ausente | Fundo de lista. |

O caso máximo é **Pixel dentro de uma página do Canva ou de um Linktree**: a pessoa
montou um substituto de landing page e instalou rastreamento nele. É o cliente da
Vertex, com o produto da Vertex mal feito, e com verba comprovada.

Demanda comprovada: `places.avaliacoes_total >= 20` **ou** `instagram.seguidores >= 1000`.
Intenção comercial: `instagram.bio_intencao_comercial` não vazio **ou**
`site.whatsapp_link` presente.

### 6.3 Valor — ordena dentro da faixa

Soma ponderada, com **todos os pesos em `config/scoring.toml`**, fora do código,
para calibração sem reprogramação.

| Componente | Insumo |
|---|---|
| Atividade | avaliação ou publicação nos últimos 90 dias |
| Volume | `places.avaliacoes_total`, `instagram.seguidores` |
| Crescimento | `places.avaliacoes_delta` positivo |
| Contato alcançável | `site.whatsapp_link` > `telefone.e_movel` > telefone fixo |
| Capacidade de pagar | `places.price_level`, `dominio.idade_dias`, presença de GTM |
| Cuidado com a presença | `places.fotos_total`, `places.nota` |

### 6.4 Confiança — quanto do quadro existe

Fração ponderada dos coletores que responderam com sucesso para aquele lead. Places
mais site mais Instagram é alta; só Places é baixa. **Aparece na interface**, para
que o operador saiba quando confiar na linha.

Invariante testável: remover um sinal nunca aumenta a confiança.

---

## 7. Dossiê de abordagem

O componente que transforma a lista em conversa de venda. Recebe os sinais de um
lead e devolve uma lista de pares **objeção → contra-argumento com evidência**.

Montado por template, sem LLM, sem custo. Todos os textos ficam em
`config/objecoes.toml`, editáveis sem tocar no código.

| Objeção provável | Contra-argumento, quando os sinais permitem |
|---|---|
| "Meu Instagram já basta" | "Você tem `{seguidores}` seguidores e nenhum link para comprar. O clique morre no perfil." |
| "Eu já tenho uma página" | "O Google dá `{performance_mobile}` de 100 para ela no celular. O relatório está aqui." |
| "Minha página está boa" | "Ela leva `{lcp_ms}` para abrir e não tem botão de WhatsApp. Não existe caminho da visita até a venda." |
| "Não tenho dinheiro para isso" | "Você já paga anúncio — o Pixel da Meta está instalado. O problema não é gastar, é para onde o clique vai." |
| "Não sei se traz retorno" | "Você tem Pixel mas nenhum evento de conversão configurado. Hoje você não consegue nem medir." |
| "Ninguém reclama" | "Nesta avaliação seu cliente escreveu: `{trecho_review}`." |
| "Aparece no Google normalmente" | "Sua página não tem título nem descrição. Para o Google, ela não tem assunto." |
| "Está tudo funcionando" | "Sua página ainda tem o texto de exemplo do modelo: `{placeholder}`." |
| "Não é para celular que vendo" | "Sua página não declara viewport — ela quebra justamente no celular, que é onde a maior parte dos seus clientes vai abrir." |

Regra: **um argumento só entra no dossiê se o sinal que o sustenta existe.** Nunca
se inventa objeção sem evidência. Um dossiê com dois argumentos verificáveis vale
mais que dez genéricos, e o operador precisa poder confiar que cada frase resiste a
ser checada na frente do cliente.

A captura de tela do PageSpeed acompanha o dossiê: a página do lead hoje, ao lado
da proposta.

---

## 8. Coleta e execução

### 8.1 Interface do coletor

```python
class SignalCollector(Protocol):
    name: str
    version: int
    custo_estimado_brl: float

    def applies_to(self, lead: Lead, sinais: Sinais) -> bool: ...
    async def collect(self, lead: Lead, sinais: Sinais) -> list[Signal]: ...
```

`applies_to` evita trabalho inútil: o `pagespeed` só se aplica a lead elegível com
página de pé; o `instagram_bio_link` só a lead elegível que já tem `@` resolvido.

**Nenhum coletor propaga exceção.** O executor captura, classifica no enum de
motivos e grava `collector.<nome>.failed`.

### 8.2 Ladrilhamento geográfico

Nearby Search devolve no máximo 20 resultados por chamada, 60 com paginação. Uma
cidade média tem mais negócios de um nicho que isso, então varrer exige ladrilhar.

Algoritmo:

1. A área da campanha vira uma grade de células com raio inicial configurável.
2. Cada célula gera um job de descoberta.
3. Célula que retorna o limite de resultados está **saturada**: subdivide em quatro
   e re-enfileira, até um raio mínimo.
4. Células abaixo do limite são finais.

Isso é densidade adaptativa: o centro da cidade vai fundo, a periferia para no
primeiro nível. Grade de tamanho fixo ou estoura a cota em área densa ou perde lead.

Testes geométricos exigidos: a união das células cobre a área sem buraco; área
minúscula não gera centenas de requisições; a subdivisão termina.

### 8.3 Fila, resiliência e motivos de falha

Fila é a tabela `jobs`. Claim atômico por `UPDATE ... WHERE estado='pendente'`
seguido de leitura, dentro de transação. Pool de corrotinas asyncio no mesmo
processo do FastAPI. SQLite em WAL, escritas curtas, um escritor serializado.

Quatro mecanismos, configuráveis por coletor:

- **Token bucket** de requisições por segundo.
- **Disjuntor**: N falhas seguidas desligam o coletor por alguns minutos. A campanha
  **não para** — segue com os outros, e os leads afetados ficam com confiança menor.
- **Retry** com backoff exponencial e jitter, teto de tentativas, depois `desistiu`
  e falha registrada.
- **Cache de negativa**: perfil ou domínio inexistente não é reconsultado por 30
  dias. Sem isso, paga-se repetidamente para descobrir a mesma ausência.

Enum de motivos de falha — **enum, nunca string livre**, porque enum é agrupável em
SQL e string livre vira log que ninguém lê:

`timeout` · `bloqueado` · `nao_encontrado` · `parse_falhou` · `cota_estourada` ·
`rede_indisponivel` · `resposta_invalida` · `dominio_nao_resolve`

### 8.4 Orçamento

Toda chamada paga debita uma linha em `cost_ledger`. A campanha carrega
`max_custo_brl`; ao atingir, entra em `estourou_orcamento`, para de enfileirar e
avisa. É o freio que impede uma varredura mal configurada de virar uma fatura ruim.

---

## 9. API HTTP

FastAPI em `127.0.0.1:8000`. Sem autenticação — operador único, máquina local.

| Grupo | Rotas |
|---|---|
| Nichos | `GET/POST/PUT /niches`, `GET /niches/{id}` |
| Campanhas | `POST /campaigns`, `POST /campaigns/{id}/pause`, `/resume`, `GET /campaigns/{id}` |
| Progresso | `GET /campaigns/{id}/progress` — células varridas, leads achados, custo gasto e restante |
| Funil | `GET /campaigns/{id}/funnel` — ver seção 10 |
| Leads | `GET /leads` com filtros: nicho, faixa, elegibilidade, confiança mínima, cidade, plataforma do site, tem WhatsApp, tem Pixel |
| Lead | `GET /leads/{id}` — dados, **linha do tempo de sinais**, dossiê de abordagem |
| Export | `POST /exports` (CSV/XLSX do filtro atual), `GET /exports/{id}` |
| Diagnóstico | `GET /diagnostics/collectors` |
| Eventos | `GET /events` — SSE |

**SSE e não WebSocket**: o fluxo é só servidor para cliente, e SSE reconecta sozinho
sem biblioteca no navegador. É o que faz a lista crescer na tela enquanto a campanha
roda, entregando a sensação de busca instantânea do modo híbrido.

A tela do lead individual é o produto: cada evidência, de onde veio e quando. É o que
transforma "confie em mim" em "olhe aqui".

### Export

Colunas: identificação, contato, elegibilidade e motivo, faixa, valor, confiança,
plataforma do site, notas do PageSpeed, sinais de rastreamento, **coluna de gancho**
e **deep links prontos** (`wa.me` com texto pré-preenchido, link do Maps, link do
perfil). Um clique a menos por lead, em centenas de leads.

---

## 10. Observabilidade

Requisito de primeira classe, não detalhe de infra.

**`GET /diagnostics/collectors`** — por coletor: taxa de sucesso, disjuntores
abertos, latência mediana, últimas falhas agrupadas por motivo.

**`GET /campaigns/{id}/funnel`** — o funil em números:

```
células varridas → leads brutos → dentro do nicho → elegíveis
   → com site analisado → com Instagram resolvido → T0/T1/T2/T3
```

É onde se enxerga **onde o lead está sendo perdido**. Se 60% morre em "Instagram
não resolvido", o problema é o coletor, não o nicho. Sem esse número, a conclusão
errada seria trocar de nicho.

**Custo por lead elegível** — `cost_ledger` dividido pelo funil. É a métrica de
negócio que diz se a campanha valeu, e é o número que decide onde gastar a reserva.

---

## 11. LGPD

A ferramenta armazena dados de contato de pessoas físicas (autônomos). A base legal
para prospecção B2B é o legítimo interesse, e ela exige três coisas que o desenho
já entrega:

1. **Rastreabilidade de origem** — `signals` grava fonte, coletor e momento de cada
   dado. Sempre é possível responder de onde veio.
2. **Retenção** — job `purge_expired` remove leads sem interação após período
   configurável, e o cache do Places por prazo próprio.
3. **Exclusão sob pedido** — `DELETE /leads/{id}` remove o lead, suas identidades,
   seus sinais e seus snapshots, e grava o `place_id` numa lista de bloqueio para
   que a próxima campanha não o recolha.

Só se coleta dado publicamente disponível e de natureza comercial. Nada de dado
sensível, nada de perfil pessoal privado.

---

## 12. Testes

**A rede nunca entra no ciclo normal.** Coletores são testados contra respostas
gravadas (`respx`). À parte, testes marcados `@pytest.mark.live` batem nas APIs de
verdade e rodam sob demanda — o canário que avisa quando o contrato de terceiro
mudou, sem travar o desenvolvimento quando a internet oscila.

Sete frentes, em ordem de importância:

1. **`site_classifier` com fixtures reais.** HTML de verdade em
   `tests/fixtures/sites/`: Canva, Linktree, Beacons, Wix, WordPress, Shopify,
   Google Sites extinto, site próprio bem-feito, domínio morto, redirecionamento
   triplo. Um arquivo, um caso. Aqui um falso positivo custa credibilidade direto
   na frente do cliente.

2. **Conjunto de referência rotulado à mão.** Cerca de 30 leads reais classificados
   pelo operador: elegível ou não, e por quê. Mede **falso positivo e falso negativo
   com número**. É o único jeito honesto de responder "essa lista é boa?", e é o
   artefato mais valioso do projeto. Roda como teste, com limiar mínimo de precisão.

3. **Pontuador em tabela de casos.** Sinais de entrada, faixa e valor de saída. Puro,
   sem I/O. Invariantes com Hypothesis: lead sem sinal nunca é elegível; remover um
   sinal nunca aumenta a confiança; T0 exige rastreamento pago presente.

4. **Resolução de identidade.** Mesmo telefone com grafias diferentes; "Studio Ana"
   contra "Studio Ana Nails"; mesmo arroba em dois `place_id`.

5. **Ladrilhamento.** Cobertura sem buraco; subdivisão termina; área pequena não
   explode em requisições.

6. **Idempotência da fila.** Rodar o mesmo job duas vezes não duplica sinal nem
   debita custo duas vezes. Este é o teste que protege a fatura.

7. **Rotas da API** com SQLite em memória.

Os snapshots capturados em uso viram fixtures: o conjunto de testes cresce sozinho
conforme a ferramenta roda.

---

## 13. Spikes obrigatórios antes de implementar

Quatro perguntas cuja resposta muda o código. Todas custam pouco e todas vêm antes
de escrever coletor.

| # | Pergunta | Decide |
|---|---|---|
| **S1** | O `og:description` do Instagram vem num `httpx` com User-Agent normal, ou só em navegador real? A partir de quantas requisições o IP residencial é bloqueado? | Se o coletor grátis funciona, e se o Apify continua restrito ao link da bio |
| **S2** | Qual a tabela de preços vigente do Places, e qual a faixa gratuita mensal por SKU? Sai mais barato pedir `websiteUri` e telefone na field mask da busca, ou fazer Place Details depois? | O custo real por campanha e o desenho do `places_discovery` |
| **S3** | Qual a redação vigente da cláusula de retenção de conteúdo da Google Maps Platform? | O prazo de `google_place_cache` |
| **S4** | Os domínios `*.negocio.site` e `*.business.site` ainda respondem, e como se apresentam hoje? | A regra de detecção de `GOOGLE_SITES_EXTINTO` |

Um spike opcional, de valor alto se der certo: a **Biblioteca de Anúncios da Meta**
é pública e mostra se um negócio anuncia agora. Se for consultável de forma estável,
confirma orçamento ativo sem depender de o Pixel estar visível. Vai como spike, não
como requisito, porque não há garantia de que seja acessível programaticamente.

**Primeira medição real:** rodar uma campanha pequena — um nicho, um bairro — e ler
o `cost_ledger`. O custo por lead elegível sai com número, não com estimativa.
Estimativa atual, a confirmar: R$ 110 a R$ 190 por cidade média e nicho, antes das
faixas gratuitas, que podem zerar a primeira campanha.

### 13.1 Ordem de construção sugerida

A spec descreve o sistema completo, mas ele não deve ser construído de uma vez. A
ordem abaixo entrega leads reais e utilizáveis o mais cedo possível, e deixa cada
etapa seguinte apoiada em algo que já funciona.

| Etapa | Entrega | Critério de pronto |
|---|---|---|
| **E0** | Spikes S1 a S4 | As quatro respostas escritas na spec |
| **E1** | Esqueleto: banco, migrações, fila, um coletor falso | Um job atravessa a fila de ponta a ponta e grava um sinal |
| **E2** | `places_discovery` + ladrilhamento + identidade + `cost_ledger` | Uma campanha real produz leads sem duplicata, com custo contabilizado |
| **E3** | `site_classifier` + `tracking_detector` + elegibilidade + faixas | **Primeira lista de verdade, já ordenada por T0–T3** |
| **E4** | Conjunto de referência rotulado + medição de precisão | Falso positivo e falso negativo com número |
| **E5** | `instagram_og` + `dominio_rdap` + valor + confiança | Ranking completo dentro de cada faixa |
| **E6** | `pagespeed` + dossiê de abordagem | Export com argumentos e captura de tela |
| **E7** | API de busca, SSE, diagnóstico, funil, export | Ferramenta fechada em si |
| **E8** | `instagram_bio_link` via Apify | Único item pago, e só se S1 mostrar que faz falta |

**E3 é o marco que importa.** Ali a ferramenta já vale mais que a planilha manual,
mesmo sem Instagram, sem PageSpeed e sem dossiê. Tudo depois disso é aumento de
precisão e de poder de argumentação sobre uma base que já entrega.

---

## 14. Riscos

| Risco | Impacto | Mitigação |
|---|---|---|
| Instagram bloqueia o IP residencial | Sem sinais de Instagram, e sem Instagram no celular de casa | Ritmo baixo, token bucket conservador, disjuntor. S1 mede o limite antes. Apify como caminho alternativo. |
| Preço do Places maior que o estimado | Campanhas inviáveis | S2 antes de qualquer código. Teto de custo por campanha. Field mask enxuta. |
| `site_classifier` com falso positivo | Credibilidade perdida na frente do cliente | Conjunto de referência rotulado com limiar de precisão, fixtures reais, versionamento do coletor para reprocessar. |
| Apify muda ou encarece | Sem link da bio | Já está atrás da interface `SignalCollector`. Os sinais grátis do og cobrem a maior parte do valor. |
| Duplicatas na lista | Operador para de confiar | `lead_identities` com normalização rigorosa e testes dedicados. |
| PageSpeed lento demais para o volume | Fila entope | Coletor de segundo estágio, só em lead elegível com página de pé, fila e ritmo próprios. |

---

## 15. Fora de escopo

Registrado para não voltar como surpresa.

**Nesta versão:** gestão de leads, envio de mensagens, geração de texto por LLM,
multiusuário, autenticação, hospedagem, sites institucionais.

**Fase 2, avaliados e adiados:**

- **Base de CNPJ da Receita Federal** como coletor offline. Dado aberto, download
  livre, ilimitado, sem custo em dinheiro. Traz data de abertura, capital social,
  CNAE e situação cadastral. Capital social é proxy de capacidade de pagar muito
  melhor que `price_level`. O custo é esforço: casar nome e endereço com o registro
  certo é fuzzy matching de verdade, e alguns gigabytes de disco.
- **OpenStreetMap via Overpass** como fonte complementar. Grátis, sem chave, e sem
  cláusula de retenção — o que entra por ali fica no banco para sempre. Cobertura de
  PME no Brasil é bem pior que a do Google, então é complemento, nunca substituto.
- Fontes adicionais: Facebook Pages, iFood, GetNinjas.

---

## 16. Estrutura do projeto

```
DiscoveryLeads/
├── src/discoveryleads/
│   ├── api/              rotas FastAPI, SSE, export
│   ├── collectors/       um módulo por coletor, todos sob SignalCollector
│   ├── core/             modelos, identidade, normalização
│   ├── scoring/          elegibilidade, faixa, valor, confiança
│   ├── pitch/            dossiê de abordagem
│   ├── geo/              ladrilhamento
│   ├── queue/            fila, disjuntor, retry, orçamento
│   └── db/               SQLAlchemy, migrações Alembic
├── config/
│   ├── scoring.toml      pesos, calibráveis sem tocar em código
│   ├── objecoes.toml     textos do dossiê
│   └── platforms.toml    assinaturas de plataforma e de rastreamento
├── tests/
│   ├── fixtures/sites/   HTML real, um arquivo por caso
│   └── referencia/       conjunto rotulado à mão
├── var/
│   ├── discoveryleads.db
│   └── snapshots/
└── docs/superpowers/specs/
```

Três arquivos de configuração fora do código porque são exatamente o que o operador
vai querer ajustar sozinho, com frequência, sem reprogramar nada.
