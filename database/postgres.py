import psycopg2
from psycopg2.extras import execute_values
from config.settings import DB_PARAMS


class PostgresDB:
    def __init__(self):
        self.conn = None
        self.connect()
    
    def connect(self):
        """连接到PostgreSQL数据库"""
        try:
            self.conn = psycopg2.connect(**DB_PARAMS)
            return True
        except Exception as e:
            print(f"数据库连接失败: {e}")
            return False
    
    def create_tables(self):
        """创建数据表"""
        create_table_query = """
        CREATE TABLE IF NOT EXISTS stock_data (
            date DATE,
            code VARCHAR(10),
            open NUMERIC,
            high NUMERIC,
            low NUMERIC,
            close NUMERIC,
            volume BIGINT,
            ma5 NUMERIC,
            ma10 NUMERIC,
            ma20 NUMERIC,
            macd NUMERIC,
            macd_signal NUMERIC,
            macd_hist NUMERIC,
            kdj_k NUMERIC,
            kdj_d NUMERIC,
            kdj_j NUMERIC,
            PRIMARY KEY (date, code)
        );
        """
        
        try:
            cur = self.conn.cursor()
            cur.execute(create_table_query)
            self.conn.commit()
            cur.close()
            print("数据表创建成功")
            return True
        except Exception as e:
            print(f"创建数据表失败: {e}")
            return False
    
    def get_latest_dates(self):
        """获取数据库中各股票的最新日期"""
        query = "SELECT code, MAX(date) FROM stock_data GROUP BY code;"
        
        try:
            cur = self.conn.cursor()
            cur.execute(query)
            results = cur.fetchall()
            cur.close()
            
            return {code: date for code, date in results}
        except Exception as e:
            print(f"获取最新日期失败: {e}")
            return {}
    
    def insert_stock_data(self, data):
        """插入股票数据"""
        insert_query = """
        INSERT INTO stock_data (date, code, open, high, low, close, volume, ma5, ma10, ma20, macd, macd_signal, macd_hist, kdj_k, kdj_d, kdj_j)
        VALUES %s
        ON CONFLICT (date, code) DO NOTHING;
        """
        
        try:
            cur = self.conn.cursor()
            execute_values(cur, insert_query, data)
            self.conn.commit()
            cur.close()
            return len(data)
        except Exception as e:
            print(f"插入数据失败: {e}")
            return 0
    
    def check_stocks_in_db(self):
        """检查数据库中哪些股票有数据"""
        # 获取所有A股股票列表
        # import akshare as ak
        # stock_list_df = ak.stock_info_a_code_name()
        from data.collector_tdx import DataCollector
        collector = DataCollector()
        stock_list_df = collector.get_stock_list()
        all_codes = set(stock_list_df['code'].tolist())
        
        # 查询数据库中存在的股票代码
        query = "SELECT DISTINCT code FROM stock_data;"
        
        try:
            cur = self.conn.cursor()
            cur.execute(query)
            db_codes = set(row[0] for row in cur.fetchall())
            cur.close()
            
            # 找出缺失的股票
            missing_codes = all_codes - db_codes
            
            print(f"\n数据库检查：")
            print(f"数据库中已有数据的股票数量：{len(db_codes)}")
            print(f"缺失数据的股票数量：{len(missing_codes)}")
            
            return db_codes, missing_codes
        except Exception as e:
            print(f"检查数据库失败: {e}")
            return set(), set()
    
    def get_stock_data(self, code, start_date, end_date):
        """获取指定股票的数据"""
        query = f"""
        SELECT date, open, high, low, close, volume, ma5, ma10, ma20, macd, macd_signal, macd_hist, kdj_k, kdj_d, kdj_j
        FROM stock_data
        WHERE code = '{code}' AND date BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY date;
        """
        
        try:
            import pandas as pd
            df = pd.read_sql(query, self.conn)
            return df
        except Exception as e:
            print(f"获取股票数据失败: {e}")
            return None
    
    def delete_delisted_stocks(self, codes_to_keep):
        """删除不在指定代码列表中的股票数据（即退市股票）"""
        # 将代码列表转换为适合SQL查询的格式
        codes_str = ",".join([f"'{code}'" for code in codes_to_keep])
    
        delete_query = f"""
        DELETE FROM stock_data 
        WHERE code NOT IN ({codes_str});
        """
    
        try:
            cur = self.conn.cursor()
            cur.execute(delete_query)
            deleted_count = cur.rowcount
            self.conn.commit()
            cur.close()
            print(f"已删除 {deleted_count} 条退市股票数据")
            return deleted_count
        except Exception as e:
            print(f"删除退市股票数据失败: {e}")
            self.conn.rollback()
            return 0
    def close(self):
        """关闭数据库连接"""
        if self.conn is not None:
            self.conn.close()
            print("数据库连接已关闭")
if __name__ == "__main__":
    k =1