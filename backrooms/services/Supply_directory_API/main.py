import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes.suppliers import router as suppliers_router


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


@app.get("/")
def root() -> dict[str, str]:
	return {"status": "ok", "service": "supplier-directory"}
