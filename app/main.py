from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import items, images

app = FastAPI(
    title="Wardrobe Architect API",
    description="API for managing wardrobe items and images, designed for GPT Actions integration",
    version="1.0.0",
)

# CORS middleware for flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(items.router)
app.include_router(images.router)


@app.get("/health", tags=["Utility"])
async def health_check():
    """Health check endpoint - no authentication required."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    from app.config import get_settings

    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
