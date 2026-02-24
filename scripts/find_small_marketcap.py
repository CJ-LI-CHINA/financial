"""Find stocks present in the database with market cap < 100亿.

This script combines the DB->distinct codes from `PostgresDB.check_stocks_in_db`
and the real-time snapshot from `akshare.stock_zh_a_spot_em()` to determine
which codes have market cap below the threshold.

Usage (PowerShell):

```
python .\scripts\find_small_marketcap.py
```

Notes:
- Akshare return column names/units vary by version. This script attempts to
  detect common column names and normalize values to CNY (float).
- It prints a small sample and a CSV `small_marketcap.csv` in the repo root.
"""

import sys
import os

# 获取当前文件的目录
current_dir = os.path.dirname(os.path.abspath(__file__))
# 获取项目根目录（假设项目根目录是folderC的父目录）
project_root = os.path.dirname(current_dir)

# 添加项目根目录到Python路径
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import akshare as ak
import pandas as pd
from database.postgres import PostgresDB


THRESHOLD_CNY = 100 * 10**8  # 100亿 in CNY (100 * 100,000,000 = 10,000,000,000)


def find_market_cap_column(df: pd.DataFrame):
    # Common column name candidates from different akshare versions/locales
    candidates = [
        '流通市值', '总市值', 'circulation_mv', 'circ_mv', 'total_mv', 'market_cap',
        'marketValue', '流通市值(亿元)', '总市值(亿元)', '流通市值(万)', '总市值(万)'
    ]
    for c in candidates:
        if c in df.columns:
            return c
    # fallback: look for columns containing '市值' or 'market' in name
    for c in df.columns:
        if '市值' in c or 'market' in c.lower():
            return c
    return None


def normalize_value(val):
    """Normalize a single market-cap cell to a float in CNY.

    Handles numeric types, strings with unit suffixes like '亿' or '万',
    and returns None on failure.
    """
    if pd.isna(val):
        return None
    # numeric already
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    # remove commas
    s = s.replace(',', '')
    try:
        # common suffix: 亿 (100 million CNY), 万 (10k CNY)
        if s.endswith('亿'):
            return float(s[:-1]) * 1e8
        if s.endswith('万'):
            return float(s[:-1]) * 1e4
        # sometimes akshare returns numbers in 亿元 as float strings
        # try plain float
        return float(s)
    except Exception:
        return None


def main():
    db = PostgresDB()
    try:
        db_codes, _ = db.check_stocks_in_db()
        if not db_codes:
            print('No codes found in database.')
            return

        print(f'Found {len(db_codes)} distinct codes in DB. Fetching market snapshot from akshare...')
        spot = ak.stock_zh_a_spot_em()

        if spot is None or spot.empty:
            print('akshare returned empty snapshot.')
            return

        # normalize code column (some versions use '代码' or 'code')
        if '代码' in spot.columns:
            spot = spot.rename(columns={'代码': 'code'})
        if '代码 ' in spot.columns:
            spot = spot.rename(columns={'代码 ': 'code'})
        if 'code' not in spot.columns:
            # try lowercase
            for c in spot.columns:
                if c.lower() == 'code' or c.lower() == '代码':
                    spot = spot.rename(columns={c: 'code'})
                    break

        spot['code'] = spot['code'].astype(str).str.zfill(6)

        mch_col = find_market_cap_column(spot)
        if mch_col is None:
            print('Could not find a market-cap column in akshare snapshot. Available columns:')
            print(list(spot.columns))
            return

        print(f'Using market-cap column: {mch_col}')

        # Normalize market cap values
        spot['_mkt_cny'] = spot[mch_col].apply(normalize_value)

        # If values appear to be in '亿元' (e.g., typical float ~ hundred), attempt heuristic
        # If median > 1e6, we assume values are already in CNY; if median < 1e6 but > 1e2,
        # it may be in 亿元, so multiply by 1e8.
        med = spot['_mkt_cny'].dropna().median()
        if med is None:
            print('No numeric market cap values parsed. Aborting.')
            return

        if med < 1e6 and med > 1:  # likely in '亿元' (e.g., 50 means 50 亿元)
            print('Heuristic: market-cap values appear to be in 亿元; scaling by 1e8 to CNY.')
            spot['_mkt_cny'] = spot['_mkt_cny'] * 1e8

        # keep only codes that exist in DB
        spot_in_db = spot[spot['code'].isin(db_codes)].copy()

        # filter by threshold
        small = spot_in_db[spot_in_db['_mkt_cny'] < THRESHOLD_CNY]

        if small.empty:
            print('No stocks in DB with market cap < 100亿 found (based on current snapshot).')
        else:
            out = small[['code'] + [c for c in ['名称', 'name', '名称 '] if c in small.columns] + ['_mkt_cny']]
            # pretty print (market cap in 亿元)
            out = out.rename(columns={'名称': 'name', '名称 ': 'name'})
            out['mkt_亿元'] = out['_mkt_cny'] / 1e8
            print(f"Found {len(out)} stocks in DB with market cap < 100亿:")
            print(out[['code', 'name', 'mkt_亿元']].to_string(index=False))
            out[['code', 'name', 'mkt_亿元']].to_csv('small_marketcap.csv', index=False, encoding='utf-8-sig')
            print("Wrote results to 'small_marketcap.csv'")

    finally:
        db.close()


if __name__ == '__main__':
    main()
