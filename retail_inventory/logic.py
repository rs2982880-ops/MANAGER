"""
Restocking alert & shelf-optimization engine (grid-aware).
============================================================
Alerts are now based on **grid occupancy** (empty cells) and
position-based sales, not raw count differences.
"""

from collections import defaultdict
from typing import Dict, List, Optional

from utils import calculate_time_to_empty, format_time_remaining


class RestockingEngine:
    """Grid-aware alerts and shelf recommendations."""

    def __init__(
        self,
        stock_threshold: int = 5,
        time_threshold_hours: float = 2.0,
        empty_cell_pct_alert: float = 0.50,
        high_sales_rate: float = 5.0,
        low_sales_rate: float = 1.0,
    ):
        """
        Args:
            stock_threshold:      alert if an item's grid count < this.
            time_threshold_hours: alert if predicted depletion < this.
            empty_cell_pct_alert: alert if shelf is this % empty.
            high_sales_rate:      items/hr considered "high demand".
            low_sales_rate:       items/hr considered "low demand".
        """
        self.stock_threshold = stock_threshold
        self.time_threshold_hours = time_threshold_hours
        self.empty_cell_pct = empty_cell_pct_alert
        self.high_sales_rate = high_sales_rate
        self.low_sales_rate = low_sales_rate

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------
    def check_alerts(
        self,
        stock: Dict[str, int],
        sales_rate: Dict[str, float],
        grid: Optional[List[List[str]]] = None,
    ) -> List[dict]:
        """
        Generate restocking alerts based on:
          1. Item count below threshold
          2. Predicted depletion time < threshold
          3. Shelf grid has too many empty cells
        """
        alerts: List[dict] = []

        # --- Per-item alerts ---
        for item, count in stock.items():
            rate = sales_rate.get(item, 0.0)
            tte = calculate_time_to_empty(count, rate)

            if count < self.stock_threshold:
                severity = "critical" if count <= 2 else "warning"
                action = "Restock immediately!" if count <= 2 else "Restock soon"
                alerts.append({
                    "item": item,
                    "stock": count,
                    "sales_rate": rate,
                    "time_to_empty": tte,
                    "severity": severity,
                    "action": action,
                    "reason": f"Stock below threshold ({self.stock_threshold})",
                })
            elif tte is not None and tte < self.time_threshold_hours:
                alerts.append({
                    "item": item,
                    "stock": count,
                    "sales_rate": rate,
                    "time_to_empty": tte,
                    "severity": "warning",
                    "action": f"Restock within {format_time_remaining(tte)}",
                    "reason": f"Depletes in {format_time_remaining(tte)}",
                })

        # --- Global shelf alert: too many empty cells ---
        if grid:
            total = sum(len(row) for row in grid)
            empty = sum(1 for row in grid for c in row if c == "empty")
            if total > 0 and (empty / total) >= self.empty_cell_pct:
                alerts.append({
                    "item": "SHELF",
                    "stock": total - empty,
                    "sales_rate": 0.0,
                    "time_to_empty": None,
                    "severity": "critical",
                    "action": "Major restock needed!",
                    "reason": f"{empty}/{total} cells empty ({empty/total:.0%})",
                })

        alerts.sort(key=lambda a: 0 if a["severity"] == "critical" else 1)
        return alerts

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------
    def get_recommendations(
        self,
        stock: Dict[str, int],
        sales_rate: Dict[str, float],
        co_occurrence: Optional[Dict[str, List[str]]] = None,
    ) -> List[dict]:
        """
        Rule-based shelf-arrangement suggestions.

        HIGH demand → eye level / centre shelf.
        LOW  demand → reposition for visibility.
        No movement → promotional placement.
        Co-occurrence → place nearby.
        """
        recs: List[dict] = []

        for item, rate in sales_rate.items():
            cur = stock.get(item, 0)

            if rate >= self.high_sales_rate:
                recs.append({
                    "item": item, "type": "high_demand",
                    "reason": f"High demand ({rate:.1f}/hr)",
                    "suggestion": "Place at eye level, centre shelf",
                    "priority": "high",
                })
            elif 0 < rate <= self.low_sales_rate:
                recs.append({
                    "item": item, "type": "low_demand",
                    "reason": f"Low demand ({rate:.1f}/hr)",
                    "suggestion": "Reposition for visibility or bundle with popular items",
                    "priority": "medium",
                })
            elif rate == 0 and cur > 0:
                recs.append({
                    "item": item, "type": "no_movement",
                    "reason": "No sales detected",
                    "suggestion": "Consider promotional placement or discount",
                    "priority": "low",
                })

        if co_occurrence:
            for item, related in co_occurrence.items():
                if related:
                    names = ", ".join(related[:3])
                    recs.append({
                        "item": item, "type": "co_occurrence",
                        "reason": f"Seen with: {names}",
                        "suggestion": f"Place near {names}",
                        "priority": "medium",
                    })

        order = {"high": 0, "medium": 1, "low": 2}
        recs.sort(key=lambda r: order.get(r["priority"], 2))
        return recs

    # ------------------------------------------------------------------
    # Co-occurrence (still useful for recommendations)
    # ------------------------------------------------------------------
    @staticmethod
    def analyse_co_occurrence(
        snapshot_grids: List[List[List[str]]],
        min_ratio: float = 0.5,
    ) -> Dict[str, List[str]]:
        """
        Items that frequently share the same snapshot grid
        are candidates for "place nearby" recommendations.
        """
        co: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        appear: Dict[str, int] = defaultdict(int)

        for grid in snapshot_grids:
            items = set()
            for row in grid:
                for cell in row:
                    if cell != "empty":
                        items.add(cell)
            for item in items:
                appear[item] += 1
                for other in items:
                    if other != item:
                        co[item][other] += 1

        result: Dict[str, List[str]] = {}
        for item, others in co.items():
            total = appear[item]
            if total == 0:
                continue
            freq = [o for o, c in others.items() if c / total >= min_ratio]
            if freq:
                result[item] = freq
        return result
