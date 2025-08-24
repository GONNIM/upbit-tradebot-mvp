"""
🏥 24시간 운영: 헬스 체크 및 모니터링 시스템
엔진 상태 추적, 자동 복구, 성능 모니터링
"""

import threading
import time
import logging
import psutil
import os
from typing import Dict, Optional
from datetime import datetime, timedelta
from services.db import insert_log
from engine.global_state import get_engine_threads, is_engine_really_running

logger = logging.getLogger(__name__)


class HealthMonitor:
    """
    🔍 24시간 안정성: 시스템 헬스 모니터링 및 자동 복구
    """
    
    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval
        self.monitoring = False
        self.monitor_thread = None
        self._lock = threading.Lock()
        
        # 📊 성능 메트릭 저장
        self.metrics = {
            'last_check_time': None,
            'memory_usage_mb': 0,
            'cpu_usage_percent': 0,
            'active_engines': 0,
            'failed_checks': 0,
            'uptime_hours': 0,
        }
        
        self.start_time = time.time()
        
    def start_monitoring(self):
        """모니터링 시작"""
        with self._lock:
            if self.monitoring:
                return False
                
            self.monitoring = True
            self.monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="health_monitor"
            )
            self.monitor_thread.start()
            logger.info("🏥 헬스 모니터링 시작됨")
            return True
    
    def stop_monitoring(self):
        """모니터링 중단"""
        with self._lock:
            self.monitoring = False
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=5)
            logger.info("🏥 헬스 모니터링 중단됨")
    
    def _monitor_loop(self):
        """메인 모니터링 루프"""
        while self.monitoring:
            try:
                self._perform_health_check()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"❌ 헬스 체크 실패: {e}")
                time.sleep(self.check_interval * 2)  # 에러 시 2배 대기
    
    def _perform_health_check(self):
        """
        🔍 종합 헬스 체크 수행
        """
        check_time = datetime.now()
        
        try:
            # 📊 시스템 리소스 체크
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            cpu_percent = process.cpu_percent(interval=1)
            
            # 🔧 엔진 상태 체크
            engine_threads = get_engine_threads()
            active_engines = len([t for t in engine_threads.values() 
                                if t.get('thread', {}).is_alive()])
            
            # 📈 메트릭 업데이트
            self.metrics.update({
                'last_check_time': check_time,
                'memory_usage_mb': memory_mb,
                'cpu_usage_percent': cpu_percent,
                'active_engines': active_engines,
                'uptime_hours': (time.time() - self.start_time) / 3600,
                'failed_checks': 0,  # 성공 시 리셋
            })
            
            # 🚨 임계치 체크 및 알림
            self._check_critical_thresholds(memory_mb, cpu_percent, active_engines)
            
            # 📝 주기적 상태 로그 (5분마다)
            if int(time.time()) % 300 < self.check_interval:
                self._log_system_status()
            
        except Exception as e:
            self.metrics['failed_checks'] += 1
            logger.error(f"❌ 헬스 체크 에러: {e}")
            
            # 연속 실패 시 알림
            if self.metrics['failed_checks'] >= 3:
                self._alert_critical_failure()
    
    def _check_critical_thresholds(self, memory_mb: float, cpu_percent: float, active_engines: int):
        """
        🚨 임계치 모니터링 및 경고
        """
        warnings = []
        
        # 메모리 사용량 체크 (500MB 초과)
        if memory_mb > 500:
            warnings.append(f"높은 메모리 사용량: {memory_mb:.1f}MB")
        
        # CPU 사용량 체크 (80% 초과)
        if cpu_percent > 80:
            warnings.append(f"높은 CPU 사용량: {cpu_percent:.1f}%")
        
        # 활성 엔진 체크 (0개면 문제)
        if active_engines == 0:
            warnings.append("활성 엔진 없음 - 매매 중단 상태")
        
        # 경고 발생 시 로그 및 알림
        for warning in warnings:
            logger.warning(f"⚠️ {warning}")
            # 모든 사용자에게 시스템 경고 로그 추가
            for user_id in self._get_all_user_ids():
                insert_log(user_id, "WARNING", f"시스템 경고: {warning}")
    
    def _log_system_status(self):
        """
        📊 시스템 상태 주기적 로그
        """
        status_msg = (
            f"🏥 시스템 상태: "
            f"메모리 {self.metrics['memory_usage_mb']:.1f}MB, "
            f"CPU {self.metrics['cpu_usage_percent']:.1f}%, "
            f"활성엔진 {self.metrics['active_engines']}개, "
            f"가동시간 {self.metrics['uptime_hours']:.1f}h"
        )
        logger.info(status_msg)
        
        # 모든 사용자에게 상태 정보 로그
        for user_id in self._get_all_user_ids():
            insert_log(user_id, "INFO", status_msg)
    
    def _alert_critical_failure(self):
        """
        🚨 치명적 실패 알림
        """
        alert_msg = f"🚨 시스템 치명적 오류: 헬스체크 {self.metrics['failed_checks']}회 연속 실패"
        logger.critical(alert_msg)
        
        # 모든 사용자에게 치명적 알림
        for user_id in self._get_all_user_ids():
            insert_log(user_id, "CRITICAL", alert_msg)
    
    def _get_all_user_ids(self) -> list:
        """활성 사용자 ID 목록 조회"""
        try:
            engine_threads = get_engine_threads()
            return list(engine_threads.keys())
        except:
            return []
    
    def get_health_status(self) -> Dict:
        """현재 헬스 상태 반환"""
        with self._lock:
            return {
                **self.metrics,
                'monitoring': self.monitoring,
                'status': 'healthy' if self.metrics['failed_checks'] == 0 else 'degraded'
            }


# 🔒 글로벌 헬스 모니터 인스턴스
_health_monitor = HealthMonitor()


def start_health_monitoring():
    """헬스 모니터링 시작"""
    return _health_monitor.start_monitoring()


def stop_health_monitoring():
    """헬스 모니터링 중단"""
    _health_monitor.stop_monitoring()


def get_health_status():
    """헬스 상태 조회"""
    return _health_monitor.get_health_status()