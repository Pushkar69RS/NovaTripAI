from fastapi import FastAPI

app = FastAPI(title="travel-yantra")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "travel-yantra"}
