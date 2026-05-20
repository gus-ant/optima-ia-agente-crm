# Óptima IA — Agente de Qualificação + CRM Integrado (Empresa Lu Decorações)

Automação do atendimento inicial e qualificação de leads via WhatsApp para o setor de decoração de eventos. O agente conduz conversas humanizadas, extrai dados estruturados e atualiza o pipeline de CRM em tempo real.

## Stack

- **Orquestração:** N8N (self-hosted)
- **Canal:** WhatsApp Cloud API (Meta) ou Evolution API
- **LLM:** OpenAI GPT-4o / Anthropic Claude
- **CRM:** Bitrix24 / HubSpot
- **Infra:** Docker + VPS (Hetzner/DigitalOcean)

## Estrutura do Repositório
```
├── flows/          # Fluxos N8N exportados em JSON
├── prompts/        # System prompts versionados em Markdown
├── schemas/        # JSON schemas de extração de dados
├── infra/          # docker-compose.yml e configs de servidor
└── docs/           # Documentação técnica e plano de implantação
```

## Como usar

1. Clone o repositório e copie `.env.example` para `.env`
2. Preencha as variáveis de ambiente (chaves de API, credenciais do CRM)
3. Suba o stack com `docker compose up -d`
4. Importe os fluxos da pasta `flows/` no painel do N8N
5. Configure o webhook no Meta Business ou Evolution API

## Variáveis de Ambiente

Por favor, colocar no Dotenv:

| Variável | Descrição |
|---|---|
| `OPENAI_API_KEY` | Chave da API OpenAI |
| `META_WEBHOOK_TOKEN` | Token de verificação do webhook Meta |
| `CRM_API_KEY` | Chave de API do CRM (Bitrix24/HubSpot) |
| `N8N_ENCRYPTION_KEY` | Chave de criptografia do N8N |
| `DB_PASSWORD` | Senha do PostgreSQL |

## Cliente

Desenvolvido para **Lu Decorações** pela **Óptima IA**.  
Documentação completa em `docs/Plano_Implementacao.pdf`.
