const WORKER_API = "";

function proxyPhoto(url, accountId) {
  if (!url) return "";
  if (url.includes("amazonaws.com")) {
    return `/api/proxy-image?url=${encodeURIComponent(url)}&account_id=${accountId || ""}`;
  }
  return url;
}

// ── Авторизация ───────────────────────────────────────────

const AUTH_TOKEN_KEY = "claw_auth_token";

function getAuthToken() {
  try { return localStorage.getItem(AUTH_TOKEN_KEY); } catch { return null; }
}

function setAuthToken(token) {
  try { localStorage.setItem(AUTH_TOKEN_KEY, token); } catch {}
}

function clearAuthToken() {
  try { localStorage.removeItem(AUTH_TOKEN_KEY); } catch {}
}

// Подклеиваем токен авторизации ко всем запросам на /api/
const _origFetch = window.fetch;

window.fetch = function(url, options = {}) {
  const urlStr =
    typeof url === "string"
      ? url
      : (url?.url || "");

  const token = getAuthToken();

  if (urlStr.startsWith("/api/") || urlStr.includes("/api/")) {
    options = {
      ...options,
      headers: {
        ...(options.headers || {}),
        "ngrok-skip-browser-warning": "true",
        ...(token ? { "Authorization": `Bearer ${token}` } : {}),
      },
    };
  }

  return _origFetch(url, options);
};

const authOverlay   = document.getElementById("authOverlay");
const authTabLogin  = document.getElementById("authTabLogin");
const authTabRegister = document.getElementById("authTabRegister");
const loginForm     = document.getElementById("loginForm");
const registerForm  = document.getElementById("registerForm");
const loginError    = document.getElementById("loginError");
const registerError = document.getElementById("registerError");
const userCardEmail = document.getElementById("userCardEmail");

const notificationsBell = document.getElementById("notificationsBell");
const notificationsCount = document.getElementById("notificationsCount");
const notificationsModal = document.getElementById("notificationsModal");
const notificationsModalClose = document.getElementById("notificationsModalClose");
const notificationsList = document.getElementById("notificationsList");

const teamInviteBtn = document.getElementById("teamInviteBtn");
const teamInviteEmail = document.getElementById("teamInviteEmail");
const teamInviteRole = document.getElementById("teamInviteRole");
const teamInviteResult = document.getElementById("teamInviteResult");

const teamMembersList = document.getElementById("teamMembersList");

function showAuthOverlay() {
  if (authOverlay) authOverlay.style.display = "flex";
  const mainApp = document.getElementById("mainApp");
  if (mainApp) mainApp.style.display = "none";
}

function hideAuthOverlay() {
  if (authOverlay) authOverlay.style.display = "none";
  const mainApp = document.getElementById("mainApp");
  if (mainApp) mainApp.style.display = "";
}

authTabLogin?.addEventListener("click", () => {
  authTabLogin.classList.add("active");
  authTabRegister.classList.remove("active");
  loginForm.style.display = "flex";
  loginForm.style.flexDirection = "column";
  registerForm.style.display = "none";
});

authTabRegister?.addEventListener("click", () => {
  authTabRegister.classList.add("active");
  authTabLogin.classList.remove("active");
  registerForm.style.display = "flex";
  registerForm.style.flexDirection = "column";
  loginForm.style.display = "none";
});

loginForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.textContent = "";
  const email = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPassword").value;
  const access_code = document.getElementById("loginAccessCode").value.trim();
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, access_code }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Ошибка входа");
    setAuthToken(data.token);
    if (userCardEmail) userCardEmail.textContent = data.email;
    if (data.username) {
      const nameEl = document.querySelector(".userCard b");
      if (nameEl) nameEl.textContent = data.username;
      const avatarEl = document.querySelector(".userAvatar");
      if (avatarEl) avatarEl.textContent = data.username.charAt(0).toUpperCase();
    }
    hideAuthOverlay();
    startApp();
  } catch (err) {
    loginError.textContent = err.message || "Не удалось войти";
  }
});

registerForm?.addEventListener("submit", async (e) => {
  e.preventDefault();
  registerError.textContent = "";
  const username = document.getElementById("registerUsername").value.trim();
  const email = document.getElementById("registerEmail").value.trim();
  const password = document.getElementById("registerPassword").value;
  const access_code = document.getElementById("registerAccessCode").value.trim();
  try {
    const res = await fetch("/api/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, email, password, access_code }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Ошибка регистрации");
    setAuthToken(data.token);
    if (userCardEmail) userCardEmail.textContent = data.email;
    if (username) {
      const nameEl = document.querySelector(".userCard b");
      if (nameEl) nameEl.textContent = username;
      const avatarEl = document.querySelector(".userAvatar");
      if (avatarEl) avatarEl.textContent = username.charAt(0).toUpperCase();
    }
    hideAuthOverlay();
    startApp();
  } catch (err) {
    registerError.textContent = err.message || "Не удалось зарегистрироваться";
  }
});

async function checkAuthAndStart() {
  const token = getAuthToken();
  
  // Показываем экран загрузки пока проверяем токен
  const loadingScreen = document.getElementById("authLoadingScreen");
  const authBox = document.querySelector(".authBox");
  if (authBox) authBox.style.display = "none";
  if (authOverlay) authOverlay.style.display = "flex";

  if (!token) {
    if (loadingScreen) loadingScreen.style.display = "none";
    if (authBox) authBox.style.display = "";
    return;
  }

  try {
    const res = await fetch("/api/auth/me");
    if (!res.ok) throw new Error("invalid session");
    const data = await res.json();
    if (userCardEmail) userCardEmail.textContent = data.email;
    hideAuthOverlay();
    startApp();
  } catch {
    clearAuthToken();
    if (loadingScreen) loadingScreen.style.display = "none";
    if (authBox) authBox.style.display = "";
  }
}

// ── Модалка удаления вкладки ───────────────────────────────

const deleteTabModal = document.getElementById("deleteTabModal");
const deleteTabName = document.getElementById("deleteTabName");
const deleteTabCancelBtn = document.getElementById("deleteTabCancelBtn");
const deleteTabConfirmBtn = document.getElementById("deleteTabConfirmBtn");
const deleteTabModalClose = document.getElementById("deleteTabModalClose");

let tabPendingDelete = null;

function openDeleteTabModal(tab) {
  tabPendingDelete = tab;
  if (deleteTabName) deleteTabName.textContent = tab.name;
  deleteTabModal?.classList.add("open");
}

function closeDeleteTabModal() {
  tabPendingDelete = null;
  deleteTabModal?.classList.remove("open");
}

deleteTabCancelBtn?.addEventListener("click", closeDeleteTabModal);
deleteTabModalClose?.addEventListener("click", closeDeleteTabModal);
deleteTabModal?.addEventListener("click", (e) => {
  if (e.target === deleteTabModal) closeDeleteTabModal();
});

deleteTabConfirmBtn?.addEventListener("click", async () => {
  if (!tabPendingDelete) return;
  const tab = tabPendingDelete;
  try {
    await fetch(WORKER_API + `/api/tabs/${encodeURIComponent(tab.id)}`, { method: "DELETE" });
    if (activeTabId === tab.id) {
      activeTabId = null;
      document.querySelector('.platformBtn[data-platform="Mamba"]')?.classList.add("active");
      activePlatform = "Mamba";
    }
    closeDeleteTabModal();
    await loadOperatorTabs();
    renderSquareGridFromCache();
  } catch (err) {
    alert("Не удалось удалить вкладку: " + err.message);
  }
});

// ── Модалка профиля ───────────────────────────────────────

const userCardBtn   = document.getElementById("userCardBtn");
const profileModal  = document.getElementById("profileModal");
const profileModalClose = document.getElementById("profileModalClose");
const profileEmail  = document.getElementById("profileEmail");
const profileCurrentPassword = document.getElementById("profileCurrentPassword");
const profileNewPassword     = document.getElementById("profileNewPassword");
const profileChangePasswordBtn = document.getElementById("profileChangePasswordBtn");
const profileChangeResult = document.getElementById("profileChangeResult");
const profileLogoutBtn = document.getElementById("profileLogoutBtn");

userCardBtn?.addEventListener("click", () => {
  if (profileEmail) profileEmail.value = userCardEmail?.textContent || "";
  const usernameInput = document.getElementById("profileUsername");
  if (usernameInput) {
    const currentName = document.querySelector(".userCard b")?.textContent || "";
    usernameInput.value = currentName;
  }
  if (profileChangeResult) { profileChangeResult.textContent = ""; profileChangeResult.className = "result"; }
  if (profileCurrentPassword) profileCurrentPassword.value = "";
  if (profileNewPassword) profileNewPassword.value = "";
  profileModal?.classList.add("open");
});

profileModalClose?.addEventListener("click", () => {
  profileModal?.classList.remove("open");
});

profileModal?.addEventListener("click", (e) => {
  if (e.target === profileModal) profileModal.classList.remove("open");
});

// Подгружаем текущее имя при открытии модалки
userCardBtn?.addEventListener("click", () => {
  const currentName = document.querySelector(".userCard b")?.textContent || "";
  const usernameInput = document.getElementById("profileUsername");
  if (usernameInput) usernameInput.value = currentName;
});

document.getElementById("profileChangeUsernameBtn")?.addEventListener("click", async () => {
  const usernameInput = document.getElementById("profileUsername");
  const resultEl = document.getElementById("profileUsernameResult");
  const newName = usernameInput?.value.trim();
  if (!newName) { 
    if (resultEl) { resultEl.textContent = "Введи имя."; resultEl.className = "result bad"; }
    return;
  }
  try {
    const res = await fetch("/api/auth/update-profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: newName }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Ошибка");
    // Обновляем имя везде
    const nameEl = document.querySelector(".userCard b");
    if (nameEl) nameEl.textContent = newName;
    // Обновляем аватар-букву
    const avatarEl = document.querySelector(".userAvatar");
    if (avatarEl) avatarEl.textContent = newName.charAt(0).toUpperCase();
    if (resultEl) { resultEl.textContent = "Имя сохранено."; resultEl.className = "result good"; }
  } catch (err) {
    if (resultEl) { resultEl.textContent = err.message || "Ошибка."; resultEl.className = "result bad"; }
  }
});

profileChangePasswordBtn?.addEventListener("click", async () => {
  const current_password = profileCurrentPassword.value;
  const new_password = profileNewPassword.value;
  if (!current_password || !new_password) {
    profileChangeResult.textContent = "Заполни оба поля пароля.";
    profileChangeResult.className = "result bad";
    return;
  }
  try {
    const res = await fetch("/api/auth/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current_password, new_password }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Не удалось сменить пароль");
    profileChangeResult.textContent = "Пароль успешно изменён.";
    profileChangeResult.className = "result good";
    profileCurrentPassword.value = "";
    profileNewPassword.value = "";
  } catch (err) {
    profileChangeResult.textContent = err.message || "Ошибка смены пароля";
    profileChangeResult.className = "result bad";
  }
});

profileLogoutBtn?.addEventListener("click", async () => {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } catch {}
  clearAuthToken();
  profileModal?.classList.remove("open");
  appStarted = false;
  location.reload();
});

const runningSplits = new Set();
window._splitLogs = {};

window._splitLogBuffer = {};

function pushLog(accountId, message) {
  if (!window._splitLogs[accountId]) return;
  const ts = new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const line = `[${ts}] ${message}`;
  window._splitLogs[accountId].push(line);
  if (!window._splitLogBuffer[accountId]) window._splitLogBuffer[accountId] = [];
  window._splitLogBuffer[accountId].push(line);
}

setInterval(async () => {
  for (const accountId of Object.keys(window._splitLogBuffer)) {
    const messages = window._splitLogBuffer[accountId];
    if (!messages || !messages.length) continue;
    window._splitLogBuffer[accountId] = [];
    try {
      await fetch(WORKER_API + "/api/split-log/push", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_id: accountId, messages }),
      });
    } catch (e) {
      console.warn("[pushLog] flush error:", e);
    }
  }
}, 5000);
const liveStats = {}; // { [accountId]: { liked, replied, contacts } }

function bumpLiveStat(accountId, field, amount = 1) {
  if (!liveStats[accountId]) {
    liveStats[accountId] = { liked: 0, replied: 0, contacts: 0 };
  }
  liveStats[accountId][field] = (liveStats[accountId][field] || 0) + amount;

  // Мгновенно обновляем DOM карточки
  const cardEl = document.querySelector(`.sqCard[data-account-id="${accountId}"]`);
  if (!cardEl) return;
  const likesVal    = cardEl.querySelector(".sqLikesVal");
  const msgsVal     = cardEl.querySelector(".sqMsgsVal");
  const contactsVal = cardEl.querySelector(".sqContactsVal");
  if (likesVal)    likesVal.textContent    = liveStats[accountId].liked;
  if (msgsVal)     msgsVal.textContent     = liveStats[accountId].replied;
  if (contactsVal) contactsVal.textContent = liveStats[accountId].contacts;
}

let reservedIds = new Set();
const form            = document.getElementById("connectForm");
const resultBox       = document.getElementById("resultBox");
const connectSlots    = document.getElementById("connectSlots");
const slotTemplate    = document.getElementById("connectSlotTemplate");
const addSlotBtn      = document.getElementById("addSlotBtn");

function addConnectSlot() {
  const node = slotTemplate.content.cloneNode(true);
  const slotEl = node.querySelector(".connectSlot");

  slotEl.querySelector(".slotRemoveBtn").addEventListener("click", () => {
    // не даём удалить последний оставшийся слот
    if (connectSlots.querySelectorAll(".connectSlot").length > 1) {
      slotEl.remove();
    }
  });

  connectSlots.appendChild(node);

  try {
    const isTwinby  = typeof activePlatform !== "undefined" && activePlatform === "Twinby";
    const isVzn     = typeof activePlatform !== "undefined" && activePlatform === "Vznakomstve";
    const isIntCity = typeof activePlatform !== "undefined" && activePlatform === "intCity";
    slotEl.querySelector(".slotStandardFields").style.display  = (isTwinby || isVzn || isIntCity) ? "none" : "";
    slotEl.querySelector(".slotTwinbyFields").style.display    = isTwinby ? "" : "none";
    slotEl.querySelector(".slotVznFields").style.display       = isVzn ? "" : "none";
    slotEl.querySelector(".slotIntCityFields").style.display   = isIntCity ? "" : "none";
  } catch(e) {}
}

addSlotBtn?.addEventListener("click", addConnectSlot);

// один слот по умолчанию при загрузке
addConnectSlot();

// ── Мульти-добавление анкет ──────────────────────────────
const multiConnectWrap = document.createElement("div");
multiConnectWrap.id = "multiConnectWrap";
const accountsList    = document.getElementById("accountsList");   // сетка на главной
const accountsListFull= document.getElementById("accountsListFull");
const gridEmpty       = document.getElementById("gridEmpty");
const countBadge      = document.getElementById("countBadge");
const template        = document.getElementById("accountTemplate");
const sqTemplate      = document.getElementById("squareCardTemplate");
const navButtons      = document.querySelectorAll(".navBtn");
const pages           = document.querySelectorAll(".page");
const connectBtn      = document.getElementById("connectBtn");

const connectToggle = document.getElementById("connectToggle");
const connectBody   = document.getElementById("connectBody");
const connectArrow  = document.querySelector(".connectArrow");

// Скрываем панель подключения при старте — показывается только через правую кнопку мыши
const connectForm = document.getElementById("connectForm");
if (connectForm) connectForm.style.display = "none";

if (connectToggle && connectBody) {
  connectToggle.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    const isOpen = connectBody.style.display === "flex";
    if (isOpen) {
      connectBody.style.display = "none";
      if (connectArrow) connectArrow.classList.remove("open");
    } else {
      connectBody.style.display = "flex";
      connectBody.style.flexDirection = "column";
      if (connectArrow) connectArrow.classList.add("open");
    }
  });
}

const aiSettingsForm    = null;
const aiAccountSelect   = { value: "", innerHTML: "" };
const aiGroqKey         = null;
const aiGroqModel       = null;
const aiBotIdentity     = null;
const aiPersona         = null;
const aiGoal            = null;
const aiStopTopics      = null;
const aiContacts        = null;
const aiContactsTrigger = null;
const aiSaveBtn         = null;
const aiSettingsResult  = null;

// Модалки
const likesModal       = document.getElementById("likesModal");
const likesModalClose  = document.getElementById("likesModalClose");
const modalLikesLimit  = document.getElementById("modalLikesLimit");
const modalRunLikesBtn = document.getElementById("modalRunLikesBtn");
const modalLikesResult = document.getElementById("modalLikesResult");

const groqModal        = document.getElementById("groqModal");
const groqModalClose   = document.getElementById("groqModalClose");
const modalRunGroqBtn  = document.getElementById("modalRunGroqBtn");
const modalGroqResult  = document.getElementById("modalGroqResult");

let activeModalAccountId = null;
let activeModalResultEl  = null;
let activeModalCardEl    = null;

let activePlatform = "Mamba";
let activeTabId = null; // если не null — мы во вкладке оператора, а не на платформе
let operatorTabs = [];

document.querySelectorAll(".platformBtn[data-platform]").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".platformBtn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    activePlatform = btn.dataset.platform;
    activeTabId = null;
    // Переключаем поля в слотах
    document.querySelectorAll(".connectSlot").forEach(slot => {
      const isTwinby  = activePlatform === "Twinby";
      const isVzn     = activePlatform === "Vznakomstve";
      const isIntCity = activePlatform === "intCity"; 
      slot.querySelector(".slotStandardFields").style.display  = (isTwinby || isVzn || isIntCity) ? "none" : "";
      slot.querySelector(".slotTwinbyFields").style.display    = isTwinby ? "" : "none";
      slot.querySelector(".slotVznFields").style.display       = isVzn ? "" : "none";
      slot.querySelector(".slotIntCityFields").style.display   = isIntCity ? "" : "none";
    });
    const connectPanel = document.getElementById("connectForm");
    if (connectPanel) connectPanel.style.display = "none";
    renderOperatorTabs();
    if (cachedAccounts.length > 0) {
      renderSquareGridFromCache();
    } else {
      loadAccounts();
    }
    renderAICardsOnCanvas();
    renderTimerCardsOnCanvas();
  });
});

async function loadOperatorTabs() {
  try {
    const res = await fetch(WORKER_API + "/api/tabs");
    const data = await res.json();
    operatorTabs = data.tabs || [];
  } catch (err) {
    console.error("loadOperatorTabs error:", err);
    operatorTabs = [];
  }
  renderOperatorTabs();
}

function renderOperatorTabs() {
  const container = document.getElementById("operatorTabsContainer");
  const divider = document.getElementById("tabsDivider");
  if (!container) return;

  container.innerHTML = "";

  const visibleTabs = operatorTabs.filter(t => (t.platform || "Mamba") === activePlatform);

  if (divider) divider.style.display = visibleTabs.length ? "block" : "none";

  visibleTabs.forEach(tab => {
    const btn = document.createElement("button");
    btn.className = "platformBtn operatorTabBtn";
    btn.dataset.tabId = tab.id;
    if (activeTabId === tab.id) btn.classList.add("active");
    btn.innerHTML = `${escapeHtml(tab.name)}<span class="tabDeleteX">✕</span>`;

    btn.addEventListener("click", (e) => {
      if (e.target.classList.contains("tabDeleteX")) return;
      document.querySelectorAll(".platformBtn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeTabId = tab.id;
      renderSquareGridFromCache();
    });

    btn.querySelector(".tabDeleteX").addEventListener("click", (e) => {
      e.stopPropagation();
      openDeleteTabModal(tab);
    });

    // Drag-and-drop: кидаем карточку на эту кнопку — присваиваем метку
    btn.addEventListener("dragover", (e) => {
      e.preventDefault();
      btn.classList.add("dragOver");
    });
    btn.addEventListener("dragleave", () => {
      btn.classList.remove("dragOver");
    });
    btn.addEventListener("drop", async (e) => {
      e.preventDefault();
      btn.classList.remove("dragOver");
      const accountId = e.dataTransfer.getData("text/account-id");
      if (!accountId) return;
      try {
        await fetch(WORKER_API + "/api/tabs/assign", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ account_id: accountId, tab_id: tab.id }),
        });
        await loadOperatorTabs();
        renderSquareGridFromCache();
      } catch (err) {
        alert("Не удалось добавить анкету во вкладку: " + err.message);
      }
    });

    container.appendChild(btn);
  });

  const addBtn = document.getElementById("addTabBtn");
  if (addBtn && addBtn.tagName === "BUTTON") {
    addBtn.onclick = startAddTabInline;
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function startAddTabInline() {
  const addBtn = document.getElementById("addTabBtn");
  if (!addBtn || addBtn.tagName !== "BUTTON") return;

  const input = document.createElement("input");
  input.type = "text";
  input.id = "addTabBtn";
  input.placeholder = "Название вкладки";
  input.maxLength = 30;
  input.style.cssText = "width:150px;padding:7px 10px;border-radius:var(--r);border:1px solid var(--accent2);background:rgba(5,8,16,0.7);color:var(--text);font:500 12px 'Space Grotesk',sans-serif;outline:none;";

  addBtn.replaceWith(input);
  input.focus();

  let done = false;

  function restoreButton() {
    const current = document.getElementById("addTabBtn");
    if (current && current.tagName === "INPUT") {
      const btn = document.createElement("button");
      btn.className = "platformBtn";
      btn.id = "addTabBtn";
      btn.title = "Добавить вкладку";
      btn.style.cssText = "width:36px;padding:7px 0;text-align:center;";
      btn.textContent = "+";
      btn.onclick = startAddTabInline;
      current.replaceWith(btn);
    }
  }

  async function finish(shouldCreate) {
    if (done) return;
    done = true;
    const name = input.value.trim();

    if (shouldCreate && name) {
      try {
        await fetch(WORKER_API + "/api/tabs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, platform: activePlatform }),
        });
        restoreButton();
        await loadOperatorTabs(); // перерисует ряд вкладок (кнопка "+" уже восстановлена выше)
        return;
      } catch (err) {
        alert("Не удалось создать вкладку: " + err.message);
      }
    }

    restoreButton();
  }

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); finish(true); }
    if (e.key === "Escape") { e.preventDefault(); finish(false); }
  });
}

const STORAGE_KEY = "claw_active_page";

const pageInfo = {
  home:      { title: "CLAW-AI MANAGER",  subtitle: "Панель подключения анкет, AI-менеджера и задач." },
  accounts:  { title: "Анкеты",           subtitle: "Все подключённые анкеты, фото, статусы и быстрые действия." },
  ai:        { title: "AI-Менеджер",      subtitle: "Настрой промт для каждой анкеты — запуск прямо с карточки на главной." },
  tasks:     { title: "Задачи",           subtitle: "Лог выполненных задач." },
  analytics: { title: "Аналитика",        subtitle: "Отчёты, статистика и данные по подключённым анкетам." },
  tables:    { title: "Таблица ключей",   subtitle: "API-ключи Groq и Gemini — управление и привязка к анкетам." },
  contacts:  { title: "Контакты",          subtitle: "Все запарсенные email адреса с intimcity." },
  settings:  { title: "Настройки",         subtitle: "Авторизация, профиль администратора и системные настойки." },
};

// ── Helpers ───────────────────────────────────────────────

function setResult(text, type = "") {
  resultBox.textContent = text;
  resultBox.className = `result ${type}`.trim();
}

function setBoxResult(box, text, type = "") {
  box.textContent = text;
  box.className = `result ${type}`.trim();
}

function formatDate(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}

async function waitForQueuedJob(jobId) {
  const startedAt = Date.now();
  const timeoutMs = 30 * 60 * 1000;

  while (Date.now() - startedAt < timeoutMs) {
    await new Promise(resolve => setTimeout(resolve, 2000));

    const res = await fetch(WORKER_API + `/api/jobs/${encodeURIComponent(jobId)}`);
    const data = await res.json();

    if (!res.ok || !data.ok) {
      throw new Error(
        data.detail || data.error || "Не удалось получить статус задачи"
      );
    }

    const job = data.job || {};

    if (job.status === "done") {
      return job.result || { ok: true };
    }

    if (job.status === "error") {
      throw new Error(
        job.result?.error ||
        job.result?.summary ||
        "Ошибка локального воркера"
      );
    }

    if (job.status === "cancelled") {
      return job.result || {
        ok: true,
        status: "stopped_by_user",
        summary: "Остановлено вручную",
      };
    }
  }

  throw new Error("Локальный воркер не завершил задачу за 30 минут");
}

async function fetchWithTimeout(url, options = {}, timeoutMs = 600_000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, {
      ...options,
      signal: controller.signal,
    });

    clearTimeout(timer);

    const isQueuedTask =
      url === "/api/tasks/broadcast";

    if (!isQueuedTask || !res.ok) {
      return res;
    }

    const enqueueData = await res.clone().json();

    if (!enqueueData.job_id) {
      return res;
    }

    const result = await waitForQueuedJob(enqueueData.job_id);

    return new Response(JSON.stringify(result), {
      status: result.ok === false ? 500 : 200,
      headers: {
        "Content-Type": "application/json",
      },
    });
  } catch (err) {
    clearTimeout(timer);

    if (err.name === "AbortError") {
      throw new Error("Сервер слишком долго не отвечал.");
    }

    throw err;
  }
}
// ── Статистика из лога задач ──────────────────────────────


function startFastStatsPolling(accountId, cardEl) {
  const intervalId = setInterval(async () => {
    if (!runningSplits.has(accountId)) {
      clearInterval(intervalId);
      return;
    }
    try {
      const res = await fetch(WORKER_API + "/api/tasks-log");
      const data = await res.json();
      const logs = data.logs || [];
      const stats = (window.cachedLogs && window.cachedLogs[accountId]) || { liked: 0, replied: 0, contacts: 0 };

      const likesVal = cardEl?.querySelector(".sqLikesVal");
      const msgsVal  = cardEl?.querySelector(".sqMsgsVal");
      const contactsVal = cardEl?.querySelector(".sqContactsVal");

      // Обновляем только если нет живых данных (сплит не запущен)
      if (!runningSplits.has(accountId)) {
        if (likesVal) likesVal.textContent = stats.liked;
        if (msgsVal) msgsVal.textContent = stats.replied;
        if (contactsVal) contactsVal.textContent = stats.contacts;
      } else {
        // Сплит запущен — показываем накопленные живые данные
        const s = liveStats[accountId];
        if (s) {
          if (likesVal) likesVal.textContent = s.liked;
          if (msgsVal) msgsVal.textContent = s.replied;
          if (contactsVal) contactsVal.textContent = s.contacts;
        }
      }
    } catch (err) {
      console.error("fast stats polling error:", err);
    }
  }, 15000);
  return intervalId;
}

function startLiveActionPolling(accountId, cardEl) {
  let lastId = 0;
  let initialized = false;

  const intervalId = setInterval(async () => {
    if (!runningSplits.has(accountId) && !cardEl?.classList.contains("sqActive")) {
      clearInterval(intervalId);
      return;
    }
    try {
      const url = initialized
        ? WORKER_API + `/api/split-log/${encodeURIComponent(accountId)}?after_id=${lastId}`
        : WORKER_API + `/api/split-log/${encodeURIComponent(accountId)}`;

      const res = await fetch(url);
      const data = await res.json();
      const logs = data.logs || [];

      if (!initialized) {
        // первый запрос — просто запоминаем текущий последний id, без бампа (не пересчитываем старое)
        lastId = data.last_id || 0;
        initialized = true;
        return;
      }

      for (const row of logs) {
        const msg = row.message || "";
        if (msg.includes("✓ Лайк поставлен")) {
          bumpLiveStat(accountId, "liked", 1);
        } else if (msg.includes("✓ ответ отправлен")) {
          bumpLiveStat(accountId, "replied", 1);
          if (msg.includes("контакт передан")) {
            bumpLiveStat(accountId, "contacts", 1);
          }
        }
      }

      if (logs.length) {
        lastId = logs[logs.length - 1].id;
      }

      const likesVal    = cardEl?.querySelector(".sqLikesVal");
      const msgsVal     = cardEl?.querySelector(".sqMsgsVal");
      const contactsVal = cardEl?.querySelector(".sqContactsVal");
      const s = liveStats[accountId];
      if (s) {
        if (likesVal)    likesVal.textContent    = s.liked;
        if (msgsVal)     msgsVal.textContent     = s.replied;
        if (contactsVal) contactsVal.textContent = s.contacts;
      }
    } catch (err) {
      console.error("live action polling error:", err);
    }
  }, 15000);

  return intervalId;
}

// ── Квадратная карточка ───────────────────────────────────

function createSquareCard(account, stats) {
  const node = sqTemplate.content.cloneNode(true);
  const cardEl = node.querySelector(".sqCard");

  cardEl.setAttribute("data-account-id", account.id);
  cardEl.setAttribute("draggable", "true");
  cardEl.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData("text/account-id", account.id);
    e.dataTransfer.effectAllowed = "copy";
    cardEl.classList.add("dragging");
  });
  cardEl.addEventListener("dragend", () => {
    cardEl.classList.remove("dragging");
  });

  const img      = node.querySelector(".sqImg");

  const fallback = node.querySelector(".sqFallback");
  const name     = node.querySelector(".sqName");
  name?.addEventListener("dblclick", async () => {
    const current = name.textContent;
    const input = document.createElement("input");
    input.value = current;
    input.style.cssText = "font:inherit;width:100%;background:transparent;border:none;border-bottom:1px solid var(--cyan);color:inherit;outline:none;padding:0;";
    name.textContent = "";
    name.appendChild(input);
    input.focus();
    input.select();
    const save = async () => {
      const val = input.value.trim() || current;
      name.textContent = val;
      try {
        await fetch(WORKER_API + `/api/accounts/${account.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: val }),
        });
      } catch {}
    };
    input.addEventListener("blur", save);
    input.addEventListener("keydown", e => {
      if (e.key === "Enter") input.blur();
      if (e.key === "Escape") { name.textContent = current; }
    });
  });
  const likesVal = node.querySelector(".sqLikesVal");
  const msgsVal  = node.querySelector(".sqMsgsVal");
  const sqResult = node.querySelector(".sqResult");
  const likesBtn = node.querySelector(".sqLikesBtn") || { disabled: false };
  const groqBtn  = node.querySelector(".sqGroqBtn") || { disabled: false };
  const delBtn   = node.querySelector(".sqDeleteBtn");

  if (account.photo_url && account.photo_url !== account.profile_url) {
    img.style.display = "none";
    img.onload  = () => { img.style.display = "block"; fallback.style.display = "none"; };
    img.onerror = () => { img.style.display = "none";  fallback.style.display = "flex"; };
    img.src = proxyPhoto(account.photo_url, account.id);
  } else {
    img.style.display = "none";
    fallback.style.display = "flex";
  }

  name.textContent     = account.name || "Анкета";
  likesVal.textContent     = stats.liked;
  msgsVal.textContent      = stats.replied;

  // ── Стрелка сворачивания AI-карточки ──
  const collapseKey = `claw_ai_collapsed_${account.id}`;
  let isCollapsed = false;
  try { isCollapsed = localStorage.getItem(collapseKey) === "1"; } catch {}

  const collapseBtn = document.createElement("button");
  collapseBtn.className = "sqCollapseBtn";
  collapseBtn.title = "Скрыть/показать AI-карточку";
  collapseBtn.textContent = isCollapsed ? "‹" : "›";
  collapseBtn.dataset.accountId = account.id;
  collapseBtn.dataset.collapsed = isCollapsed ? "1" : "0";

  collapseBtn.onclick = (e) => {
    e.stopPropagation();
    const group = cardEl.closest(".sqGroup");
    if (!group) return;
    const connector = group.querySelector(".sqConnector");
    const aCard = group.querySelector(".sqAnalyticsCard");
    if (!connector || !aCard) return;

    const nowCollapsed = collapseBtn.dataset.collapsed !== "1";
    connector.style.display = nowCollapsed ? "none" : "flex";
    aCard.style.display     = nowCollapsed ? "none" : "flex";
    collapseBtn.dataset.collapsed = nowCollapsed ? "1" : "0";
    collapseBtn.textContent = nowCollapsed ? "‹" : "›";

    try { localStorage.setItem(collapseKey, nowCollapsed ? "1" : "0"); } catch {}
  };

  cardEl.appendChild(collapseBtn);
  const contactsVal = node.querySelector(".sqContactsVal");
  if (contactsVal) contactsVal.textContent = stats.contacts;

  const sqResultEl = node.querySelector(".sqResult");

const likesInput = node.querySelector(".sqLikesInput") || { disabled: false, value: "10" };
const splitBtn   = node.querySelector(".sqSplitBtn");
const splitInput = node.querySelector(".sqSplitInput");

const blockInfo = `${account.block_reason || ""} ${account.run_note || ""} ${account.session_reason || ""}`.toLowerCase();

const isBlocked =
  account.is_blocked === true ||
  String(account.is_blocked).toLowerCase() === "true" ||
  blockInfo.includes("заблок") ||
  blockInfo.includes("blocked") ||
  blockInfo.includes("confirm photo");

const sessionInfo = `${account.session_reason || ""} ${account.run_note || ""}`.toLowerCase();

const isLoggedOut =
  !isBlocked &&
  (account.platform || "").toLowerCase() !== "lovelaz" &&
  (account.platform || "").toLowerCase() !== "vznakomstve" &&
  (account.platform || "").toLowerCase() !== "intcity" &&
  (
    account.session_valid === false ||
    String(account.session_valid).toLowerCase() === "false" ||
    account.cookies_valid === false ||
    String(account.cookies_valid).toLowerCase() === "false" ||
    sessionInfo.includes("разлогин") ||
    sessionInfo.includes("cookies недействительны") ||
    sessionInfo.includes("unauthorized") ||
    sessionInfo.includes("session expired")
  );

if (isBlocked) {
  cardEl.classList.add("sqBlocked");

  // Делаем фотографию чёрно-белой
  img.style.filter = "grayscale(100%) brightness(45%)";
  fallback.style.filter = "grayscale(100%) brightness(45%)";

  const photoArea =
    img.closest(".sqPhoto, .sqImageWrap, .sqMedia") ||
    img.parentElement;

  if (photoArea) {
    photoArea.classList.add("sqBlockedPhoto");

    if (!photoArea.querySelector(".sqBlockedOverlay")) {
      const blockedOverlay = document.createElement("div");
      blockedOverlay.className = "sqBlockedOverlay";
      blockedOverlay.textContent = "БЛОК";
      photoArea.appendChild(blockedOverlay);
    }
  }

  // Находим зелёный VALID
  const validBadge = [...cardEl.querySelectorAll("*")].find(el =>
    el.children.length === 0 &&
    el.textContent.trim().toUpperCase() === "VALID"
  );

  if (validBadge) {
    validBadge.textContent = "БЛОК";
    validBadge.classList.add("sqBlockedBadge");
  }
}

if (isLoggedOut) {
  cardEl.classList.add("sqLoggedOut");

  img.style.filter = "grayscale(100%) brightness(55%)";
  fallback.style.filter = "grayscale(100%) brightness(55%)";

  const photoArea =
    img.closest(".sqPhoto, .sqImageWrap, .sqMedia") ||
    img.parentElement;

  if (photoArea) {
    photoArea.classList.add("sqBlockedPhoto");

    if (!photoArea.querySelector(".sqBlockedOverlay")) {
      const logoutOverlay = document.createElement("div");
      logoutOverlay.className = "sqBlockedOverlay";
      logoutOverlay.textContent = "РАЗЛОГИН";
      photoArea.appendChild(logoutOverlay);
    }
  }

  const validBadge = [...cardEl.querySelectorAll("*")].find(el =>
    el.children.length === 0 &&
    el.textContent.trim().toUpperCase() === "VALID"
  );

  if (validBadge) {
    validBadge.textContent = "РАЗЛОГИН";
    validBadge.classList.add("sqBlockedBadge");
  }
}

const isTeamRunning = account.run_status === "running";

if (isTeamRunning) {
  cardEl.classList.add("sqActive");

  const taskName =
    account.run_task === "split" ? "Сплит запущен" :
    account.run_task === "groq" ? "Groq запущен" :
    account.run_task === "likes" ? "Лайки запущены" :
    "Анкета запущена";

  const startedBy = account.run_started_by ? ` · ${account.run_started_by}` : "";

  if (sqResultEl) {
    sqResultEl.textContent = account.run_note || `${taskName}${startedBy}`;
    sqResultEl.className = "sqResult";
  }

  splitBtn.classList.add("running");
  splitBtn.innerHTML = "⏹ Стоп";
  splitBtn.disabled = false;

  if (likesBtn) likesBtn.disabled = true;
  if (groqBtn) groqBtn.disabled = true;
  splitInput.disabled = true;
  if (likesInput) likesInput.disabled = true;
}

// Восстанавливаем сохранённые значения лимитов из localStorage
const likesLimitKey = `claw_likes_limit_${account.id}`;
const splitLimitKey = `claw_split_limit_${account.id}`;
try {
  const savedLikesLimit = localStorage.getItem(likesLimitKey);
  if (savedLikesLimit) likesInput.value = savedLikesLimit;
} catch {}
try {
  const savedSplitLimit = localStorage.getItem(splitLimitKey);
  if (savedSplitLimit) splitInput.value = savedSplitLimit;
} catch {}

// Сохраняем значения при изменении, чтобы они не сбрасывались после обновления страницы
likesInput.addEventListener?.("input", () => {
  try { localStorage.setItem(likesLimitKey, likesInput.value); } catch {}
});
splitInput.addEventListener("input", () => {
  try { localStorage.setItem(splitLimitKey, splitInput.value); } catch {}
});

if (likesBtn.onclick !== undefined) likesBtn.onclick = () => {
  const limit = Math.max(1, Math.min(100, Number(likesInput.value) || 10));
  runLikes(account.id, limit, sqResultEl, cardEl);
};

if (groqBtn.onclick !== undefined) groqBtn.onclick = () => runGroq(account.id, sqResultEl, cardEl);

  splitBtn.onclick = async () => {
  const limit = Math.max(1, Math.min(50, Number(splitInput.value) || 10));

  if (account.run_status === "running" && !runningSplits.has(account.id)) {
    if (sqResultEl) {
      sqResultEl.textContent = "Останавливаю...";
      sqResultEl.className = "sqResult";
    }

    try {
      await fetch(WORKER_API + "/api/tasks/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_id: account.id }),
      });
    } catch (err) {
      console.error("stop error:", err);
    }

    await setAccountRunStatus(account.id, "idle", "", "");
    runningSplits.delete(account.id);

    splitBtn.classList.remove("running");
    splitBtn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg> Сплит';

    likesBtn.disabled = false;
    groqBtn.disabled = false;
    splitBtn.disabled = false;
    splitInput.disabled = false;
    likesInput.disabled = false;
    cardEl?.classList.remove("sqActive");

    if (sqResultEl) {
      sqResultEl.textContent = "Остановлено.";
      sqResultEl.className = "sqResult";
    }

    loadAccounts();
    return;
  }

  toggleSplit(account.id, splitBtn, splitInput, likesBtn, groqBtn, likesInput, limit, sqResultEl, cardEl, account.platform);
};

  if (runningSplits.has(account.id)) {
    splitBtn.disabled = false;
    splitBtn.classList.add("running");
    splitBtn.innerHTML = "⏹ Стоп";
    likesBtn.disabled = true;
    groqBtn.disabled = true;
    splitInput.disabled = true;
    likesInput.disabled = true;
  }

if (isBlocked || isLoggedOut) {
  likesBtn.disabled = true;
  groqBtn.disabled = true;
  splitBtn.disabled = true;
  likesInput.disabled = true;
  splitInput.disabled = true;

  if (sqResultEl) {
    sqResultEl.textContent = isBlocked
      ? "Анкета заблокирована"
      : "Анкета разлогинена";
    sqResultEl.className = "sqResult bad";
  }
}

const isReserved = reservedIds.has(account.id);
if (isReserved) {
  cardEl.classList.add("sqReserve");
  likesBtn.disabled = true;
  groqBtn.disabled = true;
  splitBtn.disabled = true;
  likesInput.disabled = true;
  splitInput.disabled = true;

  if (sqResultEl) {
    sqResultEl.textContent = "Резервная анкета";
    sqResultEl.className = "sqResult";
  }
}

// intCity — дефолтное фото
if ((account.platform || "").toLowerCase() === "intcity" && !account.photo_url) {
  account.photo_url = "/intcity_logo.png";
}

// ── intCity: показываем поля рассылки ──
const isIntCityCard = (account.platform || "").toLowerCase() === "intcity";
const intCityFields = node.querySelector(".sqIntCityFields");
if (isIntCityCard && intCityFields) {
  intCityFields.style.display = "flex";

  // Скрываем ненужные элементы
  const sqStats = node.querySelector(".sqStats");
  if (sqStats) sqStats.style.display = "none";

  // Восстанавливаем сохранённые значения
  const savedSubject = localStorage.getItem(`intcity_subject_${account.id}`) || "";
  const savedBody = localStorage.getItem(`intcity_body_${account.id}`) || "";
  const savedPages = localStorage.getItem(`intcity_pages_${account.id}`) || "3";
  const subjectEl = intCityFields.querySelector(".sqIntCitySubject");
  const bodyEl = intCityFields.querySelector(".sqIntCityBody");
  const pagesEl = intCityFields.querySelector(".sqIntCityPages");
  if (subjectEl) subjectEl.value = savedSubject;
  if (bodyEl) bodyEl.value = savedBody;
  if (pagesEl) pagesEl.value = savedPages;

  subjectEl?.addEventListener("input", () => {
    localStorage.setItem(`intcity_subject_${account.id}`, subjectEl.value);
  });
  bodyEl?.addEventListener("input", () => {
    localStorage.setItem(`intcity_body_${account.id}`, bodyEl.value);
  });
  pagesEl?.addEventListener("input", () => {
    localStorage.setItem(`intcity_pages_${account.id}`, pagesEl.value);
  });

  const cookieEl = intCityFields.querySelector(".sqIntCityCookie");
  const tokenEl = intCityFields.querySelector(".sqIntCityToken");
  if (cookieEl) {
    cookieEl.value = localStorage.getItem(`intcity_cookie_${account.id}`) || "";
    cookieEl.addEventListener("input", () => localStorage.setItem(`intcity_cookie_${account.id}`, cookieEl.value));
  }
  if (tokenEl) {
    tokenEl.value = localStorage.getItem(`intcity_token_${account.id}`) || "";
    tokenEl.addEventListener("input", () => localStorage.setItem(`intcity_token_${account.id}`, tokenEl.value));
  }

  // Переопределяем сплит для intCity
  splitBtn.onclick = async () => {
    if (runningSplits.has(account.id)) {
      runningSplits.delete(account.id);
      try {
        await fetch(WORKER_API + "/api/tasks/stop", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ account_id: account.id }),
        });
      } catch {}
      await setAccountRunStatus(account.id, "idle", "", "");
      splitBtn.classList.remove("running");
      splitBtn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg> Сплит';
      splitBtn.disabled = false;
      splitInput.disabled = false;
      cardEl?.classList.remove("sqActive");
      if (sqResultEl) { sqResultEl.textContent = "Остановлено."; sqResultEl.className = "sqResult"; }
      loadAccounts();
      return;
    }

    const subject = subjectEl?.value.trim();
    const body = bodyEl?.value.trim();
    const pages = parseInt(pagesEl?.value) || 3;
    if (!subject) { alert("Введи тему письма"); return; }
    if (!body) { alert("Введи текст письма"); return; }

    runningSplits.add(account.id);
    await setAccountRunStatus(account.id, "running", "split", "Рассылка запущена");
    splitBtn.classList.add("running");
    splitBtn.innerHTML = "⏹ Стоп";
    splitBtn.disabled = false;
    splitInput.disabled = true;
    cardEl?.classList.add("sqActive");

    // Отправляем задачу в job_queue
    if (sqResultEl) { sqResultEl.textContent = "Запускаю рассылку..."; sqResultEl.className = "sqResult"; }
    try {
      const res = await fetch(WORKER_API + "/api/tasks/intcity-split", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": localStorage.getItem("claw_auth_token") || "",
        },
        body: JSON.stringify({
          account_id: account.id,
          pages,
          subject,
          body,
          mail_cookie: localStorage.getItem(`intcity_cookie_${account.id}`) || "",
          mail_token: localStorage.getItem(`intcity_token_${account.id}`) || "",
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.detail || "Ошибка запуска");
      if (sqResultEl) { sqResultEl.textContent = "Задача запущена — воркер работает"; sqResultEl.className = "sqResult good"; }
    } catch (e) {
      if (sqResultEl) { sqResultEl.textContent = `Ошибка: ${e.message}`; sqResultEl.className = "sqResult bad"; }
      runningSplits.delete(account.id);
      splitBtn.classList.remove("running");
      splitBtn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg> Сплит';
      splitBtn.disabled = false;
      splitInput.disabled = false;
      cardEl?.classList.remove("sqActive");
    }

    // НЕ сбрасываем состояние — воркер работает в фоне бесконечно
    // Кнопка Стоп отменит задачу через job_queue
  };
}

// ── Кнопка скрещивания ──
  const chainBtn = node.querySelector(".sqChainBtn");
  if (chainBtn) {
    chainBtn.onclick = () => openChainModal(account.id, account.name);
  }

  delBtn.onclick = () => {
    const modal = document.getElementById("deleteAccountModal");
    const nameEl = document.getElementById("deleteAccountName");
    if (nameEl) nameEl.textContent = account.name || account.id;
    if (modal) modal.style.display = "flex";

    document.getElementById("deleteAccountCancelBtn").onclick = () => { modal.style.display = "none"; };
    document.getElementById("deleteAccountModalClose").onclick = () => { modal.style.display = "none"; };
    document.getElementById("deleteAccountConfirmBtn").onclick = async () => {
      modal.style.display = "none";
      cachedAccounts = cachedAccounts.filter(a => a.id !== account.id);
      const group = cardEl.closest(".sqGroup") || cardEl.closest("[data-account-id]")?.parentElement || cardEl.parentElement?.parentElement;
      if (group) group.remove();
      else cardEl.parentElement?.remove();
      try {
        runningSplits.delete(account.id);
        try {
          await fetch(WORKER_API + "/api/tasks/stop", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ account_id: account.id }),
          });
        } catch {}
        await fetch(WORKER_API + `/api/accounts/${encodeURIComponent(account.id)}`, { method: "DELETE" });
      } catch (err) {
        alert("Не удалось удалить: " + err.message);
      }
    };
  };

  return node;
}

// ── Старая карточка (для страницы Анкеты) ────────────────

function createAccountCard(account) {
  const node = template.content.cloneNode(true);
  const img      = node.querySelector(".profilePhoto");
  const fallback = node.querySelector(".profileFallback");

  if (account.photo_url && account.photo_url !== account.profile_url) {
    img.style.display = "none";
    img.onload  = () => { img.style.display = "block"; fallback.style.display = "none"; };
    img.onerror = () => { img.style.display = "none";  fallback.style.display = "flex"; };
    img.src = proxyPhoto(account.photo_url);
  } else {
    img.style.display = "none";
    fallback.style.display = "grid";
  }

  node.querySelector("h3").textContent      = account.name || "Анкета";
  node.querySelector(".url").textContent    = account.final_url || account.profile_url || "";
  node.querySelector(".checked").textContent= `Сохранено: ${formatDate(account.checked_at)}`;
  node.querySelector(".cookies").textContent= `Cookies: ${account.cookies_count || 0}`;
  node.querySelector(".openBtn").onclick    = () => window.open(account.final_url || account.profile_url, "_blank");
  node.querySelector(".deleteBtn").onclick  = async (e) => {
    const card = e.target.closest(".accountCard, .card, li") || e.target.parentElement;
    if (card) card.remove();
    try {
      const res  = await fetch(WORKER_API + `/api/accounts/${encodeURIComponent(account.id)}`, { method: "DELETE" });
      const data = await res.json();
      if (!data.ok) throw new Error(data.error || "Ошибка удаления");
    } catch (err) { alert("Не удалось удалить: " + err.message); }
  };
  return node;
}

// ── Загрузка и рендер ─────────────────────────────────────

let cachedAccounts = [];
let cachedLogs = [];

const ACCOUNTS_CACHE_KEY = "claw_accounts_cache";
const LOGS_CACHE_KEY     = "claw_logs_cache";
const ANALYTICS_CACHE_KEY = "claw_analytics_cache";

function loadCachedAccountsInstantly() {
  try {
    const accRaw = localStorage.getItem(ACCOUNTS_CACHE_KEY);
    const logRaw = localStorage.getItem(LOGS_CACHE_KEY);
    const anaRaw = localStorage.getItem(ANALYTICS_CACHE_KEY);

    if (accRaw) {
      const accounts = JSON.parse(accRaw);
      const logs = logRaw ? JSON.parse(logRaw) : [];
      cachedAccounts = accounts;
      cachedLogs = logs;

      const cb = document.getElementById("countBadge");
      if (cb) cb.textContent = accounts.length;

      renderSquareGrid(accounts, logs);

      if (anaRaw) {
        try { analyticsCards = JSON.parse(anaRaw); } catch {}
      }
      renderAnalyticsGrid(accounts);
    }
  } catch (err) {
    console.error("loadCachedAccountsInstantly error:", err);
  }
}

async function loadAccounts() {
  try {
    const [accRes, statsRes, reservedRes] = await Promise.all([
      fetch(WORKER_API + "/api/accounts"),
      fetch(WORKER_API + "/api/accounts-stats"),
      fetch(WORKER_API + "/api/accounts/reserved-ids"),
    ]);
    const accData = await accRes.json();
    const statsData = await statsRes.json();
    const reservedData = await reservedRes.json();
    const accounts = accData.accounts || [];
    const statsMap = statsData.stats || {};
    reservedIds = new Set(reservedData.reserved_ids || []);
    console.log("ACCOUNTS LOADED:", accounts.length);
    cachedAccounts = accounts;
    window._cachedAccounts = accounts; // для страницы таблиц
    window.cachedLogs = statsMap;
    cachedLogs = statsMap;

    // countBadge в шапке
    const cb = document.getElementById("countBadge");
    if (cb) cb.textContent = accounts.length;

    // Главная — квадратная сетка
  try {
    localStorage.setItem(ACCOUNTS_CACHE_KEY, JSON.stringify(accounts));
    localStorage.setItem(LOGS_CACHE_KEY, JSON.stringify(statsMap));
  } catch {}

    renderSquareGrid(accounts, statsMap);

    // Страница Анкеты — старый список
    if (accountsListFull) {
      accountsListFull.innerHTML = "";
      if (!accounts.length) {
        accountsListFull.innerHTML = `<div class="empty"><div><b>Пока пусто</b><span>Подключи первую анкету.</span></div></div>`;
      } else {
        accounts.forEach(a => accountsListFull.appendChild(createAccountCard(a)));
      }
    }

    renderAiAccountOptions(accounts);
    return accounts;
  } catch (err) {
    console.error("loadAccounts error:", err);
    return [];
  }
}


let accountStatusCheckRunning = false;

async function refreshAccountStatuses() {
  if (accountStatusCheckRunning) return;

  accountStatusCheckRunning = true;

  try {
    const res = await fetch(WORKER_API + "/api/accounts/check-statuses", {
      method: "POST",
    });

    const data = await res.json();

    if (!res.ok || !data.ok) {
      throw new Error(
        data.detail ||
        data.error ||
        `Ошибка проверки статусов: HTTP ${res.status}`
      );
    }

    console.log("ACCOUNT STATUSES:", data.results);

    // Пропущенные заблокированные анкеты (жёсткий флаг)
    const skipped = data.results.filter(r => r.skipped);
    if (skipped.length) {
      console.log(`[STATUS] Пропущено заблокированных анкет: ${skipped.length}`, skipped.map(r => r.account_id));
    }

    // Перезагружаем карточки с обновлёнными статусами из Supabase
    await loadAccounts();
  } catch (err) {
    console.error("refreshAccountStatuses error:", err);
  } finally {
    accountStatusCheckRunning = false;
  }
}

// ── Infinite Canvas (pan/zoom/drag) ──────────────────────

const CANVAS_STORAGE_KEY = "claw_canvas_positions";
let canvasPositions = {}; // { [accountId]: { x, y } }
let canvasTransform = { x: 0, y: 0, scale: 1 };

function loadCanvasPositions() {
  try {
    const raw = localStorage.getItem(CANVAS_STORAGE_KEY);
    if (raw) canvasPositions = JSON.parse(raw);
  } catch {}
}

function saveCanvasPositions() {
  try { localStorage.setItem(CANVAS_STORAGE_KEY, JSON.stringify(canvasPositions)); } catch {}
}

function initInfiniteCanvas() {
  const wrapper = document.getElementById("canvasWrapper");
  const canvas = document.getElementById("webCanvas");
  const container = document.getElementById("accountsList");
  if (!wrapper || !canvas || !container) return;

  loadCanvasPositions();

  let isPanning = false;
  let isDragging = false;
  let dragGroup = null;
  let dragOffsetX = 0, dragOffsetY = 0;
  let panStartX = 0, panStartY = 0;
  let panOriginX = 0, panOriginY = 0;

  function applyTransform() {
    container.style.transform = `translate(${canvasTransform.x}px, ${canvasTransform.y}px) scale(${canvasTransform.scale})`;
    if (window._clawDrawWeb) window._clawDrawWeb(); else drawWeb();
  }

  function drawWeb() {
    const ctx = canvas.getContext("2d");
    const W = wrapper.offsetWidth;
    const H = wrapper.offsetHeight;
    canvas.width = W;
    canvas.height = H;
    ctx.clearRect(0, 0, W, H);

    const groups = [...container.querySelectorAll(".sqGroup")];
    if (groups.length < 2) return;

    const centers = groups.map(g => {
      const x = parseFloat(g.style.left || 0);
      const y = parseFloat(g.style.top || 0);
      const w = g.offsetWidth;
      const h = g.offsetHeight;
      return {
        x: (x + w / 2) * canvasTransform.scale + canvasTransform.x,
        y: (y + h / 2) * canvasTransform.scale + canvasTransform.y,
      };
    });

    ctx.strokeStyle = "rgba(92,110,248,0.15)";
    ctx.lineWidth = 1;

    for (let i = 0; i < centers.length; i++) {
      for (let j = i + 1; j < centers.length; j++) {
        const dx = centers[i].x - centers[j].x;
        const dy = centers[i].y - centers[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist > 600) continue; // не рисуем линии слишком далёких
        const alpha = Math.max(0, 1 - dist / 600) * 0.25;
        ctx.strokeStyle = `rgba(92,110,248,${alpha})`;
        ctx.beginPath();
        ctx.moveTo(centers[i].x, centers[i].y);
        ctx.lineTo(centers[j].x, centers[j].y);
        ctx.stroke();
      }
    }

    // Точки в центрах карточек
    ctx.fillStyle = "rgba(92,110,248,0.4)";
    centers.forEach(c => {
      ctx.beginPath();
      ctx.arc(c.x, c.y, 3, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  // Pan — зажатие пустого места
  wrapper.addEventListener("mousedown", (e) => {
    if (e.target.closest(".sqGroup")) return; // клик по карточке — не пан
    if (e.button !== 0) return;
    isPanning = true;
    panStartX = e.clientX;
    panStartY = e.clientY;
    panOriginX = canvasTransform.x;
    panOriginY = canvasTransform.y;
    wrapper.style.cursor = "grabbing";
  });

  window.addEventListener("mousemove", (e) => {
    if (isPanning) {
      canvasTransform.x = panOriginX + (e.clientX - panStartX);
      canvasTransform.y = panOriginY + (e.clientY - panStartY);
      applyTransform();
    }
    if (isDragging && dragGroup) {
      const x = (e.clientX - wrapper.getBoundingClientRect().left - canvasTransform.x) / canvasTransform.scale - dragOffsetX;
      const y = (e.clientY - wrapper.getBoundingClientRect().top - canvasTransform.y) / canvasTransform.scale - dragOffsetY;
      dragGroup.style.left = x + "px";
      dragGroup.style.top = y + "px";
      const id = dragGroup.dataset.accountId || `ai_${dragGroup.dataset.cardId}`;
      if (id) canvasPositions[id] = { x, y };
      if (window._clawDrawWeb) window._clawDrawWeb(); else drawWeb();
    }
  });

  window.addEventListener("mouseup", () => {
    if (isPanning) { isPanning = false; wrapper.style.cursor = ""; }
    if (isDragging) { isDragging = false; dragGroup = null; saveCanvasPositions(); }
  });

  // Zoom — колесо мыши
  document.addEventListener("wheel", (e) => {
    const homePage = document.getElementById("homePage");
    if (!homePage || !homePage.classList.contains("activePage")) return;
    if (!e.target.closest("#canvasWrapper")) return;
    e.preventDefault();
    const rect = wrapper.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    const newScale = Math.max(0.2, Math.min(3, canvasTransform.scale * delta));
    canvasTransform.x = mouseX - (mouseX - canvasTransform.x) * (newScale / canvasTransform.scale);
    canvasTransform.y = mouseY - (mouseY - canvasTransform.y) * (newScale / canvasTransform.scale);
    canvasTransform.scale = newScale;
    applyTransform();
  }, { passive: false });

  // Drag карточек (анкеты)
  container.addEventListener("mousedown", (e) => {
    const group = e.target.closest(".sqGroup");
    if (!group) return;
    if (e.target.closest("button, input, textarea, select, a")) return;
    e.preventDefault();
    isDragging = true;
    dragGroup = group;
    const rect = wrapper.getBoundingClientRect();
    const gx = parseFloat(group.style.left || 0);
    const gy = parseFloat(group.style.top || 0);
    dragOffsetX = (e.clientX - rect.left - canvasTransform.x) / canvasTransform.scale - gx;
    dragOffsetY = (e.clientY - rect.top - canvasTransform.y) / canvasTransform.scale - gy;
    group.style.zIndex = "100";
    setTimeout(() => { if (dragGroup) dragGroup.style.zIndex = ""; }, 500);
  });

  // Drag AI карточек
  container.addEventListener("mousedown", (e) => {
    const group = e.target.closest(".sqAIGroup");
    if (!group) return;
    if (e.target.closest(".sqConnectDot")) return;
    e.preventDefault();
    e.stopPropagation();
    const rect = wrapper.getBoundingClientRect();
    const gx = parseFloat(group.style.left || 0);
    const gy = parseFloat(group.style.top || 0);
    const ox = (e.clientX - rect.left) - gx;
    const oy = (e.clientY - rect.top) - gy;
    group.style.zIndex = "100";
    function move(e) {
      const x = (e.clientX - rect.left) - ox;
      const y = (e.clientY - rect.top) - oy;
      group.style.left = x + "px";
      group.style.top = y + "px";
      const cardId = group.dataset.cardId;
      if (cardId) canvasPositions[`ai_${cardId}`] = { x, y };
      if (window._clawDrawWeb) window._clawDrawWeb();
    }
    function up() {
      group.style.zIndex = "";
      saveCanvasPositions();
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    }
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    });

  // Drag нитки от sqConnectDot
  let drawingLine = false;
  let lineFromId = null;
  let lineEndX = 0, lineEndY = 0;

  container.addEventListener("mousedown", (e) => {
    const dot = e.target.closest(".sqConnectDot");
    if (!dot) return;
    e.stopPropagation();
    e.preventDefault();
    drawingLine = true;
    const group = dot.closest(".sqGroup") || dot.closest(".sqAIGroup") || dot.closest(".sqTimerGroup");
    lineFromId = group?.dataset.accountId;
    const rect = wrapper.getBoundingClientRect();
    lineEndX = e.clientX - rect.left;
    lineEndY = e.clientY - rect.top;
  });

  window.addEventListener("mousemove", (e) => {
    if (!drawingLine) return;
    const rect = wrapper.getBoundingClientRect();
    lineEndX = e.clientX - rect.left;
    lineEndY = e.clientY - rect.top;
    drawConnections();
    const ctx = canvas.getContext("2d");
    const fromEl = container.querySelector(`[data-account-id="${lineFromId}"]`);
    if (!fromEl) return;
    const fx = (parseFloat(fromEl.style.left||0) + fromEl.offsetWidth/2) * canvasTransform.scale + canvasTransform.x;
    const fy = (parseFloat(fromEl.style.top||0) + fromEl.offsetHeight/2) * canvasTransform.scale + canvasTransform.y;
    ctx.strokeStyle = "rgba(16,245,168,0.8)";
    ctx.lineWidth = 2;
    ctx.setLineDash([6,4]);
    ctx.beginPath();
    ctx.moveTo(fx, fy);
    ctx.lineTo(lineEndX, lineEndY);
    ctx.stroke();
    ctx.setLineDash([]);
  });

  window.addEventListener("mouseup", (e) => {
    if (!drawingLine) return;
    drawingLine = false;
    const target = document.elementFromPoint(e.clientX, e.clientY);
    const toGroup = target?.closest(".sqGroup") || target?.closest(".sqAIGroup") || target?.closest(".sqTimerGroup");
    const toId = toGroup?.dataset.accountId;
    if (toId && toId !== lineFromId) {
      const exists = connections.find(c => (c.from===lineFromId&&c.to===toId)||(c.from===toId&&c.to===lineFromId));
      if (!exists) {
        connections.push({ from: lineFromId, to: toId });
        saveConnections();
        const aiId = lineFromId.startsWith("ai_") ? lineFromId : toId.startsWith("ai_") ? toId : null;
        const accountId = lineFromId.startsWith("ai_") ? toId : toId.startsWith("ai_") ? lineFromId : null;
        if (aiId && accountId && !accountId.startsWith("ai_") && !accountId.startsWith("timer_")) {
          const cardId = aiId.replace("ai_", "");
          const aiCard = analyticsCards.find(c => c.cardId === cardId);
          if (aiCard) {
            aiCard.accountId = accountId;
            fetch(WORKER_API + `/api/analytics-cards/${encodeURIComponent(cardId)}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ account_id: accountId }),
            }).catch(() => {});
            fetch(WORKER_API + `/api/ai-settings/${encodeURIComponent(accountId)}`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                bot_name: aiCard.botName || "",
                bot_age: aiCard.botAge || "",
                bot_gender: aiCard.botGender || "female",
                location: aiCard.location || "",
                contacts: aiCard.contacts || "",
                contacts_trigger: aiCard.contactsTrigger || "",
              }),
            }).catch(() => {});
          }
        }
      }
    }
    drawConnections();
  });

  window.addEventListener("resize", () => {
    drawWeb();
  });

  // Контекстное меню по правой кнопке
  const ctxMenu = document.createElement("div");
  ctxMenu.id = "canvasCtxMenu";
  ctxMenu.style.cssText = "display:none;position:fixed;z-index:1000;background:rgba(15,18,30,0.97);border:1px solid rgba(255,255,255,.12);border-radius:10px;padding:6px 0;min-width:180px;box-shadow:0 8px 32px rgba(0,0,0,.4);";
  ctxMenu.innerHTML = `
    <div id="ctxAddAI" style="padding:10px 16px;cursor:pointer;font:500 13px 'Space Grotesk',sans-serif;color:var(--text);display:flex;align-items:center;gap:8px;">
      ✦ Добавить AI-менеджера
    </div>
    <div id="ctxAddTimer" style="padding:10px 16px;cursor:pointer;font:500 13px 'Space Grotesk',sans-serif;color:var(--text);display:flex;align-items:center;gap:8px;">
      ⏱ Добавить таймер
    </div>
    <div id="ctxConnectAccount" style="padding:10px 16px;cursor:pointer;font:500 13px 'Space Grotesk',sans-serif;color:var(--text);display:flex;align-items:center;gap:8px;border-top:1px solid rgba(255,255,255,0.08);margin-top:4px;">
      🔗 Подключить анкету
    </div>
  `;
  document.body.appendChild(ctxMenu);

  let ctxMenuX = 0, ctxMenuY = 0;

  wrapper.addEventListener("contextmenu", (e) => {
    if (e.target.closest(".sqGroup")) return;
    e.preventDefault();
    ctxMenu.style.display = "block";
    ctxMenu.style.left = e.clientX + "px";
    ctxMenu.style.top = e.clientY + "px";
    // Запоминаем координаты в canvas-пространстве
    const rect = wrapper.getBoundingClientRect();
    ctxMenuX = (e.clientX - rect.left - canvasTransform.x) / canvasTransform.scale;
    ctxMenuY = (e.clientY - rect.top - canvasTransform.y) / canvasTransform.scale;
  });

  document.getElementById("ctxAddAI").onclick = () => {
    ctxMenu.style.display = "none";
    window._ctxSpawnX = ctxMenuX;
    window._ctxSpawnY = ctxMenuY;
    document.getElementById("addAnalyticsBtn")?.click();
  };

  document.getElementById("ctxConnectAccount").onclick = () => {
    ctxMenu.style.display = "none";
    const form = document.getElementById("connectForm");
    const body = document.getElementById("connectBody");
    if (!form) return;
    form.style.display = "";
    if (body) body.style.display = "flex";
    form.scrollIntoView({ behavior: "smooth" });
  };

  document.addEventListener("click", () => { ctxMenu.style.display = "none"; });
  document.addEventListener("contextmenu", (e) => {
    if (!e.target.closest("#canvasWrapper")) ctxMenu.style.display = "none";
  });

  // Нитки между карточками
  const connections = JSON.parse(localStorage.getItem("claw_connections") || "[]");

  function saveConnections() {
    localStorage.setItem("claw_connections", JSON.stringify(connections));
  }

  function drawConnections() {
    const ctx = canvas.getContext("2d");
    const W = wrapper.offsetWidth;
    const H = wrapper.offsetHeight;
    canvas.width = W;
    canvas.height = H;
    ctx.clearRect(0, 0, W, H);

    wrapper.querySelectorAll(".connDisconnectBtn").forEach(el => el.remove());

    // Паутина между карточками
    const groups = [...container.querySelectorAll(".sqGroup")];
    if (groups.length >= 2) {
      const centers = groups.map(g => ({
        x: (parseFloat(g.style.left||0) + g.offsetWidth/2) * canvasTransform.scale + canvasTransform.x,
        y: (parseFloat(g.style.top||0) + g.offsetHeight/2) * canvasTransform.scale + canvasTransform.y,
      }));
      for (let i = 0; i < centers.length; i++) {
        for (let j = i+1; j < centers.length; j++) {
          const dx = centers[i].x - centers[j].x;
          const dy = centers[i].y - centers[j].y;
          const dist = Math.sqrt(dx*dx+dy*dy);
          if (dist > 600) continue;
          const alpha = Math.max(0, 1 - dist/600) * 0.08;
          ctx.strokeStyle = `rgba(92,110,248,${alpha})`;
          ctx.lineWidth = 1;
          ctx.beginPath();
          ctx.moveTo(centers[i].x, centers[i].y);
          ctx.lineTo(centers[j].x, centers[j].y);
          ctx.stroke();
        }
      }
    }

    // Нитки соединений
    const now = Date.now();

    connections.forEach((conn, idx) => {
      const fromEl = container.querySelector(`[data-account-id="${conn.from}"]`);
      const toEl = container.querySelector(`[data-account-id="${conn.to}"]`);
      if (!fromEl || !toEl) return;

      const fx = (parseFloat(fromEl.style.left||0) + fromEl.offsetWidth/2) * canvasTransform.scale + canvasTransform.x;
      const fy = (parseFloat(fromEl.style.top||0) + fromEl.offsetHeight/2) * canvasTransform.scale + canvasTransform.y;
      const tx = (parseFloat(toEl.style.left||0) + toEl.offsetWidth/2) * canvasTransform.scale + canvasTransform.x;
      const ty = (parseFloat(toEl.style.top||0) + toEl.offsetHeight/2) * canvasTransform.scale + canvasTransform.y;

      const dx = tx - fx, dy = ty - fy;
      const len = Math.sqrt(dx*dx + dy*dy);

      // Определяем — есть ли активный сплит на одном из концов
      const fromAccountId = conn.from.startsWith("ai_") ? null : conn.from.startsWith("timer_") ? null : conn.from;
      const toAccountId   = conn.to.startsWith("ai_") ? null : conn.to.startsWith("timer_") ? null : conn.to;
      const isActive = (fromAccountId && runningSplits.has(fromAccountId)) || (toAccountId && runningSplits.has(toAccountId));

      if (isActive) {
        // ── АКТИВНАЯ нитка: плазменная дуга ──

        // Пульсация яркости
        const pulse = 0.75 + 0.25 * Math.sin(now * 0.004);

        // Широкий внешний ореол
        ctx.beginPath();
        ctx.moveTo(fx, fy);
        ctx.lineTo(tx, ty);
        ctx.strokeStyle = `rgba(16,245,168,${0.06 * pulse})`;
        ctx.lineWidth = 20;
        ctx.lineCap = "round";
        ctx.shadowBlur = 0;
        ctx.stroke();

        // Средний слой
        ctx.beginPath();
        ctx.moveTo(fx, fy);
        ctx.lineTo(tx, ty);
        ctx.strokeStyle = `rgba(16,245,168,${0.2 * pulse})`;
        ctx.lineWidth = 8;
        ctx.shadowColor = "#10f5a8";
        ctx.shadowBlur = 15;
        ctx.stroke();

        // Тело кабеля — тёмное
        ctx.beginPath();
        ctx.moveTo(fx, fy);
        ctx.lineTo(tx, ty);
        ctx.strokeStyle = "rgba(0,30,20,0.8)";
        ctx.lineWidth = 3;
        ctx.shadowBlur = 0;
        ctx.stroke();

        // Плазменное ядро
        ctx.beginPath();
        ctx.moveTo(fx, fy);
        ctx.lineTo(tx, ty);
        ctx.strokeStyle = `rgba(255,255,255,${0.85 * pulse})`;
        ctx.lineWidth = 1;
        ctx.shadowColor = "#10f5a8";
        ctx.shadowBlur = 25;
        ctx.stroke();
        ctx.shadowBlur = 0;

        // Бегущие частицы — быстрые искры
        const speed = 0.0004;
        const particleCount = Math.max(3, Math.floor(len / 60));
        for (let p = 0; p < particleCount; p++) {
          const t = ((now * speed + p / particleCount) % 1);
          const px = fx + dx * t;
          const py = fy + dy * t;

          // Длинный хвост
          const tailLen = 0.18;
          const t0 = Math.max(0, t - tailLen);
          const tailX = fx + dx * t0;
          const tailY = fy + dy * t0;

          const grad = ctx.createLinearGradient(tailX, tailY, px, py);
          grad.addColorStop(0, "rgba(16,245,168,0)");
          grad.addColorStop(0.5, "rgba(16,245,168,0.4)");
          grad.addColorStop(1, "rgba(255,255,255,1)");

          ctx.beginPath();
          ctx.moveTo(tailX, tailY);
          ctx.lineTo(px, py);
          ctx.strokeStyle = grad;
          ctx.lineWidth = 3;
          ctx.shadowColor = "#ffffff";
          ctx.shadowBlur = 20;
          ctx.stroke();
          ctx.shadowBlur = 0;

          // Яркая голова
          ctx.beginPath();
          ctx.arc(px, py, 2.5, 0, Math.PI * 2);
          ctx.fillStyle = "#ffffff";
          ctx.shadowColor = "#10f5a8";
          ctx.shadowBlur = 25;
          ctx.fill();
          ctx.shadowBlur = 0;
        }

        // Терминалы — светящиеся коннекторы
        [[fx, fy], [tx, ty]].forEach(([cx, cy]) => {
          ctx.beginPath();
          ctx.arc(cx, cy, 6, 0, Math.PI * 2);
          ctx.strokeStyle = `rgba(16,245,168,${0.8 * pulse})`;
          ctx.lineWidth = 2;
          ctx.shadowColor = "#10f5a8";
          ctx.shadowBlur = 20;
          ctx.stroke();
          ctx.shadowBlur = 0;
          ctx.beginPath();
          ctx.arc(cx, cy, 3, 0, Math.PI * 2);
          ctx.fillStyle = "#ffffff";
          ctx.shadowColor = "#10f5a8";
          ctx.shadowBlur = 15;
          ctx.fill();
          ctx.shadowBlur = 0;
        });
        ctx.shadowBlur = 0;

        } else {
        // ── НЕАКТИВНАЯ нитка: кабель под напряжением ──

        // Внешний ореол — широкий размытый
        ctx.beginPath();
        ctx.moveTo(fx, fy);
        ctx.lineTo(tx, ty);
        ctx.strokeStyle = "rgba(99,102,241,0.06)";
        ctx.lineWidth = 14;
        ctx.lineCap = "round";
        ctx.shadowBlur = 0;
        ctx.stroke();

        // Средний слой — тело кабеля
        ctx.beginPath();
        ctx.moveTo(fx, fy);
        ctx.lineTo(tx, ty);
        ctx.strokeStyle = "rgba(30,27,75,0.9)";
        ctx.lineWidth = 4;
        ctx.stroke();

        // Внутреннее свечение — тонкое и яркое
        ctx.beginPath();
        ctx.moveTo(fx, fy);
        ctx.lineTo(tx, ty);
        ctx.strokeStyle = "rgba(139,92,246,0.7)";
        ctx.lineWidth = 1.5;
        ctx.shadowColor = "#7c3aed";
        ctx.shadowBlur = 10;
        ctx.stroke();
        ctx.shadowBlur = 0;

        // Блики — имитация стеклянного провода
        const perpX = -(dy / len) * 1.2;
        const perpY = (dx / len) * 1.2;
        ctx.beginPath();
        ctx.moveTo(fx + perpX, fy + perpY);
        ctx.lineTo(tx + perpX, ty + perpY);
        ctx.strokeStyle = "rgba(196,181,253,0.25)";
        ctx.lineWidth = 0.8;
        ctx.shadowBlur = 0;
        ctx.stroke();

        // Терминалы на концах — металлические коннекторы
        [[fx, fy], [tx, ty]].forEach(([cx, cy]) => {
          // Внешнее кольцо
          ctx.beginPath();
          ctx.arc(cx, cy, 7, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(139,92,246,0.5)";
          ctx.lineWidth = 1.5;
          ctx.shadowColor = "#7c3aed";
          ctx.shadowBlur = 12;
          ctx.stroke();
          ctx.shadowBlur = 0;
          // Внутренний кружок
          ctx.beginPath();
          ctx.arc(cx, cy, 3.5, 0, Math.PI * 2);
          ctx.fillStyle = "rgba(167,139,250,0.9)";
          ctx.shadowColor = "#a78bfa";
          ctx.shadowBlur = 8;
          ctx.fill();
          ctx.shadowBlur = 0;
        });
      }

      // Кнопка отсоединения
      const mx = (fx + tx) / 2;
      const my = (fy + ty) / 2;
      const btn = document.createElement("div");
      btn.className = "connDisconnectBtn";
      btn.textContent = "✕";
      btn.style.cssText = `
        position:absolute;
        left:${mx}px;
        top:${my}px;
        transform:translate(-50%,-50%);
        background:rgba(15,18,30,0.95);
        border:1px solid rgba(16,245,168,0.4);
        border-radius:50%;
        color:#10f5a8;
        font:700 11px 'Space Grotesk',sans-serif;
        width:20px;height:20px;
        display:flex;align-items:center;justify-content:center;
        cursor:pointer;
        z-index:50;
        pointer-events:all;
        opacity:0;
        transition:opacity 0.15s;
        box-shadow:0 0 10px rgba(16,245,168,0.3);
      `;
      btn.addEventListener("mouseenter", () => btn.style.opacity = "1");
      btn.addEventListener("mouseleave", () => btn.style.opacity = "0");
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const conn = connections[idx];
        const aiId = conn.from.startsWith("ai_") ? conn.from : conn.to.startsWith("ai_") ? conn.to : null;
        if (aiId) {
          const cardId = aiId.replace("ai_", "");
          const aiCard = analyticsCards.find(c => c.cardId === cardId);
          if (aiCard) {
            aiCard.accountId = null;
            fetch(WORKER_API + `/api/analytics-cards/${encodeURIComponent(cardId)}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ account_id: null }),
            }).catch(() => {});
          }
        }
        connections.splice(idx, 1);
        saveConnections();
        drawConnections();
      });
      wrapper.appendChild(btn);
    });
  }

  // Анимационный цикл для бегущих частиц
  let _animFrameId = null;
  function _startAnimLoop() {
    if (_animFrameId) return;
    function loop() {
      const hasActive = connections.some(conn => {
        const fromId = (!conn.from.startsWith("ai_") && !conn.from.startsWith("timer_")) ? conn.from : null;
        const toId   = (!conn.to.startsWith("ai_")   && !conn.to.startsWith("timer_"))   ? conn.to   : null;
        return (fromId && runningSplits.has(fromId)) || (toId && runningSplits.has(toId));
      });
      if (hasActive) {
        drawConnections();
        _animFrameId = requestAnimationFrame(loop);
      } else {
        _animFrameId = null;
        drawConnections();
      }
    }
    _animFrameId = requestAnimationFrame(loop);
  }
  window._clawStartAnim = _startAnimLoop;
  window._clawDrawWeb = drawConnections;

  applyTransform();
}

function placeGroupOnCanvas(group, accountId) {
  const saved = canvasPositions[accountId];
  if (saved) {
    group.style.left = saved.x + "px";
    group.style.top = saved.y + "px";
  } else {
    // Авто-расстановка по спирали
    const idx = document.getElementById("accountsList").querySelectorAll(".sqGroup").length;
    const angle = idx * 2.4;
    const radius = 60 + idx * 55;
    const cx = 500, cy = 100;
    const x = cx + Math.cos(angle) * radius;
    const y = cy + Math.sin(angle) * radius;
    group.style.left = x + "px";
    group.style.top = y + "px";
    canvasPositions[accountId] = { x, y };
    saveCanvasPositions();
  }
}

function drawWebIfReady() {
  window.dispatchEvent(new Event("resize"));
}

function renderSquareGridFromCache() {
  renderSquareGrid(cachedAccounts, cachedLogs);
}

function renderSquareGrid(accounts, statsMap) {
  if (!accountsList) return;

  const filtered = accounts.filter(a => {
    if ((a.platform || "").toLowerCase() !== activePlatform.toLowerCase()) return false;
    if (activeTabId) {
      const tab = operatorTabs.find(t => t.id === activeTabId);
      const tabAccounts = tab?.account_ids || [];
      return tabAccounts.includes(a.id);
    }
    return true;
  });

  const empty = document.getElementById("gridEmpty");
  const intCityPanel = document.getElementById("intCityPanel");
  if (intCityPanel) intCityPanel.style.display = "none";
  if (accountsList) accountsList.style.display = "";

  if (!filtered.length) {
    if (empty) empty.style.display = "none";
    accountsList.querySelectorAll(".sqGroup").forEach(el => el.remove());
    return;
  }
  if (empty) empty.style.display = "none";

  // Удаляем карточки которых больше нет
  const filteredIds = new Set(filtered.map(a => a.id));
  accountsList.querySelectorAll(".sqGroup").forEach(el => {
    const id = el.dataset.accountId;
    if (!filteredIds.has(id)) el.remove();
  });

  // Добавляем/обновляем только изменившиеся
  filtered.forEach((account, idx) => {
    const stats = statsMap[account.id] || { liked: 0, replied: 0, contacts: 0 };
    const existing = accountsList.querySelector(`.sqGroup[data-account-id="${account.id}"]`);
    if (existing) return; // уже есть — не трогаем

    const analyst = analyticsCards.find(c => c.accountId === account.id);
    const group = document.createElement("div");
    group.className = "sqGroup";
    group.dataset.accountId = account.id;

    const node = createSquareCard(account, stats);
    group.appendChild(node);

  

    group.style.position = "absolute";
    placeGroupOnCanvas(group, account.id);
    accountsList.appendChild(group);
    setTimeout(() => {
      const canvas = document.getElementById("webCanvas");
      if (canvas) {
        const ctx = canvas.getContext("2d");
        // триггер перерисовки паутины
        document.getElementById("canvasWrapper") && drawWebIfReady();
      }
    }, 50);
  });

  return; // дальше старый код не нужен
}

function renderAiAccountOptions(accounts) {
  // старой формы AI больше нет — ничего не делаем
}

let timerCards = [];

function saveTimerCards() {
  try { localStorage.setItem("claw_timer_cards", JSON.stringify(timerCards)); } catch {}
}

function loadTimerCards() {
  try {
    const raw = localStorage.getItem("claw_timer_cards");
    if (raw) timerCards = JSON.parse(raw);
  } catch {}
}

function addTimerCard() {
  const id = "timer_" + Date.now();
  const container = document.getElementById("accountsList");
  if (!container) return;

  const x = (window._ctxSpawnX != null) ? window._ctxSpawnX : 400 + Math.random() * 200;
  const y = (window._ctxSpawnY != null) ? window._ctxSpawnY : 200 + Math.random() * 200;
  window._ctxSpawnX = null;
  window._ctxSpawnY = null;

  const card = { id, workMin: 1, workSec: 0, pauseMin: 0, pauseSec: 30, x, y, platform: activePlatform };
  timerCards.push(card);
  saveTimerCards();
  renderTimerCard(card);
}

function renderTimerCard(card) {
  const container = document.getElementById("accountsList");
  if (!container) return;

  const existing = container.querySelector(`.sqTimerGroup[data-timer-id="${card.id}"]`);
  if (existing) existing.remove();

  const group = document.createElement("div");
  group.className = "sqTimerGroup";
  group.dataset.timerId = card.id;
  group.dataset.accountId = card.id;
  group.style.cssText = `position:absolute;left:${card.x}px;top:${card.y}px;cursor:grab;z-index:10;`;

  // Точка соединения
  const dot = document.createElement("div");
  dot.className = "sqConnectDot";
  dot.title = "Потяни чтобы соединить";
  dot.style.cssText = "position:absolute;top:50%;right:-10px;transform:translateY(-50%);width:16px;height:16px;border-radius:50%;background:var(--accent3);border:2px solid var(--bg);cursor:crosshair;z-index:10;box-shadow:0 0 8px rgba(16,245,168,0.6);";
  group.appendChild(dot);

  group.innerHTML += `
    <div style="background:rgba(15,18,30,0.97);border:1px solid rgba(251,191,36,0.4);border-radius:12px;padding:14px 16px;min-width:200px;position:relative;">
      <button class="sqTimerDeleteBtn" style="position:absolute;top:6px;right:6px;background:none;border:none;color:#fb7185;cursor:pointer;font-size:14px;opacity:0.6;">✕</button>
      <div style="font:700 11px 'Orbitron',sans-serif;color:#fbbf24;letter-spacing:0.06em;margin-bottom:12px;">⏱ ТАЙМЕР</div>
      <div style="font:500 11px 'Space Grotesk',sans-serif;color:rgba(255,255,255,0.5);margin-bottom:4px;">Работает</div>
      <div style="display:flex;gap:6px;align-items:center;margin-bottom:10px;">
        <input class="sqTimerWorkMin" type="number" min="0" max="999" value="${card.workMin}" style="width:54px;padding:5px 8px;border-radius:6px;border:1px solid rgba(251,191,36,0.3);background:rgba(5,8,16,0.8);color:#fbbf24;font:600 13px 'JetBrains Mono',monospace;text-align:center;" />
        <span style="color:rgba(255,255,255,0.4);font-size:11px;">мин</span>
        <input class="sqTimerWorkSec" type="number" min="0" max="59" value="${card.workSec}" style="width:54px;padding:5px 8px;border-radius:6px;border:1px solid rgba(251,191,36,0.3);background:rgba(5,8,16,0.8);color:#fbbf24;font:600 13px 'JetBrains Mono',monospace;text-align:center;" />
        <span style="color:rgba(255,255,255,0.4);font-size:11px;">сек</span>
      </div>
      <div style="font:500 11px 'Space Grotesk',sans-serif;color:rgba(255,255,255,0.5);margin-bottom:4px;">Пауза перед перезапуском</div>
      <div style="display:flex;gap:6px;align-items:center;margin-bottom:12px;">
        <input class="sqTimerPauseMin" type="number" min="0" max="999" value="${card.pauseMin}" style="width:54px;padding:5px 8px;border-radius:6px;border:1px solid rgba(92,110,248,0.3);background:rgba(5,8,16,0.8);color:#a5b4fc;font:600 13px 'JetBrains Mono',monospace;text-align:center;" />
        <span style="color:rgba(255,255,255,0.4);font-size:11px;">мин</span>
        <input class="sqTimerPauseSec" type="number" min="0" max="59" value="${card.pauseSec}" style="width:54px;padding:5px 8px;border-radius:6px;border:1px solid rgba(92,110,248,0.3);background:rgba(5,8,16,0.8);color:#a5b4fc;font:600 13px 'JetBrains Mono',monospace;text-align:center;" />
        <span style="color:rgba(255,255,255,0.4);font-size:11px;">сек</span>
      </div>
      <div class="sqTimerStatus" style="font:400 11px 'JetBrains Mono',monospace;color:rgba(255,255,255,0.4);margin-bottom:10px;min-height:16px;"></div>
      <button class="sqTimerStartBtn" style="width:100%;padding:7px;border-radius:7px;border:1px solid rgba(251,191,36,0.4);background:rgba(251,191,36,0.1);color:#fbbf24;font:700 11px 'Orbitron',sans-serif;cursor:pointer;letter-spacing:0.06em;">▶ ВКЛЮЧИТЬ</button>
    </div>
  `;

  // Drag
  group.addEventListener("mousedown", (e) => {
    if (e.target.closest(".sqConnectDot")) return;
    if (e.target.closest("button, input")) return;
    e.preventDefault();
    e.stopPropagation();
    const wrapper = document.getElementById("canvasWrapper");
    const rect = wrapper.getBoundingClientRect();
    const ox = e.clientX - rect.left - parseFloat(group.style.left);
    const oy = e.clientY - rect.top - parseFloat(group.style.top);
    group.style.zIndex = "100";
    function move(e) {
      const x = e.clientX - rect.left - ox;
      const y = e.clientY - rect.top - oy;
      group.style.left = x + "px";
      group.style.top = y + "px";
      card.x = x; card.y = y;
      canvasPositions[card.id] = { x, y };
      if (window._clawDrawWeb) window._clawDrawWeb();
    }
    function up() {
      group.style.zIndex = "";
      saveTimerCards();
      saveCanvasPositions();
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    }
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  });

  // Удалить
  group.querySelector(".sqTimerDeleteBtn").onclick = (e) => {
    e.stopPropagation();
    stopTimerCard(card.id);
    timerCards = timerCards.filter(c => c.id !== card.id);
    saveTimerCards();
    group.remove();
    if (window._clawDrawWeb) window._clawDrawWeb();
  };

  // Сохранение значений при изменении
  group.querySelector(".sqTimerWorkMin").addEventListener("input", (e) => { card.workMin = parseInt(e.target.value) || 0; saveTimerCards(); });
  group.querySelector(".sqTimerWorkSec").addEventListener("input", (e) => { card.workSec = parseInt(e.target.value) || 0; saveTimerCards(); });
  group.querySelector(".sqTimerPauseMin").addEventListener("input", (e) => { card.pauseMin = parseInt(e.target.value) || 0; saveTimerCards(); });
  group.querySelector(".sqTimerPauseSec").addEventListener("input", (e) => { card.pauseSec = parseInt(e.target.value) || 0; saveTimerCards(); });

  // Старт/стоп
  const startBtn = group.querySelector(".sqTimerStartBtn");
  const statusEl = group.querySelector(".sqTimerStatus");

  // Восстанавливаем состояние после перезагрузки
  if (card.watching) {
    card._watching = true;
    startBtn.innerHTML = "⏹ ВЫКЛЮЧИТЬ";
    startBtn.style.background = "rgba(251,191,36,0.2)";
    startBtn.style.borderColor = "rgba(251,191,36,0.8)";
    statusEl.textContent = "Слежу за сплитом...";
    watchTimerCard(card, statusEl, startBtn);
  }

  startBtn.onclick = () => {
    if (card._watching) {
      card._watching = false;
      card.watching = false;
      stopTimerCard(card.id);
      saveTimerCards();
      startBtn.innerHTML = "▶ ВКЛЮЧИТЬ";
      startBtn.style.background = "rgba(251,191,36,0.1)";
      startBtn.style.borderColor = "rgba(251,191,36,0.4)";
      statusEl.textContent = "Выключен";
    } else {
      card._watching = true;
      card.watching = true;
      saveTimerCards();
      startBtn.innerHTML = "⏹ ВЫКЛЮЧИТЬ";
      startBtn.style.background = "rgba(251,191,36,0.2)";
      startBtn.style.borderColor = "rgba(251,191,36,0.8)";
      statusEl.textContent = "Слежу за сплитом...";
      watchTimerCard(card, statusEl, startBtn);
    }
  };

  container.appendChild(group);
  canvasPositions[card.id] = { x: card.x, y: card.y };
  if (window._clawDrawWeb) window._clawDrawWeb();
}

const _timerIntervals = {};

function stopTimerCard(cardId) {
  const card = timerCards.find(c => c.id === cardId);
  if (!card) return;
  card._running = false;
  if (_timerIntervals[cardId]) {
    clearTimeout(_timerIntervals[cardId]);
    delete _timerIntervals[cardId];
  }
}

function watchTimerCard(card, statusEl, startBtn) {
  const workMs  = (card.workMin * 60 + card.workSec) * 1000;
  const pauseMs = (card.pauseMin * 60 + card.pauseSec) * 1000;

  if (workMs === 0) { statusEl.textContent = "Укажи время работы"; card._watching = false; return; }

  function getLinkedAccountIds() {
    const conns = JSON.parse(localStorage.getItem("claw_connections") || "[]");
    return conns
      .filter(c => c.from === card.id || c.to === card.id)
      .map(c => c.from === card.id ? c.to : c.from)
      .filter(id => !id.startsWith("ai_") && !id.startsWith("timer_"));
  }

  function waitForSplit() {
    if (!card._watching) return;
    const accountIds = getLinkedAccountIds();
    if (!accountIds.length) {
      statusEl.textContent = "⚠ Привяжи анкету ниткой";
      _timerIntervals[card.id] = setTimeout(waitForSplit, 1000);
      return;
    }
    const running = accountIds.filter(id => runningSplits.has(id));
    if (running.length) {
      statusEl.textContent = `▶ Сплит обнаружен (${running.length}), запускаю отсчёт...`;
      startWorkCountdown(accountIds);
    } else {
      statusEl.textContent = `Слежу... (${accountIds.length} анкет, жду сплита)`;
      _timerIntervals[card.id] = setTimeout(waitForSplit, 1000);
    }
  }

  function startWorkCountdown(accountIds) {
    let remaining = workMs;
    const tick = () => {
      if (!card._watching) return;
      remaining -= 1000;
      const m = Math.floor(remaining / 60000);
      const s = Math.floor((remaining % 60000) / 1000);
      statusEl.textContent = `▶ Работает: ${m}м ${s}с (${accountIds.length} анкет)`;
      if (remaining > 0) {
        _timerIntervals[card.id] = setTimeout(tick, 1000);
      } else {
        stopSplitAndPause(accountIds);
      }
    };
    _timerIntervals[card.id] = setTimeout(tick, 1000);
  }

  async function stopSplitAndPause(accountIds) {
    if (!card._watching) return;
    statusEl.textContent = "⏸ Останавливаю сплиты...";
    for (const accountId of accountIds) {
      try {
        const splitBtn = document.querySelector(`.sqGroup[data-account-id="${accountId}"] .sqSplitBtn`);
        if (splitBtn) {
          splitBtn.click();
          await new Promise(r => setTimeout(r, 300));
        }
        await fetch(WORKER_API + "/api/tasks/stop", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ account_id: accountId }),
        });
        await setAccountRunStatus(accountId, "idle", "", "");
        runningSplits.delete(accountId);
      } catch {}
    }

    if (!card._watching) return;

    if (pauseMs === 0) {
      statusEl.textContent = `Слежу... (${accountIds.length} анкет, жду сплита)`;
      _timerIntervals[card.id] = setTimeout(waitForSplit, 1000);
      return;
    }

    let remaining = pauseMs;
    const tick = () => {
      if (!card._watching) return;
      remaining -= 1000;
      const m = Math.floor(remaining / 60000);
      const s = Math.floor((remaining % 60000) / 1000);
      statusEl.textContent = `⏸ Перезапуск через: ${m}м ${s}с`;
      if (remaining > 0) {
        _timerIntervals[card.id] = setTimeout(tick, 1000);
      } else {
        restartSplits(accountIds);
      }
    };
    _timerIntervals[card.id] = setTimeout(tick, 1000);
  }

  async function restartSplits(accountIds) {
    if (!card._watching) return;
    statusEl.textContent = `▶ Перезапускаю ${accountIds.length} сплитов...`;
    for (const accountId of accountIds) {
      try {
        const splitBtn = document.querySelector(`.sqGroup[data-account-id="${accountId}"] .sqSplitBtn`);
        if (splitBtn && !splitBtn.classList.contains("running")) splitBtn.click();
        await new Promise(r => setTimeout(r, 300));
      } catch {}
    }
    _timerIntervals[card.id] = setTimeout(() => {
      const currentIds = getLinkedAccountIds();
      if (currentIds.some(id => runningSplits.has(id))) {
        startWorkCountdown(currentIds);
      } else {
        waitForSplit();
      }
    }, 2000);
  }

  waitForSplit();
}

function renderTimerCardsOnCanvas() {
  try {
    const raw = localStorage.getItem("claw_timer_cards");
    if (raw) timerCards = JSON.parse(raw);
  } catch {}
  const container = document.getElementById("accountsList");
  if (container) container.querySelectorAll(".sqTimerGroup").forEach(el => el.remove());
  timerCards.filter(c => (c.platform || "Mamba") === activePlatform).forEach(card => {
    renderTimerCard(card);
  });
}

function renderAICardsOnCanvas() {
  const container = document.getElementById("accountsList");
  if (!container) return;

  container.querySelectorAll(".sqAIGroup").forEach(el => el.remove());

  analyticsCards.filter(card => (card.platform || "Mamba") === activePlatform).forEach(card => {
    const group = document.createElement("div");
    group.className = "sqAIGroup";
    group.dataset.cardId = card.cardId;
    group.dataset.accountId = "ai_" + card.cardId;
    group.style.position = "absolute";
    group.style.cursor = "grab";

    const dot = document.createElement("div");
    dot.className = "sqConnectDot";
    dot.title = "Потяни чтобы соединить";
    dot.style.cssText = "position:absolute;top:50%;right:-10px;transform:translateY(-50%);width:16px;height:16px;border-radius:50%;background:var(--accent3);border:2px solid var(--bg);cursor:crosshair;z-index:10;box-shadow:0 0 8px rgba(16,245,168,0.6);";
    group.appendChild(dot);

    const aCard = document.createElement("div");
    aCard.className = "sqAnalyticsCard";
    aCard.style.cssText = "min-width:160px;cursor:grab;position:relative;";
    aCard.innerHTML = `
      <button class="sqAIDeleteBtn" data-card-id="${card.cardId}" style="position:absolute;top:6px;right:6px;background:none;border:none;color:#fb7185;cursor:pointer;font-size:14px;line-height:1;opacity:0.6;">✕</button>
      <button class="sqAIEditBtn" data-card-id="${card.cardId}" style="position:absolute;top:6px;right:26px;background:none;border:none;color:#a5b4fc;cursor:pointer;font-size:12px;line-height:1;opacity:0.6;">✎</button>
      <div class="sqACardHead">AI</div>
      <div class="sqACardName">${card.botName ? `${card.botName}, ${card.botAge}` : "Аналитик"}</div>
      <div class="sqACardRow"><span class="sqALabel">Контакт</span><span class="sqAVal">${card.contacts || "—"}</span></div>
    `;

    aCard.querySelector(".sqAIDeleteBtn").onclick = async (e) => {
      e.stopPropagation();
      group.remove();
      analyticsCards = analyticsCards.filter(c => c.cardId !== card.cardId);
      // Чистим нитки связанные с этой AI-карточкой
      const aiNodeId = "ai_" + card.cardId;
      try {
        const conns = JSON.parse(localStorage.getItem("claw_connections") || "[]");
        const filtered = conns.filter(c => c.from !== aiNodeId && c.to !== aiNodeId);
        localStorage.setItem("claw_connections", JSON.stringify(filtered));
        if (window._clawDrawWeb) window._clawDrawWeb();
      } catch {}
      try {
        await fetch(WORKER_API + `/api/analytics-cards/${encodeURIComponent(card.cardId)}`, { method: "DELETE" });
      } catch {}
    };

    aCard.querySelector(".sqAIEditBtn").onclick = (e) => {
      e.stopPropagation();
      const saveBtn = document.getElementById("aModalSaveBtn");
      document.getElementById("aModalBotName").value         = card.botName || "";
      document.getElementById("aModalBotAge").value          = card.botAge || "";
      document.getElementById("aModalBotGender").value       = card.botGender || "female";
      document.getElementById("aModalLocation").value        = card.location || "";
      document.getElementById("aModalContacts").value        = card.contacts || "";
      document.getElementById("aModalContactsTrigger").value = card.contactsTrigger || "";
      saveBtn.dataset.editCardId    = card.cardId;
      saveBtn.dataset.editAccountId = card.accountId || "";
      document.getElementById("analyticsModal").classList.add("open");
    };

    group.appendChild(aCard);


    const saved = canvasPositions[`ai_${card.cardId}`];
    if (saved) {
      group.style.left = saved.x + "px";
      group.style.top = saved.y + "px";
    } else {
      const x = (window._ctxSpawnX != null) ? window._ctxSpawnX : 700 + Math.random() * 200;
      const y = (window._ctxSpawnY != null) ? window._ctxSpawnY : 100 + Math.random() * 200;
      window._ctxSpawnX = null;
      window._ctxSpawnY = null;
      group.style.left = x + "px";
      group.style.top = y + "px";
      canvasPositions[`ai_${card.cardId}`] = { x, y };
      saveCanvasPositions();
    }

    container.appendChild(group);
  });
}

// ── Навигация ─────────────────────────────────────────────

function openPage(pageName) {
  if (!pageInfo[pageName]) pageName = "home";
  navButtons.forEach(btn => btn.classList.toggle("active", btn.dataset.page === pageName));
  pages.forEach(p => {
    p.classList.remove("activePage");
    p.style.display = "none";
  });
  const activePage = document.getElementById(`${pageName}Page`);
  if (activePage) {
    activePage.classList.add("activePage");
    activePage.style.display = (pageName === "tables" || pageName === "home") ? "flex" : "block";
    const appEl = document.querySelector(".app");
    if (pageName === "tables") {
      if (appEl) {
        appEl.style.overflow = "visible";
        appEl.style.position = "static";
        appEl.style.zIndex = "0";
      }
      document.body.appendChild(activePage);
    } else {
      if (appEl) {
        appEl.style.overflow = "";
        appEl.style.position = "";
        appEl.style.zIndex = "";
      }
    }
  }
  try { localStorage.setItem(STORAGE_KEY, pageName); } catch {}
  if (pageName === "tasks") {
    showChatsView("accounts");
    loadChatsAccountsList();
  }
  if (pageName === "tables") {
    if (!window._sheetInited) {
      window._sheetInited = true;
      initSheetApp(document.getElementById("sheetApp"));
    }
    setTimeout(() => {
      const c = document.querySelector("#sh_gridScroll canvas");
      if (c) c.focus();
    }, 100);
  }
  if (pageName === "analytics") {
    initReportPage();
  }
  if (pageName === "settings") {
    setTimeout(() => loadProxySettings(), 150);
  }
  if (pageName === "contacts") {
    loadContacts();
  }
}

navButtons.forEach(btn => btn.addEventListener("click", () => {
  openPage(btn.dataset.page);
  if (btn.dataset.page === "settings") {
    setTimeout(() => loadProxySettings(), 150);
  }
}));

// ── Форма подключения ─────────────────────────────────────

// ── Twinby: отправка кода ─────────────────────────────────
connectSlots.addEventListener("click", async (e) => {
  const btn = e.target.closest(".slotTwinbySendCode");
  if (!btn) return;
  const slot = btn.closest(".connectSlot");
  const email = slot.querySelector(".slotTwinbyEmail").value.trim();
  if (!email) { alert("Введи email"); return; }
  btn.disabled = true;
  btn.textContent = "Отправляю...";
  try {
    const resp = await fetch(WORKER_API + "/api/twinby/send-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    const data = await resp.json();
    if (!data.ok) throw new Error(data.error || "Ошибка");
    btn.textContent = "Код отправлен ✓";
  } catch(err) {
    btn.textContent = "Ошибка — попробуй ещё";
    btn.disabled = false;
    alert(err.message);
  }
});

// ── Vznakomstve: отправка кода ────────────────────────────
connectSlots.addEventListener("click", async (e) => {
  const btn = e.target.closest(".slotVznSendCode");
  if (!btn) return;
  const slot = btn.closest(".connectSlot");
  const email = slot.querySelector(".slotVznEmail").value.trim();
  if (!email) { alert("Введи email"); return; }
  btn.disabled = true;
  btn.textContent = "Отправляю...";
  try {
    const resp = await fetch(WORKER_API + "/api/vznakomstve/send-code", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });
    const data = await resp.json();
    if (!data.ok) throw new Error(data.error || "Ошибка");
    btn.textContent = "Код отправлен ✓";
    slot.querySelector(".slotVznCodeRow").style.display = "";
  } catch(err) {
    btn.textContent = "Ошибка — попробуй ещё";
    btn.disabled = false;
    alert(err.message);
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const slotEls = [...connectSlots.querySelectorAll(".connectSlot")];

  const jobs = slotEls.map(slotEl => {
    const isTwinby  = activePlatform === "Twinby";
    const isVzn     = activePlatform === "Vznakomstve";
    const isIntCity = activePlatform === "intCity";
    return {
      slotEl,
      name:        slotEl.querySelector(".slotAccountName").value.trim(),
      url:         (isTwinby || isVzn || isIntCity) ? "" : slotEl.querySelector(".slotCheckUrl").value.trim(),
      rawCookies:  (isTwinby || isVzn) ? "" : isIntCity ? (slotEl.querySelector(".slotIntCityCookiesJson")?.value.trim() || "") : (slotEl.querySelector(".slotCookiesJson")?.value.trim() || ""),
      twinbyEmail: isTwinby ? slotEl.querySelector(".slotTwinbyEmail").value.trim() : "",
      twinbyCode:  isTwinby ? slotEl.querySelector(".slotTwinbyCode").value.trim() : "",
      vznEmail:        isVzn ? slotEl.querySelector(".slotVznEmail").value.trim() : "",
      vznCode:         isVzn ? slotEl.querySelector(".slotVznCode").value.trim() : "",
      intCityEmail:    "",
      intCityPassword: "",
      isTwinby,
      isIntCity,
      isVzn,
    };
  }).filter(j => j.name || j.url || j.rawCookies || j.twinbyEmail || j.vznEmail || j.isIntCity);

  if (!jobs.length) { setResult("Заполни хотя бы одну анкету.", "bad"); return; }

  for (const j of jobs) {
    if (j.isTwinby) {
      if (!j.twinbyEmail) { setResult(`Анкета "${j.name || "без имени"}": введи email.`, "bad"); return; }
      if (!j.twinbyCode)  { setResult(`Анкета "${j.name || "без имени"}": введи код из письма.`, "bad"); return; }
    } else if (j.isVzn) {
      if (!j.vznEmail) { setResult(`Анкета "${j.name || "без имени"}": введи email.`, "bad"); return; }
      if (!j.vznCode)  { setResult(`Анкета "${j.name || "без имени"}": введи код из письма.`, "bad"); return; }
    } else if (j.isIntCity) {
      if (!j.rawCookies) { setResult(`Анкета "${j.name || "без имени"}": вставь Cookie Editor JSON.`, "bad"); return; }
    } else {
      if (!j.url.startsWith("http")) { setResult(`Анкета "${j.name || "без имени"}": URL должен начинаться с http.`, "bad"); return; }
      if (!j.rawCookies) { setResult(`Анкета "${j.name || "без имени"}": вставь Cookie-Editor JSON.`, "bad"); return; }
    }
  }

  connectBtn.disabled    = true;
  connectBtn.textContent = "Подключаю...";

  let succeeded = 0;
  let failed    = 0;

  for (let i = 0; i < jobs.length; i++) {
    const j = jobs[i];
    setResult(`Подключаю ${i + 1}/${jobs.length}: ${j.name || j.url}...`);

    try {
      const response = await fetch(WORKER_API + "/api/connect", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": localStorage.getItem("claw_auth_token") || "",
        },
        body: JSON.stringify({
          account_name: j.name,
          profile_url:  j.url || "https://vznakomstve.com/app/",
          cookies_raw:  j.rawCookies,
          platform:     activePlatform,
          twinby_email: j.twinbyEmail,
          twinby_code:  j.twinbyCode,
          vzn_email:         j.vznEmail,
          vzn_code:          j.vznCode,
          intcity_email:     j.intCityEmail,
          intcity_password:  j.intCityPassword,
        }),
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.detail || data.error || "Ошибка подключения");
      succeeded++;
      j.slotEl.style.opacity = "0.4";
    } catch (error) {
      failed++;
      j.slotEl.style.borderColor = "rgba(255,60,60,.6)";
      const errLabel = document.createElement("div");
      errLabel.className = "result bad";
      errLabel.style.marginTop = "8px";
      errLabel.textContent = error.message || "Ошибка подключения.";
      j.slotEl.appendChild(errLabel);
    }
  }

  await loadAccounts();

  setResult(
    failed
      ? `Готово: ${succeeded} подключено, ${failed} с ошибкой (см. под полями).`
      : `Готово: все ${succeeded} анкеты подключены.`,
    failed ? "bad" : "good"
  );

  // Прячем панель подключения после успешного подключения
  if (!failed) {
    setTimeout(() => {
      const form = document.getElementById("connectForm");
      if (form) form.style.display = "none";
    }, 2000);
  }

  // оставляем неудачные слоты на экране, удачные — очищаем форму
  if (!failed) {
    connectSlots.innerHTML = "";
    addConnectSlot();
  }

  connectBtn.disabled    = false;
  connectBtn.textContent = "Подключить и достать фото";
});


// ── AI-Менеджер: настройки ────────────────────────────────

async function loadAiSettings(accountId) {
  if (!accountId) {
    aiSettingsForm.reset();
    aiGroqModel.value = "llama-3.3-70b-versatile";
    setBoxResult(aiSettingsResult, "Выбери анкету, чтобы загрузить настройки.");
    return;
  }
  setBoxResult(aiSettingsResult, "Загружаю настройки...");
  try {
    const res  = await fetch(WORKER_API + `/api/ai-settings/${encodeURIComponent(accountId)}`);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Не удалось загрузить настройки");
    const s = data.settings || {};
    aiGroqKey.value         = s.groq_api_key  || "";
    aiGroqModel.value       = s.groq_model    || "llama-3.3-70b-versatile";
    aiBotIdentity.value     = s.bot_identity  || "";
    aiPersona.value         = s.persona       || "";
    aiGoal.value            = s.goal          || "";
    aiStopTopics.value      = s.stop_topics   || "";
    aiContacts.value        = s.contacts      || "";
    aiContactsTrigger.value = s.contacts_trigger || "";
    setBoxResult(aiSettingsResult, s.updated_at ? `Настройки загружены. Изменено: ${formatDate(s.updated_at)}` : "Настройки пока не заданы.");
  } catch (err) {
    setBoxResult(aiSettingsResult, err.message || "Ошибка загрузки настроек.", "bad");
  }
}


// ── AI Аналитики ──────────────────────────────────────────

const addAnalyticsBtn = document.getElementById("addAnalyticsBtn");
const analyticsGrid   = document.getElementById("analyticsGrid");
const analyticsEmpty  = document.getElementById("analyticsEmpty");
const analyticsCardTpl = document.getElementById("analyticsCardTemplate");

let analyticsCards = [];

async function loadAnalyticsCards() {
  try {
    const res = await fetch(WORKER_API + "/api/analytics-cards");

    if (!res.ok) {
      throw new Error(`Ошибка загрузки аналитиков: HTTP ${res.status}`);
    }

    const data = await res.json();

    analyticsCards = (data.cards || []).map(c => ({
      cardId:          c.id,
      accountId:       c.account_id,
      platform:        c.platform || "Mamba",
      botName:         c.bot_name || "",
      botAge:          c.bot_age || "",
      botGender:       c.bot_gender || "female",
      location:        c.location || "",
      persona:         c.persona || "",
      goal:            c.goal || "",
      stopTopics:      c.stop_topics || "",
      contacts:        c.contacts || "",
      contactsTrigger: c.contacts_trigger || "",
    }));

    try {
      localStorage.setItem(ANALYTICS_CACHE_KEY, JSON.stringify(analyticsCards));
    } catch {}
  } catch (err) {
    console.error("loadAnalyticsCards error:", err);

    // Важно: analyticsCards здесь не очищаем.
    // При временной ошибке остаются предыдущие карточки.
  }

  return analyticsCards;
}

function renderAnalyticsGrid(accounts) {
  if (!analyticsGrid) return;
  analyticsGrid.querySelectorAll(".analyticsCard").forEach(el => el.remove());

  if (!analyticsCards.length) {
    if (analyticsEmpty) analyticsEmpty.style.display = "flex";
    return;
  }
  if (analyticsEmpty) analyticsEmpty.style.display = "none";

  analyticsCards.forEach((card, idx) => {
    const account = accounts.find(a => a.id === card.accountId);
    const node = analyticsCardTpl.content.cloneNode(true);
    node.querySelector(".analyticsCardName").textContent    = card.botName ? `${card.botName}, ${card.botAge}` : "Аналитик";
    node.querySelector(".analyticsCardAccount").textContent = account ? account.name : "—";
    node.querySelector(".analyticsContact").textContent     = card.contacts || "—";
    node.querySelector(".analyticsPersona").textContent     = card.persona || "—";
    node.querySelector(".analyticsGoal").textContent        = card.goal || "—";

    const deleteBtn = node.querySelector(".analyticsCardDelete");
    deleteBtn.dataset.cardId = card.cardId;
    deleteBtn.onclick = async (e) => {
      e.stopPropagation();
      const cardId = deleteBtn.dataset.cardId;
      if (deleteBtn._deleting) return;
      deleteBtn._deleting = true;
      try {
        if (cardId) {
          await fetch(WORKER_API + `/api/analytics-cards/${encodeURIComponent(cardId)}`, { method: "DELETE" });
        }
      } catch (err) {
        console.error("delete analytics card error:", err);
      }
      await loadAnalyticsCards();
      const accounts = await loadAccounts();
      renderAnalyticsGrid(accounts);
      deleteBtn._deleting = false;
    };

    node.querySelector(".analyticsEditBtn").onclick = () => openAnalyticsModal(card.accountId, accounts, card.cardId);

    analyticsGrid.appendChild(node);
  });
}

async function openAnalyticsModal(accountId, accounts) {
  const saveBtn = document.getElementById("aModalSaveBtn");

  // Если accountId не передан — берём первый аккаунт активной платформы
  let resolvedAccountId = accountId;
  if (!resolvedAccountId && cachedAccounts.length) {
    const platformAcc = cachedAccounts.find(a =>
      (a.platform || "").toLowerCase() === (activePlatform || "").toLowerCase()
    );
    if (platformAcc) resolvedAccountId = platformAcc.id;
  }

  saveBtn.dataset.editAccountId = resolvedAccountId || "";

  // Грузим данные из ai_settings если есть accountId
  let settings = {};
  if (resolvedAccountId) {
    try {
      const res = await fetch(`/api/ai-settings/${encodeURIComponent(resolvedAccountId)}`);
      const data = await res.json();
      if (data.ok) settings = data.settings || {};
    } catch(e) {}
  }

  // Фоллбэк на analyticsCards если ai_settings пустые
  const card = accountId ? (analyticsCards.find(c => c.accountId === accountId) || {}) : {};

  document.getElementById("aModalBotName").value         = settings.bot_name         || card.botName || "";
  document.getElementById("aModalBotAge").value          = settings.bot_age           || card.botAge  || "";
  document.getElementById("aModalBotGender").value       = settings.bot_gender        || card.botGender || "female";
  document.getElementById("aModalLocation").value        = settings.location          || card.location || "";
  document.getElementById("aModalContacts").value        = settings.contacts          || card.contacts || "";
  document.getElementById("aModalContactsTrigger").value = settings.contacts_trigger  || card.contactsTrigger || "";

  document.getElementById("analyticsModal").classList.add("open");
}

addAnalyticsBtn?.addEventListener("click", async () => {
  await openAnalyticsModal(null, cachedAccounts);
});

document.getElementById("analyticsModalClose")?.addEventListener("click", (e) => {
  e.stopPropagation();
  document.getElementById("analyticsModal").classList.remove("open");
});

document.getElementById("analyticsModal")?.addEventListener("click", (e) => {
  if (e.target === document.getElementById("analyticsModal")) {
    document.getElementById("analyticsModal").classList.remove("open");
  }
});

document.getElementById("aModalSaveBtn")?.addEventListener("click", async () => {
  const saveBtn = document.getElementById("aModalSaveBtn");
  const targetAccountId = saveBtn.dataset.editAccountId || null;

  const botName         = document.getElementById("aModalBotName").value.trim();
  const botAge          = document.getElementById("aModalBotAge").value.trim();
  const botGender       = document.getElementById("aModalBotGender").value;
  const location        = document.getElementById("aModalLocation").value.trim();
  const contacts        = document.getElementById("aModalContacts").value.trim();
  const contactsTrigger = document.getElementById("aModalContactsTrigger").value.trim();

  // targetAccountId может быть пустым — карточка создаётся без привязки к анкете
  // привязка происходит через нитку на канвасе
  try {
    const editCardId = saveBtn.dataset.editCardId || null;
    if (editCardId) {
      // Обновляем существующую карточку
      await fetch(WORKER_API + `/api/analytics-cards/${encodeURIComponent(editCardId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bot_name: botName, bot_age: botAge, bot_gender: botGender, location, contacts, contacts_trigger: contactsTrigger }),
      });
    } else {
      // Создаём новую карточку без привязки к анкете
      const res = await fetch(WORKER_API + "/api/analytics-cards", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          account_id: targetAccountId || null,
          bot_name: botName, bot_age: botAge, bot_gender: botGender,
          location, persona: "", goal: "", stop_topics: "",
          contacts, contacts_trigger: contactsTrigger, tg_chat_id: "",
          platform: activePlatform,
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.detail || "Ошибка сохранения");
    }

    // Если есть привязанная анкета — синхронизируем в ai_settings
    if (targetAccountId) {
      await fetch(`/api/ai-settings/${encodeURIComponent(targetAccountId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bot_name: botName, bot_age: botAge, bot_gender: botGender, location, contacts, contacts_trigger: contactsTrigger }),
      });
    }
  } catch (err) {
    alert("Не удалось сохранить: " + err.message);
    return;
  }

  document.getElementById("analyticsModal").classList.remove("open");
  await loadAnalyticsCards();
  renderAICardsOnCanvas();
  delete saveBtn.dataset.editAccountId;
  delete saveBtn.dataset.editCardId;
});

// ── Модалки ───────────────────────────────────────────────

function openLikesModal(accountId) {
  activeModalAccountId = accountId;
  modalLikesResult.textContent = "";
  modalLikesResult.className   = "result";
  likesModal.classList.add("open");
}

function openGroqModal(accountId) {
  activeModalAccountId = accountId;
  modalGroqResult.textContent = "";
  modalGroqResult.className   = "result";
  groqModal.classList.add("open");
}

async function setAccountRunStatus(accountId, status, task = "", note = "", isBlocked = false) {
  try {
    const body = { run_status: status, run_task: task, run_note: note };
    if (isBlocked) body.is_blocked = true;
    const res = await fetch(WORKER_API + `/api/accounts/${encodeURIComponent(accountId)}/run-status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) console.warn("run-status не сохранился:", await res.text());
  } catch (err) {
    console.warn("setAccountRunStatus error:", err);
  }
}

async function runLikes(accountId, limit, resultEl, cardEl) {
  if (resultEl) {
    resultEl.textContent = `Запускаю ${limit} лайков...`;
    resultEl.className = "sqResult";
  }

  cardEl?.classList.add("sqActive");
  const livePollId = startLiveActionPolling(accountId, cardEl);
  await setAccountRunStatus(accountId, "running", "likes", "Лайки запущены");

  try {
    const res = await fetchWithTimeout(WORKER_API + "/api/tasks/likes-http", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_id: accountId, limit }),
    });

    const queued = await res.json();

    if (!res.ok || !queued.ok) {
      throw new Error(queued.detail || queued.error || "Ошибка постановки в очередь");
    }

    const job = await pollJob(queued.job_id);
    if (job.status === "error") {
      throw new Error(job.result?.error || "Ошибка выполнения задачи");
    }

    const data = job.result || {};
    const isCritical = ["vip_limit", "session_error"].includes(data.status);

    if (resultEl) {
      resultEl.textContent = data.summary || "Готово.";
      resultEl.className = isCritical ? "sqResult bad" : "sqResult good";
    }

    loadAccounts();
    loadTasksLog();
  } catch (err) {
    if (resultEl) {
      resultEl.textContent = err.message || "Ошибка.";
      resultEl.className = "sqResult bad";
    }
  } finally {
    clearInterval(livePollId);
    await setAccountRunStatus(accountId, "idle", "", "");
    cardEl?.classList.remove("sqActive");
    loadAccounts();
  }
}

async function pollJob(jobId, { intervalMs = 2000, timeoutMs = 600000 } = {}) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetchWithTimeout(WORKER_API + `/api/jobs/${encodeURIComponent(jobId)}`);
      const data = await res.json();
      if (!res.ok || !data.ok) {
        await new Promise(r => setTimeout(r, intervalMs));
        continue;
      }
      const job = data.job;
      if (["done", "cancelled", "error"].includes(job.status)) {
        return job;
      }
    } catch (e) {
      // сетевая ошибка — продолжаем ждать
    }
    await new Promise(r => setTimeout(r, intervalMs));
  }
  throw new Error("Превышено время ожидания задачи");
}

async function runGroq(accountId, resultEl, cardEl) {
  if (resultEl) {
    resultEl.textContent = "Запускаю автоответы...";
    resultEl.className = "sqResult";
  }

  cardEl?.classList.add("sqActive");
  await setAccountRunStatus(accountId, "running", "groq", "Groq запущен");

  try {
    const res = await fetchWithTimeout(WORKER_API + "/api/tasks/auto-reply-http", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_id: accountId }),
    });

    const data = await res.json();

    if (!res.ok || !data.ok) {
      throw new Error(data.detail || data.error || "Ошибка");
    }

    const isCritical = ["groq_keys_exhausted", "session_error"].includes(data.status);

    if (resultEl) {
      resultEl.textContent = data.summary || "Готово.";
      resultEl.className = isCritical ? "sqResult bad" : "sqResult good";
    }

    loadAccounts();
    loadTasksLog();
  } catch (err) {
    if (resultEl) {
      resultEl.textContent = err.message || "Ошибка.";
      resultEl.className = "sqResult bad";
    }
  } finally {
    await setAccountRunStatus(accountId, "idle", "", "");
    cardEl?.classList.remove("sqActive");
    loadAccounts();
  }
}

async function toggleSplit(accountId, splitBtn, splitInput, likesBtn, groqBtn, likesInput, limit, resultEl, cardEl, platform) {
  if (runningSplits.has(accountId)) {
    runningSplits.delete(accountId);

    if (resultEl) {
      resultEl.textContent = "Останавливаю немедленно...";
      resultEl.className = "sqResult";
    }

    try {
      await fetch(WORKER_API + "/api/tasks/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_id: accountId }),
      });
    } catch (err) {
      console.error("stop error:", err);
    }

    await setAccountRunStatus(accountId, "idle", "", "");

    splitBtn.classList.remove("running");
    splitBtn.innerHTML = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg> Сплит';

    likesBtn.disabled = false;
    groqBtn.disabled = false;
    splitBtn.disabled = false;
    splitInput.disabled = false;
    likesInput.disabled = false;
    cardEl?.classList.remove("sqActive");

    if (resultEl) {
      resultEl.textContent = "Сплит остановлен.";
      resultEl.className = "sqResult";
    }

    loadAccounts();
    return;
  }

  runningSplits.add(accountId);
  if (window._clawStartAnim) window._clawStartAnim();
  window._splitLogs[accountId] = [];
  pushLog(accountId, "Сплит запущен");
  // Инициализируем живой счётчик из текущей статистики
  liveStats[accountId] = {
    liked:    parseInt(cardEl?.querySelector(".sqLikesVal")?.textContent) || 0,
    replied:  parseInt(cardEl?.querySelector(".sqMsgsVal")?.textContent)  || 0,
    contacts: parseInt(cardEl?.querySelector(".sqContactsVal")?.textContent) || 0,
  };
  await setAccountRunStatus(accountId, "running", "split", "Сплит запущен");

  splitBtn.classList.add("running");
  splitBtn.innerHTML = "⏹ Стоп";

  likesBtn.disabled = true;
  groqBtn.disabled = true;
  splitBtn.disabled = false;
  splitInput.disabled = true;
  likesInput.disabled = true;
  cardEl?.classList.add("sqActive");

  const fastPollId = null;
  const livePollId = startLiveActionPolling(accountId, cardEl);
  runSplitLoop(accountId, limit, resultEl, cardEl, fastPollId, livePollId, platform);
}

async function runOneLikesStep(accountId, limit, resultEl, round) {
  try {
    pushLog(accountId, `Круг ${round}: запрос лайков...`);
    const queueRes = await fetchWithTimeout(WORKER_API + "/api/tasks/likes-http", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_id: accountId, limit }),
    }, 30000);

    const queued = await queueRes.json().catch(() => ({}));
    if (!queueRes.ok || queued.ok === false) {
      throw new Error(queued.detail || queued.error || "Ошибка постановки в очередь");
    }

    const job = await pollJob(queued.job_id, { timeoutMs: 120000 });
    const likesData = job.result || {};
    if (job.status === "error" && !likesData.error) {
      likesData.error = "Ошибка выполнения задачи";
    }
    const status = likesData.status || "completed";

    // Моментально обновляем счётчик лайков на карточке
    if (likesData.liked > 0) {
      bumpLiveStat(accountId, "liked", likesData.liked);
    }
    pushLog(accountId, `Лайков поставлено: ${likesData.liked || 0}`);

    if (likesData.blocked || status === "profile_blocked") {
      pushLog(accountId, "БЛОК — запускаю резерв");
      await loadAccounts();
      return {
        blocked: true,
        reserve_account_id:
          likesData.reserve_account_id ||
          likesData.chain_result?.reserve_account_id ||
          null,
        summary: likesData.summary || "Анкета заблокирована",
      };
    }

    if (likesData.ok === false) {
      throw new Error(likesData.detail || likesData.error || likesData.summary || "Ошибка лайков");
    }

    if (status === "vip_limit" || status === "session_error") {
      if (resultEl) {
        resultEl.textContent = `Круг ${round}: ${likesData.summary || "Остановлено."}. Продолжаю...`;
        resultEl.className = "sqResult bad";
      }
    } else if (likesData.liked === 0 && (likesData.skipped > 0 || likesData.errors > 0)) {
      if (resultEl) {
        resultEl.textContent = `Круг ${round}: лимит лайков исчерпан, пропускаю лайки`;
        resultEl.className = "sqResult";
      }
    } else {
      if (resultEl) {
        resultEl.textContent = `Круг ${round}: ${likesData.summary || "лайки готовы"}`;
        resultEl.className = "sqResult good";
      }
    }

    loadTasksLog();
  } catch (err) {
    console.error("SPLIT LIKES ERROR:", err);
    pushLog(accountId, `Круг ${round}: ОШИБКА лайков — ${err.message}`);

    if (resultEl) {
      resultEl.textContent = `Круг ${round}: ошибка лайков — ${err.message}. Продолжаю...`;
      resultEl.className = "sqResult bad";
    }
  }

  return { blocked: false, reserve_account_id: null };
}

async function runOneChatsStep(accountId, resultEl, round, passLabel) {
  try {
    pushLog(accountId, `Круг ${round} (${passLabel}): обрабатываю чаты...`);
    const queueRes = await fetchWithTimeout(WORKER_API + "/api/tasks/auto-reply-http", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_id: accountId }),
    }, 30000);

    const queued = await queueRes.json().catch(() => ({}));
    if (!queueRes.ok || queued.ok === false) {
      throw new Error(queued.detail || queued.error || "Ошибка постановки в очередь");
    }

    const job = await pollJob(queued.job_id, { timeoutMs: 120000 });
    const groqData = job.result || {};
    if (job.status === "error" && !groqData.error) {
      groqData.error = "Ошибка выполнения задачи";
    }
    const groqStatus = groqData.status || "completed";

    // Моментально обновляем счётчики ответов и лидов на карточке
    if (groqData.replied > 0) {
      bumpLiveStat(accountId, "replied", groqData.replied);
    }
    pushLog(accountId, `Ответов отправлено: ${groqData.replied || 0}, контактов: ${groqData.contacts_sent || 0}`);
    if (groqData.contacts_sent > 0) {
      bumpLiveStat(accountId, "contacts", groqData.contacts_sent);
    }

    if (groqData.blocked || groqStatus === "profile_blocked") {
      pushLog(accountId, "БЛОК в чатах — запускаю резерв");
      await loadAccounts();
      renderSquareGridFromCache();
      return {
        blocked: true,
        reserve_account_id:
          groqData.reserve_account_id ||
          groqData.chain_result?.reserve_account_id ||
          null,
        summary: groqData.summary || "Анкета заблокирована",
      };
    }

    if (groqData.ok === false) {
      throw new Error(groqData.detail || groqData.error || groqData.summary || "Ошибка чатов");
    }

    if (groqStatus === "groq_keys_exhausted" || groqStatus === "session_error") {
      if (resultEl) {
        resultEl.textContent = `Круг ${round} (${passLabel}): ${groqData.summary || "Остановлено."}. Продолжаю...`;
        resultEl.className = "sqResult bad";
      }
    } else {
      if (resultEl) {
        resultEl.textContent = `Круг ${round} (${passLabel}): ${groqData.summary || "чаты обработаны"}`;
        resultEl.className = "sqResult good";
      }
    }

    loadTasksLog();
  } catch (err) {
    console.error("SPLIT GROQ ERROR:", err);
    pushLog(accountId, `Круг ${round} (${passLabel}): ОШИБКА чатов — ${err.message}`);

    if (resultEl) {
      resultEl.textContent = `Круг ${round} (${passLabel}): ошибка чатов — ${err.message}. Продолжаю...`;
      resultEl.className = "sqResult bad";
    }
  }

  return { blocked: false, reserve_account_id: null };
}

async function switchSplitToReserve(oldAccountId, blockResult, limit, resultEl, cardEl, fastPollId, livePollId) {
  const reserveId = blockResult?.reserve_account_id || null;

  runningSplits.delete(oldAccountId);

  if (fastPollId) {
    clearInterval(fastPollId);
  }
  if (livePollId) {
    clearInterval(livePollId);
  }

  try {
    await setAccountRunStatus(oldAccountId, "idle", "", "Анкета заблокирована", true);
  } catch (err) {
    console.warn("old blocked status error:", err);
  }

  cardEl?.classList.remove("sqActive");

  if (!reserveId) {
    if (resultEl) {
      resultEl.textContent = "БЛОК: анкета заблокирована, резерв не найден";
      resultEl.className = "sqResult bad";
    }

    await loadAccounts();
    return;
  }

  if (resultEl) {
    resultEl.textContent = `БЛОК: запускаю резерв ${reserveId.slice(0, 8)}...`;
    resultEl.className = "sqResult good";
  }

  runningSplits.add(reserveId);

  await setAccountRunStatus(
    reserveId,
    "running",
    "split",
    "Резерв запущен вместо заблокированной анкеты"
  );

  await loadAccounts();

  const newLivePollId = startLiveActionPolling(reserveId, null);
  runSplitLoop(reserveId, limit, resultEl, null, null, newLivePollId, null);
}

async function runSplitLoop(accountId, limit, resultEl, cardEl, fastPollId, livePollId, platform) {
  const isLovelaz = (platform || "").toLowerCase() === "lovelaz";
  const MAX_ROUNDS = isLovelaz ? Infinity : 5; // Lovelaz: бесконечный цикл без перезапуска

  // Heartbeat — если цикл завис, перезапускаем
  let lastHeartbeat = Date.now();
  const heartbeatInterval = setInterval(() => {
    if (!runningSplits.has(accountId)) {
      clearInterval(heartbeatInterval);
      return;
    }
    if (Date.now() - lastHeartbeat > 3 * 60 * 1000) {
      // Зависли больше 3 минут — перезапускаем сплит
      clearInterval(heartbeatInterval);
      runningSplits.delete(accountId);
      runningSplits.add(accountId);
      runSplitLoop(accountId, limit, resultEl, cardEl, fastPollId, livePollId, platform);
    }
  }, 30000);

  while (runningSplits.has(accountId)) {
    let round = 1;
    lastHeartbeat = Date.now();

    // ── Внутренний цикл: 5 кругов для Mamba, бесконечно для Lovelaz ──
    while (runningSplits.has(accountId) && round <= MAX_ROUNDS) {

      // ── Шаг 1: лайки ──
      if (resultEl) {
        resultEl.textContent = `Круг ${round}: ставлю ${limit} лайков...`;
        resultEl.className = "sqResult";
      }
      pushLog(accountId, `Круг ${round}: ставлю ${limit} лайков...`);

      const likesResult = await runOneLikesStep(accountId, limit, resultEl, round);

      if (likesResult.blocked || likesResult.logged_out) {
        await switchSplitToReserve(accountId, likesResult, limit, resultEl, cardEl, fastPollId, livePollId);
        return;
      }

      if (!runningSplits.has(accountId)) break;

      // ── Шаг 2: первый проход по чатам ──
      await setAccountRunStatus(accountId, "running", "split", `Круг ${round}: чаты (1/2)`);

      if (resultEl) {
        resultEl.textContent = `Круг ${round}: проверяю чаты (1/2)...`;
        resultEl.className = "sqResult";
      }
      pushLog(accountId, `Круг ${round}: чаты (1/2)...`);

      const chatsResult1 = await runOneChatsStep(accountId, resultEl, round, "1/2");

      if (chatsResult1.blocked || chatsResult1.logged_out) {
        await switchSplitToReserve(accountId, chatsResult1, limit, resultEl, cardEl, fastPollId, livePollId);
        return;
      }

      if (!runningSplits.has(accountId)) break;

      // ── Шаг 3: второй проход по чатам ──
      await setAccountRunStatus(accountId, "running", "split", `Круг ${round}: чаты (2/2)`);

      if (resultEl) {
        resultEl.textContent = `Круг ${round}: проверяю чаты (2/2)...`;
        resultEl.className = "sqResult";
      }
      pushLog(accountId, `Круг ${round}: чаты (2/2)...`);

      const chatsResult2 = await runOneChatsStep(accountId, resultEl, round, "2/2");

      if (chatsResult2.blocked || chatsResult2.logged_out) {
        await switchSplitToReserve(accountId, chatsResult2, limit, resultEl, cardEl, fastPollId, livePollId);
        return;
      }

      if (!runningSplits.has(accountId)) break;

      // Сразу переходим к следующему кругу
      if (resultEl) {
        resultEl.textContent = `Круг ${round} завершён, запускаю следующий...`;
        resultEl.className = "sqResult";
      }
      pushLog(accountId, `Круг ${round} завершён, запускаю следующий...`);

      round++;
    } // конец внутреннего цикла (5 кругов)

    // ── После 5 кругов: полная остановка → пауза → авто-перезапуск ──
   if (!runningSplits.has(accountId)) break; // пользователь остановил вручную

    pushLog(accountId, `🔄 Завершено ${MAX_ROUNDS} кругов — полная остановка, затем перезапуск...`);
    if (resultEl) {
      resultEl.textContent = `Завершено ${MAX_ROUNDS} кругов. Останавливаю сессию...`;
      resultEl.className = "sqResult";
    }

    // Полностью останавливаем задачу на сервере
    try {
      await fetch(WORKER_API + "/api/tasks/stop", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ account_id: accountId }),
      });
    } catch (err) {
      console.warn("auto-restart stop error:", err);
    }

    await setAccountRunStatus(accountId, "idle", "", "");

    if (!runningSplits.has(accountId)) break;

    pushLog(accountId, `🔄 Перезапускаю...`);

    if (!runningSplits.has(accountId)) break;

    pushLog(accountId, `🔄 Авто-перезапуск с круга 1`);
    if (resultEl) {
      resultEl.textContent = `Перезапускаю с круга 1...`;
      resultEl.className = "sqResult";
    }
    await setAccountRunStatus(accountId, "running", "split", `Авто-перезапуск: круг 1`);

    // Внешний while продолжается — round сбросится в 1 автоматически

  } // конец внешнего цикла

  if (fastPollId) clearInterval(fastPollId);
  if (livePollId) clearInterval(livePollId);
  runningSplits.delete(accountId);
  await setAccountRunStatus(accountId, "idle", "", "");
  cardEl?.classList.remove("sqActive");
  await loadAccounts();
}

async function stopSplitDueToError(accountId, cardEl) {
  runningSplits.delete(accountId);
  await setAccountRunStatus(accountId, "idle", "", "");
  cardEl?.classList.remove("sqActive");
  loadAccounts();
}

likesModalClose?.addEventListener("click", () => likesModal.classList.remove("open"));
groqModalClose?.addEventListener("click",  () => groqModal.classList.remove("open"));

likesModal?.addEventListener("click", e => { if (e.target === likesModal) likesModal.classList.remove("open"); });
groqModal?.addEventListener("click",  e => { if (e.target === groqModal)  groqModal.classList.remove("open"); });

modalRunLikesBtn?.addEventListener("click", async () => {
  const accountId = activeModalAccountId;
  if (!accountId) return;
  const limit = Math.max(1, Math.min(100, Number(modalLikesLimit.value) || 10));

  modalRunLikesBtn.disabled    = true;
  modalRunLikesBtn.textContent = "Лайкаю...";
  setBoxResult(modalLikesResult, `Запускаю: ${limit} лайков...`);

  // подсвечиваем карточку
  activeModalCardEl?.classList.add("sqActive");
  if (activeModalResultEl) {
    activeModalResultEl.textContent = `Запускаю ${limit} лайков...`;
    activeModalResultEl.className   = "sqResult";
  }

  try {
    const res  = await fetchWithTimeout(WORKER_API + "/api/tasks/likes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_id: accountId, limit }),
    });
    const queued = await res.json();
    if (!res.ok || !queued.ok) throw new Error(queued.detail || queued.error || "Ошибка постановки в очередь");

    const job = await pollJob(queued.job_id, { timeoutMs: 120000 });
    const data = job.result || {};
    if (job.status === "error" || data.ok === false) {
      throw new Error(data.error || data.detail || data.summary || "Ошибка");
    }

    // результат в модалку
    setBoxResult(modalLikesResult, data.summary || "Готово.", "good");

    // результат в карточку
    if (activeModalResultEl) {
      activeModalResultEl.textContent = data.summary || "Готово.";
      activeModalResultEl.className   = "sqResult good";
    }

    loadAccounts();
    loadTasksLog();

  } catch (err) {
    setBoxResult(modalLikesResult, err.message || "Ошибка.", "bad");

    // ошибку тоже показываем в карточке
    if (activeModalResultEl) {
      activeModalResultEl.textContent = err.message || "Ошибка.";
      activeModalResultEl.className   = "sqResult bad";
    }

  } finally {
    modalRunLikesBtn.disabled    = false;
    modalRunLikesBtn.textContent = "▶ Дать лайки";
    activeModalCardEl?.classList.remove("sqActive");
  }
});;

modalRunGroqBtn?.addEventListener("click", async () => {
  const accountId = activeModalAccountId;
  if (!accountId) return;

  modalRunGroqBtn.disabled    = true;
  modalRunGroqBtn.textContent = "Обрабатываю...";
  setBoxResult(modalGroqResult, "Проверяю входящие и генерирую ответы...");

  try {
    const res  = await fetchWithTimeout("/api/tasks/auto-reply-http", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_id: accountId }),
    });
    const queued = await res.json();
    if (!res.ok || !queued.ok) throw new Error(queued.detail || queued.error || "Ошибка постановки в очередь");

    const job = await pollJob(queued.job_id, { timeoutMs: 120000 });
    const data = job.result || {};
    if (job.status === "error" || data.ok === false) {
      throw new Error(data.error || data.detail || data.summary || "Ошибка");
    }
    setBoxResult(modalGroqResult, data.summary || "Готово.", "good");
    loadAccounts();
    loadTasksLog();
  } catch (err) {
    setBoxResult(modalGroqResult, err.message || "Ошибка.", "bad");
  } finally {
    modalRunGroqBtn.disabled    = false;
    modalRunGroqBtn.textContent = "▶ Запустить автоответы";
  }
});

// ── ЧАТЫ ──────────────────────────────────────────────────

let currentChatsAccountId = null;
let currentChatHref       = null;

function showChatsView(viewName) {
  document.getElementById("chatsAccountsView").style.display    = viewName === "accounts"     ? "block" : "none";
  document.getElementById("chatsDialogsView").style.display     = viewName === "dialogs"       ? "block" : "none";
  document.getElementById("chatsConversationView").style.display = viewName === "conversation" ? "block" : "none";
}

async function loadChatsAccountsList() {
  const container = document.getElementById("chatsAccountsList");
  if (!container) return;
  try {
    const res = await fetch(WORKER_API + "/api/accounts");
    const data = await res.json();
    const accounts = data.accounts || [];

    if (!accounts.length) {
      container.innerHTML = '<div class="empty"><div><b>Анкет пока нет</b><span>Подключи анкету на главной.</span></div></div>';
      return;
    }

    container.innerHTML = accounts.map(acc => `
      <div class="sqCard" style="cursor:default;">
        <div class="sqPhoto" data-account-id="${acc.id}" style="cursor:pointer;">
          ${acc.photo_url ? `<img class="sqImg" src="${acc.photo_url}" alt="" />` : `<div class="sqFallback">AI</div>`}
        </div>
        <div class="sqBody">
          <div class="sqName" data-account-id="${acc.id}" style="cursor:pointer;">${acc.name || "Анкета"}</div>
          <input class="tgChatIdInput" data-account-id="${acc.id}" placeholder="TG chat_id для скринов" value="" style="margin-top:8px;font-size:11px;padding:6px 10px;" />
          <button class="sqBtn tgSaveBtn" data-account-id="${acc.id}" style="margin-top:6px;width:100%;">Сохранить chat_id</button>
        </div>
      </div>
    `).join("");

    container.querySelectorAll("[data-account-id].sqPhoto, [data-account-id].sqName").forEach(el => {
      el.addEventListener("click", () => {
        const accId = el.dataset.accountId;
        const accName = accounts.find(a => a.id === accId)?.name || "Анкета";
        openChatsDialogsView(accId, accName);
      });
    });

    // Подгружаем текущий tg_chat_id для каждой анкеты
    accounts.forEach(async acc => {
      try {
        const r = await fetch(WORKER_API + `/api/ai-settings/${encodeURIComponent(acc.id)}`);
        const d = await r.json();
        const input = container.querySelector(`.tgChatIdInput[data-account-id="${acc.id}"]`);
        if (input && d.settings) input.value = d.settings.tg_chat_id || "";
      } catch {}
    });

    container.querySelectorAll(".tgSaveBtn").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const accId = btn.dataset.accountId;
        const input = container.querySelector(`.tgChatIdInput[data-account-id="${accId}"]`);
        const chatId = input.value.trim();

        btn.disabled = true;
        btn.textContent = "Сохраняю...";
        try {
          const settingsRes = await fetch(WORKER_API + `/api/ai-settings/${encodeURIComponent(accId)}`);
          const settingsData = await settingsRes.json();
          const current = settingsData.settings || {};

          await fetch(WORKER_API + `/api/ai-settings/${encodeURIComponent(accId)}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ...current, tg_chat_id: chatId }),
          });
          btn.textContent = "Сохранено ✓";
        } catch (err) {
          btn.textContent = "Ошибка";
        } finally {
          setTimeout(() => { btn.disabled = false; btn.textContent = "Сохранить chat_id"; }, 1500);
        }
      });
    });
  } catch (err) {
    container.innerHTML = `<div class="result bad">Ошибка загрузки анкет: ${err.message}</div>`;
  }
}

async function openChatsDialogsView(accountId, accountName) {
  currentChatsAccountId = accountId;
  document.getElementById("chatsDialogsAccountName").textContent = accountName;
  showChatsView("dialogs");

  const container = document.getElementById("chatsDialogsList");
  container.innerHTML = '<div class="result">Загружаю диалоги...</div>';

  try {
    const res = await fetch(WORKER_API + `/api/chats/${encodeURIComponent(accountId)}`);
    const data = await res.json();
    const chats = data.chats || [];

    if (!chats.length) {
      container.innerHTML = '<div class="empty"><div><b>Диалогов пока нет</b><span>Запусти автоответы чтобы появились данные.</span></div></div>';
      return;
    }

    container.innerHTML = chats.map(chat => `
      <div class="result" data-href="${chat.href}" style="cursor:pointer;padding:12px 16px;">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px;opacity:.6;font-size:11px;">
          <span>${chat.contact_name || chat.href}</span>
          <span>${formatDate(chat.updated_at)}</span>
        </div>
        <div style="font-size:13px;">${chat.last_role === "user" ? "← " : "→ "}${(chat.last_message || "").slice(0, 80)}</div>
      </div>
    `).join("");

    container.querySelectorAll("[data-href]").forEach(el => {
      el.addEventListener("click", () => {
        const chat = chats.find(c => c.href === el.dataset.href);
        openChatsConversationView(el.dataset.href, chat?.contact_name);
      });
    });
  } catch (err) {
    container.innerHTML = `<div class="result bad">Ошибка загрузки диалогов: ${err.message}</div>`;
  }
}

async function openChatsConversationView(href, contactName) {
  currentChatHref = href;
  document.getElementById("chatsConversationTitle").textContent = contactName || href;
  showChatsView("conversation");

  const container = document.getElementById("chatsMessagesList");
  container.innerHTML = '<div class="result">Загружаю переписку...</div>';
  document.getElementById("chatsSendResult").textContent = "";

  try {
    const res = await fetch(WORKER_API + `/api/chats/${encodeURIComponent(currentChatsAccountId)}/history?href=${encodeURIComponent(href)}`);
    const data = await res.json();
    const history = data.history || [];

    if (!history.length) {
      container.innerHTML = '<div class="empty"><div><b>Сообщений нет</b></div></div>';
      return;
    }

    container.innerHTML = history.map(msg => `
      <div style="align-self:${msg.role === "user" ? "flex-start" : "flex-end"};max-width:75%;">
        <div class="result" style="background:${msg.role === "user" ? "rgba(255,255,255,.04)" : "rgba(92,110,248,.10)"};margin:0;">
          ${msg.content}
        </div>
      </div>
    `).join("");

    container.scrollTop = container.scrollHeight;
  } catch (err) {
    container.innerHTML = `<div class="result bad">Ошибка загрузки переписки: ${err.message}</div>`;
  }
}

document.getElementById("chatsBackToAccounts")?.addEventListener("click", () => showChatsView("accounts"));
document.getElementById("chatsBackToDialogs")?.addEventListener("click", () => {
  showChatsView("dialogs");
  openChatsDialogsView(currentChatsAccountId, document.getElementById("chatsDialogsAccountName").textContent);
});

document.getElementById("chatsSendBtn")?.addEventListener("click", async () => {
  const input = document.getElementById("chatsSendInput");
  const message = input.value.trim();
  const resultBox = document.getElementById("chatsSendResult");
  if (!message) return;

  const btn = document.getElementById("chatsSendBtn");
  btn.disabled = true;
  btn.textContent = "Отправляю...";
  setBoxResult(resultBox, "Открываю браузер и отправляю...");

  try {
    const res = await fetchWithTimeout(WORKER_API + "/api/chats/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_id: currentChatsAccountId, href: currentChatHref, message }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || "Ошибка отправки");
    input.value = "";
    setBoxResult(resultBox, "Отправлено.", "good");
    await openChatsConversationView(currentChatHref);
  } catch (err) {
    setBoxResult(resultBox, err.message || "Ошибка отправки.", "bad");
  } finally {
    btn.disabled = false;
    btn.textContent = "Отправить";
  }
});

async function loadTasksLog() {
  const container = document.getElementById("tasksLog");
  if (!container) return;
  try {
    const res  = await fetch(WORKER_API + "/api/tasks-log");
    const data = await res.json();
    const logs = data.logs || [];
    if (!logs.length) {
      container.innerHTML = '<div class="empty"><div><b>Задач пока нет</b><span>Запусти лайки или автоответы с карточки анкеты.</span></div></div>';
      return;
    }
    container.innerHTML = logs.map(log => `
      <div class="result" style="padding:12px 16px;border-radius:10px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);">
        <div style="display:flex;justify-content:space-between;margin-bottom:4px;opacity:.6;font-size:11px;">
          <span>${log.type || "—"} · ${log.account_id ? log.account_id.slice(0,8) + "…" : "—"}</span>
          <span>${formatDate(log.created_at)}</span>
        </div>
        <div style="font-size:13px;">${log.summary || JSON.stringify(log)}</div>
      </div>
    `).join("");
  } catch (err) {
    if (container) container.innerHTML = `<div class="result bad">Ошибка загрузки лога: ${err.message}</div>`;
  }
}

// ── Баннер ошибок Groq ─────────────────────────────────────

async function checkGroqError() {
  try {
    const res = await fetch(WORKER_API + "/api/groq-error");
    const data = await res.json();
    const banner = document.getElementById("groqErrorBanner");
    const text = document.getElementById("groqErrorText");
    if (data.error && data.error.message) {
      text.textContent = data.error.message;
      banner.style.display = "block";
    } else {
      banner.style.display = "none";
    }
  } catch {}
}

// ── Инициализация (запускается только после авторизации) ──

let appStarted = false;

async function loadNotifications() {
  try {
    const res = await fetch(WORKER_API + "/api/notifications");
    const data = await res.json();

    const notifications = data.notifications || [];

    const unread = notifications.filter(n => !n.is_read);

    if (notificationsCount) {
      notificationsCount.textContent = unread.length;

      notificationsCount.style.display =
        unread.length ? "block" : "none";
    }

    if (notificationsList) {

      notificationsList.innerHTML = notifications.length
        ? notifications.map(n => {

            const inviteId =
              n.data?.invite_id || "";

            const owner =
              n.data?.owner_email || "";

            return `
              <div class="result" style="margin-bottom:10px;">
                <b>${n.title}</b>

                <div style="margin-top:6px;">
                  ${n.message}
                </div>

                ${
                  n.type === "team_invite" && !n.is_read
                  ? `
                  <div style="margin-top:10px;display:flex;gap:8px;">
                    <button
                      class="taskRunBtn acceptInviteBtn"
                      data-id="${inviteId}"
                    >
                      Принять
                    </button>

                    <button
                      class="small danger rejectInviteBtn"
                      data-id="${inviteId}"
                    >
                      Отклонить
                    </button>
                  </div>
                  `
                  : ""
                }
              </div>
            `;
          }).join("")
        : `<div class="result">Уведомлений нет</div>`;

      bindInviteButtons();
    }

  } catch (err) {
    console.error(err);
  }
}

function bindInviteButtons() {

  document
    .querySelectorAll(".acceptInviteBtn")
    .forEach(btn => {

      btn.onclick = async () => {

        await fetch(
          "/api/team/invite/accept",
          {
            method: "POST",
            headers: {
              "Content-Type":"application/json"
            },
            body: JSON.stringify({
              invite_id: btn.dataset.id
            })
          }
        );

        await loadNotifications();
        await loadAccounts();
      };
    });

  document
    .querySelectorAll(".rejectInviteBtn")
    .forEach(btn => {

      btn.onclick = async () => {

        await fetch(
          "/api/team/invite/reject",
          {
            method: "POST",
            headers: {
              "Content-Type":"application/json"
            },
            body: JSON.stringify({
              invite_id: btn.dataset.id
            })
          }
        );

        await loadNotifications();
      };
    });
}

async function loadTeamMembers() {

  try {

    const res =
      await fetch(WORKER_API + "/api/team/members");

    const data =
      await res.json();

    const members =
      data.members || [];

    if (!teamMembersList) return;

    teamMembersList.innerHTML =
      members.length
      ? members.map(m => `
          <div class="result">
            ${m.member_email}
            (${m.role})
          </div>
        `).join("")
      : `<div class="result">Пока пусто</div>`;

  } catch (err) {
    console.error(err);
  }
}

function startApp() {
  if (appStarted) return;
  appStarted = true;

  // Мгновенно показываем то что было закэшировано с прошлой сессии
  loadCachedAccountsInstantly();

  loadOperatorTabs();
  initInfiniteCanvas();

  // Загружаем всё параллельно одним махом — никто никого не ждёт
  Promise.all([
    loadAnalyticsCards(),
    loadAccounts(),
    loadTasksLog(),
  ]).then(([, accounts]) => {
    renderAnalyticsGrid(accounts);
    renderAICardsOnCanvas();
    renderTimerCardsOnCanvas();

    // После отображения карточек проверяем анкеты через HTTP
    refreshAccountStatuses();
  });

  setInterval(async () => {
    await loadAnalyticsCards();
    const accounts = await loadAccounts();
    if (!document.querySelector('.analyticsCard._deleting')) {
      renderAnalyticsGrid(accounts);
    }
  }, 20000);

  const savedPage = (() => {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch {
      return null;
    }
  })();

  openPage(savedPage || "home");

  document.getElementById("groqErrorClose")?.addEventListener("click", async () => {
    try {
      await fetch(WORKER_API + "/api/groq-error/dismiss", { method: "POST" });
    } catch {}

    document.getElementById("groqErrorBanner").style.display = "none";
  });

  checkGroqError();

  loadNotifications();
  loadTeamMembers();

  setInterval(checkGroqError, 15000);
  setInterval(loadNotifications, 10000);
  setInterval(refreshAccountStatuses, 300000);
}

// ── ТАБЛИЦА (Google Sheets-style) ────────────────────────

function initSheetApp(container) {
  if (!container) return;

  const SK = "claw_sheets_v2";
  const COLS = 30, ROWS = 60;
  const DEF_COL_W = 130, DEF_ROW_H = 24;
  const HDR_W = 46, HDR_H = 24;

  function loadState() {
    try { return JSON.parse(localStorage.getItem(SK) || "null"); } catch { return null; }
  }
  function saveState() {
    try { localStorage.setItem(SK, JSON.stringify(state)); } catch {}
    // дебаунс: не шлём на сервер чаще раза в 800мс
    clearTimeout(saveState._t);
    saveState._t = setTimeout(() => _pushSheetToServer(), 800);
  }

  async function _pushSheetToServer() {
    for (const sheet of state.sheets) {
      const cells = [];
      for (const key of Object.keys(sheet.cells)) {
        const [r, c] = key.split(",").map(Number);
        const mapKey = sheet.id + ":" + key;
        const cellData = {
          row: r,
          col: c,
          value: sheet.cells[key],
        };
        const aid = assignedMap[mapKey];
        if (aid) cellData.assigned_account_id = aid;
        cells.push(cellData);
      }
      if (!cells.length) continue;
      try {
        await fetch("/api/sheet/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sheet_id: sheet.id, cells }),
        });
      } catch (e) {
        console.warn("[sheet] save error", e);
      }
    }
  }

  async function _loadSheetFromServer(sheetId) {
    try {
      const res = await fetch(`/api/sheet/load?sheet_id=${encodeURIComponent(sheetId)}`);
      const data = await res.json();
      if (!data.ok) return;
      const sheet = state.sheets.find(s => s.id === sheetId);
      if (!sheet) return;
      sheet.cells = {};
      for (const row of data.cells) {
        const key = row.row_idx + "," + row.col_idx;
        if (row.value !== undefined && row.value !== null) sheet.cells[key] = row.value;
        const mapKey = sheetId + ":" + key;
        if (row.assigned_account_id) {
          assignedMap[mapKey] = row.assigned_account_id;
        } else {
          delete assignedMap[mapKey];
        }
      }
    } catch (e) {
      console.warn("[sheet] load error", e);
    }
  }

  async function _loadBlockedAccounts() {
    try {
      const res = await fetch(WORKER_API + "/api/accounts");
      const data = await res.json();
      blockedSet = new Set(
        (data.accounts || [])
          .filter(a => a.is_blocked)
          .map(a => String(a.id))
      );
    } catch (e) {
      console.warn("[sheet] blocked load error", e);
    }
  }
  function uid() { return Math.random().toString(36).slice(2, 9); }
  function newSheet(name) {
    const fixedId = "sheet_" + name.replace(/\s+/g, "_").toLowerCase();
    return { id: fixedId, name, cells: {}, colW: {}, rowH: {} };
  }

  let state = loadState() || { sheets: [newSheet("Лист 1")], active: 0 };
  // Загружаем данные с сервера при старте
  setTimeout(async () => {
    for (const sheet of state.sheets) {
      await _loadSheetFromServer(sheet.id);
    }
    render();
  }, 500);
  // assigned_account_id по ключу "sheetId:r,c" → для окраски ячеек
  let assignedMap = {};
  // id заблокированных анкет
  let blockedSet = new Set();
  if (state.active >= state.sheets.length) state.active = 0;

  function sh() { return state.sheets[state.active]; }
  function ck(r, c) { return r + "," + c; }
  function colLetter(c) {
    let s = ""; c++;
    while (c > 0) { s = String.fromCharCode(64 + (c % 26 || 26)) + s; c = Math.floor((c - 1) / 26); }
    return s;
  }
  function cellName(r, c) { return colLetter(c) + (r + 1); }
  function cw(c) { return sh().colW[c] || DEF_COL_W; }
  function rh(r) { return sh().rowH[r] || DEF_ROW_H; }

  // selection state
  let sel = { r: 0, c: 0, r2: 0, c2: 0 };
  let editing = false;
  let dragColIdx = null, dragColX0 = 0, dragColW0 = 0;
  let dragRowIdx = null, dragRowY0 = 0, dragRowH0 = 0;

  // ── DOM ───────────────────────────────────────────────
  container.innerHTML = `
    <div style="display:flex;align-items:center;gap:6px;padding:5px 10px;background:#0a0d1a;border-bottom:1px solid rgba(100,120,255,0.15);flex-shrink:0;flex-wrap:wrap;">
      <span id="sh_cellname" style="font:500 12px 'JetBrains Mono',monospace;color:#818cf8;min-width:52px;text-align:center;background:rgba(255,255,255,0.04);border:1px solid rgba(100,120,255,0.18);border-radius:4px;padding:3px 6px;">A1</span>
      <div style="width:1px;height:18px;background:rgba(100,120,255,0.2);"></div>
      <input id="sh_formula" style="flex:1;min-width:180px;background:rgba(255,255,255,0.04);border:1px solid rgba(100,120,255,0.16);border-radius:4px;color:#e8ecff;font:400 12px 'JetBrains Mono',monospace;padding:3px 8px;outline:none;" placeholder="Значение..." />
      <div style="width:1px;height:18px;background:rgba(100,120,255,0.2);"></div>
      <button id="sh_addColBtn" style="${shBtn()}">+ Столбец</button>
      <button id="sh_addRowBtn" style="${shBtn()}">+ Строка</button>
      <button id="sh_clearBtn"  style="${shBtn()}">Очистить</button>
    </div>
    <div id="sh_gridScroll" style="flex:1;overflow:auto;position:relative;background:#050810;cursor:default;"></div>
    <div id="sh_sheetsBar" style="display:flex;align-items:center;background:#07091a;border-top:1px solid rgba(100,120,255,0.14);flex-shrink:0;min-height:32px;padding:0 6px;gap:2px;overflow-x:auto;"></div>
  `;

  function shBtn() {
    return "background:rgba(255,255,255,0.05);border:1px solid rgba(100,120,255,0.2);border-radius:4px;color:#a5b4fc;font:400 12px 'Space Grotesk',sans-serif;padding:3px 10px;cursor:pointer;";
  }

  const scroll    = container.querySelector("#sh_gridScroll");
  const formulaEl = container.querySelector("#sh_formula");
  const cellnameEl= container.querySelector("#sh_cellname");
  const sheetsBar = container.querySelector("#sh_sheetsBar");

  // ── Canvas ────────────────────────────────────────────
  let canvas, ctx;

  function totalW() {
    let w = HDR_W;
    for (let c = 0; c < COLS; c++) w += cw(c);
    return w;
  }
  function totalH() {
    let h = HDR_H;
    for (let r = 0; r < ROWS; r++) h += rh(r);
    return h;
  }
  function colX(c) {
    let x = HDR_W;
    for (let i = 0; i < c; i++) x += cw(i);
    return x;
  }
  function rowY(r) {
    let y = HDR_H;
    for (let i = 0; i < r; i++) y += rh(i);
    return y;
  }
  function colAtX(px) {
    let x = HDR_W;
    for (let c = 0; c < COLS; c++) {
      if (px < x + cw(c)) return { col: c, edge: px > x + cw(c) - 5 };
      x += cw(c);
    }
    return null;
  }
  function rowAtY(py) {
    let y = HDR_H;
    for (let r = 0; r < ROWS; r++) {
      if (py < y + rh(r)) return { row: r, edge: py > y + rh(r) - 5 };
      y += rh(r);
    }
    return null;
  }

  function buildCanvas() {
    scroll.innerHTML = "";
    canvas = document.createElement("canvas");
    canvas.style.cssText = "display:block;";
    canvas.setAttribute("tabindex", "-1");
    canvas.style.outline = "none";
    document.addEventListener("paste", (e) => {
      const tablesPage = document.getElementById('tablesPage');
      if (!tablesPage || !tablesPage.classList.contains('activePage')) return;
      e.preventDefault();
      const text = e.clipboardData.getData("text/plain");
      if (!text) return;
      const rows = text.split("\n");
      rows.forEach((row, ri) => {
        row.split("\t").forEach((cell, ci) => {
          const r = sel.r + ri, c = sel.c + ci;
          if (r < ROWS && c < COLS) {
            if (cell.trim()) sh().cells[ck(r, c)] = cell.trim();
            else delete sh().cells[ck(r, c)];
          }
        });
      });
      saveState(); render(); updateFormulaBar();
    });
    scroll.appendChild(canvas);
    canvas.addEventListener("mousedown", onMouseDown);
    canvas.addEventListener("click", () => { canvas.focus(); });
    canvas.addEventListener("mousemove", onMouseMove);
    canvas.addEventListener("mouseup",   onMouseUp);
    canvas.addEventListener("dblclick",  onDblClick);
    ctx = canvas.getContext("2d");
    render();
  }

  function render() {
    if (!canvas) return;
    const W = totalW(), H = totalH();
    canvas.width  = W;
    canvas.height = H;
    canvas.style.width  = W + "px";
    canvas.style.height = H + "px";

    ctx.clearRect(0, 0, W, H);

    const BG   = "#050810";
    const HDR  = "#0c0f20";
    const BORD = "rgba(100,120,255,0.12)";
    const SEL  = "rgba(92,110,248,0.18)";
    const SELHDR = "rgba(92,110,248,0.35)";
    const ACCENT = "#818cf8";
    const TEXT = "#c8cff5";
    const MUTED= "#4a5280";

    // background
    ctx.fillStyle = BG;
    ctx.fillRect(0, 0, W, H);

    // selection highlight
    const sx1 = Math.min(sel.c, sel.c2), sx2 = Math.max(sel.c, sel.c2);
    const sy1 = Math.min(sel.r, sel.r2), sy2 = Math.max(sel.r, sel.r2);
    ctx.fillStyle = SEL;
    ctx.fillRect(colX(sx1), rowY(sy1), colX(sx2) + cw(sx2) - colX(sx1), rowY(sy2) + rh(sy2) - rowY(sy1));

    // cells
    ctx.font = "12px 'Space Grotesk',sans-serif";
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const x = colX(c), y = rowY(r), w = cw(c), h = rh(r);
        // окраска по assigned_account_id
        const mapKey = sh().id + ":" + ck(r, c);
        const aid = assignedMap[mapKey];
        if (aid && !blockedSet.has(String(aid))) {
          ctx.fillStyle = "rgba(16,245,168,0.13)";
          ctx.fillRect(x, y, w, h);
        }
        // border
        ctx.strokeStyle = BORD;
        ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
        // text
        const val = sh().cells[ck(r, c)] || "";
        if (val) {
          if (val === "✗ ИСЧЕРПАН") {
            ctx.fillStyle = "rgba(244,63,94,0.18)";
            ctx.fillRect(x, y, w, h);
            ctx.fillStyle = "#f43f5e";
          } else if (val === "✓ OK") {
            ctx.fillStyle = "rgba(16,245,168,0.15)";
            ctx.fillRect(x, y, w, h);
            ctx.fillStyle = "#10f5a8";
          } else if (val === "? ОШИБКА") {
            ctx.fillStyle = "rgba(251,191,36,0.15)";
            ctx.fillRect(x, y, w, h);
            ctx.fillStyle = "#fbbf24";
          } else {
            ctx.fillStyle = TEXT;
          }
          ctx.save();
          ctx.beginPath();
          ctx.rect(x + 3, y + 1, w - 6, h - 2);
          ctx.clip();
          ctx.fillText(val, x + 4, y + h - 7);
          ctx.restore();
        }
      }
    }

    // active cell border
    ctx.strokeStyle = ACCENT;
    ctx.lineWidth = 2;
    ctx.strokeRect(colX(sel.c) + 1, rowY(sel.r) + 1, cw(sel.c) - 2, rh(sel.r) - 2);
    ctx.lineWidth = 1;

    // col headers
    ctx.fillStyle = HDR;
    ctx.fillRect(0, 0, W, HDR_H);
    ctx.strokeStyle = BORD;
    ctx.strokeRect(0.5, 0.5, W - 1, HDR_H - 1);
    ctx.font = "11px 'Space Grotesk',sans-serif";
    for (let c = 0; c < COLS; c++) {
      const x = colX(c), w = cw(c);
      const isSel = c >= sx1 && c <= sx2;
      ctx.fillStyle = isSel ? SELHDR : HDR;
      ctx.fillRect(x, 0, w, HDR_H);
      ctx.strokeStyle = BORD;
      ctx.strokeRect(x + 0.5, 0.5, w - 1, HDR_H - 1);
      ctx.fillStyle = isSel ? ACCENT : MUTED;
      ctx.textAlign = "center";
      ctx.fillText(colLetter(c), x + w / 2, HDR_H - 7);
    }

    // row headers
    ctx.fillStyle = HDR;
    ctx.fillRect(0, 0, HDR_W, H);
    ctx.font = "11px 'Space Grotesk',sans-serif";
    for (let r = 0; r < ROWS; r++) {
      const y = rowY(r), h = rh(r);
      const isSel = r >= sy1 && r <= sy2;
      ctx.fillStyle = isSel ? SELHDR : HDR;
      ctx.fillRect(0, y, HDR_W, h);
      ctx.strokeStyle = BORD;
      ctx.strokeRect(0.5, y + 0.5, HDR_W - 1, h - 1);
      ctx.fillStyle = isSel ? ACCENT : MUTED;
      ctx.textAlign = "center";
      ctx.fillText(r + 1, HDR_W / 2, y + h - 7);
    }

    // corner
    ctx.fillStyle = HDR;
    ctx.fillRect(0, 0, HDR_W, HDR_H);
    ctx.strokeStyle = BORD;
    ctx.strokeRect(0.5, 0.5, HDR_W - 1, HDR_H - 1);

    ctx.textAlign = "left";
  }

  // ── Mouse ─────────────────────────────────────────────
  function onMouseDown(e) {
    canvas.focus();
    if (editing) commitEdit();
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;

    // col resize?
    if (py < HDR_H) {
      let x = HDR_W;
      for (let c = 0; c < COLS; c++) {
        x += cw(c);
        if (Math.abs(px - x) < 5) {
          dragColIdx = c; dragColX0 = e.clientX; dragColW0 = cw(c);
          canvas.style.cursor = "col-resize";
          return;
        }
      }
    }
    // row resize?
    if (px < HDR_W) {
      let y = HDR_H;
      for (let r = 0; r < ROWS; r++) {
        y += rh(r);
        if (Math.abs(py - y) < 5) {
          dragRowIdx = r; dragRowY0 = e.clientY; dragRowH0 = rh(r);
          canvas.style.cursor = "row-resize";
          return;
        }
      }
    }

    const hit = hitCell(px, py);
    if (!hit) return;
    sel.r = sel.r2 = hit.r;
    sel.c = sel.c2 = hit.c;
    updateFormulaBar();
    render();
  }

  function onMouseMove(e) {
    const rect = canvas.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;

    if (dragColIdx !== null) {
      const delta = e.clientX - dragColX0;
      sh().colW[dragColIdx] = Math.max(30, dragColW0 + delta);
      saveState(); render(); return;
    }
    if (dragRowIdx !== null) {
      const delta = e.clientY - dragRowY0;
      sh().rowH[dragRowIdx] = Math.max(16, dragRowH0 + delta);
      saveState(); render(); return;
    }

    // cursor hint
    if (py < HDR_H) {
      let x = HDR_W;
      for (let c = 0; c < COLS; c++) {
        x += cw(c);
        if (Math.abs(px - x) < 5) { canvas.style.cursor = "col-resize"; return; }
      }
    }
    if (px < HDR_W) {
      let y = HDR_H;
      for (let r = 0; r < ROWS; r++) {
        y += rh(r);
        if (Math.abs(py - y) < 5) { canvas.style.cursor = "row-resize"; return; }
      }
    }
    canvas.style.cursor = "default";

    if (e.buttons === 1) {
      const hit = hitCell(px, py);
      if (hit) { sel.r2 = hit.r; sel.c2 = hit.c; render(); }
    }
  }

  function onMouseUp(e) {
    if (dragColIdx !== null || dragRowIdx !== null) {
      dragColIdx = null; dragRowIdx = null;
      canvas.style.cursor = "default";
      saveState(); render();
      return;
    }
    showSelectionPlugin(e);
  }

  function showSelectionPlugin(e) {
    document.getElementById("sh_plugin_panel")?.remove();

    const r1=Math.min(sel.r,sel.r2), r2=Math.max(sel.r,sel.r2);
    const c1=Math.min(sel.c,sel.c2), c2=Math.max(sel.c,sel.c2);

    // показываем плагин только при выделении больше одной ячейки
    if (r1 === r2 && c1 === c2) return;

    const panel = document.createElement("div");
    panel.id = "sh_plugin_panel";
    panel.style.cssText = `
      position:fixed;
      left:${e.clientX + 10}px;
      top:${e.clientY - 10}px;
      background:#0e1230;
      border:1px solid rgba(100,120,255,0.4);
      border-radius:8px;
      padding:6px;
      z-index:9999;
      display:flex;
      flex-direction:column;
      gap:4px;
      box-shadow:0 8px 32px rgba(0,0,0,0.5);
      min-width:180px;
    `;

    const assignBtn = document.createElement("button");
    assignBtn.textContent = "🔑 Присвоить анкете";
    assignBtn.style.cssText = `
      padding:8px 14px;
      border-radius:6px;
      border:1px solid rgba(92,110,248,0.3);
      background:rgba(92,110,248,0.1);
      color:#a5b4fc;
      font:600 11px 'Space Grotesk',sans-serif;
      cursor:pointer;
      text-align:left;
    `;
    assignBtn.onmouseenter = () => assignBtn.style.background = "rgba(92,110,248,0.25)";
    assignBtn.onmouseleave = () => assignBtn.style.background = "rgba(92,110,248,0.1)";
    assignBtn.onclick = () => {
      panel.remove();
      console.log("[assign] r1,r2,c1,c2 =", r1, r2, c1, c2);
      openAssignKeysModal(r1, r2, c1, c2);
    };
    panel.appendChild(assignBtn);

    const checkBtn = document.createElement("button");
    checkBtn.textContent = "🔍 Проверить статус ключей";
    checkBtn.style.cssText = `
      padding:8px 14px;
      border-radius:6px;
      border:1px solid rgba(16,245,168,0.3);
      background:rgba(16,245,168,0.07);
      color:#10f5a8;
      font:600 11px 'Space Grotesk',sans-serif;
      cursor:pointer;
      text-align:left;
    `;
    checkBtn.onmouseenter = () => checkBtn.style.background = "rgba(16,245,168,0.18)";
    checkBtn.onmouseleave = () => checkBtn.style.background = "rgba(16,245,168,0.07)";
    checkBtn.onclick = () => {
      panel.remove();
      checkKeysStatus(r1, r2, c1, c2);
    };
    panel.appendChild(checkBtn);

    const consoleBtn = document.createElement("button");
    consoleBtn.textContent = "📋 Консоль логов";
    consoleBtn.style.cssText = `
      padding:8px 14px;
      border-radius:6px;
      border:1px solid rgba(251,191,36,0.3);
      background:rgba(251,191,36,0.07);
      color:#fbbf24;
      font:600 11px 'Space Grotesk',sans-serif;
      cursor:pointer;
      text-align:left;
    `;
    consoleBtn.onmouseenter = () => consoleBtn.style.background = "rgba(251,191,36,0.18)";
    consoleBtn.onmouseleave = () => consoleBtn.style.background = "rgba(251,191,36,0.07)";
    consoleBtn.onclick = () => {
      panel.remove();
      openLogConsole(r1, r2, c1, c2);
    };
    panel.appendChild(consoleBtn);

    document.body.appendChild(panel);

    // закрыть при клике вне
    setTimeout(() => {
      document.addEventListener("mousedown", function handler(ev) {
        if (!panel.contains(ev.target)) {
          panel.remove();
          document.removeEventListener("mousedown", handler);
        }
      });
    }, 100);
  }

  function openLogConsole(r1, r2, c1, c2) {
  const existing = document.getElementById("sh_log_console");
  if (existing) existing.remove();

  const scroll = document.getElementById("sh_gridScroll");
  if (!scroll) return;

  const accounts = window._cachedAccounts || [];

  const overlay = document.createElement("div");
  overlay.id = "sh_log_console";
  overlay.style.cssText = `
    position:absolute;
    left:${colX(c1)}px;
    top:${rowY(r1)}px;
    width:${Math.max(380, colX(c2) + cw(c2) - colX(c1))}px;
    height:${Math.max(260, rowY(r2) + rh(r2) - rowY(r1))}px;
    background:rgba(5,8,16,0.97);
    border:1px solid rgba(251,191,36,0.4);
    border-radius:10px;
    z-index:500;
    display:flex;
    flex-direction:column;
    box-shadow:0 8px 32px rgba(0,0,0,0.7);
    overflow:hidden;
  `;

  // Шапка
  const header = document.createElement("div");
  header.style.cssText = `
    display:flex;align-items:center;gap:8px;
    padding:8px 12px;
    background:rgba(251,191,36,0.08);
    border-bottom:1px solid rgba(251,191,36,0.2);
    flex-shrink:0;
  `;

  const title = document.createElement("span");
  title.textContent = "📋 Консоль логов";
  title.style.cssText = "font:700 11px 'Orbitron',sans-serif;color:#fbbf24;letter-spacing:0.06em;flex:1;";
  header.appendChild(title);

  // Селект анкеты
  const select = document.createElement("select");
  select.style.cssText = `
    padding:4px 8px;border-radius:5px;
    border:1px solid rgba(251,191,36,0.3);
    background:rgba(5,8,16,0.9);color:#e8ecff;
    font:400 11px 'Space Grotesk',sans-serif;
    max-width:160px;
  `;
  const emptyOpt = document.createElement("option");
  emptyOpt.value = "";
  emptyOpt.textContent = "— выбери анкету —";
  select.appendChild(emptyOpt);
  accounts.forEach(a => {
    const o = document.createElement("option");
    o.value = a.id;
    o.textContent = (a.name || a.id).slice(0, 22);
    select.appendChild(o);
  });
  header.appendChild(select);

  // Кнопка закрыть
  const closeBtn = document.createElement("button");
  closeBtn.textContent = "✕";
  closeBtn.style.cssText = `
    background:transparent;border:none;color:#6872a8;
    font-size:16px;cursor:pointer;padding:0 4px;line-height:1;
  `;
  closeBtn.onmouseenter = () => closeBtn.style.color = "#fbbf24";
  closeBtn.onmouseleave = () => closeBtn.style.color = "#6872a8";
  closeBtn.onclick = () => {
    overlay.remove();
    try { localStorage.removeItem("claw_log_console_state"); } catch {}
  };
  header.appendChild(closeBtn);

  overlay.appendChild(header);

  // Лог-область
  const logArea = document.createElement("div");
  logArea.style.cssText = `
    flex:1;overflow-y:auto;
    padding:10px 12px;
    font:400 11px 'JetBrains Mono',monospace;
    color:#a5b4fc;
    line-height:1.7;
    white-space:pre-wrap;
    word-break:break-all;
  `;
  logArea.textContent = "Выбери анкету для просмотра лога...";
  overlay.appendChild(logArea);

  overlay.dataset.sheetId = sh().id;
  scroll.appendChild(overlay);

  // Polling логов каждые 500мс
  let lastLen = 0;
  let pollInterval = null;

  function startPolling(accountId) {
  if (pollInterval) clearInterval(pollInterval);
  lastLen = 0;
  logArea.innerHTML = "";

  let lastId = 0;

  function appendLine(line) {
    const span = document.createElement("span");
    span.textContent = line + "\n";
    if (line.includes("БЛОК")) span.style.color = "#f43f5e";
    else if (line.includes("Ошибка") || line.includes("ошибка")) span.style.color = "#fbbf24";
    else if (line.includes("поставлено") || line.includes("Ответов") || line.includes("запущен")) span.style.color = "#10f5a8";
    else span.style.color = "#a5b4fc";
    logArea.appendChild(span);
    logArea.scrollTop = logArea.scrollHeight;
  }

  // Сначала подгружаем историю из Supabase
  fetch(WORKER_API + `/api/split-log/${encodeURIComponent(accountId)}`)
    .then(r => r.json())
    .then(data => {
      if (data.logs && data.logs.length) {
        data.logs.forEach(row => appendLine(row.message));
        lastId = data.last_id || 0;
      } else {
        const noLog = document.createElement("span");
        noLog.textContent = "Логов пока нет.";
        noLog.style.color = "#4a5280";
        logArea.appendChild(noLog);
      }
    })
    .catch(() => {});

  // Потом раз в 3 сек подгружаем новые строки
  pollInterval = setInterval(async () => {
    if (!document.getElementById("sh_log_console")) {
      clearInterval(pollInterval);
      return;
    }

    // Новые строки из in-memory лога (мгновенно, без сервера)
    const logs = window._splitLogs[accountId];
    if (logs && logs.length > lastLen) {
      const newLines = logs.slice(lastLen);
      lastLen = logs.length;
      newLines.forEach(line => appendLine(line));
    }

    // Каждые 3 сек также тянем с сервера новые строки по lastId
    try {
      const res = await fetch(WORKER_API + `/api/split-log/${encodeURIComponent(accountId)}?after_id=${lastId}`);
      const data = await res.json();
      if (data.logs && data.logs.length) {
        data.logs.forEach(row => appendLine(row.message));
        lastId = data.last_id || lastId;
      }
    } catch {}

  }, 3000);
}

  select.addEventListener("change", () => {
    if (select.value) {
      startPolling(select.value);
      try {
        localStorage.setItem("claw_log_console_state", JSON.stringify({
          accountId: select.value, r1, r2, c1, c2, sheetId: sh().id
        }));
      } catch {}
    } else {
      logArea.textContent = "Выбери анкету для просмотра лога...";
      try { localStorage.removeItem("claw_log_console_state"); } catch {}
    }
  });

  // Если запущен только один сплит — выбираем его автоматически
  const runningSplitIds = [...runningSplits];
  if (runningSplitIds.length === 1) {
    select.value = runningSplitIds[0];
    startPolling(runningSplitIds[0]);
    try {
      localStorage.setItem("claw_log_console_state", JSON.stringify({
        accountId: runningSplitIds[0], r1, r2, c1, c2, sheetId: sh().id
      }));
    } catch {}
  }
}

  async function checkKeysStatus(r1, r2, c1, c2) {
    const sheet = sh();
    const keys = [];
    for (let r = r1; r <= r2; r++) {
      for (let c = c1; c <= c2; c++) {
        const v = sheet.cells[ck(r, c)];
        if (v && v.trim().startsWith("gsk_")) keys.push({ r, c, key: v.trim() });
      }
    }
    if (!keys.length) { alert("Нет Groq ключей в выделенных ячейках"); return; }

    // Показываем индикатор прогресса
    const progressId = "sh_check_progress";
    let prog = document.getElementById(progressId);
    if (prog) prog.remove();
    prog = document.createElement("div");
    prog.id = progressId;
    prog.style.cssText = `
      position:fixed;bottom:24px;right:24px;z-index:10001;
      background:#0e1230;border:1px solid rgba(16,245,168,0.4);
      border-radius:10px;padding:14px 18px;
      font:400 12px 'JetBrains Mono',monospace;color:#10f5a8;
      box-shadow:0 8px 32px rgba(0,0,0,0.5);
    `;
    prog.textContent = `Проверяю 0 / ${keys.length} ключей...`;
    document.body.appendChild(prog);

    let done = 0;
    // Проверяем батчами по 5
    const BATCH = 5;
    for (let i = 0; i < keys.length; i += BATCH) {
      const batch = keys.slice(i, i + BATCH);
      try {
        const res = await fetch("/api/sheet/check-keys", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ keys: batch.map(k => k.key) }),
        });
        const data = await res.json();
        for (const { r, c, key } of batch) {
          const status = data.results?.[key];
          const statusCol = c + 1;
          if (statusCol < COLS) {
            if (status === "ok") {
              sheet.cells[ck(r, statusCol)] = "✓ OK";
              // зелёный цвет через assignedMap не нужен — просто текст
            } else if (status === "exhausted") {
              sheet.cells[ck(r, statusCol)] = "✗ ИСЧЕРПАН";
            } else {
              sheet.cells[ck(r, statusCol)] = "? ОШИБКА";
            }
          }
        }
      } catch (e) {
        for (const { r, c } of batch) {
          if (c + 1 < COLS) sheet.cells[ck(r, c + 1)] = "? ОШИБКА";
        }
      }
      done += batch.length;
      prog.textContent = `Проверяю ${done} / ${keys.length} ключей...`;
      render();
      saveState();
    }

    prog.textContent = `✓ Проверено ${keys.length} ключей`;
    setTimeout(() => prog.remove(), 2500);
  }

  function openAssignKeysModal(r1, r2, c1, c2) {
    console.log("[modal] r1,r2,c1,c2 =", r1, r2, c1, c2, "cells:", JSON.stringify(sh().cells).slice(0,200));
    const keys = [];
    for (let r = r1; r <= r2; r++) {
      for (let c = c1; c <= c2; c++) {
        const v = sh().cells[ck(r, c)];
        if (v) keys.push(v.trim());
      }
    }
    if (!keys.length) { alert("Нет ключей в выделенных ячейках"); return; }

    const existing = document.getElementById("sh_assign_modal");
    if (existing) existing.remove();

    const modal = document.createElement("div");
    modal.id = "sh_assign_modal";
    modal.style.cssText = `
      position:fixed;inset:0;z-index:10000;
      background:rgba(5,8,16,0.8);
      display:flex;align-items:center;justify-content:center;
    `;

    modal.innerHTML = `
      <div style="background:#0e1230;border:1px solid rgba(100,120,255,0.4);border-radius:14px;padding:24px;min-width:320px;max-width:400px;">
        <div style="font:700 12px 'Orbitron',sans-serif;color:#a5b4fc;margin-bottom:16px;letter-spacing:0.06em;">ПРИСВОИТЬ КЛЮЧИ АНКЕТЕ</div>
        <div style="font:400 11px 'Space Grotesk',sans-serif;color:#6872a8;margin-bottom:12px;">Выбрано ключей: <b style="color:#a5b4fc">${keys.length}</b></div>
        <select id="sh_assign_select" style="width:100%;padding:9px 12px;border-radius:8px;border:1px solid rgba(100,120,255,0.2);background:rgba(5,8,16,0.8);color:#e8ecff;font:400 12px 'Space Grotesk',sans-serif;margin-bottom:16px;">
          <option value="">— выбери анкету —</option>
        </select>
        <div style="display:flex;gap:8px;">
          <button id="sh_assign_confirm" style="flex:1;padding:10px;border-radius:8px;border:1px solid rgba(92,110,248,0.4);background:rgba(92,110,248,0.15);color:#a5b4fc;font:700 10px 'Orbitron',sans-serif;cursor:pointer;letter-spacing:0.06em;">ПРИСВОИТЬ</button>
          <button id="sh_assign_cancel" style="padding:10px 16px;border-radius:8px;border:1px solid rgba(255,255,255,0.1);background:transparent;color:#6872a8;font:700 10px 'Orbitron',sans-serif;cursor:pointer;">ОТМЕНА</button>
        </div>
        <div id="sh_assign_result" style="margin-top:10px;font:400 11px 'JetBrains Mono',monospace;min-height:14px;"></div>
      </div>
    `;

    document.body.appendChild(modal);

    // заполняем список анкет
    const sel2 = modal.querySelector("#sh_assign_select");
    const accounts = window._cachedAccounts || [];
    accounts.forEach(a => {
      const o = document.createElement("option");
      o.value = a.id;
      o.textContent = a.name || a.id;
      sel2.appendChild(o);
    });

    modal.querySelector("#sh_assign_cancel").onclick = () => modal.remove();
    modal.querySelector("#sh_assign_confirm").onclick = async () => {
      const accountId = sel2.value;
      if (!accountId) { alert("Выбери анкету"); return; }
      const resultEl = modal.querySelector("#sh_assign_result");
      resultEl.textContent = "Сохраняю...";
      resultEl.style.color = "#a5b4fc";
      try {
        const res = await fetch(WORKER_API + `/api/ai-settings/${encodeURIComponent(accountId)}`);
        const data = await res.json();
        const current = data.settings || {};

        // Объединяем существующие ключи с новыми, без дублей (не перезатираем старые!)
        const existingKeys = (current.groq_api_keys || "")
          .split("\n")
          .map(k => k.trim())
          .filter(Boolean);
        const mergedKeys = Array.from(new Set([...existingKeys, ...keys]));

        await fetch(WORKER_API + `/api/ai-settings/${encodeURIComponent(accountId)}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...current, groq_api_keys: mergedKeys.join("\n") }),
        });

        // сохраняем assigned_account_id в sheet_cells
        const sheet = sh();
        const assignCells = [];
        for (let r = r1; r <= r2; r++) {
          for (let c = c1; c <= c2; c++) {
            const v = sheet.cells[ck(r, c)];
            if (!v) continue;
            const mapKey = sheet.id + ":" + ck(r, c);
            assignedMap[mapKey] = accountId;
            assignCells.push({
              row: r,
              col: c,
              value: v,
              assigned_account_id: accountId,
            });
          }
        }
        console.log("[assignedMap after]", JSON.stringify(assignedMap));
        console.log("[sheet.id]", sheet.id, "[sh().id]", sh().id);
        if (assignCells.length) {
          await fetch("/api/sheet/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sheet_id: sheet.id, cells: assignCells }),
          });
        }
        render(); // перерисовать зелёный
        resultEl.textContent = `✓ ${mergedKeys.length} ключей всего (добавлено новых: ${keys.length})`;
        resultEl.style.color = "#10f5a8";
        setTimeout(() => modal.remove(), 1200);
      } catch (err) {
        resultEl.textContent = "Ошибка: " + err.message;
        resultEl.style.color = "#f43f5e";
      }
    };
  }

  function onDblClick(e) {
    const rect = canvas.getBoundingClientRect();
    startEdit(e.clientX - rect.left, e.clientY - rect.top);
  }

  function hitCell(px, py) {
    if (px < HDR_W || py < HDR_H) return null;
    const ci = colAtX(px); const ri = rowAtY(py);
    if (!ci || !ri) return null;
    return { r: ri.row, c: ci.col };
  }

  // ── Inline edit ───────────────────────────────────────
  let editInput = null;

  function startEdit(px, py) {
    if (editing) return;
    const hit = hitCell(px, py);
    if (!hit) return;
    sel.r = sel.r2 = hit.r; sel.c = sel.c2 = hit.c;

    const x = colX(sel.c) + scroll.scrollLeft - scroll.scrollLeft;
    const y = rowY(sel.r) + scroll.scrollTop  - scroll.scrollTop;

    editing = true;
    editInput = document.createElement("input");
    editInput.value = sh().cells[ck(sel.r, sel.c)] || "";
    editInput.style.cssText = `
      position:absolute;
      left:${colX(sel.c)}px; top:${rowY(sel.r)}px;
      width:${cw(sel.c)}px; height:${rh(sel.r)}px;
      background:#0e1230; color:#e8ecff;
      border:2px solid #818cf8; outline:none;
      font:12px 'JetBrains Mono',monospace;
      padding:0 4px; box-sizing:border-box; z-index:10;
    `;
    scroll.appendChild(editInput);
    editInput.focus();
    editInput.select();

    editInput.addEventListener("keydown", e => {
      if (e.key === "Enter")  { commitEdit(); moveDown(); }
      if (e.key === "Tab")    { e.preventDefault(); commitEdit(); moveRight(); }
      if (e.key === "Escape") { cancelEdit(); }
    });
    editInput.addEventListener("blur", () => { if (editing) commitEdit(); });
  }

  function commitEdit() {
    if (!editInput) return;
    const val = editInput.value;
    if (val) sh().cells[ck(sel.r, sel.c)] = val;
    else delete sh().cells[ck(sel.r, sel.c)];
    const inp = editInput;
    editInput = null; editing = false;
    if (inp.parentNode) inp.remove();
    updateFormulaBar(); saveState(); render();
  }

  function cancelEdit() {
    if (editInput) { editInput.remove(); editInput = null; }
    editing = false;
  }

  function moveDown()  { if (sel.r < ROWS - 1) { sel.r++; sel.r2 = sel.r; sel.c2 = sel.c; updateFormulaBar(); render(); } }
  function moveRight() { if (sel.c < COLS - 1) { sel.c++; sel.c2 = sel.c; sel.r2 = sel.r; updateFormulaBar(); render(); } }

  // ── Formula bar ───────────────────────────────────────
  function updateFormulaBar() {
    cellnameEl.textContent = cellName(sel.r, sel.c);
    formulaEl.value = sh().cells[ck(sel.r, sel.c)] || "";
  }

  formulaEl.addEventListener("focus", () => {
    formulaEl._editing = true;
  });
  formulaEl.addEventListener("keydown", e => {
    if (e.key === "Enter") {
      const val = formulaEl.value;
      if (val) sh().cells[ck(sel.r, sel.c)] = val;
      else delete sh().cells[ck(sel.r, sel.c)];
      saveState(); render(); formulaEl.blur();
    }
    if (e.key === "Escape") { formulaEl.blur(); updateFormulaBar(); }
  });
  formulaEl.addEventListener("blur", () => { formulaEl._editing = false; });

  // ── Keyboard nav ──────────────────────────────────────
  container.setAttribute("tabindex", "0");
  container.addEventListener("keydown", e => {
    if (editing || formulaEl === document.activeElement) return;
    const mv = { ArrowUp: [-1,0], ArrowDown: [1,0], ArrowLeft: [0,-1], ArrowRight: [0,1] }[e.key];
    if (mv) {
      e.preventDefault();
      sel.r = Math.max(0, Math.min(ROWS-1, sel.r + mv[0]));
      sel.c = Math.max(0, Math.min(COLS-1, sel.c + mv[1]));
      sel.r2 = sel.r; sel.c2 = sel.c;
      updateFormulaBar(); render();
      scrollToCell();
      return;
    }
    if (e.key === "Delete" || e.key === "Backspace") {
      const r1=Math.min(sel.r,sel.r2), r2=Math.max(sel.r,sel.r2);
      const c1=Math.min(sel.c,sel.c2), c2=Math.max(sel.c,sel.c2);
      const deletedCells = [];
      for (let r=r1;r<=r2;r++) for(let c=c1;c<=c2;c++) {
        if (sh().cells[ck(r,c)]) deletedCells.push({ row: r, col: c, value: null });
        delete sh().cells[ck(r,c)];
      }
      saveState();
      if (deletedCells.length) {
        fetch("/api/sheet/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sheet_id: sh().id, cells: deletedCells }),
        }).catch(() => {});
      }
      render(); updateFormulaBar(); return;
    }
    if (e.key === "F2") { startEditByKey(); return; }
    // начать вводить символ
    if (e.key.length === 1 && !e.ctrlKey && !e.metaKey) {
      e.preventDefault();
      startEditByKeyChar(e.key);
    }
  });

  function startEditByKey() {
    const x = colX(sel.c), y = rowY(sel.r);
    editing = true;
    editInput = document.createElement("input");
    editInput.value = sh().cells[ck(sel.r, sel.c)] || "";
    editInput.style.cssText = `position:absolute;left:${x}px;top:${y}px;width:${cw(sel.c)}px;height:${rh(sel.r)}px;background:#0e1230;color:#e8ecff;border:2px solid #818cf8;outline:none;font:12px 'JetBrains Mono',monospace;padding:0 4px;box-sizing:border-box;z-index:10;`;
    scroll.appendChild(editInput);
    editInput.focus(); editInput.select();
    editInput.addEventListener("keydown", e => {
      if (e.key === "Enter")  { commitEdit(); moveDown(); }
      if (e.key === "Tab")    { e.preventDefault(); commitEdit(); moveRight(); }
      if (e.key === "Escape") { cancelEdit(); }
    });
    editInput.addEventListener("blur", () => { if (editing) commitEdit(); });
  }

  function startEditByKeyChar(char) {
    const x = colX(sel.c), y = rowY(sel.r);
    editing = true;
    editInput = document.createElement("input");
    editInput.value = char;
    editInput.style.cssText = `position:absolute;left:${x}px;top:${y}px;width:${cw(sel.c)}px;height:${rh(sel.r)}px;background:#0e1230;color:#e8ecff;border:2px solid #818cf8;outline:none;font:12px 'JetBrains Mono',monospace;padding:0 4px;box-sizing:border-box;z-index:10;`;
    scroll.appendChild(editInput);
    editInput.focus();
    editInput.setSelectionRange(editInput.value.length, editInput.value.length);
    editInput.addEventListener("keydown", e => {
      if (e.key === "Enter")  { commitEdit(); moveDown(); }
      if (e.key === "Tab")    { e.preventDefault(); commitEdit(); moveRight(); }
      if (e.key === "Escape") { cancelEdit(); }
    });
    editInput.addEventListener("blur", () => { if (editing) commitEdit(); });
  }

  function scrollToCell() {
    const x = colX(sel.c), y = rowY(sel.r);
    const w = cw(sel.c), h = rh(sel.r);
    if (x < scroll.scrollLeft) scroll.scrollLeft = x - HDR_W;
    if (x + w > scroll.scrollLeft + scroll.clientWidth) scroll.scrollLeft = x + w - scroll.clientWidth;
    if (y < scroll.scrollTop) scroll.scrollTop = y - HDR_H;
    if (y + h > scroll.scrollTop + scroll.clientHeight) scroll.scrollTop = y + h - scroll.clientHeight;
  }

  // ── Toolbar buttons ───────────────────────────────────
  container.querySelector("#sh_addColBtn").onclick = () => {
    sh().colW[COLS] = DEF_COL_W; // просто расширяем — уже есть 30 колонок
    saveState(); render();
  };
  container.querySelector("#sh_addRowBtn").onclick = () => {
    sh().rowH[ROWS] = DEF_ROW_H;
    saveState(); render();
  };
  container.querySelector("#sh_clearBtn").onclick = () => {
    const r1=Math.min(sel.r,sel.r2),r2=Math.max(sel.r,sel.r2);
    const c1=Math.min(sel.c,sel.c2),c2=Math.max(sel.c,sel.c2);
    for (let r=r1;r<=r2;r++) for(let c=c1;c<=c2;c++) {
      sh().cells[ck(r,c)] = "";
    }
    saveState();
    for (let r=r1;r<=r2;r++) for(let c=c1;c<=c2;c++) delete sh().cells[ck(r,c)];
    render(); updateFormulaBar();
  };

  // ── Sheets bar ────────────────────────────────────────
  function renderSheetsBar() {
    sheetsBar.innerHTML = "";
    state.sheets.forEach((s, i) => {
      const tab = document.createElement("div");
      tab.style.cssText = `
        display:flex;align-items:center;gap:4px;
        padding:4px 12px 4px 10px;
        border-radius:6px 6px 0 0;
        border:1px solid ${i === state.active ? "rgba(100,120,255,0.4)" : "transparent"};
        border-bottom:none;
        background:${i === state.active ? "rgba(92,110,248,0.12)" : "rgba(255,255,255,0.03)"};
        color:${i === state.active ? "#a5b4fc" : "#4a5280"};
        font:500 12px 'Space Grotesk',sans-serif;
        cursor:pointer;white-space:nowrap;user-select:none;
        transition:background 0.15s;
      `;

      // Label — double click to rename
      const label = document.createElement("span");
      label.textContent = s.name;
      let clickTimer = null;
      label.addEventListener("click", (e) => {
        e.stopPropagation();
        if (clickTimer) {
          clearTimeout(clickTimer);
          clickTimer = null;
          renameSheet(i, tab, label);
        } else {
          clickTimer = setTimeout(async () => {
            clickTimer = null;
            state.active = i;
            const existingConsole = document.getElementById("sh_log_console");
            if (existingConsole) {
              if (existingConsole.dataset.sheetId !== sh().id) {
                existingConsole.style.display = "none";
              } else {
                existingConsole.style.display = "flex";
              }
            }
            saveState();
            await _loadSheetFromServer(sh().id);
            renderSheetsBar(); render(); updateFormulaBar();
          }, 250);
        }
      });
      tab.appendChild(label);

      // Delete x (not on last sheet)
      if (state.sheets.length > 1) {
        const x = document.createElement("span");
        x.textContent = "×";
        x.style.cssText = "margin-left:2px;opacity:0.5;font-size:13px;line-height:1;";
        x.onmouseenter = () => x.style.opacity = "1";
        x.onmouseleave = () => x.style.opacity = "0.5";
        x.onclick = (e) => { e.stopPropagation(); deleteSheet(i); };
        tab.appendChild(x);
      }

      sheetsBar.appendChild(tab);
    });

    // + button
    const addBtn = document.createElement("div");
    addBtn.textContent = "+";
    addBtn.style.cssText = "padding:4px 12px;color:#4a5280;font-size:16px;cursor:pointer;line-height:24px;border-radius:4px;";
    addBtn.onmouseenter = () => addBtn.style.color = "#a5b4fc";
    addBtn.onmouseleave = () => addBtn.style.color = "#4a5280";
    addBtn.onclick = () => {
      const name = "Лист " + (state.sheets.length + 1);
      state.sheets.push(newSheet(name));
      state.active = state.sheets.length - 1;
      saveState(); renderSheetsBar(); render(); updateFormulaBar();
    };
    sheetsBar.appendChild(addBtn);
  }

  function renameSheet(i, tabEl, labelEl) {
    const inp = document.createElement("input");
    inp.value = state.sheets[i].name;
    inp.style.cssText = "width:80px;font:500 12px 'Space Grotesk',sans-serif;background:#0a0d1a;color:#e8ecff;border:1px solid #818cf8;border-radius:3px;padding:1px 4px;outline:none;";
    labelEl.replaceWith(inp);
    inp.focus(); inp.select();
    inp.addEventListener("keydown", (e) => { e.stopPropagation(); });
    inp.addEventListener("click", (e) => { e.stopPropagation(); });
    function done() {
      const v = inp.value.trim() || state.sheets[i].name;
      state.sheets[i].name = v;
      saveState(); renderSheetsBar();
    }
    inp.onblur = done;
    inp.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); done(); } if (e.key === "Escape") { renderSheetsBar(); } };
  }

  function deleteSheet(i) {
    if (!confirm(`Удалить лист «${state.sheets[i].name}»?`)) return;
    state.sheets.splice(i, 1);
    if (state.active >= state.sheets.length) state.active = state.sheets.length - 1;
    saveState(); renderSheetsBar();
  }

  // ── Инициализация ─────────────────────────────────────
  buildCanvas();
  renderSheetsBar();
  updateFormulaBar();
  // загружаем данные с сервера асинхронно
  (async () => {
    await _loadBlockedAccounts();
    for (const s of state.sheets) {
      await _loadSheetFromServer(s.id);
    }
    render();
  })();
  scroll.addEventListener("mousedown", () => { canvas.focus(); });

  // Восстанавливаем консоль логов после перезагрузки страницы
  setTimeout(() => {
    try {
      const saved = localStorage.getItem("claw_log_console_state");
      if (!saved) return;
      const { accountId, r1, r2, c1, c2, sheetId } = JSON.parse(saved);
      if (!accountId) return;
      if (sheetId && sheetId !== sh().id) return;
      openLogConsole(r1 ?? 0, r2 ?? 5, c1 ?? 4, c2 ?? 6);
      setTimeout(() => {
        const sel = document.getElementById("sh_log_console")?.querySelector("select");
        if (sel) {
          sel.value = accountId;
          sel.dispatchEvent(new Event("change"));
        }
      }, 300);
    } catch {}
  }, 800);

// Copy / paste
  let _copyBuffer = [];

  canvas.addEventListener("keydown", e => {
    // используем e.code вместо e.key — не зависит от раскладки клавиатуры (RU/EN)
    if ((e.ctrlKey || e.metaKey) && e.code === "KeyC") {
      e.preventDefault();
      _copyBuffer = [];
      const r1=Math.min(sel.r,sel.r2), r2=Math.max(sel.r,sel.r2);
      const c1=Math.min(sel.c,sel.c2), c2=Math.max(sel.c,sel.c2);
      for (let r=r1; r<=r2; r++) {
        const row = [];
        for (let c=c1; c<=c2; c++) row.push(sh().cells[ck(r,c)] || "");
        _copyBuffer.push(row);
      }
      // также пишем в системный буфер
      const text = _copyBuffer.map(r => r.join("\t")).join("\n");
      try { navigator.clipboard.writeText(text); } catch {}
    }

    if ((e.ctrlKey || e.metaKey) && e.code === "KeyV") {
      e.preventDefault();
      if (_copyBuffer.length) {
        _copyBuffer.forEach((row, ri) => {
          row.forEach((cell, ci) => {
            const r = sel.r + ri, c = sel.c + ci;
            if (r < ROWS && c < COLS) {
              if (cell) sh().cells[ck(r, c)] = cell;
              else delete sh().cells[ck(r, c)];
            }
          });
        });
        saveState(); render(); updateFormulaBar();
      } else {
        navigator.clipboard.readText().then(text => {
          const rows = text.split("\n");
          rows.forEach((row, ri) => {
            row.split("\t").forEach((cell, ci) => {
              const r = sel.r + ri, c = sel.c + ci;
              if (r < ROWS && c < COLS) {
                if (cell) sh().cells[ck(r, c)] = cell;
                else delete sh().cells[ck(r, c)];
              }
            });
          });
          saveState(); render(); updateFormulaBar();
        }).catch(()=>{});
      }
    }
  });
              

// ── Модалка скрещивания ───────────────────────────────────

let chainModalAccountId = null;
let chainModalAccountName = "";

function openChainModal(accountId, accountName) {
  chainModalAccountId = accountId;
  chainModalAccountName = accountName;

  const modal = document.getElementById("chainModal");
  const title = document.getElementById("chainModalTitle");
  if (title) title.textContent = `Цепочка резервов: ${accountName}`;

  renderChainModal();
  modal?.classList.add("open");
}

async function renderChainModal() {
  const listEl = document.getElementById("chainModalList");
  if (!listEl) return;

  listEl.innerHTML = '<div class="result">Загружаю...</div>';

  try {
    const [chainRes, accRes] = await Promise.all([
      fetch(WORKER_API + `/api/accounts/${encodeURIComponent(chainModalAccountId)}/chain`),
      fetch(WORKER_API + "/api/accounts"),
    ]);
    const chainData = await chainRes.json();
    const accData   = await accRes.json();

    const chain    = chainData.chain || [];
    const accounts = (accData.accounts || []).filter(a => a.id !== chainModalAccountId);

    listEl.innerHTML = "";

    if (!chain.length) {
      listEl.innerHTML = '<div class="result" style="opacity:.5;">Резервов пока нет</div>';
    } else {
      chain.forEach((resId, idx) => {
        const acc = accounts.find(a => a.id === resId);
        const name = acc ? (acc.name || resId) : `(удалена) ${resId.slice(0,8)}`;

        const row = document.createElement("div");
        row.className = "result";
        row.style.cssText = "display:flex;align-items:center;justify-content:space-between;padding:10px 14px;margin-bottom:6px;";
        row.innerHTML = `
          <span style="font-size:13px;">${idx + 1}. ${name}</span>
          <button class="sqBtn" data-remove-idx="${idx}" style="padding:4px 10px;font-size:11px;background:rgba(255,60,60,.15);border-color:rgba(255,60,60,.3);color:#ff6b6b;">✕</button>
        `;
        row.querySelector("[data-remove-idx]").onclick = async () => {
          const newChain = [...chain];
          newChain.splice(idx, 1);
          await saveChain(newChain);
          renderChainModal();
        };
        listEl.appendChild(row);
      });
    }

    // Селект для добавления новой резервной анкеты
    const alreadyInChain = new Set([chainModalAccountId, ...chain]);
    const available = accounts.filter(a => !alreadyInChain.has(a.id));

    const addRow = document.createElement("div");
    addRow.style.cssText = "display:flex;gap:8px;margin-top:12px;";
    addRow.innerHTML = `
      <select id="chainAddSelect" style="flex:1;padding:8px 10px;border-radius:var(--r);border:1px solid rgba(255,255,255,.12);background:rgba(5,8,16,.8);color:var(--text);font-size:13px;">
        <option value="">— добавить резерв —</option>
        ${available.map(a => `<option value="${a.id}">${a.name || a.id}</option>`).join("")}
      </select>
      <button id="chainAddBtn" class="sqBtn" style="padding:8px 14px;">+ Добавить</button>
    `;
    listEl.appendChild(addRow);

    document.getElementById("chainAddBtn").onclick = async () => {
      const sel = document.getElementById("chainAddSelect");
      const newId = sel.value;
      if (!newId) return;
      const newChain = [...chain, newId];
      await saveChain(newChain);
      renderChainModal();
    };

  } catch (err) {
    listEl.innerHTML = `<div class="result bad">Ошибка: ${err.message}</div>`;
  }
}

async function saveChain(chain) {
  const res = await fetch(WORKER_API + `/api/accounts/${encodeURIComponent(chainModalAccountId)}/chain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account_id: chainModalAccountId, chain }),
  });

  const data = await res.json().catch(() => ({}));

  if (!res.ok || !data.ok) {
    throw new Error(data.detail || data.error || "Цепочка резервов не сохранилась");
  }

  return data.chain || chain;
}

document.getElementById("chainModalClose")?.addEventListener("click", () => {
  document.getElementById("chainModal")?.classList.remove("open");
});

document.getElementById("chainModal")?.addEventListener("click", (e) => {
  if (e.target === document.getElementById("chainModal")) {
    document.getElementById("chainModal")?.classList.remove("open");
  }
});
}

checkAuthAndStart();

// ── Отчёт ─────────────────────────────────────────────────

var reportCurrentMonth = "";
var reportTgAccounts = [];
var reportSummaryRows = [];
var reportShowAll = false;

function reportGetMonthTabs() {
  const months = [];
  const now = new Date();
  for (let i = 0; i < 6; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const label = d.toLocaleString("ru", { month: "long", year: "numeric" });
    months.push({ key, label });
  }
  return months;
}


function reportGetToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;
}

function reportRenderMonthTabs() {
  const container = document.getElementById("reportMonthTabs");
  if (!container) return;
  const months = reportGetMonthTabs();
  if (!reportCurrentMonth) reportCurrentMonth = months[0].key;
  container.innerHTML = months.map(m => `
    <button class="rMonthTab ${m.key === reportCurrentMonth ? "active" : ""}" data-month="${m.key}">
      ${m.label.charAt(0).toUpperCase() + m.label.slice(1)}
    </button>
  `).join("");
  container.querySelectorAll(".rMonthTab").forEach(btn => {
    btn.addEventListener("click", () => {
      reportCurrentMonth = btn.dataset.month;
      reportShowAll = false;
      reportRenderMonthTabs();
      reportLoad();
    });
  });
}
async function reportLoad() {
  const tbody = document.getElementById("reportTableBody");
  const tfoot = document.getElementById("reportTableFoot");
  if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:32px;color:var(--text2);">Загрузка...</td></tr>`;

  try {
    const res = await fetch(`/api/report/summary?month=${reportCurrentMonth}`);
    const data = await res.json();
    console.log("REPORT DATA:", data);
    reportSummaryRows = data.rows || [];
    console.log("ROWS:", reportSummaryRows.length);
    reportRenderTable();
  } catch (err) {
    console.error("REPORT ERROR:", err);
    if (tbody) tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:32px;color:var(--red);">Ошибка загрузки</td></tr>`;
  }
}

function reportRenderTable() {
  const tbody = document.getElementById("reportTableBody");
  const tfoot = document.getElementById("reportTableFoot");
  if (!tbody) return;

  if (!reportSummaryRows.length) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:32px;color:var(--text2);">Нет данных. Добавьте TG-аккаунт.</td></tr>`;
    if (tfoot) tfoot.innerHTML = "";
    return;
  }

  const today = reportGetToday();
  const rows = reportShowAll ? reportSummaryRows : reportSummaryRows.filter(r => r.date === today);
  
  let totalLeads = 0, totalVisits = 0, totalBookings = 0, totalCancels = 0;

  tbody.innerHTML = rows.map((row) => {
    const realIdx = reportSummaryRows.indexOf(row);
    totalLeads    += row.leads || 0;
    totalVisits   += row.visits || 0;
    totalCancels += row.cancels || 0;
    const conv = row.bookings > 0 ? "50%" : row.visits > 0 ? "100%" : "—";
    const dateLabel = row.date.slice(8, 10) + "." + row.date.slice(5, 7);
    return `
      <tr data-idx="${realIdx}">
        <td class="rTd">${dateLabel}</td>
        <td class="rTd" style="color:var(--cyan);">@${row.tg_account}${row.label ? " · " + row.label : ""}</td>
        <td class="rTd editable" data-field="leads" data-idx="${realIdx}">${row.leads || 0}</td>
        <td class="rTd editable" data-field="visits" data-idx="${realIdx}" style="color:var(--green);">${row.visits || 0}</td>
        <td class="rTd editable" data-field="bookings" data-idx="${realIdx}" style="color:#60a5fa;">${row.bookings || 0}</td>
        <td class="rTd editable" data-field="cancels" data-idx="${realIdx}" style="color:var(--red);">${row.cancels || 0}</td>
        <td class="rTd" style="color:var(--green);">${conv}</td>
        <td class="rTd"><button class="rDeleteBtn" data-username="${row.tg_account}" style="background:none;border:none;color:var(--text2);cursor:pointer;font-size:13px;opacity:0.5;" title="Удалить аккаунт">✕</button></td>
      </tr>
    `;
  }).join("");

  const totalConv = totalBookings > 0 ? "50%" : totalVisits > 0 ? "100%" : "—";
  if (tfoot) {
    tfoot.innerHTML = `
      <tr>
        <td class="rFootTd" colspan="2">Итого</td>
        <td class="rFootTd">${totalLeads}</td>
        <td class="rFootTd" style="color:var(--green);">${totalVisits}</td>
        <td class="rFootTd" style="color:#60a5fa;">${totalBookings}</td>
        <td class="rFootTd" style="color:var(--red);">${totalCancels}</td>
        <td class="rFootTd">${totalConv}</td>
      </tr>
    `;
  }

  // Inline редактирование
  tbody.querySelectorAll(".rTd.editable").forEach(cell => {
    cell.addEventListener("click", () => {
      if (cell.querySelector("input")) return;
      const idx = +cell.dataset.idx;
      const field = cell.dataset.field;
      const current = reportSummaryRows[idx][field] || 0;
      cell.innerHTML = `<input class="rInlineInput" type="number" min="0" value="${current}" />`;
      const input = cell.querySelector("input");
      input.focus();
      input.select();
      const save = async () => {
        const val = parseInt(input.value) || 0;
        reportSummaryRows[idx][field] = val;
        cell.textContent = val;
        const row = reportSummaryRows[idx];
        try {
          await fetch("/api/report/entries", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              tg_account: row.tg_account,
              date: row.date,
              visits: reportSummaryRows[idx].visits || 0,
              bookings: reportSummaryRows[idx].bookings || 0,
              cancels: reportSummaryRows[idx].cancels || 0,
            }),
          });
        } catch {}
        reportRenderTable();
      };
      input.addEventListener("blur", save);
      input.addEventListener("keydown", e => {
        if (e.key === "Enter") input.blur();
        if (e.key === "Escape") { cell.textContent = current; }
      });
    });
  });

  // Удаление TG-аккаунта
  tbody.querySelectorAll(".rDeleteBtn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const username = btn.dataset.username;
      const confirmed = await new Promise(resolve => {
        const backdrop = document.createElement("div");
        backdrop.className = "modalBackdrop open";
        backdrop.innerHTML = `
          <div class="modal" style="max-width:320px;">
            <div class="modalHead">
              <span>Удалить аккаунт</span>
            </div>
            <div class="modalBody">
              <p style="font:400 13px/1.6 'Space Grotesk',sans-serif;color:var(--text2);">
                Удалить <span style="color:var(--cyan);font-weight:600;">@${username}</span> из отчёта? Все данные по нему останутся в базе.
              </p>
              <div style="display:flex;gap:8px;margin-top:18px;">
                <button class="ghost" id="rDelCancel" style="flex:1;">Отмена</button>
                <button class="small danger" id="rDelConfirm" style="flex:1;padding:10px;">Удалить</button>
              </div>
            </div>
          </div>
        `;
        document.body.appendChild(backdrop);
        backdrop.querySelector("#rDelCancel").onclick = () => { backdrop.remove(); resolve(false); };
        backdrop.querySelector("#rDelConfirm").onclick = () => { backdrop.remove(); resolve(true); };
        backdrop.onclick = (e) => { if (e.target === backdrop) { backdrop.remove(); resolve(false); } };
      });
      if (!confirmed) return;
      try {
        const accRes = await fetch("/api/report/tg-accounts");
        const accData = await accRes.json();
        const acc = (accData.accounts || []).find(a => a.tg_username === username);
        if (!acc) return;
        await fetch(`/api/report/tg-accounts/${acc.id}`, { method: "DELETE" });
        reportLoad();
      } catch {}
    });
  });
}

async function reportLoadTgAccounts() {
  try {
    const res = await fetch("/api/report/tg-accounts");
    const data = await res.json();
    reportTgAccounts = data.accounts || [];
  } catch {}
}


function initReportPage() {
  if (window._reportInited) {
    reportRenderMonthTabs();
    reportLoad();
    return;
  }
  window._reportInited = true;

  reportRenderMonthTabs();
  reportLoad();

  // Кнопка обновить
  document.getElementById("reportRefreshBtn")?.addEventListener("click", reportLoad);
  document.getElementById("reportToggleBtn")?.addEventListener("click", () => {
    reportShowAll = !reportShowAll;
    reportRenderTable();
  });

  // Модалка добавления аккаунта
  const modal = document.getElementById("reportAddAccountModal");
  document.getElementById("reportAddAccountBtn")?.addEventListener("click", () => {
    document.getElementById("reportAddUsername").value = "";
    document.getElementById("reportAddLabel").value = "";
    document.getElementById("reportAddAccountResult").textContent = "";
    modal?.classList.add("open");
  });
  document.getElementById("reportAddAccountModalClose")?.addEventListener("click", () => modal?.classList.remove("open"));
  modal?.addEventListener("click", e => { if (e.target === modal) modal.classList.remove("open"); });

  document.getElementById("reportAddAccountSaveBtn")?.addEventListener("click", async () => {
    const username = document.getElementById("reportAddUsername").value.trim();
    const label = document.getElementById("reportAddLabel").value.trim();
    const resultEl = document.getElementById("reportAddAccountResult");
    if (!username) { resultEl.textContent = "Введите @username"; resultEl.className = "result bad"; return; }
    try {
      const res = await fetch("/api/report/tg-accounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tg_username: username, label }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Ошибка");
      resultEl.textContent = "Добавлено!";
      resultEl.className = "result good";
      modal?.classList.remove("open");
      await reportLoadTgAccounts();
      reportLoad();
    } catch (err) {
      resultEl.textContent = err.message;
      resultEl.className = "result bad";
    }
  });
}

notificationsBell?.addEventListener(
  "click",
  () => {
    notificationsModal?.classList.add("open");
  }
);

notificationsModalClose?.addEventListener(
  "click",
  () => {
    notificationsModal?.classList.remove("open");
  }
);

teamInviteBtn?.addEventListener(
  "click",
  async () => {

    try {

      const res =
        await fetch(
          "/api/team/invite",
          {
            method:"POST",
            headers:{
              "Content-Type":"application/json"
            },
            body: JSON.stringify({
              email: teamInviteEmail.value,
              role: teamInviteRole.value
            })
          }
        );

      const data =
        await res.json();

      if (!res.ok)
        throw new Error(
          typeof data.detail === "string" 
            ? data.detail 
            : JSON.stringify(data.detail) || data.message || "Ошибка отправки"
        );

      teamInviteResult.textContent =
        "Приглашение отправлено";

      teamInviteResult.className =
        "result good";

      teamInviteEmail.value = "";

    } catch(err){
      teamInviteResult.textContent =
        err.message || err.detail || "Ошибка отправки приглашения";
      teamInviteResult.className =
        "result bad";
    }
  }
);

// ══════════════════════════════════════════════════════════
// ПРОКСИ НАСТРОЙКИ
// ══════════════════════════════════════════════════════════

const PROXY_PLATFORMS = [
  { id: "mamba",       label: "Mamba / Love Mail" },
  { id: "lovelaz",     label: "Lovelaz" },
  { id: "twinby",      label: "Twinby" },
  { id: "vznakomstve", label: "Vznakomstve" },
];

async function loadProxySettings() {
  const list = document.getElementById("proxyList");
  if (!list) return;

  list.innerHTML = "<div style='color:var(--text-muted);font-size:13px;'>Загрузка...</div>";

  let rows = {};
  try {
    const res = await fetch("/api/proxy-settings");
    const data = await res.json();
    if (Array.isArray(data)) {
      data.forEach(r => { rows[r.id] = r; });
    }
  } catch (e) {
    list.innerHTML = "<div style='color:#fb7185;font-size:13px;'>Ошибка загрузки прокси</div>";
    return;
  }

  list.innerHTML = "";

  PROXY_PLATFORMS.forEach(platform => {
    const row = rows[platform.id] || {};

    const card = document.createElement("div");
    card.style.cssText = `
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 16px 18px;
    `;

    card.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
        <div style="font:700 13px 'Orbitron',sans-serif;color:var(--accent3);letter-spacing:0.06em;">${platform.label}</div>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;margin:0;">
          <span style="font-size:12px;color:var(--text-muted);">Активна</span>
          <input type="checkbox" class="proxyActive" data-id="${platform.id}" ${row.use_proxy !== false ? "checked" : ""} style="width:16px;height:16px;cursor:pointer;" />
        </label>
      </div>
      <div style="display:grid;grid-template-columns:1fr 120px;gap:10px;margin-bottom:10px;">
        <div>
          <label style="font-size:11px;color:var(--text-muted);margin-bottom:4px;display:block;">HOST</label>
          <input class="proxyHost" data-id="${platform.id}" value="${row.host || ""}" placeholder="170.168.253.248" style="font-family:'JetBrains Mono',monospace;font-size:12px;" />
        </div>
        <div>
          <label style="font-size:11px;color:var(--text-muted);margin-bottom:4px;display:block;">PORT</label>
          <input class="proxyPort" data-id="${platform.id}" value="${row.port || ""}" placeholder="62508" style="font-family:'JetBrains Mono',monospace;font-size:12px;" />
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
          <label style="font-size:11px;color:var(--text-muted);margin-bottom:4px;display:block;">LOGIN</label>
          <input class="proxyUser" data-id="${platform.id}" value="${row.username || ""}" placeholder="username" style="font-family:'JetBrains Mono',monospace;font-size:12px;" />
        </div>
        <div>
          <label style="font-size:11px;color:var(--text-muted);margin-bottom:4px;display:block;">PASSWORD</label>
          <input class="proxyPass" data-id="${platform.id}" value="${row.password || ""}" placeholder="password" style="font-family:'JetBrains Mono',monospace;font-size:12px;" />
        </div>
      </div>
      <div style="margin-bottom:14px;">
        <label style="font-size:11px;color:var(--text-muted);margin-bottom:4px;display:block;">USER-AGENT</label>
        <input class="proxyUA" data-id="${platform.id}" value="${row.user_agent || ""}" placeholder="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" style="font-family:'JetBrains Mono',monospace;font-size:12px;" />
      </div>
      <button class="taskRunBtn proxySaveBtn" data-id="${platform.id}" style="width:100%;margin-top:0;">Сохранить</button>
      <div class="proxySaveMsg" data-id="${platform.id}" style="margin-top:8px;font-size:12px;min-height:18px;"></div>
    `;

    list.appendChild(card);
  });

  // Навешиваем обработчики
  document.querySelectorAll(".proxySaveBtn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id;
      const host     = document.querySelector(`.proxyHost[data-id="${id}"]`).value.trim();
      const port     = parseInt(document.querySelector(`.proxyPort[data-id="${id}"]`).value.trim()) || 0;
      const username = document.querySelector(`.proxyUser[data-id="${id}"]`).value.trim();
      const password = document.querySelector(`.proxyPass[data-id="${id}"]`).value.trim();
      const use_proxy = document.querySelector(`.proxyActive[data-id="${id}"]`).checked;
      const user_agent = document.querySelector(`.proxyUA[data-id="${id}"]`).value.trim();
      const msg = document.querySelector(`.proxySaveMsg[data-id="${id}"]`);

      btn.disabled = true;
      btn.textContent = "Сохраняю...";
      msg.textContent = "";

      try {
        const res = await fetch("/api/proxy-settings", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id, host, port, username, password, use_proxy, user_agent }),
        });
        const data = await res.json();
        if (res.ok) {
          msg.style.color = "var(--green, #10f5a8)";
          msg.textContent = "✓ Сохранено";
        } else {
          msg.style.color = "#fb7185";
          msg.textContent = "✗ " + (data.error || "Ошибка");
        }
      } catch (e) {
        msg.style.color = "#fb7185";
        msg.textContent = "✗ Ошибка сети";
      }

      btn.disabled = false;
      btn.textContent = "Сохранить";
      setTimeout(() => { msg.textContent = ""; }, 3000);
    });
  });
}

// ── intCity UI ────────────────────────────────────────────

async function loadIntCityLeads() {
  const accounts = cachedAccounts.filter(a => (a.platform || "").toLowerCase() === "intcity");
  if (!accounts.length) return;
  const accountId = accounts[0].id;

  const tableEl = document.getElementById("intCityLeadsTable");
  const countEl = document.getElementById("intCityLeadsCount");
  if (!tableEl) return;

  try {
    const res = await fetch(`/api/intcity/leads?account_id=${accountId}`, { headers: { "Authorization": localStorage.getItem("claw_auth_token") || "" } });
    const data = await res.json();
    const leads = data.leads || [];
    if (countEl) countEl.textContent = `(${leads.length})`;
    if (!leads.length) {
      tableEl.innerHTML = '<div style="color:var(--text2);">Email адресов пока нет. Нажми "Парсить".</div>';
      return;
    }
    tableEl.innerHTML = leads.map(l => `
      <div style="display:flex;gap:12px;padding:4px 0;border-bottom:1px solid rgba(255,255,255,.05);">
        <span style="color:var(--cyan);flex:1;">${l.email}</span>
        <span style="color:var(--text2);font-size:11px;">${l.sent_at ? "✓ отправлено" : "не отправлено"}</span>
        <a href="${l.ad_url}" target="_blank" style="color:var(--text2);font-size:11px;">объявление</a>
      </div>
    `).join("");
  } catch (e) {
    if (tableEl) tableEl.innerHTML = `<div style="color:#fb7185;">Ошибка: ${e.message}</div>`;
  }
}

document.getElementById("intCityParseBtn")?.addEventListener("click", async () => {
  const accounts = cachedAccounts.filter(a => (a.platform || "").toLowerCase() === "intcity");
  if (!accounts.length) { alert("Сначала подключи аккаунт intCity"); return; }
  const accountId = accounts[0].id;
  const pages = parseInt(document.getElementById("intCityPages")?.value) || 3;
  const resultEl = document.getElementById("intCityParseResult");
  const btn = document.getElementById("intCityParseBtn");

  btn.disabled = true;
  btn.textContent = "Парсю...";
  if (resultEl) { resultEl.textContent = "Парсю объявления..."; resultEl.className = "result"; }

  try {
    const res = await fetch("/api/intcity/parse", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": localStorage.getItem("claw_auth_token") || "" },
      body: JSON.stringify({ account_id: accountId, pages }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || "Ошибка парсинга");
    if (resultEl) { resultEl.textContent = data.summary; resultEl.className = "result good"; }
    loadIntCityLeads();
  } catch (e) {
    if (resultEl) { resultEl.textContent = e.message; resultEl.className = "result bad"; }
  } finally {
    btn.disabled = false;
    btn.textContent = "🔍 Парсить";
  }
});

document.getElementById("intCityRefreshLeads")?.addEventListener("click", loadIntCityLeads);

document.getElementById("intCitySendBtn")?.addEventListener("click", async () => {
  const accounts = cachedAccounts.filter(a => (a.platform || "").toLowerCase() === "intcity");
  if (!accounts.length) { alert("Сначала подключи аккаунт intCity"); return; }
  const accountId = accounts[0].id;
  const subject = document.getElementById("intCitySubject")?.value.trim();
  const body = document.getElementById("intCityBody")?.value.trim();
  const limit = parseInt(document.getElementById("intCityLimit")?.value) || 50;
  const resultEl = document.getElementById("intCitySendResult");
  const btn = document.getElementById("intCitySendBtn");

  if (!subject) { alert("Введи тему письма"); return; }
  if (!body) { alert("Введи текст письма"); return; }

  btn.disabled = true;
  btn.textContent = "Отправляю...";
  if (resultEl) { resultEl.textContent = "Отправляю рассылку..."; resultEl.className = "result"; }

  try {
    const res = await fetch("/api/intcity/send", {
      method: "POST",
      headers: { "Content-Type": "application/json", "Authorization": localStorage.getItem("claw_auth_token") || "" },
      body: JSON.stringify({ account_id: accountId, subject, body, limit }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.detail || "Ошибка отправки");
    if (resultEl) { resultEl.textContent = data.summary; resultEl.className = "result good"; }
    loadIntCityLeads();
  } catch (e) {
    if (resultEl) { resultEl.textContent = e.message; resultEl.className = "result bad"; }
  } finally {
    btn.disabled = false;
    btn.textContent = "📨 Отправить рассылку";
  }
});

// ── КОНТАКТЫ ────────────────────────────────────────────

async function loadContacts() {
  const tableEl = document.getElementById("contactsTable");
  const countEl = document.getElementById("contactsTotalCount");
  const search = document.getElementById("contactsSearch")?.value.trim().toLowerCase() || "";
  const filter = document.getElementById("contactsFilter")?.value || "all";
  if (!tableEl) return;

  tableEl.innerHTML = '<div style="color:var(--text2);">Загрузка...</div>';

  try {
    const accounts = cachedAccounts.filter(a => (a.platform || "").toLowerCase() === "intcity");
    if (!accounts.length) {
      tableEl.innerHTML = '<div style="color:var(--text2);">Нет подключённых аккаунтов intCity.</div>';
      return;
    }
    const accountId = accounts[0].id;
    const res = await fetch(`/api/intcity/leads?account_id=${accountId}`, { headers: { "Authorization": localStorage.getItem("claw_auth_token") || "" } });
    const data = await res.json();
    let leads = data.leads || [];

    if (countEl) countEl.textContent = `(всего: ${leads.length})`;

    // Фильтрация
    if (filter === "sent") leads = leads.filter(l => l.sent_at);
    if (filter === "unsent") leads = leads.filter(l => !l.sent_at);
    if (search) leads = leads.filter(l => l.email.toLowerCase().includes(search));

    if (!leads.length) {
      tableEl.innerHTML = '<div style="color:var(--text2);">Нет контактов по фильтру.</div>';
      return;
    }

    tableEl.innerHTML = `
      <div style="display:grid;grid-template-columns:1fr 140px 1fr;gap:0;border:1px solid rgba(255,255,255,.08);border-radius:10px;overflow:hidden;">
        <div style="padding:8px 12px;background:rgba(255,255,255,.04);font-weight:600;color:var(--text2);font-size:11px;">EMAIL</div>
        <div style="padding:8px 12px;background:rgba(255,255,255,.04);font-weight:600;color:var(--text2);font-size:11px;">СТАТУС</div>
        <div style="padding:8px 12px;background:rgba(255,255,255,.04);font-weight:600;color:var(--text2);font-size:11px;">ИСТОЧНИК</div>
        ${leads.map(l => `
          <div style="padding:8px 12px;border-top:1px solid rgba(255,255,255,.05);color:var(--cyan);">${l.email}</div>
          <div style="padding:8px 12px;border-top:1px solid rgba(255,255,255,.05);color:${l.sent_at ? "var(--green)" : "var(--text2)"};">${l.sent_at ? "✓ отправлено" : "ожидает"}</div>
          <div style="padding:8px 12px;border-top:1px solid rgba(255,255,255,.05);"><a href="${l.ad_url}" target="_blank" style="color:var(--text2);text-decoration:none;font-size:11px;">объявление ↗</a></div>
        `).join("")}
      </div>
    `;
  } catch (e) {
    tableEl.innerHTML = `<div style="color:#fb7185;">Ошибка: ${e.message}</div>`;
  }
}

document.getElementById("contactsRefreshBtn")?.addEventListener("click", loadContacts);

document.getElementById("contactsSearch")?.addEventListener("input", loadContacts);
document.getElementById("contactsFilter")?.addEventListener("change", loadContacts);

document.getElementById("contactsExportBtn")?.addEventListener("click", async () => {
  const accounts = cachedAccounts.filter(a => (a.platform || "").toLowerCase() === "intcity");
  if (!accounts.length) { alert("Нет аккаунтов intCity"); return; }
  const res = await fetch(`/api/intcity/leads?account_id=${accounts[0].id}`);
  const data = await res.json();
  const leads = data.leads || [];
  const csv = "email,status,ad_url\n" + leads.map(l =>
    `${l.email},${l.sent_at ? "sent" : "unsent"},${l.ad_url}`
  ).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "intcity_contacts.csv";
  a.click(); URL.revokeObjectURL(url);
});

window.loadProxySettings = loadProxySettings;
