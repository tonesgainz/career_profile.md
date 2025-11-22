"""
Prophet Model Implementation for Sales Forecasting

This module implements Facebook Prophet for time series forecasting with
automatic seasonality detection and holiday effects.

Author: Tony V. Nguyen
Email: tony@snfactor.com
"""

import pandas as pd
import numpy as np
from prophet import Prophet
from prophet.diagnostics import cross_validation, performance_metrics
from typing import Dict, Tuple, Optional, List
import logging
import joblib
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ProphetForecaster:
    """
    Prophet-based sales forecasting model with automatic seasonality detection.

    Prophet is particularly good at:
    - Handling missing data and outliers
    - Detecting multiple seasonality patterns (daily, weekly, yearly)
    - Incorporating holiday effects
    - Providing uncertainty intervals

    Attributes:
        model: Trained Prophet model instance
        params: Hyperparameters for the model
        performance_metrics: Dictionary of model performance metrics
    """

    def __init__(
        self,
        seasonality_mode: str = 'multiplicative',
        changepoint_prior_scale: float = 0.05,
        seasonality_prior_scale: float = 10.0,
        yearly_seasonality: bool = True,
        weekly_seasonality: bool = True,
        daily_seasonality: bool = False,
        holidays: Optional[pd.DataFrame] = None,
        growth: str = 'linear'
    ):
        """
        Initialize Prophet forecaster with hyperparameters.

        Args:
            seasonality_mode: 'additive' or 'multiplicative'
            changepoint_prior_scale: Flexibility of trend (higher = more flexible)
            seasonality_prior_scale: Strength of seasonality (higher = stronger)
            yearly_seasonality: Whether to include yearly seasonality
            weekly_seasonality: Whether to include weekly seasonality
            daily_seasonality: Whether to include daily seasonality
            holidays: DataFrame with 'holiday' and 'ds' columns
            growth: 'linear' or 'logistic' growth trend
        """
        self.params = {
            'seasonality_mode': seasonality_mode,
            'changepoint_prior_scale': changepoint_prior_scale,
            'seasonality_prior_scale': seasonality_prior_scale,
            'yearly_seasonality': yearly_seasonality,
            'weekly_seasonality': weekly_seasonality,
            'daily_seasonality': daily_seasonality,
            'growth': growth
        }

        self.model = Prophet(**self.params)

        if holidays is not None:
            self.model.add_country_holidays(country_name='US')

        self.performance_metrics = {}
        self.is_trained = False

        logger.info(f"Initialized Prophet model with params: {self.params}")

    def prepare_data(self, df: pd.DataFrame, date_col: str = 'date', value_col: str = 'sales') -> pd.DataFrame:
        """
        Prepare data in Prophet's required format (ds, y columns).

        Args:
            df: Input DataFrame with sales data
            date_col: Name of the date column
            value_col: Name of the value/sales column

        Returns:
            DataFrame with 'ds' (datestamp) and 'y' (value) columns
        """
        prophet_df = pd.DataFrame({
            'ds': pd.to_datetime(df[date_col]),
            'y': df[value_col].astype(float)
        })

        # Sort by date
        prophet_df = prophet_df.sort_values('ds').reset_index(drop=True)

        # Remove duplicates (keep last)
        prophet_df = prophet_df.drop_duplicates(subset=['ds'], keep='last')

        logger.info(f"Prepared {len(prophet_df)} data points for training")
        return prophet_df

    def add_custom_seasonality(self, name: str, period: float, fourier_order: int):
        """
        Add custom seasonality pattern.

        Args:
            name: Name of the seasonality component
            period: Period of the seasonality in days
            fourier_order: Number of Fourier terms to use
        """
        self.model.add_seasonality(
            name=name,
            period=period,
            fourier_order=fourier_order
        )
        logger.info(f"Added custom seasonality: {name} (period={period}, fourier_order={fourier_order})")

    def add_regressors(self, regressor_names: List[str]):
        """
        Add additional regressors (external variables) to the model.

        Args:
            regressor_names: List of regressor column names
        """
        for regressor in regressor_names:
            self.model.add_regressor(regressor)
            logger.info(f"Added regressor: {regressor}")

    def train(
        self,
        train_data: pd.DataFrame,
        validation_split: float = 0.2
    ) -> Dict[str, float]:
        """
        Train the Prophet model.

        Args:
            train_data: Training data in Prophet format (ds, y)
            validation_split: Fraction of data to use for validation

        Returns:
            Dictionary of training metrics
        """
        logger.info(f"Training Prophet model on {len(train_data)} samples...")

        # Split data for validation
        split_idx = int(len(train_data) * (1 - validation_split))
        train_df = train_data.iloc[:split_idx]
        val_df = train_data.iloc[split_idx:]

        # Fit model
        start_time = datetime.now()
        self.model.fit(train_df)
        training_time = (datetime.now() - start_time).total_seconds()

        self.is_trained = True
        logger.info(f"Training completed in {training_time:.2f} seconds")

        # Evaluate on validation set
        metrics = self.evaluate(val_df)
        metrics['training_time_seconds'] = training_time
        metrics['training_samples'] = len(train_df)
        metrics['validation_samples'] = len(val_df)

        self.performance_metrics = metrics

        logger.info(f"Validation Metrics - MAE: {metrics['mae']:.2f}, RMSE: {metrics['rmse']:.2f}, MAPE: {metrics['mape']:.2f}%")

        return metrics

    def predict(
        self,
        horizon_days: int,
        include_history: bool = False,
        frequency: str = 'D'
    ) -> pd.DataFrame:
        """
        Generate forecasts for future periods.

        Args:
            horizon_days: Number of days to forecast
            include_history: Whether to include historical fitted values
            frequency: Frequency of predictions ('D' for daily, 'W' for weekly)

        Returns:
            DataFrame with forecasts and confidence intervals
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before making predictions")

        # Create future dataframe
        future = self.model.make_future_dataframe(
            periods=horizon_days,
            freq=frequency,
            include_history=include_history
        )

        # Generate forecast
        forecast = self.model.predict(future)

        if not include_history:
            # Return only future predictions
            forecast = forecast.tail(horizon_days)

        logger.info(f"Generated {len(forecast)} predictions")

        return forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper', 'trend',
                        'yearly', 'weekly']]

    def evaluate(self, test_data: pd.DataFrame) -> Dict[str, float]:
        """
        Evaluate model performance on test data.

        Args:
            test_data: Test data in Prophet format (ds, y)

        Returns:
            Dictionary with MAE, RMSE, MAPE, and R² metrics
        """
        # Generate predictions for test period
        future = pd.DataFrame({'ds': test_data['ds']})
        forecast = self.model.predict(future)

        # Merge with actual values
        comparison = test_data.merge(
            forecast[['ds', 'yhat', 'yhat_lower', 'yhat_upper']],
            on='ds',
            how='inner'
        )

        actual = comparison['y'].values
        predicted = comparison['yhat'].values

        # Calculate metrics
        mae = np.mean(np.abs(actual - predicted))
        rmse = np.sqrt(np.mean((actual - predicted) ** 2))
        mape = np.mean(np.abs((actual - predicted) / actual)) * 100

        # R-squared
        ss_res = np.sum((actual - predicted) ** 2)
        ss_tot = np.sum((actual - np.mean(actual)) ** 2)
        r2 = 1 - (ss_res / ss_tot)

        # Coverage (percentage of actuals within confidence interval)
        within_interval = (
            (actual >= comparison['yhat_lower'].values) &
            (actual <= comparison['yhat_upper'].values)
        ).mean() * 100

        metrics = {
            'mae': float(mae),
            'rmse': float(rmse),
            'mape': float(mape),
            'r2': float(r2),
            'coverage': float(within_interval)
        }

        return metrics

    def cross_validate(
        self,
        data: pd.DataFrame,
        initial: str = '730 days',
        period: str = '90 days',
        horizon: str = '30 days'
    ) -> pd.DataFrame:
        """
        Perform time series cross-validation.

        Args:
            data: Full dataset in Prophet format
            initial: Initial training period
            period: Period between cutoff dates
            horizon: Forecast horizon

        Returns:
            DataFrame with cross-validation metrics
        """
        logger.info("Performing cross-validation...")

        df_cv = cross_validation(
            self.model,
            initial=initial,
            period=period,
            horizon=horizon
        )

        df_metrics = performance_metrics(df_cv)

        avg_metrics = {
            'mae': df_metrics['mae'].mean(),
            'rmse': df_metrics['rmse'].mean(),
            'mape': df_metrics['mape'].mean(),
        }

        logger.info(f"Cross-validation results: {avg_metrics}")

        return df_metrics

    def get_component_importance(self) -> Dict[str, float]:
        """
        Get the relative importance of different forecast components.

        Returns:
            Dictionary with component importance scores
        """
        # Create a future dataframe for a full year
        future = self.model.make_future_dataframe(periods=365, freq='D')
        forecast = self.model.predict(future)

        # Calculate variance contribution of each component
        components = {}

        if 'trend' in forecast.columns:
            components['trend'] = forecast['trend'].var()

        if 'yearly' in forecast.columns:
            components['yearly'] = forecast['yearly'].var()

        if 'weekly' in forecast.columns:
            components['weekly'] = forecast['weekly'].var()

        # Normalize to percentages
        total_var = sum(components.values())
        component_importance = {
            k: (v / total_var * 100) for k, v in components.items()
        }

        return component_importance

    def save_model(self, filepath: str):
        """
        Save trained model to disk.

        Args:
            filepath: Path to save the model
        """
        if not self.is_trained:
            raise ValueError("Cannot save untrained model")

        model_data = {
            'model': self.model,
            'params': self.params,
            'performance_metrics': self.performance_metrics,
            'is_trained': self.is_trained
        }

        joblib.dump(model_data, filepath)
        logger.info(f"Model saved to {filepath}")

    @classmethod
    def load_model(cls, filepath: str) -> 'ProphetForecaster':
        """
        Load trained model from disk.

        Args:
            filepath: Path to the saved model

        Returns:
            Loaded ProphetForecaster instance
        """
        model_data = joblib.load(filepath)

        instance = cls(**model_data['params'])
        instance.model = model_data['model']
        instance.performance_metrics = model_data['performance_metrics']
        instance.is_trained = model_data['is_trained']

        logger.info(f"Model loaded from {filepath}")
        return instance


# Example usage
if __name__ == "__main__":
    # Generate sample data
    np.random.seed(42)
    dates = pd.date_range(start='2022-01-01', end='2024-12-31', freq='D')

    # Simulate sales with trend, seasonality, and noise
    trend = np.linspace(100, 200, len(dates))
    yearly_seasonality = 30 * np.sin(2 * np.pi * np.arange(len(dates)) / 365)
    weekly_seasonality = 10 * np.sin(2 * np.pi * np.arange(len(dates)) / 7)
    noise = np.random.normal(0, 10, len(dates))

    sales = trend + yearly_seasonality + weekly_seasonality + noise
    sales = np.maximum(sales, 0)  # Ensure non-negative

    df = pd.DataFrame({
        'date': dates,
        'sales': sales
    })

    # Initialize and train model
    forecaster = ProphetForecaster(
        seasonality_mode='additive',
        changepoint_prior_scale=0.1,
        yearly_seasonality=True,
        weekly_seasonality=True
    )

    # Prepare data
    prophet_data = forecaster.prepare_data(df, date_col='date', value_col='sales')

    # Train
    metrics = forecaster.train(prophet_data, validation_split=0.2)
    print(f"\nTraining Metrics:")
    for metric, value in metrics.items():
        print(f"  {metric}: {value}")

    # Generate forecast
    forecast = forecaster.predict(horizon_days=30)
    print(f"\n30-Day Forecast:")
    print(forecast.head())
    print(f"\nTotal predicted sales (next 30 days): {forecast['yhat'].sum():.2f}")

    # Component importance
    importance = forecaster.get_component_importance()
    print(f"\nComponent Importance:")
    for component, pct in importance.items():
        print(f"  {component}: {pct:.1f}%")

    # Save model
    forecaster.save_model('models/prophet_example.pkl')
    print(f"\nModel saved successfully")
