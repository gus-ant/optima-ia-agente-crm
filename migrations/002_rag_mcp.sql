-- migrations/002_rag_mcp.sql
-- Habilita pgvector e cria tabelas para RAG e servidores MCP

CREATE EXTENSION IF NOT EXISTS vector;

-- Tabela de Documentos (Knowledge)
CREATE TABLE IF NOT EXISTS knowledge_documents (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'processing',
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_knowledge_documents_tenant_id ON knowledge_documents(tenant_id);

ALTER TABLE knowledge_documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY knowledge_documents_isolation_policy ON knowledge_documents
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer);

-- Tabela de Servidores MCP
CREATE TABLE IF NOT EXISTS tenant_mcp_servers (
    id SERIAL PRIMARY KEY,
    tenant_id INTEGER NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    transport_type VARCHAR(50) NOT NULL DEFAULT 'stdio',
    url_or_command VARCHAR(255) NOT NULL,
    env_config JSONB,
    ativo BOOLEAN NOT NULL DEFAULT true,
    criado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_tenant_mcp_servers_tenant_id ON tenant_mcp_servers(tenant_id);

ALTER TABLE tenant_mcp_servers ENABLE ROW LEVEL SECURITY;
CREATE POLICY mcp_servers_isolation_policy ON tenant_mcp_servers
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::integer);
