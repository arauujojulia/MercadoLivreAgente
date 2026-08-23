"""
Camada de persistência local. Todo dado vindo da API do Mercado Livre é
normalizado e gravado aqui antes de qualquer processamento — isso evita
chamadas repetidas à API (rate limit) e permite uso parcial offline.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config.settings import DB_PATH

Base = declarative_base()
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(bind=engine)


class Order(Base):
    __tablename__ = "orders"

    id = Column(String, primary_key=True)              # order_id do ML
    item_id = Column(String, index=True)
    item_title = Column(String)
    quantity = Column(Integer)
    unit_price = Column(Float)
    total_amount = Column(Float)
    ml_fee = Column(Float, default=0.0)                 # taxa de venda do ML
    shipping_cost = Column(Float, default=0.0)
    status = Column(String)
    date_created = Column(DateTime, index=True)


class SyncMeta(Base):
    __tablename__ = "sync_meta"

    key = Column(String, primary_key=True)
    value = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()


def upsert_orders(orders: list[dict]) -> int:
    """
    Recebe uma lista de pedidos já normalizados (ver `_normalize_order` em
    agent_core.py) e grava/atualiza no SQLite. Retorna quantidade gravada.
    """
    session = get_session()
    count = 0
    try:
        for o in orders:
            existing = session.get(Order, o["id"])
            if existing:
                for k, v in o.items():
                    setattr(existing, k, v)
            else:
                session.add(Order(**o))
            count += 1
        session.commit()
    finally:
        session.close()
    return count


def get_last_sync() -> str | None:
    session = get_session()
    try:
        row = session.get(SyncMeta, "last_order_sync")
        return row.value if row else None
    finally:
        session.close()


def set_last_sync(iso_timestamp: str) -> None:
    session = get_session()
    try:
        row = session.get(SyncMeta, "last_order_sync")
        if row:
            row.value = iso_timestamp
            row.updated_at = datetime.utcnow()
        else:
            session.add(SyncMeta(key="last_order_sync", value=iso_timestamp, updated_at=datetime.utcnow()))
        session.commit()
    finally:
        session.close()


def orders_as_dataframe() -> pd.DataFrame:
    """Carrega todos os pedidos do SQLite como DataFrame, pronto para análise."""
    with engine.connect() as conn:
        df = pd.read_sql_table("orders", conn)
    if not df.empty:
        df["date_created"] = pd.to_datetime(df["date_created"])
    return df
