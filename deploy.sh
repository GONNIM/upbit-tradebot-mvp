#!/bin/bash
set -e  # 에러 시 스크립트 중단

# ========================================
# Upbit Tradebot MVP - 배포 스크립트
# ========================================

# 설정
PROJECT_DIR="/root/upbit-tradebot-mvp"
SERVICE_NAME="tradebot"
LOG_FILE="${PROJECT_DIR}/streamlit.log"

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 로그 함수
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# 구분선
print_separator() {
    echo "=========================================="
}

# ========================================
# 1. 코드 업데이트
# ========================================
print_separator
log_info "[1/6] Pulling latest code..."
print_separator

cd "${PROJECT_DIR}" || {
    log_error "Failed to change directory to ${PROJECT_DIR}"
    exit 1
}

# 현재 커밋 확인
LOCAL_COMMIT=$(git rev-parse HEAD)
REMOTE_COMMIT=$(git rev-parse origin/main 2>/dev/null || echo "unknown")

log_info "Current commit: ${LOCAL_COMMIT:0:7}"

# Git fetch
if ! git fetch origin; then
    log_error "Failed to fetch from origin"
    exit 1
fi

REMOTE_COMMIT=$(git rev-parse origin/main)

if [ "${LOCAL_COMMIT}" = "${REMOTE_COMMIT}" ]; then
    log_success "Already up to date (${LOCAL_COMMIT:0:7})"
else
    log_info "Updating: ${LOCAL_COMMIT:0:7} → ${REMOTE_COMMIT:0:7}"

    if git pull origin main; then
        log_success "Code updated successfully"
    else
        log_error "Failed to pull from origin"
        exit 1
    fi
fi

# ========================================
# 2. Python 가상환경 활성화
# ========================================
echo ""
print_separator
log_info "[2/6] Activating virtual environment..."
print_separator

if [ -f "${PROJECT_DIR}/venv/bin/activate" ]; then
    source "${PROJECT_DIR}/venv/bin/activate"
    log_success "Virtual environment activated"
    log_info "Python: $(which python3)"
else
    log_error "Virtual environment not found at ${PROJECT_DIR}/venv"
    exit 1
fi

# ========================================
# 3. Python 캐시 삭제
# ========================================
echo ""
print_separator
log_info "[3/6] Cleaning Python cache..."
print_separator

CACHE_COUNT_BEFORE=$(find . -type f -name "*.pyc" 2>/dev/null | wc -l)
PYCACHE_COUNT_BEFORE=$(find . -type d -name "__pycache__" 2>/dev/null | wc -l)

log_info "Cache files before: ${CACHE_COUNT_BEFORE} .pyc, ${PYCACHE_COUNT_BEFORE} __pycache__"

# .pyc 파일 삭제
find . -type f -name "*.pyc" -delete 2>/dev/null || true

# __pycache__ 폴더 삭제
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

CACHE_COUNT_AFTER=$(find . -type f -name "*.pyc" 2>/dev/null | wc -l)
PYCACHE_COUNT_AFTER=$(find . -type d -name "__pycache__" 2>/dev/null | wc -l)

log_success "Cleaned $(($CACHE_COUNT_BEFORE - $CACHE_COUNT_AFTER)) .pyc files"
log_success "Cleaned $(($PYCACHE_COUNT_BEFORE - $PYCACHE_COUNT_AFTER)) __pycache__ directories"

# ========================================
# 4. 서비스 재시작
# ========================================
echo ""
print_separator
log_info "[4/6] Restarting systemd service..."
print_separator

# 서비스 상태 확인 (재시작 전)
log_info "Service status before restart:"
systemctl status "${SERVICE_NAME}" --no-pager | head -5 || true

# 서비스 재시작
if systemctl restart "${SERVICE_NAME}"; then
    log_success "Service restart command executed"
else
    log_error "Failed to restart service"
    exit 1
fi

# 재시작 대기
log_info "Waiting for service to start..."
sleep 3

# ========================================
# 5. 서비스 상태 확인
# ========================================
echo ""
print_separator
log_info "[5/6] Verifying service status..."
print_separator

if systemctl is-active --quiet "${SERVICE_NAME}"; then
    log_success "Service is active"

    # 서비스 상태 출력
    systemctl status "${SERVICE_NAME}" --no-pager | head -10

    # 프로세스 확인
    echo ""
    log_info "Running processes:"
    ps aux | grep -E "[s]treamlit" || log_warning "No streamlit process found"
else
    log_error "Service is not active!"
    log_error "Service status:"
    systemctl status "${SERVICE_NAME}" --no-pager || true
    exit 1
fi

# ========================================
# 6. 로그 확인 (JITTER 값 검증)
# ========================================
echo ""
print_separator
log_info "[6/6] Checking logs..."
print_separator

# systemd 로그 확인
log_info "Recent systemd logs:"
journalctl -u "${SERVICE_NAME}" --no-pager -n 20 | tail -10

# streamlit 로그 확인 (JITTER 값)
if [ -f "${LOG_FILE}" ]; then
    echo ""
    log_info "Checking JITTER configuration:"

    # 최근 로그에서 JITTER 값 찾기
    JITTER_LOG=$(grep "실시간 루프" "${LOG_FILE}" | tail -1)

    if [ -n "${JITTER_LOG}" ]; then
        log_success "Found JITTER log:"
        echo "  ${JITTER_LOG}"

        # JITTER 값 추출
        if echo "${JITTER_LOG}" | grep -q "jitter=1.2"; then
            log_success "JITTER value is correct (1.2 seconds)"
        elif echo "${JITTER_LOG}" | grep -q "jitter=2.0"; then
            log_success "JITTER value is correct (2.0 seconds)"
        else
            log_warning "JITTER value may be incorrect"
            echo "  Expected: 1.2 or 2.0 seconds"
            echo "  Found: ${JITTER_LOG}"
        fi
    else
        log_warning "JITTER log not found yet (may take 1-2 minutes)"
    fi

    # 최근 에러 확인
    echo ""
    log_info "Checking for recent errors:"
    if grep -i "error\|exception\|failed" "${LOG_FILE}" | tail -5 > /dev/null 2>&1; then
        log_warning "Recent errors found:"
        grep -i "error\|exception\|failed" "${LOG_FILE}" | tail -5 | sed 's/^/  /'
    else
        log_success "No recent errors found"
    fi
else
    log_warning "Log file not found: ${LOG_FILE}"
fi

# ========================================
# 배포 완료
# ========================================
echo ""
print_separator
log_success "🎉 Deployment completed successfully!"
print_separator

# 요약 정보
echo ""
log_info "Summary:"
echo "  • Current commit: $(git rev-parse --short HEAD)"
echo "  • Service name: ${SERVICE_NAME}"
echo "  • Service status: $(systemctl is-active ${SERVICE_NAME})"
echo "  • Project dir: ${PROJECT_DIR}"
echo "  • Log file: ${LOG_FILE}"

echo ""
log_info "Useful commands:"
echo "  • View logs: journalctl -u ${SERVICE_NAME} -f"
echo "  • Check status: systemctl status ${SERVICE_NAME}"
echo "  • View streamlit log: tail -f ${LOG_FILE}"

echo ""
log_info "Verification (wait 2-3 minutes):"
echo "  1. Check dashboard: Settings Snapshot table"
echo "  2. Verify log interval: Should be ~60 seconds (1 minute)"
echo "  3. Check JITTER: Run 'journalctl -u ${SERVICE_NAME} -n 100 | grep jitter'"
