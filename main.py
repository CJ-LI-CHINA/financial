from data.collector import DataCollector
from analysis.strategies import StockAnalyzer
from database.postgres import PostgresDB
from data.corporate_actions import CorporateActionsHandler
import argparse

def main():
    parser = argparse.ArgumentParser(description='A股量化分析系统')
    parser.add_argument('--update', action='store_true', help='更新股票数据')
    parser.add_argument('--analyze', type=str, help='分析指定股票代码')
    parser.add_argument('--check', action='store_true', help='检查数据库中的股票数据')
    parser.add_argument('--retry', action='store_true', help='重试失败的股票')
    parser.add_argument('--corporate-actions', action='store_true', help='处理公司行为并更新受影响股票的数据')
    parser.add_argument('--clean', action='store_true', help='清理退市股票数据')
    parser.add_argument('--start', type=str, default='20240101', help='开始日期')
    parser.add_argument('--end', type=str, default='20241231', help='结束日期')
    parser.add_argument('--days', type=int, default=30, help='检查公司行为的天数范围')
    
    args = parser.parse_args()
    
    # 创建数据库连接
    db = PostgresDB()
    
    if args.update:
        # 更新数据（默认检查公司行为）
        collector = DataCollector(db)
        success_codes, failed_codes = collector.update_all_stocks_data(check_corporate_actions=True)
        collector.close()
    
    if args.corporate_actions:
        # 处理公司行为
        handler = CorporateActionsHandler(db)
        updated_stocks = handler.process_corporate_actions(days=args.days)
        print(f"已更新 {len(updated_stocks)} 只股票的数据")
    
    if args.check:
        # 检查数据库
        db_codes, missing_codes = db.check_stocks_in_db()
        db.close()
    
    if args.retry:
        # 重试失败的股票
        collector = DataCollector(db)
        collector.retry_failed_stocks()
        collector.close()
    
    if args.analyze:
        # 分析股票
        analyzer = StockAnalyzer(db)
        analyzer.analyze_kdj_overbought_oversold(args.analyze, args.start, args.end)
        analyzer.close()
        
    if args.clean:
        # 清理退市股票
        collector = DataCollector()
        deleted_count = collector.clean_delisted_stocks(confirm=not args.force)  # 添加--force选项可以跳过确认
        print(f"已删除 {deleted_count} 条退市股票数据")
        collector.close()
    db.close()
def test():
    
        collector = DataCollector()
        collector.retry_failed_stocks()
        collector.close()
if __name__ == "__main__":
    # test()
    # collector = DataCollector()
    # success_codes, failed_codes = collector.update_all_stocks_data(True)
    # collector.close()
    db = PostgresDB()
    df = db.get_stock_data("600737","20250101","20250901")
    db.close()
    main()