from __future__ import annotations

from sqlalchemy import Column, Float, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class MarketDataORM(Base):
    __tablename__ = "market_data"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False)
    timestamp = Column(String, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    timeframe = Column(String, nullable=False)


class AnalysisLogORM(Base):
    __tablename__ = "analysis_log"

    id = Column(Integer, primary_key=True)
    brain_name = Column(String, nullable=False)
    decision = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    reasoning = Column(String, nullable=False)


class DecisionLogORM(Base):
    __tablename__ = "decision_log"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    decision = Column(String, nullable=False)
    confidence = Column(Float, nullable=False)
    veto = Column(Integer, nullable=False)


class TradeLogORM(Base):
    __tablename__ = "trade_log"

    id = Column(Integer, primary_key=True)
    symbol = Column(String, nullable=False)
    status = Column(String, nullable=False)
    side = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
