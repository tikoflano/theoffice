import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from theoffice_shared.schemas import HealthResponse

app = FastAPI(title="theoffice BFF", version="0.1.0")

_cors_origins = os.environ.get(
    "BFF_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


def run() -> None:
    import uvicorn

    host = os.environ.get("BFF_HOST", "0.0.0.0")
    port = int(os.environ.get("BFF_PORT", "8000"))
    uvicorn.run("theoffice_bff.main:app", host=host, port=port, reload=False)
