"""tradebot-v2 유닛과 같은 보호 속성 안에서 실행되는 탐침 (check_v2_unit.sh 가 systemd-run 으로 호출).

표준 라이브러리만 쓴다(v2·엔진 import 없음). 출력은 `PASS|FAIL|RESIDUAL <항목>` 줄뿐이다.
예외 문자열·파일 내용·경로 값은 출력하지 않는다. 항목은 모두 15개다(호스트 쪽 검사 unit-props·unit-rw-paths-unchanged·
no-upbit-env·pullback-inode-match 는 셸이 한다). 2차 T18 에서 제어 요청 폴더·파일과 적용본 항목 5개를 더했다.
폴더·파일이 아직 없으면 `PASS <항목>(absent)` 이다(배포 직후 정상 — 첫 모의 전환 입회 뒤 다시 돌린다, 결정 1030-06 A).

실행 시점: 배포 때와 첫 모의 전환 입회 뒤(전환 완료·워밍업 뒤). 그 밖에는 돌리지 않는다.

사용: python check_v2_unit_probe.py <tradebot MainPID> [user_id]
"""
import errno
import os
import re
import sqlite3
import stat
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
# 2차 T18: 제어 요청 통로(v2/control.py ↔ engine/control_requests.py)와 적용본(engine/pullback_params.py)
CONTROL_BASE_DIR = os.path.join(DATA_DIR, "v2_control")
CONTROL_USER_DIR = os.path.join(CONTROL_BASE_DIR, USER_ID)
APPLIED_FILE = os.path.join(ROOT, "%s_applied_params_PULLBACK.json" % USER_ID)
APPLIED_LAST_GOOD_FILE = os.path.join(ROOT, "%s_applied_params_PULLBACK.last_good.json" % USER_ID)
# 기대 소유자(서버 유닛은 root). 시험은 이 값을 바꿔 가짜 루트에서 돌린다.
ROOT_UID = 0


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
    배포 때와 첫 모의 전환 입회 뒤(전환 완료·워밍업 뒤)에만 실행한다(결정 1030-06 A). DB 가 없으면 만들지 않고 FAIL(mode=rw).
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
    """PULLBACK 파일을 r+ 로 열기만 하고 닫는다(쓰지 않음, mtime 불변). ReadWritePaths 파일 항목 확인용.
    2차 T18 계획의 `saved-writable-by-v2`(저장본 쓰기 가능)는 이 항목이 맡는다(이름 무변경, PO 결정 3)."""
    try:
        with open(PULLBACK_FILE, "r+") as f:
            pass
        print("PASS pullback-open")
    except FileNotFoundError:
        print("FAIL pullback-file-missing")
    except Exception:
        print("FAIL pullback-open")


# ---------------------------------------------------------------- 2차 T18 (모두 lstat — 링크를 따라가지 않는다)
def _lstat_or_none(path):
    """lstat 결과, 없으면 None. 그 밖의 OSError 는 그대로 올린다."""
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None


def _plain_dir_700(st):
    return stat.S_ISDIR(st.st_mode) and stat.S_IMODE(st.st_mode) == 0o700 and st.st_uid == ROOT_UID


def _plain_file_600(st):
    return stat.S_ISREG(st.st_mode) and stat.S_IMODE(st.st_mode) == 0o600 and st.st_uid == ROOT_UID


def _control_names():
    """사용자 폴더의 (req-*.json, res-*.json) 이름 목록. 폴더가 없으면 None. 폴더 이름만 읽는다(파일은 열지 않음)."""
    st = _lstat_or_none(CONTROL_USER_DIR)
    if st is None:
        return None
    if not stat.S_ISDIR(st.st_mode):
        raise OSError("control user dir is not a plain directory")
    names = sorted(os.listdir(CONTROL_USER_DIR))
    reqs = [n for n in names if n.startswith("req-") and n.endswith(".json")]
    ress = [n for n in names if n.startswith("res-") and n.endswith(".json")]
    return reqs, ress


def check_v2_control_dir_700():
    """services/data/v2_control 와 점검 계정 폴더가 700·root·링크 아님(신버전이 첫 요청 때 만든다, 엔진은 만들지 않음)."""
    try:
        for path in (CONTROL_BASE_DIR, CONTROL_USER_DIR):
            st = _lstat_or_none(path)
            if st is None:
                print("PASS v2-control-dir-700(absent)")
                return
            if not _plain_dir_700(st):
                print("FAIL v2-control-dir-700")
                return
        print("PASS v2-control-dir-700")
    except Exception:
        print("FAIL v2-control-dir-700")


def check_v2_control_files_600():
    """점검 계정 폴더의 요청(req-*.json)·결과(res-*.json) 파일이 600·root·일반 파일. 내용은 열지 않는다."""
    try:
        listed = _control_names()
        if listed is None or not (listed[0] or listed[1]):
            print("PASS v2-control-files-600(absent)")
            return
        for name in listed[0] + listed[1]:
            st = _lstat_or_none(os.path.join(CONTROL_USER_DIR, name))
            if st is not None and not _plain_file_600(st):
                print("FAIL v2-control-files-600")
                return
        print("PASS v2-control-files-600")
    except Exception:
        print("FAIL v2-control-files-600")


def check_applied_600():
    """적용본·사본(엔진만 쓴다)이 600·root·일반 파일. 활성 전략이 새 전략으로 바뀌기 전에는 없는 것이 정상."""
    try:
        found = 0
        for path in (APPLIED_FILE, APPLIED_LAST_GOOD_FILE):
            st = _lstat_or_none(path)
            if st is None:
                continue
            found += 1
            if not _plain_file_600(st):
                print("FAIL applied-600")
                return
        if found:
            print("PASS applied-600")
        else:
            print("PASS applied-600(absent)")
    except Exception:
        print("FAIL applied-600")


def _applied_write_refused(applied_path):
    """이 유닛 안에서 적용본을 쓰기로 열 수 없는가. r+ 는 만들지도(O_CREAT 없음) 비우지도(O_TRUNC 없음) 않는다.
    혹시 열리면 아무것도 쓰지 않고 바로 닫는다(→ 거짓)."""
    if os.access(applied_path, os.W_OK):
        return False
    try:
        f = open(applied_path, "r+")
    except OSError as e:
        return e.errno in (errno.EROFS, errno.EACCES)
    f.close()
    return False


def check_applied_not_writable_by_v2():
    """신버전은 적용본을 쓸 수 없어야 한다(EROFS 기대). 파일이 없으면 만들어 보지 않고 루트 쓰기 불가만 본다."""
    try:
        present = [p for p in (APPLIED_FILE, APPLIED_LAST_GOOD_FILE) if _lstat_or_none(p) is not None]
        if not present:
            if os.access(ROOT, os.W_OK):
                print("FAIL applied-not-writable-by-v2(absent)")
            else:
                print("PASS applied-not-writable-by-v2(absent)")
            return
        for applied_path in present:
            if not _applied_write_refused(applied_path):
                print("FAIL applied-not-writable-by-v2")
                return
        print("PASS applied-not-writable-by-v2")
    except Exception:
        print("FAIL applied-not-writable-by-v2")


def check_v2_control_results_readable():
    """신버전이 엔진이 쓴 결과 파일(600·root)을 읽을 수 있는가(계획 §12-10). 이름순 첫 res-*.json 1개를 1바이트만.
    지우기는 엔진 몫이라 보지 않는다. 요청 파일·임시 파일(.req-*.tmp)은 대상이 아니다."""
    try:
        listed = _control_names()
        if listed is None or not listed[1]:
            print("PASS v2-control-results-readable(absent)")
            return
        path = os.path.join(CONTROL_USER_DIR, listed[1][0])
        st = os.lstat(path)
        if not stat.S_ISREG(st.st_mode):
            print("FAIL v2-control-results-readable")
            return
        with open(path, "rb") as f:
            f.read(1)
        print("PASS v2-control-results-readable")
    except Exception:
        print("FAIL v2-control-results-readable")


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
    check_v2_control_dir_700()
    check_v2_control_files_600()
    check_applied_600()
    check_applied_not_writable_by_v2()
    check_v2_control_results_readable()


if __name__ == "__main__":
    main()
