from datetime import datetime, time, timedelta

def is_trading_day(date):
    """判断是否为交易日"""
    # 这里简化处理，实际应用中可能需要更复杂的逻辑
    # 周末不是交易日
    if date.weekday() >= 5:  # 5=Saturday, 6=Sunday
        return False
    
    # 这里可以添加节假日判断逻辑
    # 暂时假设所有工作日都是交易日
    
    return True

def determine_end_date():
    """确定更新结束日期"""
    now = datetime.now()
    current_time = now.time()
    
    # 如果当前时间在15:00之后且是交易日，则更新到当天
    if current_time >= time(15, 0) and is_trading_day(now.date()):
        end_date = now.date()
    else:
        # 否则更新到上一个交易日
        end_date = now.date() - timedelta(days=1)
        while not is_trading_day(end_date):
            end_date -= timedelta(days=1)
    
    return end_date