# FINAL CODE
# ui/style.py

style_main = """
<style>
/* ────────────────────────────────────────────────
   🔒 Streamlit 사이드바 완전 숨김
   (data-testid 선택자를 쓰면 버전 변동에 가장 안전함)
──────────────────────────────────────────────── */
[data-testid="stSidebar"],          /* 사이드바 컨테이너 */
[data-testid="stSidebarNav"] {      /* 내비 항목 */
    display: none !important;
}

/* 사이드바가 사라져도 남을 수 있는 left-margin 제거 */
.css-1d391kg { margin-left: 0rem !important; }

[data-testid="stMainBlockContainer"] { max-width: 80rem; }

/* ────────────────────────────────────────────────
   메트릭 카드 스타일 개선
──────────────────────────────────────────────── */
[data-testid="stMetric"] {
    background-color: var(--background-color);
    border-radius: 0.5em;
    padding: 1em;
    margin: 0.5em 0;
    color: var(--text-color);
    border: 1px solid #44444422;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    transition: transform 0.2s, box-shadow 0.2s;
}

[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

/* 라이트모드 */
@media (prefers-color-scheme: light) {
  [data-testid="stMetric"] {
    background-color: #f7f7f7;
    color: #222;
    border: 1px solid #e1e4e8;
  }
}

/* 다크모드 */
@media (prefers-color-scheme: dark) {
  [data-testid="stMetric"] {
    background-color: #22272b;
    color: #f7f7f7;
    border: 1px solid #444c56;
  }
}

/* ────────────────────────────────────────────────
   테이블 스타일 개선
──────────────────────────────────────────────── */
[data-testid="stDataFrame"] {
    border-radius: 0.5rem;
    overflow: hidden;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

[data-testid="stDataFrame"] table {
    border-collapse: collapse;
    width: 100%;
    font-size: 0.9rem;
}

[data-testid="stDataFrame"] th {
    background-color: #f8f9fa;
    color: #495057;
    font-weight: 600;
    padding: 0.75rem;
    text-align: left;
    border-bottom: 2px solid #dee2e6;
}

[data-testid="stDataFrame"] td {
    padding: 0.75rem;
    border-bottom: 1px solid #e9ecef;
    vertical-align: middle;
}

[data-testid="stDataFrame"] tr:hover {
    background-color: #f8f9fa;
}

/* ────────────────────────────────────────────────
   버튼 스타일 개선
──────────────────────────────────────────────── */
div.stButton > button, div.stForm > form > button {
    height: 60px !important;
    font-size: 30px !important;
    font-weight: 900 !important;
    border-radius: 0.5rem !important;
    border: none !important;
    background: linear-gradient(135deg, #4e9af1 0%, #3a7ac9 100%) !important;
    color: white !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 4px 15px rgba(78, 154, 241, 0.3) !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
}

div.stButton > button:hover, div.stForm > form > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 20px rgba(78, 154, 241, 0.4) !important;
    background: linear-gradient(135deg, #3a7ac9 0%, #2e5fa3 100%) !important;
}

div.stButton > button:active, div.stForm > form > button:active {
    transform: translateY(0) !important;
    box-shadow: 0 2px 10px rgba(78, 154, 241, 0.2) !important;
}

/* 성공 버튼 */
div.stButton > button[data-testid="baseButton-secondary"] {
    background: linear-gradient(135deg, #28a745 0%, #20c997 100%) !important;
    box-shadow: 0 4px 15px rgba(40, 167, 69, 0.3) !important;
}

div.stButton > button[data-testid="baseButton-secondary"]:hover {
    background: linear-gradient(135deg, #20c997 0%, #17a2b8 100%) !important;
    box-shadow: 0 6px 20px rgba(40, 167, 69, 0.4) !important;
}

/* 경고 버튼 */
div.stButton > button[data-testid="baseButton-secondary"]:nth-of-type(2) {
    background: linear-gradient(135deg, #ffc107 0%, #fd7e14 100%) !important;
    box-shadow: 0 4px 15px rgba(255, 193, 7, 0.3) !important;
}

div.stButton > button[data-testid="baseButton-secondary"]:nth-of-type(2):hover {
    background: linear-gradient(135deg, #fd7e14 0%, #e83e8c 100%) !important;
    box-shadow: 0 6px 20px rgba(255, 193, 7, 0.4) !important;
}

/* ────────────────────────────────────────────────
   입력 필드 스타일 개선
──────────────────────────────────────────────── */
.stTextInput > div > div > input {
    border-radius: 0.5rem !important;
    border: 2px solid #e9ecef !important;
    padding: 0.75rem 1rem !important;
    font-size: 1rem !important;
    transition: all 0.3s ease !important;
}

.stTextInput > div > div > input:focus {
    border-color: #4e9af1 !important;
    box-shadow: 0 0 0 3px rgba(78, 154, 241, 0.1) !important;
}

.stSelectbox > div > div > select {
    border-radius: 0.5rem !important;
    border: 2px solid #e9ecef !important;
    padding: 0.75rem 1rem !important;
    font-size: 1rem !important;
    transition: all 0.3s ease !important;
}

.stSelectbox > div > div > select:focus {
    border-color: #4e9af1 !important;
    box-shadow: 0 0 0 3px rgba(78, 154, 241, 0.1) !important;
}

/* ────────────────────────────────────────────────
   슬라이더 스타일 개선
──────────────────────────────────────────────── */
.stSlider > div > div > div > div {
    background: linear-gradient(90deg, #4e9af1 0%, #3a7ac9 100%) !important;
    border-radius: 1rem !important;
    height: 8px !important;
}

.stSlider > div > div > div > div:hover {
    background: linear-gradient(90deg, #3a7ac9 0%, #2e5fa3 100%) !important;
}

/* ────────────────────────────────────────────────
   확장 패널 스타일 개선
──────────────────────────────────────────────── */
.streamlit-expanderHeader {
    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%) !important;
    border-radius: 0.5rem !important;
    border: 1px solid #dee2e6 !important;
    margin-bottom: 0.5rem !important;
    transition: all 0.3s ease !important;
}

.streamlit-expanderHeader:hover {
    background: linear-gradient(135deg, #e9ecef 0%, #dee2e6 100%) !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
}

.streamlit-expanderContent {
    border-radius: 0 0 0.5rem 0.5rem !important;
    border: 1px solid #dee2e6 !important;
    border-top: none !important;
    background-color: #ffffff !important;
}

/* ────────────────────────────────────────────────
   상태 메시지 스타일 개선
──────────────────────────────────────────────── */
.element-container .stAlert {
    border-radius: 0.5rem !important;
    border: none !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
    margin: 1rem 0 !important;
}

.element-container .stSuccess {
    background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%) !important;
    color: #155724 !important;
    border-left: 4px solid #28a745 !important;
}

.element-container .stInfo {
    background: linear-gradient(135deg, #d1ecf1 0%, #bee5eb 100%) !important;
    color: #0c5460 !important;
    border-left: 4px solid #17a2b8 !important;
}

.element-container .stWarning {
    background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%) !important;
    color: #856404 !important;
    border-left: 4px solid #ffc107 !important;
}

.element-container .stError {
    background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%) !important;
    color: #721c24 !important;
    border-left: 4px solid #dc3545 !important;
}

/* ────────────────────────────────────────────────
   실시간 업데이트 애니메이션
──────────────────────────────────────────────── */
@keyframes pulse {
    0% { opacity: 1; }
    50% { opacity: 0.7; }
    100% { opacity: 1; }
}

.live-indicator {
    animation: pulse 2s infinite;
    color: #00ff00;
    font-weight: bold;
}

/* ────────────────────────────────────────────────
   카드 스타일 개선
──────────────────────────────────────────────── */
.status-card {
    background-color: #f8f9fa;
    border-radius: 0.5rem;
    padding: 1rem;
    margin: 0.5rem 0;
    border: 1px solid #dee2e6;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    transition: transform 0.2s, box-shadow 0.2s;
}

.status-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.15);
}

.warning-box {
    background-color: #fff3cd;
    border: 1px solid #ffeaa7;
    border-radius: 0.5rem;
    padding: 1.5rem;
    margin: 1rem 0;
}

.danger-box {
    background-color: #f8d7da;
    border: 1px solid #f5c6cb;
    border-radius: 0.5rem;
    padding: 1.5rem;
    margin: 1rem 0;
}

.success-box {
    background-color: #d4edda;
    border: 1px solid #c3e6cb;
    border-radius: 0.5rem;
    padding: 1.5rem;
    margin: 1rem 0;
}

/* ────────────────────────────────────────────────
   기존 스타일 호환성
──────────────────────────────────────────────── */
.header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 0;
    background: #f8f9fa;
    border-bottom: 1px solid #e9ecef;
    margin-bottom: 2rem;
}
.header input {
    flex-grow: 1;
    margin: 0 1.25rem;
    padding: 0.9rem;
    border: 1px solid #ced4da;
    border-radius: 0.5rem;
    background: #fff;
    font-size: 1.2rem;
    font-weight: 500;
    box-shadow: 0 1px 2px rgba(0,0,0,0.05);
    transition: border-color 0.2s, box-shadow 0.2s;
}
.header input:focus {
    border-color: #4e9af1;
    box-shadow: 0 0 0 0.2rem rgba(78,154,241,0.25);
    outline: none;
}
.header a {
    margin-left: 1rem;
    color: #4e9af1;
    text-decoration: none;
    font-weight: 500;
    font-size: 1.2rem;
}
.footer {
    text-align: center;
    padding: 1.8rem 0;
    margin-top: 2.4rem;
    background: #f8f9fa;
    border-top: 1px solid #e9ecef;
    color: #6c757d;
    font-size: 1.08rem;
    font-weight: 500;
}
.site-card {
    border: 1px solid #e9ecef;
    border-radius: 0.8rem;
    padding: 1.8rem;
    text-align: center;
    background: #fff;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    transition: box-shadow 0.3s, transform 0.2s;
    margin-top: 1.8rem;
}
.site-card:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.1);
    transform: translateY(-2px);
}
.site-icon {
    width: 4.8rem;
    height: 4.8rem;
    margin: 0 auto;
    border-radius: 50%;
    background: #f1f8ff;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #4e9af1;
    font-size: 2.16rem;
    font-weight: 600;
}
.site-name {
    font-size: 1.8rem;
    margin: 1.2rem 0;
    color: #212529;
    font-weight: 700;
}
.site-description {
    font-size: 1.2rem;
    color: #6c757d;
    margin-bottom: 1.8rem;
    font-weight: 500;
}
.site-link,
.site-link:link,
.site-link:visited,
.site-link:hover,
.site-link:active {
    display: inline-block;
    margin-top: 1.2rem;
    padding: 0.9rem 1.8rem;
    background-color: #4e9af1;
    color: #fff;
    text-decoration: none !important;
    border-radius: 0.6rem;
    font-weight: 600;
    font-size: 1.2rem;
    transition: background-color 0.2s, transform 0.2s;
}
.site-link:hover {
    background-color: #3a7ac9;
    transform: translateY(-1px);
}

/* --------- 반응형 --------- */
@media (max-width: 48rem) {
    .header { flex-direction: column; padding: 1.2rem 0; }
    .header input { margin: 0.6rem 0; width: 90%; }
    .site-card { padding: 1.2rem; margin-top: 1.2rem; }
    .site-name { font-size: 1.44rem; }
    .site-description { font-size: 1.08rem; }
    .site-link { padding: 0.72rem 1.44rem; }
}
@media (max-width: 30rem) {
    .header { padding: 0.96rem 0; }
    .site-card { padding: 0.96rem; margin-top: 0.96rem; }
    .site-name { font-size: 1.2rem; }
    .site-description { font-size: 0.96rem; }
    .site-link { padding: 0.6rem 1.2rem; }
}
</style>
"""
