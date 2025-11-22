"""
LSTM Model Implementation for Sales Forecasting

This module implements LSTM (Long Short-Term Memory) neural networks for
time series forecasting with support for multivariate inputs.

Author: Tony V. Nguyen
Email: tony@snfactor.com
"""

import numpy as np
import pandas as pd
from typing import Tuple, Dict, Optional, List
import logging
from datetime import datetime

# TensorFlow/Keras imports
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import LSTM, Dense, Dropout, Bidirectional
from tensorflow.keras.callbacks import EarlyStopping, ModelCheckpoint, ReduceLROnPlateau
from sklearn.preprocessing import MinMaxScaler
import joblib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LSTMForecaster:
    """
    LSTM-based sales forecasting model for capturing complex temporal patterns.

    LSTM networks excel at:
    - Capturing long-term dependencies in sequential data
    - Modeling non-linear relationships
    - Handling multivariate time series
    - Learning complex seasonal patterns

    Attributes:
        model: Trained Keras LSTM model
        scaler: MinMaxScaler for data normalization
        sequence_length: Number of time steps to look back
        hyperparameters: Dictionary of model hyperparameters
    """

    def __init__(
        self,
        sequence_length: int = 60,
        lstm_units: List[int] = [50, 50],
        dropout_rate: float = 0.2,
        learning_rate: float = 0.001,
        batch_size: int = 32,
        epochs: int = 100,
        bidirectional: bool = False
    ):
        """
        Initialize LSTM forecaster with hyperparameters.

        Args:
            sequence_length: Number of previous time steps to use for prediction
            lstm_units: List of LSTM layer sizes
            dropout_rate: Dropout rate for regularization
            learning_rate: Learning rate for Adam optimizer
            batch_size: Batch size for training
            epochs: Maximum number of training epochs
            bidirectional: Whether to use bidirectional LSTM layers
        """
        self.sequence_length = sequence_length
        self.hyperparameters = {
            'sequence_length': sequence_length,
            'lstm_units': lstm_units,
            'dropout_rate': dropout_rate,
            'learning_rate': learning_rate,
            'batch_size': batch_size,
            'epochs': epochs,
            'bidirectional': bidirectional
        }

        self.model = None
        self.scaler_X = MinMaxScaler(feature_range=(0, 1))
        self.scaler_y = MinMaxScaler(feature_range=(0, 1))
        self.feature_columns = None
        self.is_trained = False
        self.training_history = None

        logger.info(f"Initialized LSTM model with params: {self.hyperparameters}")

    def create_sequences(
        self,
        data: np.ndarray,
        target: np.ndarray,
        sequence_length: int
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Create input sequences and targets for LSTM.

        Args:
            data: Feature data array
            target: Target values array
            sequence_length: Length of input sequences

        Returns:
            Tuple of (X_sequences, y_targets)
        """
        X, y = [], []

        for i in range(len(data) - sequence_length):
            X.append(data[i:i + sequence_length])
            y.append(target[i + sequence_length])

        return np.array(X), np.array(y)

    def prepare_data(
        self,
        df: pd.DataFrame,
        target_col: str = 'sales',
        feature_cols: Optional[List[str]] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Prepare and normalize data for LSTM training.

        Args:
            df: Input DataFrame
            target_col: Name of target column
            feature_cols: List of feature column names (None = use only target)

        Returns:
            Tuple of (features, target)
        """
        # If no feature columns specified, use only target
        if feature_cols is None:
            feature_cols = [target_col]

        self.feature_columns = feature_cols

        # Extract features and target
        features = df[feature_cols].values
        target = df[target_col].values.reshape(-1, 1)

        # Normalize data
        features_scaled = self.scaler_X.fit_transform(features)
        target_scaled = self.scaler_y.fit_transform(target)

        logger.info(f"Prepared data: {len(df)} samples, {len(feature_cols)} features")

        return features_scaled, target_scaled

    def build_model(self, n_features: int):
        """
        Build LSTM model architecture.

        Args:
            n_features: Number of input features
        """
        model = Sequential()

        lstm_units = self.hyperparameters['lstm_units']
        dropout_rate = self.hyperparameters['dropout_rate']
        bidirectional = self.hyperparameters['bidirectional']

        # First LSTM layer
        if bidirectional:
            model.add(Bidirectional(
                LSTM(
                    units=lstm_units[0],
                    return_sequences=len(lstm_units) > 1,
                    input_shape=(self.sequence_length, n_features)
                )
            ))
        else:
            model.add(LSTM(
                units=lstm_units[0],
                return_sequences=len(lstm_units) > 1,
                input_shape=(self.sequence_length, n_features)
            ))
        model.add(Dropout(dropout_rate))

        # Additional LSTM layers
        for i in range(1, len(lstm_units)):
            return_sequences = i < len(lstm_units) - 1

            if bidirectional:
                model.add(Bidirectional(LSTM(
                    units=lstm_units[i],
                    return_sequences=return_sequences
                )))
            else:
                model.add(LSTM(
                    units=lstm_units[i],
                    return_sequences=return_sequences
                ))
            model.add(Dropout(dropout_rate))

        # Dense layers for output
        model.add(Dense(units=25, activation='relu'))
        model.add(Dense(units=1))

        # Compile model
        optimizer = keras.optimizers.Adam(
            learning_rate=self.hyperparameters['learning_rate']
        )
        model.compile(
            optimizer=optimizer,
            loss='mse',
            metrics=['mae', 'mape']
        )

        self.model = model

        logger.info(f"Built LSTM model with {model.count_params():,} parameters")
        logger.info(f"Model architecture:\n{model.summary()}")

    def train(
        self,
        train_data: pd.DataFrame,
        target_col: str = 'sales',
        feature_cols: Optional[List[str]] = None,
        validation_split: float = 0.2,
        early_stopping_patience: int = 15
    ) -> Dict[str, any]:
        """
        Train the LSTM model.

        Args:
            train_data: Training DataFrame
            target_col: Name of target column
            feature_cols: List of feature columns
            validation_split: Fraction for validation
            early_stopping_patience: Patience for early stopping

        Returns:
            Dictionary with training metrics and history
        """
        logger.info(f"Training LSTM model on {len(train_data)} samples...")

        # Prepare data
        features_scaled, target_scaled = self.prepare_data(
            train_data,
            target_col=target_col,
            feature_cols=feature_cols
        )

        # Create sequences
        X, y = self.create_sequences(
            features_scaled,
            target_scaled,
            self.sequence_length
        )

        # Build model
        self.build_model(n_features=features_scaled.shape[1])

        # Split into train and validation
        split_idx = int(len(X) * (1 - validation_split))
        X_train, X_val = X[:split_idx], X[split_idx:]
        y_train, y_val = y[:split_idx], y[split_idx:]

        # Define callbacks
        callbacks = [
            EarlyStopping(
                monitor='val_loss',
                patience=early_stopping_patience,
                restore_best_weights=True,
                verbose=1
            ),
            ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=5,
                min_lr=1e-7,
                verbose=1
            ),
            ModelCheckpoint(
                'models/lstm_best.keras',
                monitor='val_loss',
                save_best_only=True,
                verbose=0
            )
        ]

        # Train model
        start_time = datetime.now()
        history = self.model.fit(
            X_train,
            y_train,
            batch_size=self.hyperparameters['batch_size'],
            epochs=self.hyperparameters['epochs'],
            validation_data=(X_val, y_val),
            callbacks=callbacks,
            verbose=1
        )
        training_time = (datetime.now() - start_time).total_seconds()

        self.is_trained = True
        self.training_history = history.history

        # Evaluate on validation set
        val_predictions = self.model.predict(X_val, verbose=0)
        val_predictions_rescaled = self.scaler_y.inverse_transform(val_predictions)
        y_val_rescaled = self.scaler_y.inverse_transform(y_val)

        metrics = self._calculate_metrics(y_val_rescaled, val_predictions_rescaled)
        metrics['training_time_seconds'] = training_time
        metrics['training_samples'] = len(X_train)
        metrics['validation_samples'] = len(X_val)
        metrics['epochs_trained'] = len(history.history['loss'])

        logger.info(f"Training completed in {training_time:.2f} seconds")
        logger.info(f"Validation Metrics - MAE: {metrics['mae']:.2f}, RMSE: {metrics['rmse']:.2f}, MAPE: {metrics['mape']:.2f}%")

        return {
            'metrics': metrics,
            'history': history.history
        }

    def predict(
        self,
        data: pd.DataFrame,
        horizon_days: int = 30,
        recursive: bool = True
    ) -> np.ndarray:
        """
        Generate forecasts.

        Args:
            data: Recent historical data for context
            horizon_days: Number of days to forecast
            recursive: Whether to use recursive multi-step forecasting

        Returns:
            Array of predictions
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before making predictions")

        # Prepare input data
        features = data[self.feature_columns].values
        features_scaled = self.scaler_X.transform(features)

        predictions = []

        if recursive:
            # Recursive forecasting: use previous predictions as input
            current_sequence = features_scaled[-self.sequence_length:].copy()

            for _ in range(horizon_days):
                # Reshape for prediction
                input_seq = current_sequence.reshape(1, self.sequence_length, -1)

                # Predict next value
                pred_scaled = self.model.predict(input_seq, verbose=0)[0][0]
                predictions.append(pred_scaled)

                # Update sequence with prediction
                new_features = current_sequence[-1].copy()
                new_features[0] = pred_scaled  # Assuming target is first feature
                current_sequence = np.vstack([current_sequence[1:], new_features])

        else:
            # Direct forecasting: use actual data for all predictions
            for i in range(len(features_scaled) - self.sequence_length, len(features_scaled)):
                if len(predictions) >= horizon_days:
                    break

                input_seq = features_scaled[i-self.sequence_length:i].reshape(1, self.sequence_length, -1)
                pred_scaled = self.model.predict(input_seq, verbose=0)[0][0]
                predictions.append(pred_scaled)

        # Rescale predictions
        predictions = np.array(predictions).reshape(-1, 1)
        predictions_rescaled = self.scaler_y.inverse_transform(predictions)

        logger.info(f"Generated {len(predictions_rescaled)} predictions")

        return predictions_rescaled.flatten()

    def evaluate(self, test_data: pd.DataFrame, target_col: str = 'sales') -> Dict[str, float]:
        """
        Evaluate model performance on test data.

        Args:
            test_data: Test DataFrame
            target_col: Name of target column

        Returns:
            Dictionary with evaluation metrics
        """
        # Prepare data
        features_scaled, target_scaled = self.prepare_data(
            test_data,
            target_col=target_col,
            feature_cols=self.feature_columns
        )

        # Create sequences
        X_test, y_test = self.create_sequences(
            features_scaled,
            target_scaled,
            self.sequence_length
        )

        # Make predictions
        predictions_scaled = self.model.predict(X_test, verbose=0)

        # Rescale
        predictions = self.scaler_y.inverse_transform(predictions_scaled)
        actuals = self.scaler_y.inverse_transform(y_test)

        # Calculate metrics
        metrics = self._calculate_metrics(actuals, predictions)

        logger.info(f"Test Metrics - MAE: {metrics['mae']:.2f}, RMSE: {metrics['rmse']:.2f}, MAPE: {metrics['mape']:.2f}%")

        return metrics

    def _calculate_metrics(self, y_true: np.ndarray, y_pred: np.ndarray) -> Dict[str, float]:
        """Calculate performance metrics."""
        mae = np.mean(np.abs(y_true - y_pred))
        rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
        mape = np.mean(np.abs((y_true - y_pred) / y_true)) * 100

        ss_res = np.sum((y_true - y_pred) ** 2)
        ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
        r2 = 1 - (ss_res / ss_tot)

        return {
            'mae': float(mae),
            'rmse': float(rmse),
            'mape': float(mape),
            'r2': float(r2)
        }

    def save_model(self, model_path: str, scaler_path: str):
        """Save trained model and scalers."""
        if not self.is_trained:
            raise ValueError("Cannot save untrained model")

        self.model.save(model_path)

        scaler_data = {
            'scaler_X': self.scaler_X,
            'scaler_y': self.scaler_y,
            'sequence_length': self.sequence_length,
            'feature_columns': self.feature_columns,
            'hyperparameters': self.hyperparameters
        }
        joblib.dump(scaler_data, scaler_path)

        logger.info(f"Model saved to {model_path}, scalers saved to {scaler_path}")

    @classmethod
    def load_model(cls, model_path: str, scaler_path: str) -> 'LSTMForecaster':
        """Load trained model and scalers."""
        scaler_data = joblib.load(scaler_path)

        instance = cls(
            sequence_length=scaler_data['sequence_length'],
            **{k: v for k, v in scaler_data['hyperparameters'].items()
               if k != 'sequence_length'}
        )

        instance.model = load_model(model_path)
        instance.scaler_X = scaler_data['scaler_X']
        instance.scaler_y = scaler_data['scaler_y']
        instance.feature_columns = scaler_data['feature_columns']
        instance.is_trained = True

        logger.info(f"Model loaded from {model_path}")
        return instance


# Example usage
if __name__ == "__main__":
    # Generate sample data
    np.random.seed(42)
    dates = pd.date_range(start='2022-01-01', end='2024-12-31', freq='D')

    # Simulate sales with trend and seasonality
    trend = np.linspace(100, 200, len(dates))
    seasonality = 30 * np.sin(2 * np.pi * np.arange(len(dates)) / 365)
    noise = np.random.normal(0, 10, len(dates))

    sales = trend + seasonality + noise
    sales = np.maximum(sales, 0)

    df = pd.DataFrame({
        'date': dates,
        'sales': sales,
        'day_of_week': dates.dayofweek,
        'month': dates.month
    })

    # Initialize and train
    forecaster = LSTMForecaster(
        sequence_length=60,
        lstm_units=[64, 32],
        dropout_rate=0.2,
        epochs=50
    )

    result = forecaster.train(
        df[:-30],  # Hold out last 30 days
        target_col='sales',
        feature_cols=['sales', 'day_of_week', 'month']
    )

    print(f"\nTraining Metrics: {result['metrics']}")

    # Generate forecast
    forecast = forecaster.predict(df[:-30], horizon_days=30)
    print(f"\n30-Day Forecast: {forecast[:5]}")
    print(f"Total predicted sales: {forecast.sum():.2f}")

    # Evaluate on test set
    test_metrics = forecaster.evaluate(df[-90:], target_col='sales')
    print(f"\nTest Metrics: {test_metrics}")
