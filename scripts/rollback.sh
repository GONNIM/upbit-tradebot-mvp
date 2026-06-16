#!/bin/bash
# FoodBid Boilerplate 적용 롤백 스크립트 v3.4 (Codex Process Substitution 제거)
# 작성일: 2026-04-22
# 목적: 백업에서 파일 복원 (임시 백업 보존, 경로 안전, 에러 처리)

set -euo pipefail

# 프로젝트 루트 디렉토리
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# 인자 확인
if [ $# -eq 0 ]; then
    echo "사용법: $0 <TIMESTAMP|LATEST>"
    echo ""
    echo "사용 가능한 백업:"
    if [ -d ".backup" ]; then
        ls -1 .backup | grep -v LATEST | sort -r | head -n 5
    else
        echo "  (백업 없음)"
    fi
    exit 1
fi

# 백업 디렉토리 결정
BACKUP_ID="$1"
if [ "$BACKUP_ID" = "LATEST" ]; then
    if [ ! -L ".backup/LATEST" ]; then
        echo "❌ 오류: LATEST 백업이 존재하지 않습니다."
        exit 1
    fi
    BACKUP_DIR=".backup/$(readlink .backup/LATEST)"
else
    BACKUP_DIR=".backup/${BACKUP_ID}"
fi

# 백업 디렉토리 존재 확인
if [ ! -d "$BACKUP_DIR" ]; then
    echo "❌ 오류: 백업 디렉토리가 존재하지 않습니다: $BACKUP_DIR"
    exit 1
fi

echo "======================================"
echo "FoodBid Boilerplate 롤백 v3.4"
echo "======================================"
echo "프로젝트: $PROJECT_ROOT"
echo "백업 소스: $BACKUP_DIR"
echo ""

# 백업 정보 출력
if [ -f "$BACKUP_DIR/backup-info.txt" ]; then
    echo "백업 정보:"
    cat "$BACKUP_DIR/backup-info.txt"
    echo ""
fi

# 확인 요청
read -p "⚠️  현재 파일을 덮어쓰시겠습니까? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ 롤백 취소됨"
    exit 0
fi

# 백업 대상 목록 (단일 소스 - manifest 우선, Codex #2 해결)
if [ -f "$BACKUP_DIR/backup-manifest.txt" ]; then
    # Bash 3.2 호환 배열 읽기 - Codex v3.3 MEDIUM 이슈 해결 (process substitution 제거)
    BACKUP_TARGETS=()
    TEMP_FILE=$(mktemp)
    trap 'rm -f "$TEMP_FILE"' EXIT

    if ! grep -Ev '^[[:space:]]*(#|$)' "$BACKUP_DIR/backup-manifest.txt" > "$TEMP_FILE"; then
        echo "  ❌ 백업 manifest 파일 읽기 실패"
        exit 1
    fi

    while IFS= read -r line; do
        BACKUP_TARGETS+=("$line")
    done < "$TEMP_FILE"

    if [ ${#BACKUP_TARGETS[@]} -eq 0 ]; then
        echo "  ❌ 복원할 대상이 없습니다"
        exit 1
    fi

    echo "  ✓ manifest에서 백업 대상 로드 (${#BACKUP_TARGETS[@]}개)"
else
    # Fallback: 기본값
    BACKUP_TARGETS=(
        "CLAUDE.md"
        ".claude/context/project-rules.md"
        ".claude/lessons-learned.md"
        "docs/issues"
    )
    echo "  ⚠ manifest 없음, 기본 백업 대상 사용 (${#BACKUP_TARGETS[@]}개)"
fi

# 임시 백업 생성 (롤백 전 현재 상태 보존 - CRITICAL #2 해결)
TEMP_BACKUP_TIMESTAMP=$(date +%Y%m%d_%H%M%S)
TEMP_BACKUP_DIR=".backup/temp_${TEMP_BACKUP_TIMESTAMP}"
mkdir -p "$TEMP_BACKUP_DIR"

echo ""
echo "[1/4] 임시 백업 생성 중 (롤백 전 현재 상태 - 전체 보존)..."
TEMP_EXISTING=()
for target in "${BACKUP_TARGETS[@]}"; do
    if [ -e "$target" ]; then
        TEMP_EXISTING+=("$target")
        echo "  ✓ $target"
    fi
done

if [ ${#TEMP_EXISTING[@]} -gt 0 ]; then
    tar -czf "$TEMP_BACKUP_DIR/files.tar.gz" "${TEMP_EXISTING[@]}" 2>/dev/null || {
        echo "  ⚠ tar 실패, cp 사용"
        for target in "${TEMP_EXISTING[@]}"; do
            if [ -d "$target" ]; then
                mkdir -p "$TEMP_BACKUP_DIR/$(dirname "$target")"
                cp -r "$target" "$TEMP_BACKUP_DIR/$target"
            else
                mkdir -p "$TEMP_BACKUP_DIR/$(dirname "$target")"
                cp "$target" "$TEMP_BACKUP_DIR/$target"
            fi
        done
    }
    echo "  → $TEMP_BACKUP_DIR"
else
    echo "  ⚠ 임시 백업할 파일 없음"
fi

echo ""
echo "[2/4] 파일 복원 중 (경로 보존 - CRITICAL #1, #3 해결)..."

# tar.gz 백업이 있으면 tar로 복원 (경로 자동 보존)
if [ -f "$BACKUP_DIR/files.tar.gz" ]; then
    echo "  ✓ tar.gz 백업 감지, tar로 복원 중..."
    tar -xzf "$BACKUP_DIR/files.tar.gz" -C "$PROJECT_ROOT" 2>/dev/null && {
        echo "  ✅ tar 복원 성공"
    } || {
        echo "  ❌ tar 복원 실패, 대안 시도"
        exit 1
    }
else
    # Fallback: 개별 파일 복원 (find -print0로 안전하게 - CRITICAL #3 해결)
    echo "  ⚠ tar.gz 없음, 개별 파일 복원 중..."
    if [ -d "$BACKUP_DIR/CLAUDE.md" ] || [ -f "$BACKUP_DIR/CLAUDE.md" ]; then
        # v2.0 백업 형식 (평탄화) - 수동 매핑
        for target in "${BACKUP_TARGETS[@]}"; do
            BACKUP_FILE="$BACKUP_DIR/$(basename "$target")"
            if [ -e "$BACKUP_FILE" ]; then
                echo "  ✓ $target <- $(basename "$target")"
                mkdir -p "$(dirname "$target")"
                cp -r "$BACKUP_FILE" "$target"
            fi
        done
    else
        # 구조 보존 백업 형식 (파일만 복원 - Codex #3 해결)
        find "$BACKUP_DIR" -mindepth 1 -type f ! -name '*.txt' ! -name '*.tar.gz' -print0 |
        while IFS= read -r -d '' file; do
            RELATIVE_PATH="${file#$BACKUP_DIR/}"

            echo "  ✓ $RELATIVE_PATH"
            mkdir -p "$(dirname "$RELATIVE_PATH")"
            cp "$file" "$RELATIVE_PATH"
        done
    fi
fi

echo ""
echo "[3/4] Git 상태 확인..."
if [ -f "$BACKUP_DIR/git-full-state.txt" ]; then
    echo "백업 시점 Git 상태:"
    head -n 5 "$BACKUP_DIR/git-full-state.txt"
    echo "  (전체: cat $BACKUP_DIR/git-full-state.txt)"
elif [ -f "$BACKUP_DIR/git-commit.txt" ]; then
    echo "백업 시점 커밋:"
    cat "$BACKUP_DIR/git-commit.txt"
fi

echo ""
echo "[4/4] 검증 중..."
RESTORED_COUNT=0
for target in "${BACKUP_TARGETS[@]}"; do
    if [ -e "$target" ]; then
        RESTORED_COUNT=$((RESTORED_COUNT + 1))
        echo "  ✓ $target (복원됨)"
    else
        echo "  ⚠ $target (백업에 없었음)"
    fi
done

echo ""
echo "======================================"
echo "✅ 롤백 완료!"
echo "======================================"
echo "복원된 파일: $RESTORED_COUNT/${#BACKUP_TARGETS[@]}"
echo "임시 백업: $TEMP_BACKUP_DIR"
echo "  (문제 발생 시 이 백업에서 재복원 가능)"
echo ""
echo "롤백 취소 (임시 백업에서 복원):"
echo "  ./scripts/rollback.sh temp_${TEMP_BACKUP_TIMESTAMP}"
echo ""
echo "======================================"
echo "Codex v3.4 개선 사항:"
echo "- ✅ tar로 경로 보존 복원 (CRITICAL #1)"
echo "- ✅ 임시 백업 전체 보존 (CRITICAL #2)"
echo "- ✅ find -print0 안전 반복 (HIGH #3)"
echo "- ✅ Bash 3.2 호환 (mapfile → while read, v3.2)"
echo "- ✅ 버전 표기 일관성 (v3.3)"
echo "- ✅ Process substitution 제거 + 에러 처리 (v3.4)"
echo "======================================"
echo ""
