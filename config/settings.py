# 数据库连接参数
DB_PARAMS = {
    "dbname": "my_stock",
    "user": "postgres",
    "password": "123456",
    "host": "localhost",
    "port": "5432"
}

# 数据收集配置
DATA_CONFIG = {
    "default_start_date": "20100101",
    "retry_interval": 0.5,  # 请求间隔秒数
    "max_retries": 3,  # 最大重试次数
    "failed_codes_file": "failed_stocks.csv"
}

# 日志配置
LOG_CONFIG = {
    "level": "INFO",
    "format": "%(asctime)s - %(levelname)s - %(message)s",
    "filename": "stock_quant.log"
}
