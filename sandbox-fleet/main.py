from fastapi import FastAPI

app = FastAPI(title="devin-clone sandbox-fleet", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "sandbox-fleet"}
