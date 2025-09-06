# tools/gen_repo_insights.py
# -*- coding: utf-8 -*-
"""
Generate REPO_MAP.txt (구조 요약) & CODE_FLAGS.txt (TODO/FIXME 등)
- 결정적(Deterministic) 출력: 정렬/제외/마지막개행 고정
- --check: 파일을 수정하지 않고 최신 여부만 검사 (같으면 0, 다르면 1)
"""
import os, re, sys, argparse
from pathlib import Path

EXCLUDE_DIRS = {
    "node_modules",
    ".git",
    "dist",
    "build",
    "out",
    ".next",
    ".turbo",
    ".vercel",
    ".venv",
    "venv",
    "__pycache__",
    "coverage",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
EXCLUDE_FILE_PAT = re.compile(r"\.(pyc|pyo|pyd|so|dll|exe|bin|class|log)$", re.I)
EXCLUDE_FILE_NAMES = {
    ".DS_Store",
    "REPO_MAP.txt",
    "CODE_FLAGS.txt",
}

FLAG_PAT = re.compile(r"\b(TODO|FIXME|HACK|XXX|@deprecated|BUG|SECURITY)\b", re.I)


def should_skip_dir(p: Path) -> bool:
    return any(part in EXCLUDE_DIRS for part in p.parts)


def should_skip_file(p: Path) -> bool:
    if any(part in EXCLUDE_DIRS for part in p.parts):
        return True
    if p.name in EXCLUDE_FILE_NAMES:
        return True
    if EXCLUDE_FILE_PAT.search(p.name):
        return True
    return False


def generate(root: Path):
    repo_map_lines, code_flags_lines = [], []

    for dirpath, dirnames, filenames in os.walk(root):
        dp = Path(dirpath)
        if should_skip_dir(dp):
            dirnames[:] = []  # 하위 탐색 중단
            continue

        # 결정적 순서
        dirnames.sort()
        filenames = sorted(filenames)

        rel_dir = "." if dp == root else os.path.relpath(dp, root)
        repo_map_lines.append(f"[DIR] {rel_dir}")

        for fn in filenames:
            fp = dp / fn
            if should_skip_file(fp):
                continue

            rel_file = os.path.relpath(fp, root)
            repo_map_lines.append(f"      {rel_file}")

            # 텍스트 파일만 안전하게 스캔
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if FLAG_PAT.search(line):
                            code_flags_lines.append(f"{rel_file}:{i}: {line.rstrip()}")
            except Exception:
                pass

    # 마지막 줄 개행 고정
    map_txt = "\n".join(repo_map_lines).rstrip("\n") + "\n"
    flags_txt = "\n".join(code_flags_lines).rstrip("\n") + "\n"
    return map_txt, flags_txt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--check", action="store_true", help="파일을 수정하지 않고 최신 여부만 검사"
    )
    args = ap.parse_args()

    root = Path(".").resolve()
    map_txt, flags_txt = generate(root)

    if args.check:

        def read_or_empty(p):
            try:
                return Path(p).read_text(encoding="utf-8")
            except FileNotFoundError:
                return ""

        same = (read_or_empty("REPO_MAP.txt") == map_txt) and (
            read_or_empty("CODE_FLAGS.txt") == flags_txt
        )
        sys.exit(0 if same else 1)

    Path("REPO_MAP.txt").write_text(map_txt, encoding="utf-8")
    Path("CODE_FLAGS.txt").write_text(flags_txt, encoding="utf-8")
    print("Generated REPO_MAP.txt and CODE_FLAGS.txt")


if __name__ == "__main__":
    main()
