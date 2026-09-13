import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
