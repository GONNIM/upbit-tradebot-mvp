#!/bin/bash
# FoodBid Boilerplate 적용 전 백업 스크립트 v3.4 (Codex 최종 버전)
# 작성일: 2026-04-22
# 목적: CLAUDE.md 및 관련 파일 안전 백업 (타임스탬프 기반, 경로 보존)

set -euo pipefail

# 프로젝트 루트 디렉토리
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# 백업 디렉토리 및 타임스탬프
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=".backup/${TIMESTAMP}"
LATEST_LINK=".backup/LATEST"

echo "======================================"
echo "FoodBid Boilerplate 적용 전 백업 v3.4"
echo "======================================"
echo "프로젝트: $PROJECT_ROOT"
echo "백업 디렉토리: $BACKUP_DIR"
echo "타임스탬프: $TIMESTAMP"
echo ""

# 백업 디렉토리 생성
mkdir -p "$BACKUP_DIR"

# 백업 대상 파일 목록 (단일 소스)
BACKUP_TARGETS=(
    "CLAUDE.md"
    ".claude/context/project-rules.md"
    ".claude/lessons-learned.md"
    "docs/issues"
)

echo "[1/5] 파일 백업 중 (tar로 경로 보존)..."
# tar로 원본 상대경로 보존하여 백업
EXISTING_FILES=()
for target in "${BACKUP_TARGETS[@]}"; do
    if [ -e "$target" ]; then
        EXISTING_FILES+=("$target")
        echo "  ✓ $target"
    else
        echo "  ⚠ $target (존재하지 않음, 스킵)"
    fi
done

if [ ${#EXISTING_FILES[@]} -gt 0 ]; then
    tar -czf "$BACKUP_DIR/files.tar.gz" "${EXISTING_FILES[@]}" 2>/dev/null || {
        echo "  ❌ tar 백업 실패, 대안으로 cp 사용"
        # Fallback: cp with --parents
        for target in "${EXISTING_FILES[@]}"; do
            if [ -d "$target" ]; then
                mkdir -p "$BACKUP_DIR/$(dirname "$target")"
                cp -r "$target" "$BACKUP_DIR/$target"
            else
                mkdir -p "$BACKUP_DIR/$(dirname "$target")"
                cp "$target" "$BACKUP_DIR/$target"
            fi
        done
    }
else
    echo "  ⚠ 백업할 파일 없음"
fi

echo ""
echo "[2/5] Git 상태 저장 중 (완전 추적)..."
{
    echo "=== Git Commit ===$(git log -1 --oneline 2>/dev/null || echo 'Not a git repo')"
    echo ""
    echo "=== Git Diff (unstaged) ==="
    git diff 2>/dev/null || echo "(no diff)"
    echo ""
    echo "=== Git Diff (staged) ==="
    git diff --cached 2>/dev/null || echo "(no staged)"
    echo ""
    echo "=== Git Untracked Files ==="
    git ls-files --others --exclude-standard 2>/dev/null || echo "(no untracked)"
    echo ""
    echo "=== Git Status ==="
    git status 2>/dev/null || echo "(not a git repo)"
} > "$BACKUP_DIR/git-full-state.txt"

echo ""
echo "[3/5] 백업 대상 목록 저장 (복원 참조용)..."
cat > "$BACKUP_DIR/backup-manifest.txt" <<EOF
# 백업 대상 파일 목록 (단일 소스)
# 이 목록은 backup.sh와 rollback.sh에서 공유됨

$(for target in "${BACKUP_TARGETS[@]}"; do echo "$target"; done)
EOF

echo ""
echo "[4/5] LATEST 링크 업데이트 중..."
rm -f "$LATEST_LINK"
ln -s "$TIMESTAMP" "$LATEST_LINK"
echo "  ✓ .backup/LATEST -> $TIMESTAMP"

echo ""
echo "[5/5] 백업 메타데이터 생성 중..."
cat > "$BACKUP_DIR/backup-info.txt" <<EOF
====================================
FoodBid Boilerplate 백업 정보 v3.4
====================================

백업 시각: $TIMESTAMP
프로젝트: Upbit Tradebot MVP
목적: FoodBid Boilerplate 적용 전 백업
백업 스크립트: scripts/backup.sh v3.4

백업된 파일 (경로 보존):
$(for target in "${EXISTING_FILES[@]}"; do echo "  - $target"; done)

백업 형식: tar.gz (원본 상대경로 보존)
복원 방법: ./scripts/rollback.sh $TIMESTAMP

Git 커밋:
$(git log -1 --oneline 2>/dev/null || echo "Not a git repo")

====================================
Codex v3.4 개선 사항:
- ✅ tar로 경로 보존 백업 (CRITICAL 해결)
- ✅ Git staged/untracked 추적 (HIGH 해결)
- ✅ 백업 대상 단일 소스화 (manifest)
====================================
EOF

echo ""
echo "======================================"
echo "✅ 백업 완료!"
echo "======================================"
echo "백업 위치: $BACKUP_DIR"
echo "복원 명령: ./scripts/rollback.sh $TIMESTAMP"
echo ""
echo "백업 파일 목록:"
ls -lh "$BACKUP_DIR" | tail -n +2
echo ""
echo "백업 크기:"
du -sh "$BACKUP_DIR"
echo ""
