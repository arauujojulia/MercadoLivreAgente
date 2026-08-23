"""
Motor de previsão de vendas.

O modelo "oficial" é treinado no Kaggle Notebook (EDA + seleção de
features + validação) e exportado como artefato (.pkl via joblib). Este
módulo só faz *inferência* localmente — nenhum treino pesado roda na
máquina do usuário final.

Um fallback de treino simples (RandomForest sobre poucas features de
calendário) existe apenas para permitir uso do app antes de haver um
modelo "oficial" exportado do Kaggle — ele é substituído pelo artefato
real assim que o arquivo `forecast_model.pkl` estiver disponível.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from config.settings import MODEL_PATH


def _build_features(daily_revenue: pd.DataFrame) -> pd.DataFrame:
    """Features simples de calendário a partir da série diária de faturamento."""
    df = daily_revenue.copy()
    df["day_of_week"] = df["period"].dt.dayofweek
    df["day_of_month"] = df["period"].dt.day
    df["month"] = df["period"].dt.month
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    return df


def train_fallback_model(daily_revenue: pd.DataFrame) -> RandomForestRegressor:
    """Treina um modelo simples local, só para não deixar o forecast vazio."""
    features_df = _build_features(daily_revenue)
    X = features_df[["day_of_week", "day_of_month", "month", "is_weekend"]]
    y = features_df["net_revenue"]

    model = RandomForestRegressor(n_estimators=200, random_state=42)
    model.fit(X, y)
    return model


def load_model() -> RandomForestRegressor | None:
    """Carrega o modelo exportado do Kaggle, se existir localmente."""
    if Path(MODEL_PATH).exists():
        return joblib.load(MODEL_PATH)
    return None


def save_model(model) -> None:
    joblib.dump(model, MODEL_PATH)


def forecast_next_days(daily_revenue: pd.DataFrame, days_ahead: int = 30) -> pd.DataFrame:
    """
    Gera previsão de faturamento líquido para os próximos `days_ahead` dias.
    Usa o modelo do Kaggle se disponível; caso contrário treina o fallback
    on-the-fly (e o salva para não retreinar a cada execução).
    """
    if daily_revenue.empty or len(daily_revenue) < 14:
        return pd.DataFrame(columns=["date", "predicted_net_revenue"])

    model = load_model()
    if model is None:
        model = train_fallback_model(daily_revenue)
        save_model(model)

    last_date = daily_revenue["period"].max()
    future_dates = pd.date_range(start=last_date + pd.Timedelta(days=1), periods=days_ahead, freq="D")
    future_df = pd.DataFrame({"period": future_dates})
    future_features = _build_features(future_df)

    X_future = future_features[["day_of_week", "day_of_month", "month", "is_weekend"]]
    predictions = model.predict(X_future)

    return pd.DataFrame({"date": future_dates, "predicted_net_revenue": predictions})


def backtest_accuracy(daily_revenue: pd.DataFrame, model) -> dict:
    """
    Métricas simples de acurácia (MAE/RMSE) comparando previsão do modelo
    contra o real dos últimos dias disponíveis — usado para logging no W&B.
    """
    from sklearn.metrics import mean_absolute_error, mean_squared_error

    features_df = _build_features(daily_revenue)
    X = features_df[["day_of_week", "day_of_month", "month", "is_weekend"]]
    y_true = features_df["net_revenue"]
    y_pred = model.predict(X)

    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(mean_squared_error(y_true, y_pred) ** 0.5),
    }
