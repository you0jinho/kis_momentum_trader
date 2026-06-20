"""
로깅 설정
- logs/trader.log 파일 + 콘솔에 동시 출력
- 파일은 용량 제한 + 백업 회전 (RotatingFileHandler)
"""
import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("kis_trader")
logger.setLevel(logging.INFO)

_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)

_file_handler = RotatingFileHandler(
    os.path.join(LOG_DIR, "trader.log"), maxBytes=2_000_000, backupCount=3, encoding="utf-8"
)
_file_handler.setFormatter(_formatter)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)

# 모듈이 여러 번 import 되어도 핸들러가 중복 등록되지 않도록 방지
if not logger.handlers:
    logger.addHandler(_file_handler)
    logger.addHandler(_console_handler)
