import sqlite3
from datetime import datetime, timedelta
import csv
import json
import re
from typing import Optional, Dict

DB_PATH = "expenses.db"

class ExpenseStorage:
    """Storage layer for expense entries using SQLite."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.conn = sqlite3.connect(db_path)
        self._create_table()

    def _create_table(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                timestamp TEXT NOT NULL
            )
            """
        )
        self.conn.commit()

    def add_expense(self, amount: float, category: str, timestamp: datetime) -> None:
        self.conn.execute(
            "INSERT INTO expenses(amount, category, timestamp) VALUES(?,?,?)",
            (amount, category, timestamp.isoformat()),
        )
        self.conn.commit()

    def weekly_summary(self) -> Dict[str, float]:
        """Return total expenses per category for the current week."""
        now = datetime.now()
        start_of_week = now - timedelta(days=now.weekday())
        start_dt = datetime.combine(start_of_week.date(), datetime.min.time())
        cur = self.conn.execute(
            """
            SELECT category, SUM(amount) FROM expenses
            WHERE timestamp >= ?
            GROUP BY category
            """,
            (start_dt.isoformat(),),
        )
        return {row[0]: row[1] for row in cur.fetchall()}

    def monthly_category_breakdown(self, category: str) -> Dict[str, float]:
        """Return day-wise totals for a category in the current month."""
        now = datetime.now()
        start = datetime(now.year, now.month, 1)
        if now.month == 12:
            next_month = datetime(now.year + 1, 1, 1)
        else:
            next_month = datetime(now.year, now.month + 1, 1)
        cur = self.conn.execute(
            """
            SELECT DATE(timestamp), SUM(amount) FROM expenses
            WHERE timestamp >= ? AND timestamp < ? AND category = ?
            GROUP BY DATE(timestamp)
            ORDER BY DATE(timestamp)
            """,
            (start.isoformat(), next_month.isoformat(), category),
        )
        return {row[0]: row[1] for row in cur.fetchall()}

    def export_data(self, fmt: str = "csv") -> str:
        """Export all expense records to CSV or JSON. Returns the filename."""
        cur = self.conn.execute(
            "SELECT amount, category, timestamp FROM expenses ORDER BY timestamp"
        )
        rows = [
            {"amount": r[0], "category": r[1], "timestamp": r[2]}
            for r in cur.fetchall()
        ]
        if fmt == "csv":
            filename = "expenses_export.csv"
            with open(filename, "w", newline="") as f:
                writer = csv.DictWriter(
                    f, fieldnames=["amount", "category", "timestamp"]
                )
                writer.writeheader()
                writer.writerows(rows)
            return filename
        if fmt == "json":
            filename = "expenses_export.json"
            with open(filename, "w") as f:
                json.dump(rows, f, indent=2)
            return filename
        raise ValueError("Unsupported format. Use 'csv' or 'json'.")

    def __del__(self) -> None:  # pragma: no cover - ensure connection closes
        try:
            self.conn.close()
        except Exception:
            pass

def parse_expense_message(message: str, *, now: Optional[datetime] = None) -> tuple[float, str, datetime]:
    """Parse messages like 'Spent ₹250 on lunch' into amount, category, and date."""
    now = now or datetime.now()
    amount_match = re.search(r"₹?\s*([0-9]+(?:\.[0-9]+)?)", message)
    category_match = re.search(r"on\s+([A-Za-z]+)", message)
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", message)

    if not amount_match or not category_match:
        raise ValueError("Could not parse expense message")

    amount = float(amount_match.group(1))
    category = category_match.group(1).lower()

    if date_match:
        date = datetime.fromisoformat(date_match.group(1))
    elif "yesterday" in message.lower():
        date = now - timedelta(days=1)
    else:
        date = now

    return amount, category, date
