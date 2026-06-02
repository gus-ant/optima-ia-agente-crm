from fastapi import APIRouter, HTTPException, Depends, Header, Request
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
import os
import uuid

from crm.database import get_db_session
from crm.models import Tenant, AgentConfig, MCPServer

router = APIRouter(prefix="/api/master", tags=["master"])

MASTER_KEY = os.getenv("MASTER_KEY", "optima_master_secret_key")

def verify_master_key(x_master_key: str = Header(...)):
    if x_master_key != MASTER_KEY:
        raise HTTPException(status_code=403, detail="Invalid Master Key")
    return True

class MCPServerSchema(BaseModel):
    id: Optional[int] = None
    name: str
    command: str
    args: List[str]
    env: Dict[str, str] = {}

class AgentConfigSchema(BaseModel):
    llm_model: Optional[str] = None
    system_prompt: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    human_agent_whatsapp: Optional[str] = None

class TenantCreateSchema(BaseModel):
    slug: str
    name: str
    plan: str = "basic"
    is_active: bool = True
    llm_model: Optional[str] = None
    system_prompt: Optional[str] = None

class TenantUpdateSchema(BaseModel):
    name: Optional[str] = None
    plan: Optional[str] = None
    is_active: Optional[bool] = None

class TenantOutSchema(BaseModel):
    id: int
    slug: str
    name: str
    plan: str
    is_active: bool
    created_at: Any

@router.get("/stats", dependencies=[Depends(verify_master_key)])
async def get_master_stats():
    try:
        async with get_db_session() as session:
            t_stmt = select(func.count(Tenant.id))
            t_res = await session.execute(t_stmt)
            total_tenants = t_res.scalar() or 0

            active_stmt = select(func.count(Tenant.id)).where(Tenant.status == "active")
            active_res = await session.execute(active_stmt)
            active_tenants = active_res.scalar() or 0

            return {
                "total_tenants": total_tenants,
                "active_tenants": active_tenants
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tenants", response_model=List[TenantOutSchema], dependencies=[Depends(verify_master_key)])
async def get_tenants():
    try:
        async with get_db_session() as session:
            stmt = select(Tenant).order_by(Tenant.criado_em.desc())
            res = await session.execute(stmt)
            tenants = res.scalars().all()
            return [
                {
                    "id": t.id,
                    "slug": t.slug,
                    "name": t.nome,
                    "plan": t.plano.value if hasattr(t.plano, 'value') else t.plano,
                    "is_active": t.status == "active" or (hasattr(t.status, 'value') and t.status.value == "active"),
                    "created_at": t.criado_em
                } for t in tenants
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tenants", response_model=TenantOutSchema, dependencies=[Depends(verify_master_key)])
async def create_tenant(data: TenantCreateSchema):
    try:
        async with get_db_session() as session:
            # Check if slug exists
            stmt = select(Tenant).where(Tenant.slug == data.slug)
            res = await session.execute(stmt)
            if res.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Slug already exists")

            tenant = Tenant(
                slug=data.slug,
                nome=data.name,
                plano=data.plan,
                status="active" if data.is_active else "suspended"
            )
            session.add(tenant)
            await session.flush() # get id
            
            # create agent config
            config = AgentConfig(
                tenant_id=tenant.id,
                llm_model=data.llm_model,
                system_prompt=data.system_prompt
            )
            session.add(config)
            
            # Note: session will commit automatically when asynccontextmanager exits
            return {
                "id": tenant.id,
                "slug": tenant.slug,
                "name": tenant.nome,
                "plan": tenant.plano,
                "is_active": tenant.status == "active",
                "created_at": tenant.criado_em
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/tenants/{tenant_id}", dependencies=[Depends(verify_master_key)])
async def update_tenant(tenant_id: int, data: TenantUpdateSchema):
    try:
        async with get_db_session() as session:
            stmt = select(Tenant).where(Tenant.id == tenant_id)
            res = await session.execute(stmt)
            tenant = res.scalar_one_or_none()
            if not tenant:
                raise HTTPException(status_code=404, detail="Tenant not found")
            
            if data.name is not None:
                tenant.nome = data.name
            if data.plan is not None:
                tenant.plano = data.plan
            if data.is_active is not None:
                tenant.status = "active" if data.is_active else "suspended"
                
            return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tenants/{tenant_id}/agent-config", dependencies=[Depends(verify_master_key)])
async def get_agent_config(tenant_id: int):
    try:
        async with get_db_session() as session:
            stmt = select(AgentConfig).where(AgentConfig.tenant_id == tenant_id)
            res = await session.execute(stmt)
            config = res.scalar_one_or_none()
            if not config:
                return {}
            return {
                "llm_model": config.llm_model,
                "system_prompt": config.system_prompt,
                "temperature": config.temperatura,
                "max_tokens": None, # max_tokens was removed
                "human_agent_whatsapp": config.human_agent_whatsapp
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/tenants/{tenant_id}/agent-config", dependencies=[Depends(verify_master_key)])
async def update_agent_config(tenant_id: int, data: AgentConfigSchema):
    try:
        async with get_db_session() as session:
            stmt = select(AgentConfig).where(AgentConfig.tenant_id == tenant_id)
            res = await session.execute(stmt)
            config = res.scalar_one_or_none()
            if not config:
                config = AgentConfig(tenant_id=tenant_id)
                session.add(config)
            
            if data.llm_model is not None: config.llm_model = data.llm_model
            if data.system_prompt is not None: config.system_prompt = data.system_prompt
            if data.temperature is not None: config.temperatura = data.temperature
            if data.human_agent_whatsapp is not None: config.human_agent_whatsapp = data.human_agent_whatsapp
            
            return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tenants/{tenant_id}/mcp-servers", response_model=List[MCPServerSchema], dependencies=[Depends(verify_master_key)])
async def get_mcp_servers(tenant_id: int):
    try:
        async with get_db_session() as session:
            stmt = select(MCPServer).where(MCPServer.tenant_id == tenant_id)
            res = await session.execute(stmt)
            servers = res.scalars().all()
            return [
                {
                    "id": s.id,
                    "name": s.name,
                    "command": s.command,
                    "args": s.args,
                    "env": s.env
                } for s in servers
            ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/tenants/{tenant_id}/mcp-servers", dependencies=[Depends(verify_master_key)])
async def add_mcp_server(tenant_id: int, data: MCPServerSchema):
    try:
        async with get_db_session() as session:
            server = MCPServer(
                tenant_id=tenant_id,
                name=data.name,
                command=data.command,
                args=data.args,
                env=data.env
            )
            session.add(server)
            return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/tenants/{tenant_id}/mcp-servers/{server_id}", dependencies=[Depends(verify_master_key)])
async def delete_mcp_server(tenant_id: int, server_id: int):
    try:
        async with get_db_session() as session:
            stmt = select(MCPServer).where(MCPServer.id == server_id, MCPServer.tenant_id == tenant_id)
            res = await session.execute(stmt)
            server = res.scalar_one_or_none()
            if not server:
                raise HTTPException(status_code=404, detail="Server not found")
            await session.delete(server)
            return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
