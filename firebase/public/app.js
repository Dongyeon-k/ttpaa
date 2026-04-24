import { initializeApp } from "https://www.gstatic.com/firebasejs/10.12.5/firebase-app.js";
import {
  createUserWithEmailAndPassword,
  getAuth,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  signOut
} from "https://www.gstatic.com/firebasejs/10.12.5/firebase-auth.js";
import {
  addDoc,
  collection,
  doc,
  getDoc,
  getDocs,
  getFirestore,
  limit,
  orderBy,
  query,
  runTransaction,
  serverTimestamp,
  setDoc,
  updateDoc,
  where,
  writeBatch
} from "https://www.gstatic.com/firebasejs/10.12.5/firebase-firestore.js";
import {
  deleteObject,
  getDownloadURL,
  getStorage,
  ref as storageRef,
  uploadBytes
} from "https://www.gstatic.com/firebasejs/10.12.5/firebase-storage.js";

const config = window.TTPAA_FIREBASE_CONFIG || {};
const chatbotConfig = window.TTPAA_CHATBOT_CONFIG || {};
const expenseSyncConfig = window.TTPAA_EXPENSE_SYNC_CONFIG || {};
const MAX_RECEIPT_FILES = 10;
const MAX_RECEIPT_FILE_SIZE = 10 * 1024 * 1024;

const STATUS_LABELS = {
  submitted: "제출됨",
  under_review: "검토중",
  approved: "승인",
  rejected: "반려",
  paid: "지급 완료"
};

const DEFAULT_CATEGORIES = [
  { id: "activity", name: "교우회 활동비", sortOrder: 10, active: true },
  { id: "meeting", name: "교우회 모임지출", sortOrder: 20, active: true },
  { id: "event", name: "경조사 축하금", sortOrder: 30, active: true },
  { id: "support", name: "근조기", sortOrder: 40, active: true },
  { id: "other", name: "기타 지출", sortOrder: 50, active: true }
];

let app;
let auth;
let db;
let storage;
let currentUser = null;
let currentProfile = null;
let categories = [];

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

const money = (value) => `${Number(value || 0).toLocaleString("ko-KR")}원`;

const dateText = (timestampOrDate) => {
  if (!timestampOrDate) {
    return "-";
  }
  if (typeof timestampOrDate === "string") {
    return timestampOrDate;
  }
  const date = timestampOrDate.toDate ? timestampOrDate.toDate() : new Date(timestampOrDate);
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium" }).format(date);
};

const timestampMillis = (timestampOrDate) => {
  if (!timestampOrDate) {
    return 0;
  }
  if (timestampOrDate.toMillis) {
    return timestampOrDate.toMillis();
  }
  if (timestampOrDate.toDate) {
    return timestampOrDate.toDate().getTime();
  }
  return new Date(timestampOrDate).getTime() || 0;
};

const timestampToIso = (timestampOrDate) => {
  if (!timestampOrDate) {
    return "";
  }
  if (typeof timestampOrDate === "string") {
    return timestampOrDate;
  }
  const date = timestampOrDate.toDate ? timestampOrDate.toDate() : new Date(timestampOrDate);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
};

const showNotice = (message, type = "info") => {
  const notice = $("#notice");
  notice.textContent = message;
  notice.className = `notice show ${type}`;
  window.setTimeout(() => {
    notice.className = "notice";
  }, 4200);
};

const safeText = (value) => {
  const span = document.createElement("span");
  span.textContent = value ?? "";
  return span.innerHTML;
};

const renderInlineMarkdown = (value) =>
  safeText(value)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>");

const markdownBlock = (lines) => {
  if (!lines.length) {
    return "";
  }

  if (lines.every((line) => /^[-*]\s+/.test(line))) {
    return `<ul>${lines
      .map((line) => `<li>${renderInlineMarkdown(line.replace(/^[-*]\s+/, ""))}</li>`)
      .join("")}</ul>`;
  }

  if (lines.every((line) => /^\d+\.\s+/.test(line))) {
    return `<ol>${lines
      .map((line) => `<li>${renderInlineMarkdown(line.replace(/^\d+\.\s+/, ""))}</li>`)
      .join("")}</ol>`;
  }

  if (lines.length === 1) {
    const heading = lines[0].match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = Math.min(heading[1].length + 2, 4);
      return `<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`;
    }
  }

  return `<p>${lines.map(renderInlineMarkdown).join("<br>")}</p>`;
};

const renderMarkdown = (value) => {
  const blocks = String(value || "")
    .replace(/\r\n/g, "\n")
    .split(/\n{2,}/)
    .map((block) => block.split("\n").map((line) => line.trim()).filter(Boolean))
    .filter((lines) => lines.length);

  if (!blocks.length) {
    return "<p>답변을 받지 못했습니다.</p>";
  }

  return blocks.map(markdownBlock).join("");
};

const assertFirebaseConfig = () => {
  if (!config.apiKey || config.apiKey === "REPLACE_ME") {
    throw new Error("firebase/public/firebase-config.js에 Firebase Web App 설정을 넣어주세요.");
  }
};

const initFirebase = () => {
  assertFirebaseConfig();
  app = initializeApp(config);
  auth = getAuth(app);
  db = getFirestore(app);
  storage = getStorage(app);
};

const ensureProfile = async (user) => {
  const ref = doc(db, "users", user.uid);
  const snapshot = await getDoc(ref);
  if (snapshot.exists()) {
    return snapshot.data();
  }

  const profile = {
    uid: user.uid,
    email: user.email || "",
    displayName: user.displayName || user.email?.split("@")[0] || "member",
    role: "member",
    createdAt: serverTimestamp(),
    updatedAt: serverTimestamp()
  };

  await setDoc(ref, profile);
  return profile;
};

const isAdmin = () => currentProfile?.role === "admin";

const setSignedInUi = async (user) => {
  currentUser = user;
  currentProfile = await ensureProfile(user);
  $("#auth-screen").hidden = true;
  $("#app-shell").hidden = false;
  $("#sign-out-button").hidden = false;
  $("#dashboard-greeting").textContent = `${currentProfile.displayName || currentUser.email}님, 반갑습니다.`;
  $("#role-pill").textContent = currentProfile.role || "member";

  $$("[data-admin-only]").forEach((element) => {
    element.hidden = !isAdmin();
  });

  await loadCategories();
  await renderRoute();
};

const setSignedOutUi = () => {
  currentUser = null;
  currentProfile = null;
  $("#auth-screen").hidden = false;
  $("#app-shell").hidden = true;
  $("#sign-out-button").hidden = true;
};

const loadCategories = async () => {
  const snapshot = await getDocs(query(collection(db, "expenseCategories"), orderBy("sortOrder", "asc")));
  categories = snapshot.docs.map((entry) => ({ id: entry.id, ...entry.data() })).filter((category) => category.active);

  if (!categories.length) {
    categories = DEFAULT_CATEGORIES;
  }

  const select = $("#expense-category");
  select.innerHTML = categories
    .map((category) => `<option value="${safeText(category.name)}">${safeText(category.name)}</option>`)
    .join("");
};

const seedCategories = async () => {
  const batch = writeBatch(db);
  DEFAULT_CATEGORIES.forEach((category) => {
    batch.set(doc(db, "expenseCategories", category.id), {
      name: category.name,
      sortOrder: category.sortOrder,
      active: true,
      updatedAt: serverTimestamp()
    });
  });
  await batch.commit();
  await loadCategories();
  showNotice("기본 카테고리를 저장했습니다.");
};

const readMyExpenses = async (count = 50) => {
  const snapshot = await getDocs(
    query(
      collection(db, "expenseRequests"),
      where("requesterUid", "==", currentUser.uid),
      limit(count)
    )
  );
  return snapshot.docs
    .map((entry) => ({ id: entry.id, ...entry.data() }))
    .sort((a, b) => timestampMillis(b.createdAt) - timestampMillis(a.createdAt));
};

const readAdminExpenses = async () => {
  const status = $("#admin-status-filter").value;
  const constraints = [limit(100)];
  if (status) {
    constraints.unshift(where("status", "==", status));
  }
  const snapshot = await getDocs(query(collection(db, "expenseRequests"), ...constraints));
  return snapshot.docs
    .map((entry) => ({ id: entry.id, ...entry.data() }))
    .sort((a, b) => timestampMillis(b.createdAt) - timestampMillis(a.createdAt));
};

const expenseItem = (expense, options = {}) => {
  const statusClass = `status-${expense.status || "submitted"}`;
  const receiptFiles = Array.isArray(expense.receiptFiles) ? expense.receiptFiles : [];
  const receipt = expense.receiptUrl
    ? `<a href="${safeText(expense.receiptUrl)}" target="_blank" rel="noreferrer">자료 열기</a>`
    : receiptFiles.length
      ? `${receiptFiles.length}개 첨부`
      : "자료 없음";
  const receiptFileHtml = receiptFiles.length
    ? `<div class="attachment-list">${receiptFiles
        .map(
          (file, index) => file.storageDeleted
            ? `<span>원본 삭제됨 ${index + 1}</span>`
            : `<a href="${safeText(file.downloadUrl)}" target="_blank" rel="noreferrer">첨부 ${index + 1}</a>`
        )
        .join("")}</div>`
    : "";
  const syncedFiles = Array.isArray(expense.syncedDriveFiles) ? expense.syncedDriveFiles : [];
  const syncHtml =
    expense.syncState && expense.syncState !== "manual"
      ? `<p class="sync-state"><strong>Drive/Sheets:</strong> ${safeText(syncLabel(expense.syncState))}
          ${expense.syncError ? ` · ${safeText(expense.syncError)}` : ""}
        </p>`
      : "";
  const cleanupHtml =
    expense.storageCleanupState
      ? `<p class="sync-state"><strong>Firebase Storage 원본:</strong> ${safeText(cleanupLabel(expense.storageCleanupState))}
          ${expense.storageCleanupError ? ` · ${safeText(expense.storageCleanupError)}` : ""}
        </p>`
      : "";
  const syncedFileHtml = syncedFiles.length
    ? `<div class="attachment-list">${syncedFiles
        .map(
          (file, index) =>
            `<a href="${safeText(file.url)}" target="_blank" rel="noreferrer">Drive 저장본 ${index + 1}</a>`
        )
        .join("")}</div>`
    : "";
  const adminActions =
    options.admin && isAdmin()
      ? `<div class="item-actions" data-expense-actions="${expense.id}">
          <button class="secondary-button" data-status="under_review" type="button">검토중</button>
          <button class="secondary-button" data-status="approved" type="button">승인</button>
          <button class="secondary-button" data-status="rejected" type="button">반려</button>
          <button data-status="paid" type="button">지급 완료</button>
        </div>`
      : "";

  return `<article class="item">
    <div class="item-header">
      <div>
        <p class="item-title">${safeText(expense.category)} · ${money(expense.amountKrw)}</p>
        <div class="item-meta">
          <span>${safeText(expense.requesterName || expense.requesterEmail || "신청자")}</span>
          <span>지출일 ${safeText(expense.expenseDate || "-")}</span>
          <span>신청 ${dateText(expense.createdAt)}</span>
          <span>${receipt}</span>
        </div>
      </div>
      <span class="status-pill ${statusClass}">${STATUS_LABELS[expense.status] || expense.status}</span>
    </div>
    ${expense.comment ? `<p>${safeText(expense.comment)}</p>` : ""}
    ${receiptFileHtml}
    ${syncHtml}
    ${cleanupHtml}
    ${syncedFileHtml}
    ${expense.adminNote ? `<p><strong>관리 메모:</strong> ${safeText(expense.adminNote)}</p>` : ""}
    ${expense.rejectionReason ? `<p><strong>반려 사유:</strong> ${safeText(expense.rejectionReason)}</p>` : ""}
    ${adminActions}
  </article>`;
};

const syncLabel = (state) =>
  ({
    pending: "대기",
    syncing: "동기화 중",
    synced: "완료",
    failed: "실패",
    skipped: "건너뜀",
    manual: "수동"
  })[state] || state;

const cleanupLabel = (state) =>
  ({
    deleted: "삭제 완료",
    failed: "삭제 실패",
    skipped: "삭제할 원본 없음"
  })[state] || state;

const renderDashboard = async () => {
  const expenses = await readMyExpenses(20);
  $("#stat-my-total").textContent = expenses.length;
  $("#stat-pending").textContent = expenses.filter((item) => ["submitted", "under_review", "approved"].includes(item.status)).length;
  $("#stat-paid").textContent = expenses.filter((item) => item.status === "paid").length;
  $("#dashboard-recent").innerHTML = expenses.length
    ? expenses.slice(0, 5).map((expense) => expenseItem(expense)).join("")
    : `<p class="empty-state">아직 신청한 지출이 없습니다.</p>`;
};

const renderMyExpenses = async () => {
  const expenses = await readMyExpenses();
  $("#my-expense-list").innerHTML = expenses.length
    ? expenses.map((expense) => expenseItem(expense)).join("")
    : `<p class="empty-state">신청 내역이 비어 있습니다.</p>`;
};

const renderAdmin = async () => {
  if (!isAdmin()) {
    $("#admin-expense-list").innerHTML = `<p class="empty-state">관리자 권한이 필요합니다.</p>`;
    return;
  }
  const expenses = await readAdminExpenses();
  $("#admin-expense-list").innerHTML = expenses.length
    ? expenses.map((expense) => expenseItem(expense, { admin: true })).join("")
    : `<p class="empty-state">검토할 신청이 없습니다.</p>`;
};

const setRoute = (route) => {
  $$("[data-page]").forEach((page) => {
    page.hidden = page.dataset.page !== route;
  });
  $$("[data-route-link]").forEach((link) => {
    link.classList.toggle("active", link.dataset.routeLink === route);
  });
};

const routeFromHash = () => window.location.hash.replace("#", "") || "dashboard";

const renderRoute = async () => {
  const route = routeFromHash();
  const guardedRoute = route === "admin" && !isAdmin() ? "dashboard" : route;
  setRoute(guardedRoute);

  if (guardedRoute === "dashboard") {
    await renderDashboard();
  } else if (guardedRoute === "my-expenses") {
    await renderMyExpenses();
  } else if (guardedRoute === "admin") {
    await renderAdmin();
  }
};

const createExpense = async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  button.textContent = "저장 중";
  try {
    const requestRef = doc(collection(db, "expenseRequests"));
    const receiptFiles = await uploadReceiptFiles(requestRef.id, Array.from($("#expense-receipt-files").files || []));

    await setDoc(requestRef, {
      requesterUid: currentUser.uid,
      requesterEmail: currentUser.email || "",
      requesterName: currentProfile.displayName || currentUser.email || "",
      expenseDate: $("#expense-date").value,
      category: $("#expense-category").value,
      amountKrw: Number($("#expense-amount").value),
      receiptUrl: $("#expense-receipt-url").value.trim(),
      receiptFiles,
      comment: $("#expense-comment").value.trim(),
      status: "submitted",
      syncState: "manual",
      createdAt: serverTimestamp(),
      updatedAt: serverTimestamp()
    });
    event.target.reset();
    showNotice("지출 신청을 저장했습니다.");
    window.location.hash = "my-expenses";
    await renderRoute();
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "신청하기";
  }
};

const uploadReceiptFiles = async (expenseId, files) => {
  if (files.length > MAX_RECEIPT_FILES) {
    throw new Error(`첨부 이미지는 최대 ${MAX_RECEIPT_FILES}개까지 가능합니다.`);
  }

  const uploads = [];
  for (const [index, file] of files.entries()) {
    if (!file.type.startsWith("image/")) {
      throw new Error("이미지 파일만 첨부할 수 있습니다.");
    }
    if (file.size > MAX_RECEIPT_FILE_SIZE) {
      throw new Error("첨부 이미지는 파일당 10MB 이하만 가능합니다.");
    }

    const path = `receipts/${currentUser.uid}/${expenseId}/${String(index + 1).padStart(2, "0")}-${safeFileName(file.name)}`;
    const fileRef = storageRef(storage, path);
    await uploadBytes(fileRef, file, {
      contentType: file.type,
      customMetadata: {
        expenseId,
        uploaderUid: currentUser.uid
      }
    });
    const downloadUrl = await getDownloadURL(fileRef);
    uploads.push({
      order: index + 1,
      name: file.name,
      contentType: file.type,
      size: file.size,
      storagePath: path,
      downloadUrl
    });
  }
  return uploads;
};

const safeFileName = (value) =>
  String(value || "receipt")
    .replace(/[\\/:*?"<>|#%{}~&]/g, "_")
    .replace(/\s+/g, "_")
    .slice(0, 80);

const transitionExpense = async (expenseId, status) => {
  const note = window.prompt("관리 메모를 입력하세요.", "") || "";
  const extra = {};
  if (status === "rejected") {
    extra.rejectionReason = window.prompt("반려 사유를 입력하세요.", "") || "";
  }
  if (status === "paid") {
    extra.paymentDate = new Date().toISOString().slice(0, 10);
    extra.paidByUid = currentUser.uid;
    extra.paidByName = currentProfile.displayName || currentUser.email || "";
    extra.syncState = "pending";
    extra.syncError = "";
  }

  const requestRef = doc(db, "expenseRequests", expenseId);
  const expenseForSync = await runTransaction(db, async (transaction) => {
    const snapshot = await transaction.get(requestRef);
    if (!snapshot.exists()) {
      throw new Error("신청을 찾을 수 없습니다.");
    }
    const previous = snapshot.data();
    transaction.update(requestRef, {
      status,
      adminNote: note,
      ...extra,
      updatedAt: serverTimestamp()
    });
    transaction.set(doc(collection(requestRef, "statusHistory")), {
      fromStatus: previous.status || "",
      toStatus: status,
      note,
      changedByUid: currentUser.uid,
      changedByName: currentProfile.displayName || currentUser.email || "",
      createdAt: serverTimestamp()
    });
    return {
      id: expenseId,
      ...previous,
      status,
      adminNote: note,
      ...extra
    };
  });

  showNotice(`상태를 ${STATUS_LABELS[status]}로 변경했습니다.`);
  if (status === "paid") {
    await syncPaidExpense(expenseForSync);
  }
  await renderAdmin();
};

const syncPaidExpense = async (expense) => {
  const endpointUrl = (expenseSyncConfig.endpointUrl || "").trim();
  const requestRef = doc(db, "expenseRequests", expense.id);

  if (!endpointUrl) {
    await updateDoc(requestRef, {
      syncState: "skipped",
      syncError: "expense sync endpointUrl이 설정되지 않았습니다.",
      updatedAt: serverTimestamp()
    });
    showNotice("지급 완료는 저장했지만 Drive/Sheets endpoint가 설정되지 않았습니다.", "error");
    return;
  }

  await updateDoc(requestRef, {
    syncState: "syncing",
    syncError: "",
    updatedAt: serverTimestamp()
  });

  try {
    const idToken = await currentUser.getIdToken();
    const result = await callExpenseSync({ endpointUrl, idToken, expense: serializeExpense(expense) });
    await updateDoc(requestRef, {
      syncState: "synced",
      syncError: "",
      syncSheetRow: result.sheetRow || null,
      syncedDriveFiles: result.driveFiles || [],
      syncedAt: serverTimestamp(),
      updatedAt: serverTimestamp()
    });

    try {
      const cleanup = await deleteSyncedReceiptFiles(expense.receiptFiles || []);
      await updateDoc(requestRef, {
        receiptFiles: cleanup.files,
        storageCleanupState: cleanup.deletedCount ? "deleted" : "skipped",
        storageCleanupError: "",
        storageCleanedAt: serverTimestamp(),
        updatedAt: serverTimestamp()
      });
      showNotice("지급 완료, Drive/Sheets 동기화, Firebase Storage 원본 삭제를 마쳤습니다.");
    } catch (cleanupError) {
      await updateDoc(requestRef, {
        storageCleanupState: "failed",
        storageCleanupError: cleanupError.message,
        updatedAt: serverTimestamp()
      });
      showNotice(`Drive/Sheets 동기화는 완료했지만 Storage 원본 삭제에 실패했습니다: ${cleanupError.message}`, "error");
    }
  } catch (error) {
    await updateDoc(requestRef, {
      syncState: "failed",
      syncError: error.message,
      updatedAt: serverTimestamp()
    });
    showNotice(`지급 완료는 저장했지만 Drive/Sheets 동기화에 실패했습니다: ${error.message}`, "error");
  }
};

const deleteSyncedReceiptFiles = async (receiptFiles) => {
  const files = [];
  let deletedCount = 0;

  for (const file of receiptFiles) {
    if (!file.storagePath || file.storageDeleted) {
      files.push(file);
      continue;
    }

    try {
      await deleteObject(storageRef(storage, file.storagePath));
      deletedCount += 1;
      files.push({
        ...file,
        storageDeleted: true,
        storageDeletedAt: new Date().toISOString()
      });
    } catch (error) {
      if (error.code === "storage/object-not-found") {
        files.push({
          ...file,
          storageDeleted: true,
          storageDeletedAt: new Date().toISOString()
        });
        continue;
      }
      throw error;
    }
  }

  return { files, deletedCount };
};

const serializeExpense = (expense) => ({
  ...expense,
  createdAt: timestampToIso(expense.createdAt),
  updatedAt: timestampToIso(expense.updatedAt),
  receiptFiles: Array.isArray(expense.receiptFiles) ? expense.receiptFiles : []
});

const callExpenseSync = async ({ endpointUrl, idToken, expense }) => {
  const response = await fetch(endpointUrl, {
    method: "POST",
    headers: {
      "Content-Type": "text/plain;charset=utf-8"
    },
    body: JSON.stringify({
      idToken,
      expense
    })
  });

  if (!response.ok) {
    throw new Error(`Drive/Sheets 동기화 요청에 실패했습니다. (${response.status})`);
  }

  const result = await response.json();
  if (!result.ok) {
    throw new Error(result.error || "Drive/Sheets 동기화에 실패했습니다.");
  }
  return result;
};

const legacySearchPolicy = async (event) => {
  event.preventDefault();
  const queryText = $("#policy-query").value.trim().toLowerCase();
  const snapshot = await getDocs(query(collection(db, "policyPages"), limit(500)));
  const results = snapshot.docs
    .map((entry) => ({ id: entry.id, ...entry.data() }))
    .filter((page) => policySearchText(page).includes(queryText))
    .sort((a, b) => policySortKey(a).localeCompare(policySortKey(b), "ko-KR"))
    .slice(0, 12);

  await addDoc(collection(db, "chatQueryLogs"), {
    userUid: currentUser.uid,
    query: queryText,
    resultCount: results.length,
    createdAt: serverTimestamp()
  });

  $("#policy-results").innerHTML = results.length
    ? results
        .map(
          (page) => `<article class="item">
            <p class="item-title">${safeText(policyCitation(page))}</p>
            <div class="item-meta">
              <span>${safeText(page.version || "규정")}</span>
            </div>
            <p>${safeText(page.paragraph || page.text || "")}</p>
          </article>`
        )
        .join("")
    : `<p class="empty-state">일치하는 문장을 찾지 못했습니다.</p>`;
};

const policySearchText = (page) =>
  Object.entries(page)
    .filter(([, value]) => ["string", "number"].includes(typeof value))
    .map(([, value]) => String(value))
    .join(" ")
    .toLowerCase();

const policySortKey = (page) =>
  [page.section || "", page.article || "", page.clause || "", page.createdAt?.seconds || ""].join(" ");

const policyCitation = (page) =>
  [page.section, page.article, page.clause]
    .filter(Boolean)
    .join(" · ") || `${page.version || "규정"} · ${page.pageNumber || "문단"}`;

const parsePolicyEntries = (rawText, version) => {
  const trimmed = rawText.trim();
  if (!trimmed) {
    return [];
  }

  try {
    const parsed = JSON.parse(trimmed);
    const items = Array.isArray(parsed) ? parsed : [parsed];
    return items
      .map((item, index) => ({
        version,
        section: String(item.section || "").trim(),
        article: String(item.article || "").trim(),
        clause: String(item.clause || "").trim(),
        paragraph: String(item.paragraph || item.text || "").trim(),
        order: Number(item.order || index + 1)
      }))
      .filter((item) => item.paragraph);
  } catch {
    return trimmed
      .split(/\n{2,}|\r?\n/)
      .map((line, index) => ({
        version,
        section: "",
        article: "",
        clause: "",
        paragraph: line.trim(),
        order: index + 1
      }))
      .filter((item) => item.paragraph);
  }
};

const importPolicy = async (event) => {
  event.preventDefault();
  const version = $("#policy-version").value.trim() || "운영 규정";
  const entries = parsePolicyEntries($("#policy-text").value, version);

  if (!entries.length) {
    showNotice("저장할 규정 텍스트가 없습니다.", "error");
    return;
  }

  const batch = writeBatch(db);
  entries.slice(0, 400).forEach((entry) => {
    batch.set(doc(collection(db, "policyPages")), {
      ...entry,
      createdAt: serverTimestamp(),
      updatedAt: serverTimestamp()
    });
  });
  await batch.commit();
  event.target.reset();
  showNotice(`${entries.length}개 조항을 저장했습니다.`);
};

const searchPolicy = async (event) => {
  event.preventDefault();
  const button = event.submitter;
  const question = $("#policy-query").value.trim();
  const endpointUrl = (chatbotConfig.endpointUrl || "").trim();

  if (!endpointUrl) {
    showNotice("챗봇 API endpointUrl을 firebase-config.js에 설정해주세요.", "error");
    return;
  }

  button.disabled = true;
  button.textContent = "답변 중";

  try {
    const policies = await readPolicyPages();
    const idToken = await currentUser.getIdToken();
    const result = await callPolicyChatbot({ endpointUrl, question, policies, idToken });

    await addDoc(collection(db, "chatQueryLogs"), {
      userUid: currentUser.uid,
      query: question,
      resultCount: Array.isArray(result.evidence) ? result.evidence.length : 0,
      answer: result.answer || "",
      createdAt: serverTimestamp()
    });

    renderPolicyAnswer(result);
  } catch (error) {
    showNotice(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "검색";
  }
};

const readPolicyPages = async () => {
  const snapshot = await getDocs(query(collection(db, "policyPages"), limit(500)));
  return snapshot.docs
    .map((entry) => policyPayloadItem(entry.id, entry.data()))
    .sort((a, b) => policySortKey(a).localeCompare(policySortKey(b), "ko-KR"));
};

const policyPayloadItem = (id, page) => {
  const item = { id };
  Object.entries(page).forEach(([key, value]) => {
    if (["string", "number", "boolean"].includes(typeof value)) {
      item[key] = value;
    }
  });
  return item;
};

const callPolicyChatbot = async ({ endpointUrl, question, policies, idToken }) => {
  const response = await fetch(endpointUrl, {
    method: "POST",
    headers: {
      "Content-Type": "text/plain;charset=utf-8"
    },
    body: JSON.stringify({
      question,
      idToken,
      user: {
        uid: currentUser.uid,
        email: currentUser.email || "",
        role: currentProfile?.role || "member"
      },
      policies
    })
  });

  if (!response.ok) {
    throw new Error(`챗봇 API 요청에 실패했습니다. (${response.status})`);
  }

  const result = await response.json();
  if (typeof result === "string") {
    return { answer: result, evidence: [] };
  }
  return {
    answer: result.answer || result.text || "",
    evidence: result.evidence || result.citations || [],
    error: result.error || ""
  };
};

const renderPolicyAnswer = (result) => {
  const evidence = Array.isArray(result.evidence) ? result.evidence : [];
  const evidenceHtml = evidence.length
    ? evidence
        .map(
          (page) => `<article class="item">
            <p class="item-title">${safeText(policyCitation(page))}</p>
            <div class="item-meta">
              <span>${safeText(page.version || "규정")}</span>
            </div>
            <p>${safeText(page.paragraph || page.text || "")}</p>
          </article>`
        )
        .join("")
    : `<p class="empty-state">제시된 근거 조항이 없습니다.</p>`;

  const errorHtml = result.error
    ? `<p class="empty-state">오류 상세: ${safeText(result.error)}</p>`
    : "";

  $("#policy-results").innerHTML = `<article class="item">
    <p class="item-title">답변</p>
    <div class="markdown-answer">${renderMarkdown(result.answer || "답변을 받지 못했습니다.")}</div>
    ${errorHtml}
  </article>${evidenceHtml}`;
};

const bindEvents = () => {
  $("#auth-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await signInWithEmailAndPassword(auth, $("#auth-email").value, $("#auth-password").value);
    } catch (error) {
      showNotice(error.message, "error");
    }
  });

  $("#create-account-button").addEventListener("click", async () => {
    try {
      await createUserWithEmailAndPassword(auth, $("#auth-email").value, $("#auth-password").value);
    } catch (error) {
      showNotice(error.message, "error");
    }
  });

  $("#sign-out-button").addEventListener("click", () => signOut(auth));
  $("#expense-form").addEventListener("submit", createExpense);
  $("#seed-categories-button").addEventListener("click", seedCategories);
  $("#admin-status-filter").addEventListener("change", renderAdmin);
  $("#policy-search-form").addEventListener("submit", searchPolicy);
  $("#policy-import-form").addEventListener("submit", importPolicy);

  $("#admin-expense-list").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-status]");
    const actionWrap = event.target.closest("[data-expense-actions]");
    if (!button || !actionWrap) {
      return;
    }
    button.disabled = true;
    try {
      await transitionExpense(actionWrap.dataset.expenseActions, button.dataset.status);
    } catch (error) {
      showNotice(error.message, "error");
    } finally {
      button.disabled = false;
    }
  });

  window.addEventListener("hashchange", renderRoute);

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/service-worker.js").catch(() => {});
    });
  }
};

const boot = async () => {
  try {
    initFirebase();
    bindEvents();
    onAuthStateChanged(auth, async (user) => {
      if (user) {
        try {
          await setSignedInUi(user);
        } catch (error) {
          showNotice(error.message, "error");
        }
      } else {
        setSignedOutUi();
      }
    });
  } catch (error) {
    $("#auth-screen").innerHTML = `<div class="auth-form"><h1>설정이 필요합니다.</h1><p>${safeText(error.message)}</p></div>`;
  }
};

boot();
