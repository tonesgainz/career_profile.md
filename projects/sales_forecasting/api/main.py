"""
FastAPI Application for Sales Forecasting Platform

RESTful API providing endpoints for sales data management, model training,
and forecast generation.

Author: Tony V. Nguyen
Email: tony@snfactor.com
"""

from fastapi import FastAPI, HTTPException, Depends, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
from enum import Enum
import logging
import sys
from pathlib import Path

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Sales Forecasting API",
    description="ML-powered sales forecasting platform with ARIMA, Prophet, and LSTM models",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== Enums ====================

class ModelType(str, Enum):
    """Supported forecasting models"""
    ARIMA = "arima"
    PROPHET = "prophet"
    LSTM = "lstm"
    AUTO = "auto"  # Automatically select best model


class IntervalLevel(float, Enum):
    """Confidence interval levels"""
    NINETY = 0.90
    NINETY_FIVE = 0.95
    NINETY_NINE = 0.99


# ==================== Request Models ====================

class SalesDataPoint(BaseModel):
    """Single sales data point"""
    date: date
    quantity: int = Field(..., ge=0, description="Sales quantity")
    revenue: float = Field(..., ge=0, description="Sales revenue")

    class Config:
        json_schema_extra = {
            "example": {
                "date": "2024-01-15",
                "quantity": 120,
                "revenue": 1200.00
            }
        }


class BulkSalesData(BaseModel):
    """Bulk sales data upload"""
    product_id: str = Field(..., min_length=1, max_length=100)
    sales_history: List[SalesDataPoint]
    category: Optional[str] = None
    region: Optional[str] = None

    @validator('sales_history')
    def validate_sales_history(cls, v):
        if len(v) < 30:
            raise ValueError("Minimum 30 days of historical data required")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "product_id": "SKU-12345",
                "sales_history": [
                    {"date": "2024-01-01", "quantity": 100, "revenue": 1000.00},
                    {"date": "2024-01-02", "quantity": 110, "revenue": 1100.00}
                ],
                "category": "Electronics",
                "region": "West"
            }
        }


class ForecastRequest(BaseModel):
    """Forecast generation request"""
    product_id: str = Field(..., min_length=1)
    horizon_days: int = Field(..., ge=1, le=365, description="Forecast horizon (1-365 days)")
    model_type: ModelType = Field(default=ModelType.AUTO)
    include_confidence_intervals: bool = Field(default=True)
    confidence_level: IntervalLevel = Field(default=IntervalLevel.NINETY_FIVE)

    class Config:
        json_schema_extra = {
            "example": {
                "product_id": "SKU-12345",
                "horizon_days": 30,
                "model_type": "prophet",
                "include_confidence_intervals": True,
                "confidence_level": 0.95
            }
        }


class BatchForecastRequest(BaseModel):
    """Batch forecast for multiple products"""
    product_ids: List[str] = Field(..., min_items=1, max_items=100)
    horizon_days: int = Field(..., ge=1, le=90)
    model_type: ModelType = Field(default=ModelType.AUTO)
    include_metrics: bool = Field(default=True)

    class Config:
        json_schema_extra = {
            "example": {
                "product_ids": ["SKU-001", "SKU-002", "SKU-003"],
                "horizon_days": 14,
                "model_type": "auto",
                "include_metrics": True
            }
        }


class ModelTrainingRequest(BaseModel):
    """Model training request"""
    product_id: str
    model_type: ModelType
    hyperparameters: Optional[Dict[str, Any]] = None
    validation_split: float = Field(default=0.2, ge=0.1, le=0.4)

    class Config:
        json_schema_extra = {
            "example": {
                "product_id": "SKU-12345",
                "model_type": "prophet",
                "hyperparameters": {
                    "changepoint_prior_scale": 0.1,
                    "seasonality_prior_scale": 10
                },
                "validation_split": 0.2
            }
        }


# ==================== Response Models ====================

class ForecastDataPoint(BaseModel):
    """Single forecast data point"""
    date: date
    predicted_sales: float
    lower_bound: Optional[float] = None
    upper_bound: Optional[float] = None


class ForecastResponse(BaseModel):
    """Forecast response"""
    product_id: str
    model_type: str
    model_version: str
    forecast_generated_at: datetime
    horizon_days: int
    predictions: List[ForecastDataPoint]
    total_predicted_sales: float
    confidence_level: Optional[float] = None

    class Config:
        json_schema_extra = {
            "example": {
                "product_id": "SKU-12345",
                "model_type": "prophet",
                "model_version": "v1.2.0",
                "forecast_generated_at": "2024-11-22T10:30:00",
                "horizon_days": 30,
                "predictions": [
                    {
                        "date": "2024-11-23",
                        "predicted_sales": 125.5,
                        "lower_bound": 110.2,
                        "upper_bound": 140.8
                    }
                ],
                "total_predicted_sales": 3765.0,
                "confidence_level": 0.95
            }
        }


class ModelMetrics(BaseModel):
    """Model performance metrics"""
    mae: float = Field(..., description="Mean Absolute Error")
    rmse: float = Field(..., description="Root Mean Squared Error")
    mape: float = Field(..., description="Mean Absolute Percentage Error")
    r2: float = Field(..., description="R-squared")
    coverage: Optional[float] = Field(None, description="Confidence interval coverage %")


class ModelInfo(BaseModel):
    """Model metadata"""
    model_id: str
    model_name: str
    model_type: str
    model_version: str
    trained_on: datetime
    training_data_period: str
    performance_metrics: ModelMetrics
    is_active: bool


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    timestamp: datetime
    version: str
    database_connected: bool
    models_loaded: int


# ==================== Helper Functions ====================

async def get_product_sales_data(product_id: str) -> List[Dict]:
    """
    Fetch sales data for a product from database.

    TODO: Implement database connection
    """
    # Placeholder - implement database query
    logger.info(f"Fetching sales data for product: {product_id}")
    return []


async def select_best_model(product_id: str, available_models: List[str]) -> str:
    """
    Automatically select best performing model for a product.

    TODO: Implement model selection logic
    """
    logger.info(f"Auto-selecting best model for product: {product_id}")
    return ModelType.PROPHET.value


async def train_model_async(
    product_id: str,
    model_type: ModelType,
    hyperparameters: Optional[Dict] = None
):
    """
    Background task for model training.
    """
    logger.info(f"Starting training for {model_type} model on product {product_id}")
    # TODO: Implement model training
    await asyncio.sleep(1)  # Simulate training
    logger.info(f"Training completed for {product_id}")


# ==================== API Endpoints ====================

@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint"""
    return {
        "message": "Sales Forecasting API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now(),
        version="1.0.0",
        database_connected=True,  # TODO: Check actual DB connection
        models_loaded=3  # TODO: Count loaded models
    )


# ==================== Sales Data Endpoints ====================

@app.post("/api/v1/sales", status_code=status.HTTP_201_CREATED)
async def upload_sales_data(data: BulkSalesData):
    """
    Upload historical sales data for a product.

    - **product_id**: Unique product identifier
    - **sales_history**: List of sales data points (min 30 days)
    - **category**: Product category (optional)
    - **region**: Sales region (optional)
    """
    try:
        logger.info(f"Uploading {len(data.sales_history)} sales records for {data.product_id}")

        # TODO: Validate and store data in database

        return {
            "message": "Sales data uploaded successfully",
            "product_id": data.product_id,
            "records_uploaded": len(data.sales_history),
            "date_range": {
                "start": min(sp.date for sp in data.sales_history),
                "end": max(sp.date for sp in data.sales_history)
            }
        }
    except Exception as e:
        logger.error(f"Error uploading sales data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload sales data: {str(e)}"
        )


@app.get("/api/v1/sales/{product_id}")
async def get_sales_data(
    product_id: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    limit: int = Field(default=1000, le=10000)
):
    """
    Retrieve historical sales data for a product.

    - **product_id**: Unique product identifier
    - **start_date**: Filter from this date (optional)
    - **end_date**: Filter until this date (optional)
    - **limit**: Maximum records to return (default: 1000)
    """
    try:
        sales_data = await get_product_sales_data(product_id)

        # TODO: Apply filters and return actual data

        return {
            "product_id": product_id,
            "total_records": 0,
            "date_range": {
                "start": start_date,
                "end": end_date
            },
            "sales_data": []
        }
    except Exception as e:
        logger.error(f"Error retrieving sales data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sales data not found for product: {product_id}"
        )


# ==================== Forecasting Endpoints ====================

@app.post("/api/v1/forecast", response_model=ForecastResponse)
async def generate_forecast(request: ForecastRequest):
    """
    Generate sales forecast for a product.

    - **product_id**: Product to forecast
    - **horizon_days**: Number of days to forecast (1-365)
    - **model_type**: Model to use (arima, prophet, lstm, or auto)
    - **include_confidence_intervals**: Include prediction intervals
    - **confidence_level**: Confidence level for intervals (0.90, 0.95, 0.99)
    """
    try:
        logger.info(f"Generating {request.horizon_days}-day forecast for {request.product_id}")

        # Determine which model to use
        if request.model_type == ModelType.AUTO:
            model_type = await select_best_model(request.product_id, ["prophet", "lstm", "arima"])
        else:
            model_type = request.model_type.value

        # TODO: Load trained model and generate forecast

        # Placeholder response
        predictions = [
            ForecastDataPoint(
                date=date.today() + timedelta(days=i),
                predicted_sales=100.0 + i * 0.5,
                lower_bound=90.0 + i * 0.5 if request.include_confidence_intervals else None,
                upper_bound=110.0 + i * 0.5 if request.include_confidence_intervals else None
            )
            for i in range(1, request.horizon_days + 1)
        ]

        return ForecastResponse(
            product_id=request.product_id,
            model_type=model_type,
            model_version="v1.0.0",
            forecast_generated_at=datetime.now(),
            horizon_days=request.horizon_days,
            predictions=predictions,
            total_predicted_sales=sum(p.predicted_sales for p in predictions),
            confidence_level=request.confidence_level.value if request.include_confidence_intervals else None
        )

    except Exception as e:
        logger.error(f"Error generating forecast: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate forecast: {str(e)}"
        )


@app.post("/api/v1/forecast/batch")
async def generate_batch_forecasts(request: BatchForecastRequest):
    """
    Generate forecasts for multiple products in batch.

    - **product_ids**: List of products to forecast (max 100)
    - **horizon_days**: Forecast horizon for all products
    - **model_type**: Model to use (auto will select best per product)
    - **include_metrics**: Include model performance metrics
    """
    try:
        logger.info(f"Generating batch forecasts for {len(request.product_ids)} products")

        # TODO: Implement parallel forecast generation

        forecasts = []
        for product_id in request.product_ids:
            # Placeholder forecast
            forecasts.append({
                "product_id": product_id,
                "model_type": "prophet",
                "total_predicted": 3000.0,
                "metrics": ModelMetrics(
                    mae=15.2,
                    rmse=20.5,
                    mape=8.3,
                    r2=0.89
                ) if request.include_metrics else None
            })

        return {
            "total_forecasts": len(forecasts),
            "horizon_days": request.horizon_days,
            "forecasts": forecasts
        }

    except Exception as e:
        logger.error(f"Error in batch forecasting: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch forecast failed: {str(e)}"
        )


# ==================== Model Management Endpoints ====================

@app.get("/api/v1/models", response_model=List[ModelInfo])
async def list_models(
    model_type: Optional[ModelType] = None,
    active_only: bool = True
):
    """
    List available models.

    - **model_type**: Filter by model type (optional)
    - **active_only**: Show only active models (default: true)
    """
    try:
        # TODO: Query database for models
        models = [
            ModelInfo(
                model_id="model_001",
                model_name="Prophet Sales Forecaster",
                model_type="prophet",
                model_version="v1.0.0",
                trained_on=datetime.now() - timedelta(days=7),
                training_data_period="2022-01-01 to 2024-11-15",
                performance_metrics=ModelMetrics(
                    mae=38.7,
                    rmse=53.4,
                    mape=9.8,
                    r2=0.89,
                    coverage=94.5
                ),
                is_active=True
            )
        ]

        return models

    except Exception as e:
        logger.error(f"Error listing models: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve models"
        )


@app.post("/api/v1/models/train", status_code=status.HTTP_202_ACCEPTED)
async def train_model(request: ModelTrainingRequest, background_tasks: BackgroundTasks):
    """
    Train a new model (async background task).

    - **product_id**: Product to train model for
    - **model_type**: Type of model to train
    - **hyperparameters**: Custom hyperparameters (optional)
    - **validation_split**: Validation data fraction

    Returns immediately with task ID. Check status via GET /api/v1/models/tasks/{task_id}
    """
    try:
        # Generate task ID
        task_id = f"task_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Add training to background tasks
        background_tasks.add_task(
            train_model_async,
            request.product_id,
            request.model_type,
            request.hyperparameters
        )

        logger.info(f"Started model training task: {task_id}")

        return {
            "message": "Model training started",
            "task_id": task_id,
            "product_id": request.product_id,
            "model_type": request.model_type.value,
            "status_endpoint": f"/api/v1/models/tasks/{task_id}"
        }

    except Exception as e:
        logger.error(f"Error starting model training: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start training: {str(e)}"
        )


@app.get("/api/v1/models/{model_id}")
async def get_model_details(model_id: str):
    """
    Get detailed information about a specific model.
    """
    try:
        # TODO: Query database for model details
        return {
            "model_id": model_id,
            "status": "active",
            "details": "Model details here"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Model not found: {model_id}"
        )


# ==================== Analytics Endpoints ====================

@app.get("/api/v1/analytics/accuracy")
async def get_accuracy_trends(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
):
    """
    Get model accuracy trends over time.
    """
    # TODO: Implement accuracy tracking
    return {
        "message": "Accuracy trends endpoint",
        "start_date": start_date,
        "end_date": end_date
    }


@app.get("/api/v1/analytics/trends/{product_id}")
async def get_sales_trends(product_id: str, period_days: int = 90):
    """
    Analyze sales trends for a product.
    """
    # TODO: Implement trend analysis
    return {
        "product_id": product_id,
        "period_days": period_days,
        "trends": {}
    }


# ==================== Exception Handlers ====================

@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)}
    )


# ==================== Application Lifecycle ====================

@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup"""
    logger.info("Starting Sales Forecasting API...")
    # TODO: Load models, connect to database, etc.
    logger.info("API startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    logger.info("Shutting down Sales Forecasting API...")
    # TODO: Close database connections, save state, etc.
    logger.info("API shutdown complete")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
