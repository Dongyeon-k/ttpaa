# TTPAA Operations Portal

TTPAA Operations Portal은 고려대학교 피아노 동아리 교우회 내부에서 쓰는 소규모 운영 웹앱입니다. 현재 버전은 Firebase 기반 정적 웹앱입니다.

운영 목표는 단순합니다.

- 친한 구성원끼리 가끔 사용
- 서버 운영 없이 Firebase Hosting + Firebase Auth + Firestore로 운영
- 지출 신청과 검토 상태를 Firestore에 저장
- 회칙 데이터는 Firestore에 구조화 저장
- 회칙 질문은 Apps Script Web App을 거쳐 Gemini API를 1회 호출

## Current Stack

- Frontend: static HTML/CSS/JavaScript
- Hosting: Firebase Hosting
- Auth: Firebase Authentication email/password
- Database: Cloud Firestore
- Policy chatbot proxy: Google Apps Script Web App
- LLM: Gemini API, default `gemini-2.5-flash`
- Policy import: Node.js script using Firebase Web SDK

Live hosting target:

```text
https://ttpaa.web.app
```

Firebase project:

```text
ttpaa-c64a6
```

## Repository Layout

```text
.
|-- firebase.json                         # Firebase Hosting and Firestore deploy config
|-- .firebaserc                           # Firebase project alias
|-- firebase/
|   |-- firestore.rules                   # Firestore security rules
|   |-- firestore.indexes.json            # Firestore indexes
|   `-- public/
|       |-- index.html                    # Static app shell
|       |-- app.js                        # Firebase Auth, Firestore, UI logic
|       |-- styles.css
|       |-- firebase-config.js            # Firebase web config and chatbot endpoint
|       |-- firebase-config.example.js
|       |-- manifest.webmanifest
|       |-- service-worker.js
|       `-- assets/
|-- data/
|   `-- policies/
|       `-- ttpaa-policy.json             # Structured TTPAA bylaws data
|-- integrations/
|   |-- apps-script-policy-chatbot.gs     # Apps Script Gemini chatbot endpoint
|   `-- apps-script-expense-sync.gs       # Apps Script Drive/Sheets expense sync endpoint
|-- scripts/
|   |-- import-policy-client.mjs          # Import policy using Firebase Auth admin user
|   `-- import-policy.mjs                 # Admin SDK import option, requires ADC/service account
|-- docs/
|   `-- firebase-migration.md             # Migration notes and deeper setup notes
|-- package.json
`-- package-lock.json
```

## Features

### Authentication

Users sign in with Firebase Authentication email/password accounts.

On first login, the app creates a Firestore profile:

```text
users/{uid}
```

Default profile:

```json
{
  "uid": "firebase-auth-uid",
  "email": "user@example.com",
  "displayName": "user",
  "role": "member",
  "createdAt": "...",
  "updatedAt": "..."
}
```

Roles:

- `member`: submit and view own expense requests, read policy data, ask the policy chatbot
- `admin`: all member permissions plus expense review, policy import, category setup, user/profile administration through Firestore

To make an admin, create or sign in with the account, then edit Firestore:

```text
users/{uid}.role = "admin"
```

### Expense Requests

Firestore collection:

```text
expenseRequests/{requestId}
```

The app supports:

- expense request creation
- my request list
- admin queue
- status transitions
- status history
- receipt image upload from desktop or mobile
- optional receipt/reference URL field
- Drive image copy and Sheets append when an admin marks a request as paid

Statuses:

```text
submitted
under_review
approved
rejected
paid
```

Status history is stored under:

```text
expenseRequests/{requestId}/statusHistory/{historyId}
```

### Policy Data

Firestore collection:

```text
policyPages/{policyId}
```

Policy entries are stored as structured records:

```json
{
  "version": "TTPAA 회칙",
  "order": 1,
  "section": "제1장 총칙",
  "article": "제1조 명칭",
  "clause": "①",
  "subclause": "",
  "paragraph": "본문",
  "createdAt": "...",
  "updatedAt": "..."
}
```

The current seed data lives at:

```text
data/policies/ttpaa-policy.json
```

It currently contains 78 policy records.

### Policy Chatbot

The browser does not call Gemini directly. Gemini API keys must not be exposed in browser JavaScript.

Current flow:

```text
Browser
  -> reads policyPages from Firestore
  -> sends question + policy JSON + Firebase idToken to Apps Script endpoint
Apps Script
  -> verifies Firebase idToken
  -> calls Gemini generateContent once
  -> returns answer + evidence
Browser
  -> renders answer and cited section/article/clause/paragraph
```

One user question results in:

- one Firestore read pass for policy data
- one Apps Script request
- one Gemini API call

The chatbot endpoint returns JSON:

```json
{
  "answer": "한국어 답변",
  "evidence": [
    {
      "section": "제4장 재무",
      "article": "제17조 재정의 집행",
      "clause": "⑤",
      "paragraph": "회원 본인의 결혼..."
    }
  ]
}
```

## Firebase Setup

The Firebase project must have:

- Firebase Authentication enabled
- Email/Password sign-in enabled
- Cloud Firestore database created
- Firebase Storage enabled
- Firebase Hosting site `ttpaa`

Firestore database:

```text
(default)
location: asia-northeast3
edition: standard
free tier: true
```

Deploy Firestore rules and indexes:

```powershell
firebase deploy --only firestore --project ttpaa-c64a6
```

Deploy Storage rules:

```powershell
firebase deploy --only storage --project ttpaa-c64a6
```

Deploy Hosting:

```powershell
firebase deploy --only hosting:ttpaa --project ttpaa-c64a6
```

Deploy both:

```powershell
firebase deploy --only firestore,hosting:ttpaa --project ttpaa-c64a6
```

## Local Configuration

Firebase web config lives in:

```text
firebase/public/firebase-config.js
```

Shape:

```js
window.TTPAA_FIREBASE_CONFIG = {
  apiKey: "...",
  authDomain: "ttpaa-c64a6.firebaseapp.com",
  projectId: "ttpaa-c64a6",
  storageBucket: "ttpaa-c64a6.firebasestorage.app",
  messagingSenderId: "...",
  appId: "..."
};

window.TTPAA_CHATBOT_CONFIG = {
  endpointUrl: "https://script.google.com/macros/s/.../exec"
};

window.TTPAA_EXPENSE_SYNC_CONFIG = {
  endpointUrl: "https://script.google.com/macros/s/.../exec"
};
```

`TTPAA_FIREBASE_CONFIG.apiKey` is a Firebase web API key, not a server secret. `GEMINI_API_KEY` must never be placed here.

## Apps Script Gemini Endpoint

The Apps Script source is:

```text
integrations/apps-script-policy-chatbot.gs
```

Create a Google Apps Script project:

```text
https://script.google.com/
```

Replace `Code.gs` with the contents of `integrations/apps-script-policy-chatbot.gs`.

Add Script properties:

```text
FIREBASE_WEB_API_KEY=<firebase web api key from firebase-config.js>
GEMINI_API_KEY=<Gemini API key>
GEMINI_CHAT_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODEL=gemini-2.5-flash-lite
GEMINI_THINKING_BUDGET=0
```

Deploy as:

```text
Deploy > New deployment > Web app
Execute as: Me
Who has access: Anyone
```

The endpoint still verifies Firebase Auth id tokens before calling Gemini. `Anyone` is used so the Firebase-hosted browser app can reach the Web App URL.

After deployment, put the `/exec` URL into:

```js
window.TTPAA_CHATBOT_CONFIG = {
  endpointUrl: "https://script.google.com/macros/s/.../exec"
};
```

Then redeploy Hosting.

## Apps Script Expense Sync Endpoint

The expense sync endpoint restores the old paid-expense automation without putting Google Drive or Sheets credentials in browser JavaScript.

Current flow:

```text
User
  -> submits expense with receipt images
Browser
  -> uploads images to Firebase Storage
  -> stores receipt metadata in expenseRequests/{requestId}
Admin
  -> marks request as paid
Browser
  -> calls Apps Script with Firebase idToken + expense data
Apps Script
  -> verifies Firebase login token
  -> verifies the user profile role is admin
  -> downloads receipt images
  -> saves files to Drive
  -> appends one row to Google Sheets
Browser
  -> deletes the original Firebase Storage images after Drive/Sheets sync succeeds
  -> marks receiptFiles as storageDeleted in Firestore
```

Create a separate Google Apps Script project for expense sync and replace `Code.gs` with:

```text
integrations/apps-script-expense-sync.gs
```

Add Script properties:

```text
FIREBASE_WEB_API_KEY=<firebase web api key from firebase-config.js>
FIREBASE_PROJECT_ID=ttpaa-c64a6
EXPENSE_SPREADSHEET_ID=<target Google spreadsheet id>
EXPENSE_SHEET_NAME=buffer
EXPENSE_DRIVE_FOLDER_ID=<target Drive folder id>
```

Deploy as:

```text
Deploy > New deployment > Web app
Execute as: Me
Who has access: Anyone
```

The Web App is publicly reachable, but the script rejects calls without a valid Firebase id token and an admin `users/{uid}.role`.

After deployment, put the `/exec` URL into:

```js
window.TTPAA_EXPENSE_SYNC_CONFIG = {
  endpointUrl: "https://script.google.com/macros/s/.../exec"
};
```

Then redeploy Hosting.

Receipt image files are stored in Drive with this format, then the Firebase Storage originals are deleted:

```text
YYYYMMDD_순번_아이디_사진순서.ext
```

Example:

```text
20260417_003_kimttp_01.jpg
```

The default sheet row columns are:

```text
지출일, 카테고리, 금액, 신청자명, Drive 링크, 메모, requestId, 지급일, 지급 처리자, 동기화 시각
```

## Importing Policy Data

The easiest import path uses the Firebase Web SDK and an existing admin user.

Install dependencies:

```powershell
npm install
```

Set admin credentials for an account whose Firestore profile has `role = "admin"`:

```powershell
$env:TTPAA_ADMIN_EMAIL="admin@example.com"
$env:TTPAA_ADMIN_PASSWORD="your-password"
```

Import policy data:

```powershell
npm run import:policy:client
```

This command:

- reads `data/policies/ttpaa-policy.json`
- deletes existing `policyPages` documents
- writes `policy-001` through `policy-078`
- stores `version`, `order`, `section`, `article`, `clause`, `subclause`, and `paragraph`

Append without deleting existing data:

```powershell
node scripts/import-policy-client.mjs --replace false
```

There is also an Admin SDK import script:

```powershell
npm run import:policy
```

That path requires Application Default Credentials or a service account with Firestore permissions on project `ttpaa-c64a6`.

## Firestore Security

Rules live in:

```text
firebase/firestore.rules
```

Current rules:

- signed-in users can read policy data
- signed-in users can create their own expense requests
- users can read their own expense requests
- admins can read and update all expense requests
- admins can write expense categories and policy data
- users can create their own chat query logs

Deploy after changing rules:

```powershell
firebase deploy --only firestore --project ttpaa-c64a6
```

## Development Notes

Check JavaScript syntax:

```powershell
node --check firebase/public/app.js
node --check scripts/import-policy-client.mjs
```

Validate policy JSON:

```powershell
node -e "const data=require('./data/policies/ttpaa-policy.json'); console.log(data.length, data[0].section)"
```

Deploy static app:

```powershell
firebase deploy --only hosting:ttpaa --project ttpaa-c64a6
```

If the browser keeps an old version of `app.js`, hard refresh or unregister the service worker:

```text
Chrome DevTools > Application > Service Workers > Unregister
```

## Operational Runbook

### Add User

Users can create accounts through the web app. Their profile is created as `member`.

To promote:

```text
Firestore > users > {uid} > role = "admin"
```

### Update Policy

Edit:

```text
data/policies/ttpaa-policy.json
```

Then run:

```powershell
$env:TTPAA_ADMIN_EMAIL="admin@example.com"
$env:TTPAA_ADMIN_PASSWORD="your-password"
npm run import:policy:client
```

### Change Chatbot Model

In Apps Script Script properties:

```text
GEMINI_CHAT_MODEL=gemini-2.5-flash
GEMINI_FALLBACK_MODEL=gemini-2.5-flash-lite
GEMINI_THINKING_BUDGET=0
```

Redeploy the Apps Script Web App after code changes. Script property changes usually apply without a Firebase Hosting deploy.

### Change Firebase Frontend Config

Edit:

```text
firebase/public/firebase-config.js
```

Then deploy Hosting:

```powershell
firebase deploy --only hosting:ttpaa --project ttpaa-c64a6
```

## Current Limitations

- Receipt files are uploaded to Firebase Storage first, copied to Drive when marked as paid, then deleted from Firebase Storage after a successful Drive/Sheets sync.
- Drive/Sheets automatic synchronization requires the separate Apps Script expense sync endpoint.
- The policy chatbot sends the full policy JSON to the Apps Script endpoint per question.
- Firestore policy import requires an admin Firebase Auth account or a service account with Firestore permissions.
- Account self-signup is currently possible. For stricter access, change default user role to `pending` and allow only admins to promote users to `member`.

## References

- Firebase Hosting: https://firebase.google.com/docs/hosting
- Firebase Authentication: https://firebase.google.com/docs/auth
- Cloud Firestore: https://firebase.google.com/docs/firestore
- Firestore security rules: https://firebase.google.com/docs/firestore/security/get-started
- Gemini API: https://ai.google.dev/api
