# TTPAA Operations Portal

TTPAA 운영 포털은 4-5명의 임원진이 사용하는 비공개 내부 웹 서비스입니다.  
핵심 기능은 `지출 청구 워크플로우`와 `회칙/규정 근거 기반 챗봇`이며, Docker-first 운영을 전제로 설계했습니다.

## 1. 프로젝트 구조

```text
.
|-- apps/
|   |-- accounts/      # 사용자/권한/관리 설정/시드 명령
|   |-- chatbot/       # 회칙 업로드, 인덱싱, 근거 기반 챗봇 UI
|   |-- core/          # 대시보드, 공통 권한, 알림 로그, 헬스체크
|   |-- expenses/      # 지출 요청, 상태 전환, 감사 이력, Google 동기화
|   `-- pwa/           # manifest/service worker
|-- compose/
|   `-- caddy/         # VPS HTTPS reverse proxy 설정
|-- config/            # Django settings / urls / wsgi / asgi
|-- docs/              # 운영/배포 문서
|-- services/          # Google Drive/Sheets, 회칙 파일 인덱싱, OpenAI 챗봇, 알림
|-- static/            # CSS, JS, PWA 아이콘
|-- templates/         # Django 템플릿
|-- tests/             # 핵심 플로우 테스트
|-- Dockerfile
|-- docker-compose.yml
|-- compose.production.yml
|-- .env.example
`-- scripts/entrypoint.sh
```

## 2. 아키텍처 요약

- 백엔드: Django 5 + PostgreSQL + Django Templates
- 동적 UX: HTMX로 관리자 큐/챗봇 응답 부분만 부분 갱신
- 인증: Django 세션 인증, `admin` / `member` 두 역할
- 지출 워크플로우: 제출 -> 검토중 -> 승인/반려 -> 지급완료
- Google 연동: `paid` 상태에서만 Drive 업로드 + Sheets append
- 챗봇: PDF/DOCX/XLSX 텍스트 추출 -> PostgreSQL 저장 -> 간단한 lexical retrieval -> OpenAI 응답 -> quote/page post-validation
- PWA: manifest + service worker + installable icons + 오프라인 셸
- 배포: Docker Compose 기준, VPS+Caddy 또는 PaaS Dockerfile 배포 지원

## 3. 로컬 Docker 실행

### 3.1 사전 준비

1. `.env.example`을 `.env`로 복사합니다.
2. 필수 값을 채웁니다.
3. Docker Desktop 또는 Docker Engine이 실행 중인지 확인합니다.

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

### 3.2 컨테이너 실행

```bash
docker compose up --build
```

앱은 기본적으로 `http://localhost:8000` 에서 열립니다.

### 3.3 초기 설정

새 터미널에서 다음을 실행합니다.

```bash
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_demo
```

선택 명령:

```bash
docker compose exec web python manage.py test
docker compose exec web python manage.py collectstatic --noinput
```

### 3.4 로컬 필수 환경변수

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=True`
- `DJANGO_ALLOWED_HOSTS`
- `DATABASE_URL`

선택 환경변수:

- `OPENAI_API_KEY`
- `GOOGLE_SERVICE_ACCOUNT_FILE` 또는 `GOOGLE_SERVICE_ACCOUNT_JSON`
- `GOOGLE_DRIVE_FOLDER_ID`
- `GOOGLE_SHEET_ID`
- `GOOGLE_SHEET_NAME`: 비워두면 첫 시트 또는 기본 범위에 append
- `EMAIL_*`

OpenAI 또는 Google 키가 비어 있으면:

- 챗봇은 안전하게 답변을 거절합니다.
- Google 동기화는 실패 상태와 로그를 남기고 관리자 재시도를 기다립니다.

## 4. 운영 기능 요약

### 4.1 지출 요청

- 일반 구성원은 모바일/데스크톱에서 사진 첨부와 함께 지출 요청 제출
- 관리자는 필터 가능한 검토 큐에서 승인/반려/지급 완료 처리
- 상태 변경 이력, 관리자 메모, 반려 사유, Google 동기화 상태를 상세 화면에서 확인
- `paid` 전환 시 Google Drive/Sheets 동기화 수행
- 기본 Sheets 출력은 `buffer` 탭 기준 A열 지출일자, B열 사유 분류, C열 청구 금액, F열 비고입니다.
- 중복 동기화 방지를 위해 DB 상태 + 시트 request id 조회를 함께 사용

### 4.2 회칙 챗봇

- 관리자가 PDF, DOCX, XLSX 회칙 파일 업로드 후 인덱싱
- 페이지/청크 단위로 텍스트 저장합니다. DOCX는 문서 전체를 1페이지처럼, XLSX는 시트별로 페이지처럼 저장합니다.
- PDF 인덱싱은 선택 가능한 텍스트 레이어를 `pypdf`로 먼저 추출하고, 텍스트가 없는 페이지는 Tesseract OCR로 보완합니다. DOCX는 `python-docx`, XLSX는 `openpyxl`로 텍스트를 추출합니다.
- 답변은 정확한 quote/page citation이 검증될 때만 노출
- 검증 실패, 근거 부족, 관련 없는 질문, OpenAI 설정/연결 문제는 서로 다른 메시지로 안내합니다.

### 4.3 관리자 운영

- Django admin에서 주요 모델 관리 가능
- 별도 관리 설정 화면에서 구성원 계정과 카테고리 추가/비활성화
- 헬스체크: `/health/`

## 5. Docker 파일

핵심 배포 파일은 저장소에 포함되어 있습니다.

- [Dockerfile](/c:/Users/dong/Desktop/projects/ttpaa/Dockerfile)
- [docker-compose.yml](/c:/Users/dong/Desktop/projects/ttpaa/docker-compose.yml)
- [compose.production.yml](/c:/Users/dong/Desktop/projects/ttpaa/compose.production.yml)
- [entrypoint.sh](/c:/Users/dong/Desktop/projects/ttpaa/scripts/entrypoint.sh)
- [Caddyfile](/c:/Users/dong/Desktop/projects/ttpaa/compose/caddy/Caddyfile)
- [.env.example](/c:/Users/dong/Desktop/projects/ttpaa/.env.example)

## 6. VPS 배포 가이드

권장 기본 배포는 Ubuntu VPS + Docker Compose + Caddy 입니다.

### 6.1 서버 준비

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker $USER
```

로그아웃 후 다시 로그인합니다.

### 6.2 배포 절차

```bash
git clone <your-repo-url> ttpaa
cd ttpaa
cp .env.example .env
```

`.env` 예시:

```env
DJANGO_SECRET_KEY=very-strong-secret
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=portal.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://portal.example.com
APP_BASE_URL=https://portal.example.com
APP_DOMAIN=portal.example.com
POSTGRES_DB=ttpaa
POSTGRES_USER=ttpaa
POSTGRES_PASSWORD=strong-db-password
DATABASE_URL=postgres://ttpaa:strong-db-password@db:5432/ttpaa
DEFAULT_FROM_EMAIL=no-reply@portal.example.com
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=no-reply@portal.example.com
EMAIL_HOST_PASSWORD=change-me
EMAIL_USE_TLS=True
ADMIN_EMAILS=finance@example.com
OPENAI_API_KEY=sk-...
GOOGLE_SERVICE_ACCOUNT_FILE=/app/secrets/google-service-account.json
GOOGLE_DRIVE_FOLDER_ID=...
GOOGLE_SHEET_ID=...
GOOGLE_SHEET_NAME=Expenses
```

서비스 계정 키 파일을 쓰는 경우 로컬 또는 서버의 `secrets/google-service-account.json`에 키 파일을 두면 Docker Compose가 컨테이너의 `/app/secrets/google-service-account.json`로 읽기 전용 마운트합니다. 이 파일은 커밋하지 않습니다.

서비스 시작:

```bash
docker compose -f compose.production.yml up -d --build
docker compose -f compose.production.yml exec web python manage.py createsuperuser
docker compose -f compose.production.yml exec web python manage.py seed_demo
```

### 6.3 DNS / HTTPS

- DNS A 레코드를 VPS 공인 IP로 연결합니다.
- `APP_DOMAIN` 을 실제 도메인으로 설정합니다.
- Caddy가 80/443 포트에서 자동으로 HTTPS 인증서를 발급합니다.

추천 도메인 예:

- `portal.ttpaa.kr`
- `app.ttpaa.kr`
- `ttpaa.club`

### 6.4 업데이트

```bash
git pull
docker compose -f compose.production.yml up -d --build
docker compose -f compose.production.yml exec web python manage.py migrate
```

### 6.5 재시작 / 로그

```bash
docker compose -f compose.production.yml restart
docker compose -f compose.production.yml logs -f web
docker compose -f compose.production.yml logs -f caddy
```

### 6.6 백업

DB 백업:

```bash
docker compose -f compose.production.yml exec db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > backup.sql
```

미디어 백업:

```bash
docker run --rm -v ttpaa_media_data:/source -v $(pwd):/backup alpine tar czf /backup/media-backup.tar.gz -C /source .
```

복원 예시:

```bash
cat backup.sql | docker compose -f compose.production.yml exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB"
```

## 7. PaaS 배포

Render / Railway / Fly.io 같은 Dockerfile 지원 플랫폼에도 배포할 수 있습니다.

- 웹 서비스는 이 저장소의 [Dockerfile](/c:/Users/dong/Desktop/projects/ttpaa/Dockerfile) 사용
- PostgreSQL은 플랫폼 관리형 DB 사용
- 환경변수는 `.env.example` 기준으로 등록
- 정적/미디어는 persistent disk 또는 외부 스토리지 사용 권장
- 도메인은 플랫폼 custom domain 기능으로 연결

필수 체크:

- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DATABASE_URL`
- `APP_BASE_URL`

## 8. 운영 runbook

- 사용자 생성: Django admin 또는 관리 설정 화면
- 카테고리 변경: 관리 설정 화면 또는 Django admin
- 회칙 업로드/교체: `회칙 관리` 화면
- 재인덱싱: `회칙 관리` 화면의 `재인덱싱`
- 지출 검토: `관리 검토` 화면
- 지급 완료 처리: 상세 화면에서 `지급 완료 처리`
- Google 동기화 재시도: 상세 화면에서 `Google 동기화 재시도`
- 비밀키 교체: `.env` 변경 후 컨테이너 재시작
- 로그 확인: `docker compose logs -f web`

운영 상세 문서는 [operations.md](/c:/Users/dong/Desktop/projects/ttpaa/docs/operations.md) 를 참고하세요.

## 9. 테스트

작성된 테스트 범위:

- 지출 요청 제출
- 관리자 승인
- 관리자 반려
- 지급 완료 처리
- Google 동기화 성공
- 중복 동기화 방지
- 회칙 업로드 및 인덱싱
- 챗봇 지원 답변
- 챗봇 거절 답변
- 권한 제한

실행:

```bash
docker compose exec web python manage.py test
```

## 10. 한계와 설계 선택

- `pgvector` 는 Docker 단순성을 위해 도입하지 않았습니다.
- 회칙 retrieval 은 PostgreSQL 저장 + Python lexical scoring 기반입니다.
- 회칙 PDF 인덱싱은 텍스트 레이어를 우선 사용하고, 텍스트가 없거나 너무 짧은 페이지는 Tesseract OCR로 텍스트 추출을 시도합니다. DOCX/XLSX는 파일 내 텍스트를 직접 추출합니다. OCR 언어, 해상도, OCR fallback 기준은 `CONSTITUTION_OCR_LANG`, `CONSTITUTION_OCR_DPI`, `CONSTITUTION_OCR_MIN_TEXT_CHARS`로 조정할 수 있습니다.
- HEIC 파일은 업로드/저장은 허용하지만 브라우저 미리보기는 환경에 따라 제한될 수 있습니다.
- 백그라운드 큐(Celery/Redis)는 운영 단순성을 위해 제외했습니다.
