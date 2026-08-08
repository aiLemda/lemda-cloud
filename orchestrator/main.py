from fastapi import FastAPI

app = FastAPI(title="devin-clone orchestrator", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "orchestrator"}
