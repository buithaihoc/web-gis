/**
 * HANOI SATELLITE WEBGIS — app.js v3
 *
 * Kiến trúc 2-panel:
 * - Panel trái (Kho ảnh R2): catalog, filter, hiển thị, xuất
 * - Panel phải (Thông tin & Tải ảnh): lớp bản đồ + download workflow
 *
 * Download workflow: Form → Search → Preview/Confirm → Download → Progress → Done
 */

document.addEventListener("DOMContentLoaded", () => {

  // ═══════════════════════════════════════════════════════════════════
  // 1. KHỞI TẠO MAP
  // ═══════════════════════════════════════════════════════════════════

  const HANOI_COORDS    = [105.8342, 21.0278];
  const HANOI_CENTER    = ol.proj.fromLonLat(HANOI_COORDS);
  const PANEL_W         = 290;

  const basemapSources = {
    dark: new ol.source.XYZ({
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      maxZoom: 18,
    }),
    osm: new ol.source.OSM(),
    satellite: new ol.source.XYZ({
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      maxZoom: 19,
    }),
  };

  const basemapLayer = new ol.layer.Tile({ source: basemapSources.dark, zIndex: 1 });

  const satelliteLayer = new ol.layer.Tile({
    source: null,
    opacity: 1.0,
    zIndex: 5,
    visible: true,
  });

  const boundaryLayer = new ol.layer.Vector({
    source: new ol.source.Vector({
      url: "/api/imagery/boundary",
      format: new ol.format.GeoJSON(),
    }),
    style: new ol.style.Style({
      stroke: new ol.style.Stroke({ color: "#38bdf8", width: 2, lineDash: [4, 4] }),
      fill:   new ol.style.Fill({ color: "rgba(56,189,248,0.03)" }),
    }),
    zIndex: 10,
  });

  const map = new ol.Map({
    target: "map-container",
    layers: [basemapLayer, satelliteLayer, boundaryLayer],
    view: new ol.View({ center: HANOI_CENTER, zoom: 10.2, minZoom: 7, maxZoom: 18 }),
    controls: ol.control.defaults.defaults({ zoom: false, rotate: false, attribution: false }),
  });

  // Coordinate bar
  const coordBar = document.getElementById("coordinate-bar");
  map.on("pointermove", (e) => {
    const [lng, lat] = ol.proj.toLonLat(e.coordinate);
    const z = Math.round(map.getView().getZoom());
    coordBar.textContent = `${lng.toFixed(4)}°E  ${lat.toFixed(4)}°N · Zoom ${z}`;
  });

  // ═══════════════════════════════════════════════════════════════════
  // 2. PANEL TOGGLE
  // ═══════════════════════════════════════════════════════════════════

  const panelLeft     = document.getElementById("panel-left");
  const panelRight    = document.getElementById("panel-right");
  const toggleLeft    = document.getElementById("toggle-left");
  const toggleRight   = document.getElementById("toggle-right");
  const toggleLeftIco = document.getElementById("toggle-left-icon");
  const toggleRightIco= document.getElementById("toggle-right-icon");

  const workspace = document.querySelector(".workspace");

  function collapseLeft(collapsed) {
    panelLeft.classList.toggle("collapsed", collapsed);
    workspace.classList.toggle("left-collapsed", collapsed);
    toggleLeftIco.setAttribute("data-lucide", collapsed ? "chevron-right" : "chevron-left");
    lucide.createIcons();
    setTimeout(() => map.updateSize(), 340);
  }

  function collapseRight(collapsed) {
    panelRight.classList.toggle("collapsed", collapsed);
    workspace.classList.toggle("right-collapsed", collapsed);
    toggleRightIco.setAttribute("data-lucide", collapsed ? "chevron-left" : "chevron-right");
    lucide.createIcons();
    setTimeout(() => map.updateSize(), 340);
  }


  toggleLeft.addEventListener("click", () => collapseLeft(!panelLeft.classList.contains("collapsed")));
  toggleRight.addEventListener("click", () => collapseRight(!panelRight.classList.contains("collapsed")));

  // ═══════════════════════════════════════════════════════════════════
  // 3. MAP CONTROLS
  // ═══════════════════════════════════════════════════════════════════

  document.getElementById("btn-reset-view").addEventListener("click", () => {
    map.getView().animate({ center: HANOI_CENTER, zoom: 10.2, duration: 700 });
  });

  document.getElementById("btn-fullscreen").addEventListener("click", () => {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen();
    else document.exitFullscreen();
  });

  // ═══════════════════════════════════════════════════════════════════
  // 4. RIGHT PANEL — TABS
  // ═══════════════════════════════════════════════════════════════════

  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.toggle("active", b.dataset.tab === tab));
      document.querySelectorAll(".tab-pane").forEach(p => p.classList.toggle("active", p.id === `tab-${tab}`));
    });
  });

  // ═══════════════════════════════════════════════════════════════════
  // 5. RIGHT PANEL — DISPLAY SETTINGS
  // ═══════════════════════════════════════════════════════════════════

  let currentProductType = "rgb";

  // Mode buttons
  const modeRgb  = document.getElementById("mode-rgb");
  const modeNdvi = document.getElementById("mode-ndvi");

  function setMode(mode) {
    currentProductType = mode;
    modeRgb.classList.toggle("active",  mode === "rgb");
    modeNdvi.classList.toggle("active", mode === "ndvi");
  }

  modeRgb.addEventListener("click",  () => setMode("rgb"));
  modeNdvi.addEventListener("click", () => setMode("ndvi"));

  // Opacity slider
  const opacitySlider = document.getElementById("opacity-slider");
  const opacityVal    = document.getElementById("opacity-val");
  opacitySlider.addEventListener("input", (e) => {
    satelliteLayer.setOpacity(e.target.value / 100);
    opacityVal.textContent = `${e.target.value}%`;
  });

  // Basemap
  document.getElementById("basemap-select").addEventListener("change", (e) => {
    if (basemapSources[e.target.value]) basemapLayer.setSource(basemapSources[e.target.value]);
  });

  // Boundary toggle
  document.getElementById("boundary-toggle").addEventListener("change", (e) => {
    boundaryLayer.setVisible(e.target.checked);
  });

  // Export (download current product COG)
  const btnExport = document.getElementById("btn-export-cog");
  let currentProductId = null;

  btnExport.addEventListener("click", async () => {
    if (!currentProductId) return;
    try {
      const res  = await fetch(`/api/imagery/${currentProductId}/download-url`);
      const data = await res.json();
      if (data.download_url) window.open(data.download_url, "_blank");
    } catch (err) {
      toast("Không lấy được link tải: " + err.message, "error");
    }
  });

  // ═══════════════════════════════════════════════════════════════════
  // 6. DATE ALERT BANNER
  // ═══════════════════════════════════════════════════════════════════

  const dateBanner     = document.getElementById("date-alert-banner");
  const dateBannerIcon = document.getElementById("date-alert-icon");
  const dateBannerText = document.getElementById("date-alert-text");

  function showDateBanner(data) {
    if (!data || (!data.date_info_message && !data.cloud_warning)) { hideDateBanner(); return; }
    dateBanner.style.display = "flex";
    if (data.date_match_status === "nearest") {
      dateBanner.className = "date-alert-banner date-alert-nearest";
      dateBannerIcon.setAttribute("data-lucide", "calendar-x");
      dateBannerText.textContent = data.date_info_message || "";
    } else if (data.cloud_warning) {
      dateBanner.className = "date-alert-banner date-alert-cloud";
      dateBannerIcon.setAttribute("data-lucide", "cloud-alert");
      dateBannerText.textContent = data.cloud_warning;
    } else {
      dateBanner.className = "date-alert-banner date-alert-exact";
      dateBannerIcon.setAttribute("data-lucide", "calendar-check");
      dateBannerText.textContent = data.date_info_message || "Ảnh đúng ngày yêu cầu";
    }
    lucide.createIcons();
  }

  function hideDateBanner() {
    if (dateBanner) dateBanner.style.display = "none";
  }

  // ═══════════════════════════════════════════════════════════════════
  // 7. KHI SẢN PHẨM SẴN SÀNG → hiển thị lên bản đồ
  // ═══════════════════════════════════════════════════════════════════

  const metaCache = document.getElementById("meta-cache");
  const metaDate  = document.getElementById("meta-date");
  const metaCloud = document.getElementById("meta-cloud");
  const metaSize  = document.getElementById("meta-size");

  function onProductReady(p) {
    currentProductId = p.product_id;

    // Tile layer
    if (p.tile_url_template) {
      satelliteLayer.setSource(new ol.source.XYZ({ url: p.tile_url_template, maxZoom: 18 }));
      satelliteLayer.setVisible(true);
    }

    // Sync display mode
    if (p.product_type) setMode(p.product_type);

    // Metadata
    const hit = (p.cache_status || "").includes("HIT");
    metaCache.innerHTML = hit
      ? `<span class="badge-hit">✓ R2 Cache</span>`
      : `<span class="badge-miss">⟳ Mới tải</span>`;
    metaDate.textContent  = p.actual_date || p.acquisition_date || "--";
    metaCloud.textContent = p.cloud_cover !== undefined ? `${p.cloud_cover}%` : "-- %";
    metaSize.textContent  = p.file_size_bytes
      ? `${(p.file_size_bytes / 1048576).toFixed(1)} MB`
      : "~140 MB";

    btnExport.disabled = false;

    // Highlight catalog item
    document.querySelectorAll(".cat-item").forEach(el => {
      el.classList.toggle("active", el.dataset.productId === p.product_id);
    });

    // Fit bounds
    if (p.bounds?.length === 4) {
      const ext = ol.proj.transformExtent(p.bounds, "EPSG:4326", "EPSG:3857");
      map.getView().fit(ext, { padding: [60, 60, 60, 60], maxZoom: 12, duration: 700 });
    }
  }

  // ═══════════════════════════════════════════════════════════════════
  // 8. CATALOG — Kho ảnh R2 (panel trái)
  // ═══════════════════════════════════════════════════════════════════

  const catalogList    = document.getElementById("catalog-list");
  const catalogLoading = document.getElementById("catalog-loading");
  const catalogEmpty   = document.getElementById("catalog-empty");
  const catalogCount   = document.getElementById("catalog-count");

  let allItems       = [];
  let activeFilter   = "all";

  document.querySelectorAll(".filter-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeFilter = btn.dataset.filter;
      renderCatalog(allItems, activeFilter);
    });
  });

  const btnRefresh = document.getElementById("btn-refresh-catalog");
  btnRefresh.addEventListener("click", async () => {
    btnRefresh.disabled = true;
    await loadCatalog();
    btnRefresh.disabled = false;
  });

  async function loadCatalog() {
    catalogLoading.style.display = "flex";
    catalogEmpty.style.display   = "none";
    catalogList.innerHTML = "";

    try {
      const res  = await fetch("/api/imagery/r2-catalog");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      allItems = data.items || [];
      if (catalogCount) catalogCount.textContent = allItems.length;
      renderCatalog(allItems, activeFilter);
    } catch (err) {
      catalogLoading.style.display = "none";
      catalogEmpty.style.display   = "flex";
      catalogEmpty.innerHTML = `<i data-lucide="wifi-off" style="width:20px;height:20px;opacity:0.3;"></i><span>Lỗi kết nối R2</span>`;
      lucide.createIcons();
    }
  }

  function renderCatalog(items, filter) {
    catalogLoading.style.display = "none";
    catalogList.innerHTML = "";

    const filtered = filter === "all" ? items : items.filter(i => i.product_type === filter);

    if (filtered.length === 0) {
      catalogEmpty.style.display = "flex";
      catalogEmpty.innerHTML = `
        <i data-lucide="inbox" style="width:20px;height:20px;opacity:0.3;"></i>
        <span>${filter === "all" ? "Chưa có ảnh nào trong kho" : `Chưa có ảnh ${filter.toUpperCase()}`}</span>
        <small>Tải ảnh mới từ tab "Tải ảnh" bên phải →</small>`;
      lucide.createIcons();
      return;
    }

    catalogEmpty.style.display = "none";

    filtered.forEach(item => {
      const cloudColor = item.cloud_cover <= 20 ? "#10b981"
                       : item.cloud_cover <= 40 ? "#f59e0b"
                       : "#f43f5e";
      const sizeTxt = item.file_size_mb ? `${item.file_size_mb} MB` : "--";

      const el = document.createElement("div");
      el.className = "cat-item";
      el.dataset.productId = item.product_id;

      el.innerHTML = `
        <div class="cat-item-top">
          <div class="cat-date">${item.acquisition_date}</div>
          <div class="type-badge type-${item.product_type}">${item.product_type === "ndvi" ? "🌿 NDVI" : "🌈 RGB"}</div>
        </div>
        <div class="cat-item-meta">
          <span style="color:${cloudColor};">
            <i data-lucide="cloud" style="width:11px;height:11px;"></i>
            ${item.cloud_cover}%
          </span>
          <span>
            <i data-lucide="hard-drive" style="width:11px;height:11px;"></i>
            ${sizeTxt}
          </span>
        </div>
        <div class="cat-item-actions">
          <button class="btn-show" data-action="show">
            <i data-lucide="map-pin" style="width:12px;height:12px;"></i>
            Hiển thị
          </button>
          <button class="btn-export" data-action="export">
            <i data-lucide="download" style="width:11px;height:11px;"></i>
            Xuất
          </button>
        </div>`;

      // Show button
      el.querySelector("[data-action='show']").addEventListener("click", (e) => {
        e.stopPropagation();
        if (!item.tile_url_template) { toast("Không có tile URL cho ảnh này", "warning"); return; }
        hideDateBanner();
        onProductReady({
          product_id:       item.product_id,
          cache_status:     "HIT",
          tile_url_template:item.tile_url_template,
          cloud_cover:      item.cloud_cover,
          bounds:           item.bounds,
          actual_date:      item.acquisition_date,
          product_type:     item.product_type,
          file_size_bytes:  item.file_size_bytes,
        });
        toast(`Đã hiển thị ảnh ${item.product_type.toUpperCase()} ngày ${item.acquisition_date}`, "success");
      });

      // Export button
      el.querySelector("[data-action='export']").addEventListener("click", async (e) => {
        e.stopPropagation();
        try {
          const res  = await fetch(`/api/imagery/${item.product_id}/download-url`);
          const data = await res.json();
          if (data.download_url) {
            window.open(data.download_url, "_blank");
            toast(`Đang xuất file GeoTIFF cho ngày ${item.acquisition_date}`, "info");
          }
        } catch (err) {
          toast("Lỗi lấy link tải: " + err.message, "error");
        }
      });

      catalogList.appendChild(el);
    });

    lucide.createIcons();
  }

  // ═══════════════════════════════════════════════════════════════════
  // 9. DOWNLOAD WORKFLOW (Right panel → Tab "Tải ảnh mới")
  // ═══════════════════════════════════════════════════════════════════

  // Sections
  const sectionForm     = document.getElementById("download-form-section");
  const sectionPreview  = document.getElementById("download-preview-section");
  const sectionProgress = document.getElementById("download-progress-section");

  // Form inputs
  const dlDateInput   = document.getElementById("dl-date-input");
  const dlCloudSelect = document.getElementById("dl-cloud-select");
  const btnSearch     = document.getElementById("btn-search-scene");

  // Preview elements
  const scenePreviewCard  = document.getElementById("scene-preview-card");
  const btnConfirmDownload= document.getElementById("btn-confirm-download");
  const btnCancelDownload = document.getElementById("btn-cancel-download");

  // Progress elements
  const progIcon       = document.getElementById("prog-icon");
  const progTitle      = document.getElementById("prog-title");
  const progPct        = document.getElementById("prog-pct");
  const progBarFill    = document.getElementById("prog-bar-fill");
  const progStatus     = document.getElementById("prog-status");
  const progElapsed    = document.getElementById("prog-elapsed");
  const progActualDate = document.getElementById("prog-actual-date");

  // State
  let downloadState   = "idle";   // idle | searching | preview | downloading | done | error
  let previewScene    = null;
  let activeJobId     = null;
  let pollingInterval = null;
  let elapsedTimer    = null;
  let elapsedSeconds  = 0;
  let progDisplay     = 0;
  let progTarget      = 0;
  let progAnimTimer   = null;

  // Set today as default date
  dlDateInput.value = new Date().toISOString().slice(0, 10);

  // Render the download tab state
  function setDownloadState(state) {
    downloadState = state;
    sectionForm.style.display     = (state === "idle" || state === "done" || state === "error") ? "block" : "block";
    sectionPreview.style.display  = (state === "preview") ? "block" : "none";
    sectionProgress.style.display = (state === "downloading") ? "block" : "none";

    // While searching: disable button
    if (state === "searching") {
      btnSearch.disabled = true;
      btnSearch.innerHTML = `<i data-lucide="loader" class="spin" style="width:14px;height:14px;"></i><span>Đang tìm kiếm...</span>`;
    } else {
      btnSearch.disabled = false;
      btnSearch.innerHTML = `<i data-lucide="search" style="width:14px;height:14px;"></i><span>Tìm kiếm ảnh phù hợp</span>`;
    }
    lucide.createIcons();
  }

  // ── STEP 1: SEARCH SCENE ──
  btnSearch.addEventListener("click", async () => {
    const date = dlDateInput.value;
    if (!date) { toast("Vui lòng chọn ngày", "warning"); return; }

    const maxCloud = parseFloat(dlCloudSelect.value);
    setDownloadState("searching");

    try {
      const res = await fetch(`/api/imagery/search?date=${date}&max_cloud=${maxCloud}&search_window_days=5`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      if (!data.scenes || data.scenes.length === 0) {
        toast(`Không tìm thấy ảnh quanh ngày ${date}`, "warning");
        setDownloadState("idle");
        return;
      }

      previewScene = data.scenes[0];
      renderPreview(previewScene, date, maxCloud);
      setDownloadState("preview");

    } catch (err) {
      toast("Lỗi tìm kiếm: " + err.message, "error");
      setDownloadState("idle");
    }
  });

  function renderPreview(scene, requestedDate, maxCloud) {
    const actualDate   = scene.date || requestedDate;
    const cloud        = scene.cloud_cover || 0;
    const isNearest    = scene.date_match_status === "nearest";
    const diffDays     = scene.date_diff_days || 0;
    const hasSouth     = scene.has_southern_tile;
    const cloudWarning = scene.cloud_warning;

    let html = `
      <div class="preview-row">
        <span class="preview-lbl">Ngày yêu cầu</span>
        <span class="preview-val">${requestedDate}</span>
      </div>
      <div class="preview-row">
        <span class="preview-lbl">Ngày ảnh thực tế</span>
        <span class="preview-val" style="color:${isNearest ? '#fbbf24' : '#34d399'};">${actualDate}</span>
      </div>
      <div class="preview-row">
        <span class="preview-lbl">Độ che phủ mây</span>
        <span class="preview-val" style="color:${cloud <= 20 ? '#10b981' : cloud <= 40 ? '#f59e0b' : '#f43f5e'};">${cloud.toFixed(1)}%</span>
      </div>
      <div class="preview-row">
        <span class="preview-lbl">Vệ tinh</span>
        <span class="preview-val">${scene.platform || "Sentinel-2"}</span>
      </div>
      <div class="preview-row">
        <span class="preview-lbl">Độ phủ Hà Nội</span>
        <span class="preview-val">${hasSouth ? "Đầy đủ (Bắc + Nam)" : "Một phần (Bắc)"}</span>
      </div>`;

    if (isNearest) {
      const direction = new Date(actualDate) < new Date(requestedDate) ? "trước" : "sau";
      html += `
        <div class="preview-warning">
          <i data-lucide="calendar-x" style="width:13px;height:13px;flex-shrink:0;margin-top:1px;"></i>
          <span>Không có ảnh ngày ${requestedDate}. Ngày gần nhất: <strong>${actualDate}</strong> (chênh ${diffDays} ngày ${direction})</span>
        </div>`;
    }

    if (cloudWarning) {
      html += `
        <div class="preview-cloud-warn">
          <i data-lucide="cloud-alert" style="width:13px;height:13px;flex-shrink:0;margin-top:1px;"></i>
          <span>${cloudWarning}</span>
        </div>`;
    }

    scenePreviewCard.innerHTML = html;
    lucide.createIcons();
  }

  // ── STEP 2: CANCEL ──
  btnCancelDownload.addEventListener("click", () => {
    previewScene = null;
    setDownloadState("idle");
  });

  // ── STEP 3: CONFIRM → DOWNLOAD ──
  btnConfirmDownload.addEventListener("click", async () => {
    if (!previewScene) return;

    const date       = dlDateInput.value;
    const maxCloud   = parseFloat(dlCloudSelect.value);
    const productType= document.querySelector('input[name="dl-product-type"]:checked')?.value || "rgb";

    // Check existing product for actual date
    const actualDate    = previewScene.date || date;
    const actualProdId  = `s2_${actualDate.replace(/-/g, "")}_hanoi_${productType}`;

    setDownloadState("downloading");
    startElapsedTimer();
    resetProgress();
    progActualDate.textContent = actualDate;
    updateStep("stac", "active");

    // Show banner if date differs
    if (previewScene.date_match_status === "nearest") {
      showDateBanner(previewScene);
    }

    try {
      const res = await fetch("/api/imagery/prepare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          date,
          product_type: productType,
          max_cloud: maxCloud,
          search_window_days: 5,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();

      if (data.status === "ready") {
        // Already cached (from actual date)
        stopElapsedTimer();
        setDownloadState("idle");
        updateStep("stac",   "done");
        updateStep("raster", "done");
        updateStep("upload", "done");
        onProductReady({ ...data, actual_date: data.actual_date || actualDate });
        showDateBanner(data);
        await loadCatalog();
        toast(`Ảnh đã có sẵn trong kho! Đã tải lên bản đồ.`, "success");

        // Switch to info tab
        setTimeout(() => {
          document.querySelector('[data-tab="info"]').click();
        }, 1000);

      } else if (data.status === "processing") {
        activeJobId = data.job_id;
        pollJob(data.job_id, actualDate);
      } else {
        throw new Error(data.message || "Không thể xử lý yêu cầu");
      }
    } catch (err) {
      stopElapsedTimer();
      setDownloadState("error");
      setDownloadState("idle");
      toast("Lỗi tải ảnh: " + err.message, "error");
    }
  });

  // ── POLLING JOB STATUS ──
  function pollJob(jobId, actualDate) {
    if (pollingInterval) clearInterval(pollingInterval);

    pollingInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) return;
        const job = await res.json();

        // Animate progress
        setProgress(job.progress || 0, job.message || "");

        // Update pipeline steps based on progress
        if (job.progress >= 10) updateStep("stac", "done");
        if (job.progress >= 30) updateStep("raster", "active");
        if (job.progress >= 80) { updateStep("raster", "done"); updateStep("upload", "active"); }
        if (job.progress >= 96) updateStep("upload", "done");

        if (job.date_match_status) showDateBanner(job);
        if (job.actual_date) progActualDate.textContent = job.actual_date;

        if (job.status === "completed") {
          clearInterval(pollingInterval);
          pollingInterval = null;
          stopElapsedTimer();

          setProgress(100, "✓ Hoàn thành! Đang tải lên bản đồ...");
          updateStep("stac", "done");
          updateStep("raster", "done");
          updateStep("upload", "done");

          // Set progress icon to check
          progIcon.classList.remove("spin");
          progIcon.setAttribute("data-lucide", "check-circle-2");
          progIcon.style.color = "#10b981";
          lucide.createIcons();

          setTimeout(async () => {
            setDownloadState("idle");
            onProductReady({
              product_id:        job.product_id,
              cache_status:      "MISS",
              tile_url_template: job.tile_url_template,
              cloud_cover:       job.cloud_cover,
              bounds:            job.bounds,
              actual_date:       job.actual_date || actualDate,
              product_type:      job.product_type || currentProductType,
              file_size_bytes:   job.file_size_bytes,
            });

            showDateBanner(job);
            await loadCatalog();
            toast(`Tải thành công! Ảnh ngày ${job.actual_date || actualDate} đã vào kho.`, "success");

            // Switch to info tab
            document.querySelector('[data-tab="info"]').click();
          }, 1500);

        } else if (job.status === "failed") {
          clearInterval(pollingInterval);
          pollingInterval = null;
          stopElapsedTimer();
          setDownloadState("idle");
          toast("Xử lý thất bại: " + (job.error || job.message), "error");
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 1500);
  }

  // ── PROGRESS HELPERS ──
  function resetProgress() {
    progDisplay = 0;
    progTarget  = 0;
    progBarFill.style.width  = "0%";
    progPct.textContent      = "0%";
    progStatus.textContent   = "Đang khởi tạo pipeline...";
    progTitle.textContent    = "Đang xử lý...";
    // Reset progress icon
    progIcon.classList.add("spin");
    progIcon.setAttribute("data-lucide", "loader");
    progIcon.style.color = "var(--cyan)";
    lucide.createIcons();
    // Reset steps
    ["stac", "raster", "upload"].forEach(s => updateStep(s, "idle"));
  }

  function setProgress(pct, msg) {
    progTarget = Math.max(0, Math.min(100, pct));
    if (msg) progStatus.textContent = msg;

    if (!progAnimTimer) {
      progAnimTimer = setInterval(() => {
        if (progDisplay < progTarget) progDisplay = Math.min(progDisplay + 1, progTarget);
        else if (progDisplay > progTarget) progDisplay = progTarget;

        progBarFill.style.width = `${progDisplay}%`;
        progPct.textContent     = `${progDisplay}%`;

        if (progDisplay >= 100 && progTarget >= 100) {
          clearInterval(progAnimTimer);
          progAnimTimer = null;
        }
      }, 20);
    }
  }

  function updateStep(stepName, state) {
    const stepEl  = document.getElementById(`step-${stepName}`);
    const iconEl  = document.getElementById(`step-${stepName}-status`);
    if (!stepEl || !iconEl) return;

    stepEl.className = `step step-${state}`;
    const iconMap = { idle: "circle", active: "loader", done: "check-circle-2", error: "alert-circle" };
    iconEl.setAttribute("data-lucide", iconMap[state] || "circle");
    if (state === "active") iconEl.classList.add("spin");
    else iconEl.classList.remove("spin");
    lucide.createIcons();
  }

  function startElapsedTimer() {
    elapsedSeconds = 0;
    progElapsed.textContent = "00:00";
    if (elapsedTimer) clearInterval(elapsedTimer);
    elapsedTimer = setInterval(() => {
      elapsedSeconds++;
      const m = String(Math.floor(elapsedSeconds / 60)).padStart(2, "0");
      const s = String(elapsedSeconds % 60).padStart(2, "0");
      progElapsed.textContent = `${m}:${s}`;
    }, 1000);
  }

  function stopElapsedTimer() {
    if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null; }
  }

  // ═══════════════════════════════════════════════════════════════════
  // 10. TOAST NOTIFICATIONS
  // ═══════════════════════════════════════════════════════════════════

  function toast(message, type = "info") {
    const iconMap = { success: "check-circle-2", error: "alert-circle", warning: "alert-triangle", info: "info" };
    const el = document.createElement("div");
    el.className = `toast toast-${type}`;
    el.innerHTML = `<i data-lucide="${iconMap[type]}" style="width:15px;height:15px;flex-shrink:0;"></i><span>${message}</span>`;

    let container = document.getElementById("toast-container");
    if (!container) { container = document.createElement("div"); container.id = "toast-container"; document.body.appendChild(container); }

    container.appendChild(el);
    lucide.createIcons();
    requestAnimationFrame(() => el.classList.add("toast-visible"));
    setTimeout(() => { el.classList.remove("toast-visible"); setTimeout(() => el.remove(), 350); }, 4000);
  }

  // ═══════════════════════════════════════════════════════════════════
  // 11. KHỞI ĐỘNG
  // ═══════════════════════════════════════════════════════════════════

  setDownloadState("idle");
  loadCatalog();

  // Khởi tạo tất cả Lucide icons
  lucide.createIcons();

});
