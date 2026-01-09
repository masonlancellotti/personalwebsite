"""Strategy base class and registry."""

from abc import ABC, abstractmethod
from typing import Any, Optional

import pandas as pd
from pydantic import BaseModel

from execution.intents import OrderIntent

# Strategy registry
_registry: dict[str, type] = {}
_param_schemas: dict[str, type[BaseModel]] = {}
_explanations: dict[str, str] = {}


class StrategyParams(BaseModel):
    """Base parameter schema for strategies."""

    pass


class Strategy(ABC):
    """Abstract base class for trading strategies."""

    def __init__(self, **kwargs):
        """Initialize strategy with parameters."""
        # Validate parameters using schema if available
        # Find the registered name for this class
        strategy_name = None
        for name, cls in _registry.items():
            if cls == self.__class__:
                strategy_name = name
                break
        
        if strategy_name and strategy_name in _param_schemas:
            schema = _param_schemas[strategy_name]
            validated = schema(**kwargs)
            # Copy validated params to self
            for key, value in validated.model_dump().items():
                setattr(self, key, value)
        else:
            # No schema, accept all kwargs
            for key, value in kwargs.items():
                setattr(self, key, value)

    @abstractmethod
    def on_bar(self, symbol: str, bar: pd.Series) -> list[OrderIntent]:
        """
        Called when a new bar is available.

        Args:
            symbol: Symbol
            bar: Bar data (Series with open, high, low, close, volume, etc.)

        Returns:
            List of OrderIntents
        """
        pass

    def on_start(self):
        """Called when strategy starts."""
        pass

    def on_stop(self):
        """Called when strategy stops."""
        pass

    def on_order_fill(self, symbol: str, side: str, qty: float, price: float):
        """Called when an order is filled."""
        pass


def register_strategy(
    name: Optional[str] = None,
    params_schema: Optional[type[BaseModel]] = None,
    explanation: Optional[str] = None,
):
    """
    Decorator to register a strategy.

    Args:
        name: Strategy name (default: class name)
        params_schema: Pydantic model for parameters
        explanation: Strategy explanation text
    """
    def decorator(cls: type[Strategy]):
        strategy_name = name or cls.__name__
        _registry[strategy_name] = cls

        if params_schema:
            _param_schemas[strategy_name] = params_schema

        if explanation:
            _explanations[strategy_name] = explanation

        return cls

    return decorator


def list_strategies() -> list[str]:
    """List all registered strategies."""
    return sorted(_registry.keys())


def get_strategy(name: str) -> type[Strategy]:
    """Get strategy class by name."""
    if name not in _registry:
        raise ValueError(f"Strategy '{name}' not found. Available: {list_strategies()}")
    return _registry[name]


def explain_strategy(name: str) -> dict[str, Any]:
    """Get strategy explanation and parameter schema."""
    if name not in _registry:
        raise ValueError(f"Strategy '{name}' not found. Available: {list_strategies()}")

    info = {
        "name": name,
        "class": _registry[name].__name__,
        "explanation": _explanations.get(name, "No explanation available"),
    }

    if name in _param_schemas:
        schema = _param_schemas[name]
        info["params_schema"] = schema.model_json_schema()

    return info

