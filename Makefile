PY ?= python3   # 파이썬 실행기 기본값 (M2 맥북은 python3 권장)

.PHONY: insights test test-all test-strategy test-trader test-engine test-clean test-report help

# 인사이트 생성
insights:
	$(PY) tools/gen_repo_insights.py

# 테스트 관련
test-all:
	@echo "🧪 전체 테스트 스위트 실행"
	@$(PY) tests/test_runner.py --test all --verbose --report test_report.md

test-strategy:
	@echo "🎯 전략 테스트 실행"
	@$(PY) tests/test_runner.py --test strategy --verbose

test-trader:
	@echo "💰 트레이더 테스트 실행"
	@$(PY) tests/test_runner.py --test trader --verbose

test-engine:
	@echo "⚙️  엔진 테스트 실행"
	@$(PY) tests/test_runner.py --test engine --verbose

test-unit:
	@echo "🔬 단위 테스트 실행 (unittest)"
	@$(PY) -m unittest discover tests -v

test-pytest:
	@echo "🐍 pytest 실행"
	@which pytest > /dev/null 2>&1 && pytest tests -v || echo "pytest가 설치되지 않았습니다. pip install pytest로 설치해주세요."

test-coverage:
	@echo "📊 테스트 커버리지 확인"
	@which pytest > /dev/null 2>&1 && pytest tests --cov=tests --cov-report=html --cov-report=term || echo "pytest와 pytest-cov가 필요합니다."

test-clean:
	@echo "🧹 테스트 결과 정리"
	@find . -name "*.pyc" -delete
	@find . -name "__pycache__" -type d -exec rm -rf {} +
	@find . -name ".pytest_cache" -type d -exec rm -rf {} +
	@find . -name "htmlcov" -type d -exec rm -rf {} +
	@rm -f .coverage
	@rm -f test_report.md

test-report:
	@echo "📄 테스트 보고서 생성"
	@$(PY) tests/test_runner.py --test all --report test_report.md
	@echo "✅ 보고서가 test_report.md에 생성되었습니다."

# 개발 환경 설정
setup-test:
	@echo "🔧 테스트 환경 설정"
	@pip install -r requirements.txt
	@pip install pytest pytest-cov psutil
	@mkdir -p tests/logs
	@mkdir -p tests/data

# 도움말
help:
	@echo "📖 사용 가능한 명령어:"
	@echo ""
	@echo "인사이트:"
	@echo "  insights         - 레포지토리 인사이트 생성"
	@echo ""
	@echo "테스트 실행:"
	@echo "  test-all         - 전체 테스트 스위트 실행"
	@echo "  test-strategy    - 전략 테스트만 실행"
	@echo "  test-trader      - 트레이더 테스트만 실행"
	@echo "  test-engine      - 엔진 테스트만 실행"
	@echo "  test-unit        - unittest로 모든 테스트 실행"
	@echo "  test-pytest      - pytest로 테스트 실행"
	@echo "  test-coverage    - 테스트 커버리지 확인"
	@echo ""
	@echo "유틸리티:"
	@echo "  test-clean       - 테스트 결과 정리"
	@echo "  test-report      - 테스트 보고서 생성"
	@echo "  setup-test       - 테스트 환경 설정"
	@echo "  help             - 이 도움말 표시"
	@echo ""
	@echo "사용 예시:"
	@echo "  make test-all"
	@echo "  make test-strategy"
	@echo "  make test-clean && make test-all"
