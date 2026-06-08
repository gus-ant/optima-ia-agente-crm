# Óptima IA — CRM Multi-Tenant & Agente Lara × Lu Decorações

Agente inteligente de qualificação de leads via WhatsApp, construído com **LangGraph + LangChain** e integrado a um **CRM Multi-Tenant** que utiliza **Supabase (PostgreSQL)** com **Row Level Security (RLS)** e persistência em memória/Redis.

---

## 🚀 Arquitetura & Stack de Tecnologias

| Camada | Tecnologia | Descrição |
| :--- | :--- | :--- |
| **Orquestração do Agente** | LangGraph + LangChain | Inteligência artificial, tomada de decisão e fluxo de conversa estruturado. |
| **API / Webhook Receiver** | FastAPI | Receptor de webhooks do WhatsApp e endpoints REST dos dashboards. |
| **Banco de Dados** | Supabase (PostgreSQL) | Banco relacional hospedado na nuvem com extensão **pgvector** habilitada. |
| **Segurança Multi-Tenant** | PostgreSQL Row Level Security (RLS) | Isolamento lógico completo de dados por tenant_id sem vazamento de escopo. |
| **Mecanismo de Conexão** | SQLAlchemy (Asyncpg) | Acesso assíncrono ao banco com suporte a SSL e pooler desabilitador de cached statements. |
| **Sessão & Estado** | Redis | Buffer rápido e fallback local na memória RAM do servidor para dev. |

---

## 📂 Estrutura do Repositório

```
optima-ia-agente-crm/
├── agent/                   # Grafo cognitivo da Lara (LangGraph)
├── api/                     # FastAPI e controladores (routers)
│   ├── routers/
│   │   ├── master.py        # Painel Master global (criação e gestão de tenants)
│   │   └── dashboard.py     # Endpoints do dashboard de CRM do tenant
│   └── middleware.py        # TenantMiddleware (resolução de inquilino por slug/header)
├── crm/                     # Relacional do CRM Local
│   ├── database.py          # SQLAlchemy Async Engine com tratamento para SSL
│   └── models.py            # Modelos relacionais (enforca TIMESTAMPTZ em todas as datas)
├── whatsapp/                # Integração com UazAPI / Meta API
├── migrations/              # Scripts SQL para execução no Supabase Editor
│   ├── 002_rag_mcp.sql      # Extensões vector
│   ├── 003_supabase_rls_compat.sql # Políticas de isolamento RLS para plano gratuito
│   └── 004_seed_tenant_supabase.sql # Script de carga do primeiro tenant
├── static/                  # HTMLs/CSS/JS Estáticos dos Dashboards
└── .env                     # Variáveis de ambiente secretas
```

---

## 🔒 Segurança Multi-Tenant (RLS no Supabase)

O projeto usa **Row Level Security (RLS)** nativo do Postgres para garantir que um inquilino (tenant) jamais acesse os leads, negócios ou mensagens de outro.

1. O **`TenantMiddleware`** identifica o tenant acessado a partir de:
   * Header HTTP `X-Tenant-Slug`
   * Parâmetro de Query `?tenant_slug=ludecor`
   * Subdomínio (ex: `ludecor.optimaia.com.br`)
2. Ao realizar qualquer requisição, o SQLAlchemy executa localmente dentro da transação:
   ```sql
   SELECT set_config('app.current_tenant_id', '<id_do_tenant>', true);
   ```
3. O banco de dados Supabase intercepta todas as consultas através de políticas (`USING` e `WITH CHECK`) definindo que a query só trará dados onde `tenant_id` for igual ao valor desse parâmetro temporário.

---

## 🛠️ Configuração & Inicialização com Supabase

### 1. Clonar e configurar ambiente
Duplique o arquivo `.env.example` para `.env` e configure as credenciais da API do Supabase obtidas em **Settings → API**:

```env
# Banco de Dados — Conexão Direta (porta 5432)
DATABASE_URL=postgresql+asyncpg://postgres:[SUA_SENHA]@db.[REF_PROJECT].supabase.co:5432/postgres

# Credenciais SDK Supabase
SUPABASE_URL=https://[REF_PROJECT].supabase.co
SUPABASE_ANON_KEY=[SUA_ANON_KEY]
SUPABASE_SERVICE_ROLE_KEY=[SUA_SERVICE_ROLE_KEY]

# Ambiente e Porta
ENV=development
ENVIRONMENT=development
PORT=8000
```

### 2. Inicialização Automática das Tabelas
O próprio FastAPI possui um gatilho de lifespan que cria as tabelas caso não existam no banco conectado.
Para rodar a primeira vez e fazer o upload do Schema:

```bash
# Ativar venv e instalar dependências
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Iniciar o servidor (irá criar as tabelas no Supabase automaticamente)
python -m api.main
```

### 3. Rodar as Migrações de Segurança no SQL Editor
Com as tabelas criadas no Supabase, acesse o painel web do seu **Supabase → SQL Editor → New Query** e execute na seguinte ordem:

1. **[002_rag_mcp.sql](file:///e:/optima-ia-agente-crm/migrations/002_rag_mcp.sql)**: Habilita extensões obrigatórias (`vector`).
2. **[003_supabase_rls_compat.sql](file:///e:/optima-ia-agente-crm/migrations/003_supabase_rls_compat.sql)**: Ativa o RLS em todas as tabelas e cria as regras de filtro automáticas baseadas em `app.current_tenant_id` (compatível com plano Free).
3. **[004_seed_tenant_supabase.sql](file:///e:/optima-ia-agente-crm/migrations/004_seed_tenant_supabase.sql)**: Insere o primeiro tenant (`ludecor`) e cria a agente `Lara` vinculada a ele.

---

## 📋 Acessando os Dashboards

### Painel Master (Administração Global)
Usado para criar novos tenants (empresas) e definir limites ou configurações individuais de LLM.
* **URL**: `http://localhost:8000/master`
* **Senha de Acesso (Master Key)**: Definido pela variável `MASTER_KEY` no seu `.env` (Padrão local se vazia: `optima_master_secret_key`).

### Dashboard do Cliente (CRM do Tenant)
Exibe funil de vendas, contatos qualificados e histórico de conversas do WhatsApp em tempo real.
* **URL**: `http://localhost:8000/?tenant_slug=ludecor` (Insira o slug do tenant que você criou).

---

## 💡 Informações de Desenvolvimento (Timezones & SSL)

* **Compatibilidade com Transaction Pooler (Supabase porta 6543)**: Projetos Supabase usam pooler que quebra se prepared statements forem cacheados pelo driver Python. O engine do projeto é configurado automaticamente com `statement_cache_size=0` ao detectar o host do Supabase, evitando este problema.
* **Forçamento de SSL**: O driver `asyncpg` é instruído a exigir conexão segura (`ssl="require"`) obrigatoriamente para as conexões do Supabase.
* **Mapeamento de Timezone (Fix do PostgreSQL)**: O banco PostgreSQL e o driver `asyncpg` exigem correspondência de fuso horário. Por padrão, todas as datas em [`crm/models.py`](file:///e:/optima-ia-agente-crm/crm/models.py) foram migradas para `DateTime(timezone=True)` para que os campos aceitem as datas geradas por `datetime.now(timezone.utc)` sem conflito de tipos.
