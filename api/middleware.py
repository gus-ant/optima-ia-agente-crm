"""
api/middleware.py
-----------------
Middleware FastAPI para resolução de Tenant (Multi-Tenant).

Estratégias de resolução (em ordem de prioridade):
  1. Header X-Tenant-Slug (para chamadas server-to-server / N8N)
  2. Query param ?tenant_slug=<slug> (para webhooks com token no URL)
  3. Subdomínio: <slug>.optimaia.com.br (para ambiente de produção)

O middleware resolve o slug → tenant_id e:
  - Armazena no ContextVar (current_tenant_id) para o restante da requisição
  - Injeta request.state.tenant_id e request.state.tenant_slug para uso nos routers
  - Retorna 403 se o tenant não for encontrado ou estiver suspenso

Exceções (sem necessidade de tenant):
  - /health, /docs, /openapi.json, /redoc, /favicon.ico
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from crm.database import AsyncSessionLocal
from crm.tenant import current_tenant_id, resolve_tenant_by_slug

logger = logging.getLogger(__name__)

# Prefixos de rota que NÃO precisam de tenant resolvido
_EXEMPT_PREFIXES = (
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/favicon.ico",
    "/api/master",
    "/master",
)

# Domínio base da plataforma (usado para extração de subdomínio)
BASE_DOMAIN = os.getenv("BASE_DOMAIN", "optimaia.com.br")


class TenantMiddleware(BaseHTTPMiddleware):
    """
    Middleware que resolve o tenant para cada requisição.
    Funciona com FastAPI/Starlette via BaseHTTPMiddleware.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Rotas isentas de resolução de tenant
        if any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES):
            return await call_next(request)

        slug = self._extract_slug(request)

        if not slug:
            # Permite requests sem tenant em ambiente de dev local
            env = os.getenv("ENVIRONMENT", "development")
            if env == "development":
                logger.debug("TenantMiddleware: sem slug — ambiente dev, seguindo sem tenant")
                request.state.tenant_id = None
                request.state.tenant_slug = None
                return await call_next(request)
            return JSONResponse(
                status_code=400,
                content={"detail": "Tenant não identificado. Informe X-Tenant-Slug ou use o subdomínio correto."},
            )

        # Resolve slug → tenant_id consultando o banco (tabela tenants é global, sem RLS)
        async with AsyncSessionLocal() as session:
            tenant_id = await resolve_tenant_by_slug(session, slug)

        if tenant_id is None:
            logger.warning("TenantMiddleware: tenant '%s' não encontrado ou inativo", slug)
            return JSONResponse(
                status_code=403,
                content={"detail": f"Tenant '{slug}' não encontrado ou inativo."},
            )

        # Armazena no ContextVar (disponível em todo o código durante esta requisição)
        token = current_tenant_id.set(tenant_id)

        # Injeta no request.state para conveniência nos routers
        request.state.tenant_id = tenant_id
        request.state.tenant_slug = slug

        logger.debug("TenantMiddleware: tenant_id=%d slug=%s path=%s", tenant_id, slug, path)

        try:
            response = await call_next(request)
        finally:
            current_tenant_id.reset(token)

        return response

    def _extract_slug(self, request: Request) -> Optional[str]:
        """
        Extrai o slug do tenant a partir de:
        1. Header X-Tenant-Slug
        2. Query param ?tenant_slug
        3. Subdomínio (ex: ludecor.optimaia.com.br)
        """
        # 1. Header (mais confiável para N8N / server-to-server)
        slug = request.headers.get("X-Tenant-Slug")
        if slug:
            return slug.lower().strip()

        # 2. Query param (útil para webhooks que não suportam headers custom)
        slug = request.query_params.get("tenant_slug")
        if slug:
            return slug.lower().strip()

        # 3. Subdomínio
        host = request.headers.get("host", "")
        # Remove porta se presente
        host_clean = host.split(":")[0]
        if host_clean.endswith(f".{BASE_DOMAIN}"):
            subdomain = host_clean[: -len(f".{BASE_DOMAIN}")]
            if subdomain and subdomain not in ("www", "api", "app"):
                return subdomain.lower()

        return None
