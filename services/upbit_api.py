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
    키 유효성 검증 + 상세 디버깅
    """
    server_ip = get_server_public_ip()
    
    headers = {
        "Authorization": _bearer(access_key, secret_key),
    }
    
    debug_info = {
        "server_ip": server_ip,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    try:
        r = requests.get(f"{UPBIT_API_BASE}/v1/accounts", headers=headers, timeout=timeout)
        debug_info["status_code"] = r.status_code
        debug_info["response_body"] = r.text[:500]  # 처음 500자만
    except requests.RequestException as e:
        return False, f"네트워크 오류: {e}\n서버 IP: {server_ip}"

    if r.status_code == 200:
        try:
            data = r.json()
            return True, data
        except Exception as e:
            return True, []
    elif r.status_code == 401:
        try:
            j = r.json()
            error_msg = j.get("error", {}).get("message", "인증 실패")
            
            # IP 제한 에러 상세 안내
            if "IP" in error_msg or "ip" in error_msg.lower():
                return False, (
                    f"🚫 IP 접근 제한 오류\n\n"
                    f"현재 서버 IP: {server_ip}\n\n"
                    f"해결 방법:\n"
                    f"1. Upbit 웹사이트 로그인\n"
                    f"2. Open API 관리 페이지 이동\n"
                    f"3. 위 IP 주소를 화이트리스트에 추가\n\n"
                    f"원본 메시지: {error_msg}"
                )
            return False, error_msg
        except Exception:
            return False, f"인증 실패(401)\n서버 IP: {server_ip}"
    else:
        try:
            j = r.json()
            msg = j.get("error", {}).get("message")
        except Exception:
            msg = None
        return False, msg or f"검증 실패(status={r.status_code})\n서버 IP: {server_ip}"
