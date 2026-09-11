# Spike S4 + armadilhas encontradas ao montar as fixtures

**Data:** 2026-09-10
**Contexto:** Peça 1 da Fatia Dia 1 (`site_classifier` + `tracking_detector`)
**Método:** `curl` com User-Agent de navegador, sem JavaScript — exatamente o que o
coletor enxerga. 13 páginas reais, gravadas em `tests/fixtures/sites/`.

Este documento existe porque montar as fixtures antes de escrever o classificador
respondeu um spike e revelou seis armadilhas de falso positivo que não estavam
na spec. Nenhuma delas foi deduzida — todas apareceram no HTML de verdade, e três
delas eu só descobri porque errei primeiro.

---

## S4 — respondido

> **Pergunta:** os domínios `*.negocio.site` e `*.business.site` ainda respondem,
> e como se apresentam hoje?
> **Decide:** a regra de detecção de `GOOGLE_SITES_EXTINTO`.

### Medição

| URL | HTTP | Redirects | Destino final |
|---|---|---|---|
| `https://negocio.site/` | 200 | 3 | `business.google.com/br/business-profile/` |
| `https://business.site/` | 200 | 3 | `business.google.com/br/business-profile/` |
| `https://teste.negocio.site/` | **404** | 0 | — |
| `https://barbearia.business.site/` | **404** | 0 | — |

O corpo do 404 (gravado em `google_sites_extinto_404.html`, 1.561 bytes) é a página
de erro genérica do Google: `<title>Error 404 (Not Found)!!1</title>`, sem viewport,
sem meta description, **sem uma única string que identifique Google Sites**.

### Resposta

O recurso foi encerrado em março de 2024. Os apexes redirecionam para o Google
Business Profile; os subdomínios de negócio devolvem 404 seco.

**A regra é de domínio, e só pode ser de domínio.** Não existe assinatura de HTML
para procurar, porque não sobrou HTML do negócio.

### Consequência para o código — precedência

`site.plataforma = google_sites_extinto` quando o host casa `*.negocio.site` ou
`*.business.site`, **antes** de olhar o status HTTP.

Isso não é detalhe de implementação: a ordem inverte a faixa do lead.

| Ordem | Elegibilidade | Faixa | Efeito |
|---|---|---|---|
| domínio primeiro | `GOOGLE_SITES_EXTINTO` | **T1** | correto |
| status primeiro | `SITE_QUEBRADO` | *sem faixa T1* | lead some do topo da lista |

Pela seção 6.2 da spec, T1 é "substituto improvisado" e inclui
`GOOGLE_SITES_EXTINTO`; `SITE_QUEBRADO` não aparece em nenhuma faixa. Um lead que
tinha site do Google e ficou sem é exatamente quem já foi convencido de que precisa
de presença digital — e a inversão de ordem o jogaria fora do ranking.

O mesmo raciocínio vale para o 403: ver armadilha 7.

---

## As seis armadilhas de falso positivo

A spec avisa que esta é "a peça onde falso positivo custa credibilidade na frente
do cliente". Estas seis são concretas, todas verificadas nas fixtures, e cada uma
virou teste.

### 1. `metaPixelConsentId` da Linktree — a pior de todas

Toda página da Linktree carrega, no `__NEXT_DATA__`:

```
"facebookPixelId":  null                       <- campo do lojista
"googleAnalyticsId":null                       <- campo do lojista
"tiktokPixelId":    null                       <- campo do lojista
"metaPixelConsentId":  "6StlrDkNFNcBNFbPe7JJRF"    <- constante da Linktree
"tiktokPixelConsentId":"1h9aMwwDHM0koRqcj6Qj83"    <- constante da Linktree
```

Os dois `*ConsentId` vieram **idênticos nas três** páginas de Linktree
inspecionadas (`FascinoBeleza`, `galaxyhairshop`, `agendamentoantony`). São
identificadores do fornecedor de consentimento da própria Linktree, não do lojista.

**O estrago:** um detector que procure `pixel` — ou até o mais específico
`tiktokPixel` — marca **toda página de Linktree** como tendo rastreamento pago.
Pela seção 6.2, "elegível + qualquer sinal `tracking.*` pago" é **T0**, a faixa de
maior prioridade. O resultado seria o topo inteiro da lista ocupado por leads sem
verba nenhuma, que é o pior defeito possível numa ferramenta cujo valor é a ordem.

**Regra:** para agregador, ler o campo nomeado do lojista (`facebookPixelId`,
`googleAnalyticsId`, `tiktokPixelId`) e exigir valor não nulo. Nunca casar
substring solta.

### 2. `G-` de GA4 casado sem diferenciar maiúscula

Procurar `G-[A-Z0-9]{8,}` sem distinção de caixa produziu, em 6 das 13 fixtures,
os "ids" `g-generator`, `g-profileBackground`, `g-animation`, `g-recaptcha`,
`g-calculated`, `g-frontend`, `g-function`, `g-progress` — todos nomes de classe
CSS e de identificador JavaScript.

Com casamento sensível a maiúsculas, o conjunto inteiro devolve **um** id, e ele é
real: `G-C2BKCGLQ6T`, em `wordpress_com_whatsapp.html`.

**Regra:** `G-` sensível a maiúsculas **e** ancorado em contexto de verdade
(`gtag('config', 'G-…')` ou `googletagmanager.com/gtag/js?id=G-…`), nunca solto no
documento. Mesma disciplina para `AW-`.

### 3. `<title>` dentro de `<svg>`

`shopify_em_dominio_proprio.html` (hifly.com.br) derruba extração por expressão
regular em dois passos, e eu caí nos dois ao montar a fixture.

Primeiro, o `<title>` verdadeiro está quebrado em três linhas:

```html
<title>
      HIFLY
</title>
```

Regex orientada a linha não casa com ele. Tendo perdido esse, a mesma regex
encontra os **cinco** `<title>` seguintes, cada um em linha única:

```html
<svg ... aria-labelledby="pi-american_express">
  <title id="pi-american_express">American Express</title>
```

São rótulos de acessibilidade dos ícones de bandeira de cartão, no `<body>`.

**O estrago:** `site.title` vira `"American Express"` em vez de `"HIFLY"`. Não é um
defeito inventado nem um lead ruim — é um dado de identificação simplesmente
errado, que aparece no CSV e na tela do lead que a spec chama de "o produto".

**Regra:** extrair de `head > title` com parser de árvore. O parser não vê os
`<svg>`, porque eles estão no body.

### 4. `wa.me` que não tem telefone

Três formatos aparecem nas fixtures, e só dois dão número:

| Forma | Exemplo real | Telefone? |
|---|---|---|
| `wa.me/<E164>` | `wa.me/557999015030` | sim |
| `api.whatsapp.com/send?phone=<E164>` | `…?phone=5511974904291` | sim |
| `wa.me/message/<CÓDIGO>` | `wa.me/message/VR7BW3RWVSZAE1` | **não** |

O formato `/message/` é um link curto de contato: abre a conversa certa, mas não
carrega o número. **As duas páginas de Canva do conjunto usam exatamente esse
formato** — ou seja, é o caso comum no perfil de lead que mais interessa, não a
exceção.

Pior: `agregador_linktree.html` tem `https://api.whatsapp.com/send?phone=` com o
valor **vazio**, ao lado de um `wa.me` válido.

**Regra:** `site.whatsapp_link` (fato: existe caminho até o WhatsApp) é separado do
telefone derivado dele (que pode não existir). Link com `phone=` vazio não é link.

### 5. No Canva, o contato não está no DOM

`canva_salao.html` e `canva_variante_sem_app_name.html` têm **zero** elementos
`<a href>` apontando para o WhatsApp. O link existe, mas mora no JSON do design:

```
"link":{"B":"https://wa.me/message/VR7BW3RWVSZAE1"}
```

**O estrago:** um extrator de contatos que percorra `a[href]` — que é a maneira
óbvia e correta de fazer isso em qualquer outra página — não acha contato nenhum
**exatamente nas páginas de Canva**, que são o lead T1 que a ferramenta existe
para encontrar. O lead entra na lista sem telefone e sem WhatsApp, e o operador
descarta a linha achando que não há como falar com o negócio.

Na Linktree o mesmo vale para o link vazio da armadilha 4: ele está declarado no
JSON-LD (`"sameAs":[…,"https://api.whatsapp.com/send?phone="]`), antes do link
bom, e o `<a href>` bom aparece só uma vez.

**Regra:** título e meta vêm da árvore; **contatos vêm do texto cru**. São duas
técnicas no mesmo coletor, cada uma por um motivo medido, não por gosto.

### 6. `<meta name="description" content="">`

`canva_variante_sem_app_name.html` traz a tag presente e o conteúdo vazio.
Verificar a existência da tag responde "sim, tem description" quando o defeito
vendável — meta description ausente, seção 5 — está lá.

**Regra:** `site.meta_description` é nulo quando o `content` está vazio ou só tem
espaço em branco.

### 7. (bônus) Bloqueio de anti-bot não é site quebrado

Duas fixtures não entregaram conteúdo:

- `agregador_beacons_bloqueado_403.html` — 403 com `<title>Just a moment...</title>`,
  que é desafio de Cloudflare
- `loja_integrada_bloqueada_403.html` — 403, página de erro Varnish da própria
  Loja Integrada, que **ainda assim** carrega `cdn.awsli.com.br` e permite
  classificar

Em ambos o domínio já diz a plataforma. Rebaixar para `quebrado` porque o anti-bot
respondeu 403 tira da lista um lead T1 legítimo.

**Regra:** a classificação por domínio vale mesmo sem corpo. O motivo `bloqueado`
é gravado **ao lado** de `site.plataforma`, nunca no lugar dela. É o princípio 1 do
CLAUDE.md — falha é dado, não ausência de dado.

---

## Assinaturas confirmadas

Contagens de ocorrência nas fixtures. Servem de base para `config/platforms.toml`,
que será preenchido teste a teste, não de uma vez.

| Plataforma | Domínio | Assinatura de HTML | Confirmado em |
|---|---|---|---|
| `canva` | `*.my.canva.site` | `__canva_website_bootstrap__` | 2 variantes distintas |
| `agregador` | `linktr.ee`, `beacons.ai` | `assets.production.linktr.ee` | 3 Linktree + 1 Beacons |
| `wix` | `*.wixsite.com` | `static.parastorage.com` (237–373×) | 2 |
| `wordpress` | — | `/wp-content/` (131–156×), `/wp-includes/` | 2 |
| `shopify` | `*.myshopify.com` | `cdn.shopify.com`, `Shopify.theme` | 3, uma em domínio próprio |
| `loja_integrada` | `*.lojaintegrada.com.br` | `cdn.awsli.com.br` | 1 |
| `google_sites_extinto` | `*.negocio.site`, `*.business.site` | **não existe** — ver S4 | 1 |

**`__canva_website_bootstrap__` é o achado que justifica ter baixado duas páginas
de Canva.** A variante A traz `<meta name="app-name" content="export_website">`;
a variante B não traz. Um classificador construído em cima de uma página só teria
escolhido o `app-name` e classificaria a variante B como `proprio`.

---

## Perguntas que ficam para a Peça 3 (elegibilidade)

**Respondidas em 2026-09-11** — ver a emenda da peça 3 no plano da fatia.
Resumo: (1) construtor só é elegível em subdomínio grátis; (2) a loja suspensa
é `SITE_QUEBRADO`, porque status de erro só torna elegível; (3) a coluna
`rastreamento` do CSV diz "nenhum visível no HTML cru", nunca "não anuncia".

1. **`wix` / `wordpress` / `shopify` / `loja_integrada` são elegíveis?** A seção 6.1
   lista como elegíveis apenas `SEM_SITE`, `CANVA`, `AGREGADOR`,
   `GOOGLE_SITES_EXTINTO` e `SITE_QUEBRADO`, e define `TEM_SITE_PROPRIO` como
   "domínio próprio, responde 200, e não é construtor de página única". Wix e
   WordPress são construtores, mas não de página única. A regra não decide o caso.

2. **Loja Shopify suspensa (HTTP 402).** `shopify_suspensa_402.html` é
   `u10pfz-mz.myshopify.com`, respondendo 402 Payment Required — a loja existe e
   parou de pagar. Assinatura diz `shopify`, status diz `quebrado`. Qual vence? É
   plausível que seja um lead ótimo: já vendeu online e o negócio parou.

3. **Ausência de rastreamento não é prova de ausência de anúncio.**
   `proprio_bem_feito.html` é uma rede nacional grande e não tem nenhuma
   assinatura de rastreamento no HTML cru — provavelmente carregado depois por
   GTM ou barrado por consentimento. A faixa T0 depende de detectar rastreamento,
   então esse falso negativo tem custo direto no ranking, e precisa aparecer como
   limite conhecido na interface, não como fato.

---

## Lacunas do conjunto de fixtures

- **Nenhuma** das 13 páginas tem Google Ads (`AW-`), heatmap ou TikTok Pixel. O
  detector desses três vai nascer sem caso positivo real.
- **Nenhuma** das 5 páginas de Canva/Linktree inspecionadas tem Pixel do lojista —
  que é o caso máximo T0 descrito na seção 6.2. Na Linktree, Pixel exige plano
  pago, o que por si só é um dado sobre o tamanho esperado da faixa T0.
- `quebrado` por DNS e redirecionamento triplo são comportamento do fetcher, não
  HTML. Verificados ao vivo (`Could not resolve host` em dois domínios;
  3 saltos em `negocio.site`) e serão testados com transporte falso, sem rede.
