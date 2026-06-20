"""
공통 API 클라이언트
- 인증 헤더 자동 부착
- 타임아웃 + 간단한 재시도 로직
- API 레이어를 트레이딩 로직과 분리하기 위한 단일 진입점
"""
import time
from typing import Optional

import requests

from config import BASE_URL, APP_KEY, APP_SECRET
from auth import get_access_token, get_hashkey
from logger import logger

TIMEOUT = 5
MAX_RETRIES = 2
RETRY_DELAY_SEC = 2


class ApiClient:
    def __init__(self) -> None:
        self.token = get_access_token()

    def _headers(self, tr_id: str, hashkey_body: Optional[dict] = None) -> dict:
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self.token}",
            "appkey": APP_KEY,
            "appsecret": APP_SECRET,
            "tr_id": tr_id,
            "custtype": "P",
        }
        if hashkey_body is not None:
            headers["hashkey"] = get_hashkey(hashkey_body)
        return headers

    def get(self, path: str, tr_id: str, params: dict) -> dict:
        return self._request("GET", path, tr_id, params=params)

    def post(self, path: str, tr_id: str, body: dict, use_hashkey: bool = False) -> dict:
        return self._request("POST", path, tr_id, body=body, use_hashkey=use_hashkey)

    def _request(
        self,
        method: str,
        path: str,
        tr_id: str,
        params: Optional[dict] = None,
        body: Optional[dict] = None,
        use_hashkey: bool = False,
    ) -> dict:
        url = f"{BASE_URL}{path}"
        headers = self._headers(tr_id, hashkey_body=body if use_hashkey else None)

        last_error: Optional[Exception] = None
        for attempt in range(1, MAX_RETRIES + 2):
            try:
                if method == "GET":
                    res = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
                else:
                    res = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
                res.raise_for_status()
                return res.json()
            except requests.exceptions.Timeout as e:
                last_error = e
                logger.error(f"[API 타임아웃] 시도 {attempt}/{MAX_RETRIES + 1} - {path}")
            except requests.exceptions.RequestException as e:
                last_error = e
                logger.error(f"[API 오류] 시도 {attempt}/{MAX_RETRIES + 1} - {path} - {e}")

            if attempt <= MAX_RETRIES:
                time.sleep(RETRY_DELAY_SEC)

        raise RuntimeError(f"API 요청 최종 실패: {path} ({last_error})")
