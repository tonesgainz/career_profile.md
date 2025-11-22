"""
E-commerce Analytics Platform - FastAPI Backend

Real-time analytics platform for multi-channel e-commerce data.
Integrates Amazon, Shopify, and Walmart with ML-powered forecasting.

Author: Tony V. Nguyen
Email: tony@snfactor.com
GitHub: github.com/tonesgainz
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
from typing import List
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import configuration and database
from app.core.config import settings
from app.core.database import engine, SessionLocal
from app.core.redis_client import redis_client

# Import routers
from app.api.v1 import (
    dashboard,
    products,
    orders,
    inventory,
    analytics,
    forecasting,
    alerts,
    channels
)

# WebSocket connection manager
class ConnectionManager:
    """Manages WebSocket connections for real-time updates"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active_connections)}")

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients"""
        import json
        message_str = json.dumps(message)
        for connection in self.active_connections:
            try:
                await connection.send_text(message_str)
            except Exception as e:
                logger.error(f"Error broadcasting to websocket: {e}")

manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    logger.info("🚀 Starting E-commerce Analytics Platform API...")

    # Initialize database
    logger.info("📊 Initializing database connection...")

    # Initialize Redis
    logger.info("💾 Connecting to Redis...")
    try:
        await redis_client.ping()
        logger.info("✅ Redis connected successfully")
    except Exception as e:
        logger.error(f"❌ Redis connection failed: {e}")

    # Load ML models
    logger.info("🤖 Loading ML forecasting models...")
    # TODO: Load Prophet and LSTM models

    logger.info("✅ API startup complete!")

    yield

    # Shutdown
    logger.info("🛑 Shutting down API...")
    await redis_client.close()
    logger.info("👋 Shutdown complete")


# Initialize FastAPI app
app = FastAPI(
    title="E-commerce Analytics Platform",
    description="Real-time multi-channel e-commerce analytics with ML-powered forecasting",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip Compression
app.add_middleware(GZipMiddleware, minimum_size=1000)


# Middleware for request timing
@app.middleware("http")
async def add_process_time_header(request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)

    # Log slow requests
    if process_time > 1.0:
        logger.warning(f"Slow request: {request.method} {request.url.path} took {process_time:.2f}s")

    return response


# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "status_code": exc.status_code}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "status_code": 500}
    )


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """API root endpoint"""
    return {
        "message": "E-commerce Analytics Platform API",
        "version": "1.0.0",
        "documentation": "/docs",
        "health": "/health",
        "author": "Tony V. Nguyen",
        "github": "https://github.com/tonesgainz"
    }


# Health check endpoint
@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint for load balancers and monitoring"""
    try:
        # Check database
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"

    try:
        # Check Redis
        await redis_client.ping()
        redis_status = "healthy"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        redis_status = "unhealthy"

    overall_status = "healthy" if db_status == "healthy" and redis_status == "healthy" else "degraded"

    return {
        "status": overall_status,
        "timestamp": time.time(),
        "components": {
            "database": db_status,
            "redis": redis_status,
            "api": "healthy"
        },
        "version": "1.0.0"
    }


# WebSocket endpoint for real-time updates
@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """
    WebSocket endpoint for real-time dashboard updates.

    Sends:
    - New order notifications
    - Inventory changes
    - Alert notifications
    - Real-time metric updates
    """
    await manager.connect(websocket)
    try:
        while True:
            # Wait for messages from client
            data = await websocket.receive_text()

            # Echo back (for ping/pong)
            await websocket.send_text(f"Received: {data}")

            # In production, this would:
            # 1. Listen to Redis pub/sub for real-time events
            # 2. Broadcast updates to connected clients
            # 3. Handle client subscriptions to specific channels

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected from dashboard WebSocket")


# Include API routers
app.include_router(
    dashboard.router,
    prefix="/api/v1/dashboard",
    tags=["Dashboard"]
)

app.include_router(
    products.router,
    prefix="/api/v1/products",
    tags=["Products"]
)

app.include_router(
    orders.router,
    prefix="/api/v1/orders",
    tags=["Orders"]
)

app.include_router(
    inventory.router,
    prefix="/api/v1/inventory",
    tags=["Inventory"]
)

app.include_router(
    analytics.router,
    prefix="/api/v1/analytics",
    tags=["Analytics"]
)

app.include_router(
    forecasting.router,
    prefix="/api/v1/forecast",
    tags=["Forecasting"]
)

app.include_router(
    alerts.router,
    prefix="/api/v1/alerts",
    tags=["Alerts"]
)

app.include_router(
    channels.router,
    prefix="/api/v1/channels",
    tags=["Channels"]
)


# Prometheus metrics endpoint
@app.get("/metrics", tags=["System"])
async def metrics():
    """
    Prometheus metrics endpoint.

    Exposes application metrics for monitoring.
    """
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi.responses import Response

    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Development only
        log_level="info"
    )
