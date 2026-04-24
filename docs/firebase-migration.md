# Firebase migration guide

이 문서는 기존 Django/PostgreSQL 앱을 Firebase Hosting, Firebase Authentication, Cloud Firestore 중심으로 옮기는 1차 전환 가이드입니다.

## 목표 구조

```text
Browser
  |
  | Firebase Auth email/password
  | Firestore Web SDK
  v
Firebase Hosting
Cloud Firestore
Firebase Storage
Google Apps Script Web Apps
```

Firebase 버전은 별도 Django 서버를 두지 않습니다. 그래서 비밀키가 필요한 작업은 브라우저에서 직접 처리하지 않고 Apps Script Web App 뒤에 둡니다.

- Firebase Auth: 로그인, 계정 생성
- Firestore: 사용자 프로필, 지출 신청, 상태 이력, 규정 문단, 검색 로그
- Firebase Storage: 지출 신청 영수증/자료 이미지 임시 저장
- Firebase Hosting: 정적 웹앱 배포
- Apps Script: Gemini 챗봇, 지급 완료 시 Drive/Sheets 동기화

## 무료 범위 메모

2026-04-17 기준 공식 문서 확인 내용입니다.

- Firestore는 프로젝트당 무료 DB 1개에 대해 저장 1 GiB, 문서 읽기 50,000/day, 쓰기 20,000/day, 삭제 20,000/day, outbound 10 GiB/month 무료 quota가 있습니다.
- Firebase Hosting은 저장 용량과 전송량 기준 quota가 있으며, Hosting 사이트는 CDN을 사용합니다.
- Firestore TTL 삭제, PITR, 백업, 복원, clone 같은 기능은 무료 사용에 포함되지 않습니다.

작은 내부용 서비스라면 Firestore 무료 quota 안에서 충분히 버틸 가능성이 큽니다. 다만 quota는 제품 정책에 따라 바뀔 수 있으니 배포 전에 Firebase Console과 Google Cloud Console에서 한 번 더 확인하세요.

## Firebase Console 설정

1. Firebase 프로젝트를 만듭니다.
2. Authentication에서 Email/Password provider를 켭니다.
3. Firestore Database를 Native mode로 만듭니다.
4. Storage를 켭니다.
5. Hosting을 켭니다.
5. Project settings > General > Your apps에서 Web app을 추가합니다.
6. Web app config 값을 `firebase/public/firebase-config.js`에 넣습니다.
7. 첫 계정으로 로그인한 뒤 Firestore `users/{uid}` 문서의 `role`을 `admin`으로 바꿉니다.
8. `firebase deploy --only firestore,hosting`으로 규칙과 앱을 배포합니다.

## 로컬 확인

Firebase CLI가 설치되어 있다면 다음처럼 확인할 수 있습니다.

```bash
firebase emulators:start --only hosting,firestore,auth
```

또는 정적 파일만 빠르게 확인하려면 `firebase/public`을 정적 서버로 열어도 됩니다. 실제 로그인과 Firestore 작업은 Firebase config가 필요합니다.

## Firestore 데이터 모델

### `users/{uid}`

```json
{
  "uid": "firebase-auth-uid",
  "email": "user@example.com",
  "displayName": "홍길동",
  "role": "member",
  "createdAt": "serverTimestamp",
  "updatedAt": "serverTimestamp"
}
```

`role`은 `member` 또는 `admin`입니다. 일반 사용자는 자기 role을 바꿀 수 없고, 관리자는 다른 사용자의 role을 바꿀 수 있습니다.

### `expenseCategories/{categoryId}`

```json
{
  "name": "교우회 활동비",
  "sortOrder": 10,
  "active": true,
  "updatedAt": "serverTimestamp"
}
```

관리 화면의 `기본 카테고리 넣기` 버튼으로 기본값을 넣을 수 있습니다.

### `expenseRequests/{requestId}`

```json
{
  "requesterUid": "firebase-auth-uid",
  "requesterEmail": "user@example.com",
  "requesterName": "홍길동",
  "expenseDate": "2026-04-17",
  "category": "교우회 활동비",
  "amountKrw": 30000,
  "receiptUrl": "https://drive.google.com/...",
  "comment": "간단한 사유",
  "status": "submitted",
  "syncState": "manual",
  "createdAt": "serverTimestamp",
  "updatedAt": "serverTimestamp"
}
```

상태값은 `submitted`, `under_review`, `approved`, `rejected`, `paid`입니다.

### `expenseRequests/{requestId}/statusHistory/{historyId}`

```json
{
  "fromStatus": "submitted",
  "toStatus": "approved",
  "note": "확인 완료",
  "changedByUid": "admin-uid",
  "changedByName": "관리자",
  "createdAt": "serverTimestamp"
}
```

### `policyPages/{pageId}`

```json
{
  "version": "2026 운영 규정",
  "section": "제5장 상벌",
  "article": "제20조 임원의 포상, 징계 및 파면",
  "clause": "③",
  "paragraph": "임원이 본 회 및 피아노 동아리의 운영에 심대한 영향을 끼쳐 정상적으로 그 직무를 운영하기 힘들다고 판단될 경우 또는 2회의 경고를 받은 경우 회원은 임원의 탄핵을 발의할 수 있고 총회 출석 회원 2/3 이상의 동의로 파면, 면직시킬 수 있다.",
  "order": 1,
  "createdAt": "serverTimestamp",
  "updatedAt": "serverTimestamp"
}
```

1차 버전에서는 PDF/DOCX/XLSX OCR 인덱싱을 제거하고, 관리자가 JSON 배열 또는 일반 텍스트를 붙여넣으면 Firestore에 저장합니다. JSON 배열을 넣으면 `section`, `article`, `clause`, `paragraph`를 보존합니다. 일반 텍스트를 넣으면 각 줄을 `paragraph`로 저장합니다.

예시:

```json
[
  {
    "section": "제5장 상벌",
    "article": "제20조 임원의 포상, 징계 및 파면",
    "clause": "③",
    "paragraph": "임원이 본 회 및 피아노 동아리의 운영에 심대한 영향을 끼쳐 정상적으로 그 직무를 운영하기 힘들다고 판단될 경우 또는 2회의 경고를 받은 경우 회원은 임원의 탄핵을 발의할 수 있고 총회 출석 회원 2/3 이상의 동의로 파면, 면직시킬 수 있다."
  }
]
```

검색은 Firestore에서 `policyPages` 문서를 가져온 뒤 브라우저에서 `section`, `article`, `clause`, `paragraph`를 합쳐 확인합니다. 결과에는 `제5장 상벌 · 제20조 임원의 포상, 징계 및 파면 · ③`처럼 근거 위치를 함께 표시합니다.

## Django에서 바뀐 점

### 유지한 기능

- 이메일/비밀번호 로그인
- member/admin 역할
- 지출 신청
- 내 신청 목록
- 관리자 검토 목록
- 상태 변경
- 상태 이력 저장
- 규정 검색
- PWA 설치 기본값

### 바꾼 기능

- Django admin은 Firebase Console과 앱 내부 관리 화면으로 대체합니다.
- 첨부파일은 Firebase Storage에 먼저 업로드하고, 지급 완료 시 Apps Script가 Drive로 복사합니다.
- Google Drive/Sheets 자동 동기화는 Apps Script Web App endpoint로 처리합니다.
- LLM 챗봇은 Apps Script Web App을 통해 Gemini API를 호출합니다.

## 왜 Drive/Sheets와 LLM을 바로 옮기지 않았나

서버가 없는 정적 Firebase 앱에서는 Google service account JSON, OpenAI API key, Gemini API key 같은 비밀값을 안전하게 숨길 수 없습니다. 브라우저 코드에 넣으면 사용자가 볼 수 있습니다.

현재 Firebase 웹앱의 회칙 질문 흐름은 다음과 같습니다.

1. 브라우저가 Firestore `policyPages` 문서를 최대 500개 읽습니다.
2. 질문, Firebase ID token, 회칙 JSON 전체를 `firebase-config.js`의 `TTPAA_CHATBOT_CONFIG.endpointUrl`로 한 번만 POST합니다.
3. endpoint 뒤쪽 서버 또는 Apps Script가 Gemini API를 한 번만 호출합니다.
4. 응답은 `{ "answer": "...", "evidence": [...] }` JSON 형태로 돌려줍니다.
5. 웹앱은 답변과 `section`, `article`, `clause`, `paragraph` 근거를 표시합니다.

브라우저에서 Gemini API key를 직접 쓰지 않는 것이 중요합니다.

Drive/Sheets 동기화 흐름은 다음과 같습니다.

1. 사용자가 컴퓨터나 휴대폰에서 영수증/자료 이미지를 첨부해 지출 신청을 만듭니다.
2. 브라우저가 이미지를 Firebase Storage `receipts/{uid}/{expenseId}/...`에 업로드합니다.
3. Firestore `expenseRequests/{requestId}.receiptFiles`에 파일 이름, Storage path, download URL을 저장합니다.
4. 관리자가 `paid` 처리할 때 브라우저가 `TTPAA_EXPENSE_SYNC_CONFIG.endpointUrl`로 Firebase ID token과 지출 데이터를 POST합니다.
5. Apps Script가 Firebase ID token을 검증하고, Firestore `users/{uid}.role == admin`인지 확인합니다.
6. Apps Script가 이미지를 Drive 폴더에 `YYYYMMDD_순번_아이디_사진순서.ext` 이름으로 저장하고 Google Sheets에 한 줄을 append합니다.
7. 브라우저가 Drive/Sheets 동기화 성공을 확인한 뒤 Firebase Storage 원본을 삭제하고, Firestore `receiptFiles`에 `storageDeleted` 상태를 기록합니다.

더 단단한 방식은 Cloud Functions 또는 Cloud Run이지만, 무료만 고집하면 billing 요구 조건이 생길 수 있어서 1차 목표와 맞지 않을 수 있습니다.

## Apps Script 챗봇 endpoint

`integrations/apps-script-policy-chatbot.gs`는 Google Apps Script Web App으로 배포할 수 있는 예시입니다. 이 endpoint는 Firebase ID token을 검증한 뒤 Gemini `generateContent` API를 한 번 호출합니다.

Apps Script의 Script properties에 다음 값을 넣습니다.

```text
FIREBASE_WEB_API_KEY=<firebase web api key>
GEMINI_API_KEY=<gemini api key>
GEMINI_CHAT_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODEL=gemini-2.5-flash-lite
GEMINI_THINKING_BUDGET=0
```

배포 후 Web App URL을 `firebase/public/firebase-config.js`에 넣습니다.

## Apps Script 지출 동기화 endpoint

`integrations/apps-script-expense-sync.gs`는 지급 완료 시 Drive/Sheets 동기화를 수행하는 별도 Apps Script Web App입니다.

Apps Script의 Script properties에 다음 값을 넣습니다.

```text
FIREBASE_WEB_API_KEY=<firebase web api key>
FIREBASE_PROJECT_ID=ttpaa-c64a6
EXPENSE_SPREADSHEET_ID=<target spreadsheet id>
EXPENSE_SHEET_NAME=buffer
EXPENSE_DRIVE_FOLDER_ID=<target drive folder id>
```

배포 후 Web App URL을 `firebase/public/firebase-config.js`에 넣습니다.

```js
window.TTPAA_EXPENSE_SYNC_CONFIG = {
  endpointUrl: "https://script.google.com/macros/s/.../exec"
};
```

```js
window.TTPAA_CHATBOT_CONFIG = {
  endpointUrl: "https://script.google.com/macros/s/your-deployment-id/exec"
};
```

웹앱은 JSON을 `text/plain` POST로 보냅니다. 이렇게 하면 브라우저 preflight를 피하면서 질문 1회당 챗봇 endpoint 호출도 1회로 유지할 수 있습니다.

## 배포 명령

```bash
firebase login
firebase use your-firebase-project-id
firebase deploy --only firestore,hosting
```

배포 전에는 `firebase/.firebaserc.example`을 참고해 `.firebaserc`를 만들거나 `firebase use`로 프로젝트를 지정하세요.

## 참고한 공식 문서

- Firestore quotas: https://docs.cloud.google.com/firestore/quotas
- Firestore pricing: https://firebase.google.com/docs/firestore/pricing
- Firestore data model: https://firebase.google.com/docs/firestore/data-model
- Firebase Auth ID token verification: https://firebase.google.com/docs/auth/admin/verify-id-tokens
- Gemini generateContent API: https://ai.google.dev/api
- Firebase Hosting usage and pricing: https://firebase.google.com/docs/hosting/usage-quotas-pricing
