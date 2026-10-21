// Bible Reels Studio — Frontend App Logic

document.addEventListener("DOMContentLoaded", () => {
  let currentPosts = [];
  let selectedPost = null;
  let currentFilter = "scriptures";

  // Elementos DOM
  const statVerses = document.getElementById("stat-verses");
  const statPosts = document.getElementById("stat-posts");
  const statPending = document.getElementById("stat-pending");
  const statSent = document.getElementById("stat-sent");
  const postsContainer = document.getElementById("posts-container");
  const queueTbody = document.getElementById("queue-tbody");
  const profilesContainer = document.getElementById("profiles-container");
  const logContent = document.getElementById("log-content");
  const toastContainer = document.getElementById("toast-container");

  // Filtros de Posts
  const countScriptures = document.getElementById("count-scriptures");
  const countSaints = document.getElementById("count-saints");
  const countAll = document.getElementById("count-all");
  const countUnpublished = document.getElementById("count-unpublished");
  const countPublished = document.getElementById("count-published");
  const filterStatusText = document.getElementById("filter-status-text");
  const filterPills = document.querySelectorAll(".filter-pill");

  // Modal
  const modal = document.getElementById("preview-modal");
  const modalClose = document.getElementById("modal-close-btn");
  const modalMediaSlot = document.getElementById("modal-media-slot");
  const modalReference = document.getElementById("modal-reference");
  const modalText = document.getElementById("modal-text");
  const modalHashtags = document.getElementById("modal-hashtags");
  const modalBtnPublish = document.getElementById("modal-btn-publish");

  // Abas
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabPanes = document.querySelectorAll(".tab-pane");

  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");
      tabBtns.forEach(b => b.classList.remove("active"));
      tabPanes.forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(targetTab).classList.add("active");

      if (targetTab === "tab-logs") loadLogs();
      if (targetTab === "tab-profiles") loadProfiles();
      if (targetTab === "tab-queue") loadQueue();
    });
  });

  // Alternador de Filtro de Posts (Todos / Não Publicados / Publicados)
  filterPills.forEach(pill => {
    pill.addEventListener("click", () => {
      filterPills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      currentFilter = pill.getAttribute("data-filter") || "all";
      renderPosts();
    });
  });

  // Modal fechar
  modalClose.addEventListener("click", () => {
    modal.classList.remove("active");
    modalMediaSlot.innerHTML = "";
  });

  modal.addEventListener("click", (e) => {
    if (e.target === modal) {
      modal.classList.remove("active");
      modalMediaSlot.innerHTML = "";
    }
  });

  // Notificações Toast
  function showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = "toast";
    const icon = type === "success" ? "✅" : type === "error" ? "❌" : "ℹ️";
    toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
    toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transition = "opacity 0.4s ease";
      setTimeout(() => toast.remove(), 400);
    }, 4000);
  }

  // ── Carregamento de Dados ──────────────────────────────────────

  async function loadStats() {
    try {
      const res = await fetch("/api/stats");
      const data = await res.json();
      statVerses.textContent = data.verses_count ?? 0;
      statPosts.textContent = data.posts_count ?? 0;
      statPending.textContent = data.queue_pending ?? 0;
      statSent.textContent = data.queue_sent ?? 0;

      const pubBadge = document.getElementById("postproxy-status");
        const pub = (data.default_publisher || "").toLowerCase();
        if (pub === "all" || pub === "multi") {
          pubBadge.innerHTML = `<span>🚀 Multi-Canal (Instagram + TikTok + YouTube)</span>`;
          pubBadge.style.background = "linear-gradient(135deg, rgba(236,72,153,0.2), rgba(16,185,129,0.2))";
          pubBadge.style.color = "#fff";
          pubBadge.style.borderColor = "rgba(236, 72, 153, 0.4)";
        } else if (pub.includes("instagram")) {
          pubBadge.innerHTML = `<span>📸 Instagram Direto (Instagrapi)</span>`;
          pubBadge.style.background = "rgba(236, 72, 153, 0.15)";
          pubBadge.style.color = "#f472b6";
          pubBadge.style.borderColor = "rgba(236, 72, 153, 0.3)";
        } else if (pub.includes("tiktok")) {
          pubBadge.innerHTML = `<span>🎵 TikTok Oficial (API v2)</span>`;
          pubBadge.style.background = "rgba(0, 242, 234, 0.15)";
          pubBadge.style.color = "#00f2fe";
          pubBadge.style.borderColor = "rgba(0, 242, 234, 0.4)";
        } else if (pub === "webhook") {
          pubBadge.innerHTML = `<span>⚡ n8n Webhook / Buffer</span>`;
          pubBadge.style.background = "rgba(16, 185, 129, 0.15)";
          pubBadge.style.color = "#34d399";
          pubBadge.style.borderColor = "rgba(16, 185, 129, 0.3)";
        } else {
          pubBadge.innerHTML = `<span>⚡ Postproxy Ativo</span>`;
          pubBadge.style.background = "rgba(245, 158, 11, 0.15)";
          pubBadge.style.color = "#fbbf24";
          pubBadge.style.borderColor = "rgba(245, 158, 11, 0.3)";
        }
    } catch (err) {
      console.error("Erro ao carregar estatísticas:", err);
    }
  }

  function updateFilterCounts() {
    if (!currentPosts) return;
    const total = currentPosts.length;
    const scriptures = currentPosts.filter(p => p.content_type === "scripture").length;
    const gospel = currentPosts.filter(p => p.content_type === "gospel").length;
    const saints = currentPosts.filter(p => p.content_type === "saint").length;
    const prayers = currentPosts.filter(p => p.content_type === "prayer").length;
    const community = currentPosts.filter(p => p.content_type === "community").length;
    const unpub = currentPosts.filter(p => p.status !== "published").length;
    const pub = currentPosts.filter(p => p.status === "published").length;

    const elScriptures = document.getElementById("count-scriptures");
    const elGospel = document.getElementById("count-gospel");
    const elSaints = document.getElementById("count-saints");
    const elPrayers = document.getElementById("count-prayers");
    const elCommunity = document.getElementById("count-community");
    const elAll = document.getElementById("count-all");
    const elUnpub = document.getElementById("count-unpublished");
    const elPub = document.getElementById("count-published");

    if (elScriptures) elScriptures.textContent = scriptures;
    if (elGospel) elGospel.textContent = gospel;
    if (elSaints) elSaints.textContent = saints;
    if (elPrayers) elPrayers.textContent = prayers;
    if (elCommunity) elCommunity.textContent = community;
    if (elAll) elAll.textContent = total;
    if (elUnpub) elUnpub.textContent = unpub;
    if (elPub) elPub.textContent = pub;
  }

  function renderPosts() {
    if (!currentPosts || currentPosts.length === 0) {
      postsContainer.innerHTML = `
        <div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 4rem;">
          <h3>Nenhum post gerado ainda</h3>
          <p style="margin-top: 0.5rem; font-size: 0.9rem;">Clique em "Executar Pipeline Completo" para coletar e renderizar conteúdos automaticamente.</p>
        </div>
      `;
      if (filterStatusText) filterStatusText.textContent = "Nenhum post disponível";
      return;
    }

    let filtered = currentPosts;
    if (currentFilter === "scriptures") {
      filtered = currentPosts.filter(p => p.content_type === "scripture");
      if (filterStatusText) filterStatusText.textContent = `Mostrando ${filtered.length} passagem(ns) da Escritura Sagrada`;
    } else if (currentFilter === "gospel") {
      filtered = currentPosts.filter(p => p.content_type === "gospel");
      if (filterStatusText) filterStatusText.textContent = `Mostrando ${filtered.length} Evangelho(s) do Dia`;
    } else if (currentFilter === "saints") {
      filtered = currentPosts.filter(p => p.content_type === "saint");
      if (filterStatusText) filterStatusText.textContent = `Mostrando ${filtered.length} post(s) do Santo do Dia`;
    } else if (currentFilter === "prayers") {
      filtered = currentPosts.filter(p => p.content_type === "prayer");
      if (filterStatusText) filterStatusText.textContent = `Mostrando ${filtered.length} Grande(s) Oração(ões) Clássica(s)`;
    } else if (currentFilter === "community") {
      filtered = currentPosts.filter(p => p.content_type === "community");
      if (filterStatusText) filterStatusText.textContent = `Mostrando ${filtered.length} Oração(ões) pelos Inscritos da Comunidade`;
    } else if (currentFilter === "unpublished") {
      filtered = currentPosts.filter(p => p.status !== "published");
      if (filterStatusText) filterStatusText.textContent = `Mostrando ${filtered.length} post(s) ainda não publicado(s)`;
    } else if (currentFilter === "published") {
      filtered = currentPosts.filter(p => p.status === "published");
      if (filterStatusText) filterStatusText.textContent = `Mostrando ${filtered.length} post(s) já publicado(s)`;
    } else {
      if (filterStatusText) filterStatusText.textContent = `Mostrando todos os ${currentPosts.length} posts`;
    }

    if (filtered.length === 0) {
      const msg = currentFilter === "scriptures"
        ? "Nenhuma passagem bíblica encontrada. Clique em 'Coletar Versos' para buscar as Escrituras."
        : currentFilter === "saints"
        ? "Nenhum post de Santo do Dia cadastrado."
        : currentFilter === "unpublished"
        ? "🎉 Todos os posts desta lista já foram publicados!"
        : currentFilter === "published"
        ? "Nenhum post publicado encontrado."
        : "Nenhum post encontrado.";
      postsContainer.innerHTML = `
        <div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 4rem;">
          <h3>${msg}</h3>
          <p style="margin-top: 0.5rem; font-size: 0.9rem;">Alterne para outra aba de filtro ou colete novos versículos para gerar mais posts.</p>
        </div>
      `;
      return;
    }

    postsContainer.innerHTML = filtered.map(post => {
      const hasVideo = Boolean(post.video_url);
      const hasMedia = Boolean(post.video_url || post.image_url);
      const isScheduled = post.scheduled_at && post.status !== "published";
      const badgeClass = post.status === "published" ? "badge-published" : post.status === "failed" ? "badge-failed" : isScheduled ? "badge-scheduled" : "badge-created";
      const badgeText = post.status === "published" ? "✓ Publicado" : post.status === "failed" ? "✗ Falha" : isScheduled ? "⏰ Agendado" : "Pronto";
      const isSaint = post.content_type === "saint";
      const isGospel = post.content_type === "gospel";
      const isPrayer = post.content_type === "prayer";
      const isCommunity = post.content_type === "community";

      let typeBadgeHtml = `<span style="position: absolute; top: 12px; left: 12px; font-size: 0.72rem; padding: 3px 8px; border-radius: 9999px; background: rgba(59, 130, 246, 0.9); color: #fff; font-weight: 700; z-index: 5; box-shadow: 0 2px 6px rgba(0,0,0,0.4);">📖 ESCRITURA</span>`;
      if (isSaint) {
        typeBadgeHtml = `<span style="position: absolute; top: 12px; left: 12px; font-size: 0.72rem; padding: 3px 8px; border-radius: 9999px; background: rgba(212, 175, 55, 0.9); color: #000; font-weight: 700; z-index: 5; box-shadow: 0 2px 6px rgba(0,0,0,0.4);">🕊️ SANTO DO DIA</span>`;
      } else if (isGospel) {
        typeBadgeHtml = `<span style="position: absolute; top: 12px; left: 12px; font-size: 0.72rem; padding: 3px 8px; border-radius: 9999px; background: rgba(56, 189, 248, 0.9); color: #000; font-weight: 700; z-index: 5; box-shadow: 0 2px 6px rgba(0,0,0,0.4);">📜 EVANGELHO</span>`;
      } else if (isPrayer) {
        typeBadgeHtml = `<span style="position: absolute; top: 12px; left: 12px; font-size: 0.72rem; padding: 3px 8px; border-radius: 9999px; background: rgba(168, 85, 247, 0.9); color: #fff; font-weight: 700; z-index: 5; box-shadow: 0 2px 6px rgba(0,0,0,0.4);">🙏 ORAÇÃO</span>`;
      } else if (isCommunity) {
        typeBadgeHtml = `<span style="position: absolute; top: 12px; left: 12px; font-size: 0.72rem; padding: 3px 8px; border-radius: 9999px; background: rgba(52, 211, 153, 0.9); color: #000; font-weight: 700; z-index: 5; box-shadow: 0 2px 6px rgba(0,0,0,0.4);">🤝 COMUNIDADE</span>`;
      }

      let mediaSlotHtml = "";
      if (post.is_carousel && post.video_url) {
        const slideCount = post.carousel_slides ? post.carousel_slides.length : 5;
        mediaSlotHtml = `
          <video src="${post.video_url}" muted loop playsinline onmouseover="this.play()" onmouseout="this.pause()"></video>
          <span class="badge-carousel" style="bottom: 34px;">📑 Carrossel (${slideCount} lâminas) - IG</span>
          <span class="badge-video">🎥 Vídeo MP4 - TT/YT</span>
        `;
      } else if (hasVideo) {
        mediaSlotHtml = `
          <video src="${post.video_url}" muted loop playsinline onmouseover="this.play()" onmouseout="this.pause()"></video>
          <span class="badge-video">▶ Vídeo MP4</span>
        `;
      } else if (post.is_carousel) {
        const slideCount = post.carousel_slides ? post.carousel_slides.length : 5;
        mediaSlotHtml = `
          <img src="${post.image_url}" alt="Post #${post.id}" loading="lazy">
          <span class="badge-carousel">📑 Carrossel (${slideCount} lâminas)</span>
        `;
      } else if (post.image_url) {
        mediaSlotHtml = `<img src="${post.image_url}" alt="Post #${post.id}" loading="lazy">`;
      } else {
        mediaSlotHtml = `
          <div class="media-placeholder">
            <span style="font-size: 2rem;">🖼️</span>
            <span>Aguardando Mídia</span>
          </div>
        `;
      }

      const tagsHtml = (post.hashtags || []).slice(0, 4).map(t => `<span class="tag">#${t}</span>`).join("");

      return `
        <div class="post-card" data-id="${post.id}">
          <div class="media-container" onclick="openPreview(${post.id})">
            ${typeBadgeHtml}
            ${mediaSlotHtml}
            <span class="card-badge ${badgeClass}">${badgeText}</span>
          </div>
          <div class="post-content">
            <div class="post-ref">${escapeHtml(post.reference || "Reflexão")}</div>
            <div class="post-text">${escapeHtml(post.formatted_text || post.original_text || "")}</div>
            <div class="post-tags">${tagsHtml}</div>
            <div class="post-footer">
              <span class="post-date">Post #${post.id}</span>
              <div style="display: flex; gap: 0.35rem; flex-wrap: wrap;">
                <button class="btn btn-secondary" style="padding: 0.35rem 0.6rem; font-size: 0.75rem;" onclick="renderPostDirect(event, ${post.id})" title="Gerar Vídeo MP4">
                  🎬 ${hasVideo ? "Regerar" : "Vídeo"}
                </button>
                <button class="btn btn-secondary" style="padding: 0.35rem 0.65rem; font-size: 0.75rem; border-color: rgba(139, 92, 246, 0.4);" onclick="openQuickSchedule(${post.id})" title="Agendar Horário no Buffer">
                  ⏰ Agendar
                </button>
                <button class="btn btn-secondary" style="padding: 0.35rem 0.65rem; font-size: 0.75rem;" onclick="publishPostDirect(${post.id})">
                  🚀 Postar
                </button>
              </div>
            </div>
          </div>
        </div>
      `;
    }).join("");
  }

  async function loadPosts() {
    try {
      postsContainer.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 3rem;">Carregando posts...</div>`;
      const res = await fetch("/api/posts?limit=100");
      currentPosts = await res.json();
      updateFilterCounts();
      renderPosts();
    } catch (err) {
      postsContainer.innerHTML = `<div style="grid-column: 1/-1; color: var(--accent-rose);">Erro ao carregar posts: ${err}</div>`;
    }
  }

  async function loadQueue() {
    try {
      const res = await fetch("/api/queue?limit=50");
      const queue = await res.json();
      if (!queue || queue.length === 0) {
        queueTbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">Nenhum item na fila</td></tr>`;
        return;
      }

      queueTbody.innerHTML = queue.map(q => {
        const badgeColor = q.status === "sent" ? "var(--accent-emerald)" : q.status === "failed" ? "var(--accent-rose)" : "var(--accent-amber)";
        return `
          <tr>
            <td>#${q.id}</td>
            <td><strong>${escapeHtml(q.reference || "")}</strong></td>
            <td><span style="text-transform: uppercase; font-weight: 600;">${q.platform}</span></td>
            <td><span style="color: ${badgeColor}; font-weight: 700;">● ${q.status.toUpperCase()}</span></td>
            <td>${q.attempts}</td>
            <td>${formatDate(q.queued_at)}</td>
            <td>${q.sent_at ? formatDate(q.sent_at) : "—"}</td>
          </tr>
        `;
      }).join("");
    } catch (err) {
      console.error("Erro ao carregar fila:", err);
    }
  }

  async function loadProfiles() {
    try {
      profilesContainer.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted);">Consultando API do Postproxy...</div>`;
      const res = await fetch("/api/profiles");
      const profiles = await res.json();

      if (!profiles || profiles.length === 0 || profiles.error) {
        profilesContainer.innerHTML = `
          <div style="grid-column: 1/-1; color: var(--accent-rose); background: rgba(244,63,94,0.1); padding: 1.5rem; border-radius: 8px;">
            ${profiles.error || "Nenhum perfil conectado retornado pela API."}
          </div>
        `;
        return;
      }

      profilesContainer.innerHTML = profiles.map(p => {
        const pid = p.id || p.accountId || "ID não especificado";
        const name = p.name || p.username || "Canal Conectado";
        const platform = (p.platform || p.type || "social").toUpperCase();
        const icon = platform.includes("INSTAGRAM") ? "📸" : platform.includes("TIKTOK") ? "🎵" : platform.includes("YOUTUBE") ? "▶️" : "🌐";

        return `
          <div class="stat-card purple" style="flex-direction: column; align-items: flex-start; gap: 0.75rem;">
            <div style="display: flex; align-items: center; justify-content: space-between; width: 100%;">
              <div class="stat-icon-wrap" style="width: 36px; height: 36px; font-size: 1.1rem;">${icon}</div>
              <span class="status-badge" style="background: rgba(139,92,246,0.2); color: #c4b5fd;">${platform}</span>
            </div>
            <div>
              <div style="font-weight: 700; font-size: 1.1rem; color: #fff;">${escapeHtml(name)}</div>
              <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.2rem;">ID Postproxy: <code>${pid}</code></div>
            </div>
          </div>
        `;
      }).join("");
    } catch (err) {
      profilesContainer.innerHTML = `<div style="grid-column: 1/-1; color: var(--accent-rose);">Erro ao consultar perfis: ${err}</div>`;
    }
  }

  async function loadLogs() {
    try {
      const res = await fetch("/api/logs");
      const data = await res.json();
      logContent.textContent = (data.lines || []).join("") || "Nenhum registro de log encontrado.";
      logContent.scrollTop = logContent.scrollHeight;
    } catch (err) {
      logContent.textContent = `Erro ao carregar logs: ${err}`;
    }
  }

  // ── Modal de Visualização ──────────────────────────────────────

  let currentSlideIdx = 0;
  window.renderCarouselViewer = function(slides, audioUrl) {
    const count = slides.length;
    const audioBarHtml = audioUrl ? `
      <div class="carousel-audio-bar" style="margin-top: 10px; width: 100%; max-width: 480px; display: flex; flex-direction: column; align-items: center; gap: 6px; background: rgba(0,0,0,0.6); padding: 8px 14px; border-radius: 12px; border: 1px solid rgba(212, 175, 55, 0.4);">
        <div style="font-size: 0.8rem; color: #d4af37; font-weight: 600; display: flex; align-items: center; gap: 6px;">
          <span>🎵 Trilha Sacra & Narração do Carrossel</span>
        </div>
        <audio id="carousel-audio-player" src="${audioUrl}" controls preload="metadata" style="width: 100%; height: 32px;"></audio>
      </div>
    ` : '';

    modalMediaSlot.innerHTML = `
      <div class="carousel-viewer">
        <div class="carousel-stage">
          <button class="carousel-nav-btn prev" onclick="changePreviewSlide(-1)">❮</button>
          <img id="carousel-current-img" src="${slides[0]}" alt="Slide 1">
          <button class="carousel-nav-btn next" onclick="changePreviewSlide(1)">❯</button>
        </div>
        <div class="carousel-slide-counter" id="carousel-counter">Slide 1 de ${count}</div>
        <div class="carousel-indicators">
          ${slides.map((_, i) => `<span class="carousel-indicator-dot ${i === 0 ? 'active' : ''}" onclick="goToPreviewSlide(${i})"></span>`).join('')}
        </div>
        ${audioBarHtml}
      </div>
    `;
    window.currentCarouselSlides = slides;
    currentSlideIdx = 0;
  };

  window.changePreviewSlide = function(delta) {
    const slides = window.currentCarouselSlides;
    if (!slides || slides.length === 0) return;
    currentSlideIdx = (currentSlideIdx + delta + slides.length) % slides.length;
    updateCarouselView();
  };

  window.goToPreviewSlide = function(idx) {
    const slides = window.currentCarouselSlides;
    if (!slides || !slides[idx]) return;
    currentSlideIdx = idx;
    updateCarouselView();
  };

  function updateCarouselView() {
    const slides = window.currentCarouselSlides;
    const img = document.getElementById("carousel-current-img");
    const counter = document.getElementById("carousel-counter");
    const dots = document.querySelectorAll(".carousel-indicator-dot");
    if (img) img.src = slides[currentSlideIdx];
    if (counter) counter.textContent = `Slide ${currentSlideIdx + 1} de ${slides.length}`;
    dots.forEach((d, i) => {
      if (i === currentSlideIdx) d.classList.add("active");
      else d.classList.remove("active");
    });
  }

  window.openPreview = function(postId) {
    const post = currentPosts.find(p => p.id === postId);
    if (!post) return;
    selectedPost = post;

    modalReference.textContent = post.reference || `Post #${post.id}`;
    modalText.textContent = post.caption || post.formatted_text || post.original_text || "";
    modalHashtags.innerHTML = (post.hashtags || []).map(t => `<span class="tag">#${t}</span>`).join("");

    if (post.is_carousel && post.video_url && post.carousel_slides && post.carousel_slides.length > 0) {
      modalMediaSlot.innerHTML = `
        <div class="modal-media-switcher-wrap" style="width: 100%; display: flex; flex-direction: column; align-items: center; gap: 0.75rem; padding: 1rem 0;">
          <div class="media-tabs" style="display: flex; gap: 0.5rem; background: rgba(0,0,0,0.5); padding: 4px; border-radius: 9999px; border: 1px solid var(--border-subtle);">
            <button id="btn-tab-carousel" class="filter-pill active" onclick="switchModalMedia('carousel')">📑 Carrossel (Instagram)</button>
            <button id="btn-tab-video" class="filter-pill" onclick="switchModalMedia('video')">🎥 Vídeo (TikTok & YT)</button>
          </div>
          <div id="modal-switcher-content" style="width: 100%; display: flex; justify-content: center;"></div>
        </div>
      `;
      window.switchModalMedia = function(type) {
        const cTab = document.getElementById("btn-tab-carousel");
        const vTab = document.getElementById("btn-tab-video");
        const container = document.getElementById("modal-switcher-content");
        if (!container) return;
        if (type === "carousel") {
          cTab?.classList.add("active");
          vTab?.classList.remove("active");
          const audioBarHtml = post.carousel_audio_url ? `
            <div class="carousel-audio-bar" style="margin-top: 10px; width: 100%; max-width: 480px; display: flex; flex-direction: column; align-items: center; gap: 6px; background: rgba(0,0,0,0.6); padding: 8px 14px; border-radius: 12px; border: 1px solid rgba(212, 175, 55, 0.4);">
              <div style="font-size: 0.8rem; color: #d4af37; font-weight: 600; display: flex; align-items: center; gap: 6px;">
                <span>🎵 Trilha Sacra & Narração do Carrossel</span>
              </div>
              <audio id="carousel-audio-player" src="${post.carousel_audio_url}" controls preload="metadata" style="width: 100%; height: 32px;"></audio>
            </div>
          ` : '';

          container.innerHTML = `
            <div class="carousel-viewer">
              <div class="carousel-stage">
                <button class="carousel-nav-btn prev" onclick="changePreviewSlide(-1)">❮</button>
                <img id="carousel-current-img" src="${post.carousel_slides[0]}" alt="Slide 1">
                <button class="carousel-nav-btn next" onclick="changePreviewSlide(1)">❯</button>
              </div>
              <div class="carousel-slide-counter" id="carousel-counter">Slide 1 de ${post.carousel_slides.length}</div>
              <div class="carousel-indicators">
                ${post.carousel_slides.map((_, i) => `<span class="carousel-indicator-dot ${i === 0 ? 'active' : ''}" onclick="goToPreviewSlide(${i})"></span>`).join('')}
              </div>
              ${audioBarHtml}
            </div>
          `;
          window.currentCarouselSlides = post.carousel_slides;
          currentSlideIdx = 0;
        } else {
          vTab?.classList.add("active");
          cTab?.classList.remove("active");
          const vUrl = post.video_url.includes('?') ? post.video_url : `${post.video_url}?v=${Date.now()}`;
          container.innerHTML = `<video src="${vUrl}" controls autoplay playsinline style="max-height: 75vh; max-width: 100%; border-radius: 8px;"></video>`;
        }
      };
      window.switchModalMedia("video");
    } else if (post.is_carousel && post.carousel_slides && post.carousel_slides.length > 0) {
      window.renderCarouselViewer(post.carousel_slides, post.carousel_audio_url);
    } else if (post.video_url) {
      modalMediaSlot.innerHTML = `<video src="${post.video_url}" controls autoplay style="max-height: 80vh; max-width: 100%; border-radius: 8px;"></video>`;
    } else if (post.image_url) {
      modalMediaSlot.innerHTML = `<img src="${post.image_url}" alt="Post #${post.id}" style="max-height: 80vh; max-width: 100%; border-radius: 8px;">`;
    } else {
      modalMediaSlot.innerHTML = `<div style="color: var(--text-muted);">Sem mídia gerada para este post.</div>`;
    }

    modal.classList.add("active");
  };

  // ── Ações em Lote e Diretas ────────────────────────────────────

  window.renderPostDirect = async function(e, postId) {
    if (e) e.stopPropagation();
    const btn = e?.currentTarget;
    await triggerAction("/api/actions/media", { post_id: postId, make_video: true }, btn, `Vídeo do Post #${postId} renderizado com sucesso!`);
  };

  window.publishPostDirect = async function(postId) {
    if (!confirm(`Deseja disparar a publicação do post #${postId} agora?`)) return;
    showToast(`Disparando post #${postId} para publicação...`, "info");
    try {
      const res = await fetch("/api/actions/publish-post", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ post_id: postId })
      });
      const data = await res.json();
      if (data.success) {
        showToast(data.message || "Publicado com sucesso!", "success");
        refreshAll();
      } else {
        showToast(data.error || "Falha ao publicar post.", "error");
      }
    } catch (err) {
      showToast(`Erro na requisição: ${err}`, "error");
    }
  };

  modalBtnPublish.addEventListener("click", () => {
    if (selectedPost) {
      publishPostDirect(selectedPost.id);
      modal.classList.remove("active");
    }
  });

  const modalBtnSchedule = document.getElementById("modal-btn-schedule");
  if (modalBtnSchedule) {
    modalBtnSchedule.addEventListener("click", () => {
      if (selectedPost) {
        modal.classList.remove("active");
        openQuickSchedule(selectedPost.id);
      }
    });
  }

  // ── Modal Santo do Dia & Agendamento ───────────────────────
  const saintModal = document.getElementById("saint-modal");
  const saintModalClose = document.getElementById("saint-modal-close-btn");
  const saintModalCancel = document.getElementById("saint-modal-cancel");
  const saintModalSubmit = document.getElementById("saint-modal-submit");
  const saintDateInput = document.getElementById("saint-date-input");
  const saintVideoCheckbox = document.getElementById("saint-video-checkbox");
  const saintScheduleCheckbox = document.getElementById("saint-schedule-checkbox");
  const saintSchedulePanel = document.getElementById("saint-schedule-panel");
  const saintScheduleTime = document.getElementById("saint-schedule-time");

  function getTomorrowDateStr() {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return d.toISOString().split("T")[0];
  }

  function getTodayDateStr() {
    return new Date().toISOString().split("T")[0];
  }

  function formatDateTimeLocal(d, hour = 6, minute = 0) {
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const hh = String(hour).padStart(2, "0");
    const mm = String(minute).padStart(2, "0");
    return `${year}-${month}-${day}T${hh}:${mm}`;
  }

  let selectedSaintFormat = "carousel";

  function setupFormatCards() {
    const formatCards = document.querySelectorAll(".format-card");
    formatCards.forEach(card => {
      card.addEventListener("click", () => {
        formatCards.forEach(c => c.classList.remove("active"));
        card.classList.add("active");
        const radio = card.querySelector('input[type="radio"]');
        if (radio) {
          radio.checked = true;
          selectedSaintFormat = radio.value;
        }
      });
    });
  }
  setupFormatCards();

  function initSaintModalDefaults() {
    const tomorrowStr = getTomorrowDateStr();
    saintDateInput.value = tomorrowStr;

    // Véspera do santo: padrão é hoje às 20:30!
    const dEve = new Date();
    saintScheduleTime.value = formatDateTimeLocal(dEve, 20, 30);

    selectedSaintFormat = "video";
    document.querySelectorAll(".format-card").forEach(c => c.classList.remove("active"));
    document.getElementById("format-card-video")?.classList.add("active");
    const videoRadio = document.querySelector('input[name="saint-format"][value="video"]');
    if (videoRadio) videoRadio.checked = true;

    if (saintScheduleCheckbox) saintScheduleCheckbox.checked = true;
    if (saintSchedulePanel) saintSchedulePanel.style.display = "flex";
  }

  if (saintScheduleCheckbox) {
    saintScheduleCheckbox.addEventListener("change", (e) => {
      saintSchedulePanel.style.display = e.target.checked ? "flex" : "none";
    });
  }

  // Chips de Data do Santo
  document.getElementById("chip-saint-today")?.addEventListener("click", () => {
    saintDateInput.value = getTodayDateStr();
    setActiveChip("chip-saint-today", ["chip-saint-today", "chip-saint-tomorrow", "chip-saint-1012", "chip-saint-1013"]);
  });

  document.getElementById("chip-saint-tomorrow")?.addEventListener("click", () => {
    saintDateInput.value = getTomorrowDateStr();
    setActiveChip("chip-saint-tomorrow", ["chip-saint-today", "chip-saint-tomorrow", "chip-saint-1012", "chip-saint-1013"]);
  });

  document.getElementById("chip-saint-1012")?.addEventListener("click", () => {
    const yr = new Date().getFullYear();
    saintDateInput.value = `${yr}-10-12`;
    setActiveChip("chip-saint-1012", ["chip-saint-today", "chip-saint-tomorrow", "chip-saint-1012", "chip-saint-1013"]);
  });

  document.getElementById("chip-saint-1013")?.addEventListener("click", () => {
    const yr = new Date().getFullYear();
    saintDateInput.value = `${yr}-10-13`;
    setActiveChip("chip-saint-1013", ["chip-saint-today", "chip-saint-tomorrow", "chip-saint-1012", "chip-saint-1013"]);
  });

  // Chips de Horário de Disparo
  document.getElementById("chip-sched-today-2030")?.addEventListener("click", () => {
    const d = new Date();
    saintScheduleTime.value = formatDateTimeLocal(d, 20, 30);
    setActiveChip("chip-sched-today-2030", ["chip-sched-today-2030", "chip-sched-tomorrow-6am", "chip-sched-tomorrow-12pm"]);
  });

  document.getElementById("chip-sched-tomorrow-6am")?.addEventListener("click", () => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    saintScheduleTime.value = formatDateTimeLocal(d, 6, 0);
    setActiveChip("chip-sched-tomorrow-6am", ["chip-sched-today-2030", "chip-sched-tomorrow-6am", "chip-sched-tomorrow-12pm"]);
  });

  document.getElementById("chip-sched-tomorrow-12pm")?.addEventListener("click", () => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    saintScheduleTime.value = formatDateTimeLocal(d, 12, 0);
    setActiveChip("chip-sched-tomorrow-12pm", ["chip-sched-today-2030", "chip-sched-tomorrow-6am", "chip-sched-tomorrow-12pm"]);
  });

  function setActiveChip(activeId, groupIds) {
    groupIds.forEach(id => {
      document.getElementById(id)?.classList.remove("active");
    });
    document.getElementById(activeId)?.classList.add("active");
  }

  function closeSaintModal() {
    saintModal?.classList.remove("active");
  }

  saintModalClose?.addEventListener("click", closeSaintModal);
  saintModalCancel?.addEventListener("click", closeSaintModal);
  saintModal?.addEventListener("click", (e) => {
    if (e.target === saintModal) closeSaintModal();
  });

  saintModalSubmit?.addEventListener("click", async () => {
    const targetDate = saintDateInput.value;
    if (!targetDate) {
      showToast("Por favor, selecione a data litúrgica do santo.", "error");
      return;
    }

    const autoSchedule = saintScheduleCheckbox ? saintScheduleCheckbox.checked : false;
    const scheduleTime = autoSchedule ? saintScheduleTime.value : null;

    saintModalSubmit.disabled = true;
    saintModalSubmit.classList.add("loading");
    showToast(`Iniciando geração do Santo de ${targetDate} (${selectedSaintFormat})...`, "info");

    try {
      const res = await fetch("/api/actions/saint", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_date: targetDate,
          format: selectedSaintFormat,
          make_video: selectedSaintFormat === "video",
          schedule_time: scheduleTime,
          auto_publish: autoSchedule
        })
      });
      const data = await res.json();
      if (data.success) {
        showToast(data.message || `Post do Santo (${data.saint_name}) gerado com sucesso!`, "success");
        closeSaintModal();
        refreshAll();
      } else {
        showToast(data.error || "Erro ao gerar post do Santo.", "error");
      }
    } catch (err) {
      showToast(`Erro na requisição: ${err}`, "error");
    } finally {
      saintModalSubmit.disabled = false;
      saintModalSubmit.classList.remove("loading");
    }
  });

  // ── Modal Agendamento Rápido de Post Existente ─────────────
  const quickScheduleModal = document.getElementById("quick-schedule-modal");
  const quickScheduleClose = document.getElementById("quick-schedule-close-btn");
  const quickScheduleCancel = document.getElementById("quick-schedule-cancel");
  const quickScheduleSubmit = document.getElementById("quick-schedule-submit");
  const quickScheduleTimeInput = document.getElementById("quick-schedule-time-input");
  const quickScheduleLabel = document.getElementById("quick-schedule-post-label");
  let quickScheduleTargetPostId = null;

  window.openQuickSchedule = function(postId) {
    quickScheduleTargetPostId = postId;
    const post = currentPosts.find(p => p.id === postId);
    if (quickScheduleLabel) {
      const ref = post?.reference || `Post #${postId}`;
      quickScheduleLabel.textContent = `Selecione o horário para agendar o post: "${ref}"`;
    }

    const d = new Date();
    quickScheduleTimeInput.value = formatDateTimeLocal(d, 20, 30);

    quickScheduleModal?.classList.add("active");
  };

  function closeQuickSchedule() {
    quickScheduleModal?.classList.remove("active");
    quickScheduleTargetPostId = null;
  }

  quickScheduleClose?.addEventListener("click", closeQuickSchedule);
  quickScheduleCancel?.addEventListener("click", closeQuickSchedule);
  quickScheduleModal?.addEventListener("click", (e) => {
    if (e.target === quickScheduleModal) closeQuickSchedule();
  });

  document.getElementById("chip-quick-today-2030")?.addEventListener("click", () => {
    const d = new Date();
    quickScheduleTimeInput.value = formatDateTimeLocal(d, 20, 30);
    setActiveChip("chip-quick-today-2030", ["chip-quick-today-2030", "chip-quick-tomorrow-6am", "chip-quick-today-6pm"]);
  });

  document.getElementById("chip-quick-tomorrow-6am")?.addEventListener("click", () => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    quickScheduleTimeInput.value = formatDateTimeLocal(d, 6, 0);
    setActiveChip("chip-quick-tomorrow-6am", ["chip-quick-today-2030", "chip-quick-tomorrow-6am", "chip-quick-today-6pm"]);
  });

  document.getElementById("chip-quick-today-6pm")?.addEventListener("click", () => {
    const d = new Date();
    quickScheduleTimeInput.value = formatDateTimeLocal(d, 18, 0);
    setActiveChip("chip-quick-today-6pm", ["chip-quick-today-2030", "chip-quick-tomorrow-6am", "chip-quick-today-6pm"]);
  });

  quickScheduleSubmit?.addEventListener("click", async () => {
    if (!quickScheduleTargetPostId) return;
    const scheduleTime = quickScheduleTimeInput.value;
    if (!scheduleTime) {
      showToast("Informe a data e o horário para o agendamento.", "error");
      return;
    }

    quickScheduleSubmit.disabled = true;
    quickScheduleSubmit.classList.add("loading");
    showToast(`Agendando post #${quickScheduleTargetPostId} no Buffer...`, "info");

    try {
      const res = await fetch("/api/actions/schedule-post", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          post_id: quickScheduleTargetPostId,
          schedule_time: scheduleTime
        })
      });
      const data = await res.json();
      if (data.success) {
        showToast(data.message || "Post agendado no Buffer com sucesso!", "success");
        closeQuickSchedule();
        refreshAll();
      } else {
        showToast(data.error || "Falha ao agendar post.", "error");
      }
    } catch (err) {
      showToast(`Erro na requisição: ${err}`, "error");
    } finally {
      quickScheduleSubmit.disabled = false;
      quickScheduleSubmit.classList.remove("loading");
    }
  });

  async function triggerAction(actionUrl, payload = {}, btnElement = null, successMsg = "") {
    if (btnElement) {
      btnElement.disabled = true;
      btnElement.classList.add("loading");
    }
    showToast("Executando automação em segundo plano...", "info");

    try {
      const res = await fetch(actionUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) {
        showToast(successMsg || data.message || "Ação concluída com sucesso!", "success");
        refreshAll();
      } else {
        showToast(data.error || "Ação retornou erro.", "error");
      }
    } catch (err) {
      showToast(`Falha ao executar ação: ${err}`, "error");
    } finally {
      if (btnElement) {
        btnElement.disabled = false;
        btnElement.classList.remove("loading");
      }
    }
  }

  // Botões de Ação
  document.getElementById("btn-refresh").addEventListener("click", refreshAll);
  document.getElementById("btn-refresh-logs").addEventListener("click", loadLogs);

  document.getElementById("btn-action-collect")?.addEventListener("click", function() {
    triggerAction("/api/actions/collect", { source: "both", count: 1, full_pipeline: true }, this, "Verso coletado, formatado com IA e vídeo final renderizado!");
  });

  document.getElementById("btn-action-gospel")?.addEventListener("click", function() {
    triggerAction("/api/actions/collect", { source: "gospel", count: 1, full_pipeline: true }, this, "Evangelho do Dia: coleta, IA e vídeo completo renderizados!");
  });

  const btnSaint = document.getElementById("btn-action-saint");
  if (btnSaint) {
    btnSaint.addEventListener("click", function() {
      initSaintModalDefaults();
      saintModal?.classList.add("active");
    });
  }

  document.getElementById("btn-action-prayer")?.addEventListener("click", function() {
    triggerAction("/api/actions/collect", { source: "prayer", count: 1, full_pipeline: true }, this, "Oração Clássica: coleta, IA e vídeo completo renderizados!");
  });

  document.getElementById("btn-action-community")?.addEventListener("click", function() {
    triggerAction("/api/actions/collect", { source: "community", count: 1, full_pipeline: true }, this, "Oração dos Inscritos: gerada, formatada com IA e vídeo renderizado!");
  });

  document.getElementById("btn-action-process").addEventListener("click", function() {
    triggerAction("/api/actions/process", { limit: 3 }, this, "Versículos formatados com IA!");
  });

  document.getElementById("btn-action-media-img").addEventListener("click", function() {
    triggerAction("/api/actions/media", { limit: 3, make_video: false }, this, "Imagens 9:16 geradas com sucesso!");
  });

  document.getElementById("btn-action-media-vid").addEventListener("click", function() {
    triggerAction("/api/actions/media", { limit: 3, make_video: true }, this, "Vídeos MP4 renderizados com sucesso!");
  });

  document.getElementById("btn-action-dispatch").addEventListener("click", function() {
    triggerAction("/api/actions/dispatch", {}, this, "Fila disparada para o Postproxy!");
  });

  document.getElementById("btn-action-full").addEventListener("click", async function() {
    if (!confirm("Deseja executar o pipeline completo (Coleta -> IA -> Mídia -> Fila)?")) return;
    this.disabled = true;
    showToast("Iniciando pipeline completo...", "info");
    await triggerAction("/api/actions/collect", { source: "both", count: 3 });
    await triggerAction("/api/actions/process", { limit: 3 });
    await triggerAction("/api/actions/media", { limit: 3, make_video: false });
    this.disabled = false;
    showToast("Pipeline completo finalizado com sucesso!", "success");
    refreshAll();
  });

  function refreshAll() {
    loadStats();
    loadPosts();
    loadQueue();
  }

  function escapeHtml(text) {
    if (!text) return "";
    return text.replace(/[&<>"']/g, m => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;"
    })[m]);
  }

  function formatDate(isoStr) {
    if (!isoStr) return "";
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString("pt-BR") + " " + d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    } catch {
      return isoStr;
    }
  }

  // Inicializa
  refreshAll();
});
