from fastapi import APIRouter
from .endpoints.nodes import router as nodes_router

api_router = APIRouter()
api_router.include_router(nodes_router)