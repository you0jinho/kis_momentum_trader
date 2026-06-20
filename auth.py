"""
인증 모듈
- 접근 토큰: 당일 발급분이 캐시에 있으면 재사용, 없으면 신규 발급
- hashkey: 주문 API 호출 시 body 무결성 검증용으로 필요
"""
import json
import os
from datetime import datetime
from typing import Optional

import requests

from config import BASE_URL, APP_KEY, APP_SECRET, TOKEN_CACHE_PATH
from logger import logger

TIMEOUT = 5


def _load_cached_token() -> Optional[str]:
    """오늘 발급된 토큰이 캐시 파일에 있으면 반환, 없으면 None."""
    if not os.path.exists(TOKEN_CACHE_PATH):
        return None
    try:
        with open(TOKEN_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        logger.error("토큰 캐시 파일을 읽을 수 없어 재발급을 진행합니다.")
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    if data.get("issued_date") == today and data.get("access_token"):
        logger.info("[토큰] 당일 발급된 캐시 토큰을 재사용합니다.")
        return data["access_token"]
    return None


def _save_token(token: str) -> None:
    with open(TOKEN_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {"access_token": token, "issued_date": datetime.now().strftime("%Y-%m-%d")},
            f,
        )


def get_access_token() -> str:
    """당일 캐시 토큰이 있으면 재사용하고, 없을 때만 신규 발급한다."""
    cached = _load_cached_token()
    if cached:
        return cached

    logger.info("[토큰] 캐시된 당일 토큰이 없어 신규 발급을 요청합니다.")
    url = f"{BASE_URL}/oauth2/tokenP"
    body = {"grant_type": "client_credentials", "appkey": APP_KEY, "appsecret": APP_SECRET}

    try:
        res = requests.post(url, json=body, timeout=TIMEOUT)
        res.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"[토큰] 발급 실패: {e}")
        raise

    token = res.json()["access_token"]
    _save_token(token)
    logger.info("[토큰] 신규 발급 완료, 캐시에 저장했습니다.")
    return token


def get_hashkey(body: dict) -> str:
    """
    주문 body를 해시 처리해서 반환.
    ⚠️ 확인 필요: 경로/응답 필드명("HASH")은 공식 문서에서 재확인할 것.
    """
    url = f"{BASE_URL}/uapi/hashkey"
    headers = {
        "content-type": "application/json",
        "appkey": APP_KEY,
        "appsecret": APP_SECRET,
    }
    try:
        res = requests.post(url, headers=headers, json=body, timeout=TIMEOUT)
        res.raise_for_status()
        return res.json()["HASH"]
    except requests.exceptions.RequestException as e:
        logger.error(f"[hashkey] 발급 실패: {e}")
        raise
