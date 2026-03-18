# CS Deadlines Hub MVP

GitHub Pages + GitHub Actions 기반의 **CS 전반 학회/워크숍 deadline tracker** 예시 프로젝트입니다.

## 핵심 아이디어
- `data/venues.yml`: 전체 venue master catalog
- `data/instances.yml`: 연도별 인스턴스(deadline, 개최일, 위치)
- `scripts/fetch.py`: `venues.yml`에 있는 venue만 우선 스캔
- `scripts/build_site.py`: 정적 JSON 생성
- `docs/`: GitHub Pages에서 배포할 정적 사이트
- `.github/workflows/update.yml`: 정기 스캔 + 사이트 빌드 + Pages 배포

## 운영 원칙
1. **기본 스캔은 venues.yml 기준**으로만 수행
2. 새 venue는 discovery 결과를 바로 반영하지 않고, 사람이 검토 후 `venues.yml`에 추가
3. deadline이 확인된 경우만 `instances.yml`에 기록
4. 사이트는 `docs/assets/venues.json`을 읽어 렌더링

## 빠른 시작
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/validate.py
python scripts/fetch.py
python scripts/build_site.py
```

## GitHub Pages 배포
GitHub Pages는 custom GitHub Actions workflow로 배포할 수 있고, scheduled workflows는 cron 기반으로 실행할 수 있습니다. 또한 scheduled workflows는 기본 브랜치에서 동작하며 가장 짧은 주기는 5분입니다. citeturn990087search0turn990087search3

## 주의
- 현재 `venues.yml`은 **seed dataset**입니다.
- 일부 venue의 URL/분류/tier는 운영자가 검토하면서 다듬는 것을 전제로 합니다.
- `instances.yml`은 예시 데이터만 포함합니다.
