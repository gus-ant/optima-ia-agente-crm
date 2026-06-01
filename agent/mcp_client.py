"""
agent/mcp_client.py
-------------------
Integração com o Model Context Protocol (MCP).
Permite que o Agente Lara consuma ferramentas dinâmicas de ERPs e CRMs terceiros.
"""

from __future__ import annotations

import logging
import shlex
from typing import List, Callable

from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)

async def get_mcp_tools_for_tenant(tenant_id: int) -> List[StructuredTool]:
    """
    Conecta-se aos servidores MCP configurados pelo tenant e retorna as 
    ferramentas mapeadas para o formato do LangChain (StructuredTool).
    
    Nota: O SDK do MCP estabelece conexões STDIO/SSE. Em produção, essas conexões 
    podem ser persistidas em um pool de conexões para evitar overhead.
    """
    from sqlalchemy import select
    from crm.database import get_db_session
    from crm.models import TenantMCPServer
    
    async with get_db_session() as session:
        stmt = select(TenantMCPServer).where(
            TenantMCPServer.tenant_id == tenant_id,
            TenantMCPServer.ativo == True
        )
        result = await session.execute(stmt)
        servers = result.scalars().all()

    tools = []
    
    if not servers:
        return tools

    # Requer `mcp` SDK instalado
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        logger.warning("SDK do MCP não encontrado. Ignorando ferramentas MCP.")
        return tools

    for server in servers:
        if server.transport_type != "stdio":
            logger.warning("Transporte %s não suportado neste momento.", server.transport_type)
            continue
            
        logger.info("Carregando ferramentas do MCP Server: %s (Tenant %d)", server.name, tenant_id)
        cmd_parts = shlex.split(server.url_or_command)
        
        try:
            # Em uma arquitetura serverless, isso idealmente faria lazy load ou usaria um connection pool.
            # Como prova de conceito arquitetural, inicializamos aqui para demonstrar o discovery dinâmico.
            server_params = StdioServerParameters(
                command=cmd_parts[0],
                args=cmd_parts[1:],
                env=server.env_config
            )
            
            # TODO: O uso de context managers (async with) para stdio_client fecharia a conexão
            # assim que saíssemos desta função. O LangChain tool precisa chamar a conexão quando
            # o LLM decidir usá-la. 
            # Como implementação proxy, a tool LangChain, ao ser invocada, fará a conexão MCP
            # executará a tool_call respectiva, e retornará o resultado.
            
            # Aqui construiríamos as tools com base nas descrições persistidas/cacheadas no banco,
            # ou faríamos uma chamada MCP de discovery prévia.
            
            pass
            
        except Exception as exc:
            logger.error("Erro ao configurar MCP server %s: %s", server.name, exc)

    return tools
