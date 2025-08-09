from datetime import datetime, timedelta
import os
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from expense_tracker import parse_expense_message, ExpenseStorage


def test_parse_expense_message():
    now = datetime(2024, 8, 12, 15, 0, 0)
    amount, category, date = parse_expense_message("Spent ₹250 on lunch", now=now)
    assert amount == 250
    assert category == "lunch"
    assert date == now


def test_storage_queries_and_export(tmp_path):
    original_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        storage = ExpenseStorage(db_path="test.db")
        now = datetime.now()
        storage.add_expense(100, "food", now)
        storage.add_expense(50, "food", now - timedelta(days=1))
        storage.add_expense(20, "food", now - timedelta(days=31))
        storage.add_expense(70, "travel", now)

        weekly = storage.weekly_summary()
        assert weekly["food"] == 150
        assert weekly["travel"] == 70

        monthly = storage.monthly_category_breakdown("food")
        today = now.strftime("%Y-%m-%d")
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        old_date = (now - timedelta(days=31)).strftime("%Y-%m-%d")
        assert monthly[today] == 100
        assert monthly[yesterday] == 50
        assert old_date not in monthly

        csv_file = storage.export_data("csv")
        json_file = storage.export_data("json")
        assert Path(csv_file).exists()
        assert Path(json_file).exists()
    finally:
        os.chdir(original_cwd)
