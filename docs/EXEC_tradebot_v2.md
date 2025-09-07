# FINAL CODE
# docs/EXEC_tradebot_v2.md

## 업비트 트레이드봇 MVP v2 실행 가이드

**버전**: v2.0  
**작성일**: 2025-09-07  
**대상**: 개발자 및 운영자  

---

## 1. 시스템 요구사항

### 1.1 최소 사양
- **OS**: macOS 10.15+, Ubuntu 18.04+, Windows 10+
- **Python**: 3.11 이상
- **RAM**: 4GB 이상 (권장 8GB+)
- **Storage**: 1GB 이상 여유 공간
- **Network**: 안정적인 인터넷 연결

### 1.2 필수 소프트웨어
```bash
# Python 3.11+
python --version
# pip
pip --version
# git
git --version
```

---

## 2. 설치 가이드

### 2.1 레포지토리 클론
```bash
git clone <repository-url>
cd upbit-tradebot-mvp
```

### 2.2 가상 환경 설정 (권장)
```bash
# 가상 환경 생성
python -m venv venv

# 가상 환경 활성화
# macOS/Linux
source venv/bin/activate
# Windows
venv\Scripts\activate
```

### 2.3 의존성 설치
```bash
# 기본 의존성 설치
pip install -r requirements.txt

# 테스트 의존성 설치 (선택사항)
pip install pytest pytest-cov psutil

# 개발 도구 설치 (선택사항)
pip install black flake8 mypy
```

### 2.4 환경 변수 설정
```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 편집
UPBIT_ACCESS=your_upbit_access_key
UPBIT_SECRET=your_upbit_secret_key
DB_URL=sqlite:///tradebot_default.db  # 또는 MySQL/PostgreSQL
```

---

## 3. 초기 설정

### 3.1 데이터베이스 초기화
```bash
# 자동 초기화 스크립트 실행
python services/init_db.py

# 또는 수동 초기화
python -c "
import sys
sys.path.append('.')
from services.init_db import initialize_database
from services.logger import LogManager
LogManager.setup_logging()
initialize_database()
print('✅ 데이터베이스 초기화 완료')
"
```

### 3.2 API 키 설정
```bash
# credentials.yaml 파일 생성
cp credentials.yaml.example credentials.yaml

# credentials.yaml 파일 편집
upbit:
  access: "your_upbit_access_key"
  secret: "your_upbit_secret_key"
```

### 3.3 설정 파일 확인
```python
# 설정 확인 테스트
python -c "
import sys
sys.path.append('.')
from services.logger import LogManager
LogManager.setup_logging()

# 환경변수 확인
import os
print(f'UPBIT_ACCESS: {\"✅\" if os.getenv(\"UPBIT_ACCESS\") else \"❌\"}')
print(f'UPBIT_SECRET: {\"✅\" if os.getenv(\"UPBIT_SECRET\") else \"❌\"}')

# DB 연결 확인
from services.db import get_db_manager
try:
    db = get_db_manager()
    print('✅ 데이터베이스 연결 성공')
except Exception as e:
    print(f'❌ 데이터베이스 연결 실패: {e}')
"
```

---

## 4. 애플리케이션 실행

### 4.1 개발 모드 실행
```bash
# Streamlit 개발 모드
streamlit run app.py

# 또는 특정 포트 지정
streamlit run app.py --server.port 8501

# 헤드리스 모드 (서버 환경)
streamlit run app.py --server.headless true --server.port 8501
```

### 4.2 프로덕션 모드 실행
```bash
# 포트 충돌 방지
lsof -ti:8501 | xargs kill -9

# 프로덕션 설정으로 실행
streamlit run app.py \
  --server.headless true \
  --server.port 8501 \
  --server.enableCORS=false \
  --server.maxUploadSize=200 \
  --browser.gatherUsageStats=false
```

### 4.3 백그라운드 실행 (Linux/macOS)
```bash
# 백그라운드 실행
nohup streamlit run app.py \
  --server.headless true \
  --server.port 8501 \
  > tradebot.log 2>&1 &

# 프로세스 확인
ps aux | grep streamlit

# 프로세스 종료
kill <pid>
```

---

## 5. 테스트 실행

### 5.1 전체 테스트 스위트
```bash
# 전체 테스트 실행
make test-all

# 또는
python tests/test_runner.py --test all --verbose

# 보고서 생성
make test-report
```

### 5.2 개별 테스트 실행
```bash
# 전략 테스트만 실행
make test-strategy

# 트레이더 테스트만 실행
make test-trader

# 엔진 테스트만 실행
make test-engine
```

### 5.3 pytest 사용 (선택사항)
```bash
# pytest 설치 후
pip install pytest pytest-cov

# pytest 실행
pytest tests/ -v

# 커버리지 확인
pytest tests/ --cov=tests --cov-report=html
```

---

## 6. 모니터링 및 관리

### 6.1 시스템 상태 확인
```bash
# 프로세스 상태 확인
ps aux | grep streamlit

# 포트 사용 확인
lsof -i :8501

# 메모리 사용량 확인
ps aux | grep streamlit | awk '{print $4}'

# 로그 확인
tail -f tradebot.log
```

### 6.2 데이터베이스 관리
```bash
# SQLite 데이터베이스 확인
ls -la *.db

# 데이터베이스 백업
cp tradebot_default.db tradebot_default_backup.db

# 로그 정리 (선택사항)
find logs/ -name "*.log" -mtime +7 -delete
```

### 6.3 성능 모니터링
```python
# 성능 모니터링 스크립트
python -c "
import psutil
import time

process = psutil.Process()
print('CPU 사용량:', process.cpu_percent())
print('메모리 사용량:', process.memory_info().rss / 1024 / 1024, 'MB')
print('스레드 수:', process.num_threads())
"
```

---

## 7. 문제 해결

### 7.1 일반적인 문제

#### 포트 충돌
```bash
# 포트 확인
lsof -i :8501

# 포트 종료
lsof -ti:8501 | xargs kill -9

# 다른 포트 사용
streamlit run app.py --server.port 8502
```

#### 임포트 에러
```bash
# Python 경로 확인
echo $PYTHONPATH

# 경로 추가 (임시)
export PYTHONPATH=$PYTHONPATH:$(pwd)

# 또는 스크립트 실행 시
PYTHONPATH=. python app.py
```

#### 데이터베이스 에러
```bash
# 데이터베이스 파일 삭제 후 재생성
rm -f *.db
python services/init_db.py

# 권한 문제 해결
chmod 755 *.db
```

### 7.2 API 관련 문제

#### API 키 오류
```bash
# 환경변수 확인
echo $UPBIT_ACCESS
echo $UPBIT_SECRET

# .env 파일 재로드
source .env
```

#### API 레이트 리밋
```bash
# 요청 간격 확인 (초당 10회 제한)
# 자동으로 재시도 로직이 구현되어 있음
# 수동으로 대기 시간 추가 필요
```

### 7.3 메모리 문제
```bash
# 메모리 사용량 모니터링
watch -n 1 'ps aux | grep streamlit'

# 메모리 누수 시 프로세스 재시작
lsof -ti:8501 | xargs kill -9
streamlit run app.py --server.headless true --server.port 8501 &
```

---

## 8. 배포 가이드

### 8.1 로컬 배포
```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경 설정
cp .env.example .env
# .env 파일 편집

# 3. 데이터베이스 초기화
python services/init_db.py

# 4. 애플리케이션 실행
streamlit run app.py --server.headless true --server.port 8501
```

### 8.2 서버 배포 (Ubuntu)
```bash
# 1. 시스템 업데이트
sudo apt update && sudo apt upgrade -y

# 2. Python 설치
sudo apt install python3 python3-pip python3-venv -y

# 3. 레포지토리 클론
git clone <repository-url>
cd upbit-tradebot-mvp

# 4. 가상 환경 설정
python3 -m venv venv
source venv/bin/activate

# 5. 의존성 설치
pip install -r requirements.txt

# 6. 환경 설정
cp .env.example .env
nano .env

# 7. 서비스 파일 생성
sudo nano /etc/systemd/system/tradebot.service
```

### 8.3 Systemd 서비스 설정
```ini
[Unit]
Description=Upbit TradeBot MVP
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/path/to/upbit-tradebot-mvp
Environment=PATH=/path/to/upbit-tradebot-mvp/venv/bin
ExecStart=/path/to/upbit-tradebot-mvp/venv/bin/streamlit run app.py --server.headless true --server.port 8501
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# 서비스 시작
sudo systemctl daemon-reload
sudo systemctl enable tradebot
sudo systemctl start tradebot

# 상태 확인
sudo systemctl status tradebot

# 로그 확인
sudo journalctl -u tradebot -f
```

---

## 9. 유지보수

### 9.1 정기적인 작업
```bash
# 주간 로그 정리
0 0 * * 0 find /path/to/logs -name "*.log" -mtime +7 -delete

# 월간 데이터베이스 백업
0 0 1 * * cp /path/to/tradebot.db /path/to/backups/tradebot_$(date +\%Y\%m\%d).db

# 시스템 모니터링
*/5 * * * * /path/to/monitoring_script.sh
```

### 9.2 업데이트 절차
```bash
# 1. 현재 버전 백업
cp -r upbit-tradebot-mvp upbit-tradebot-mvp-backup

# 2. 코드 업데이트
git pull origin main

# 3. 의존성 업데이트
pip install -r requirements.txt

# 4. 데이터베이스 마이그레이션
python services/init_db.py

# 5. 서비스 재시작
sudo systemctl restart tradebot
```

---

## 10. 보안 가이드

### 10.1 API 키 관리
- **절대로 코드에 API 키를 하드코딩하지 마세요**
- **환경 변수 또는 보안 저장소를 사용하세요**
- **주기적으로 API 키를 교체하세요**
- **IP 화이트리스트를 설정하세요**

### 10.2 서버 보안
```bash
# 방화벽 설정
sudo ufw enable
sudo ufw allow 8501/tcp
sudo ufw allow ssh

# SSH 키 기반 인증만 허용
sudo nano /etc/ssh/sshd_config
PasswordAuthentication no

# 시스템 업데이트
sudo apt update && sudo apt upgrade -y
```

### 10.3 데이터베이스 보안
```bash
# 데이터베이스 파일 권한 설정
chmod 600 *.db

# 정기적인 백업
crontab -e
0 2 * * * cp /path/to/tradebot.db /path/to/backups/tradebot_$(date +\%Y\%m\%d).db
```

---

## 11. 모니터링 대시보드

### 11.1 기본 모니터링
- **URL**: http://localhost:8501
- **시스템 상태**: CPU, 메모리, 디스크 사용량
- **엔진 상태**: 활성 엔진, 거래 상태
- **거래 내역**: 실시간 거래 기록

### 11.2 고급 모니터링
```bash
# 성능 모니터링 스크립트
python -c "
import psutil
import time
from datetime import datetime

def monitor_system():
    while True:
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        
        print(f'{datetime.now()} - CPU: {cpu}%, Memory: {memory}%, Disk: {disk}%')
        time.sleep(60)

monitor_system()
"
```

---

## 12. 연락처 및 지원

### 12.1 문제 보고
- **이슈 트래커**: GitHub Issues
- **버그 보고**: bug-reports@example.com
- **기능 요청**: feature-requests@example.com

### 12.2 문서
- **API 문서**: `/docs/api/`
- **사용자 가이드**: `/docs/user-guide/`
- **개발자 가이드**: `/docs/developer-guide/`

---

## 13. 부록

### 13.1 유용한 명령어
```bash
# Python 패키지 목록
pip list

# 가상 환경 목록
lsvirtualenv  # virtualenv-wrapper 사용 시

# 포트 스캔
nmap -p 8501 localhost

# 네트워크 연결 확인
netstat -tulpn | grep :8501

# 디스크 사용량
df -h

# 시스템 정보
uname -a
```

### 13.2 환경 변수 목록
```bash
# 필수 환경 변수
UPBIT_ACCESS=your_access_key
UPBIT_SECRET=your_secret_key
DB_URL=sqlite:///tradebot.db

# 선택적 환경 변수
LOG_LEVEL=INFO
MAX_MEMORY_USAGE=512
HEALTH_CHECK_INTERVAL=60
```

### 13.3 파일 구조
```
upbit-tradebot-mvp/
├── app.py                 # 메인 애플리케이션
├── config.py              # 설정 파일
├── requirements.txt       # 의존성 목록
├── .env.example          # 환경 변수 예시
├── credentials.yaml.example  # API 키 예시
├── services/              # 서비스 모듈
├── core/                  # 핵심 모듈
├── engine/                # 엔진 모듈
├── pages/                 # Streamlit 페이지
├── tests/                 # 테스트 코드
├── docs/                  # 문서
├── logs/                  # 로그 파일
└── *.db                  # 데이터베이스 파일
```

---

**실행 전 체크리스트:**

- [ ] Python 3.11+ 설치 확인
- [ ] 가상 환경 설정
- [ ] 의존성 설치 완료
- [ ] 환경 변수 설정 (.env)
- [ ] API 키 설정 (credentials.yaml)
- [ ] 데이터베이스 초기화
- [ ] 포트 가용성 확인 (8501)
- [ ] 방화벽 설정 (서버 환경)
- [ ] 백업 시스템 구성

이 가이드를 따라 업비트 트레이드봇 MVP v2를 성공적으로 실행하고 관리할 수 있습니다.