import { readFile } from "node:fs/promises";
import process from "node:process";
import { initializeApp } from "firebase/app";
import { getAuth, signInWithEmailAndPassword } from "firebase/auth";
import {
  collection,
  deleteDoc,
  doc,
  getDocs,
  getFirestore,
  limit,
  query,
  serverTimestamp,
  writeBatch
} from "firebase/firestore";

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

const email = process.env.TTPAA_ADMIN_EMAIL || args.get("email");
const password = process.env.TTPAA_ADMIN_PASSWORD || args.get("password");
const filePath = args.get("file") || "data/policies/ttpaa-policy.json";
const version = args.get("version") || "TTPAA 회칙";
const replace = args.get("replace") !== "false";

if (!email || !password) {
  throw new Error(
    "Set TTPAA_ADMIN_EMAIL and TTPAA_ADMIN_PASSWORD, or pass --email and --password. The account must have users/{uid}.role = admin."
  );
}

const app = initializeApp({
  apiKey: "AIzaSyA6J-xsccvxF86-uGrkNADskBxmuyPL9ms",
  authDomain: "ttpaa-c64a6.firebaseapp.com",
  projectId: "ttpaa-c64a6",
  storageBucket: "ttpaa-c64a6.firebasestorage.app",
  messagingSenderId: "169643496194",
  appId: "1:169643496194:web:f223035c08f14b8c98681b"
});

const auth = getAuth(app);
const db = getFirestore(app);

await signInWithEmailAndPassword(auth, email, password);

const raw = await readFile(filePath, "utf8");
const entries = JSON.parse(raw);

if (!Array.isArray(entries) || entries.length === 0) {
  throw new Error(`${filePath} must contain a non-empty JSON array.`);
}

const policyRef = collection(db, "policyPages");

if (replace) {
  await deleteCollection(policyRef);
}

let batch = writeBatch(db);
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
    createdAt: serverTimestamp(),
    updatedAt: serverTimestamp()
  };

  if (!document.paragraph) {
    return;
  }

  const id = `policy-${String(index + 1).padStart(3, "0")}`;
  batch.set(doc(db, "policyPages", id), document);
  count += 1;
});

await batch.commit();

console.log(`Imported ${count} policy documents into policyPages.`);

async function deleteCollection(collectionRef) {
  while (true) {
    const snapshot = await getDocs(query(collectionRef, limit(450)));
    if (snapshot.empty) {
      return;
    }
    await Promise.all(snapshot.docs.map((documentSnapshot) => deleteDoc(documentSnapshot.ref)));
  }
}
