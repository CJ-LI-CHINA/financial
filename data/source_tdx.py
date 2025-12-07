from pytdx.hq import TdxHq_API
from pytdx.params import TDXParams
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time

class TDXDataSource:
    def __init__(self):
        self.api = TdxHq_API()
        self.connected = False
        self.best_ip = None
        self.connect()
    
    def connect(self):
        """连接到通达信服务器"""
        try:
            # 尝试连接多个服务器
            ips = [
                ('124.71.187.122', 7709),  # 默认服务器
                ('106.14.95.149', 7709),
                ('113.105.142.162', 7709),
                ('113.105.142.163', 7709),
            ]
            
            for ip, port in ips:
                try:
                    self.api.connect(ip, port)
                    if self.api.get_security_count(0) > 0:  # 测试连接
                        self.connected = True
                        self.best_ip = (ip, port)
                        print(f"成功连接到通达信服务器: {ip}:{port}")
                        return True
                except Exception as e:
                    print(f"连接 {ip}:{port} 失败: {e}")
                    continue
            
            print("无法连接到任何通达信服务器")
            return False
        except Exception as e:
            print(f"连接通达信服务器失败: {e}")
            return False
    
    def reconnect(self):
        """重新连接服务器"""
        self.api.disconnect()
        time.sleep(1)
        return self.connect()
    
    def get_stock_list(self):
        """获取所有A股股票列表，排除北交所股票"""
        try:
            if not self.connected and not self.reconnect():
                return None
            
            # 获取上海和深圳市场的股票列表
            sh_count = self.api.get_security_count(1)  # 上海市场
            sz_count = self.api.get_security_count(0)  # 深圳市场
            
            # 获取上海市场股票
            sh_stocks = []
            for i in range(0, sh_count, 1000):
                stocks = self.api.get_security_list(1, i)
                sh_stocks.extend(stocks)
            
            # 获取深圳市场股票
            sz_stocks = []
            for i in range(0, sz_count, 1000):
                stocks = self.api.get_security_list(0, i)
                sz_stocks.extend(stocks)
            
            # 转换为DataFrame
            columns = ['code', 'name', 'volunit', 'decimal_point', 'pre_close', 'open', 'high', 'low']
            sh_df = pd.DataFrame(sh_stocks, columns=columns)
            sz_df = pd.DataFrame(sz_stocks, columns=columns)
            
            # 合并两个市场
            all_stocks = pd.concat([sh_df, sz_df], ignore_index=True)
            
            # 排除北交所股票（代码以8或43开头的股票）
            all_stocks = all_stocks[~all_stocks['code'].str.startswith(('8', '43'))]
            
            print(f"获取股票列表数量: {len(all_stocks)}")
            return all_stocks
            
        except Exception as e:
            print(f"获取股票列表失败: {e}")
            if self.reconnect():
                return self.get_stock_list()
            return None
    
    def get_k_data(self, code, start_date, end_date):
        """获取股票K线数据"""
        try:
            if not self.connected and not self.reconnect():
                return None
            
            # 确定市场
            market = 1 if code.startswith('6') else 0  # 1=上海, 0=深圳
            
            # 转换日期格式
            start_dt = datetime.strptime(start_date, '%Y%m%d')
            end_dt = datetime.strptime(end_date, '%Y%m%d')
            
            # 计算需要获取的数据量
            days = (end_dt - start_dt).days + 1
            
            # 获取K线数据
            data = self.api.get_security_bars(
                category=TDXParams.KLINE_TYPE_DAILY,
                market=market,
                code=code,
                start=0,
                count=days
            )
            
            if not data:
                return None
            
            # 转换为DataFrame
            df = pd.DataFrame(data, columns=['date', 'open', 'close', 'high', 'low', 'volume', 'amount', 'unknown'])
            
            # 转换日期格式
            df['date'] = pd.to_datetime(df['date'], format='%Y-%m-%d')
            
            # 过滤日期范围
            df = df[(df['date'] >= start_dt) & (df['date'] <= end_dt)]
            
            if df.empty:
                return None
            
            # 重置索引
            df.reset_index(drop=True, inplace=True)
            
            return df
            
        except Exception as e:
            print(f"获取股票 {code} K线数据失败: {e}")
            if self.reconnect():
                return self.get_k_data(code, start_date, end_date)
            return None
    
    def close(self):
        """关闭连接"""
        try:
            self.api.disconnect()
            self.connected = False
            print("已断开通达信服务器连接")
        except:
            pass