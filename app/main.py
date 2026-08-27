from dotenv import load_dotenv
from fastapi import FastAPI

from app.api.routes import router

load_dotenv()

app = FastAPI(title="travel-yantra")
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "travel-yantra"}
