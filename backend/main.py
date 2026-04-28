from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from app.database import engine, Base
from app.routers import routes, health

app = FastAPI(
    title="SafeStep API",
    description="AI Safety Route Navigator API",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    # create db tables if they don't exist
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"db connection failed: {e}")

default_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
env_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
    if origin.strip()
]
allow_origins = list(dict.fromkeys(default_origins + env_origins))
frontend_origin_regex = os.getenv("FRONTEND_ORIGIN_REGEX", r"https://.*\.vercel\.app")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=frontend_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(routes.router, prefix="/api", tags=["routes"])

@app.get("/")
async def root():
    return {"message": "SafeStep API is running"}

