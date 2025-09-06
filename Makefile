PY ?= python3   # 파이썬 실행기 기본값 (M2 맥북은 python3 권장)

.PHONY: insights
insights:
	$(PY) tools/gen_repo_insights.py
