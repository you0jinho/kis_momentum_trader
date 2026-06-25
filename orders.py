"""
주문 모듈
- 돌파/타임컷 전략은 즉시 체결이 핵심이라 시장가 주문만 사용
  (지정가는 안 걸릴 수 있어 전략 의도에 맞지 않음)
"""
from api_client import ApiClient
from config import TrId, CANO, ACNT_PRDT_CD, ORD_DVSN_MARKET, get_symbol_name
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
        name = get_symbol_name(symbol)
        logger.info(f"[매수주문] {name}({symbol}) {qty}주 시장가 매수 요청")
        res = self._order(symbol, qty, TrId.BUY_ORDER)
        self._log_order_result(name, symbol, res)
        return res

    def sell_market(self, symbol: str, qty: int) -> dict:
        name = get_symbol_name(symbol)
        logger.info(f"[매도주문] {name}({symbol}) {qty}주 시장가 매도 요청")
        res = self._order(symbol, qty, TrId.SELL_ORDER)
        self._log_order_result(name, symbol, res)
        return res

    @staticmethod
    def _log_order_result(name: str, symbol: str, res: dict) -> None:
        """
        주문 응답에서 실제 주문번호(ODNO)를 뽑아서 로그에 남긴다.
        이 번호가 실제로 찍히면, 한투 앱/HTS의 모의투자 주문내역에서 같은
        번호를 검색해 "진짜 시스템에 접수됐는지"를 직접 대조 확인할 수 있다.
        ODNO가 비어있다면 그건 접수 자체가 안 됐다는 뜻이므로 바로 알 수 있다.
        """
        output = res.get("output", {})
        odno = output.get("ODNO", "")
        ord_tmd = output.get("ORD_TMD", "")
        if odno:
            logger.info(
                f"[주문 응답] {name}({symbol}) rt_cd={res.get('rt_cd')} "
                f"주문번호(ODNO)={odno} 주문시각={ord_tmd} msg1={res.get('msg1')}"
            )
        else:
            logger.error(
                f"[주문 응답에 주문번호 없음] {name}({symbol}) rt_cd={res.get('rt_cd')} "
                f"전체응답={res}"
            )
