#!/usr/bin/env bash
set -euo pipefail

ROOT="$(pwd)"
echo "Project root: $ROOT"

# 0. 필수 확인
command -v python3 >/dev/null || { echo "Python3 필요"; exit 1; }
command -v git >/dev/null || { echo "git 필요"; exit 1; }

# 1. 구조 생성
mkdir -p orchestration/{agents,logs,config} dashboards/{static,templates,data} scripts .vscode
mkdir -p orchestration/agents/roles

# 2. 가상환경 + 패키지
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install aider-chat flask flask_socketio eventlet python-dotenv pyyaml pandas plotly

# 3. 예시 Config
cat > orchestration/config/config.yaml <<'YAML'
model: gpt-5-reasoning
aider:
  bin: aider
  opts: []
loop:
  max_loops: 100
  loop_interval_sec: 30
  min_improvement_sec: 0.01
  auto_commit: false     # 원하면 true
bench:
  # 프로젝트에 맞게 명령 갱신하세요.
  commands:
    - name: "unit-perf"
      cmd: "pytest -q -k perf || true"
    - name: "paper-trade"
      cmd: "python -m orchestration.benchmarks --scenario paper || true"
    - name: "latency"
      cmd: "python -m orchestration.benchmarks --scenario latency || true"
YAML

# 4. 역할 프롬프트(모두 동일 모델 사용)
cat > orchestration/agents/roles/architect.md <<'MD'
너는 시스템 아키텍트다. 트레이딩 봇의 병목/지연/메모리/네트워크/DB/동시성 관점에서 개선 아이디어를 제시하고, 각 역할에 명확히 전달하라. 변경 시 벤치 기준을 업데이트하도록 지시하라.
MD

cat > orchestration/agents/roles/trading.md <<'MD'
너는 트레이딩 로직 담당 엔지니어다. 시그널 계산, 주문 큐, 슬리피지/리트라이/백오프/윈도우 최적화, 백테스트 가속을 수행하라. 안전장치(손절/노에러 실패 안전)도 강화하라.
MD

cat > orchestration/agents/roles/data.md <<'MD'
너는 데이터/DB/ETL 담당이다. 캔들/오더북 수집 파이프라인, 캐시 정책, 인덱스, 배치/스트림 분리, 스키마 진화, I/O 병렬화를 최적화하라.
MD

cat > orchestration/agents/roles/infra.md <<'MD'
너는 인프라/운영 담당이다. 로깅/모니터링, 알림, 설정/시크릿(.env), 컨테이너/배포 스크립트, 리소스 제한, 장애 시 롤백 전략을 개선하라.
MD

cat > orchestration/agents/roles/qa.md <<'MD'
너는 QA/검증 담당이다. 벤치마크 로그를 분석하고 회귀/개선 판단, 위험/안전 이슈를 요약해 Architect에게 전달하라. 거짓 양성/음성 최소화를 목표로 한다.
MD

# 5. .env 로더
cat > scripts/export_env.sh <<'BASH'
#!/usr/bin/env bash
set -a
[ -f .env ] && source .env
set +a
echo "OPENAI_API_KEY=${OPENAI_API_KEY:+(loaded)}"
BASH
chmod +x scripts/export_env.sh

# 6. 벤치마크 (실제 실행시간 측정 기반)
cat > orchestration/benchmarks.py <<'PY'
import argparse, time, subprocess, requests

def run_backtest():
    t0 = time.time()
    result = subprocess.run(
        ["python", "engine/engine_runner.py", "--mode", "backtest", "--days", "30"],
        capture_output=True, text=True
    )
    dur = time.time() - t0
    print(result.stdout)
    print(f"[benchmark] backtest took {dur:.3f}s")
    return dur

def run_live_loop():
    t0 = time.time()
    result = subprocess.run(
        ["python", "engine/live_loop.py", "--test", "--steps", "100"],
        capture_output=True, text=True
    )
    dur = time.time() - t0
    print(result.stdout)
    print(f"[benchmark] live-loop took {dur:.3f}s")
    return dur

def run_latency():
    url = "https://api.upbit.com/v1/ticker?markets=KRW-BTC"
    t0 = time.time()
    r = requests.get(url, timeout=5)
    dur = time.time() - t0
    print(f"[benchmark] latency={dur:.3f}s status={r.status_code}")
    return dur

def run_paper():
    # paper-trade 는 backtest로 대체 (필요시 수정 가능)
    return run_backtest()

def run_scenario(name: str) -> float:
    if name == "backtest":
        return run_backtest()
    elif name == "live-loop":
        return run_live_loop()
    elif name == "latency":
        return run_latency()
    elif name == "paper":
        return run_paper()
    else:
        print(f"[benchmark] unknown scenario: {name}")
        return 0.0

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="paper")
    args = ap.parse_args()
    run_scenario(args.scenario)
PY

# 7. 오케스트레이터(에이전트 멀티롤 + 대시보드 스트림 + 로그 + 개선판단)
cat > orchestration/multi_agent_runner.py <<'PY'
#!/usr/bin/env python3
import os, json, time, subprocess, yaml, shlex
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "orchestration" / "logs"
STATE_FILE = ROOT / "dashboards" / "data" / "state.json"
HIST_FILE = ROOT / "dashboards" / "data" / "history.jsonl"
ROLES_DIR = ROOT / "orchestration" / "agents" / "roles"
CONFIG = ROOT / "orchestration" / "config" / "config.yaml"

LOG_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / ".env")

def load_config():
    with open(CONFIG) as f: return yaml.safe_load(f)

def call_aider(role_name:str, prompt:str, model:str, bin_path:str="aider", extra_opts:list[str]|None=None)->str:
    sys_path = ROLES_DIR / f"{role_name}.md"
    if not sys_path.exists():
        return f"[{role_name}] role prompt missing"
    system_prompt = sys_path.read_text()
    cmd = [bin_path, "--model", model, "--system", system_prompt]
    if extra_opts: cmd += extra_opts
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = proc.communicate(prompt)
    if err: out += f"\n[stderr]\n{err}"
    return out.strip()

def run_bench_all(bench_cfg:dict)->dict:
    results = {}
    for item in bench_cfg.get("commands", []):
        name, cmd = item["name"], item["cmd"]
        t0 = time.time()
        try:
            subprocess.run(cmd, shell=True, check=False, capture_output=True, text=True)
            dur = time.time() - t0
        except Exception as e:
            dur = None
        results[name] = round(dur, 3) if dur is not None else None
    return results

def git_commit(msg:str):
    try:
        subprocess.run("git add -A", shell=True, check=True)
        subprocess.run(shlex.split(f'git commit -m {json.dumps(msg)}'), check=True)
        print("✅ git committed")
    except subprocess.CalledProcessError:
        print("ℹ️ no changes to commit")

def main():
    cfg = load_config()
    model = cfg["model"]
    aider_bin = cfg["aider"]["bin"]
    aider_opts = cfg["aider"].get("opts", [])
    loop_cfg = cfg["loop"]
    bench_cfg = cfg["bench"]

    prev_total = None
    for i in range(1, loop_cfg["max_loops"] + 1):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n=== LOOP #{i} @ {ts} ===")
        state = {"loop": i, "timestamp": ts, "agents": {}, "bench": {}, "model": model}

        # 1) 아이디어 수집/수행
        state["agents"]["architect"] = call_aider("architect", "트레이딩봇 전반 성능/안정성 개선안을 내고 각 역할에게 구체 지시를 써줘.", model, aider_bin, aider_opts)
        state["agents"]["trading"]   = call_aider("trading",   "핵심 트레이딩 루프/주문 처리/시그널 경로 최적화 코드를 제안/갱신해줘.", model, aider_bin, aider_opts)
        state["agents"]["data"]      = call_aider("data",      "데이터/DB/캐시/ETL의 병목 제거 및 인덱스/파티셔닝/캐시 전략을 제안/갱신해줘.", model, aider_bin, aider_opts)
        state["agents"]["infra"]     = call_aider("infra",     "로깅/모니터링/알림/설정 관리 개선과 장애 복구 전략을 갱신해줘.", model, aider_bin, aider_opts)

        # 2) 벤치 실행(프로젝트 맞게 bench.commands 수정)
        bench = run_bench_all(bench_cfg)
        state["bench"] = bench

        # 3) QA 판단
        qa_input = "다음 벤치 결과로 회귀/개선을 판단하고 아키텍트에게 요약 피드백:\n" + json.dumps(bench, ensure_ascii=False)
        state["agents"]["qa"] = call_aider("qa", qa_input, model, aider_bin, aider_opts)

        # 4) 개선/종료 판단
        total = sum([v for v in bench.values() if isinstance(v, (int, float))]) if bench else None
        state["total_bench_sec"] = total
        with open(HIST_FILE, "a", encoding="utf-8") as hf:
            hf.write(json.dumps(state, ensure_ascii=False) + "\n")
        with open(STATE_FILE, "w", encoding="utf-8") as sf:
            json.dump(state, sf, ensure_ascii=False, indent=2)

        if loop_cfg.get("auto_commit", False):
            git_commit(f"loop #{i}: bench={bench}")

        if prev_total is not None and total is not None:
            if (prev_total - total) < loop_cfg["min_improvement_sec"]:
                print("⚠️ 개선 미미 → 루프 종료")
                break
        prev_total = total
        time.sleep(loop_cfg["loop_interval_sec"])

if __name__ == "__main__":
    main()
PY
chmod +x orchestration/multi_agent_runner.py

# 8. 대시보드(Flask + Socket.IO + Plotly)
cat > dashboards/app.py <<'PY'
from flask import Flask, jsonify, render_template, send_from_directory
from flask_socketio import SocketIO
import json, os, time, threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "dashboards" / "data"
STATE = DATA_DIR / "state.json"
HIST = DATA_DIR / "history.jsonl"

app = Flask(__name__, template_folder="templates", static_folder="static")
socketio = SocketIO(app, cors_allowed_origins="*")

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/state")
def api_state():
    if STATE.exists():
        return send_from_directory(DATA_DIR, "state.json")
    return jsonify({})

@app.route("/api/history")
def api_history():
    rows = []
    if HIST.exists():
        with open(HIST, "r", encoding="utf-8") as f:
            for line in f:
                try: rows.append(json.loads(line))
                except: pass
    return jsonify(rows)

def watcher():
    mtime = 0
    while True:
        try:
            cur = STATE.stat().st_mtime if STATE.exists() else 0
            if cur > mtime:
                mtime = cur
                with open(STATE, "r", encoding="utf-8") as f:
                    socketio.emit("state", json.load(f))
        except: pass
        time.sleep(1)

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=watcher, daemon=True).start()
    socketio.run(app, port=5000)

if __name__ == "__main__":
    main()
PY

# 8-1. 대시보드 템플릿/정적파일
cat > dashboards/templates/index.html <<'HTML'
<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>Tradebot Multi-Agent Dashboard</title>
<script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
<script src="https://cdn.plot.ly/plotly-2.32.0.min.js"></script>
<style>
body{font-family:ui-sans-serif,system-ui,Segoe UI,Roboto,Apple Color Emoji,Segoe UI Emoji;margin:20px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{border:1px solid #eee;border-radius:12px;padding:14px;box-shadow:0 1px 4px rgba(0,0,0,.04)}
.pre{white-space:pre-wrap;background:#fafafa;border:1px solid #eee;border-radius:8px;padding:8px;max-height:320px;overflow:auto}
.badge{display:inline-block;padding:2px 6px;border-radius:8px;background:#eee;margin-right:6px}
</style>
</head>
<body>
<h2>Upbit Tradebot – Multi-Agent Dashboard</h2>
<div class="grid">
  <div class="card">
    <div id="perf" style="height:320px;"></div>
  </div>
  <div class="card">
    <div><span class="badge">Loop</span><span id="loop">-</span> <span class="badge">Model</span><span id="model">-</span> <span class="badge">Time</span><span id="ts">-</span></div>
    <div id="bench" class="pre"></div>
  </div>
  <div class="card">
    <h4>Architect</h4>
    <div id="architect" class="pre"></div>
  </div>
  <div class="card">
    <h4>Trading</h4>
    <div id="trading" class="pre"></div>
  </div>
  <div class="card">
    <h4>Data</h4>
    <div id="data" class="pre"></div>
  </div>
  <div class="card">
    <h4>Infra</h4>
    <div id="infra" class="pre"></div>
  </div>
  <div class="card">
    <h4>QA</h4>
    <div id="qa" class="pre"></div>
  </div>
</div>

<script>
const socket = io();
let historyX=[], perfSeries={};

function renderPerf(){
  const traces = Object.keys(perfSeries).map(k=>({name:k, x:historyX, y:perfSeries[k], type:'scatter'}));
  Plotly.newPlot('perf', traces, {title:'Bench (sec, lower is better)'});
}
function pushBench(loop, bench){
  historyX.push(loop);
  Object.entries(bench||{}).forEach(([k,v])=>{
    if(!perfSeries[k]) perfSeries[k]=[];
    perfSeries[k].push(v ?? null);
  });
  renderPerf();
}
function setText(id, txt){ document.getElementById(id).textContent = txt ?? ''; }

async function init(){
  const hist = await fetch('/api/history').then(r=>r.json());
  hist.forEach(s=>{
    pushBench(s.loop, s.bench);
  });
  socket.on('state', s=>{
    setText('loop', s.loop);
    setText('model', s.model);
    setText('ts', s.timestamp);
    document.getElementById('bench').textContent = JSON.stringify(s.bench, null, 2);
    ['architect','trading','data','infra','qa'].forEach(k=>{
      document.getElementById(k).textContent = s.agents?.[k] ?? '';
    });
    pushBench(s.loop, s.bench);
  });
}
init();
</script>
</body>
</html>
HTML

# 9. VS Code Task/Launch
cat > .vscode/tasks.json <<'JSON'
{
  "version": "2.0.0",
  "tasks": [
    { "label": "Run Dashboard", "type": "shell", "command": "${workspaceFolder}/.venv/bin/python", "args": ["${workspaceFolder}/dashboards/app.py"], "presentation": {"reveal":"always","panel":"shared"} },
    { "label": "Run Multi-Agent Loop", "type": "shell", "command": "${workspaceFolder}/.venv/bin/python", "args": ["${workspaceFolder}/orchestration/multi_agent_runner.py"], "options": { "env": { "OPENAI_API_KEY": "${env:OPENAI_API_KEY}" } }, "presentation": {"reveal":"always","panel":"shared"} }
  ]
}
JSON

cat > .vscode/launch.json <<'JSON'
{
  "version": "0.2.0",
  "configurations": [
    { "name": "Dashboard", "type": "python", "request": "launch", "program": "${workspaceFolder}/dashboards/app.py", "console": "integratedTerminal" },
    { "name": "Multi-Agent Loop", "type": "python", "request": "launch", "program": "${workspaceFolder}/orchestration/multi_agent_runner.py", "console": "integratedTerminal", "env": { "OPENAI_API_KEY": "${env:OPENAI_API_KEY}" } }
  ]
}
JSON

# 10. Makefile(편의)
cat > Makefile <<'MK'
venv:
	python3 -m venv .venv && . .venv/bin/activate

env:
	source scripts/export_env.sh

dashboard:
	. scripts/export_env.sh && ./.venv/bin/python dashboards/app.py

loop:
	. scripts/export_env.sh && ./.venv/bin/python orchestration/multi_agent_runner.py
MK

echo "✅ Install complete. Next:"
echo "   1) source scripts/export_env.sh   # .env 로드"
echo "   2) make dashboard                 # http://localhost:5000"
echo "   3) make loop                      # 오케스트레이터 실행"
