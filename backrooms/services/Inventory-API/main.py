"""FastAPI entrypoint for the Nexova Inventory API.

Run from this folder:

    uvicorn main:app --reload

On startup the service creates the inventory schema in Supabase and wires the
``/inventory`` router. TinyDB auth is reused from the existing Supply Directory
service, so the app talks to both databases simultaneously.
"""

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# The folder name contains a hyphen, so this module is run as a standalone app
# root: internal modules live at the top level (``database``, ``routers``) and
# ``backrooms`` is on the path so ``services.Supply_directory_API`` is importable.
BASE_DIR = Path(__file__).resolve().parent
BACKROOMS_ROOT = BASE_DIR.parent.parent
for candidate in (BASE_DIR, BACKROOMS_ROOT):
	if str(candidate) not in sys.path:
		sys.path.insert(0, str(candidate))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from database import init_inventory_schema
from routers.inventory import router as inventory_router
from schemas import HealthResponse
from services.telemetry.router import router as telemetry_router


@asynccontextmanager
async def lifespan(app: FastAPI):
	init_inventory_schema()
	yield


app = FastAPI(title="Nexova Inventory API", lifespan=lifespan)

allowed_origins = [
	origin.strip()
	for origin in os.getenv(
		"INVENTORY_ALLOWED_ORIGINS",
		"http://localhost:3000,http://localhost:3001",
	).split(",")
	if origin.strip()
]

app.add_middleware(
	CORSMiddleware,
	allow_origins=allowed_origins,
	allow_credentials=False,
	allow_methods=["*"],
	allow_headers=["*"],
)

app.include_router(inventory_router)
app.include_router(telemetry_router)


@app.get("/", response_model=HealthResponse)
def root() -> HealthResponse:
	return HealthResponse(status="ok", service="inventory")
