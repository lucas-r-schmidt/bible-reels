// ==========================================================================
// Bible Reels Studio — Frontend App Logic (Modern UX v2)
// ==========================================================================

document.addEventListener("DOMContentLoaded", () => {
  let currentUser = null;
  let currentPosts = [];
  let currentQueue = [];
  let currentSaints = [];
  let selectedPost = null;
  let selectedPostIds = new Set();

  let activeStatus = "all";
  let activeCategory = "all";
  let activeSort = "newest";
  let searchQuery = "";
  let isListMode = false;
  let calendarOffsetWeeks = 0;

  // Icons Helper
  function refreshIcons() {
    if (window.lucide) window.lucide.createIcons();
  }

  // Toasts
  function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
  }

  // --------------------------------------------------------------------------
  // AUTHENTICATION & ACCESS CONTROL
  // --------------------------------------------------------------------------
  const authOverlay = document.getElementById("auth-overlay");
  const formLogin = document.getElementById("form-login");
  const formRegister = document.getElementById("form-register");
  const authPendingCard = document.getElementById("auth-pending-card");
  const loginErrorMsg = document.getElementById("login-error-msg");
  const regErrorMsg = document.getElementById("reg-error-msg");
  const linkShowRegister = document.getElementById("link-show-register");
  const linkShowLogin = document.getElementById("link-show-login");
  const btnPendingLogout = document.getElementById("btn-pending-logout");
  const btnLogout = document.getElementById("btn-logout");
  const userSessionCard = document.getElementById("user-session-card");
  const userDisplayName = document.getElementById("user-display-name");
  const userDisplayEmail = document.getElementById("user-display-email");
  const navBtnUsers = document.getElementById("nav-btn-users");
  const navCountPendingUsers = document.getElementById("nav-count-pending-users");

  if (linkShowRegister) {
    linkShowRegister.addEventListener("click", (e) => {
      e.preventDefault();
      formLogin.style.display = "none";
      formRegister.style.display = "block";
      authPendingCard.style.display = "none";
      regErrorMsg.style.display = "none";
    });
  }

  if (linkShowLogin) {
    linkShowLogin.addEventListener("click", (e) => {
      e.preventDefault();
      formRegister.style.display = "none";
      formLogin.style.display = "block";
      authPendingCard.style.display = "none";
      loginErrorMsg.style.display = "none";
    });
  }

  if (btnPendingLogout) {
    btnPendingLogout.addEventListener("click", () => handleLogout());
  }

  if (btnLogout) {
    btnLogout.addEventListener("click", () => handleLogout());
  }

  async function checkAuthSession() {
    try {
      const res = await fetch("/api/auth/me");
      const data = await res.json();
      if (data.authenticated && data.user) {
        currentUser = data.user;
        if (currentUser.status === "pending") {
          showAuthScreen("pending");
          return false;
        }
        hideAuthScreen();
        renderUserSession(currentUser);
        return true;
      } else {
        showAuthScreen("login");
        return false;
      }
    } catch (e) {
      showAuthScreen("login");
      return false;
    }
  }

  function showAuthScreen(mode = "login") {
    authOverlay.style.display = "flex";
    if (mode === "login") {
      formLogin.style.display = "block";
      formRegister.style.display = "none";
      authPendingCard.style.display = "none";
    } else if (mode === "register") {
      formLogin.style.display = "none";
      formRegister.style.display = "block";
      authPendingCard.style.display = "none";
    } else if (mode === "pending") {
      formLogin.style.display = "none";
      formRegister.style.display = "none";
      authPendingCard.style.display = "block";
    }
    refreshIcons();
  }

  function hideAuthScreen() {
    authOverlay.style.display = "none";
  }

  function renderUserSession(user) {
    if (!user) return;
    if (userSessionCard) userSessionCard.style.display = "block";
    if (userDisplayName) userDisplayName.textContent = user.name || "Usuário";
    if (userDisplayEmail) userDisplayEmail.textContent = user.email || "";

    if (user.role === "admin") {
      if (navBtnUsers) navBtnUsers.style.display = "flex";
      loadAdminUsers();
    } else {
      if (navBtnUsers) navBtnUsers.style.display = "none";
    }
  }

  if (formLogin) {
    formLogin.addEventListener("submit", async (e) => {
      e.preventDefault();
      const email = document.getElementById("login-email").value.trim();
      const password = document.getElementById("login-password").value;
      const btn = document.getElementById("btn-submit-login");

      btn.disabled = true;
      btn.textContent = "Entrando...";
      loginErrorMsg.style.display = "none";

      try {
        const res = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email, password, remember_me: true })
        });
        const data = await res.json();
        if (res.ok && data.success && data.user) {
          currentUser = data.user;
          if (currentUser.status === "pending") {
            showAuthScreen("pending");
          } else {
            hideAuthScreen();
            renderUserSession(currentUser);
            loadStats();
            loadPosts();
            showToast(`Bem-vindo, ${currentUser.name}!`, "success");
          }
        } else {
          loginErrorMsg.textContent = data.error || "E-mail ou senha incorretos.";
          loginErrorMsg.style.display = "block";
        }
      } catch (err) {
        loginErrorMsg.textContent = "Erro ao conectar ao servidor.";
        loginErrorMsg.style.display = "block";
      } finally {
        btn.disabled = false;
        btn.textContent = "Entrar no Studio";
      }
    });
  }

  if (formRegister) {
    formRegister.addEventListener("submit", async (e) => {
      e.preventDefault();
      const name = document.getElementById("reg-name").value.trim();
      const email = document.getElementById("reg-email").value.trim();
      const password = document.getElementById("reg-password").value;
      const btn = document.getElementById("btn-submit-register");

      btn.disabled = true;
      btn.textContent = "Cadastrando...";
      regErrorMsg.style.display = "none";

      try {
        const res = await fetch("/api/auth/register", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name, email, password, remember_me: true })
        });
        const data = await res.json();
        if (res.ok && data.success && data.user) {
          currentUser = data.user;
          if (currentUser.status === "pending") {
            showAuthScreen("pending");
          } else {
            hideAuthScreen();
            renderUserSession(currentUser);
            loadStats();
            loadPosts();
            showToast(`Conta criada com sucesso!`, "success");
          }
        } else {
          regErrorMsg.textContent = data.error || "Falha ao registrar.";
          regErrorMsg.style.display = "block";
        }
      } catch (err) {
        regErrorMsg.textContent = "Erro ao conectar ao servidor.";
        regErrorMsg.style.display = "block";
      } finally {
        btn.disabled = false;
        btn.textContent = "Solicitar Acesso";
      }
    });
  }

  async function handleLogout() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch (e) {}
    currentUser = null;
    if (userSessionCard) userSessionCard.style.display = "none";
    showAuthScreen("login");
  }

  // --------------------------------------------------------------------------
  // ADMIN USERS MANAGEMENT
  // --------------------------------------------------------------------------
  async function loadAdminUsers() {
    if (!currentUser || currentUser.role !== "admin") return;
    try {
      const res = await fetch("/api/admin/users");
      if (!res.ok) return;
      const data = await res.json();
      renderUsersTable(data.users || []);
    } catch (e) {
      console.error("Erro ao carregar usuários:", e);
    }
  }

  function renderUsersTable(users) {
    const tbody = document.getElementById("users-table-body");
    if (!tbody) return;

    let pendingCount = 0;
    if (!users || users.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="padding: 16px; text-align: center; color: var(--text-muted);">Nenhum usuário cadastrado.</td></tr>`;
      return;
    }

    tbody.innerHTML = users.map(u => {
      if (u.status === "pending") pendingCount++;
      const isSelf = currentUser && currentUser.id === u.id;
      const isAdmEmail = u.email.toLowerCase() === "lucas.r.schmidt@gmail.com";

      let statusBadge = "";
      if (u.status === "active") {
        statusBadge = `<span class="badge" style="background: var(--success-soft); color: var(--success); font-weight: 600;">Ativo</span>`;
      } else if (u.status === "pending") {
        statusBadge = `<span class="badge" style="background: var(--warn-soft); color: var(--warn); font-weight: 600;">Pendente</span>`;
      } else {
        statusBadge = `<span class="badge" style="background: var(--danger-soft); color: var(--danger); font-weight: 600;">Bloqueado</span>`;
      }

      let actions = "";
      if (isAdmEmail) {
        actions = `<span class="muted-sm" style="font-size: 11px;">Admin Principal</span>`;
      } else {
        const approveBtn = u.status !== "active" ? `
          <button class="btn btn-sm" onclick="window._updateUserStatus(${u.id}, 'active')" style="background: var(--success); color: white; padding: 4px 8px; font-size: 11px; margin-right: 4px;">Aprovar</button>
        ` : "";
        const blockBtn = u.status === "active" ? `
          <button class="btn btn-sm btn-ghost" onclick="window._updateUserStatus(${u.id}, 'disabled')" style="color: var(--danger); padding: 4px 8px; font-size: 11px; margin-right: 4px;">Bloquear</button>
        ` : "";
        const delBtn = `
          <button class="btn btn-sm btn-ghost" onclick="window._deleteUser(${u.id})" style="color: var(--text-muted); padding: 4px 8px; font-size: 11px;">Excluir</button>
        `;
        actions = `${approveBtn}${blockBtn}${delBtn}`;
      }

      const created = u.created_at ? u.created_at.slice(0, 10).split("-").reverse().join("/") : "-";

      return `
        <tr style="border-bottom: 1px solid var(--border);">
          <td style="padding: 12px; font-weight: 600;">${escapeHtml(u.name)}</td>
          <td style="padding: 12px; color: var(--text-secondary); font-family: monospace;">${escapeHtml(u.email)}</td>
          <td style="padding: 12px;"><span style="text-transform: capitalize;">${u.role}</span></td>
          <td style="padding: 12px;">${statusBadge}</td>
          <td style="padding: 12px; font-size: 12px; color: var(--text-muted);">${created}</td>
          <td style="padding: 12px; text-align: right;">${actions}</td>
        </tr>
      `;
    }).join("");

    if (navCountPendingUsers) {
      navCountPendingUsers.textContent = pendingCount;
      navCountPendingUsers.style.display = pendingCount > 0 ? "inline-block" : "none";
    }
  }

  window._updateUserStatus = async function(userId, status) {
    try {
      const res = await fetch("/api/admin/users/status", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId, status })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        showToast("Status atualizado com sucesso!", "success");
        loadAdminUsers();
      } else {
        showToast(data.error || "Erro ao atualizar status.", "error");
      }
    } catch (e) {
      showToast("Erro na comunicação.", "error");
    }
  };

  window._deleteUser = async function(userId) {
    if (!confirm("Tem certeza que deseja excluir esta conta?")) return;
    try {
      const res = await fetch("/api/admin/users/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: userId })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        showToast("Conta excluída com sucesso!", "success");
        loadAdminUsers();
      } else {
        showToast(data.error || "Erro ao excluir conta.", "error");
      }
    } catch (e) {
      showToast("Erro na comunicação.", "error");
    }
  };

  const btnRefreshUsers = document.getElementById("btn-refresh-users");
  if (btnRefreshUsers) {
    btnRefreshUsers.addEventListener("click", () => loadAdminUsers());
  }

  // Navigation: Switch View
  function switchView(viewName) {
    document.querySelectorAll(".view").forEach(v => v.classList.toggle("active", v.id === `view-${viewName}`));
    document.querySelectorAll(".nav-btn").forEach(b => b.classList.toggle("active", b.dataset.view === viewName));

    if (viewName === "queue") loadQueue();
    if (viewName === "settings") { loadProfiles(); loadLogs(); }
    if (viewName === "calendar") renderCalendar();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  document.querySelectorAll(".nav-btn").forEach(btn => {
    btn.addEventListener("click", () => switchView(btn.dataset.view));
  });

  document.querySelectorAll("[data-nav-target]").forEach(btn => {
    btn.addEventListener("click", () => switchView(btn.dataset.navTarget));
  });

  // Theme Toggle
  const themeToggle = document.getElementById("theme-toggle");
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const html = document.documentElement;
      const nextTheme = html.getAttribute("data-theme") === "dark" ? "light" : "dark";
      html.setAttribute("data-theme", nextTheme);
      localStorage.setItem("br_theme", nextTheme);
      showToast(`Tema alterado para ${nextTheme === "dark" ? "Escuro" : "Claro"}`);
    });
    const savedTheme = localStorage.getItem("br_theme");
    if (savedTheme) document.documentElement.setAttribute("data-theme", savedTheme);
  }

  // Helper date functions
  function getTodayDateStr() {
    return new Date().toISOString().split("T")[0];
  }

  function getTomorrowDateStr() {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return d.toISOString().split("T")[0];
  }

  function formatDateTimeLocal(d, hour = 6, minute = 0) {
    const copy = new Date(d);
    copy.setHours(hour, minute, 0, 0);
    const pad = n => String(n).padStart(2, "0");
    return `${copy.getFullYear()}-${pad(copy.getMonth() + 1)}-${pad(copy.getDate())}T${pad(copy.getHours())}:${pad(copy.getMinutes())}`;
  }

  function escapeHtml(text) {
    if (!text) return "";
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatDate(isoStr) {
    if (!isoStr) return "-";
    try {
      const d = new Date(isoStr);
      return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
    } catch {
      return isoStr;
    }
  }

  // Greeting and Subtitle
  function updateGreeting() {
    const hour = new Date().getHours();
    let greet = "Bom dia 👋";
    if (hour >= 12 && hour < 18) greet = "Boa tarde 👋";
    else if (hour >= 18 || hour < 5) greet = "Boa noite 👋";

    const el = document.getElementById("home-greeting");
    if (el) el.textContent = greet;

    const sub = document.getElementById("home-date-subtitle");
    if (sub) {
      const options = { weekday: "long", day: "numeric", month: "long" };
      const dateStr = new Date().toLocaleDateString("pt-BR", options);
      sub.textContent = dateStr.charAt(0).toUpperCase() + dateStr.slice(1);
    }
  }

  // Stats & Pipeline
  async function loadStats() {
    try {
      const res = await fetch("/api/stats");
      if (!res.ok) throw new Error("Erro HTTP");
      const data = await res.json();

      const elVerses = document.getElementById("stat-pipe-verses");
      const elPosts = document.getElementById("stat-pipe-formatted");
      const elPending = document.getElementById("stat-pipe-pending");
      const elSent = document.getElementById("stat-pipe-sent");

      if (elVerses) elVerses.textContent = data.verses_count ?? 0;
      if (elPosts) elPosts.textContent = data.posts_count ?? 0;
      if (elPending) elPending.textContent = data.queue_pending ?? 0;
      if (elSent) elSent.textContent = data.queue_sent ?? 0;

      const navPosts = document.getElementById("nav-count-posts");
      const navQueue = document.getElementById("nav-count-queue");
      if (navPosts) navPosts.textContent = data.posts_count ?? 0;
      if (navQueue) navQueue.textContent = data.queue_pending ?? 0;

      const dot = document.getElementById("engine-status-dot");
      const sub = document.getElementById("engine-status-sub");
      if (dot) {
        dot.className = "status-dot";
        if (data.postproxy_active) sub.textContent = "Postproxy Ativo";
        else sub.textContent = "Buffer Ativo";
      }

      // Novena Spotlight banner
      const novenaCard = document.getElementById("novena-spotlight");
      if (novenaCard) {
        if (data.active_novena) {
          novenaCard.style.display = "flex";
          const nov = data.active_novena;
          const novTitle = document.getElementById("novena-spotlight-title");
          const novDesc = document.getElementById("novena-spotlight-desc");
          const novDate = document.getElementById("novena-badge-date");
          const novBtnLabel = document.getElementById("btn-novena-action-label");
          const novMenuSub = document.getElementById("new-novena-subtitle");

          if (novTitle) novTitle.textContent = `Novena de ${nov.saint_name} (${nov.novena_day}º Dia)`;
          if (novDesc) novDesc.textContent = `Estamos no ${nov.novena_day}º Dia da novena (de ${nov.total_days}). A grande solenidade será celebrada em ${nov.feast_date}!`;
          if (novDate) novDate.textContent = `Festa Solene em ${nov.feast_date}`;
          if (novBtnLabel) novBtnLabel.textContent = `Gerar ${nov.novena_day}º Dia`;
          if (novMenuSub) novMenuSub.textContent = `${nov.saint_name} (${nov.novena_day}º Dia)`;
        } else {
          novenaCard.style.display = "none";
        }
      }

      // Attention list
      renderAttentionList(data);
    } catch (err) {
      console.warn("Erro ao carregar stats:", err);
      const dot = document.getElementById("engine-status-dot");
      if (dot) dot.className = "status-dot offline";
      const txt = document.getElementById("engine-status-text");
      if (txt) txt.textContent = "Servidor Offline";
    }
  }

  function renderAttentionList(stats) {
    const container = document.getElementById("home-attention-list");
    if (!container) return;

    const items = [];
    if (stats.queue_failed > 0) {
      items.push(`
        <div class="list-row alert-row error">
          <div class="alert-icon"><i data-lucide="alert-triangle"></i></div>
          <div class="row-info">
            <strong>${stats.queue_failed} post(s) falharam no envio</strong>
            <span>Verifique a fila para diagnosticar o erro</span>
          </div>
          <button class="btn btn-secondary btn-sm" data-nav-target="queue">Ver Fila</button>
        </div>
      `);
    }

    if (stats.queue_pending > 0) {
      items.push(`
        <div class="list-row alert-row warn">
          <div class="alert-icon"><i data-lucide="clock"></i></div>
          <div class="row-info">
            <strong>${stats.queue_pending} post(s) aguardando na fila</strong>
            <span>Prontos para disparo ou agendamento</span>
          </div>
          <button class="btn btn-primary btn-sm" id="btn-quick-dispatch">Disparar</button>
        </div>
      `);
    } else {
      items.push(`
        <div class="list-row alert-row info">
          <div class="alert-icon"><i data-lucide="check-circle-2"></i></div>
          <div class="row-info">
            <strong>Pipeline em dia</strong>
            <span>Sem falhas críticas pendentes</span>
          </div>
          <button class="btn btn-ghost btn-sm" id="btn-quick-new-saint">Gerar Santo</button>
        </div>
      `);
    }

    container.innerHTML = items.join("");
    refreshIcons();

    const quickDisp = document.getElementById("btn-quick-dispatch");
    if (quickDisp) {
      quickDisp.addEventListener("click", () => triggerAction("/api/actions/dispatch", {}, quickDisp, "Fila disparada!"));
    }
    const quickSaint = document.getElementById("btn-quick-new-saint");
    if (quickSaint) {
      quickSaint.addEventListener("click", openSaintModal);
    }
  }

  // Posts Library
  async function loadPosts() {
    try {
      const res = await fetch("/api/posts?limit=150");
      if (!res.ok) throw new Error("Erro HTTP posts");
      currentPosts = await res.json();
      updateFilterCounts();
      renderPosts();
      renderUpcomingHome();
      renderCalendar();
    } catch (err) {
      console.warn("Erro ao buscar posts:", err);
      const container = document.getElementById("posts-container");
      if (container) {
        container.innerHTML = `<div class="panel-card" style="grid-column: 1/-1; text-align:center; padding: 30px;">
          <strong>Falha ao carregar posts</strong>
          <p class="subtitle">Certifique-se de que o backend local está em execução.</p>
        </div>`;
      }
    }
  }

  function isPostPublished(post) {
    if (!post) return false;
    return post.status === "published" || Boolean(post.published_at) || (Number(post.published_count || 0) > 0);
  }

  function getPostSourceCategory(postOrSource) {
    if (!postOrSource) return "scripture";
    let s = "";
    let ref = "";
    if (typeof postOrSource === "object") {
      s = (postOrSource.content_type || postOrSource.verse_source || postOrSource.source || "").toLowerCase();
      ref = (postOrSource.reference || "").toLowerCase();
    } else {
      s = String(postOrSource).toLowerCase();
    }

    if (s === "novena" || ref.includes("novena")) return "novena";
    if (s === "saint" || s === "santo" || ref.includes("santo") || ref.includes("santa") || ref.includes("senhora")) return "saint";
    if (s === "gospel" || s === "evangelho" || ref.includes("evangelho")) return "gospel";
    if (s === "prayer" || s === "psalm" || s === "salmo" || s === "oracao" || ref.includes("oração") || ref.includes("oracao") || ref.includes("salmo")) return "prayer";
    if (s === "community" || s === "comunidade" || ref.includes("inscrito") || ref.includes("comunidade")) return "community";
    return "scripture";
  }

  function getCategoryLabel(cat) {
    const map = {
      saint: "🕊️ Santo do Dia",
      novena: "🔥 Novena Litúrgica",
      gospel: "📜 Evangelho",
      scripture: "📖 Escrituras",
      prayer: "🙏 Orações & Salmos",
      community: "🤝 Comunidade"
    };
    return map[cat] || "📖 Escrituras";
  }

  function updateFilterCounts() {
    const cAll = currentPosts.length;
    let cUnpub = 0, cPub = 0, cReady = 0;
    let cScript = 0, cGosp = 0, cSaint = 0, cNovena = 0, cPray = 0, cComm = 0;

    currentPosts.forEach(p => {
      const pub = isPostPublished(p);
      if (pub) cPub++;
      else cUnpub++;

      if (p.video_path || p.video_url || p.image_path || p.image_url) cReady++;

      const cat = getPostSourceCategory(p);
      if (cat === "saint") cSaint++;
      else if (cat === "novena") cNovena++;
      else if (cat === "gospel") cGosp++;
      else if (cat === "prayer") cPray++;
      else if (cat === "community") cComm++;
      else cScript++;
    });

    const setT = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.textContent = val;
    };

    setT("count-all", cAll);
    setT("count-ready", cReady);
    setT("count-unpublished", cUnpub);
    setT("count-published", cPub);
    setT("count-scriptures", cScript);
    setT("count-gospel", cGosp);
    setT("count-saints", cSaint);
    setT("count-novenas", cNovena);
    setT("count-prayers", cPray);
    setT("count-community", cComm);
  }

  function renderPosts() {
    const container = document.getElementById("posts-container");
    if (!container) return;

    let filtered = currentPosts.filter(p => {
      const isPub = isPostPublished(p);
      const isReady = Boolean(p.video_path || p.video_url || p.image_path || p.image_url);

      if (activeStatus === "published" && !isPub) return false;
      if (activeStatus === "unpublished" && isPub) return false;
      if (activeStatus === "ready" && !isReady) return false;

      const cat = getPostSourceCategory(p);
      if (activeCategory !== "all" && cat !== activeCategory) return false;

      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const ref = (p.reference || "").toLowerCase();
        const text = (p.formatted_text || p.original_text || p.verse_text || p.caption || "").toLowerCase();
        if (!ref.includes(q) && !text.includes(q)) return false;
      }
      return true;
    });

    // Ordenação
    if (activeSort === "newest") {
      filtered.sort((a, b) => (b.id || 0) - (a.id || 0));
    } else if (activeSort === "oldest") {
      filtered.sort((a, b) => (a.id || 0) - (b.id || 0));
    } else if (activeSort === "reference") {
      filtered.sort((a, b) => (a.reference || "").localeCompare(b.reference || ""));
    }

    if (!filtered.length) {
      container.innerHTML = `
        <div class="panel-card" style="grid-column: 1/-1; text-align:center; padding: 40px;">
          <strong>Nenhum conteúdo encontrado</strong>
          <p class="subtitle">Ajuste os filtros de status ou categoria para ver outros posts.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = filtered.map(post => {
      const isPub = isPostPublished(post);
      const isVideo = Boolean(post.video_path || post.video_url);
      const isSel = selectedPostIds.has(post.id);
      const cat = getPostSourceCategory(post);
      const catLabel = getCategoryLabel(cat);
      const text = post.formatted_text || post.original_text || post.verse_text || post.caption || "";

      let mediaThumbStyle = "";
      const imgTarget = post.image_url || (post.image_path ? `/media/${encodeURIComponent(post.image_path)}` : null);
      if (imgTarget) {
        mediaThumbStyle = `background-image: url('${imgTarget}');`;
      } else {
        mediaThumbStyle = "background: linear-gradient(135deg, #1e1b4b, #312e81);";
      }

      return `
        <article class="post-card ${isSel ? "selected" : ""}" data-post-id="${post.id}">
          <input type="checkbox" class="card-check" data-select-id="${post.id}" ${isSel ? "checked" : ""} aria-label="Selecionar post">
          <div class="card-thumb" style="${mediaThumbStyle}" data-click-open="${post.id}">
            <div class="card-top-badges">
              ${isVideo ? '<span class="badge badge-accent">🎥 Vídeo</span>' : '<span class="badge badge-neutral">🖼️ Imagem</span>'}
              ${isPub ? '<span class="badge badge-success">✓ Publicado</span>' : '<span class="badge badge-warn">⏳ Pendente</span>'}
            </div>
            <p class="card-quote">“${escapeHtml(text)}”</p>
          </div>
          <div class="card-body">
            <div class="card-title-row">
              <strong title="${escapeHtml(post.reference)}">${escapeHtml(post.reference || "Sem Referência")}</strong>
            </div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span class="muted-sm">${catLabel}</span>
              <span class="muted-sm">#${post.id}</span>
            </div>
            <div class="card-footer">
              <span>${formatDate(post.created_at)}</span>
              <button class="btn btn-ghost btn-sm" data-click-open="${post.id}">Abrir →</button>
            </div>
          </div>
        </article>
      `;
    }).join("");

    updateBulkBar();
    refreshIcons();
  }

  function updateBulkBar() {
    const bar = document.getElementById("bulk-bar");
    const countEl = document.getElementById("bulk-count");
    if (!bar || !countEl) return;
    countEl.textContent = selectedPostIds.size;
    bar.hidden = selectedPostIds.size === 0;
  }

  // Upcoming items on Home
  function renderUpcomingHome() {
    const list = document.getElementById("home-upcoming-list");
    if (!list) return;

    const upcoming = currentPosts.filter(p => !p.published_count || p.published_count === 0).slice(0, 3);
    if (!upcoming.length) {
      list.innerHTML = `<div class="muted-sm" style="padding: 12px; text-align:center;">Todos os posts gerados foram publicados!</div>`;
      return;
    }

    list.innerHTML = upcoming.map(p => {
      const thumbStyle = p.image_path ? `background-image: url('/media/${encodeURIComponent(p.image_path)}');` : "background: #27272a;";
      return `
        <div class="list-row" data-click-open="${p.id}" style="cursor:pointer;">
          <div class="row-thumb" style="${thumbStyle}"></div>
          <div class="row-info">
            <strong>${escapeHtml(p.reference || "Sem título")}</strong>
            <span>${p.video_path ? "Vídeo 9:16 Pronto" : "Imagem única pronta"} • #${p.id}</span>
          </div>
          <div class="row-platforms">
            <span class="plat-pill general">Auto</span>
          </div>
        </div>
      `;
    }).join("");
  }

  // Calendar
  function renderCalendar() {
    const board = document.getElementById("calendar-board");
    if (!board) return;

    const now = new Date();
    now.setDate(now.getDate() + (calendarOffsetWeeks * 7));

    // Achar o início da semana (segunda-feira)
    const dayOfWeek = now.getDay();
    const diffToMonday = (dayOfWeek === 0 ? -6 : 1) - dayOfWeek;
    const monday = new Date(now);
    monday.setDate(now.getDate() + diffToMonday);

    const weekDays = [];
    const dayNames = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

    for (let i = 0; i < 7; i++) {
      const d = new Date(monday);
      d.setDate(monday.getDate() + i);
      const isToday = (d.toDateString() === new Date().toDateString());
      const isoDate = d.toISOString().split("T")[0];

      // Busca eventos e santos do catálogo
      const saintEvent = currentSaints.find(s => s.date === isoDate);
      const matchingPosts = currentPosts.filter(p => (p.created_at || "").startsWith(isoDate));

      weekDays.push({
        dayName: dayNames[i],
        dayNum: d.getDate(),
        isToday,
        isoDate,
        liturgy: saintEvent ? saintEvent.name : "Liturgia Diária",
        posts: matchingPosts
      });
    }

    const rangeLabel = document.getElementById("cal-range-label");
    if (rangeLabel) {
      const startStr = `${weekDays[0].dayNum}/${monday.getMonth() + 1}`;
      const endD = new Date(monday);
      endD.setDate(monday.getDate() + 6);
      const endStr = `${endD.getDate()}/${endD.getMonth() + 1}/${endD.getFullYear()}`;
      rangeLabel.textContent = `${startStr} – ${endStr}`;
    }

    board.innerHTML = weekDays.map(d => `
      <div class="cal-col ${d.isToday ? "today" : ""}">
        <div class="cal-day-head">
          <span class="cal-day-name">${d.dayName}${d.isToday ? " • Hoje" : ""}</span>
          <span class="cal-day-num">${d.dayNum}</span>
        </div>
        <div class="cal-liturgy" data-open-saint-date="${d.isoDate}" title="Clique para gerar post deste dia">
          🕊️ ${escapeHtml(d.liturgy)}
        </div>
        ${d.posts.map(p => {
          const cat = getPostSourceCategory(p.source);
          return `
            <div class="cal-event ${cat}" data-click-open="${p.id}">
              <span class="cal-event-time">Post #${p.id}</span>
              <strong>${escapeHtml(p.reference || "Verso")}</strong>
            </div>
          `;
        }).join("")}
      </div>
    `).join("");

    refreshIcons();
  }

  // Queue
  async function loadQueue() {
    const tbody = document.getElementById("queue-tbody");
    if (!tbody) return;
    try {
      const res = await fetch("/api/queue");
      if (!res.ok) throw new Error("Erro HTTP fila");
      currentQueue = await res.json();

      if (!currentQueue.length) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 24px;">Nenhum item na fila no momento.</td></tr>`;
        return;
      }

      tbody.innerHTML = currentQueue.map(item => {
        let statusBadge = `<span class="badge badge-neutral">${item.status}</span>`;
        if (item.status === "sent") statusBadge = `<span class="badge badge-success">✓ Enviado</span>`;
        else if (item.status === "pending") statusBadge = `<span class="badge badge-warn">⏳ Pendente</span>`;
        else if (item.status === "failed") statusBadge = `<span class="badge badge-danger">✗ Falhou</span>`;

        const isPendingOrFailed = item.status === "pending" || item.status === "failed";

        return `
          <tr>
            <td><strong>#${item.id}</strong></td>
            <td>
              <a href="javascript:void(0)" class="queue-post-link" data-click-open="${item.post_id}" title="Abrir e visualizar Post #${item.post_id}">
                ${escapeHtml(item.reference || `Post #${item.post_id}`)}
              </a>
            </td>
            <td><span class="badge badge-neutral">${escapeHtml(item.platform || "all")}</span></td>
            <td>${statusBadge}</td>
            <td>${item.attempts ?? 0}</td>
            <td>${formatDate(item.created_at || item.queued_at)}</td>
            <td>${formatDate(item.sent_at)}</td>
            <td class="text-right">
              <div class="queue-row-actions">
                <button class="btn btn-ghost btn-sm" data-click-open="${item.post_id}" title="Visualizar Post #${item.post_id}">
                  <i data-lucide="eye"></i> <span>Abrir</span>
                </button>
                ${isPendingOrFailed ? `
                  <button class="btn btn-secondary btn-sm" data-dispatch-single="${item.id}" title="Disparar este item agora">Disparar</button>
                  <button class="btn btn-ghost btn-sm text-danger" data-remove-queue="${item.id}" title="Tirar post da fila">
                    <i data-lucide="trash-2"></i>
                  </button>
                ` : `
                  <span class="muted-sm">Concluído</span>
                `}
              </div>
            </td>
          </tr>
        `;
      }).join("");

      refreshIcons();
    } catch (err) {
      console.warn("Erro ao buscar fila:", err);
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color: var(--danger);">Falha ao carregar fila.</td></tr>`;
    }
  }

  // Profiles
  async function loadProfiles() {
    const container = document.getElementById("profiles-container");
    if (!container) return;
    try {
      const res = await fetch("/api/profiles");
      if (!res.ok) throw new Error("Erro HTTP perfis");
      const profiles = await res.json();

      if (!profiles.length) {
        container.innerHTML = `<div class="muted-sm" style="padding: 12px;">Nenhum perfil Postproxy configurado no .env.</div>`;
        return;
      }

      container.innerHTML = profiles.map(p => `
        <div class="list-row">
          <span class="plat-pill general lg">API</span>
          <div class="row-info">
            <strong>${escapeHtml(p.name || p.id)}</strong>
            <span>${escapeHtml(p.platform || "Rede Social")} • ID: ${p.id}</span>
          </div>
          <span class="badge badge-success">Ativo</span>
        </div>
      `).join("");
    } catch (err) {
      container.innerHTML = `<div class="muted-sm" style="padding: 12px; color: var(--danger);">Erro ao carregar perfis.</div>`;
    }
  }

  // Logs
  async function loadLogs() {
    const el = document.getElementById("log-content");
    if (!el) return;
    try {
      const res = await fetch("/api/logs");
      if (!res.ok) throw new Error("Erro HTTP logs");
      const text = await res.text();
      el.textContent = text || "Nenhum log registrado.";
      el.scrollTop = el.scrollHeight;
    } catch (err) {
      el.textContent = "Erro ao carregar logs.";
    }
  }

  // Saints Catalog
  async function loadSaintsCatalog() {
    try {
      const res = await fetch("/api/saints");
      if (!res.ok) return;
      currentSaints = await res.json();

      const sel = document.getElementById("saint-select-input");
      if (sel) {
        sel.innerHTML = `<option value="auto" selected>✨ Automático pela data litúrgica</option>`;
        currentSaints.forEach(s => {
          const opt = document.createElement("option");
          opt.value = s.date;
          opt.textContent = `${s.date} — ${s.name}`;
          sel.appendChild(opt);
        });
      }

      // Spotlight hero no Início
      const tomorrowStr = getTomorrowDateStr();
      const saintTomorrow = currentSaints.find(s => s.date === tomorrowStr) || currentSaints[0];
      if (saintTomorrow) {
        const spotTitle = document.getElementById("spotlight-title");
        const spotDesc = document.getElementById("spotlight-desc");
        const spotDate = document.getElementById("spotlight-date");
        if (spotTitle) spotTitle.textContent = saintTomorrow.name;
        if (spotDate) spotDate.textContent = `Amanhã (${saintTomorrow.date})`;
        if (spotDesc) spotDesc.textContent = `Liturgia pronta. Gere o vídeo vertical 9:16 com narração neural de voz e deixe agendado para às 20:30 de hoje (véspera).`;
      }
    } catch (err) {
      console.warn("Erro ao buscar santos:", err);
    }
  }

  // Drawer Lateral (Preview do Post)
  async function openDrawer(postId) {
    const id = Number(postId);
    let post = currentPosts.find(p => p.id === id);
    if (!post) {
      try {
        const res = await fetch(`/api/posts?id=${id}`);
        if (res.ok) {
          const list = await res.json();
          post = Array.isArray(list) ? (list.find(p => p.id === id) || list[0]) : list;
          if (post) currentPosts.push(post);
        }
      } catch (err) {
        console.warn("Erro ao buscar dados do post:", err);
      }
    }
    if (!post) {
      showToast(`Post #${id} não encontrado.`, "warning");
      return;
    }
    selectedPost = post;

    const modalRef = document.getElementById("modal-reference");
    const modalTxt = document.getElementById("modal-text");
    const modalSlot = document.getElementById("modal-media-slot");
    const modalTags = document.getElementById("modal-hashtags");
    const drawerBadge = document.getElementById("drawer-post-badge");

    if (modalRef) modalRef.textContent = post.reference || `Post #${post.id}`;
    if (modalTxt) modalTxt.textContent = post.formatted_text || post.original_text || post.verse_text || post.caption || "";
    if (drawerBadge) drawerBadge.textContent = getCategoryLabel(getPostSourceCategory(post));

    // Mídia
    if (modalSlot) {
      modalSlot.innerHTML = "";
      const vidSrc = post.video_url || (post.video_path ? `/media/${encodeURIComponent(post.video_path)}` : null);
      const imgSrc = post.image_url || (post.image_path ? `/media/${encodeURIComponent(post.image_path)}` : null);

      if (vidSrc) {
        const video = document.createElement("video");
        video.src = vidSrc;
        video.controls = true;
        video.autoplay = true;
        video.loop = true;
        video.playsInline = true;
        modalSlot.appendChild(video);
      } else if (imgSrc) {
        const img = document.createElement("img");
        img.src = imgSrc;
        modalSlot.appendChild(img);
      } else {
        modalSlot.innerHTML = `<div style="color:var(--text-muted); font-size:12px; text-align:center; padding:20px;">Nenhuma mídia renderizada</div>`;
      }
    }

    if (modalTags) {
      modalTags.innerHTML = "";
      if (post.hashtags) {
        let tagList = [];
        if (Array.isArray(post.hashtags)) {
          tagList = post.hashtags;
        } else if (typeof post.hashtags === "string") {
          try {
            const parsed = JSON.parse(post.hashtags);
            tagList = Array.isArray(parsed) ? parsed : post.hashtags.split(/\s+/);
          } catch {
            tagList = post.hashtags.split(/\s+/);
          }
        }
        tagList.forEach(t => {
          const cleanTag = String(t).trim();
          if (cleanTag) {
            const span = document.createElement("span");
            span.className = "post-tag";
            span.textContent = cleanTag.startsWith("#") ? cleanTag : `#${cleanTag}`;
            modalTags.appendChild(span);
          }
        });
      }
    }

    // Default time chip
    const schedInput = document.getElementById("quick-schedule-time");
    if (schedInput) schedInput.value = formatDateTimeLocal(new Date(), 20, 30);

    document.getElementById("preview-backdrop").hidden = false;
    const drawer = document.getElementById("preview-drawer");
    drawer.classList.add("open");
    drawer.setAttribute("aria-hidden", "false");
  }

  function closeDrawer() {
    document.getElementById("preview-backdrop").hidden = true;
    const drawer = document.getElementById("preview-drawer");
    drawer.classList.remove("open");
    drawer.setAttribute("aria-hidden", "true");
    const modalSlot = document.getElementById("modal-media-slot");
    if (modalSlot) modalSlot.innerHTML = "";
  }

  const drawerCloseBtn = document.getElementById("modal-close-btn");
  if (drawerCloseBtn) drawerCloseBtn.addEventListener("click", closeDrawer);
  const drawerBackdrop = document.getElementById("preview-backdrop");
  if (drawerBackdrop) drawerBackdrop.addEventListener("click", closeDrawer);

  // Wizard Modal
  function openSaintModal(dateStr = null) {
    const backdrop = document.getElementById("wizard-backdrop");
    const modal = document.getElementById("saint-modal");
    if (!backdrop || !modal) return;

    backdrop.hidden = false;
    modal.hidden = false;

    const dateInput = document.getElementById("saint-date-input");
    if (dateInput) dateInput.value = dateStr || getTomorrowDateStr();

    const timeInput = document.getElementById("saint-schedule-time");
    if (timeInput) timeInput.value = formatDateTimeLocal(new Date(), 20, 30);
  }

  function closeSaintModal() {
    const backdrop = document.getElementById("wizard-backdrop");
    const modal = document.getElementById("saint-modal");
    if (backdrop) backdrop.hidden = true;
    if (modal) modal.hidden = true;
  }

  const wizClose = document.getElementById("saint-modal-close-btn");
  if (wizClose) wizClose.addEventListener("click", closeSaintModal);
  const wizCancel = document.getElementById("saint-modal-cancel");
  if (wizCancel) wizCancel.addEventListener("click", closeSaintModal);
  const wizBackdrop = document.getElementById("wizard-backdrop");
  if (wizBackdrop) wizBackdrop.addEventListener("click", closeSaintModal);

  // Dropdown Novo Post
  const btnNewPost = document.getElementById("btn-new-post");
  const newPostMenu = document.getElementById("new-post-menu");
  if (btnNewPost && newPostMenu) {
    btnNewPost.addEventListener("click", (e) => {
      e.stopPropagation();
      newPostMenu.hidden = !newPostMenu.hidden;
    });
    document.addEventListener("click", () => {
      newPostMenu.hidden = true;
    });
  }

  document.querySelectorAll("[data-create]").forEach(btn => {
    btn.addEventListener("click", () => {
      const type = btn.dataset.create;
      if (type === "saint") {
        openSaintModal();
      } else if (type === "novena") {
        triggerAction("/api/actions/novena", { make_video: true }, null, "Post do Dia da Novena Litúrgica em geração...");
      } else if (type === "prayer") {
        triggerAction("/api/actions/prayer", { source: "prayer", make_video: true }, null, "Oração Clássica em geração...");
      } else if (type === "psalm") {
        triggerAction("/api/actions/prayer", { source: "psalm", make_video: true }, null, "Salmo do Dia em geração...");
      } else {
        // Disparar coleta e processamento direto para o tipo escolhido
        triggerAction("/api/actions/collect", {
          source: type,
          count: 1,
          theme: "general",
          full_pipeline: true
        }, null, `Gerando post de ${type}...`);
      }
    });
  });

  const novenaAction = document.getElementById("btn-novena-action");
  if (novenaAction) {
    novenaAction.addEventListener("click", () => {
      triggerAction("/api/actions/novena", { make_video: true }, novenaAction, "Post do Dia da Novena gerado com sucesso!");
    });
  }

  const heroAction = document.getElementById("btn-hero-action");
  if (heroAction) heroAction.addEventListener("click", () => openSaintModal());
  const calNewSaint = document.getElementById("btn-cal-new-saint");
  if (calNewSaint) calNewSaint.addEventListener("click", () => openSaintModal());

  // Wizard Submit
  const saintSubmit = document.getElementById("saint-modal-submit");
  if (saintSubmit) {
    saintSubmit.addEventListener("click", async () => {
      const dateInput = document.getElementById("saint-date-input");
      const schedCheck = document.getElementById("saint-schedule-checkbox");
      const schedTime = document.getElementById("saint-schedule-time");
      const fmtRadio = document.querySelector('input[name="saint-format"]:checked');

      const dateStr = dateInput ? dateInput.value : getTomorrowDateStr();
      const format = fmtRadio ? fmtRadio.value : "video";
      const scheduleTime = (schedCheck && schedCheck.checked && schedTime) ? schedTime.value : null;

      closeSaintModal();
      await triggerAction("/api/actions/saint", {
        target_date: dateStr,
        date: dateStr,
        format: format,
        make_video: (format === "video"),
        schedule_time: scheduleTime
      }, saintSubmit, "Santo do Dia gerado e configurado com sucesso!");
    });
  }


  // ==================== VIDEOFLOW CUTS HANDLER ====================
  const btnVfCut = document.getElementById("btn-vf-generate-cut");
  const vfUrlInput = document.getElementById("vf-cut-url");
  const vfPresetSelect = document.getElementById("vf-cut-preset");
  const vfCountSelect = document.getElementById("vf-cut-count");
  const vfProgressBox = document.getElementById("vf-cut-progress");
  const vfProgressText = document.getElementById("vf-progress-text");
  const vfProgressTimer = document.getElementById("vf-progress-timer");
  const vfStatusBadge = document.getElementById("vf-status-badge");
  const btnMenuCut = document.getElementById("btn-menu-cut");

  if (btnMenuCut) {
    btnMenuCut.addEventListener("click", () => {
      const card = document.getElementById("videoflow-cut-card");
      if (card) {
        card.scrollIntoView({ behavior: "smooth", block: "center" });
        if (vfUrlInput) vfUrlInput.focus();
      }
    });
  }

  if (btnVfCut) {
    btnVfCut.addEventListener("click", async () => {
      const url = (vfUrlInput ? vfUrlInput.value : "").trim();
      if (!url) {
        showToast("Cole o link do YouTube para gerar os cortes.", "error");
        if (vfUrlInput) vfUrlInput.focus();
        return;
      }

      if (!url.includes("youtube.com") && !url.includes("youtu.be")) {
        showToast("O link precisa ser um vídeo do YouTube.", "error");
        return;
      }

      const preset = vfPresetSelect ? vfPresetSelect.value : "biblico";
      const count = vfCountSelect ? parseInt(vfCountSelect.value, 10) : 3;

      btnVfCut.disabled = true;
      if (vfProgressBox) vfProgressBox.style.display = "block";
      if (vfProgressText) vfProgressText.textContent = "Disparando corte inteligente no VideoFlow (VM Oracle)...";
      if (vfStatusBadge) {
        vfStatusBadge.textContent = "Processando cortes...";
        vfStatusBadge.className = "badge badge-warn";
      }

      let elapsedSeconds = 0;
      if (vfProgressTimer) vfProgressTimer.textContent = "00:00";
      const timerInterval = setInterval(() => {
        elapsedSeconds++;
        const mins = String(Math.floor(elapsedSeconds / 60)).padStart(2, "0");
        const secs = String(elapsedSeconds % 60).padStart(2, "0");
        if (vfProgressTimer) vfProgressTimer.textContent = `${mins}:${secs}`;
      }, 1000);

      try {
        const res = await fetch("/api/actions/cut", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url, preset, count })
        });
        const data = await res.json();

        if (!res.ok || data.error) {
          throw new Error(data.error || "Erro ao solicitar corte");
        }

        const jobId = data.job_id;
        showToast(`Job #${jobId.substring(0, 8)} iniciado no VideoFlow!`, "success");
        if (vfProgressText) vfProgressText.textContent = "Vídeo em download e análise de melhores momentos pela IA...";

        // Polling loop
        let attempts = 0;
        const maxAttempts = 120; // 10 minutos (a cada 5s)
        const pollInterval = setInterval(async () => {
          attempts++;
          try {
            const statusRes = await fetch(`/api/actions/cut/status?job_id=${encodeURIComponent(jobId)}`);
            const statusData = await statusRes.json();
            const currentStatus = statusData.status;

            if (currentStatus === "completed" || currentStatus === "done") {
              clearInterval(pollInterval);
              clearInterval(timerInterval);
              btnVfCut.disabled = false;
              if (vfStatusBadge) {
                vfStatusBadge.textContent = "Cortes Prontos";
                vfStatusBadge.className = "badge badge-success";
              }
              const importedCount = (statusData.post_ids || []).length || count;
              if (vfProgressText) vfProgressText.textContent = `✅ ${importedCount} corte(s) gerado(s) e importado(s) para o Bible Reels!`;
              showToast(`Sucesso! ${importedCount} corte(s) importado(s) para a biblioteca.`, "success");
              if (vfUrlInput) vfUrlInput.value = "";
              refreshAll();
              setTimeout(() => {
                if (vfProgressBox) vfProgressBox.style.display = "none";
              }, 8000);
            } else if (currentStatus === "failed" || currentStatus === "error") {
              clearInterval(pollInterval);
              clearInterval(timerInterval);
              btnVfCut.disabled = false;
              if (vfStatusBadge) {
                vfStatusBadge.textContent = "Falha no corte";
                vfStatusBadge.className = "badge badge-error";
              }
              const errMsg = statusData.error || "Falha no processamento do vídeo";
              if (vfProgressText) vfProgressText.textContent = `❌ ${errMsg}`;
              showToast(errMsg, "error");
            } else {
              if (attempts > 6 && vfProgressText) {
                vfProgressText.textContent = "Cortando trechos, aplicando blur 9:16 e gerando legendas dinâmicas...";
              }
            }

            if (attempts >= maxAttempts) {
              clearInterval(pollInterval);
              clearInterval(timerInterval);
              btnVfCut.disabled = false;
              showToast("Tempo de espera longo. O corte continuará em segundo plano na VM.", "info");
            }
          } catch (pollErr) {
            console.warn("Polling error:", pollErr);
          }
        }, 5000);

      } catch (err) {
        clearInterval(timerInterval);
        btnVfCut.disabled = false;
        if (vfProgressBox) vfProgressBox.style.display = "none";
        if (vfStatusBadge) {
          vfStatusBadge.textContent = "Erro";
          vfStatusBadge.className = "badge badge-error";
        }
        showToast(err.message || "Erro de conexão ao solicitar corte.", "error");
      }
    });
  }

  // Trigger Generic Actions
  async function triggerAction(actionUrl, payload = {}, btnElement = null, successMsg = "") {
    if (btnElement) btnElement.disabled = true;
    showToast("Executando ação no motor Bible Reels...");
    try {
      const res = await fetch(actionUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (!res.ok || data.error) {
        showToast(data.error || "Falha na execução", "error");
      } else {
        showToast(successMsg || data.message || "Ação concluída com sucesso!", "success");
        refreshAll();
      }
    } catch (err) {
      showToast("Erro de conexão com o servidor local.", "error");
    } finally {
      if (btnElement) btnElement.disabled = false;
    }
  }

  // Pipeline Buttons Actions
  const btnProcessPipe = document.getElementById("btn-action-process-pipe");
  if (btnProcessPipe) {
    btnProcessPipe.addEventListener("click", (e) => {
      e.stopPropagation();
      triggerAction("/api/actions/process", {}, btnProcessPipe, "Textos formatados com IA!");
    });
  }

  const btnRenderPipe = document.getElementById("btn-action-render-pipe");
  if (btnRenderPipe) {
    btnRenderPipe.addEventListener("click", (e) => {
      e.stopPropagation();
      triggerAction("/api/actions/media", { make_video: true }, btnRenderPipe, "Vídeos renderizados!");
    });
  }

  const btnDispatchPipe = document.getElementById("btn-action-dispatch-pipe");
  if (btnDispatchPipe) {
    btnDispatchPipe.addEventListener("click", (e) => {
      e.stopPropagation();
      triggerAction("/api/actions/dispatch", {}, btnDispatchPipe, "Fila de publicação disparada!");
    });
  }

  // Pipeline Filter Cards
  document.querySelectorAll(".pipe-card").forEach(card => {
    card.addEventListener("click", (e) => {
      if (e.target.closest(".pipe-action")) return;
      const st = card.dataset.goStatus;
      activeStatus = st || "all";
      document.querySelectorAll("#content-status-tabs .status-tab").forEach(t => {
        t.classList.toggle("active", t.dataset.status === activeStatus);
      });
      renderPosts();
      switchView("content");
    });
  });

  // Content Filters: Status Tabs
  document.querySelectorAll("#content-status-tabs .status-tab").forEach(tab => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("#content-status-tabs .status-tab").forEach(t => t.classList.remove("active"));
      tab.classList.add("active");
      activeStatus = tab.dataset.status;
      renderPosts();
    });
  });

  // Content Filters: Categories
  document.querySelectorAll("#category-chips .cat-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.querySelectorAll("#category-chips .cat-chip").forEach(c => c.classList.remove("active"));
      chip.classList.add("active");
      activeCategory = chip.dataset.category;
      renderPosts();
    });
  });

  // Sort Select
  const sortSelect = document.getElementById("sort-select");
  if (sortSelect) {
    sortSelect.addEventListener("change", () => {
      activeSort = sortSelect.value;
      renderPosts();
    });
  }

  // Grid / List Toggle
  document.querySelectorAll("[data-layout]").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("[data-layout]").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      isListMode = (btn.dataset.layout === "list");
      document.getElementById("posts-container").classList.toggle("list-mode", isListMode);
    });
  });

  // Global Search
  const searchInput = document.getElementById("global-search");
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      searchQuery = searchInput.value;
      switchView("content");
      renderPosts();
    });
  }

  // Delegated clicks (Cards, Open Drawer, Select Checkbox, Calendar)
  document.body.addEventListener("click", (e) => {
    const openTrigger = e.target.closest("[data-click-open]");
    if (openTrigger) {
      openDrawer(openTrigger.dataset.clickOpen);
      return;
    }

    const selectBox = e.target.closest("[data-select-id]");
    if (selectBox) {
      const id = Number(selectBox.dataset.selectId);
      if (selectBox.checked) selectedPostIds.add(id);
      else selectedPostIds.delete(id);
      updateBulkBar();
      const card = selectBox.closest(".post-card");
      if (card) card.classList.toggle("selected", selectBox.checked);
      return;
    }

    const saintDateTrigger = e.target.closest("[data-open-saint-date]");
    if (saintDateTrigger) {
      openSaintModal(saintDateTrigger.dataset.openSaintDate);
      return;
    }

    const dispSingle = e.target.closest("[data-dispatch-single]");
    if (dispSingle) {
      triggerAction("/api/actions/dispatch", {}, dispSingle, `Item #${dispSingle.dataset.dispatchSingle} processado!`);
      return;
    }

    const removeQueueBtn = e.target.closest("[data-remove-queue]");
    if (removeQueueBtn) {
      const qId = removeQueueBtn.dataset.removeQueue;
      if (confirm(`Deseja retirar o item #${qId} da fila de publicação?`)) {
        triggerAction("/api/actions/queue-remove", { queue_id: qId }, removeQueueBtn, `Item #${qId} retirado da fila!`).then(() => {
          loadQueue();
          loadStats();
        });
      }
      return;
    }
  });

  // Bulk Bar Check All / Actions
  const bulkCheckAll = document.getElementById("bulk-check-all");
  if (bulkCheckAll) {
    bulkCheckAll.addEventListener("change", () => {
      if (!bulkCheckAll.checked) {
        selectedPostIds.clear();
        renderPosts();
      }
    });
  }

  const btnBulkRender = document.getElementById("btn-bulk-render");
  if (btnBulkRender) {
    btnBulkRender.addEventListener("click", () => {
      showToast(`Renderizando ${selectedPostIds.size} vídeos selecionados...`);
      selectedPostIds.forEach(pid => {
        triggerAction("/api/actions/media", { post_id: pid, make_video: true });
      });
    });
  }

  const btnBulkPublish = document.getElementById("btn-bulk-publish");
  if (btnBulkPublish) {
    btnBulkPublish.addEventListener("click", () => {
      showToast(`Publicando ${selectedPostIds.size} post(s) agora...`);
      selectedPostIds.forEach(pid => {
        triggerAction("/api/actions/publish-post", { post_id: pid });
      });
    });
  }

  // Drawer Action Buttons
  const modalBtnPublish = document.getElementById("modal-btn-publish");
  if (modalBtnPublish) {
    modalBtnPublish.addEventListener("click", () => {
      if (!selectedPost) return;
      closeDrawer();
      triggerAction("/api/actions/publish-post", { post_id: selectedPost.id }, null, `Post #${selectedPost.id} publicado!`);
    });
  }

  const modalBtnSchedule = document.getElementById("modal-btn-schedule");
  if (modalBtnSchedule) {
    modalBtnSchedule.addEventListener("click", () => {
      if (!selectedPost) return;
      const timeInput = document.getElementById("quick-schedule-time");
      const schedVal = timeInput ? timeInput.value : null;
      closeDrawer();
      triggerAction("/api/actions/schedule-post", { post_id: selectedPost.id, schedule_time: schedVal }, null, `Post #${selectedPost.id} agendado no Buffer!`);
    });
  }

  const modalBtnRegenerateVideo = document.getElementById("modal-btn-regenerate-video");
  if (modalBtnRegenerateVideo) {
    modalBtnRegenerateVideo.addEventListener("click", () => {
      if (!selectedPost) return;
      triggerAction("/api/actions/regenerate-video", { post_id: selectedPost.id }, modalBtnRegenerateVideo, `Vídeo e narração do post #${selectedPost.id} regerados!`);
    });
  }

  const modalBtnRegenerateFull = document.getElementById("modal-btn-regenerate-full");
  if (modalBtnRegenerateFull) {
    modalBtnRegenerateFull.addEventListener("click", () => {
      if (!selectedPost) return;
      if (!confirm("Regenerar todo o conteúdo deste tema, incluindo texto, mídia, narração e vídeo?")) return;
      triggerAction("/api/actions/regenerate-full", { post_id: selectedPost.id }, modalBtnRegenerateFull, `Conteúdo completo do post #${selectedPost.id} regenerado!`).then(() => loadPosts());
    });
  }

  // Quick Chips in Drawer
  document.getElementById("chip-q-today-2030")?.addEventListener("click", () => {
    document.getElementById("quick-schedule-time").value = formatDateTimeLocal(new Date(), 20, 30);
  });
  document.getElementById("chip-q-tomorrow-6am")?.addEventListener("click", () => {
    const tm = new Date(); tm.setDate(tm.getDate() + 1);
    document.getElementById("quick-schedule-time").value = formatDateTimeLocal(tm, 6, 0);
  });
  document.getElementById("chip-q-tomorrow-12pm")?.addEventListener("click", () => {
    const tm = new Date(); tm.setDate(tm.getDate() + 1);
    document.getElementById("quick-schedule-time").value = formatDateTimeLocal(tm, 12, 0);
  });

  // Modal Wizard Chips & Formats
  document.querySelectorAll("#wiz-type-selector .type-card").forEach(card => {
    card.addEventListener("click", () => {
      document.querySelectorAll("#wiz-type-selector .type-card").forEach(c => c.classList.remove("active"));
      card.classList.add("active");
    });
  });

  document.querySelectorAll(".format-card").forEach(card => {
    card.addEventListener("click", () => {
      document.querySelectorAll(".format-card").forEach(c => c.classList.remove("active"));
      card.classList.add("active");
      const radio = card.querySelector('input[type="radio"]');
      if (radio) radio.checked = true;
    });
  });

  document.getElementById("chip-saint-today")?.addEventListener("click", () => {
    const input = document.getElementById("saint-date-input");
    if (input) input.value = getTodayDateStr();
    setActiveChip("chip-saint-today", ["chip-saint-today", "chip-saint-tomorrow", "chip-saint-1012", "chip-saint-1013"]);
  });

  document.getElementById("chip-saint-tomorrow")?.addEventListener("click", () => {
    const input = document.getElementById("saint-date-input");
    if (input) input.value = getTomorrowDateStr();
    setActiveChip("chip-saint-tomorrow", ["chip-saint-today", "chip-saint-tomorrow", "chip-saint-1012", "chip-saint-1013"]);
  });

  document.getElementById("chip-saint-1012")?.addEventListener("click", () => {
    const yr = new Date().getFullYear();
    const input = document.getElementById("saint-date-input");
    if (input) input.value = `${yr}-10-12`;
    setActiveChip("chip-saint-1012", ["chip-saint-today", "chip-saint-tomorrow", "chip-saint-1012", "chip-saint-1013"]);
  });

  document.getElementById("chip-saint-1013")?.addEventListener("click", () => {
    const yr = new Date().getFullYear();
    const input = document.getElementById("saint-date-input");
    if (input) input.value = `${yr}-10-13`;
    setActiveChip("chip-saint-1013", ["chip-saint-today", "chip-saint-tomorrow", "chip-saint-1012", "chip-saint-1013"]);
  });

  document.getElementById("chip-sched-today-2030")?.addEventListener("click", () => {
    const input = document.getElementById("saint-schedule-time");
    if (input) input.value = formatDateTimeLocal(new Date(), 20, 30);
    setActiveChip("chip-sched-today-2030", ["chip-sched-today-2030", "chip-sched-tomorrow-6am", "chip-sched-tomorrow-12pm"]);
  });

  document.getElementById("chip-sched-tomorrow-6am")?.addEventListener("click", () => {
    const d = new Date(); d.setDate(d.getDate() + 1);
    const input = document.getElementById("saint-schedule-time");
    if (input) input.value = formatDateTimeLocal(d, 6, 0);
    setActiveChip("chip-sched-tomorrow-6am", ["chip-sched-today-2030", "chip-sched-tomorrow-6am", "chip-sched-tomorrow-12pm"]);
  });

  document.getElementById("chip-sched-tomorrow-12pm")?.addEventListener("click", () => {
    const d = new Date(); d.setDate(d.getDate() + 1);
    const input = document.getElementById("saint-schedule-time");
    if (input) input.value = formatDateTimeLocal(d, 12, 0);
    setActiveChip("chip-sched-tomorrow-12pm", ["chip-sched-today-2030", "chip-sched-tomorrow-6am", "chip-sched-tomorrow-12pm"]);
  });

  function setActiveChip(activeId, groupIds) {
    groupIds.forEach(id => {
      document.getElementById(id)?.classList.remove("active");
    });
    document.getElementById(activeId)?.classList.add("active");
  }

  // Calendar Prev / Next
  document.getElementById("btn-cal-prev")?.addEventListener("click", () => {
    calendarOffsetWeeks--;
    renderCalendar();
  });
  document.getElementById("btn-cal-next")?.addEventListener("click", () => {
    calendarOffsetWeeks++;
    renderCalendar();
  });

  // Refresh All
  async function refreshAll() {
    const btnSite = document.getElementById("btn-refresh-site");
    const btnAll = document.getElementById("btn-refresh-all");
    if (btnSite) btnSite.classList.add("spinning");
    if (btnAll) btnAll.classList.add("spinning");
    try {
      await Promise.all([
        loadStats(),
        loadPosts(),
        loadQueue(),
        loadSaintsCatalog(),
        loadLogs()
      ]);
      updateGreeting();
      showToast("Site e dados atualizados com sucesso!", "success");
    } catch (err) {
      console.warn("Erro ao atualizar dados do site:", err);
      showToast("Erro ao sincronizar dados com o servidor.", "error");
    } finally {
      if (btnSite) btnSite.classList.remove("spinning");
      if (btnAll) btnAll.classList.remove("spinning");
      refreshIcons();
    }
  }

  document.getElementById("btn-refresh-site")?.addEventListener("click", refreshAll);
  document.getElementById("btn-refresh-all")?.addEventListener("click", refreshAll);
  document.getElementById("btn-queue-refresh")?.addEventListener("click", loadQueue);
  document.getElementById("btn-queue-clear")?.addEventListener("click", async (e) => {
    if (!confirm("Deseja realmente remover da fila todos os posts pendentes que ainda não foram disparados?")) return;
    await triggerAction("/api/actions/queue-remove", { clear_all: true }, e.currentTarget, "Posts pendentes retirados da fila!");
    loadQueue();
    loadStats();
  });
  document.getElementById("btn-queue-dispatch")?.addEventListener("click", (e) => {
    triggerAction("/api/actions/dispatch", {}, e.target, "Fila disparada!");
  });
  document.getElementById("btn-refresh-logs")?.addEventListener("click", loadLogs);

  // Keyboard Shortcuts (Esc & Ctrl+K)
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeDrawer();
      closeSaintModal();
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      searchInput?.focus();
    }
  });

  // Init Calls
  updateGreeting();
  refreshIcons();
  checkAuthSession().then(isAuth => {
    if (isAuth) {
      loadStats();
      loadSaintsCatalog();
      loadPosts();
    }
  });
});
