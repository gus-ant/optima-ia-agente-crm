# Guia de Configuração, Ativação de Módulos e Histórico de Alterações

Este documento fornece as instruções necessárias para ativar, configurar e testar cada módulo do Agente Lara (Lu Decorações), bem como o mapeamento das alterações da migração da arquitetura baseada puramente em N8N para a nova arquitetura baseada em **LangGraph + LangChain**.

---

## 1. Histórico de Alterações (Arquitetura)

### De: Orquestração N8N (Legado)
- **Roteamento Visual:** Toda a árvore de decisão, controle de estado do lead, contagem de mensagens e regras de transbordo eram gerenciadas por nós visuais e condicionais no N8N.
- **Histórico de Mensagens:** Dependência de bancos de dados intermediários ou nós de memória do N8N para manter o contexto.
- **Extração de Dados:** Feita de forma rígida em nós LLM encadeados no N8N.

### Para: LangGraph + LangChain (Nova Arquitetura)
- **Orquestração por Grafo (LangGraph):** O fluxo conversacional agora é um grafo cíclico direcionado programático (`AgentState`). As decisões de roteamento (ir para transbordo, chamar tools) são tomadas por código determinístico e edges condicionais.
- **Gerenciamento de Estado Nativo:** LangGraph gerencia o merge do histórico usando o reducer `add_messages` e mantém a memória de curto prazo no Redis.
- **Extração Híbrida/Robusta:** Feita através de tags XML estruturadas no prompt base (`<extraction>`) e com fallback via `with_structured_output` (Pydantic) no módulo `agent/extraction.py`.
- **N8N Simplificado:** O N8N agora atua exclusivamente como trigger para rotinas temporais assíncronas (como cron de follow-up a cada 24h) e alertas de erros para canais externos (Slack/e-mail).

---

## 2. Guia de Ativação e Configuração dos Módulos

Abaixo está o passo a passo para configurar e ativar cada módulo do sistema no ambiente local ou de homologação.

### Passo 1: Configuração do Ambiente (`.env`)

Copie o arquivo `.env.example` para `.env` na raiz do projeto e preencha as variáveis correspondentes:
```bash
cp .env.example .env
```

#### Variáveis Críticas a Preencher:
*   `OPENAI_API_KEY`: Chave da OpenAI para o modelo `gpt-4o`.
*   `BITRIX24_WEBHOOK_URL`: Webhook do Bitrix24 (gerado no menu de desenvolvedor).
*   `BITRIX24_BASE_URL`: URL da sua instância Bitrix24 (ex: `https://optima.bitrix24.com.br`).
*   `REDIS_URL`: Endpoint do Redis. Para dev local com Compose, use `redis://redis:6379`.
*   `META_WEBHOOK_VERIFY_TOKEN`: Token de verificação do Webhook.

---

### Passo 2: Ativação dos Módulos Individuais

#### A. Módulo de Mensageria (WhatsApp)
O sistema suporta Meta Cloud API (oficial) ou Evolution API (self-hosted).

1.  **Meta Cloud API (Recomendado):**
    *   No `.env`, defina `WHATSAPP_PROVIDER=meta`.
    *   Configure `META_PHONE_NUMBER_ID` e `META_ACCESS_TOKEN`.
    *   Aponte o Webhook para `https://seu-dominio.com/webhook/meta`.
2.  **Evolution API (Alternativa):**
    *   No `.env`, defina `WHATSAPP_PROVIDER=evolution`.
    *   Preencha `EVOLUTION_API_URL`, `EVOLUTION_API_KEY` e `EVOLUTION_INSTANCE`.
    *   Aponte o webhook da Evolution para `https://seu-dominio.com/webhook/evolution`.

#### B. Módulo CRM (Bitrix24 / HubSpot)
1.  **Bitrix24 (Padrão):**
    *   No `.env`, defina `CRM_PROVIDER=bitrix24`.
    *   Crie um Webhook de Entrada no Bitrix24 com permissões para: **CRM (crm)** e **Atividades (activity)**.
    *   Configure a URL resultante na variável `BITRIX24_WEBHOOK_URL`.
2.  **HubSpot:**
    *   No `.env`, defina `CRM_PROVIDER=hubspot` e configure `HUBSPOT_API_KEY`.

#### C. Módulo de Persistência (Redis Store)
*   **Produção / Docker:** O Redis inicia automaticamente com o Compose e persiste via volumes.
*   **Desenvolvimento (Sem Redis):** Caso não configure o Redis local, o módulo `memory/store.py` faz fallback automático para dicionário local em memória RAM.

---

### Passo 3: Executando a Aplicação

#### Opção A: Execução Local
1.  Inicie seu ambiente virtual e instale dependências:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ```
2.  Rode o servidor FastAPI:
    ```bash
    python -m api.main
    ```

#### Opção B: Docker Compose
Suba toda a stack (Agente + Redis + N8N):
```bash
docker compose -f infra/docker-compose.yml up -d
```

---

### Passo 4: Integração com N8N (Cron Triggers)

O N8N servirá apenas como gatilho agendado para follow-ups.

1.  No N8N, crie um workflow com um **Schedule Trigger** (diário ou de 24h).
2.  Conecte a um nó **HTTP Request** apontando para o endpoint da API:
    *   **Method:** `POST`
    *   **URL:** `https://seu-dominio-da-api.com/webhook/followup` (ou via container alias se estiver na mesma rede Docker).

---

## 3. Testando o Funcionamento

Execute os testes automatizados para validar que as integrações e roteamentos estão em conformidade:

```bash
pytest tests/ -v
```
