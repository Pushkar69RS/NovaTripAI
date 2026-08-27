"""travel-yantra: the JSON API under /api, the pages everywhere else."""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.web import pages

load_dotenv()

STATIC = Path(__file__).resolve().parent / "static"


def _warm_embedder() -> None:
    with suppress(Exception):  # a cold model is slow, never fatal
        from app.rag.embed import embed_query

        embed_query("Mysuru")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # ponytail: warm the local embedder off the request path so the first
    # Katha of the demo is not a ten-second wait. Nothing else to start.
    threading.Thread(target=_warm_embedder, daemon=True).start()
    yield


app = FastAPI(title="travel-yantra", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
app.include_router(router)
app.include_router(pages)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "travel-yantra"}
