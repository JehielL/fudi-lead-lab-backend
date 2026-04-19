from fastapi import FastAPI

app = FastAPI(title="Fudi Lead Lab API")

@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
