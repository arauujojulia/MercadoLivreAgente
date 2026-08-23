"""
Motor financeiro: transforma o histórico de pedidos (SQLite) em métricas de
negócio — faturamento, taxas, lucro líquido e performance por produto.
"""

from __future__ import annotations

import pandas as pd


def revenue_summary(df: pd.DataFrame, period: str = "D") -> pd.DataFrame:
    """
    Agrega faturamento bruto/líquido por período ('D' diário, 'W' semanal, 'M' mensal).
    """
    if df.empty:
        return pd.DataFrame(columns=["period", "gross_revenue", "ml_fees", "shipping_cost", "net_revenue"])

    grouped = (
        df.set_index("date_created")
        .resample(period)
        .agg(
            gross_revenue=("total_amount", "sum"),
            ml_fees=("ml_fee", "sum"),
            shipping_cost=("shipping_cost", "sum"),
        )
        .reset_index()
        .rename(columns={"date_created": "period"})
    )
    grouped["net_revenue"] = (
        grouped["gross_revenue"] - grouped["ml_fees"] - grouped["shipping_cost"]
    )
    return grouped


def product_performance(df: pd.DataFrame, top_n: int = 10) -> dict[str, pd.DataFrame]:
    """
    Retorna os produtos que mais e menos vendem, por quantidade e por
    faturamento líquido.
    """
    if df.empty:
        empty = pd.DataFrame(columns=["item_id", "item_title", "quantity", "net_revenue"])
        return {"top_sellers": empty, "worst_sellers": empty}

    df = df.copy()
    df["net_revenue"] = df["total_amount"] - df["ml_fee"] - df["shipping_cost"]

    by_product = (
        df.groupby(["item_id", "item_title"])
        .agg(quantity=("quantity", "sum"), net_revenue=("net_revenue", "sum"))
        .reset_index()
        .sort_values("net_revenue", ascending=False)
    )

    return {
        "top_sellers": by_product.head(top_n),
        "worst_sellers": by_product.tail(top_n).sort_values("net_revenue"),
    }


def operating_costs_breakdown(df: pd.DataFrame) -> dict:
    """Resumo simples de custos operacionais no período total carregado."""
    if df.empty:
        return {"ml_fees": 0.0, "shipping_cost": 0.0, "total_costs": 0.0}

    ml_fees = float(df["ml_fee"].sum())
    shipping = float(df["shipping_cost"].sum())
    return {
        "ml_fees": ml_fees,
        "shipping_cost": shipping,
        "total_costs": ml_fees + shipping,
    }


def kpi_summary(df: pd.DataFrame) -> dict:
    """Conjunto de KPIs de topo de dashboard."""
    if df.empty:
        return {
            "gross_revenue": 0.0,
            "net_revenue": 0.0,
            "orders_count": 0,
            "avg_ticket": 0.0,
            "margin_pct": 0.0,
        }

    gross = float(df["total_amount"].sum())
    costs = operating_costs_breakdown(df)["total_costs"]
    net = gross - costs
    orders_count = int(df["id"].nunique())
    avg_ticket = gross / orders_count if orders_count else 0.0
    margin_pct = (net / gross * 100) if gross else 0.0

    return {
        "gross_revenue": gross,
        "net_revenue": net,
        "orders_count": orders_count,
        "avg_ticket": avg_ticket,
        "margin_pct": margin_pct,
    }
