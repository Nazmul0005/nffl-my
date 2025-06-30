from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from App.api.api_routes import router as api_router
from App.core.config import settings

# Create FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    description=settings.API_DESCRIPTION,
    version=settings.API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Include API router
app.include_router(api_router)

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Welcome to NFL Data API",
        "docs": "/docs",
        "redoc": "/redoc"
    }

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok"}

# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

if __name__ == "__main__":
    import uvicorn
    import signal
    import sys
    
    def handle_exit(sig, frame):
        print('Shutting down API server...')
        sys.exit(0)
        
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    
    
    
    """
     Vaai check it out -----
     
     1. There is showing an error getting list object - showing list object has no attribute 'get'
     2. Reduce the Time consuming part. delete the cache and see the results. Does there any imporvement in the time consuming part??
     
     3. Check the VORP calculation is it showing any hellucinated result or, not please check it out.
    
    
    """