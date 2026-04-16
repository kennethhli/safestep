from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

# localhost vs 127.0.0.1 are different origins — include both so preflight (OPTIONS) does not 400
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(routes.router, prefix="/api", tags=["routes"])

@app.get("/")
async def root():
    return {"message": "SafeStep API is running"}

