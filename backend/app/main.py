import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager

from azure.monitor.opentelemetry import configure_azure_monitor
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import _logs, trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from app.config import settings
from app.dependencies import (
    get_blob_service,
    get_cosmos_service,
    get_mcp_service,
    get_redis_service,
)
from app.redis_listener import RedisListener
from app.routers import (
    accounts_router,
    chat_router,
    document_router,
    room_router,
    test_router,
    websocket_router,
)

if settings.APPLICATIONINSIGHTS_CONNECTION_STRING:
    configure_azure_monitor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown events.
    """
    async with AsyncExitStack() as stack:
        # Register the MCP lifespan
        await stack.enter_async_context(mcp_app.lifespan(mcp_app))

        # Start up
        listener = RedisListener()
        subscribe_task = asyncio.create_task(listener.listen())

        logger.info("Application and MCP startup complete.")

        yield

        # Shutdown
        subscribe_task.cancel()
        try:
            await subscribe_task
        except asyncio.CancelledError:
            pass

        await get_blob_service().close()
        await get_cosmos_service().close()
        await get_redis_service().close()

        # OpenTelemetry
        tracer_provider = trace.get_tracer_provider()
        if hasattr(tracer_provider, "shutdown"):
            tracer_provider.shutdown()
        logger_provider = _logs.get_logger_provider()
        if hasattr(logger_provider, "shutdown"):
            logger_provider.shutdown()


app = FastAPI(lifespan=lifespan)

origins = [
    "http://localhost",
    "http://localhost:3000",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
    "https://thankful-bay-09ec9cf1e.2.azurestaticapps.net",  # Frontend URL
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["mcp-session-id"],
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

FastAPIInstrumentor.instrument_app(app)

mcp_service = get_mcp_service()
mcp_app = mcp_service.get_app()
app.mount("/mcp", mcp_app)

app.include_router(accounts_router.router)
app.include_router(chat_router.router)
app.include_router(document_router.router)
app.include_router(room_router.router)
app.include_router(test_router.router)
app.include_router(websocket_router.router)

# Then mount the static files at the root
# app.mount("/", StaticFiles(directory="path/to/frontend/build", html=True), name="static")


@app.get("/")
def test():
    return {"status": "ok"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}
