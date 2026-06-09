---
name: run-app
description: Inicializa, monitora ou reinicia o servidor FastAPI do CRM local do Óptima IA. Use sempre que for solicitado rodar ou parar a aplicação.
license: MIT
metadata:
  version: "1.0"
---

# Skill: Executar a Aplicação Óptima IA CRM

Esta skill instrui o agente Antigravity sobre como colocar a aplicação **Óptima IA — Agente Lara × Lu Decorações** para rodar localmente, monitorar sua saúde e solucionar problemas comuns de inicialização.

## Pré-requisitos

1. **Arquivo de Ambiente (`.env`)**:
   - Certifique-se de que o arquivo `.env` existe na raiz do projeto e contém as chaves necessárias (como `OPENAI_API_KEY`, etc.).
   - Se não existir, copie do arquivo `.env.example`:
     ```powershell
     Copy-Item .env.example .env
     ```

2. **Ambiente Virtual (`.venv`)**:
   - Garanta que a pasta `.venv` existe na raiz do projeto.
   - Caso precise criar o ambiente virtual:
     ```powershell
     python -m venv .venv
     ```
   - E instale as dependências:
     ```powershell
     .venv\Scripts\pip install -r requirements.txt
     ```

## Como Rodar a Aplicação

Para iniciar o servidor FastAPI localmente, execute o Python do ambiente virtual apontando para o módulo da API:

```powershell
.venv\Scripts\python -m api.main
```

> [!NOTE]
> No Windows, chamar `.venv\Scripts\python` diretamente garante que o interpretador correto com as dependências instaladas seja usado, sem a necessidade de ativar o ambiente virtual no terminal de forma persistente.

### Rodar em Segundo Plano (Background Task)

Se você estiver executando o comando através do Antigravity e precisar que o terminal continue livre para outras tarefas, use a ferramenta `run_command` com `WaitMsBeforeAsync` ajustado para um valor baixo (ex: `1000`) ou execute como tarefa de segundo plano.

## Como Verificar a Saúde do Servidor

Uma vez iniciado o servidor (por padrão na porta `8000`), a API expõe uma rota de monitoramento. Você pode verificar se o servidor está ativo acessando a rota `/health/`:

- **URL Local**: `http://localhost:8000/health/`
- **Comando de Teste (PowerShell)**:
  ```powershell
  Invoke-RestMethod -Uri "http://localhost:8000/health"
  ```

Retorno esperado (JSON):
```json
{
  "status": "ok",
  "database": "connected",
  "redis": "connected/fallback_local",
  "agent": "ready"
}
```

## Como Parar a Aplicação

Se o servidor foi iniciado como uma tarefa em segundo plano (`background task`) pelo Antigravity, você pode usar a ferramenta `manage_task` com a ação `kill` especificando o `TaskId` da tarefa de execução.

Se estiver rodando em uma porta específica que você precisa liberar, você pode encontrar e encerrar o processo no Windows:

1. **Encontrar o PID usando a porta (ex: 8000)**:
   ```powershell
   Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
   ```
2. **Encerrar o processo**:
   ```powershell
   Stop-Process -Id <PID> -Force
   ```

## Solução de Problemas

- **Erro de Porta já em Uso (`Address already in use`)**:
  - Outro processo está escutando na porta `8000`. Encontre o processo e encerre-o usando os comandos acima, ou mude a porta no arquivo `.env` alterando o valor de `PORT=8000`.
- **Erro de Módulo não Encontrado (`ModuleNotFoundError`)**:
  - Certifique-se de estar executando a aplicação a partir do diretório raiz (`e:\optima-ia-agente-crm`) com o comando completo `.venv\Scripts\python -m api.main` (o parâmetro `-m` é crucial para resolver os paths dos módulos corretamente).
- **Falha de Inicialização do Banco de Dados**:
  - O banco SQLite local é criado automaticamente na inicialização (`optimacrm.db`). Certifique-se de ter permissão de escrita na raiz do projeto.
