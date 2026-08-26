# TransitGuard 기여 안내

TransitGuard 개선에 관심을 가져주셔서 감사합니다.

## 개발 환경 준비

    python -m venv .venv
    source .venv/bin/activate
    python -m pip install -e ".[dev,api]"
    python -m pytest -q

Windows에서는 가상환경을 활성화하지 않고 다음과 같이 실행할 수 있습니다.

    py -3 -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -e ".[dev,api]"
    .\.venv\Scripts\python.exe -m pytest -q

## 변경 전 확인 사항

- 실제 API 키나 .env를 커밋하지 않습니다.
- 기존 기능과 관련 없는 파일을 함께 수정하지 않습니다.
- 외부 API 응답을 테스트에 사용할 때는 개인정보와 서비스 키를 제거합니다.
- 새 기능에는 정상 입력, 잘못된 입력과 실패 상황을 확인하는 테스트를 추가합니다.
- 사용자에게 표시되는 실제 시각과 추정 시각을 명확히 구분합니다.

## Pull Request 전 검사

    python -m ruff check .
    python -m pytest -q

실제 TAGO 테스트는 선택적으로 실행합니다.

    python -m pytest -m live_tago -q

실데이터 테스트 결과에는 실행 시각, 사용 지역과 외부 API 상태를 함께 기록하는 것이 좋습니다.

## 프로젝트 방향

TransitGuard의 핵심 범위는 **기존 대중교통 경로 후보의 환승 안정성 평가**입니다. 완성형 지도 렌더링, 요금 계산과 내비게이션 UI는 환승 신뢰도 평가를 직접 개선하는 경우에만 프로젝트 범위에 포함합니다.

후보 생성 기능은 제한적·실험적 기능임을 유지하고, 전국 모든 경로를 완전 탐색한다고 표현하지 않습니다.

## 문서와 사용자 안내

- 공개 문서는 기본적으로 한국어로 작성합니다.
- 코드 식별자, API 경로, JSON 필드와 오류 코드에는 원래 영문 표기를 유지합니다.
- 새 환경변수나 API가 추가되면 README와 관련 문서를 함께 수정합니다.
- 현재 한계와 추정값을 숨기지 않고 명시합니다.

