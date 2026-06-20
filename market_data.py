"""국내주식 현재가 조회"""
from api_client import ApiClient
from config import TrId
from logger import logger


class MarketData:
    def __init__(self, client: ApiClient) -> None:
        self.client = client

    def get_current_price(self, symbol: str) -> int:
        """
        국내주식 현재가 조회.
        ⚠️ 확인 필요: tr_id(FHKST01010100) 및 응답 필드명(stck_prpr)은
        KIS 공식 문서에서 재확인할 것.
        """
        params = {
            "FID_COND_MRKT_DIV_CODE": "J",  # 코스피/코스닥 통합 구분 코드
            "FID_INPUT_ISCD": symbol,
        }
        res = self.client.get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            TrId.CURRENT_PRICE,
            params,
        )
        price = int(res["output"]["stck_prpr"])
        logger.info(f"[시세조회] {symbol} 현재가 {price:,}원")
        return price
