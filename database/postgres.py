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
        import akshare as ak
        stock_list_df = ak.stock_info_a_code_name()
        # from data.collector_tdx import DataCollector
        # collector = DataCollector()
        # stock_list_df = collector.get_stock_list()
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
    def update_indicators(self, update_rows):
        """批量更新指标：update_rows 为 (date, code, macd, macd_signal, macd_hist, kdj_k, kdj_d, kdj_j) 列表"""
        if not update_rows:
            return 0

        # 诊断：检查有多少行能匹配到数据库中的数据
        codes_to_check = set((row[0], row[1]) for row in update_rows)  # (date, code) 对
        if len(codes_to_check) > 0:
            try:
                sample_date, sample_code = list(codes_to_check)[0]
                check_query = f"SELECT COUNT(*) FROM stock_data WHERE date = '{sample_date}'::date AND code = %s LIMIT 1;"
                cur = self.conn.cursor()
                cur.execute(check_query, (sample_code,))
                sample_count = cur.fetchone()[0]
                cur.close()
                if sample_count == 0:
                    print(f"警告：样本日期 {sample_date}、代码 {sample_code} 在数据库中无匹配记录，可能 WHERE 条件全部不匹配")
            except Exception as e:
                print(f"诊断检查失败: {e}")

        update_query = """
        UPDATE stock_data AS s
        SET macd = v.macd,
            macd_signal = v.macd_signal,
            macd_hist = v.macd_hist,
            kdj_k = v.kdj_k,
            kdj_d = v.kdj_d,
            kdj_j = v.kdj_j
        FROM (VALUES %s) AS v(date, code, macd, macd_signal, macd_hist, kdj_k, kdj_d, kdj_j)
        WHERE s.date = v.date::date AND s.code = v.code;
        """

        try:
            cur = self.conn.cursor()
            execute_values(cur, update_query, update_rows)
            updated = cur.rowcount
            self.conn.commit()
            cur.close()
            return updated
        except Exception as e:
            print(f"批量更新指标失败: {e}")
            self.conn.rollback()
            return 0
    
    def clear_indicators(self):
        """清空所有 KDJ 和 MACD 指标数据，将相关列设为 NULL"""
        clear_query = """
        UPDATE stock_data 
        SET macd = NULL,
            macd_signal = NULL,
            macd_hist = NULL,
            kdj_k = NULL,
            kdj_d = NULL,
            kdj_j = NULL;
        """
        
        try:
            cur = self.conn.cursor()
            cur.execute(clear_query)
            cleared_count = cur.rowcount
            self.conn.commit()
            cur.close()
            print(f"已清空 {cleared_count} 条记录的指标数据")
            return cleared_count
        except Exception as e:
            print(f"清空指标数据失败: {e}")
            self.conn.rollback()
            return 0
    def close(self):
        """关闭数据库连接"""
        if self.conn is not None:
            self.conn.close()
            print("数据库连接已关闭")
if __name__ == "__main__":
    k =1