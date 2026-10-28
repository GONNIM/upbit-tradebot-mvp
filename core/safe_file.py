"""
2차 T11 수정 1·2회차: 링크(심볼릭 링크)를 따라가지 않는 작은 파일 읽기·쓰기 — 표준 라이브러리만.

- atomic_write_600: 같은 폴더에 임의 이름 임시 파일(O_CREAT|O_EXCL|O_NOFOLLOW, 0o600)을 만들어 쓰고 fchmod 600 뒤
  os.replace. 고정 임시 이름 + O_TRUNC 는 그 자리에 미리 둔 링크를 따라가 바깥 파일을 덮어쓴다(검수 재현).
  os.replace 는 대상이 링크여도 링크 자체를 바꾼다(따라가지 않음). dir_fd 를 주면 그 열린 폴더 기준(이름만).
- read_nofollow: O_NOFOLLOW 로 열고 일반 파일만, 크기 상한. dir_fd 를 주면 그 열린 폴더 기준.
- open_dir_nofollow + check_dir_fd: 폴더를 링크를 따라가지 않고 연 뒤(fd) 소유자 = 이 프로세스·권한 700 을 확인한다.
  권한이 다르면 고치지 않고 거부한다(수정 2회차 N2 — 경로 기준 chmod 는 바꿔치기 경쟁으로 바깥 폴더를 바꿀 수 있었다).
  그 뒤 읽기·쓰기·지우기는 모두 이 fd 기준(dir_fd)이라 경로를 링크로 바꿔치기해도 바깥을 건드리지 않는다.
- clean_stale_tmp: 기동 때 오래된 우리 임시 파일 정리(링크는 건너뜀).
"""
from __future__ import annotations

import os
import secrets
import stat
import tempfile
import time
from typing import Iterable, List, Optional

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)


def atomic_write_600(path, text: str, *, dir_fd: Optional[int] = None) -> None:
    if dir_fd is None:
        path = os.fspath(path)
        d, name = os.path.split(path)
        fd, tmp = tempfile.mkstemp(dir=d or ".", prefix=f".{name}.", suffix=".tmp")
    else:
        name = os.fspath(path)
        tmp = f".{name}.{secrets.token_hex(6)}.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600, dir_fd=dir_fd)
        path = name
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fchmod(f.fileno(), 0o600)   # 엔진 UMask 0022 와 무관하게 600
        if dir_fd is None:
            os.replace(tmp, path)
        else:
            os.replace(tmp, path, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    except BaseException:
        try:
            if dir_fd is None:
                os.unlink(tmp)
            else:
                os.unlink(tmp, dir_fd=dir_fd)
        except OSError:
            pass
        raise


def read_nofollow(path, max_bytes: int, *, dir_fd: Optional[int] = None) -> Optional[bytes]:
    """일반 파일 내용(링크·폴더·상한 초과·없음은 None)."""
    try:
        fd = os.open(os.fspath(path), os.O_RDONLY | _NOFOLLOW | _NONBLOCK, dir_fd=dir_fd)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_size > max_bytes:
            return None
        with os.fdopen(fd, "rb") as f:
            fd = -1
            data = f.read(max_bytes + 1)
        return data if len(data) <= max_bytes else None
    except OSError:
        return None
    finally:
        if fd >= 0:
            os.close(fd)


def open_dir_nofollow(path, *, dir_fd: Optional[int] = None) -> int:
    """폴더를 링크를 따라가지 않고 연다. 없으면 FileNotFoundError, 링크·폴더 아님은 OSError(ELOOP·ENOTDIR)."""
    return os.open(os.fspath(path), os.O_RDONLY | _DIRECTORY | _NOFOLLOW, dir_fd=dir_fd)


def check_dir_fd(fd: int) -> Optional[str]:
    """괜찮으면 None, 아니면 사유 낱말(not_dir·owner·mode). 권한은 고치지 않는다."""
    st = os.fstat(fd)
    if not stat.S_ISDIR(st.st_mode):
        return "not_dir"
    if st.st_uid != os.geteuid():
        return "owner"
    if stat.S_IMODE(st.st_mode) & 0o077:
        return "mode"
    return None


def is_symlink_at(name: str, dir_fd: int) -> bool:
    try:
        return stat.S_ISLNK(os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_mode)
    except OSError:
        return False


def clean_stale_tmp(directory, prefixes: Iterable[str], older_than_sec: float = 600,
                    now: Optional[float] = None) -> List[str]:
    """directory 안의 「<접두>…tmp」 점 파일 가운데 older_than_sec 넘은 일반 파일만 지운다(링크·폴더는 건너뜀).
    지운 이름 목록."""
    now = time.time() if now is None else now
    prefixes = tuple(prefixes)
    removed = []
    try:
        entries = list(os.scandir(os.fspath(directory)))
    except OSError:
        return removed
    for e in entries:
        if not (e.name.startswith(".") and e.name.endswith(".tmp") and e.name.startswith(prefixes)):
            continue
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode) or now - st.st_mtime <= older_than_sec:
            continue
        try:
            os.unlink(e.path)
            removed.append(e.name)
        except OSError:
            pass
    return removed
