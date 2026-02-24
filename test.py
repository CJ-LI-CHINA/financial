from data.collector_tdx import DataCollector
from analysis.strategies import StockAnalyzer
from database.postgres import PostgresDB
import argparse
import akshare as ak

df = ak.stock_zh_a_spot_em()
k=1
# start_date = "20100101";
# start_date.strftime('%Y%m%d')
# collector = DataCollector()
# success_codes, failed_codes = collector.update_all_stocks_data()
# collector.close()