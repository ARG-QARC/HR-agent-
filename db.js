/**
 * db.js - IndexedDB local database wrapper
 * Stores settings, jobs, and candidate evaluation records locally on the device.
 */

const DB_NAME = "LinkedInAssistantDB";
const DB_VERSION = 2;

let dbInstance = null;

export function openDB() {
  return new Promise((resolve, reject) => {
    if (dbInstance) {
      return resolve(dbInstance);
    }
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;

      // Settings store
      if (!db.objectStoreNames.contains("settings")) {
        db.createObjectStore("settings", { keyPath: "key" });
      }

      // Jobs store
      if (!db.objectStoreNames.contains("jobs")) {
        const jobStore = db.createObjectStore("jobs", { keyPath: "job_id" });
        jobStore.createIndex("created_at", "created_at", { unique: false });
      }

      // Candidates store
      if (!db.objectStoreNames.contains("candidates")) {
        const candStore = db.createObjectStore("candidates", { keyPath: "candidate_id", autoIncrement: true });
        candStore.createIndex("job_id", "job_id", { unique: false });
        candStore.createIndex("relevance_score", "relevance_score", { unique: false });
      }

      // Chat history store for persistent continuable conversation memory
      if (!db.objectStoreNames.contains("chat_history")) {
        const chatStore = db.createObjectStore("chat_history", { keyPath: "id", autoIncrement: true });
        chatStore.createIndex("timestamp", "timestamp", { unique: false });
      }
    };

    request.onsuccess = (event) => {
      dbInstance = event.target.result;
      resolve(dbInstance);
    };

    request.onerror = (event) => {
      console.error("IndexedDB error:", event.target.error);
      reject(event.target.error);
    };
  });
}

// ── Settings Helpers ──────────────────────────────────────────────────────────
export async function getSetting(key, defaultValue = "") {
  try {
    const db = await openDB();
    return new Promise((resolve) => {
      const tx = db.transaction("settings", "readonly");
      const store = tx.objectStore("settings");
      const request = store.get(key);
      request.onsuccess = () => {
        resolve(request.result ? request.result.value : defaultValue);
      };
      request.onerror = () => resolve(defaultValue);
    });
  } catch (err) {
    return defaultValue;
  }
}

export async function setSetting(key, value) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("settings", "readwrite");
    const store = tx.objectStore("settings");
    const request = store.put({ key, value });
    request.onsuccess = () => resolve(true);
    request.onerror = (e) => reject(e);
  });
}

// ── Job Helpers ───────────────────────────────────────────────────────────────
export async function getAllJobs() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("jobs", "readonly");
    const store = tx.objectStore("jobs");
    const request = store.getAll();
    request.onsuccess = () => {
      const jobs = request.result || [];
      jobs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      resolve(jobs);
    };
    request.onerror = (e) => reject(e);
  });
}

export async function addJob(job) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("jobs", "readwrite");
    const store = tx.objectStore("jobs");
    const request = store.put(job);
    request.onsuccess = () => resolve(job);
    request.onerror = (e) => reject(e);
  });
}

export async function deleteJob(job_id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("jobs", "readwrite");
    const store = tx.objectStore("jobs");
    const request = store.delete(job_id);
    request.onsuccess = () => resolve(true);
    request.onerror = (e) => reject(e);
  });
}

// ── Candidate Helpers ─────────────────────────────────────────────────────────
export async function getCandidatesByJob(job_id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("candidates", "readonly");
    const store = tx.objectStore("candidates");
    const index = store.index("job_id");
    const request = index.getAll(job_id);
    request.onsuccess = () => {
      const candidates = request.result || [];
      candidates.sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0));
      resolve(candidates);
    };
    request.onerror = (e) => reject(e);
  });
}

export async function addCandidate(candidate) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("candidates", "readwrite");
    const store = tx.objectStore("candidates");
    const request = store.add(candidate);
    request.onsuccess = (event) => {
      candidate.candidate_id = event.target.result;
      resolve(candidate);
    };
    request.onerror = (e) => reject(e);
  });
}

export async function updateCandidate(candidate) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("candidates", "readwrite");
    const store = tx.objectStore("candidates");
    const request = store.put(candidate);
    request.onsuccess = () => resolve(candidate);
    request.onerror = (e) => reject(e);
  });
}

export async function deleteCandidate(candidate_id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction("candidates", "readwrite");
    const store = tx.objectStore("candidates");
    const request = store.delete(candidate_id);
    request.onsuccess = () => resolve(true);
    request.onerror = (e) => reject(e);
  });
}

// ── Chat History Memory Helpers ───────────────────────────────────────────────
export async function getChatHistory() {
  const db = await openDB();
  return new Promise((resolve) => {
    try {
      const tx = db.transaction("chat_history", "readonly");
      const store = tx.objectStore("chat_history");
      const request = store.getAll();
      request.onsuccess = () => {
        const msgs = request.result || [];
        msgs.sort((a, b) => new Date(a.timestamp || 0) - new Date(b.timestamp || 0));
        resolve(msgs);
      };
      request.onerror = () => resolve([]);
    } catch (e) {
      resolve([]);
    }
  });
}

export async function saveChatMessage(sender, text) {
  const db = await openDB();
  return new Promise((resolve) => {
    try {
      const tx = db.transaction("chat_history", "readwrite");
      const store = tx.objectStore("chat_history");
      const msg = { sender, text, timestamp: new Date().toISOString() };
      const req = store.add(msg);
      req.onsuccess = () => resolve(true);
      req.onerror = () => resolve(false);
    } catch (e) {
      resolve(false);
    }
  });
}

export async function clearChatHistory() {
  const db = await openDB();
  return new Promise((resolve) => {
    try {
      const tx = db.transaction("chat_history", "readwrite");
      const store = tx.objectStore("chat_history");
      const req = store.clear();
      req.onsuccess = () => resolve(true);
      req.onerror = () => resolve(false);
    } catch (e) {
      resolve(false);
    }
  });
}

// ── Cloud Sync & Standalone Export/Import Helpers ─────────────────────────────
export async function exportDatabaseToJSON() {
  const jobs = await getAllJobs();
  const chat_history = await getChatHistory();
  const db = await openDB();
  
  // Get settings
  const settings = await new Promise((resolve) => {
    const tx = db.transaction("settings", "readonly");
    const store = tx.objectStore("settings");
    const req = store.getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => resolve([]);
  });

  // Get all candidates across all jobs
  const candidates = await new Promise((resolve) => {
    const tx = db.transaction("candidates", "readonly");
    const store = tx.objectStore("candidates");
    const req = store.getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => resolve([]);
  });

  return {
    version: DB_VERSION,
    exported_at: new Date().toISOString(),
    settings,
    jobs,
    candidates,
    chat_history
  };
}

export async function importDatabaseFromJSON(data) {
  if (!data || (!data.jobs && !data.settings && !data.candidates)) {
    throw new Error("Invalid backup data format.");
  }
  const db = await openDB();

  // Import settings
  if (Array.isArray(data.settings)) {
    const tx = db.transaction("settings", "readwrite");
    const store = tx.objectStore("settings");
    for (const item of data.settings) {
      store.put(item);
    }
  }

  // Import jobs
  if (Array.isArray(data.jobs)) {
    const tx = db.transaction("jobs", "readwrite");
    const store = tx.objectStore("jobs");
    for (const job of data.jobs) {
      store.put(job);
    }
  }

  // Import candidates
  if (Array.isArray(data.candidates)) {
    const tx = db.transaction("candidates", "readwrite");
    const store = tx.objectStore("candidates");
    for (const cand of data.candidates) {
      store.put(cand);
    }
  }

  // Import chat_history
  if (Array.isArray(data.chat_history)) {
    const tx = db.transaction("chat_history", "readwrite");
    const store = tx.objectStore("chat_history");
    for (const msg of data.chat_history) {
      store.put(msg);
    }
  }

  return true;
}

export async function syncToCloudStorage(endpointUrl, apiKey) {
  const payload = await exportDatabaseToJSON();
  const headers = { "Content-Type": "application/json" };
  if (apiKey) {
    headers["Authorization"] = `Bearer ${apiKey}`;
    headers["X-Master-Key"] = apiKey; // Compatible with JSONBin.io & Cloud KV
  }

  const response = await fetch(endpointUrl, {
    method: "POST",
    headers,
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    throw new Error(`Cloud Sync failed with HTTP status ${response.status}`);
  }
  return await response.json();
}

export async function syncFromCloudStorage(endpointUrl, apiKey) {
  const headers = {};
  if (apiKey) {
    headers["Authorization"] = `Bearer ${apiKey}`;
    headers["X-Master-Key"] = apiKey;
  }

  const response = await fetch(endpointUrl, { method: "GET", headers });
  if (!response.ok) {
    throw new Error(`Cloud Restore failed with HTTP status ${response.status}`);
  }
  const data = await response.json();
  const payload = data.record || data.data || data;
  await importDatabaseFromJSON(payload);
  return payload;
}


