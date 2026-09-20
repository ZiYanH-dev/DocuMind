"""日志模块。"""

import logging
import sys
from logging.handlers import RotatingFileHandler

from app.config.settings import settings

# 日志级别映射
LOG_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

LOG_FILE = settings.log_path


def setup_logger(name: str = "app") -> logging.Logger:
    """初始化应用日志器。"""

    logger: logging.Logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVELS.get(settings.app_env.upper(), logging.INFO))

    # 控制台处理器
    console_handler: logging.StreamHandler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_format: logging.Formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_format)

    # 文件处理器（按大小轮转）
    file_handler: RotatingFileHandler = RotatingFileHandler(
        str(LOG_FILE),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(console_format)

    # 避免重复添加处理器
    if not logger.handlers:
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    return logger


logger: logging.Logger = setup_logger()
