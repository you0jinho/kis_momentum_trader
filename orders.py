"""
주문 모듈
- 돌파/타임컷 전략은 즉시 체결이 핵심이라 시장가 주문만 사용
  (지정가는 안 걸릴 수 있어 전략 의도에 맞지 않음)
"""
from api_client import ApiClient
from config import TrId, CANO, ACNT_PRDT_CD, ORD_DVSN_MARKET
from logger import logger


class Orders:
    def __init__(self, client: ApiClient) -> None:
        self.client = client

    def _order(self, symbol: str, qty: int, tr_id: str) -> dict:
        """
        ⚠️ 확인 필요: ORD_UNPR 등 필드명은 KIS 공식 문서에서 재확인할 것.
        시장가 주문은 ORD_UNPR을 "0"으로 보낸다.
        """
        body = {
            "CANO": CANO,
            "ACNT_PRDT_CD": ACNT_PRDT_CD,
            "PDNO": symbol,
            "ORD_DVSN": ORD_DVSN_MARKET,
            "ORD_QTY": str(qty),
            "ORD_UNPR": "0",
        }
        return self.client.post(
            "/uapi/domestic-stock/v1/trading/order-cash",
            tr_id,
            body,
            use_hashkey=True,
        )

    def buy_market(self, symbol: str, qty: int) -> dict:
        logger.info(f"[매수주문] {symbol} {qty}주 시장가 매수 요청")
        res = self._order(symbol, qty, TrId.BUY_ORDER)
        logger.info(f"[매수주문 응답] {symbol}: {res.get('msg1', res)}")
        return res

    def sell_market(self, symbol: str, qty: int) -> dict:
        logger.info(f"[매도주문] {symbol} {qty}주 시장가 매도 요청")
        res = self._order(symbol, qty, TrId.SELL_ORDER)
        logger.info(f"[매도주문 응답] {symbol}: {res.get('msg1', res)}")
        return res
