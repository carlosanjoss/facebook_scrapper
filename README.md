# Facebook Scraper — Radar Ódio

Scraper automatizado de posts e comentários do Facebook, desenvolvido para pesquisa de mestrado sobre discurso de ódio direcionado a páginas de segurança pública.

Coleta de forma contínua e incremental posts e comentários de páginas públicas. Usa Playwright (Chromium persistente) para simular um navegador real com sessão autenticada, extraindo dados via JavaScript e locators do DOM.

---

## Sumário

- [Fluxo de coleta](#fluxo-de-coleta)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Instalação](#instalação)
- [Autenticação](#autenticação)
- [Configuração](#configuração)
- [Execução](#execução)
- [Docker](#docker)
- [Saída de dados](#saída-de-dados)
- [Exports](#exports)
- [Logs e visual](#logs-e-visual)
- [Limitações conhecidas](#limitações-conhecidas)
- [Contexto acadêmico](#contexto-acadêmico)

---

## Fluxo de coleta

1. Lê as URLs de `data/input/links.txt`
2. Para cada URL, acessa a página e rola o feed para carregar posts
3. Para cada post, navega para a URL individual e captura metadados (texto, autor, data, reações, compartilhamentos)
4. Expande comentários e replies ("Ver mais", "Carregar mais comentários"), ordena por "Todos os comentários"
5. Salva cada post em arquivo JSON individual imediatamente (dados nunca perdidos se o processo cair)
6. Ao final do ciclo, aguarda o intervalo configurado e reinicia

---

## Estrutura do projeto

```
facebook_scrapper/
├── app/
│   ├── main.py              # CLI e orquestração de ciclos
│   ├── config.py            # Todas as configurações via .env
│   ├── logger.py            # Logger com RichHandler (console) + arquivo rotativo
│   ├── utils.py             # Helpers: parse_count, clean_text, stable_hash, etc.
│   │
│   ├── browser/             # Tudo relacionado ao Chromium
│   │   ├── driver.py        # start_browser / close_browser (Playwright persistent context)
│   │   ├── cleaner.py       # Script injetado que remove banners de cookies e popups
│   │   ├── scroller.py      # Scroll inteligente (detecta o container correto)
│   │   └── login.py         # Helper para autenticação manual inicial
│   │
│   ├── runtime/             # Infraestrutura de execução
│   │   ├── lock.py          # Lock de arquivo: impede dois processos simultâneos
│   │   └── state.py         # URLs já coletadas (estado entre ciclos)
│   │
│   ├── storage/             # Persistência de dados
│   │   ├── persist.py       # JSON incremental por post; exports JSONL/CSV; relatórios
│   │   └── quality.py       # Enriquecimento: post_type, created_at_absolute, data_quality
│   │
│   ├── navigation/          # Como chegar na página certa
│   │   ├── navigate.py      # navigate_to, _navigate_pfbid, verify_on_target_page
│   │   └── detect.py        # detect_block_or_checkpoint, save_error_artifacts
│   │
│   ├── collector/           # Orquestra o ciclo de coleta
│   │   ├── options.py       # RuntimeOptions, parse_args, load_links
│   │   ├── page.py          # collect_page: feed → posts → comentários
│   │   └── cycle.py         # run_cycle: itera páginas, grava relatório do ciclo
│   │
│   └── extractors/          # Extrai dados de cada tipo de página
│       ├── page.py          # extract_page_metadata (nome, seguidores, etc.)
│       ├── feed.py          # collect_post_urls_from_feed (JS no DOM do feed)
│       ├── post.py          # collect_post_data_from_page, snapshot_page_metadata
│       └── comments/
│           ├── parsers.py   # Regex de autor/data/reações (PT e EN)
│           ├── post.py      # Fluxo post/foto: sort, expand, scroll
│           ├── reel.py      # Fluxo reel: pausa vídeo, abre painel lateral
│           └── __init__.py  # Ponto de entrada único: collect_comments_from_post_page
│
├── data/
│   ├── input/
│   │   └── links.txt        # URLs a monitorar (uma por linha; # para comentários)
│   ├── output/              # JSONs coletados (ver estrutura em Saída de dados)
│   ├── exports/             # JSONL e CSV gerados ao final de cada ciclo
│   ├── reports/             # Relatórios JSON de cada ciclo de coleta
│   ├── sessions/
│   │   └── facebook_chrome_profile/  # Perfil persistente do Chromium (cookies/sessão)
│   ├── logs/
│   │   ├── scraper.log      # Log completo (DEBUG), rotação a cada 5 MB
│   │   ├── screenshots/     # Capturas em caso de erro
│   │   └── artifacts/       # HTML salvo em caso de falha de navegação
│   └── state/               # Lock de processo e checkpoint de ciclo em andamento
│
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── requirements.txt
└── .env.example
```

---

## Instalação

**Pré-requisitos:** Python 3.10+, Git

```bash
# Clonar e criar ambiente virtual
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux / macOS

# Instalar dependências
pip install -r requirements.txt

# Instalar o Chromium do Playwright
playwright install chromium
```

Copie o arquivo de exemplo e ajuste:

```bash
cp .env.example .env
```

Adicione as URLs alvo em `data/input/links.txt`:

```
https://www.facebook.com/bopeoficial.pmerj
https://www.facebook.com/reel/1234567890
# linhas com # são ignoradas
```

---

## Autenticação

O scraper usa um perfil persistente do Chromium. O login precisa ser feito **uma única vez** manualmente:

```bash
python -m app.browser.login
```

Isso abre o browser, você faz login no Facebook normalmente e fecha a janela. Os cookies ficam salvos em `data/sessions/facebook_chrome_profile/` para todas as execuções futuras. Só é necessário refazer se a sessão expirar.

> **Atenção:** Apenas um processo pode usar o perfil persistente por vez. Para fazer testes enquanto o scraper está rodando, pare-o primeiro (`Ctrl+C`).

---

## Configuração

Todas as variáveis são lidas do arquivo `.env`. Os valores abaixo são os defaults:

```env
# Browser
HEADLESS=false          # false = abre janela; true = sem interface (obrigatório no Docker)
SLOW_MO=80              # delay em ms entre ações (simula comportamento humano)

# Timing entre navegações (segundos)
PAGE_WAIT_MIN=4
PAGE_WAIT_MAX=7
SCROLL_DELAY_SECONDS=3
CLICK_DELAY_MIN=0.8
CLICK_DELAY_MAX=2.0

# Scroll: para quando a altura não cresce por N rounds consecutivos
MAX_SCROLL_ATTEMPTS=200
STABLE_SCROLL_ROUNDS=3

# Limites de coleta
MAX_POSTS_PER_PAGE=100
MAX_COMMENT_EXPAND_PER_ARTICLE=50
MAX_REPLY_EXPAND_PER_COMMENT=20
MAX_RETRIES=3
RETRY_DELAY_SECONDS=10
SKIP_RECENT_EMPTY_HOURS=24      # pula posts sem comentários coletados recentemente
RESTART_BROWSER_EVERY_POSTS=0   # reinicia o browser a cada N posts (0 = desativado)
COLLECT_ALBUM_PHOTOS=true

# Modo contínuo
CONTINUOUS_MODE=true
CONTINUOUS_INTERVAL_MINUTES=60

# Proxy (opcional)
# PROXY_SERVER=http://host:port
# PROXY_USERNAME=user
# PROXY_PASSWORD=pass
```

---

## Execução

```bash
# Modo contínuo — roda ciclos indefinidamente (padrão, conforme CONTINUOUS_MODE)
python -m app.main

# Rodar exatamente um ciclo e sair
python -m app.main --once

# Limitar posts por página nesta execução (0 = sem limite)
python -m app.main --limit-posts 5

# Coletar apenas metadados, sem comentários (mais rápido para smoke test)
python -m app.main --no-comments

# Não gerar exports JSONL/CSV ao final do ciclo
python -m app.main --no-export

# Reiniciar o browser a cada 10 posts processados
python -m app.main --restart-browser-every-posts 10

# Ignorar o cache de posts sem comentários (forçar recoleta)
python -m app.main --skip-recent-empty-hours 0

# Combinações possíveis
python -m app.main --once --no-comments --limit-posts 3
```

| Argumento | Default | Descrição |
|---|---|---|
| `--once` | — | Um ciclo e encerra, ignorando `CONTINUOUS_MODE` |
| `--limit-posts N` | `MAX_POSTS_PER_PAGE` | Máx. de posts por página nesta execução |
| `--no-comments` | — | Pula a coleta de comentários |
| `--no-export` | — | Não gera JSONL/CSV ao final |
| `--skip-recent-empty-hours N` | `SKIP_RECENT_EMPTY_HOURS` | Horas de cache para posts sem comentários |
| `--restart-browser-every-posts N` | `RESTART_BROWSER_EVERY_POSTS` | Reinicia o browser a cada N posts |

---

## Docker

O Docker é a forma recomendada para coleta contínua em servidor. A imagem inclui o Chromium e todas as dependências de sistema.

### Pré-requisito: login no host

O perfil Chrome precisa ser criado **antes** de usar o Docker (não há interface gráfica no container):

```bash
# No host, com HEADLESS=false
python -m app.browser.login
# Faça login no Facebook e feche a janela
```

O perfil fica em `data/sessions/facebook_chrome_profile/` e é montado como volume no container.

### Build e execução

```bash
# Build da imagem
docker compose build

# Iniciar em background (modo daemon)
docker compose up -d

# Acompanhar logs em tempo real
docker compose logs -f

# Parar
docker compose down
```

### Execução pontual com argumentos

```bash
docker compose run --rm scraper --once --limit-posts 5
docker compose run --rm scraper --once --no-comments
```

### Como funciona

- **Volume** `./data:/app/data`: todo o `data/` (perfil Chrome, links, output, logs) persiste no host
- **`HEADLESS=true` e `SLOW_MO=0`** são forçados pelo `docker-compose.yml`, sobrescrevendo o `.env`
- **`--disable-dev-shm-usage`**: já incluso nos args do browser para evitar crash por `/dev/shm` limitado a 64 MB no Docker
- **`restart: unless-stopped`**: o container reinicia automaticamente em caso de falha ou reinício do servidor

---

## Saída de dados

### Estrutura de diretórios

```
data/output/
└── www_facebook_com_bopeoficial_pmerj/
    ├── _page.json              # Metadados da página + índice de posts
    └── posts/
        ├── photo_1463290149170843.json
        ├── reel_2084648822083616.json
        ├── pfbid_02Cozb...json
        └── ...
```

O slug do diretório é derivado da URL. O slug do arquivo é derivado do tipo de conteúdo:

| Padrão de URL | Slug do arquivo |
|---|---|
| `/photo/?fbid=123` | `photo_123` |
| `/reel/123` | `reel_123` |
| `/videos/123` | `video_123` |
| `/watch/?v=123` | `watch_123` |
| `/posts/pfbid...` | `pfbid_<24 chars>` |
| `/posts/123` | `post_123` |

### Schema de um post (`posts/{slug}.json`)

```json
{
  "schema_version": "2.1",
  "post_id": "a1b2c3d4e5f6...",
  "post_url": "https://www.facebook.com/photo/?fbid=1463290149170843",
  "post_type": "photo",
  "album_id": "532640361555527",
  "post_index": 2,
  "author": null,
  "created_at": "11 hours ago",
  "created_at_absolute": "2026-06-29T04:00:00+00:00",
  "text": "O povo confia, e quer cada dia mais...",
  "hashtags": ["#BOPE"],
  "mentions": [],
  "content_type": "text",
  "reactions_count": 912,
  "reactions_detail": {
    "like": 912,
    "love": 95,
    "haha": 0,
    "wow": 0,
    "sad": 0,
    "angry": 0,
    "care": 0,
    "total": 1007
  },
  "shares_count": null,
  "comments_count": 40,
  "replies_count": 12,
  "first_collected_at": "2026-06-29T15:29:37+00:00",
  "last_collected_at": "2026-06-30T02:45:38+00:00",
  "data_quality": {
    "missing_fields": [],
    "duplicate_items_removed": 0,
    "observed_comments_count": 43,
    "extracted_comments_count": 40,
    "comments_gap": 3,
    "possible_incomplete_comments": true,
    "has_media": false
  },
  "comments": [
    {
      "comment_id": "f1e2d3c4...",
      "comment_index": 1,
      "author": "Nome do Comentarista",
      "created_at": "2 days ago",
      "created_at_absolute": "2026-06-27T15:00:00+00:00",
      "text": "Texto do comentário...",
      "hashtags": [],
      "mentions": [],
      "content_type": "text",
      "reactions": { "total": 5 },
      "data_quality": { "missing_fields": [] },
      "replies": [
        {
          "reply_id": "a9b8c7d6...",
          "reply_index": 1,
          "author": "Nome",
          "created_at": "1 day ago",
          "created_at_absolute": "2026-06-28T10:00:00+00:00",
          "text": "Texto da resposta...",
          "hashtags": [],
          "mentions": [],
          "content_type": "text",
          "reactions": null,
          "data_quality": { "missing_fields": [] }
        }
      ]
    }
  ]
}
```

### Campos do post

| Campo | Tipo | Descrição |
|---|---|---|
| `schema_version` | string | Versão do schema de dados (`"2.1"`) |
| `post_id` | string | Hash estável derivado da URL |
| `post_url` | string | URL completa do post |
| `post_type` | string | `photo`, `reel`, `video`, `watch_video`, `post`, `story`, `unknown` |
| `album_id` | string\|null | ID do álbum (quando `?set=a.{id}` está na URL) |
| `post_index` | int | Posição no feed durante a coleta |
| `author` | string\|null | Autor do post (nem sempre disponível) |
| `created_at` | string\|null | Data relativa original do DOM (`"2 hours ago"`, `"há 3 dias"`) |
| `created_at_absolute` | string\|null | Data absoluta estimada em ISO 8601 |
| `text` | string | Texto/legenda do post |
| `hashtags` | list | Hashtags extraídas do texto |
| `mentions` | list | Menções (`@usuario`) extraídas do texto |
| `content_type` | string | `text`, `link_only`, `link_with_text`, `emoji_or_symbol_only`, `empty_or_media` |
| `reactions_count` | int\|null | Total de reações |
| `reactions_detail` | dict\|null | Breakdown por tipo de reação |
| `shares_count` | int\|null | Total de compartilhamentos |
| `comments_count` | int | Comentários extraídos |
| `replies_count` | int | Replies extraídas |
| `data_quality` | dict | Diagnóstico de completude (ver abaixo) |
| `first_collected_at` | ISO 8601 | Primeira vez que o post foi visto |
| `last_collected_at` | ISO 8601 | Última atualização do arquivo |

**`data_quality`:**

| Campo | Descrição |
|---|---|
| `missing_fields` | Campos ausentes entre `author`, `created_at`, `text` |
| `duplicate_items_removed` | Comentários/replies descartados por hash duplicado |
| `observed_comments_count` | Contador exibido pelo Facebook no DOM |
| `extracted_comments_count` | Comentários de fato extraídos |
| `comments_gap` | Diferença entre observado e extraído (>0 = coleta incompleta) |
| `possible_incomplete_comments` | `true` se `comments_gap > 0` |
| `has_media` | `true` se o post tem mídia detectada |

### `_page.json`

Gerado em `data/output/{slug}/_page.json` ao final de cada ciclo:

```json
{
  "source": "facebook",
  "schema_version": "2.1",
  "page_url": "https://www.facebook.com/bopeoficial.pmerj",
  "status": "ok",
  "page_metadata": { "page_name": "BOPE", "followers": "152K" },
  "first_collected_at": "2026-06-01T00:00:00+00:00",
  "last_collected_at": "2026-06-30T14:00:00+00:00",
  "total_posts": 87,
  "total_comments": 3241,
  "total_replies": 891,
  "post_slugs": ["photo_123", "reel_456", "..."],
  "new_posts_count": 3
}
```

---

## Exports

Ao final de cada ciclo (se não usar `--no-export`), o scraper gera arquivos consolidados em `data/exports/{slug}/`:

```
data/exports/
└── www_facebook_com_bopeoficial_pmerj/
    ├── posts.jsonl       # Um post por linha (JSON Lines)
    └── comments.csv      # Todos os comentários e replies em formato tabular
```

### `comments.csv`

| Coluna | Descrição |
|---|---|
| `post_id` | Hash do post pai |
| `post_url` | URL do post pai |
| `item_type` | `comment` ou `reply` |
| `item_id` | Hash do item |
| `parent_comment_id` | Hash do comentário pai (apenas para replies) |
| `author` | Autor |
| `created_at` | Data relativa original |
| `created_at_absolute` | Data absoluta estimada |
| `text` | Texto |
| `content_type` | Tipo de conteúdo |
| `reactions_total` | Total de reações |
| `hashtags` | Hashtags separadas por `;` |
| `mentions` | Menções separadas por `;` |

### Relatórios de ciclo

Cada ciclo gera um relatório JSON em `data/reports/cycle_{id}.json` com estatísticas por página: posts processados, novos, pulados, falhas, comentários coletados, tempo de execução.

---

## Logs e visual

### Console (Rich)

O terminal usa `rich` para saída formatada:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 ciclo 1  ·  30/06  14:32
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[14:32:05] Acessando página: https://facebook.com/bopeoficial.pmerj
[14:32:08] Feed: 12 posts encontrados

  ⠹  Posts  ████████████░░░░  8/12  ·  0:00:45  reel_1234567890

[14:36:28] 3 novos posts — bopeoficial/
▲ [14:36:30] Checkpoint detectado — parando coleta.

  ✓  bopeoficial.pmerj  12 posts  3 novos  847 coment.  182s

──────── 1/1  ·  3 posts  ·  847 coment. ────────
```

- Timestamps curtos `[HH:MM:SS]` sem label de nível — warnings têm `▲`, erros têm `✗`
- Barra de progresso `rich.progress` integrada ao mesmo console (sem conflito de output)
- Cabeçalho e rodapé de ciclo com `Rule` — o rodapé desaparece e é substituído pelo próximo ciclo

### Arquivo de log

```
data/logs/scraper.log    # Nível DEBUG, rotação a cada 5 MB, 3 backups
```

Para diagnóstico detalhado de extração, JS executado e decisões internas, consulte `scraper.log`.

---

## Notas técnicas

### Snapshot pré-expand

A data, reações e compartilhamentos são capturados **antes** do clique em "Ver mais". O Facebook remove esses elementos do DOM durante a re-renderização do expand. O `snapshot_page_metadata` aguarda o elemento de data aparecer fora de artigos de comentários (via `wait_for_function`) antes de capturar.

### Estrutura de comentários no DOM

```
[role="article"]  ← container do post
  [role="article"] aria-label="Comment by João 2 days ago"  ← comentário
    [role="article"] aria-label="Reply by Maria 1 day ago"  ← reply
```

O `aria-label` é parseado com regex bilíngue (PT e EN) para separar autor e data.

### Navegação pfbid

Posts com URL `/posts/pfbid...` não suportam `goto` direto — o Facebook redireciona para a home. O scraper detecta esse padrão e navega via clique no feed (`_navigate_pfbid`).

### Proteção de comentários

Se um novo ciclo coleta menos que 50% dos comentários de um ciclo anterior, os comentários antigos são preservados (proteção contra falhas transitórias de carregamento do DOM).

### Reels

O fluxo de reels é separado do fluxo de posts/fotos: pausa o vídeo, abre o painel lateral de comentários e usa o JS de extração específico desse DOM. O `scroll_page` é pulado em reels porque o scroller genérico avança para o próximo reel em vez de rolar o painel.

---

## Limitações conhecidas

- **Data relativa:** `created_at` é sempre relativa (`"2 days ago"`, `"há 3 dias"`). `created_at_absolute` é uma estimativa com granularidade de hora/dia — não é timestamp preciso
- **Idioma:** o Facebook pode renderizar em PT ou EN dependendo da sessão; regex bilíngues cobrem ambos, mas formatos novos podem escapar
- **Reels com 0 comentários:** se a extração retornar vazio, verifique `scraper.log` — o DOM do painel pode ter mudado
- **Sessão expirada:** se o scraper parar de coletar e os logs mostrarem "checkpoint", refaça o login com `python -m app.browser.login`
- **Processo único:** o perfil persistente do Chromium não suporta acesso simultâneo de dois processos — o lock de arquivo em `data/state/collector.lock` impede isso, mas dois terminais podem conflitar se o lock não for liberado

---

## Contexto acadêmico

Este scraper foi desenvolvido para o projeto **Radar Ódio**, pesquisa de mestrado que analisa padrões de discurso de ódio em comentários de páginas de segurança pública no Facebook. Os dados coletados são utilizados exclusivamente para fins de pesquisa acadêmica.

