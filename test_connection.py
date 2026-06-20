"""
연결 테스트용 스크립트
- main.py 는 09:00~09:30 사이에만 동작하지만, 이 스크립트는 그 시간과
  무관하게 지금 바로 인증/시세조회/잔고조회가 정상인지 확인할 수 있다.
- API 호출은 시세조회 1회 + 잔고조회 1회뿐이라 호출량 걱정 없음.

실행:
    python test_connection.py
"""
from config import validate_credentials
from api_client import ApiClient
from market_data import MarketData
from account import Account
from logger import logger


def main() -> None:
    validate_credentials()
    logger.info("[연결테스트] 시작")

    try:
        client = ApiClient()  # 토큰 발급 또는 당일 캐시 재사용
        logger.info("[연결테스트] 토큰 발급/로드 성공")

        market = MarketData(client)
        price = market.get_current_price("005930")
        logger.info(f"[연결테스트] 삼성전자(005930) 현재가 조회 성공: {price:,}원")

        account = Account(client)
        holdings, cash = account.get_balances()
        logger.info(f"[연결테스트] 잔고조회 성공 - 보유종목: {holdings} / 가용현금: {cash:,}원")

        logger.info("[연결테스트] 모든 항목 정상 - main.py 실행 준비가 된 상태입니다.")
    except Exception as e:
        logger.error(f"[연결테스트] 실패: {e}")
        logger.error("위 에러 메시지를 그대로 복사해서 확인해보세요.")


if __name__ == "__main__":
    main()
