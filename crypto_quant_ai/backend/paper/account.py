from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PaperPosition(BaseModel):
    symbol: str
    quantity: float = Field(gt=0)
    avg_cost: float = Field(gt=0)

    @field_validator("symbol")
    @classmethod
    def symbol_must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("symbol must not be blank")
        return value.strip().upper()


class PaperOrder(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    timestamp: datetime

    @field_validator("symbol")
    @classmethod
    def symbol_must_not_be_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("symbol must not be blank")
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_side(self) -> "PaperOrder":
        if self.side not in {"buy", "sell"}:
            raise ValueError("side must be 'buy' or 'sell'")
        return self


class PaperAccount(BaseModel):
    cash: float = Field(default=100000.0, gt=0)
    positions: dict[str, PaperPosition] = Field(default_factory=dict)
    orders: list[PaperOrder] = Field(default_factory=list)

    @field_validator("cash")
    @classmethod
    def cash_must_be_finite(cls, value: float) -> float:
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError("cash must be finite")
        return value

    @model_validator(mode="after")
    def validate_positions(self) -> "PaperAccount":
        for symbol, position in self.positions.items():
            if symbol != symbol.strip().upper():
                raise ValueError(f"position symbol must be uppercase: {symbol}")
            if position.quantity <= 0:
                raise ValueError("position quantity must be positive")
            if position.avg_cost <= 0:
                raise ValueError("position avg_cost must be positive")
        return self


def buy(
    account: PaperAccount,
    symbol: str,
    quantity: float,
    price: float,
) -> tuple[PaperAccount, PaperOrder]:
    """Execute a paper BUY order against the account."""
    cost = quantity * price
    if cost > account.cash:
        raise ValueError(
            f"Insufficient cash: required {cost:.2f}, available {account.cash:.2f}"
        )
    order = PaperOrder(
        symbol=symbol.upper(),
        side="buy",
        quantity=quantity,
        price=price,
        timestamp=datetime.now(timezone.utc),
    )
    # Update positions
    positions = dict(account.positions)
    if symbol.upper() in positions:
        existing = positions[symbol.upper()]
        total_qty = existing.quantity + quantity
        new_avg = (
            existing.avg_cost * existing.quantity + price * quantity
        ) / total_qty
        positions[symbol.upper()] = PaperPosition(
            symbol=symbol.upper(),
            quantity=total_qty,
            avg_cost=new_avg,
        )
    else:
        positions[symbol.upper()] = PaperPosition(
            symbol=symbol.upper(),
            quantity=quantity,
            avg_cost=price,
        )
    new_account = PaperAccount(
        cash=account.cash - cost,
        positions=positions,
        orders=account.orders + [order],
    )
    return new_account, order


def sell(
    account: PaperAccount,
    symbol: str,
    quantity: float,
    price: float,
) -> tuple[PaperAccount, PaperOrder]:
    """Execute a paper SELL order against the account."""
    symbol = symbol.upper()
    if symbol not in account.positions:
        raise ValueError(f"No position to sell for symbol: {symbol}")
    position = account.positions[symbol]
    if quantity > position.quantity:
        raise ValueError(
            f"Cannot sell {quantity} {symbol}: only {position.quantity} held"
        )
    order = PaperOrder(
        symbol=symbol,
        side="sell",
        quantity=quantity,
        price=price,
        timestamp=datetime.now(timezone.utc),
    )
    # Update positions
    positions = dict(account.positions)
    remaining = position.quantity - quantity
    if remaining <= 1e-9:
        del positions[symbol]
    else:
        positions[symbol] = PaperPosition(
            symbol=symbol,
            quantity=remaining,
            avg_cost=position.avg_cost,
        )
    new_account = PaperAccount(
        cash=account.cash + quantity * price,
        positions=positions,
        orders=account.orders + [order],
    )
    return new_account, order
