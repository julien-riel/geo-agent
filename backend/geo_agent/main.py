from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from geo_agent.agent.registry import init_services
from geo_agent.config import get_settings
from geo_agent.routes.copilotkit import mount_copilotkit
from geo_agent.routes.datasets import router as datasets_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_services(settings)
    mount_copilotkit(app, settings)
    yield


app = FastAPI(title="Géo-agent backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(datasets_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
