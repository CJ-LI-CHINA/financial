from data.collector import DataCollector
from analysis.strategies import StockAnalyzer
from database.postgres import PostgresDB
from data.corporate_actions import CorporateActionsHandler
import argparse
from datetime import datetime, time, timedelta
from utils.helpers import is_trading_day, determine_end_date

# 更新数据（默认检查公司行为）
now = datetime.now()
if not is_trading_day(now.date()):
    print("非工作日不更新")
else:
    collector = DataCollector()
    success_codes, failed_codes = collector.update_all_stocks_data()
    collector.retry_failed_stocks()
    collector.close()
k=1