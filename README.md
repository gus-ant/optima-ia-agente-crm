# Óptima IA — Agente Lara × Lu Decorações

Agente de qualificação de leads via WhatsApp, construído com **LangGraph + LangChain** e integrado ao **Bitrix24/HubSpot**. O N8N é usado exclusivamente para triggers simples (follow-up cron, fallback webhook).

## Stack

| Camada | Tecnologia |
|--------|-----------|
| **Orquestração do agente** | LangGraph + LangChain |
| **API / Webhook receiver** | FastAPI |
| **LLM** | OpenAI GPT-4o / Anthropic Claude |
| **Canal** | WhatsApp Cloud API (Meta) ou Evolution API |
| **CRM** | Bitrix24 (padrão) ou HubSpot |
| **Estado de sessão** | Redis |
| **Triggers simples** | N8N (follow-up cron, notificações) |
| **Infra** | Docker + VPS (Hetzner/DigitalOcean) |

## Estrutura do Repositório

```
optima-ia-agente-crm/
├── agent/                   # Núcleo do agente (LangGraph)
│   ├── graph.py             # Definição e compilação do grafo
│   ├── nodes.py             # Nós do grafo (receive, LLM, sync, handoff)
│   ├── state.py             # AgentState — estado compartilhado tipado
│   ├── tools.py             # LangChain Tools (CRM, WhatsApp)
│   ├── prompts.py           # System prompts versionados
│   └── extraction.py        # Extração estruturada via Pydantic + LLM
│
├── api/                     # FastAPI — Webhook receiver
│   ├── main.py              # App principal + lifespan
│   └── routers/
│       ├── webhook.py       # POST /webhook/meta e /webhook/evolution
│       └── health.py        # GET /health/
│
├── crm/                     # Clientes CRM
│   └── client.py            # Bitrix24Client + HubSpotClient (factory)
│
├── whatsapp/                # Clientes WhatsApp
│   └── client.py            # MetaWhatsAppClient + EvolutionWhatsAppClient
│
├── memory/                  # Persistência de estado
│   └── store.py             # Redis store + fallback in-memory
│
├── n8n_flows/               # Fluxos N8N exportados (triggers simples)
│
├── tests/                   # Testes unitários e de integração
│   └── test_graph.py
│
├── infra/
│   └── docker-compose.yml   # Stack completo: agent + Redis + N8N
│
├── prompts/                 # System prompts versionados em Markdown
├── schemas/                 # JSON schemas de extração
├── docs/                    # Documentação técnica
│
├── Dockerfile
├── requirements.txt
├── pyproject.toml
└── .env.example
```

## Fluxo do Agente (LangGraph)

```
START
  │
  ▼
receive_message          ← entrada: mensagem do WhatsApp
  │
  ▼
call_llm (Lara)          ← invoca GPT-4o com system prompt + histórico
  │
  ├─[tool_calls?]──► tool_executor    ← create_contact, update_crm, etc.
  │                       │
  │◄──────────────────────┘
  ▼
sync_crm                 ← atualiza campos + pipeline no CRM
  │
  ├─[pronto_transbordo?]──► handoff   ← notifica atendente + mensagem final
  │
  └─[aguardando]──► END
```

## Início Rápido

```bash
# 1. Clone e configure o ambiente
git clone <repo>
cd optima-ia-agente-crm
cp .env.example .env
# Edite .env com suas chaves de API

# 2. Desenvolvimento local (sem Docker)
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Inicia Redis (requer Docker)
docker run -d -p 6379:6379 redis:7-alpine

# Inicia o agente
python -m api.main

# 3. Produção (Docker Compose)
docker compose -f infra/docker-compose.yml up -d

# 4. Testes
pytest tests/ -v
```

## Configuração do Webhook

### Meta Cloud API
1. No Meta Business → WhatsApp → Webhooks
2. URL: `https://seu-dominio.com/webhook/meta`
3. Token de verificação: valor de `META_WEBHOOK_VERIFY_TOKEN` no `.env`
4. Campos assinados: `messages`

### Evolution API
1. No painel Evolution, configure webhook URL: `https://seu-dominio.com/webhook/evolution`
2. Evento: `messages.upsert`

## N8N — Triggers Usados

| Fluxo | Gatilho | Ação |
|-------|---------|------|
| Follow-up 24h | Cron: diário | Chama `GET /webhook/n8n/followup` |
| Alerta de falha | Webhook de erro | Notifica Slack/e-mail |

## Variáveis de Ambiente

Veja [`.env.example`](.env.example) para a lista completa.

Mínimo necessário para funcionar:
```
OPENAI_API_KEY=sk-...
META_ACCESS_TOKEN=...
META_PHONE_NUMBER_ID=...
META_WEBHOOK_VERIFY_TOKEN=...
BITRIX24_WEBHOOK_URL=...
```

## Cliente

Desenvolvido para **Lu Decorações** pela **Óptima IA**.  
Documentação completa em `docs/`.
