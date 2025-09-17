import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
import time as sleep_time
import csv
from config.settings import DATA_CONFIG
from database.postgres import PostgresDB
from data.indicators import calculate_all_indicators
from utils.helpers import is_trading_day, determine_end_date

class DataCollector:
    def __init__(self):
        self.db = PostgresDB()
        self.failed_codes_file = DATA_CONFIG["failed_codes_file"]
    
    def get_stock_list(self):
        """获取所有A股股票列表，排除北交所股票"""
        try:
            stock_list_df = ak.stock_info_a_code_name()
            print(f"获取股票列表数量: {len(stock_list_df)}")
            
            # 排除北交所股票（代码以8或43开头的股票）
            # 北交所股票通常以8开头，也有部分以43开头
            stock_list_df = stock_list_df[~stock_list_df['code'].str.startswith(('8', '43','92'))]
            print(f"排除北交所股票后数量: {len(stock_list_df)}")
            
            return stock_list_df
        except Exception as e:
            print(f"获取股票列表失败: {e}")
            return None
    
    def process_stock_data(self, code, start_date, end_date):
        """处理单只股票的数据"""
        try:
            # 获取股票日线数据（前复权）
            symbol = f"sh{code}" if code.startswith('6') else f"sz{code}"
            df = ak.stock_zh_a_daily(symbol=symbol, start_date=start_date, 
                                   end_date=end_date, adjust="qfq")
            
            if df.empty:
                print(f"股票 {code} 无前复权数据，跳过。")
                return None, "无前复权数据"
            
            # 计算指标
            df = calculate_all_indicators(df)
            
            # 准备插入数据（处理NaN为None）
            data = []
            for _, row in df.iterrows():
                data.append((
                    row['date'], code, row['open'], row['high'], row['low'], row['close'], int(row['volume']),
                    row['ma5'] if not np.isnan(row['ma5']) else None,
                    row['ma10'] if not np.isnan(row['ma10']) else None,
                    row['ma20'] if not np.isnan(row['ma20']) else None,
                    row['macd'] if not np.isnan(row['macd']) else None,
                    row['macd_signal'] if not np.isnan(row['macd_signal']) else None,
                    row['macd_hist'] if not np.isnan(row['macd_hist']) else None,
                    row['kdj_k'] if not np.isnan(row['kdj_k']) else None,
                    row['kdj_d'] if not np.isnan(row['kdj_d']) else None,
                    row['kdj_j'] if not np.isnan(row['kdj_j']) else None
                ))
            
            return data, None
        except Exception as e:
            print(f"股票 {code} 数据处理失败：{e}")
            return None, str(e)
    
    def update_all_stocks_data(self, retry_failed=False):
        """更新所有股票的数据"""
        # 获取数据库中各股票的最新日期
        latest_dates = self.db.get_latest_dates()
        
        # 获取所有A股股票列表（已排除北交所）
        stock_list_df = self.get_stock_list()
        if stock_list_df is None:
            return [], []
        
        codes = stock_list_df['code'].tolist()
        
        if retry_failed:
            try:
                failed_df = pd.read_csv(self.failed_codes_file, dtype={'code': str})
                # 确保重试时也排除北交所股票
                failed_codes = failed_df['code'].tolist()
                # 过滤掉北交所股票代码
                codes = [code for code in failed_codes if not code.startswith(('8', '43','92'))]
                print(f"重试失败股票列表，从 {self.failed_codes_file} 加载 {len(codes)} 只股票（已排除北交所）。")
            except FileNotFoundError:
                print(f"未找到 {self.failed_codes_file}，无法重试失败股票。")
                return [], []
        
        # 确定更新结束日期
        end_date = determine_end_date()
        print(f"更新结束日期: {end_date}")
        
        # 记录成功和失败的股票
        success_codes = []
        failed_codes = []
        
        for code in codes:
            # 确定该股票的起始日期
            if code in latest_dates:
                start_date = latest_dates[code] + timedelta(days=1)
                # 如果起始日期大于结束日期，则跳过
                if start_date > end_date:
                    print(f"股票 {code} 已是最新数据，跳过。")
                    success_codes.append(code)
                    continue
            else:
                # 如果数据库中无该股票数据，则从默认开始日期
                start_date = DATA_CONFIG["default_start_date"]
            
            # 处理股票数据
            data, error = self.process_stock_data(code, start_date, end_date.strftime('%Y%m%d'))
            if data is None:
                failed_codes.append((code, error))
                continue
            
            # 插入数据
            inserted_count = self.db.insert_stock_data(data)
            if inserted_count > 0:
                success_codes.append(code)
                print(f"股票 {code} 数据处理并插入完成，更新了 {inserted_count} 条记录。")
            else:
                failed_codes.append((code, "插入数据失败"))
            
            # 避免AKShare限频
            sleep_time.sleep(DATA_CONFIG["retry_interval"])
        
        # 保存失败股票到CSV
        if failed_codes:
            with open(self.failed_codes_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['code', 'error'])
                writer.writerows(failed_codes)
        
        # 打印成功和失败统计
        print(f"\n数据更新完成：")
        print(f"成功股票数量：{len(success_codes)}")
        print(f"失败股票数量：{len(failed_codes)}，详情已保存到 {self.failed_codes_file}")
        
        #暂时不开；
        # if not retry_failed:  # 只在完整更新时清理，不在重试时清理
        #     self.clean_delisted_stocks(confirm=False)
            
        return success_codes, failed_codes
    
    def retry_failed_stocks(self, max_retries=3):
        """补救失败的股票数据"""
        for attempt in range(1, max_retries + 1):
            print(f"\n第 {attempt} 次重试失败股票...")
            success_codes, failed_codes = self.update_all_stocks_data(retry_failed=True)
            if not failed_codes:
                print("所有失败股票已成功补救。")
                break
            print(f"第 {attempt} 次重试后仍失败的股票数量：{len(failed_codes)}")
            sleep_time.sleep(5)  # 每次重试间隔5秒
            
    def clean_delisted_stocks(self, confirm=True):
        """清理数据库中已退市的股票数据"""
    # 获取当前有效的股票列表
        current_stocks = self.get_stock_list()
        if current_stocks is None:
            print("无法获取当前股票列表，清理操作取消")
            return 0
    
        current_codes = current_stocks['code'].tolist()
    
        # 获取数据库中的所有股票代码
        db_codes, _ = self.db.check_stocks_in_db()
    
        # 找出不在当前股票列表中的代码（退市股票）
        delisted_codes = db_codes - set(current_codes)
    
        if not delisted_codes:
            print("没有发现退市股票")
            return 0
    
        print(f"发现 {len(delisted_codes)} 只退市股票: {', '.join(sorted(delisted_codes)[:10])}{'...' if len(delisted_codes) > 10 else ''}")
        
        if confirm:
            response = input("确定要删除这些退市股票的数据吗？(y/N): ")
            if response.lower() != 'y':
                print("取消删除操作")
                return 0
        
        # 删除不在当前股票列表中的数据
        deleted_count = self.db.delete_delisted_stocks(current_codes)
        return deleted_count
    
    def close(self):
        """关闭资源"""
        self.db.close()