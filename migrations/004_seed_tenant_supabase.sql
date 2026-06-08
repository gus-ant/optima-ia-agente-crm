-- migrations/004_seed_tenant_supabase.sql
-- =========================================
-- Seed: Cria o primeiro tenant e AgentConfig no Supabase
-- =========================================
-- Adapte os valores abaixo para o seu tenant real antes de executar.
-- Execute no SQL Editor do Supabase APÓS rodar a aplicação uma vez
-- (para que as tabelas existam) e APÓS o 003_supabase_rls_compat.sql.
-- =========================================

-- ---------------------------------------------------------------------------
-- Tenant: Lu Decorações (exemplo — altere slug, nome e config)
-- ---------------------------------------------------------------------------

INSERT INTO tenants (slug, nome, status, plano, config, criado_em, atualizado_em)
VALUES (
    'ludecor',                         -- slug único (usado no subdomínio e header X-Tenant-Slug)
    'Lu Decorações',                    -- nome exibido no painel
    'ACTIVE',                           -- status: ACTIVE | SUSPENDED | TRIAL | CANCELLED
    'PRO',                              -- plano: BASIC | PRO | ENTERPRISE
    jsonb_build_object(
        'whatsapp_number', '5511999998888',  -- número WhatsApp do tenant (sem +)
        'webhook_token', 'ludecor_token_dev' -- token de verificação do webhook (opcional)
    ),
    NOW(),
    NOW()
)
ON CONFLICT (slug) DO UPDATE
    SET nome         = EXCLUDED.nome,
        status       = EXCLUDED.status,
        plano        = EXCLUDED.plano,
        config       = EXCLUDED.config,
        atualizado_em = NOW();

-- ---------------------------------------------------------------------------
-- AgentConfig: configuração padrão da Lara para o tenant
-- ---------------------------------------------------------------------------

INSERT INTO agent_configs (
    tenant_id,
    nome_agente,
    system_prompt,
    llm_model,
    temperatura,
    human_agent_whatsapp,
    ativo,
    criado_em
)
SELECT
    t.id,
    'Lara',                             -- nome do agente exibido nos logs
    NULL,                               -- NULL = usa o LARA_SYSTEM_PROMPT padrão do código
    NULL,                               -- NULL = usa o modelo padrão do plano (pro → gpt-4o)
    0.3,                                -- temperatura do LLM
    '5511999990000',                    -- WhatsApp do atendente humano (transbordo)
    true,
    NOW()
FROM tenants t
WHERE t.slug = 'ludecor'
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- Verificação: exibe os registros criados
-- ---------------------------------------------------------------------------

SELECT
    t.id        AS tenant_id,
    t.slug,
    t.nome,
    t.status,
    t.plano,
    t.config,
    ac.nome_agente,
    ac.temperatura,
    ac.ativo    AS agente_ativo
FROM tenants t
LEFT JOIN agent_configs ac ON ac.tenant_id = t.id
ORDER BY t.id;
