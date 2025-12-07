# data/corporate_actions.py
import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from database.postgres import PostgresDB

class CorporateActionsHandler:
    def __init__(self, db_connection):
        self.db = db_connection
    
    def get_corporate_actions(self, code, start_date, end_date):
        """获取股票的公司行为（分红送配）"""
        try:
            # 使用AKShare获取分红送配信息
            df = ak.stock_history_dividend(symbol=code)
            
            if df is None or df.empty:
                return None
            
            # 过滤日期范围
            df['公告日期'] = pd.to_datetime(df['公告日期'])
            df = df[(df['公告日期'] >= pd.to_datetime(start_date)) & 
                    (df['公告日期'] <= pd.to_datetime(end_date))]
            
            return df
        except Exception as e:
            print(f"获取股票 {code} 公司行为失败: {e}")
            return None
    
    def check_recent_corporate_actions(self, days=30):
        """检查最近一段时间内的公司行为"""
        # 获取所有股票代码
        stock_list_df = ak.stock_info_a_code_name()
        stock_list_df = stock_list_df[~stock_list_df['code'].str.startswith(('8', '43','92'))]
        codes = stock_list_df['code'].tolist()
        
        # 计算日期范围
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
        
        # 存储有公司行为的股票
        stocks_with_actions = []
        
        for code in codes:
            actions = self.get_corporate_actions(code, start_date, end_date)
            if actions is not None and not actions.empty:
                stocks_with_actions.append(code)
                print(f"股票 {code} 在最近 {days} 天内有公司行为")
        
        return stocks_with_actions
    
    def update_stock_data_with_new_adjustment(self, code):
        """重新获取股票的完整前复权数据并更新数据库"""
        try:
            # 获取股票的上市日期
            stock_list_df = ak.stock_info_a_code_name()
            stock_info = stock_list_df[stock_list_df['code'] == code]
            
            if stock_info.empty:
                print(f"未找到股票 {code} 的基本信息")
                return False
            
            list_date = stock_info.iloc[0]['list_date']
            
            # 获取当前日期
            end_date = datetime.now().strftime('%Y%m%d')
            
            # 重新获取完整的股票数据（前复权）
            symbol = f"sh{code}" if code.startswith('6') else f"sz{code}"
            df = ak.stock_zh_a_daily(symbol=symbol, start_date=list_date, 
                                   end_date=end_date, adjust="qfq")
            
            if df is None or df.empty:
                print(f"股票 {code} 无前复权数据")
                return False
            
            # 计算技术指标
            from data.indicators import calculate_all_indicators
            df = calculate_all_indicators(df)
            
            # 准备插入数据
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
            
            # 删除数据库中该股票的所有数据
            delete_query = "DELETE FROM stock_data WHERE code = %s;"
            cur = self.db.conn.cursor()
            cur.execute(delete_query, (code,))
            self.db.conn.commit()
            
            # 插入新的数据
            inserted_count = self.db.insert_stock_data(data)
            
            print(f"股票 {code} 数据已重新计算并更新，插入了 {inserted_count} 条记录")
            return True
            
        except Exception as e:
            print(f"更新股票 {code} 数据失败: {e}")
            return False
    
    def process_corporate_actions(self, days=30):
        """处理最近的公司行为，重新计算受影响股票的数据"""
        # 检查最近的公司行为
        stocks_with_actions = self.check_recent_corporate_actions(days)
        
        if not stocks_with_actions:
            print(f"最近 {days} 天内没有发现公司行为")
            return []
        
        print(f"发现 {len(stocks_with_actions)} 只股票在最近 {days} 天内有公司行为，开始更新数据...")
        
        # 更新受影响股票的数据
        updated_stocks = []
        for code in stocks_with_actions:
            success = self.update_stock_data_with_new_adjustment(code)
            if success:
                updated_stocks.append(code)
        
        print(f"已完成 {len(updated_stocks)} 只股票的数据更新")
        return updated_stocks