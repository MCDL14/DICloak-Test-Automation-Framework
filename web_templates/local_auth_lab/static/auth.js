"use strict";

const body = document.body;
const siteId = body.dataset.siteId;
const storageType = body.dataset.storageType;
const authKey = "dicloak_auth";

const elements = {
  status: document.querySelector('[data-testid="auth-status"]'),
  account: document.querySelector('[data-testid="current-account"]'),
  runId: document.querySelector('[data-testid="run-id"]'),
  fingerprint: document.querySelector('[data-testid="token-fingerprint"]'),
  message: document.querySelector('[data-testid="message"]'),
  tabs: document.querySelector('.tabs'),
  loginForm: document.querySelector('[data-form="login"]'),
  registerForm: document.querySelector('[data-form="register"]'),
  logoutButton: document.querySelector('[data-action="logout"]'),
};

const indexedDbAdapter = {
  async hasDatabase() {
    if (typeof indexedDB.databases !== "function") return false;
    const databases = await indexedDB.databases();
    return databases.some((item) => item.name === "dicloak_auth");
  },
  async getToken() {
    const record = await this.getRecord();
    return record && record.token ? record.token : "";
  },
  async getRecord() {
    if (!await this.hasDatabase()) return null;
    return new Promise((resolve, reject) => {
      const request = indexedDB.open("dicloak_auth", 1);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains("sessions")) {
          db.createObjectStore("sessions", { keyPath: "id" });
        }
      };
      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        const db = request.result;
        const transaction = db.transaction("sessions", "readonly");
        const getRequest = transaction.objectStore("sessions").get("current");
        getRequest.onsuccess = () => resolve(getRequest.result || null);
        getRequest.onerror = () => reject(getRequest.error);
        transaction.oncomplete = () => db.close();
      };
    });
  },
  async setToken(session) {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open("dicloak_auth", 1);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains("sessions")) {
          db.createObjectStore("sessions", { keyPath: "id" });
        }
      };
      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        const db = request.result;
        const transaction = db.transaction("sessions", "readwrite");
        transaction.objectStore("sessions").put({ id: "current", version: 1, ...session });
        transaction.oncomplete = () => { db.close(); resolve(); };
        transaction.onerror = () => { db.close(); reject(transaction.error); };
        transaction.onabort = () => { db.close(); reject(transaction.error); };
      };
    });
  },
  async clearToken() {
    if (!await this.hasDatabase()) return;
    return new Promise((resolve, reject) => {
      const request = indexedDB.open("dicloak_auth", 1);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (!db.objectStoreNames.contains("sessions")) {
          db.createObjectStore("sessions", { keyPath: "id" });
        }
      };
      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        const db = request.result;
        const transaction = db.transaction("sessions", "readwrite");
        transaction.objectStore("sessions").delete("current");
        transaction.oncomplete = () => { db.close(); resolve(); };
        transaction.onerror = () => { db.close(); reject(transaction.error); };
      };
    });
  },
};

const storageAdapter = siteId === "localstorage" ? {
  async getToken() {
    try { return JSON.parse(localStorage.getItem(authKey) || "null")?.token || ""; }
    catch (_) { return ""; }
  },
  async setToken(session) { localStorage.setItem(authKey, JSON.stringify({ version: 1, ...session })); },
  async clearToken() { localStorage.removeItem(authKey); },
} : siteId === "indexeddb" ? indexedDbAdapter : {
  async getToken() { return ""; },
  async setToken() {},
  async clearToken() {},
};

function renderState(state, payload = {}) {
  const authenticated = state === "AUTHENTICATED";
  const unavailable = state === "SERVICE_UNAVAILABLE";
  elements.status.textContent = authenticated ? "已登录" : unavailable ? "服务不可用" : state === "INITIALIZING" ? "正在检查登录状态" : "未登录";
  elements.account.textContent = authenticated ? payload.username || "—" : "—";
  elements.runId.textContent = authenticated ? payload.runId || "—" : "—";
  elements.fingerprint.textContent = authenticated ? payload.tokenFingerprint || "—" : "—";
  elements.loginForm.hidden = authenticated;
  elements.registerForm.hidden = true;
  elements.tabs.hidden = authenticated;
  elements.logoutButton.hidden = !authenticated;
}

function showMessage(message, isError = false) {
  elements.message.textContent = message || "";
  elements.message.classList.toggle("error", isError);
}

async function authHeaders() {
  const token = await storageAdapter.getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function checkSession() {
  renderState("INITIALIZING");
  try {
    const response = await fetch("/api/session", { headers: await authHeaders(), cache: "no-store" });
    const payload = await response.json();
    if (response.ok && payload.authenticated) {
      if (siteId !== "cookie" && payload.token) {
        await storageAdapter.setToken({
          storageType,
          username: payload.username,
          runId: payload.runId,
          token: payload.token,
          tokenFingerprint: payload.tokenFingerprint,
          issuedAt: payload.issuedAt,
          expiresAt: payload.expiresAt,
        });
      }
      renderState("AUTHENTICATED", payload);
      showMessage("");
      return;
    }
    if (response.status === 401) {
      await storageAdapter.clearToken();
      renderState("UNAUTHENTICATED");
      showMessage(payload.reason && payload.reason !== "TOKEN_MISSING" ? "登录已失效" : "");
      return;
    }
    renderState("SERVICE_UNAVAILABLE");
    showMessage("服务状态检查失败", true);
  } catch (_) {
    renderState("SERVICE_UNAVAILABLE");
    showMessage("本地认证服务不可用", true);
  }
}

elements.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  showMessage("");
  const body = Object.fromEntries(new FormData(elements.loginForm).entries());
  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) {
      showMessage(payload.message || "登录失败", true);
      renderState("UNAUTHENTICATED");
      return;
    }
    if (siteId !== "cookie") {
      await storageAdapter.setToken({
        storageType,
        username: payload.username,
        runId: payload.runId,
        token: payload.token,
        tokenFingerprint: payload.tokenFingerprint,
        issuedAt: payload.issuedAt,
        expiresAt: payload.expiresAt,
      });
    }
    await checkSession();
  } catch (_) {
    renderState("SERVICE_UNAVAILABLE");
    showMessage("本地认证服务不可用", true);
  }
});

elements.registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  showMessage("");
  const body = Object.fromEntries(new FormData(elements.registerForm).entries());
  try {
    const response = await fetch("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const payload = await response.json();
    if (!response.ok) {
      showMessage(payload.message || "注册失败", true);
      return;
    }
    await storageAdapter.clearToken();
    renderState("UNAUTHENTICATED");
    showMessage(payload.message || "注册成功，请登录");
    elements.loginForm.querySelector('[name="username"]').value = payload.username || "";
  } catch (_) {
    renderState("SERVICE_UNAVAILABLE");
    showMessage("本地认证服务不可用", true);
  }
});

elements.logoutButton.addEventListener("click", async () => {
  try {
    await fetch("/api/logout", { method: "POST", headers: await authHeaders() });
    await storageAdapter.clearToken();
    renderState("UNAUTHENTICATED");
    showMessage("已退出登录");
  } catch (_) {
    renderState("SERVICE_UNAVAILABLE");
    showMessage("退出登录失败：本地认证服务不可用", true);
  }
});

document.querySelector('[data-action="show-login"]').addEventListener("click", () => {
  elements.loginForm.hidden = false;
  elements.registerForm.hidden = true;
});

document.querySelector('[data-action="show-register"]').addEventListener("click", () => {
  elements.loginForm.hidden = true;
  elements.registerForm.hidden = false;
});

checkSession();
