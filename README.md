# 📉 Moedas Monitoradas — Crypto Price Hunter

> Pipeline de monitoramento de preços de criptomoedas em tempo real com alertas automáticos via Telegram.

[![Python](https://img.shields.io/badge/Python-3.11-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?logo=fastapi)](https://fastapi.tiangolo.com)
[![n8n](https://img.shields.io/badge/n8n-workflow-EA4B71?logo=n8n)](https://n8n.io)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql)](https://postgresql.org)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)](https://docker.com)

---

## 📸 Screenshots

### Workflow no n8n

![Workflow n8n](docs/n8n-workflow.png)

> Pipeline completo: agendador → CoinGecko → FastAPI → alerta Telegram.

### Alerta no Telegram

![Alerta Telegram](docs/telegram-alert.png)

> Mensagem enviada automaticamente quando uma criptomoeda cai mais de 10% em relação ao último preço registrado.

---

## 🏗️ Arquitetura

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     projetos_shared  (Docker Network)                   │
│                                                                         │
│  ┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐   │
│  │  n8n            │    │  CoinGecko API   │    │  PostgreSQL 16   │   │
│  │  Orquestrador   │───▶│  api.coingecko   │    │  :5432           │   │
│  │  :5678          │    │  .com (externa)  │    │  price_history   │   │
│  └────────┬────────┘    └────────┬─────────┘    └────────▲─────────┘   │
│           │                      │                        │             │
│           │              preços em BRL                    │             │
│           │           (BTC, ETH, SOL...)                  │             │
│           │                      │                        │             │
│           │             ┌────────▼──────────┐             │             │
│           └────────────▶│  FastAPI          │─────────────┘             │
│                         │  price-monitor    │  INSERT price_history      │
│                         │  :8001            │                           │
│                         └────────┬──────────┘                           │
│                                  │                                      │
│                     queda ≥ ALERT_THRESHOLD_PCT ?                       │
│                                  │                                      │
│                    ┌─────────────┴─────────────┐                        │
│                    │ Sim                        │ Não                   │
│                    ▼                            ▼                       │
│           ┌────────────────┐          ┌─────────────────┐               │
│           │  n8n Telegram  │          │  No Operation   │               │
│           │  Alerta enviado│          │  (silencioso)   │               │
│           └────────────────┘          └─────────────────┘               │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Fluxo do Pipeline

```
Schedule Trigger (1h)
        │
        ▼
Set Crypto Params ──── lê CRYPTO_IDS e CRYPTO_LIMIT do ambiente
        │
        ▼
Fetch CoinGecko Prices ──── GET /coins/markets?vs_currency=brl&ids=...
        │
        ▼
Extract Items ──── mapeia resposta para formato interno
        │
        ▼
Analyze Prices ──── POST /webhook/analyze → FastAPI
        │              ├── busca último preço no PostgreSQL
        │              ├── calcula variação percentual
        │              ├── insere novo registro
        │              └── retorna { has_alert, alerts[] }
        │
        ▼
     Has Alert?
    /          \
  Sim          Não
   │            │
   ▼            ▼
Format Alert   No Operation
Message
   │
   ▼
Send Telegram Alert ──── mensagem formatada em Markdown
```

---

## 🛠️ Stack de Tecnologias

| Camada         | Tecnologia           | Função                                      |
|----------------|----------------------|---------------------------------------------|
| Orquestração   | **n8n**              | Agendamento, chamadas HTTP, lógica de fluxo |
| API de dados   | **CoinGecko API**    | Preços em tempo real (gratuita, sem auth)   |
| Backend        | **FastAPI + Python** | Lógica de alerta e persistência             |
| Banco de dados | **PostgreSQL 16**    | Histórico de preços                         |
| Mensageria     | **Telegram Bot API** | Envio de alertas                            |
| Container      | **Docker Compose**   | Orquestração de serviços                    |
| Infra          | **projetos_shared**  | Rede Docker compartilhada entre projetos    |

---

## 📦 Pré-requisitos

A infraestrutura compartilhada precisa estar rodando antes de subir este projeto:

```bash
cd ../infra
docker compose up -d
```

Serviços provisionados pela infra:

| Serviço    | Host (interno) | Porta |
|------------|----------------|-------|
| PostgreSQL | `postgres`     | 5432  |
| n8n        | `n8n`          | 5678  |
| pgAdmin    | `pgadmin`      | 5050  |

---

## 🚀 Setup

### 1. Variáveis de ambiente

```bash
cp .env.example .env
```

Edite `.env` com seus valores:

```dotenv
# PostgreSQL — mesmo da infra compartilhada
DB_HOST=postgres
DB_PORT=5432
DB_USER=airflow
DB_PASSWORD=airflow
DB_NAME=airflow

# Moedas monitoradas (IDs do CoinGecko, separados por vírgula)
# Lista completa: https://api.coingecko.com/api/v3/coins/list
CRYPTO_IDS=bitcoin,ethereum,solana,cardano,chainlink
CRYPTO_LIMIT=5

# Percentual de queda mínima para disparar alerta
# -10.0 = alerta quando o preço cair 10% ou mais
ALERT_THRESHOLD_PCT=-10.0

# Telegram Bot
TELEGRAM_BOT_TOKEN=seu_token_aqui
TELEGRAM_CHAT_ID=seu_chat_id_aqui
```

### 2. Subir o serviço FastAPI

```bash
docker compose up --build -d
```

Verificar se está no ar:

```bash
curl http://localhost:8001/health
# {"status":"ok","ts":"2026-06-05T00:00:00"}
```

### 3. Importar o workflow no n8n

1. Acesse **http://localhost:5678**
2. Menu → **Workflows** → **Import from file**
3. Selecione `n8n/workflow.json`
4. Abra o nó **Send Telegram Alert** → configure a credencial do Telegram
5. Ative o workflow pelo toggle no canto superior direito

### 4. Configurar credencial do Telegram no n8n

1. **Credentials** → **Add credential** → busque **Telegram**
2. Cole o `Bot Token`
3. Salve como `Telegram Bot`
4. No nó **Send Telegram Alert**, selecione essa credencial

---

## 🪙 Moedas monitoradas (padrão)

| Moeda     | ID CoinGecko | Símbolo |
|-----------|--------------|---------|
| Bitcoin   | `bitcoin`    | BTC     |
| Ethereum  | `ethereum`   | ETH     |
| Solana    | `solana`     | SOL     |
| Cardano   | `cardano`    | ADA     |
| Chainlink | `chainlink`  | LINK    |

> Para adicionar moedas, edite `CRYPTO_IDS` no `.env` e reinicie o n8n:
> ```bash
> cd ../infra && docker compose up -d --no-deps n8n
> ```

---

## 📡 API Reference

### `GET /health`

```bash
curl http://localhost:8001/health
```

```json
{ "status": "ok", "ts": "2026-06-05T00:00:00.000000" }
```

### `POST /webhook/analyze`

**Request:**
```json
{
  "items": [
    {
      "id": "bitcoin",
      "title": "Bitcoin (BTC)",
      "price": 320401.00,
      "currency_id": "BRL",
      "permalink": "https://www.coingecko.com/en/coins/bitcoin",
      "seller": {}
    }
  ],
  "query": "crypto-brl"
}
```

**Response — com alerta:**
```json
{
  "processed": 1,
  "has_alert": true,
  "alerts": [
    {
      "product_id": "bitcoin",
      "title": "Bitcoin (BTC)",
      "previous_price": 400000.00,
      "current_price": 320401.00,
      "variation_pct": -19.90,
      "permalink": "https://www.coingecko.com/en/coins/bitcoin"
    }
  ]
}
```

**Response — sem alerta:**
```json
{ "processed": 5, "has_alert": false, "alerts": [] }
```

---

## 🗄️ Esquema do Banco de Dados

Tabela `price_history` — criada automaticamente na inicialização:

```sql
CREATE TABLE IF NOT EXISTS price_history (
    id               SERIAL PRIMARY KEY,
    product_id       VARCHAR(50)    NOT NULL,
    product_title    TEXT           NOT NULL,
    seller_id        VARCHAR(50),
    seller_nickname  VARCHAR(100),
    price            NUMERIC(18, 2) NOT NULL,
    original_price   NUMERIC(18, 2),
    currency_id      VARCHAR(10)    NOT NULL DEFAULT 'BRL',
    permalink        TEXT,
    variation_pct    NUMERIC(8, 4),
    alerted          BOOLEAN        NOT NULL DEFAULT FALSE,
    searched_at      TIMESTAMP      NOT NULL DEFAULT NOW()
);
```

| Coluna          | Tipo          | Descrição                                    |
|-----------------|---------------|----------------------------------------------|
| `product_id`    | VARCHAR(50)   | ID da moeda no CoinGecko (ex: `bitcoin`)    |
| `product_title` | TEXT          | Nome completo (ex: `Bitcoin (BTC)`)         |
| `price`         | NUMERIC(18,2) | Preço em BRL no momento da captura          |
| `variation_pct` | NUMERIC(8,4)  | Variação % em relação ao registro anterior  |
| `alerted`       | BOOLEAN       | Se gerou alerta no Telegram                 |
| `searched_at`   | TIMESTAMP     | Data/hora UTC da captura                    |

---

## 📁 Estrutura do Projeto

```
moedas-monitoradas/
│
├── src/
│   ├── app.py           # FastAPI — /health e /webhook/analyze
│   ├── database.py      # Conexão PostgreSQL
│   └── sql/
│       └── schema.sql   # DDL da tabela price_history
│
├── n8n/
│   └── workflow.json    # Workflow exportado (importar via UI do n8n)
│
├── docs/
│   └── telegram-alert.png  # Screenshot do alerta no Telegram
│
├── Dockerfile           # Imagem do serviço FastAPI
├── docker-compose.yaml  # Sobe o price-monitor (infra é separada)
├── .env.example         # Template de variáveis de ambiente
├── .env                 # Variáveis locais (não versionar)
└── README.md            # Este arquivo
```

---

## ⚙️ Como Estender

| Objetivo                              | Onde modificar                            |
|---------------------------------------|-------------------------------------------|
| Adicionar novas moedas                | `CRYPTO_IDS` no `.env` + restart n8n     |
| Monitorar em USD ou EUR               | Parâmetro `vs_currency` no workflow n8n  |
| Trocar canal de alerta (Slack, etc.)  | Substituir nó Telegram no workflow       |
| Alterar limiar de queda               | `ALERT_THRESHOLD_PCT` no `.env`          |
| Criar dashboard de preços             | Conectar Metabase/Grafana ao PostgreSQL  |
| Aumentar frequência de coleta         | Ajustar intervalo no nó Schedule Trigger |
| Monitorar alta de preço               | Adicionar condição positiva no FastAPI   |

---

## 🔧 Comandos Úteis

```bash
# Ver logs do FastAPI
docker compose logs -f

# Consultar histórico de preços no banco
docker exec -it infra-postgres-1 psql -U airflow -d airflow \
  -c "SELECT product_title, price, variation_pct, alerted, searched_at
      FROM price_history ORDER BY searched_at DESC LIMIT 20;"

# Reiniciar n8n após mudar variáveis de ambiente
cd ../infra && docker compose up -d --no-deps n8n

# Testar o webhook manualmente
curl -X POST http://localhost:8001/webhook/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "items": [{
      "id": "bitcoin",
      "title": "Bitcoin (BTC)",
      "price": 300000,
      "currency_id": "BRL",
      "permalink": "https://www.coingecko.com/en/coins/bitcoin",
      "seller": {}
    }],
    "query": "test"
  }'
```

---

## 📄 Licença

Projeto de estudo — livre para uso e modificação.
