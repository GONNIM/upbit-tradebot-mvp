import time
import uuid
import requests
import jwt


UPBIT_API_BASE = "https://api.upbit.com"


class UpbitAuthError(Exception):
    pass


def _bearer(access_key: str, secret_key: str) -> str:
    """
    Upbit JWT 생성 (쿼리 없는 GET의 경우 query_hash 불필요)
    """
    payload = {
        "access_key": access_key,
        "nonce": str(uuid.uuid4()),
        "iat": int(time.time())
    }
    token = jwt.encode(payload, secret_key, algorithm="HS256")
    return f"Bearer {token}"


def get_server_public_ip():
    """서버의 공인 IP 주소 확인"""
    try:
        services = [
            "https://api.ipify.org?format=json",
            "https://ifconfig.me/ip",
            "https://icanhazip.com",
        ]
        for service in services:
            try:
                r = requests.get(service, timeout=3)
                if r.status_code == 200:
                    if "json" in service:
                        return r.json().get("ip")
                    else:
                        return r.text.strip()
            except:
                continue
        return "IP 확인 실패"
    except Exception as e:
        return f"오류: {e}"


def validate_upbit_keys(access_key: str, secret_key: str, timeout: float = 5.0):
    """
    키 유효성 검증:
      - GET /v1/accounts 로 호출
      - 200이면 성공(잔고 리스트 반환)
      - 401/422 등은 실패(메시지 반환)
    반환: (ok: bool, data_or_error: dict|str)
    """
    server_ip = get_server_public_ip()
    print(f"[DEBUG] 현재 서버 공인 IP: {server_ip}")

    headers = {
        "Authorization": _bearer(access_key, secret_key),
    }
    try:
        r = requests.get(f"{UPBIT_API_BASE}/v1/accounts", headers=headers, timeout=timeout)
    except requests.RequestException as e:
        return False, f"네트워크 오류: {e}"

    print(f"[DEBUG] Status: {r.status_code}")
    print(f"[DEBUG] Body: {r.text}")
    
    if r.status_code == 200:
        try:
            data = r.json()
            print(f"[DEBUG] Parsed JSON: {data}")
            print(f"[DEBUG] Type: {type(data)}, Length: {len(data) if isinstance(data, list) else 'N/A'}")
            return True, data # 계좌/잔고 배열
        except Exception:
            return True, [] # 응답이 비정상 JSON이면 빈 배열
    elif r.status_code == 401:
        # Upbit는 401에서 상세메시지(body) 제공
        try:
            j = r.json()
            return False, j.get("error", {}).get("message", "인증 실패(401)")
        except Exception:
            return False, "인증 실패(401)"
    else:
        # 기타 상태코드
        try:
            j = r.json()
            msg = j.get("error", {}).get("message")
        except Exception:
            msg = None
        return False, msg or f"검증 실패(status={r.status_code})"
