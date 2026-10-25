"""tradebot-v2 유닛과 같은 보호 속성 안에서 실행되는 탐침 (check_v2_unit.sh 가 systemd-run 으로 호출).

표준 라이브러리만 쓴다(v2·엔진 import 없음). 출력은 `PASS|FAIL|RESIDUAL <항목>` 줄뿐이다.
예외 문자열·파일 내용·경로 값은 출력하지 않는다. 항목은 모두 10개다(호스트 쪽 검사 no-upbit-env·pullback-inode-match 는 셸이 한다).

사용: python check_v2_unit_probe.py <tradebot MainPID> [user_id]
"""
import os
import re
import sqlite3
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
USER_ID = "mcmax33"
if len(sys.argv) > 2 and re.fullmatch(r"[A-Za-z0-9_]{1,32}", sys.argv[2]):
    USER_ID = sys.argv[2]

DATA_DIR = os.path.join(ROOT, "services", "data")
LIVE_DB = os.path.join(DATA_DIR, "tradebot_%s.db" % USER_ID)
HIST_DB = os.path.join(DATA_DIR, "v2hist_%s.db" % USER_ID)
ACTIVE_STRATEGY_FILE = os.path.join(ROOT, "%s_active_strategy.txt" % USER_ID)
PULLBACK_FILE = os.path.join(ROOT, "%s_latest_params_PULLBACK.json" % USER_ID)
ENV_FILE = os.path.join(ROOT, ".env")
SECRETS_FILE = os.path.join(ROOT, ".streamlit", "secrets.toml")
CREDENTIALS_FILE = os.path.join(ROOT, "credentials.yaml")


def check_live_db_ro():
    """실매매 DB 를 읽기 전용으로 연다. (ro 연결이 -wal·-shm 을 만들 수 있다 — 본 DB 와 같은 권한, 엔진이 정리)"""
    conn = None
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % LIVE_DB, uri=True, timeout=5)
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
        print("PASS live-db-ro-read")
    except Exception:
        print("FAIL live-db-ro-read")
    finally:
        if conn is not None:
            conn.close()


def check_live_db_write_lock():
    """실매매 DB 에 쓰기 연결을 열어 BEGIN IMMEDIATE → 곧바로 ROLLBACK 만 한다(데이터는 바뀌지 않는다).

    신버전의 매매 중지/재개(v2.db.set_paused)가 이 유닛 안에서 실매매 DB 에 쓸 수 있는지 미리 본다.
    BEGIN IMMEDIATE 가 잡혀 있는 밀리초 동안 엔진의 쓰기가 잠깐 기다릴 수 있다(busy_timeout 안에서 풀림).
    배포 점검 때 한 번만 실행한다. DB 가 없으면 만들지 않고 FAIL(mode=rw).
    """
    conn = None
    try:
        conn = sqlite3.connect("file:%s?mode=rw" % LIVE_DB, uri=True, timeout=5, isolation_level=None)
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
        print("PASS live-db-write-lock")
    except Exception:
        print("FAIL live-db-write-lock")
    finally:
        if conn is not None:
            conn.close()


def check_v2hist_write():
    """v2hist 쓰기 가능 여부. 파일이 있으면 BEGIN-INSERT-ROLLBACK(행 남지 않음), 없으면 폴더 쓰기만 본다."""
    if os.path.exists(HIST_DB):
        conn = None
        try:
            conn = sqlite3.connect("file:%s?mode=rw" % HIST_DB, uri=True, timeout=5, isolation_level=None)
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT INTO v2_settings_history(user_id, saved_at, source_page, strategy_type) "
                    "VALUES ('probe', 'probe', 'probe', 'probe')"
                )
            finally:
                conn.execute("ROLLBACK")
            print("PASS v2hist-write")
        except Exception:
            print("FAIL v2hist-write")
        finally:
            if conn is not None:
                conn.close()
        return
    path = os.path.join(DATA_DIR, ".v2probe_%d" % os.getpid())
    created = False
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        created = True
        os.close(fd)
        os.unlink(path)
        created = False
        print("PASS v2hist-write(folder)")
    except Exception:
        print("FAIL v2hist-write(folder)")
    finally:
        if created:
            try:
                os.unlink(path)
            except Exception:
                pass


def check_active_strategy_read():
    try:
        with open(ACTIVE_STRATEGY_FILE, "rb") as f:
            f.read(1)
        print("PASS active-strategy-read")
    except Exception:
        print("FAIL active-strategy-read")


def _inaccessible_state(path):
    """InaccessiblePaths 로 가려졌는지 본다. 열려도 내용은 읽지 않는다.
    반환: blocked(열기 실패) / placeholder(0바이트 자리표) / missing(파일 없음) / stat(크기 확인 실패) / readable(내용 있음)"""
    try:
        fd = os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "blocked"
    os.close(fd)
    try:
        size = os.stat(path).st_size
    except OSError:
        return "stat"
    # InaccessiblePaths 는 0바이트 자리표를 덧씌운다
    return "placeholder" if size == 0 else "readable"


def check_env_inaccessible():
    state = _inaccessible_state(ENV_FILE)
    if state == "blocked":
        print("PASS env-inaccessible")
    elif state == "placeholder":
        print("PASS env-inaccessible(placeholder)")
    elif state == "missing":
        print("FAIL env-not-found(cannot-verify)")
    else:
        print("FAIL env-readable")


def check_secrets_inaccessible():
    state = _inaccessible_state(SECRETS_FILE)
    if state == "blocked":
        print("PASS secrets-inaccessible")
    elif state == "placeholder":
        print("PASS secrets-inaccessible(placeholder)")
    elif state == "missing":
        print("FAIL secrets-not-found(cannot-verify)")
    else:
        print("FAIL secrets-readable")


def check_credentials_inaccessible():
    state = _inaccessible_state(CREDENTIALS_FILE)
    if state == "blocked":
        print("PASS credentials-inaccessible")
    elif state == "placeholder":
        print("PASS credentials-inaccessible(placeholder)")
    elif state == "missing":
        print("FAIL credentials-not-found(cannot-verify)")
    else:
        print("FAIL credentials-readable")


def check_root_readonly():
    """저장소 루트에 새 파일을 만들 수 없어야 한다(ProtectSystem=strict, EROFS 기대)."""
    path = os.path.join(ROOT, ".v2probe_root_%d" % os.getpid())
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except OSError:
        print("PASS root-readonly")
        return
    try:
        os.close(fd)
    except OSError:
        pass
    try:
        os.unlink(path)
    except OSError:
        pass
    print("FAIL root-writable")


def check_proc_environ(pid_text):
    """tradebot 프로세스의 환경 변수 파일을 1바이트만 읽어 본다. 내용은 버린다(spec E18 남는 위험)."""
    if not re.fullmatch(r"[1-9][0-9]{0,8}", pid_text or ""):
        print("FAIL proc-tradebot-pid-unknown")
        return
    try:
        with open("/proc/%s/environ" % pid_text, "rb") as f:
            f.read(1)
    except FileNotFoundError:
        print("FAIL proc-tradebot-gone")
    except OSError:
        print("PASS proc-environ-blocked")
    else:
        print("RESIDUAL proc-environ-readable")


def check_pullback_open():
    """PULLBACK 파일을 r+ 로 열기만 하고 닫는다(쓰지 않음, mtime 불변). ReadWritePaths 파일 항목 확인용."""
    try:
        with open(PULLBACK_FILE, "r+") as f:
            pass
        print("PASS pullback-open")
    except FileNotFoundError:
        print("FAIL pullback-file-missing")
    except Exception:
        print("FAIL pullback-open")


def main():
    pid_text = sys.argv[1] if len(sys.argv) > 1 else ""
    check_live_db_ro()
    check_live_db_write_lock()
    check_v2hist_write()
    check_active_strategy_read()
    check_env_inaccessible()
    check_secrets_inaccessible()
    check_credentials_inaccessible()
    check_root_readonly()
    check_proc_environ(pid_text)
    check_pullback_open()


if __name__ == "__main__":
    main()
