-- migrations/001_multitenant_rls.sql
-- ===================================
-- Migration: Multi-Tenant com Row Level Security (RLS)
-- Executar como superusuário do PostgreSQL (ou role com CREATEROLE)
--
-- Aplica isolamento por tenant_id nas tabelas: contatos, negocios, atividades, agent_configs
-- A tabela tenants é GLOBAL (sem RLS) — acessada apenas pelo Master/Admin.
--
-- Uso:
--   psql -U postgres -d optima_crm -f migrations/001_multitenant_rls.sql

-- ---------------------------------------------------------------------------
-- 1. Adiciona tenant_id às tabelas existentes (idempotente via IF NOT EXISTS)
-- ---------------------------------------------------------------------------

ALTER TABLE contatos
    ADD COLUMN IF NOT EXISTS tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE;

ALTER TABLE negocios
    ADD COLUMN IF NOT EXISTS tenant_id INTEGER;

ALTER TABLE atividades
    ADD COLUMN IF NOT EXISTS tenant_id INTEGER;

ALTER TABLE agent_configs
    ADD COLUMN IF NOT EXISTS tenant_id INTEGER REFERENCES tenants(id) ON DELETE CASCADE;

-- Cria índices para performance
CREATE INDEX IF NOT EXISTS idx_contatos_tenant_id ON contatos(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agent_configs_tenant_id ON agent_configs(tenant_id);

-- ---------------------------------------------------------------------------
-- 2. Popula tenant_id nas tabelas filhas (negocios e atividades via JOIN)
-- ---------------------------------------------------------------------------
-- Executar apenas se houver dados legados a migrar:
-- UPDATE negocios n SET tenant_id = c.tenant_id
--     FROM contatos c WHERE n.contato_id = c.id AND n.tenant_id IS NULL;
-- UPDATE atividades a SET tenant_id = c.tenant_id
--     FROM contatos c WHERE a.contato_id = c.id AND a.tenant_id IS NULL;

-- ---------------------------------------------------------------------------
-- 3. Habilita RLS nas tabelas protegidas
-- ---------------------------------------------------------------------------

ALTER TABLE contatos    ENABLE ROW LEVEL SECURITY;
ALTER TABLE negocios    ENABLE ROW LEVEL SECURITY;
ALTER TABLE atividades  ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_configs ENABLE ROW LEVEL SECURITY;

-- Garante que superuser vê tudo (para migrations e diagnósticos)
ALTER TABLE contatos    FORCE ROW LEVEL SECURITY;
ALTER TABLE negocios    FORCE ROW LEVEL SECURITY;
ALTER TABLE atividades  FORCE ROW LEVEL SECURITY;
ALTER TABLE agent_configs FORCE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- 4. Cria role da aplicação (se não existir)
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'optima_app') THEN
        CREATE ROLE optima_app LOGIN PASSWORD 'troque_em_producao';
    END IF;
END
$$;

-- Garante permissões necessárias
GRANT CONNECT ON DATABASE optima_crm TO optima_app;
GRANT USAGE ON SCHEMA public TO optima_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO optima_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO optima_app;

-- ---------------------------------------------------------------------------
-- 5. DROP de políticas antigas (idempotência)
-- ---------------------------------------------------------------------------

DROP POLICY IF EXISTS tenant_isolation_contatos    ON contatos;
DROP POLICY IF EXISTS tenant_isolation_negocios    ON negocios;
DROP POLICY IF EXISTS tenant_isolation_atividades  ON atividades;
DROP POLICY IF EXISTS tenant_isolation_agent_configs ON agent_configs;

-- ---------------------------------------------------------------------------
-- 6. Cria políticas de isolamento usando parâmetro de runtime
--    O Python injeta: SET LOCAL "app.current_tenant_id" = '<id>'
--    dentro da transação antes de qualquer query.
-- ---------------------------------------------------------------------------

-- Contatos: filtra diretamente pelo tenant_id da linha
CREATE POLICY tenant_isolation_contatos ON contatos
    TO optima_app
    USING (tenant_id = current_setting('app.current_tenant_id', true)::INTEGER);

-- Negocios: filtra via JOIN implícito — o tenant_id é copiado de contatos
-- Abordagem: adicionar tenant_id redundante em negocios para performance
CREATE POLICY tenant_isolation_negocios ON negocios
    TO optima_app
    USING (
        contato_id IN (
            SELECT id FROM contatos
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::INTEGER
        )
    );

-- Atividades: mesma abordagem de subquery
CREATE POLICY tenant_isolation_atividades ON atividades
    TO optima_app
    USING (
        contato_id IN (
            SELECT id FROM contatos
            WHERE tenant_id = current_setting('app.current_tenant_id', true)::INTEGER
        )
    );

-- AgentConfig: filtra diretamente
CREATE POLICY tenant_isolation_agent_configs ON agent_configs
    TO optima_app
    USING (tenant_id = current_setting('app.current_tenant_id', true)::INTEGER);

-- ---------------------------------------------------------------------------
-- 7. Tabela tenants: SEM RLS (visível globalmente para roteamento e auth)
--    Apenas a role master_admin pode INSERT/UPDATE/DELETE
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'master_admin') THEN
        CREATE ROLE master_admin LOGIN PASSWORD 'troque_master_em_producao';
    END IF;
END
$$;

GRANT ALL ON tenants TO master_admin;
-- optima_app só pode ler tenants (para resolver slug → tenant_id)
GRANT SELECT ON tenants TO optima_app;

-- ---------------------------------------------------------------------------
-- 8. Unique constraint (tenant_id, whatsapp_id) em contatos
-- ---------------------------------------------------------------------------

ALTER TABLE contatos
    DROP CONSTRAINT IF EXISTS uq_contatos_tenant_whatsapp;

ALTER TABLE contatos
    ADD CONSTRAINT uq_contatos_tenant_whatsapp UNIQUE (tenant_id, whatsapp_id);

-- Remove unique constraint global antiga se existir
ALTER TABLE contatos
    DROP CONSTRAINT IF EXISTS contatos_whatsapp_id_key;

-- ---------------------------------------------------------------------------
-- 9. Insere tenant de exemplo para desenvolvimento local
-- ---------------------------------------------------------------------------

INSERT INTO tenants (slug, nome, status, plano, config)
VALUES (
    'ludecor',
    'Lu Decorações',
    'active',
    'pro',
    '{
        "whatsapp_number": "5511999998888",
        "webhook_token": "ludecor_token_dev"
    }'::jsonb
)
ON CONFLICT (slug) DO NOTHING;

-- Insere AgentConfig padrão para o tenant de exemplo
INSERT INTO agent_configs (tenant_id, nome_agente, temperatura, ativo)
SELECT id, 'Lara', 0.3, true
FROM tenants WHERE slug = 'ludecor'
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Verificação final
-- ---------------------------------------------------------------------------

SELECT
    schemaname,
    tablename,
    rowsecurity AS "RLS Enabled"
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('tenants', 'contatos', 'negocios', 'atividades', 'agent_configs')
ORDER BY tablename;
