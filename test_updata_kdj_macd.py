"""
test_updata_kdj_macd.py

Small CLI tool to run only the KDJ/MACD update routine (`update_Critical_Factors`).

Usage examples:
  # dry run, list first 50 DB codes that would be updated
  python test_updata_kdj_macd.py --dry-run --limit 50

  # update specific codes
  python test_updata_kdj_macd.py --codes 600000,000001

  # update first 20 codes from DB
  python test_updata_kdj_macd.py --limit 20

  # use live stock list instead of DB codes
  python test_updata_kdj_macd.py --from-list --limit 50

  # use 8 threads for faster processing
  python test_updata_kdj_macd.py --max-workers 8

Notes:
- Make sure `config/settings.py` DB_PARAMS are set and the DB is reachable.
"""

import argparse
from data.collector import DataCollector


def main():
    parser = argparse.ArgumentParser(description='Run update_Critical_Factors to recalc KDJ/MACD')
    parser.add_argument('--codes', help='Comma-separated stock codes to update (e.g. 600000,000001)')
    parser.add_argument('--limit', type=int, default=0, help='Limit to first N codes from DB or stock list')
    parser.add_argument('--from-list', action='store_true', help='Select codes from stock list (get_stock_list) instead of DB')
    parser.add_argument('--dry-run', action='store_true', help='Do not perform updates, just show selection')
    parser.add_argument('--max-workers', type=int, default=4, help='Number of concurrent threads for processing (default: 4)')
    args = parser.parse_args()

    collector = None
    try:
        collector = DataCollector()

        # Prepare codes
        codes = None
        if args.codes:
            codes = [c.strip() for c in args.codes.split(',') if c.strip()]
        else:
            if args.from_list:
                sl = collector.get_stock_list()
                if sl is None:
                    print('无法获取股票列表')
                    return
                codes = sl['code'].tolist()
            else:
                db_codes, _ = collector.db.check_stocks_in_db()
                codes = sorted(list(db_codes))

        if args.limit and codes is not None:
            codes = codes[:args.limit]

        print(f"将更新的股票数量: {len(codes) if codes is not None else 0}")
        if codes:
            print('示例代码:', ','.join(codes[:10]) + ('...' if len(codes) > 10 else ''))

        if args.dry_run:
            print('dry-run: 未执行任何更新')
            return

        updated = collector.update_Critical_Factors(codes if codes else None, max_workers=args.max_workers)
        print('更新完成，估计更新行数:', updated)

    except Exception as e:
        print('运行时发生错误:', e)
    finally:
        if collector:
            collector.close()


if __name__ == '__main__':
    main()
