from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1 import router as v1_router

app = FastAPI(
    title="Climate-Resilient Water Management System",
    description="Backend API for water risk modelling and decision support",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API version 1 routes
app.include_router(v1_router)


@app.get("/")
async def root():
    return {"message": "Water Management API is running"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}