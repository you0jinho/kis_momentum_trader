"""
실행 진입점

사전 준비:
    export GH_ACCOUNT="12345678-01"
    export GH_APPKEY="..."
    export GH_APPSECRET="..."

실행:
    python main.py
"""
from config import validate_credentials
from trader import BreakoutScalpTrader
from logger import logger


def main() -> None:
    validate_credentials()
    trader = BreakoutScalpTrader()
    try:
        trader.run()
    except KeyboardInterrupt:
        logger.info("[종료] 사용자가 프로그램을 중단했습니다.")


if __name__ == "__main__":
    main()
