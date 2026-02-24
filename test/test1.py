# 测试寻找百亿以下，且有横盘向上趋势的股票；

import sys
import os

# 获取当前文件的目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录（假设项目根目录是folderC的父目录）
project_root = os.path.dirname(current_dir)

# 添加项目根目录到Python路径
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    
    

from data.collector import DataCollector
from analysis.strategies import StockAnalyzer
from database.postgres import PostgresDB
from data.corporate_actions import CorporateActionsHandler
import argparse
if __name__ == "__main__":
    db = PostgresDB()
    df = db.get_stock_data("600737","20250101","20250901")