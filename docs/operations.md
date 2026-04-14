# 운영 가이드

## 일상 운영

- 새 사용자 추가: `관리 설정` 페이지 또는 Django admin
- 사용자 비활성화: `관리 설정` 페이지
- 카테고리 추가/비활성화: `관리 설정` 페이지 또는 Django admin
- 지출 검토: `관리 검토` -> 상세 -> 승인/반려/지급 완료
- Google 동기화 실패 확인: 지출 상세의 `Google Sync` 상태와 `sync_error`
- 재시도: `Google 동기화 재시도`

## 회칙 운영

- 새 PDF 업로드: `회칙 관리`
- 현재 활성 버전 확인: 대시보드 / 회칙 관리
- 재인덱싱: `회칙 관리`의 `재인덱싱`
- 챗봇이 근거 없이 답하면 안 되므로, 인용 검증 실패 시 의도적으로 답변을 거절하도록 설계되어 있습니다.

## 비밀값 교체

1. `.env` 수정
2. `docker compose up -d`
3. 필요시 `docker compose restart web`

교체 권장 항목:

- `DJANGO_SECRET_KEY`
- `POSTGRES_PASSWORD`
- `EMAIL_HOST_PASSWORD`
- `OPENAI_API_KEY`
- Google 서비스 계정 키

## 백업 정책 권장

- DB: 하루 1회 SQL dump
- 미디어: 하루 1회 tar 백업
- `.env`: 안전한 비밀 저장소에 별도 보관

## 장애 대응

- 앱 상태 확인: `/health/`
- 로그 확인: `docker compose logs -f web`
- DB 연결 문제: `docker compose logs -f db`
- Caddy HTTPS 문제: `docker compose -f compose.production.yml logs -f caddy`
