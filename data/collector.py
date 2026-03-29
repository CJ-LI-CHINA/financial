import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
import time as sleep_time
import csv
from config.settings import DATA_CONFIG
from database.postgres import PostgresDB
from data.indicators import calculate_all_indicators, calculate_macd, calculate_kdj
from utils.helpers import is_trading_day, determine_end_date
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    
    def update_all_stocks_data(self, retry_failed=False, max_workers=8, batch_size=50):
        """高并发批量更新所有股票的数据（带节流机制）。
        - 使用线程池按批次并发抓取，每个批次抓取完后睡眠 `DATA_CONFIG["retry_interval"]` 秒以防被封。
        - `max_workers`：每个批次的并发请求数；`batch_size`：每批包含的股票数量。
        """
        latest_dates = self.db.get_latest_dates()

        stock_list_df = self.get_stock_list()
        if stock_list_df is None:
            return [], []

        codes = stock_list_df['code'].tolist()

        if retry_failed:
            try:
                failed_df = pd.read_csv(self.failed_codes_file, dtype={'code': str})
                failed_codes_list = failed_df['code'].tolist()
                codes = [code for code in failed_codes_list if not code.startswith(('8', '43', '92'))]
                print(f"重试失败股票列表，从 {self.failed_codes_file} 加载 {len(codes)} 只股票（已排除北交所）。")
            except FileNotFoundError:
                print(f"未找到 {self.failed_codes_file}，无法重试失败股票。")
                return [], []

        end_date = determine_end_date()
        print(f"更新结束日期: {end_date}")

        success_codes = []
        failed_codes = []

        # 预准备待抓取的任务列表：只有需要更新的股票
        tasks = []  # list of (code, start_date)
        for code in codes:
            if code in latest_dates:
                start_date = latest_dates[code] + timedelta(days=1)
                if start_date > end_date:
                    success_codes.append(code)
                    continue
            else:
                start_date = DATA_CONFIG["default_start_date"]

            tasks.append((code, start_date))

        # helper for fetching one stock
        def fetch_task(code, start_date):
            try:
                data, error = self.process_stock_data(code, start_date, end_date.strftime('%Y%m%d'))
                return code, data, error
            except Exception as e:
                return code, None, str(e)

        # split into batches to control total request rate
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            batch_rows = []
            attempted_codes = []

            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {ex.submit(fetch_task, code, sd): code for code, sd in batch}
                for fut in as_completed(futures):
                    code = futures[fut]
                    try:
                        c, data, err = fut.result()
                        if data is None:
                            failed_codes.append((c, err))
                        else:
                            # 收集行和记录尝试过的代码，实际插入后再认定成功/失败
                            batch_rows.extend(data)
                            attempted_codes.append(c)
                    except Exception as e:
                        failed_codes.append((code, str(e)))

            # 批量插入本批次数据
            if batch_rows:
                try:
                    inserted = self.db.insert_stock_data(batch_rows)
                    if inserted and inserted > 0:
                        success_codes.extend(attempted_codes)
                    else:
                        for c in attempted_codes:
                            failed_codes.append((c, '插入数据失败或已存在'))
                except Exception as e:
                    for c in attempted_codes:
                        failed_codes.append((c, f'插入异常: {e}'))

            # 节流：等待一定时间再进行下一批，防止被风控
            sleep_time.sleep(DATA_CONFIG.get('retry_interval', 1))

        # 保存失败股票到CSV
        if failed_codes:
            with open(self.failed_codes_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['code', 'error'])
                writer.writerows(failed_codes)

        print(f"\n数据更新完成：")
        print(f"成功股票数量：{len(success_codes)}")
        print(f"失败股票数量：{len(failed_codes)}，详情已保存到 {self.failed_codes_file}")

        return success_codes, failed_codes

    def update_today_all_stocks_data(self, max_workers=8, batch_size=500):
        """并发/批量拉取当日所有股票日K并批量写入数据库。
        优先使用 `ak.stock_zh_a_spot_em()` 一次性获取快照；若该接口不可用或列不足，回退为并发按代码逐只调用 `ak.stock_zh_a_daily`。
        - `max_workers`: 并发工作线程数（回退模式）
        - `batch_size`: 每次批量插入的行数
        返回 (success_codes, failed_codes)
        """
        end_date = determine_end_date()
        today = datetime.now().date()
        if end_date != today:
            print("当前时间可能未到收盘或不是交易日，建议在交易日17:00之后运行此方法。")

        stock_list_df = self.get_stock_list()
        if stock_list_df is None:
            return [], []

        codes_master = set(stock_list_df['code'].tolist())

        success_codes = []
        failed_codes = []
        data_rows_all = []

        # 首先尝试一次性拉取快照
        try:
            all_spot = ak.stock_zh_a_spot_em()
        except Exception as e:
            all_spot = None
            print(f"获取当日快照失败: {e}，将回退并发按代码拉取。")

        if all_spot is not None and not all_spot.empty:
            # 尝试识别列名
            col_code = None
            col_open = None
            col_high = None
            col_low = None
            col_price = None
            col_volume = None

            for c in all_spot.columns:
                lc = str(c).lower()
                if '代码' in lc or lc == 'code' or lc.startswith('code'):
                    col_code = c
                if '今开' in lc or lc == 'open':
                    col_open = c
                if '最高' in lc or lc == 'high':
                    col_high = c
                if '最低' in lc or lc == 'low':
                    col_low = c
                if '最新' in lc or 'price' in lc or 'last' in lc:
                    col_price = c
                if '成交量' in lc or lc == 'volume':
                    col_volume = c

            # 如果没有基本列，则回退到并发逐只拉取
            if not col_code or not col_price:
                print("快照返回的列不完整，回退并发按代码拉取。")
                all_spot = None
            else:
                for _, row in all_spot.iterrows():
                    try:
                        code = str(row[col_code])
                        if code not in codes_master:
                            continue
                        if code.startswith(('8', '43', '92')):
                            continue

                        open_v = row[col_open] if col_open and pd.notna(row[col_open]) else None
                        high_v = row[col_high] if col_high and pd.notna(row[col_high]) else None
                        low_v = row[col_low] if col_low and pd.notna(row[col_low]) else None
                        close_v = row[col_price] if col_price and pd.notna(row[col_price]) else None

                        vol_v = None
                        if col_volume and pd.notna(row[col_volume]):
                            try:
                                vol_v = int(float(row[col_volume]))
                            except Exception:
                                vol_v = None

                        date_db = end_date.strftime('%Y-%m-%d')
                        data_rows_all.append((date_db, code, open_v, high_v, low_v, close_v, vol_v,
                                              None, None, None, None, None, None, None, None, None))
                        success_codes.append(code)
                    except Exception as e:
                        failed_codes.append((row.get(col_code, None), str(e)))

        # 如果无法使用快照，使用并发按代码逐只拉取当日日K
        if all_spot is None or all_spot.empty:
            codes = sorted(list(codes_master))

            def fetch_single(code):
                try:
                    symbol = f"sh{code}" if code.startswith('6') else f"sz{code}"
                    df = ak.stock_zh_a_daily(symbol=symbol, start_date=end_date.strftime('%Y%m%d'),
                                               end_date=end_date.strftime('%Y%m%d'), adjust='qfq')
                    if df is None or df.empty:
                        return code, None, '无当日数据'

                    # 依赖于 API 返回的列名
                    row = df.iloc[0]
                    date_db = row['date'] if 'date' in row else end_date.strftime('%Y-%m-%d')
                    open_v = row.get('open', None)
                    high_v = row.get('high', None)
                    low_v = row.get('low', None)
                    close_v = row.get('close', None)
                    vol_v = None
                    try:
                        vol_v = int(row.get('volume', 0)) if not pd.isna(row.get('volume', None)) else None
                    except Exception:
                        vol_v = None

                    data_row = (date_db, code, open_v, high_v, low_v, close_v, vol_v,
                                None, None, None, None, None, None, None, None, None)
                    return code, data_row, None
                except Exception as e:
                    return code, None, str(e)

            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {ex.submit(fetch_single, code): code for code in codes_master}
                for fut in as_completed(futures):
                    code = futures[fut]
                    try:
                        c, data_row, err = fut.result()
                        if data_row is not None:
                            data_rows_all.append(data_row)
                            success_codes.append(code)
                        else:
                            failed_codes.append((code, err))
                    except Exception as e:
                        failed_codes.append((code, str(e)))

        # 批量按 batch_size 插入
        inserted_total = 0
        for i in range(0, len(data_rows_all), batch_size):
            batch = data_rows_all[i:i+batch_size]
            try:
                inserted = self.db.insert_stock_data(batch)
                inserted_total += inserted
            except Exception as e:
                print(f"批量插入失败: {e}")

        print(f"完成当日数据拉取，准备插入行数: {len(data_rows_all)}，DB 接受数（估计）: {inserted_total}")
        return success_codes, failed_codes

    def update_Critical_Factors(self, codes=None, max_workers=4):
        """重新计算并更新数据库中已存在日K的 MACD 与 KDJ 指标。
        如果 `codes` 为 None，则对数据库中所有有数据的股票进行更新。
        使用多线程加速处理，`max_workers` 控制并发线程数。
        返回更新的行数（估计）。"""
        # 确定要处理的股票列表
        if codes is None:
            # 直接从数据库读取已有股票的最新日期字典，键为代码
            latest_dates = self.db.get_latest_dates()
            codes_to_process = sorted(list(latest_dates.keys()))
        else:
            codes_to_process = codes

        if not codes_to_process:
            print("没有需要更新指标的股票（数据库中无数据）。")
            return 0

        end_date = determine_end_date()
        updated_total = 0

        def process_single_code(code):
            """处理单个股票代码的指标更新"""
            db_local = PostgresDB()  # 每个线程使用独立的数据库连接
            try:
                df = db_local.get_stock_data(code, '1900-01-01', end_date.strftime('%Y-%m-%d'))
                if df is None or df.empty:
                    return 0

                df = df.sort_values('date').reset_index(drop=True)

                # 确保数值列为 numeric
                df['close'] = pd.to_numeric(df['close'], errors='coerce')
                df['low'] = pd.to_numeric(df['low'], errors='coerce')
                df['high'] = pd.to_numeric(df['high'], errors='coerce')

                df_calc = df.copy()
                df_calc = calculate_macd(df_calc)
                df_calc = calculate_kdj(df_calc)

                update_rows = []
                for _, row in df_calc.iterrows():
                    macd = None if pd.isna(row.get('macd')) else float(row.get('macd'))
                    macd_signal = None if pd.isna(row.get('macd_signal')) else float(row.get('macd_signal'))
                    macd_hist = None if pd.isna(row.get('macd_hist')) else float(row.get('macd_hist'))
                    kdj_k = None if pd.isna(row.get('kdj_k')) else float(row.get('kdj_k'))
                    kdj_d = None if pd.isna(row.get('kdj_d')) else float(row.get('kdj_d'))
                    kdj_j = None if pd.isna(row.get('kdj_j')) else float(row.get('kdj_j'))

                    date_val = row['date']
                    if hasattr(date_val, 'strftime'):
                        date_str = date_val.strftime('%Y-%m-%d')
                    else:
                        date_str = str(date_val)

                    update_rows.append((date_str, code, macd, macd_signal, macd_hist, kdj_k, kdj_d, kdj_j))

                # 去重：如果有重复的 (date, code) 对，只保留最后一个（按 DataFrame 顺序）
                unique_rows = {}
                for row_tuple in update_rows:
                    key = (row_tuple[0], row_tuple[1])  # (date, code)
                    unique_rows[key] = row_tuple
                update_rows = list(unique_rows.values())

                updated = db_local.update_indicators(update_rows)
                print(f"{code}: 原始准备更新 {len(df_calc)} 行，去重后 {len(update_rows)} 行，DB 返回 {updated}")
                return updated if updated else 0
            except Exception as e:
                print(f"{code} 更新指标失败: {e}")
                return 0
            finally:
                db_local.close()

        # 使用线程池并发处理
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_single_code, code) for code in codes_to_process]
            for future in as_completed(futures):
                updated_total += future.result()

        print(f"指标更新完成，总计更新行（估计）: {updated_total}")
        return updated_total
    
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