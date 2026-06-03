from fastapi import FastAPI
from contextlib import asynccontextmanager

from database import init_db
from routers import metrics, commands, status, auth, dashboard_api, idrac


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="SX Monitor Server", lifespan=lifespan)

# Agent-facing
app.include_router(metrics.router)
app.include_router(commands.router)
app.include_router(status.router)

# Dashboard-facing
app.include_router(auth.router)
app.include_router(dashboard_api.router)

# iDRAC Redfish event receiver
app.include_router(idrac.router)


@app.get("/health")
def health():
    return {"ok": True}
