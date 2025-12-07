import numpy as np
import pandas as pd

def calculate_moving_averages(df):
    """计算MA5、MA10、MA20"""
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma10'] = df['close'].rolling(window=10).mean()
    df['ma20'] = df['close'].rolling(window=20).mean()
    return df

def calculate_macd(df, short_period=12, long_period=26, signal_period=9):
    """计算MACD指标"""
    ema_short = df['close'].ewm(span=short_period, adjust=False).mean()
    ema_long = df['close'].ewm(span=long_period, adjust=False).mean()
    df['macd'] = ema_short - ema_long  #DIF 同花顺   快线
    df['macd_signal'] = df['macd'].ewm(span=signal_period, adjust=False).mean()  # DEA 同花顺  慢线
    df['macd_hist'] = df['macd'] - df['macd_signal']   #MACD 
    return df

def calculate_kdj(df, n_rsv=9, n_k=3, n_d=3):
    """计算KDJ指标"""
    low_min = df['low'].rolling(window=n_rsv).min()
    high_max = df['high'].rolling(window=n_rsv).max()
    rsv = ((df['close'] - low_min) / (high_max - low_min)) * 100
    df['kdj_k'] = rsv.rolling(window=n_k).mean()
    df['kdj_d'] = df['kdj_k'].rolling(window=n_d).mean()
    df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']
    return df

def calculate_all_indicators(df):
    """计算所有技术指标"""
    df = calculate_moving_averages(df)
    df = calculate_macd(df)
    df = calculate_kdj(df)
    return df