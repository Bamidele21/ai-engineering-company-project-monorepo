from fastapi import FastAPI

from routes.suppliers import router as suppliers_router


app = FastAPI(title="Nexova Supplier Directory API")
app.include_router(suppliers_router)


@app.get("/")
def root() -> dict[str, str]:
	return {"status": "ok", "service": "supplier-directory"}
