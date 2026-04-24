import { readFile } from "node:fs/promises";
import process from "node:process";
import admin from "firebase-admin";

const args = new Map();
for (let index = 2; index < process.argv.length; index += 1) {
  const arg = process.argv[index];
  if (arg.startsWith("--")) {
    const key = arg.slice(2);
    const next = process.argv[index + 1];
    if (next && !next.startsWith("--")) {
      args.set(key, next);
      index += 1;
    } else {
      args.set(key, "true");
    }
  }
}

const projectId = args.get("project") || process.env.GCLOUD_PROJECT || "ttpaa-c64a6";
const filePath = args.get("file") || "data/policies/ttpaa-policy.json";
const version = args.get("version") || "TTPAA 회칙";
const replace = args.get("replace") !== "false";

admin.initializeApp({
  credential: admin.credential.applicationDefault(),
  projectId
});

const db = admin.firestore();
const policyRef = db.collection("policyPages");

const raw = await readFile(filePath, "utf8");
const entries = JSON.parse(raw);

if (!Array.isArray(entries) || entries.length === 0) {
  throw new Error(`${filePath} must contain a non-empty JSON array.`);
}

if (replace) {
  await deleteCollection(policyRef);
}

let batch = db.batch();
let count = 0;

entries.forEach((entry, index) => {
  const document = {
    version,
    order: index + 1,
    section: String(entry.section || "").trim(),
    article: String(entry.article || "").trim(),
    clause: String(entry.clause || "").trim(),
    subclause: String(entry.subclause || "").trim(),
    paragraph: String(entry.paragraph || entry.text || "").trim(),
    createdAt: admin.firestore.FieldValue.serverTimestamp(),
    updatedAt: admin.firestore.FieldValue.serverTimestamp()
  };

  if (!document.paragraph) {
    return;
  }

  const id = `policy-${String(index + 1).padStart(3, "0")}`;
  batch.set(policyRef.doc(id), document);
  count += 1;

  if (count % 450 === 0) {
    batch.commit();
    batch = db.batch();
  }
});

await batch.commit();

console.log(`Imported ${count} policy documents into ${projectId}/policyPages.`);

async function deleteCollection(collectionRef) {
  const snapshot = await collectionRef.limit(450).get();
  if (snapshot.empty) {
    return;
  }

  const deleteBatch = db.batch();
  snapshot.docs.forEach((doc) => deleteBatch.delete(doc.ref));
  await deleteBatch.commit();
  await deleteCollection(collectionRef);
}
