"""Agent Server lifespan hooks for local LangGraph Studio development."""

from contextlib import asynccontextmanager

from starlette.applications import Starlette

from agent_graph import warm_rag_models


@asynccontextmanager
async def lifespan(app: Starlette):
    # Run once per server worker so the first visitor request does not need to
    # load the embedding and reranker models.
    warm_rag_models()
    yield


app = Starlette(lifespan=lifespan)
