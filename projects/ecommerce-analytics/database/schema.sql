-- E-commerce Analytics Platform Database Schema
-- PostgreSQL 15+
-- Author: Tony V. Nguyen
-- Description: Unified schema for multi-channel e-commerce analytics

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm"; -- For full-text search

-- =============================================================================
-- CORE TABLES
-- =============================================================================

-- Channels (Sales platforms: Amazon, Shopify, Walmart)
CREATE TABLE channels (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    display_name VARCHAR(100) NOT NULL,
    api_credentials JSONB, -- Encrypted API keys and tokens
    api_config JSONB, -- Rate limits, endpoints, etc.
    is_active BOOLEAN DEFAULT TRUE,
    last_sync_at TIMESTAMP,
    sync_frequency_minutes INTEGER DEFAULT 15,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_channel_name CHECK (name IN ('amazon', 'shopify', 'walmart', 'custom'))
);

CREATE INDEX idx_channels_active ON channels(is_active) WHERE is_active = TRUE;

-- Insert default channels
INSERT INTO channels (name, display_name, sync_frequency_minutes) VALUES
('amazon', 'Amazon Marketplace', 15),
('shopify', 'Shopify Store', 15),
('walmart', 'Walmart Marketplace', 30);

-- =============================================================================
-- PRODUCT MANAGEMENT
-- =============================================================================

-- Products (unified product catalog)
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    sku VARCHAR(100) UNIQUE NOT NULL,
    name VARCHAR(500) NOT NULL,
    description TEXT,
    category VARCHAR(100),
    subcategory VARCHAR(100),
    brand VARCHAR(100),
    cost_price DECIMAL(10,2), -- Your cost
    weight_kg DECIMAL(8,3),
    dimensions_cm VARCHAR(50), -- Format: "LxWxH"
    is_active BOOLEAN DEFAULT TRUE,
    tags TEXT[], -- Array of tags for filtering
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_products_sku ON products(sku);
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_active ON products(is_active) WHERE is_active = TRUE;
CREATE INDEX idx_products_search ON products USING gin(to_tsvector('english', name || ' ' || COALESCE(description, '')));

-- Channel-specific product listings
CREATE TABLE channel_products (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    external_id VARCHAR(255), -- ASIN, Shopify product ID, etc.
    listing_title VARCHAR(500),
    listing_price DECIMAL(10,2),
    compare_at_price DECIMAL(10,2), -- Original price (for discounts)
    listing_url VARCHAR(1000),
    is_active BOOLEAN DEFAULT TRUE,
    last_synced_at TIMESTAMP,
    sync_data JSONB, -- Raw data from channel API
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(product_id, channel_id)
);

CREATE INDEX idx_channel_products_product ON channel_products(product_id);
CREATE INDEX idx_channel_products_channel ON channel_products(channel_id);
CREATE INDEX idx_channel_products_external ON channel_products(external_id);

-- =============================================================================
-- ORDER MANAGEMENT
-- =============================================================================

-- Orders
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    order_number VARCHAR(100) UNIQUE NOT NULL,
    channel_id INTEGER NOT NULL REFERENCES channels(id),
    order_date TIMESTAMP NOT NULL,
    customer_email VARCHAR(255),
    customer_name VARCHAR(255),
    shipping_address JSONB,
    billing_address JSONB,

    -- Financial details
    subtotal DECIMAL(10,2) NOT NULL,
    shipping_cost DECIMAL(10,2) DEFAULT 0,
    tax DECIMAL(10,2) DEFAULT 0,
    discount DECIMAL(10,2) DEFAULT 0,
    total DECIMAL(10,2) NOT NULL,
    channel_fees DECIMAL(10,2) DEFAULT 0, -- Amazon fees, Shopify fees, etc.
    net_revenue DECIMAL(10,2) GENERATED ALWAYS AS (total - channel_fees) STORED,

    -- Status
    order_status VARCHAR(50), -- pending, paid, shipped, delivered, cancelled, refunded
    fulfillment_status VARCHAR(50), -- unfulfilled, partial, fulfilled
    payment_status VARCHAR(50), -- pending, paid, refunded, partially_refunded

    -- Metadata
    currency VARCHAR(3) DEFAULT 'USD',
    external_order_id VARCHAR(255), -- Channel's original order ID
    raw_data JSONB, -- Complete data from channel API
    notes TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_order_status CHECK (order_status IN (
        'pending', 'paid', 'shipped', 'delivered', 'cancelled', 'refunded'
    ))
);

CREATE INDEX idx_orders_date ON orders(order_date DESC);
CREATE INDEX idx_orders_channel ON orders(channel_id);
CREATE INDEX idx_orders_status ON orders(order_status);
CREATE INDEX idx_orders_number ON orders(order_number);
CREATE INDEX idx_orders_customer ON orders(customer_email);
CREATE INDEX idx_orders_external ON orders(external_order_id);

-- Order items (line items)
CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER REFERENCES products(id),
    channel_product_id INTEGER REFERENCES channel_products(id),

    -- Product details (snapshot at time of order)
    product_name VARCHAR(500) NOT NULL,
    sku VARCHAR(100),

    -- Pricing
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(10,2) NOT NULL,
    discount DECIMAL(10,2) DEFAULT 0,
    tax DECIMAL(10,2) DEFAULT 0,
    total DECIMAL(10,2) NOT NULL,

    -- Cost (for profit calculation)
    unit_cost DECIMAL(10,2), -- Cost at time of sale

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_order_items_order ON order_items(order_id);
CREATE INDEX idx_order_items_product ON order_items(product_id);

-- =============================================================================
-- INVENTORY MANAGEMENT
-- =============================================================================

-- Warehouses / Fulfillment centers
CREATE TABLE warehouses (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    address JSONB,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Default warehouses for common FBA/fulfillment
INSERT INTO warehouses (code, name) VALUES
('FBA_US_EAST', 'Amazon FBA - US East'),
('FBA_US_WEST', 'Amazon FBA - US West'),
('SHOPIFY_US', 'Shopify Fulfillment - US'),
('WALMART_FC', 'Walmart Fulfillment Center'),
('MAIN_WAREHOUSE', 'Main Warehouse');

-- Inventory levels
CREATE TABLE inventory (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    channel_id INTEGER REFERENCES channels(id),
    warehouse_id INTEGER REFERENCES warehouses(id),

    -- Quantities
    quantity_available INTEGER DEFAULT 0 CHECK (quantity_available >= 0),
    quantity_reserved INTEGER DEFAULT 0 CHECK (quantity_reserved >= 0),
    quantity_incoming INTEGER DEFAULT 0, -- Purchase orders in transit

    -- Reorder settings
    reorder_point INTEGER DEFAULT 10,
    reorder_quantity INTEGER DEFAULT 50,
    optimal_stock_level INTEGER, -- ML-calculated optimal level

    -- Metadata
    last_counted_at TIMESTAMP,
    last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(product_id, channel_id, warehouse_id)
);

CREATE INDEX idx_inventory_product ON inventory(product_id);
CREATE INDEX idx_inventory_channel ON inventory(channel_id);
CREATE INDEX idx_inventory_warehouse ON inventory(warehouse_id);

-- Index for low stock alerts
CREATE INDEX idx_inventory_low_stock ON inventory(product_id, channel_id)
WHERE quantity_available < reorder_point;

-- Inventory transactions (audit trail)
CREATE TABLE inventory_transactions (
    id SERIAL PRIMARY KEY,
    inventory_id INTEGER NOT NULL REFERENCES inventory(id),
    transaction_type VARCHAR(50), -- 'sale', 'restock', 'adjustment', 'return', 'transfer'
    quantity_change INTEGER NOT NULL,
    quantity_after INTEGER NOT NULL,
    reason VARCHAR(255),
    reference_id INTEGER, -- order_id, transfer_id, etc.
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_transaction_type CHECK (transaction_type IN (
        'sale', 'restock', 'adjustment', 'return', 'transfer', 'damage', 'lost'
    ))
);

CREATE INDEX idx_inventory_transactions_inventory ON inventory_transactions(inventory_id);
CREATE INDEX idx_inventory_transactions_date ON inventory_transactions(created_at DESC);

-- =============================================================================
-- FORECASTING & ANALYTICS
-- =============================================================================

-- Sales forecasts
CREATE TABLE forecasts (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    channel_id INTEGER REFERENCES channels(id),
    forecast_date DATE NOT NULL,

    -- Predictions
    predicted_units DECIMAL(10,2) NOT NULL,
    predicted_revenue DECIMAL(10,2),
    lower_bound DECIMAL(10,2), -- 95% confidence interval lower
    upper_bound DECIMAL(10,2), -- 95% confidence interval upper

    -- Model metadata
    model_type VARCHAR(50), -- 'prophet', 'lstm', 'arima', 'ensemble'
    model_version VARCHAR(50),
    confidence_level DECIMAL(3,2) DEFAULT 0.95,
    accuracy_mape DECIMAL(5,2), -- Mean Absolute Percentage Error

    -- Metadata
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    training_data_start DATE,
    training_data_end DATE,

    UNIQUE(product_id, channel_id, forecast_date, model_type),

    CONSTRAINT valid_model CHECK (model_type IN ('prophet', 'lstm', 'arima', 'ensemble'))
);

CREATE INDEX idx_forecasts_product ON forecasts(product_id);
CREATE INDEX idx_forecasts_date ON forecasts(forecast_date);
CREATE INDEX idx_forecasts_generated ON forecasts(generated_at DESC);

-- Model performance tracking
CREATE TABLE model_performance (
    id SERIAL PRIMARY KEY,
    model_type VARCHAR(50) NOT NULL,
    model_version VARCHAR(50),
    evaluation_date DATE NOT NULL,

    -- Metrics
    mae DECIMAL(10,4), -- Mean Absolute Error
    rmse DECIMAL(10,4), -- Root Mean Squared Error
    mape DECIMAL(5,2), -- Mean Absolute Percentage Error
    r2_score DECIMAL(5,4), -- R-squared

    -- Metadata
    products_evaluated INTEGER,
    date_range_days INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_model_performance_type ON model_performance(model_type);

-- =============================================================================
-- ALERTS & NOTIFICATIONS
-- =============================================================================

-- Alerts
CREATE TABLE alerts (
    id SERIAL PRIMARY KEY,
    alert_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL, -- 'critical', 'warning', 'info'

    -- Related entities
    product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
    channel_id INTEGER REFERENCES channels(id),
    order_id INTEGER REFERENCES orders(id),

    -- Content
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    action_url VARCHAR(500),
    action_label VARCHAR(100),

    -- Status
    is_read BOOLEAN DEFAULT FALSE,
    is_dismissed BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMP,
    dismissed_at TIMESTAMP,

    -- Metadata
    metadata JSONB, -- Additional context
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT valid_alert_type CHECK (alert_type IN (
        'low_stock', 'stockout', 'reorder_needed', 'trending_product',
        'sales_spike', 'sales_drop', 'price_change', 'inventory_sync_failed',
        'forecast_accuracy_low', 'high_return_rate'
    )),

    CONSTRAINT valid_severity CHECK (severity IN ('critical', 'warning', 'info'))
);

CREATE INDEX idx_alerts_unread ON alerts(is_read, created_at DESC) WHERE is_read = FALSE;
CREATE INDEX idx_alerts_product ON alerts(product_id);
CREATE INDEX idx_alerts_type ON alerts(alert_type);
CREATE INDEX idx_alerts_created ON alerts(created_at DESC);

-- Alert subscriptions (for email/slack notifications)
CREATE TABLE alert_subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER, -- Reference to users table (not created here)
    alert_type VARCHAR(50) NOT NULL,
    channel VARCHAR(50), -- 'email', 'slack', 'sms'
    is_active BOOLEAN DEFAULT TRUE,
    config JSONB, -- Email address, Slack webhook, etc.
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- ANALYTICS MATERIALIZED VIEWS
-- =============================================================================

-- Daily sales summary (for fast analytics queries)
CREATE MATERIALIZED VIEW daily_sales_summary AS
SELECT
    DATE(o.order_date) as sale_date,
    o.channel_id,
    p.id as product_id,
    p.category,
    COUNT(DISTINCT o.id) as num_orders,
    SUM(oi.quantity) as total_units,
    SUM(oi.total) as total_revenue,
    AVG(oi.unit_price) as avg_price,
    SUM(oi.unit_cost * oi.quantity) as total_cost,
    SUM(oi.total - (oi.unit_cost * oi.quantity)) as gross_profit
FROM orders o
JOIN order_items oi ON o.id = oi.order_id
JOIN products p ON oi.product_id = p.id
WHERE o.order_status NOT IN ('cancelled', 'refunded')
GROUP BY DATE(o.order_date), o.channel_id, p.id, p.category;

CREATE UNIQUE INDEX idx_daily_sales_summary ON daily_sales_summary(sale_date, channel_id, product_id);
CREATE INDEX idx_daily_sales_date ON daily_sales_summary(sale_date DESC);

-- Product performance summary
CREATE MATERIALIZED VIEW product_performance AS
SELECT
    p.id as product_id,
    p.sku,
    p.name,
    p.category,
    COUNT(DISTINCT oi.order_id) as total_orders,
    SUM(oi.quantity) as total_units_sold,
    SUM(oi.total) as total_revenue,
    AVG(oi.unit_price) as avg_selling_price,
    MAX(o.order_date) as last_sold_date,
    EXTRACT(EPOCH FROM (NOW() - MAX(o.order_date))) / 86400 as days_since_last_sale
FROM products p
LEFT JOIN order_items oi ON p.id = oi.product_id
LEFT JOIN orders o ON oi.order_id = o.id
WHERE o.order_status NOT IN ('cancelled', 'refunded')
GROUP BY p.id, p.sku, p.name, p.category;

CREATE UNIQUE INDEX idx_product_performance ON product_performance(product_id);

-- =============================================================================
-- FUNCTIONS & TRIGGERS
-- =============================================================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply trigger to relevant tables
CREATE TRIGGER update_channels_updated_at BEFORE UPDATE ON channels
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_products_updated_at BEFORE UPDATE ON products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_channel_products_updated_at BEFORE UPDATE ON channel_products
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_orders_updated_at BEFORE UPDATE ON orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Function to create low stock alert
CREATE OR REPLACE FUNCTION check_low_stock()
RETURNS TRIGGER AS $$
BEGIN
    -- If quantity falls below reorder point, create alert
    IF NEW.quantity_available < NEW.reorder_point AND
       (OLD.quantity_available IS NULL OR OLD.quantity_available >= NEW.reorder_point) THEN

        INSERT INTO alerts (
            alert_type,
            severity,
            product_id,
            channel_id,
            title,
            message,
            metadata
        )
        SELECT
            'low_stock',
            CASE
                WHEN NEW.quantity_available = 0 THEN 'critical'
                WHEN NEW.quantity_available < NEW.reorder_point / 2 THEN 'warning'
                ELSE 'info'
            END,
            NEW.product_id,
            NEW.channel_id,
            'Low Stock Alert: ' || p.name,
            format('Product %s is running low. Current stock: %s units (reorder point: %s)',
                   p.name, NEW.quantity_available, NEW.reorder_point),
            jsonb_build_object(
                'current_stock', NEW.quantity_available,
                'reorder_point', NEW.reorder_point,
                'warehouse_id', NEW.warehouse_id
            )
        FROM products p
        WHERE p.id = NEW.product_id
        ON CONFLICT DO NOTHING;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER inventory_low_stock_alert
AFTER UPDATE ON inventory
FOR EACH ROW
EXECUTE FUNCTION check_low_stock();

-- Function to refresh materialized views
CREATE OR REPLACE FUNCTION refresh_analytics_views()
RETURNS void AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY daily_sales_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY product_performance;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- SAMPLE DATA (for development/testing)
-- =============================================================================

-- Commented out for production, uncomment for dev environment
/*
-- Sample products
INSERT INTO products (sku, name, category, brand, cost_price) VALUES
('WIDGET-001', 'Premium Widget Pro', 'Electronics', 'TechBrand', 25.00),
('GADGET-002', 'Smart Gadget Plus', 'Electronics', 'SmartCo', 15.00),
('TOOL-003', 'Professional Tool Kit', 'Tools', 'ToolMaster', 40.00);

-- Sample channel products
INSERT INTO channel_products (product_id, channel_id, external_id, listing_title, listing_price)
SELECT p.id, c.id, 'ASIN-' || p.sku, p.name, p.cost_price * 2.5
FROM products p
CROSS JOIN channels c
WHERE c.name = 'amazon';

-- Sample inventory
INSERT INTO inventory (product_id, channel_id, warehouse_id, quantity_available, reorder_point)
SELECT p.id, c.id, w.id, 100, 20
FROM products p
CROSS JOIN channels c
CROSS JOIN warehouses w
WHERE w.code = 'MAIN_WAREHOUSE'
LIMIT 10;
*/

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE channels IS 'E-commerce sales channels (Amazon, Shopify, Walmart)';
COMMENT ON TABLE products IS 'Unified product catalog across all channels';
COMMENT ON TABLE channel_products IS 'Channel-specific product listings and prices';
COMMENT ON TABLE orders IS 'All orders across channels';
COMMENT ON TABLE order_items IS 'Line items for each order';
COMMENT ON TABLE inventory IS 'Current inventory levels by product, channel, and warehouse';
COMMENT ON TABLE forecasts IS 'ML-generated sales forecasts';
COMMENT ON TABLE alerts IS 'System-generated alerts and notifications';
COMMENT ON TABLE daily_sales_summary IS 'Materialized view of daily sales aggregations';
COMMENT ON TABLE product_performance IS 'Materialized view of product-level performance metrics';
