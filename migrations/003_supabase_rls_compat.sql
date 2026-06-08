-- migrations/003_supabase_rls_compat.sql
-- ==============================================
-- Migration: RLS Multi-Tenant Compatível com Supabase (Plano Free)
-- ==============================================
-- Diferenças em relação ao 001_multitenant_rls.sql:
--   - NÃO cria roles customizadas (optima_app, master_admin) —
--     requer plano Pro do Supabase. Usa a role 'postgres' padrão.
--   - Usa NULLIF para lidar com a ausência do parâmetro de runtime
--     sem lançar exceção (safe current_setting).
--   - Políticas usam USING + WITH CHECK para cobrir SELECT e INSERT/UPDATE.
--   - Idempotente: pode ser executado múltiplas vezes sem erro.
--
-- Como executar:
--   Supabase Dashboard → SQL Editor → New Query → colar e executar
--
-- PRÉ-REQUISITO: as tabelas devem existir (rodar a aplicação uma vez
--   com DATABASE_URL apontando pro Supabase para criar via SQLAlchemy).
-- ==============================================


-- ---------------------------------------------------------------------------
-- 1. Habilitar RLS nas tabelas protegidas
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS contatos       ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS negocios       ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS atividades     ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS agendamentos   ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS agent_configs  ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS knowledge_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS tenant_mcp_servers  ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS mcp_servers         ENABLE ROW LEVEL SECURITY;

-- tenants: SEM RLS — tabela global, lida apenas pelo master/admin
-- (não aplicar RLS aqui para que o TenantMiddleware possa resolver slugs)


-- ---------------------------------------------------------------------------
-- 2. Helper: extrai o tenant_id do parâmetro de runtime de forma segura
--    Retorna NULL se o parâmetro não estiver definido (sem exceção)
-- ---------------------------------------------------------------------------
-- O Python injeta via: SELECT set_config('app.current_tenant_id', '<id>', true)
-- O 'true' = LOCAL (válido apenas na transação corrente — mais seguro)


-- ---------------------------------------------------------------------------
-- 3. Drop de políticas antigas (idempotência — evita erro "already exists")
-- ---------------------------------------------------------------------------

DROP POLICY IF EXISTS rls_contatos         ON contatos;
DROP POLICY IF EXISTS rls_negocios         ON negocios;
DROP POLICY IF EXISTS rls_atividades       ON atividades;
DROP POLICY IF EXISTS rls_agendamentos     ON agendamentos;
DROP POLICY IF EXISTS rls_agent_configs    ON agent_configs;
DROP POLICY IF EXISTS rls_knowledge_docs   ON knowledge_documents;
DROP POLICY IF EXISTS rls_mcp_servers      ON mcp_servers;
DROP POLICY IF EXISTS rls_tenant_mcp       ON tenant_mcp_servers;

-- Remove políticas do script antigo se existirem
DROP POLICY IF EXISTS tenant_isolation_contatos    ON contatos;
DROP POLICY IF EXISTS tenant_isolation_negocios    ON negocios;
DROP POLICY IF EXISTS tenant_isolation_atividades  ON atividades;
DROP POLICY IF EXISTS tenant_isolation_agent_configs ON agent_configs;
DROP POLICY IF EXISTS knowledge_documents_isolation_policy ON knowledge_documents;
DROP POLICY IF EXISTS mcp_servers_isolation_policy ON tenant_mcp_servers;


-- ---------------------------------------------------------------------------
-- 4. Criar políticas de isolamento por tenant_id
--    Usa NULLIF para retornar NULL (sem erro) quando o parâmetro não existe
-- ---------------------------------------------------------------------------

-- CONTATOS: filtra diretamente pelo tenant_id da linha
CREATE POLICY rls_contatos ON contatos
    USING (
        tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
    )
    WITH CHECK (
        tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
    );

-- AGENT_CONFIGS: filtra diretamente pelo tenant_id
CREATE POLICY rls_agent_configs ON agent_configs
    USING (
        tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
    )
    WITH CHECK (
        tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
    );

-- NEGOCIOS: tenant_id copiado do contato (JOIN + redundância)
-- O campo tenant_id em negocios é adicionado via migration para performance
CREATE POLICY rls_negocios ON negocios
    USING (
        contato_id IN (
            SELECT id FROM contatos
            WHERE tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
        )
    )
    WITH CHECK (
        contato_id IN (
            SELECT id FROM contatos
            WHERE tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
        )
    );

-- ATIVIDADES: via join com contatos
CREATE POLICY rls_atividades ON atividades
    USING (
        contato_id IN (
            SELECT id FROM contatos
            WHERE tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
        )
    )
    WITH CHECK (
        contato_id IN (
            SELECT id FROM contatos
            WHERE tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
        )
    );

-- AGENDAMENTOS: via join com contatos
CREATE POLICY rls_agendamentos ON agendamentos
    USING (
        contato_id IN (
            SELECT id FROM contatos
            WHERE tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
        )
    )
    WITH CHECK (
        contato_id IN (
            SELECT id FROM contatos
            WHERE tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
        )
    );

-- KNOWLEDGE_DOCUMENTS: filtra diretamente pelo tenant_id
CREATE POLICY rls_knowledge_docs ON knowledge_documents
    USING (
        tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
    )
    WITH CHECK (
        tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
    );

-- MCP_SERVERS (tabela legada, se existir)
CREATE POLICY rls_mcp_servers ON mcp_servers
    USING (
        tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
    )
    WITH CHECK (
        tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
    );

-- TENANT_MCP_SERVERS: filtra diretamente pelo tenant_id
CREATE POLICY rls_tenant_mcp ON tenant_mcp_servers
    USING (
        tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
    )
    WITH CHECK (
        tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer
    );


-- ---------------------------------------------------------------------------
-- 5. Índices complementares para performance das policies de RLS
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_contatos_tenant_id      ON contatos(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agent_configs_tenant_id ON agent_configs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_negocios_contato_id     ON negocios(contato_id);
CREATE INDEX IF NOT EXISTS idx_atividades_contato_id   ON atividades(contato_id);
CREATE INDEX IF NOT EXISTS idx_agendamentos_contato_id ON agendamentos(contato_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_tenant_id     ON knowledge_documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_mcp_tenant_id           ON tenant_mcp_servers(tenant_id);


-- ---------------------------------------------------------------------------
-- 6. Verificação final — exibe status do RLS em cada tabela
-- ---------------------------------------------------------------------------

SELECT
    tablename,
    rowsecurity        AS "RLS Habilitado"
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN (
      'tenants', 'contatos', 'negocios', 'atividades',
      'agendamentos', 'agent_configs', 'knowledge_documents',
      'tenant_mcp_servers', 'mcp_servers'
  )
ORDER BY tablename;
