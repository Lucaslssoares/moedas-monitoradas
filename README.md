# Moedas Monitoradas — Crypto Price Hunter

Pipeline de monitoramento de preços de criptomoedas em tempo real, com alertas automáticos via Telegram quando ocorrem quedas de preço significativas.

Dados fornecidos pela [CoinGecko API](https://www.coingecko.com/en/api) — pública, gratuita e sem autenticação.

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────────┐
│                        projetos_shared (Docker Network)             │
│                                                                     │
│   ┌──────────────┐     ┌──────────────────┐     ┌──────────────┐   │
│   │  n8n Cron    │────▶│  CoinGecko API   │     │  PostgreSQL  │   │
│   │  (agendador) │     │  (externa)       │     │  :5432       │   │
│   └──────┬───────┘     └────────┬─────────┘     └──────▲───────┘   │
│          │                      │                       │           │
│          │              preços em BRL                   │           │
│          │                      │                       │           │
│          │             ┌────────▼──────────┐            │           │
│          └────────────▶│  Python FastAPI   │────────────┘           │
│                        │  :8001            │  INSERT price_history  │
│                        └────────┬──────────┘                        │
│                                 │                                   │
│                    queda >= ALERT_THRESHOLD_PCT?                     │
│                                 │                                   │
│                        ┌────────▼──────────┐                        │
│                        │  n8n Telegram     │                        │
│                        │  Node (alerta)    │                        │
│                        └───────────────────┘                        │
└─────────────────────────────────────────────────────────────────────┘
```

Fluxo resumido:

1. O **n8n Cron** dispara a cada hora.
2. O nó **HTTP Request** consulta a CoinGecko API pelos preços em BRL das moedas configuradas.
3. Os dados são enviados via **POST** ao serviço **Python FastAPI** (`/webhook/analyze`).
4. O FastAPI persiste o histórico de preços no **PostgreSQL** e retorna se deve ou não disparar alerta.
5. Caso a queda de preço atinja o limiar configurado (`ALERT_THRESHOLD_PCT`), o n8n aciona o nó **Telegram**.

---

## Pré-requisitos

A infraestrutura compartilhada **deve estar em execução**:

```bash
cd ../infra
docker compose up -d
```

| Serviço    | Host interno | Porta |
|------------|--------------|-------|
| PostgreSQL | `postgres`   | 5432  |
| n8n        | `n8n`        | 5678  |

---

## Setup

### Passo 1 — Variáveis de ambiente

```bash
cp .env.example .env
```

Edite o `.env` com suas configurações:

```dotenv
# PostgreSQL (infra compartilhada)
DB_HOST=postgres
DB_PORT=5432
DB_USER=airflow
DB_PASSWORD=airflow
DB_NAME=airflow

# Moedas monitoradas (IDs do CoinGecko)
CRYPTO_IDS=bitcoin,ethereum,solana,cardano,chainlink
CRYPTO_LIMIT=5

# Percentual de queda que dispara alerta
ALERT_THRESHOLD_PCT=-10.0

# Telegram
TELEGRAM_BOT_TOKEN=seu_token_aqui
TELEGRAM_CHAT_ID=seu_chat_id_aqui
```

> IDs de moedas disponíveis em: `https://api.coingecko.com/api/v3/coins/list`

### Passo 2 — Subir o serviço Python

```bash
docker compose up --build -d
```

Acompanhar logs:

```bash
docker compose logs -f
```

### Passo 3 — Importar o workflow no n8n

1. Acesse `http://localhost:5678`
2. **Workflows** → **Import from file** → selecione `n8n/workflow.json`
3. Configure a credencial do Telegram no nó **Send Telegram Alert**
4. Ative o workflow pelo toggle

---

## Como configurar o Telegram

1. Abra o Telegram e busque **@BotFather**
2. Envie `/newbot` e siga as instruções para criar o bot
3. Copie o token gerado (formato: `123456789:ABCDef...`)
4. Envie uma mensagem para o seu bot, depois acesse:
   ```
   https://api.telegram.org/bot<SEU_TOKEN>/getUpdates
   ```
5. Localize o campo `"chat": { "id": XXXXXXX }` — esse é o `TELEGRAM_CHAT_ID`
6. Preencha os dois valores no `.env`

---

## Moedas monitoradas (padrão)

| Moeda     | ID CoinGecko  |
|-----------|---------------|
| Bitcoin   | `bitcoin`     |
| Ethereum  | `ethereum`    |
| Solana    | `solana`      |
| Cardano   | `cardano`     |
| Chainlink | `chainlink`   |

Para adicionar ou trocar moedas, edite `CRYPTO_IDS` no `.env` e reinicie o container do n8n.

---

## Endpoints da API

### `GET /health`

```
GET http://localhost:8001/health
```

```json
{ "status": "ok", "ts": "2025-06-04T12:00:00" }
```

### `POST /webhook/analyze`

```json
{
  "items": [
    {
      "id": "bitcoin",
      "title": "Bitcoin (BTC)",
      "price": 320000.00,
      "currency_id": "BRL",
      "permalink": "https://www.coingecko.com/en/coins/bitcoin",
      "seller": {}
    }
  ],
  "query": "crypto-brl"
}
```

Resposta com alerta:

```json
{
  "processed": 1,
  "alerts": [
    {
      "product_id": "bitcoin",
      "title": "Bitcoin (BTC)",
      "previous_price": 355000.00,
      "current_price": 320000.00,
      "variation_pct": -9.86,
      "permalink": "https://www.coingecko.com/en/coins/bitcoin"
    }
  ],
  "has_alert": true
}
```

---

## Estrutura do projeto

```
moedas-monitoradas/
│
├── src/
│   ├── app.py          # FastAPI — rotas /health e /webhook/analyze
│   └── database.py     # Conexão PostgreSQL
│
├── n8n/
│   └── workflow.json   # Workflow n8n (importar via UI)
│
├── docker-compose.yaml # Sobe apenas o serviço FastAPI
├── .env.example        # Modelo de variáveis de ambiente
├── .env                # Variáveis locais (não versionar)
└── README.md
```

---

## Como estender

| Objetivo                              | Onde modificar                        |
|---------------------------------------|---------------------------------------|
| Adicionar novas moedas                | `CRYPTO_IDS` no `.env`               |
| Monitorar em outra moeda (USD, EUR)   | Parâmetro `vs_currency` no workflow  |
| Alterar canal de alerta (Slack, etc.) | Substituir nó Telegram no n8n        |
| Criar dashboard de preços             | Conectar Metabase/Grafana ao PostgreSQL |
| Aumentar frequência de coleta         | Ajustar intervalo no nó Schedule Trigger |
