# 1030-09: 이 패키지 시험을 불러오면 바깥 연결(업비트 등) 차단을 켠다 — 게이트 밖 단독 실행 포함
from tests._netguard import activate as _netguard_activate
_netguard_activate()
