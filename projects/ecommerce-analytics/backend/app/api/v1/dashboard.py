"""
Dashboard API endpoints

Real-time metrics and KPIs for the analytics dashboard.
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import Optional
from datetime import datetime, timedelta
from app.core.database import get_db
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/metrics")
async def get_dashboard_metrics(
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    channel_id: Optional[int] = Query(None, description="Filter by channel ID"),
    db: Session = Depends(get_db)
):
    """
    Get real-time dashboard metrics.

    Returns:
    - Total revenue
    - Total orders
    - Average order value
    - Revenue by channel
    - Top products
    - Low stock alerts count
    """

    # Default to last 30 days if no dates provided
    if not end_date:
        end_date = datetime.now()
    else:
        end_date = datetime.strptime(end_date, "%Y-%m-%d")

    if not start_date:
        start_date = end_date - timedelta(days=30)
    else:
        start_date = datetime.strptime(start_date, "%Y-%m-%d")

    # TODO: Replace with actual database queries
    # For now, returning mock data structure

    mock_data = {
        "period": {
            "start_date": start_date.isoformat() if isinstance(start_date, datetime) else start_date,
            "end_date": end_date.isoformat() if isinstance(end_date, datetime) else end_date,
            "days": (end_date - start_date).days if isinstance(end_date, datetime) and isinstance(start_date, datetime) else 30
        },
        "total_revenue": 125430.50,
        "total_orders": 1247,
        "avg_order_value": 100.50,
        "revenue_growth": 15.3,  # % vs previous period
        "orders_growth": 12.8,

        "revenue_by_channel": {
            "amazon": {
                "revenue": 65000.00,
                "orders": 650,
                "avg_order_value": 100.00,
                "percentage": 51.8
            },
            "shopify": {
                "revenue": 45000.00,
                "orders": 450,
                "avg_order_value": 100.00,
                "percentage": 35.9
            },
            "walmart": {
                "revenue": 15430.50,
                "orders": 147,
                "avg_order_value": 105.00,
                "percentage": 12.3
            }
        },

        "top_products": [
            {
                "product_id": 123,
                "sku": "WIDGET-001",
                "name": "Premium Widget Pro",
                "revenue": 15000.00,
                "units_sold": 300,
                "avg_price": 50.00,
                "inventory_available": 45
            },
            {
                "product_id": 124,
                "sku": "GADGET-002",
                "name": "Smart Gadget Plus",
                "revenue": 12500.00,
                "units_sold": 250,
                "avg_price": 50.00,
                "inventory_available": 120
            },
            {
                "product_id": 125,
                "sku": "TOOL-003",
                "name": "Professional Tool Kit",
                "revenue": 10000.00,
                "units_sold": 100,
                "avg_price": 100.00,
                "inventory_available": 8  # Low stock!
            }
        ],

        "alerts": {
            "total": 15,
            "critical": 3,
            "warning": 7,
            "info": 5,
            "types": {
                "low_stock": 8,
                "stockout": 3,
                "trending_product": 2,
                "sales_spike": 1,
                "price_change": 1
            }
        },

        "recent_orders": [
            {
                "order_id": 1001,
                "order_number": "AMZ-001-2024",
                "channel": "amazon",
                "total": 150.00,
                "status": "shipped",
                "order_date": (datetime.now() - timedelta(hours=2)).isoformat()
            },
            {
                "order_id": 1002,
                "order_number": "SHOP-002-2024",
                "channel": "shopify",
                "total": 89.99,
                "status": "pending",
                "order_date": (datetime.now() - timedelta(hours=1)).isoformat()
            }
        ]
    }

    logger.info(f"Dashboard metrics requested: {start_date} to {end_date}, channel: {channel_id}")

    return mock_data


@router.get("/trends")
async def get_revenue_trends(
    period: str = Query("daily", description="Granularity: daily, weekly, monthly"),
    days: int = Query(30, description="Number of days of data"),
    db: Session = Depends(get_db)
):
    """
    Get revenue and orders trends over time.

    Used for time-series charts on dashboard.
    """

    # Generate sample trend data
    from datetime import datetime, timedelta

    trends = []
    end_date = datetime.now()

    for i in range(days):
        date = end_date - timedelta(days=days - i - 1)
        trends.append({
            "date": date.strftime("%Y-%m-%d"),
            "revenue": 4000 + (i * 50) + (i % 7) * 200,  # Simulated trend
            "orders": 40 + (i % 7) * 5,
            "avg_order_value": 100.00
        })

    return {
        "period": period,
        "days": days,
        "trends": trends
    }


@router.get("/performance")
async def get_channel_performance(
    db: Session = Depends(get_db)
):
    """
    Compare performance metrics across channels.

    Returns comparative metrics for all active channels.
    """

    return {
        "channels": [
            {
                "id": 1,
                "name": "amazon",
                "display_name": "Amazon Marketplace",
                "metrics": {
                    "revenue_30d": 65000.00,
                    "revenue_growth": 18.5,
                    "orders_30d": 650,
                    "orders_growth": 15.2,
                    "avg_order_value": 100.00,
                    "conversion_rate": 3.2,
                    "return_rate": 2.1
                },
                "top_category": "Electronics"
            },
            {
                "id": 2,
                "name": "shopify",
                "display_name": "Shopify Store",
                "metrics": {
                    "revenue_30d": 45000.00,
                    "revenue_growth": 12.3,
                    "orders_30d": 450,
                    "orders_growth": 10.5,
                    "avg_order_value": 100.00,
                    "conversion_rate": 2.8,
                    "return_rate": 1.5
                },
                "top_category": "Home & Garden"
            },
            {
                "id": 3,
                "name": "walmart",
                "display_name": "Walmart Marketplace",
                "metrics": {
                    "revenue_30d": 15430.50,
                    "revenue_growth": 8.7,
                    "orders_30d": 147,
                    "orders_growth": 7.2,
                    "avg_order_value": 105.00,
                    "conversion_rate": 2.5,
                    "return_rate": 1.8
                },
                "top_category": "Tools"
            }
        ],
        "total_revenue": 125430.50,
        "total_orders": 1247
    }
