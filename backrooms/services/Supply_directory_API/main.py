import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# This service is normally imported as ``services.Supply_directory_API.main`` by
# the test suite, but it can also be launched directly with ``uvicorn main:app``
# from this folder. Put ``backrooms`` on sys.path so the absolute ``services.*``
# imports below resolve in both cases.
BACKROOMS_ROOT = Path(__file__).resolve().parent.parent.parent
if str(BACKROOMS_ROOT) not in sys.path:
	sys.path.insert(0, str(BACKROOMS_ROOT))

from services.Supply_directory_API.routes.auth import router as auth_router
from services.Supply_directory_API.routes.profiles import router as profiles_router
from services.Supply_directory_API.routes.suppliers import router as suppliers_router
from services.Supply_directory_API.routes.users import router as users_router


app = FastAPI(title="Nexova Supplier Directory API")

allowed_origins = [
	origin.strip()
	for origin in os.getenv(
		"SUPPLIERS_ALLOWED_ORIGINS",
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

app.include_router(suppliers_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(profiles_router)


@app.get("/")
def root() -> dict[str, str]:
	return {"status": "ok", "service": "supplier-directory"}
