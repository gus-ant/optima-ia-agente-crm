# Óptima IA — Agente Lara × Lu Decorações

Agente de qualificação de leads via WhatsApp, construído com **LangGraph + LangChain** e integrado a um **CRM Próprio Local** rodando em **PostgreSQL**. O N8N é usado exclusivamente para triggers simples (follow-up cron, fallback webhook).

## Stack

| Camada | Tecnologia |
|--------|-----------|
| **Orquestração do agente** | LangGraph + LangChain |
| **API / Webhook receiver** | FastAPI |
| **LLM** | OpenAI GPT-4o / Anthropic Claude |
| **Canal** | WhatsApp Cloud API (Meta) ou Evolution API |
| **CRM** | CRM Próprio Local (PostgreSQL + SQLAlchemy Assíncrono) |
| **Estado de sessão** | Redis (LangGraph memory/checkpointer) |
| **Triggers simples** | N8N (follow-up cron, notificações) |
| **Infra** | Docker + VPS (Hetzner/DigitalOcean) |

## Estrutura do Repositório

```
optima-ia-agente-crm/
├── agent/                   # Núcleo do agente (LangGraph)
│   ├── graph.py             # Definição e compilação do grafo
│   ├── nodes.py             # Nós do grafo (receive, LLM, sync, handoff)
│   ├── state.py             # AgentState — estado compartilhado tipado (inclui contato_id/negocio_id)
│   ├── tools.py             # LangChain Tools (Integração com Local CRM, WhatsApp)
│   ├── prompts.py           # System prompts versionados
│   └── extraction.py        # Extração estruturada via Pydantic + LLM
│
├── api/                     # FastAPI — Webhook receiver
│   ├── main.py              # App principal + lifespan (inicializa tabelas DB local)
│   └── routers/
│       ├── webhook.py       # POST /webhook/meta e /webhook/evolution
│       └── health.py        # GET /health/
│
├── crm/                     # CRM Próprio Local
│   ├── database.py          # Configurações do SQLAlchemy assíncrono (engine, get_db_session)
│   ├── models.py            # Modelos relacionais (Contato, Negocio, Atividade)
│   └── client.py            # LocalCRMClient (gestão de contatos, negócios e atividades)
│
├── whatsapp/                # Clientes WhatsApp
│   └── client.py            # MetaWhatsAppClient + EvolutionWhatsAppClient
│
├── memory/                  # Persistência de estado conversacional
│   └── store.py             # Redis store + fallback in-memory para dev
│
├── n8n_flows/               # Fluxos N8N exportados (triggers simples de follow-up)
│
├── tests/                   # Testes unitários e de integração
│   └── test_graph.py        # Testes usando banco SQLite em memória
│
├── infra/
│   └── docker-compose.yml   # Stack local: FastAPI Agent + Redis + PostgreSQL + N8N
│
├── prompts/                 # System prompts versionados em Markdown
├── schemas/                 # JSON schemas de extração
├── docs/                    # Documentação técnica e guias de alterações/configurações
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
  ├─[tool_calls?]──► tool_executor    ← create_crm_contact, update_crm_lead, etc.
  │                       │
  │◄──────────────────────┘
  ▼
sync_crm                 ← atualiza campos + pipeline no Banco Relacional Local
  │
  ├─[pronto_transbordo?]──► handoff   ← notifica atendente + mensagem final
  │
  └─[aguardando]──► END
```

## Modelagem do CRM Local (Banco de Dados)

O banco de dados do CRM Próprio possui três tabelas fundamentais:
*   **`Contato` (`contatos`):** Armazena dados de cadastro (ID, WhatsApp ID único, nome, data de criação).
*   **`Negocio` (`negocios`):** Registra a oportunidade de vendas vinculada ao contato (tipo de evento, data do evento, orçamento estimado parseado automaticamente, etapa do funil e notas detalhadas da Lara).
*   **`Atividade` (`atividades`):** Logs de conversas (mensagens inbound e outbound) com timestamp para fins de auditoria.

---

## Início Rápido

### 1. Clonar e configurar ambiente
```bash
git clone <repo>
cd optima-ia-agente-crm
cp .env.example .env
# Edite o arquivo .env com a sua OPENAI_API_KEY
```

### 2. Desenvolvimento local (Usando SQLite em memória)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Roda a API FastAPI localmente (Cria automaticamente as tabelas SQLite)
python -m api.main
```

### 3. Rodando em Produção (Docker Compose)
Suba a stack inteira contendo o PostgreSQL local configurado e persistente:
```bash
docker compose -f infra/docker-compose.yml up -d
```

### 4. Executando testes locais
```bash
source .venv/bin/activate
pytest tests/ -v
```

---

## Configuração do Webhook

### Meta WhatsApp Cloud API
1.  No Meta Business Suite → WhatsApp → Webhooks
2.  URL: `https://seu-dominio.com/webhook/meta`
3.  Token de verificação: valor de `META_WEBHOOK_VERIFY_TOKEN` configurado no `.env`
4.  Campos assinados: `messages`

---

## Cliente

Desenvolvido para **Lu Decorações** pela **Óptima IA**.  
Documentação completa de alterações e arquitetura em `docs/alteracoes_e_configuracao.md`.
