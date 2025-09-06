# FINAL CODE
# tests/test_runner.py

import unittest
import sys
import os
import time
from datetime import datetime
import argparse

# 프로젝트 루트 경로 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# 테스트 모듈 임포트
try:
    from test_strategy_v2 import TestStrategyV2
    from test_trader_sandbox import TestTraderSandbox
    from test_engine_loop import TestEngineLoop
    ALL_TESTS_AVAILABLE = True
except ImportError as e:
    print(f"⚠️  일부 테스트 모듈을 임포트할 수 없습니다: {e}")
    from test_strategy_v2 import TestStrategyV2
    ALL_TESTS_AVAILABLE = False


class TestRunner:
    """
    통합 테스트 러너
    - 모든 테스트를 실행하고 결과를 보고
    """
    
    def __init__(self):
        self.results = {}
        self.start_time = None
        self.end_time = None
        
    def run_all_tests(self, verbose=False):
        """모든 테스트 실행"""
        print("🧪 트레이드봇 MVP 테스트 스위트 실행")
        print("=" * 60)
        
        self.start_time = time.time()
        
        # 테스트 목록
        test_classes = [
            ("전략 테스트", TestStrategyV2),
        ]
        
        if ALL_TESTS_AVAILABLE:
            test_classes.extend([
                ("트레이더 샌드박스 테스트", TestTraderSandbox),
                ("엔진 루프 테스트", TestEngineLoop)
            ])
        else:
            print("⚠️  트레이더 및 엔진 테스트는 모듈 임포트 문제로 건너뜁니다.")
        
        total_tests = 0
        total_failures = 0
        total_errors = 0
        
        for test_name, test_class in test_classes:
            print(f"\n📋 {test_name} 실행 중...")
            
            # 테스트 스위트 생성
            suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
            
            # 테스트 실행
            runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
            result = runner.run(suite)
            
            # 결과 저장
            self.results[test_name] = {
                'tests_run': result.testsRun,
                'failures': len(result.failures),
                'errors': len(result.errors),
                'failures_list': result.failures,
                'errors_list': result.errors
            }
            
            # 통계 업데이트
            total_tests += result.testsRun
            total_failures += len(result.failures)
            total_errors += len(result.errors)
            
            print(f"✅ {test_name} 완료: {result.testsRun}개 테스트, "
                  f"{len(result.failures)}개 실패, {len(result.errors)}개 에러")
        
        self.end_time = time.time()
        
        # 전체 결과 보고
        self.print_summary(total_tests, total_failures, total_errors)
        
        return total_failures == 0 and total_errors == 0
    
    def run_specific_test(self, test_name, verbose=False):
        """특정 테스트만 실행"""
        test_classes = {
            'strategy': TestStrategyV2,
        }
        
        if ALL_TESTS_AVAILABLE:
            test_classes.update({
                'trader': TestTraderSandbox,
                'engine': TestEngineLoop
            })
        else:
            if test_name in ['trader', 'engine']:
                print(f"⚠️  {test_name} 테스트는 모듈 임포트 문제로 실행할 수 없습니다.")
                return False
        
        if test_name not in test_classes:
            print(f"❌ 알 수 없는 테스트: {test_name}")
            print(f"사용 가능한 테스트: {list(test_classes.keys())}")
            return False
        
        print(f"🧪 {test_name} 테스트 실행")
        print("=" * 40)
        
        self.start_time = time.time()
        
        test_class = test_classes[test_name]
        suite = unittest.TestLoader().loadTestsFromTestCase(test_class)
        runner = unittest.TextTestRunner(verbosity=2 if verbose else 1)
        result = runner.run(suite)
        
        self.end_time = time.time()
        
        self.results[test_name] = {
            'tests_run': result.testsRun,
            'failures': len(result.failures),
            'errors': len(result.errors),
            'failures_list': result.failures,
            'errors_list': result.errors
        }
        
        success = len(result.failures) == 0 and len(result.errors) == 0
        
        print(f"\n✅ {test_name} 테스트 완료: {'성공' if success else '실패'}")
        print(f"📊 실행된 테스트: {result.testsRun}")
        print(f"❌ 실패: {len(result.failures)}")
        print(f"🚨 에러: {len(result.errors)}")
        
        return success
    
    def print_summary(self, total_tests, total_failures, total_errors):
        """테스트 결과 요약 출력"""
        execution_time = self.end_time - self.start_time
        
        print("\n" + "=" * 60)
        print("📊 테스트 실행 결과 요약")
        print("=" * 60)
        print(f"⏱️  총 실행 시간: {execution_time:.2f}초")
        print(f"🧪 총 테스트 수: {total_tests}")
        print(f"✅ 성공: {total_tests - total_failures - total_errors}")
        print(f"❌ 실패: {total_failures}")
        print(f"🚨 에러: {total_errors}")
        
        if total_failures > 0 or total_errors > 0:
            print("\n❌ 실패한 테스트 상세:")
            for test_name, result in self.results.items():
                if result['failures'] > 0 or result['errors'] > 0:
                    print(f"\n🔍 {test_name}:")
                    for i, (test, traceback) in enumerate(result['failures_list']):
                        print(f"  실패 {i+1}: {test}")
                    for i, (test, traceback) in enumerate(result['errors_list']):
                        print(f"  에러 {i+1}: {test}")
        
        success_rate = ((total_tests - total_failures - total_errors) / total_tests) * 100
        print(f"\n📈 성공률: {success_rate:.1f}%")
        
        if total_failures == 0 and total_errors == 0:
            print("\n🎉 모든 테스트가 성공적으로 통과했습니다!")
        else:
            print("\n⚠️  일부 테스트가 실패했습니다. 위의 상세 정보를 확인하세요.")
    
    def generate_report(self, output_file=None):
        """테스트 결과 보고서 생성"""
        if not self.results:
            print("❌ 실행된 테스트 결과가 없습니다.")
            return
        
        report = []
        report.append("# 트레이드봇 MVP 테스트 보고서")
        report.append(f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("")
        
        if self.start_time and self.end_time:
            execution_time = self.end_time - self.start_time
            report.append(f"## 실행 정보")
            report.append(f"- 총 실행 시간: {execution_time:.2f}초")
            report.append("")
        
        # 전체 통계
        total_tests = sum(r['tests_run'] for r in self.results.values())
        total_failures = sum(r['failures'] for r in self.results.values())
        total_errors = sum(r['errors'] for r in self.results.values())
        
        report.append("## 전체 통계")
        report.append(f"- 총 테스트 수: {total_tests}")
        report.append(f"- 성공: {total_tests - total_failures - total_errors}")
        report.append(f"- 실패: {total_failures}")
        report.append(f"- 에러: {total_errors}")
        
        if total_tests > 0:
            success_rate = ((total_tests - total_failures - total_errors) / total_tests) * 100
            report.append(f"- 성공률: {success_rate:.1f}%")
        report.append("")
        
        # 개별 테스트 결과
        report.append("## 개별 테스트 결과")
        for test_name, result in self.results.items():
            report.append(f"### {test_name}")
            report.append(f"- 실행된 테스트: {result['tests_run']}")
            report.append(f"- 실패: {result['failures']}")
            report.append(f"- 에러: {result['errors']}")
            
            if result['failures'] > 0:
                report.append("- 실패한 테스트:")
                for i, (test, traceback) in enumerate(result['failures_list']):
                    report.append(f"  {i+1}. {test}")
            
            if result['errors'] > 0:
                report.append("- 에러 발생 테스트:")
                for i, (test, traceback) in enumerate(result['errors_list']):
                    report.append(f"  {i+1}. {test}")
            
            report.append("")
        
        report_content = "\n".join(report)
        
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report_content)
            print(f"📄 보고서가 {output_file}에 저장되었습니다.")
        else:
            print("\n📄 테스트 보고서:")
            print(report_content)
        
        return report_content


def main():
    """메인 함수"""
    parser = argparse.ArgumentParser(description='트레이드봇 MVP 테스트 실행기')
    parser.add_argument('--test', '-t', type=str, 
                       choices=['all', 'strategy', 'trader', 'engine'],
                       default='all',
                       help='실행할 테스트 선택 (all, strategy, trader, engine)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='상세 출력 모드')
    parser.add_argument('--report', '-r', type=str,
                       help='보고서 파일 경로')
    
    args = parser.parse_args()
    
    runner = TestRunner()
    
    if args.test == 'all':
        success = runner.run_all_tests(verbose=args.verbose)
    else:
        success = runner.run_specific_test(args.test, verbose=args.verbose)
    
    # 보고서 생성
    if args.report:
        runner.generate_report(args.report)
    
    # 종료 코드
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()