import numpy as np
import pandas as pd
from database.postgres import PostgresDB
from datetime import datetime

class StockAnalyzer:
    def __init__(self):
        self.db = PostgresDB()
    
    def analyze_kdj_overbought_oversold(self, code, start_date='20240101', end_date=datetime.now().strftime('%Y%m%d')):
        """基于KDJ查找超买/超卖信号"""
        df = self.db.get_stock_data(code, start_date, end_date)
        
        if df is None or df.empty:
            print(f"股票 {code} 无数据。")
            return
        
        # 简单分析：K > 80 超买，K < 20 超卖；金叉（K上穿D），死叉（K下穿D）
        df['signal'] = np.where(df['kdj_k'] > 80, '超买', np.where(df['kdj_k'] < 20, '超卖', '正常'))
        df['cross'] = np.where((df['kdj_k'].shift(1) < df['kdj_d'].shift(1)) & (df['kdj_k'] > df['kdj_d']), '金叉（买入信号）',
                               np.where((df['kdj_k'].shift(1) > df['kdj_d'].shift(1)) & (df['kdj_k'] < df['kdj_d']), '死叉（卖出信号）', '无'))
        
        print(f"股票 {code} 的KDJ分析（基于前复权数据）：")
        print(df[['date', 'close', 'kdj_k', 'kdj_d', 'kdj_j', 'signal', 'cross']].tail(10))
    
    def find_golden_cross(self, code, start_date, end_date):
        """寻找金叉机会"""
        df = self.db.get_stock_data(code, start_date, end_date)
        if df is None or df.empty:
            return None
        
        # 寻找5日线上穿10日线的金叉
        df['ma5_above_ma10'] = df['ma5'] > df['ma10']
        df['golden_cross'] = df['ma5_above_ma10'] & (~df['ma5_above_ma10'].shift(1))
        
        golden_cross_dates = df[df['golden_cross']].index
        return golden_cross_dates
    
    def find_kdj_low(self, code, start_date, end_date, k_threshold=20):
        """寻找KDJ低位机会"""
        df = self.db.get_stock_data(code, start_date, end_date)
        if df is None or df.empty:
            return None
        
        # 寻找K值低于阈值的机会
        kdj_low = df[df['kdj_k'] < k_threshold].index
        return kdj_low
    
    def close(self):
        """关闭资源"""
        self.db.close()