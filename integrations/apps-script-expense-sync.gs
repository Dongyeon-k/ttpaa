const EXPENSE_SYNC_VERSION = "expense-sync-2026-04-17-v1";

function doGet() {
  return jsonResponse({
    ok: true,
    version: EXPENSE_SYNC_VERSION,
    service: "expense-sync"
  });
}

function doPost(e) {
  try {
    const payload = JSON.parse((e.postData && e.postData.contents) || "{}");
    const idToken = String(payload.idToken || "");
    const expense = payload.expense || {};

    if (!idToken) {
      throw new Error("missing_id_token");
    }
    if (!expense.id) {
      throw new Error("missing_expense_id");
    }

    const firebaseUser = verifyFirebaseUser(idToken);
    verifyAdminUser(idToken, firebaseUser.localId);

    const result = syncExpenseToDriveAndSheet(expense);
    return jsonResponse({
      ok: true,
      version: EXPENSE_SYNC_VERSION,
      sheetRow: result.sheetRow,
      driveFiles: result.driveFiles
    });
  } catch (error) {
    const message = String(error && error.message ? error.message : error);
    return jsonResponse({
      ok: false,
      version: EXPENSE_SYNC_VERSION,
      error: message
    });
  }
}

function verifyFirebaseUser(idToken) {
  const firebaseApiKey = PropertiesService.getScriptProperties().getProperty("FIREBASE_WEB_API_KEY");
  if (!firebaseApiKey) {
    throw new Error("FIREBASE_WEB_API_KEY script property is missing.");
  }

  const response = UrlFetchApp.fetch(
    "https://identitytoolkit.googleapis.com/v1/accounts:lookup?key=" + encodeURIComponent(firebaseApiKey),
    {
      method: "post",
      contentType: "application/json",
      payload: JSON.stringify({ idToken: idToken }),
      muteHttpExceptions: true
    }
  );

  if (response.getResponseCode() >= 300) {
    throw new Error("Firebase login token could not be verified: " + response.getContentText());
  }

  const body = JSON.parse(response.getContentText() || "{}");
  if (!body.users || !body.users.length) {
    throw new Error("Firebase login token is invalid.");
  }
  return body.users[0];
}

function verifyAdminUser(idToken, uid) {
  const projectId = PropertiesService.getScriptProperties().getProperty("FIREBASE_PROJECT_ID") || "ttpaa-c64a6";
  const url =
    "https://firestore.googleapis.com/v1/projects/" +
    encodeURIComponent(projectId) +
    "/databases/(default)/documents/users/" +
    encodeURIComponent(uid);

  const response = UrlFetchApp.fetch(url, {
    method: "get",
    headers: {
      Authorization: "Bearer " + idToken
    },
    muteHttpExceptions: true
  });

  if (response.getResponseCode() >= 300) {
    throw new Error("Admin profile could not be loaded: " + response.getContentText());
  }

  const body = JSON.parse(response.getContentText() || "{}");
  const role = (((body.fields || {}).role || {}).stringValue || "");
  if (role !== "admin") {
    throw new Error("Admin role is required.");
  }
}

function syncExpenseToDriveAndSheet(expense) {
  const spreadsheetId = PropertiesService.getScriptProperties().getProperty("EXPENSE_SPREADSHEET_ID");
  const sheetName = PropertiesService.getScriptProperties().getProperty("EXPENSE_SHEET_NAME") || "buffer";
  const folderId = PropertiesService.getScriptProperties().getProperty("EXPENSE_DRIVE_FOLDER_ID");

  if (!spreadsheetId) {
    throw new Error("EXPENSE_SPREADSHEET_ID script property is missing.");
  }
  if (!folderId) {
    throw new Error("EXPENSE_DRIVE_FOLDER_ID script property is missing.");
  }

  const spreadsheet = SpreadsheetApp.openById(spreadsheetId);
  const sheet = spreadsheet.getSheetByName(sheetName) || spreadsheet.insertSheet(sheetName);
  const existingRow = findRequestRow(sheet, String(expense.id));
  if (existingRow) {
    return {
      sheetRow: existingRow,
      driveFiles: []
    };
  }

  const sheetRow = Math.max(sheet.getLastRow() + 1, 1);
  const sequence = String(sheetRow).padStart(3, "0");
  const driveFiles = saveReceiptFiles(expense, sequence, folderId);
  const driveLinks = driveFiles.map(function (file) {
    return file.url;
  }).join("\n");

  sheet.appendRow([
    expense.expenseDate || "",
    expense.category || "",
    Number(expense.amountKrw || 0),
    expense.requesterName || "",
    driveLinks || expense.receiptUrl || "",
    expense.comment || "",
    expense.id || "",
    expense.paymentDate || "",
    expense.paidByName || "",
    new Date()
  ]);

  return {
    sheetRow: sheet.getLastRow(),
    driveFiles: driveFiles
  };
}

function saveReceiptFiles(expense, sequence, folderId) {
  const folder = DriveApp.getFolderById(folderId);
  const receiptFiles = Array.isArray(expense.receiptFiles) ? expense.receiptFiles : [];
  const ymd = compactDate(expense.expenseDate || expense.paymentDate || new Date());
  const userId = sanitizeFilePart(userIdFromExpense(expense));

  return receiptFiles.map(function (receipt, index) {
    if (!receipt.downloadUrl) {
      throw new Error("Receipt file is missing downloadUrl.");
    }

    const response = UrlFetchApp.fetch(receipt.downloadUrl, {
      method: "get",
      muteHttpExceptions: true
    });
    if (response.getResponseCode() >= 300) {
      throw new Error("Receipt download failed: " + response.getContentText());
    }

    const extension = fileExtension(receipt.name, receipt.contentType);
    const photoOrder = String(index + 1).padStart(2, "0");
    const fileName = [ymd, sequence, userId, photoOrder].join("_") + "." + extension;
    const blob = response.getBlob().setName(fileName);
    const file = folder.createFile(blob);

    return {
      name: fileName,
      id: file.getId(),
      url: file.getUrl()
    };
  });
}

function findRequestRow(sheet, requestId) {
  if (!requestId || sheet.getLastRow() < 1) {
    return 0;
  }

  const values = sheet.getRange(1, 7, sheet.getLastRow(), 1).getValues();
  for (let index = 0; index < values.length; index += 1) {
    if (String(values[index][0] || "") === requestId) {
      return index + 1;
    }
  }
  return 0;
}

function compactDate(value) {
  if (value instanceof Date) {
    return Utilities.formatDate(value, "Asia/Seoul", "yyyyMMdd");
  }

  const text = String(value || "");
  const match = text.match(/^(\d{4})-?(\d{2})-?(\d{2})/);
  if (match) {
    return match[1] + match[2] + match[3];
  }

  return Utilities.formatDate(new Date(), "Asia/Seoul", "yyyyMMdd");
}

function userIdFromExpense(expense) {
  const email = String(expense.requesterEmail || "");
  if (email.indexOf("@") > 0) {
    return email.split("@")[0];
  }
  return expense.requesterUid || "user";
}

function sanitizeFilePart(value) {
  return String(value || "user")
    .replace(/[^A-Za-z0-9가-힣_-]+/g, "_")
    .replace(/_+/g, "_")
    .slice(0, 40);
}

function fileExtension(name, contentType) {
  const fileName = String(name || "");
  const match = fileName.match(/\.([A-Za-z0-9]+)$/);
  if (match) {
    return match[1].toLowerCase();
  }

  const type = String(contentType || "").toLowerCase();
  if (type.indexOf("png") >= 0) {
    return "png";
  }
  if (type.indexOf("webp") >= 0) {
    return "webp";
  }
  if (type.indexOf("gif") >= 0) {
    return "gif";
  }
  if (type.indexOf("heic") >= 0 || type.indexOf("heif") >= 0) {
    return "heic";
  }
  return "jpg";
}

function jsonResponse(body) {
  return ContentService.createTextOutput(JSON.stringify(body)).setMimeType(ContentService.MimeType.JSON);
}
