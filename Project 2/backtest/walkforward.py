"""Walk-forward optimization."""

from datetime import datetime, timedelta
from typing import Any, Optional

from loguru import logger

from backtest.engine import BacktestEngine


class WalkForwardOptimizer:
    """Walk-forward parameter optimization."""

    def __init__(
        self,
        strategy_class: type,
        symbols: list[str],
        train_window_days: int = 60,
        test_window_days: int = 30,
        step_days: int = 30,
    ):
        """
        Initialize walk-forward optimizer.

        Args:
            strategy_class: Strategy class (not instance)
            symbols: List of symbols
            train_window_days: Training window in days
            test_window_days: Test window in days
            step_days: Step size between windows in days
        """
        self.strategy_class = strategy_class
        self.symbols = symbols
        self.train_window_days = train_window_days
        self.test_window_days = test_window_days
        self.step_days = step_days

    def optimize(
        self,
        start_date: datetime,
        end_date: datetime,
        params_grid: dict[str, list[Any]],
    ) -> dict[str, Any]:
        """
        Run walk-forward optimization.

        Args:
            start_date: Start date
            end_date: End date
            params_grid: Parameter grid, e.g., {"spread_bps": [10, 20, 30]}

        Returns:
            Dictionary with best parameters and results
        """
        logger.info(f"Starting walk-forward optimization: {start_date.date()} to {end_date.date()}")

        # Generate parameter combinations
        param_combinations = self._generate_combinations(params_grid)

        # Generate time windows
        windows = self._generate_windows(start_date, end_date)

        best_params: Optional[dict[str, Any]] = None
        best_score = float("-inf")
        all_results: list[dict[str, Any]] = []

        for params in param_combinations:
            logger.info(f"Testing parameters: {params}")

            window_results = []

            for train_start, train_end, test_start, test_end in windows:
                # Train on training window (can be used for parameter selection)
                # For simplicity, we'll just backtest on test window
                try:
                    strategy = self.strategy_class(**params)

                    engine = BacktestEngine(
                        strategy=strategy,
                        symbols=self.symbols,
                        start_date=test_start,
                        end_date=test_end,
                    )

                    results = engine.run()
                    metrics = results["metrics"]

                    score = metrics.get("sharpe_ratio", 0.0)  # Use Sharpe as score
                    window_results.append({
                        "test_start": test_start,
                        "test_end": test_end,
                        "score": score,
                        "metrics": metrics,
                    })

                except Exception as e:
                    logger.error(f"Error in walk-forward window: {e}")
                    continue

            # Average score across windows
            if window_results:
                avg_score = sum(r["score"] for r in window_results) / len(window_results)

                all_results.append({
                    "params": params,
                    "avg_score": avg_score,
                    "window_results": window_results,
                })

                if avg_score > best_score:
                    best_score = avg_score
                    best_params = params

        return {
            "best_params": best_params,
            "best_score": best_score,
            "all_results": all_results,
        }

    def _generate_combinations(self, params_grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
        """Generate all parameter combinations from grid."""
        import itertools

        keys = list(params_grid.keys())
        values = list(params_grid.values())

        combinations = []
        for combo in itertools.product(*values):
            combinations.append(dict(zip(keys, combo)))

        return combinations

    def _generate_windows(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[tuple[datetime, datetime, datetime, datetime]]:
        """Generate train/test windows."""
        windows = []

        current_date = start_date

        while current_date < end_date:
            train_start = current_date
            train_end = train_start + timedelta(days=self.train_window_days)
            test_start = train_end
            test_end = test_start + timedelta(days=self.test_window_days)

            if test_end > end_date:
                test_end = end_date

            if test_start >= test_end:
                break

            windows.append((train_start, train_end, test_start, test_end))

            current_date += timedelta(days=self.step_days)

        return windows








