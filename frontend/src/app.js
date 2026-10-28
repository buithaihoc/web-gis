/**
 * HANOI SATELLITE WEBGIS - CLIENT ENGINE v2
 * Powered by OpenLayers 10, TiTiler, Cloudflare R2, and FastAPI
 *
 * Cải tiến v2:
 * - R2 Catalog sidebar: danh sách ảnh đã lưu, click để load lên bản đồ
 * - Date alert banner: thông báo ngày thực tế vs ngày yêu cầu
 * - Cloud coverage indicator: đánh dấu ngày đủ/không đủ yêu cầu mây
 * - Tách luồng: nút topbar chỉ tải từ MPC, click catalog item load từ R2
 */

document.addEventListener("DOMContentLoaded", () => {
  // ═══════════════════════════════════════════════════════
  // 1. KHỞI TẠO STATE TOÀN CỤC
  // ═══════════════════════════════════════════════════════
  const HANOI_COORDS = [105.8342, 21.0278];
  const HANOI_CENTER_3857 = ol.proj.fromLonLat(HANOI_COORDS);

  let currentProductId = null;
  let currentProductType = "rgb";
  let activePollingInterval = null;
  let progressAnimTimer = null;
  let currentDisplayPercent = 0;
  let targetPercent = 0;

  // ═══════════════════════════════════════════════════════
  // 2. KHỞI TẠO CÁC LỚP BẢN ĐỒ NỀN (BASEMAPS)
  // ═══════════════════════════════════════════════════════
  const basemapSources = {
    dark: new ol.source.XYZ({
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
      attributions: "© Esri, HERE, Garmin, OpenStreetMap contributors",
      maxZoom: 18,
    }),
    osm: new ol.source.OSM(),
    satellite: new ol.source.XYZ({
      url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      attributions: "© Esri, DigitalGlobe, GeoEye, Earthstar Geographics",
      maxZoom: 19,
    }),
  };

  const basemapLayer = new ol.layer.Tile({ source: basemapSources.dark, zIndex: 1 });

  // ═══════════════════════════════════════════════════════
  // 3. LỚP ẢNH VỆ TINH COG ĐỘNG
  // ═══════════════════════════════════════════════════════
  const satelliteLayer = new ol.layer.Tile({ source: null, opacity: 1.0, zIndex: 5, visible: true });

  // ═══════════════════════════════════════════════════════
  // 4. LỚP VECTOR RANH GIỚI HÀ NỘI
  // ═══════════════════════════════════════════════════════
  const boundarySource = new ol.source.Vector({
    url: "/api/imagery/boundary",
    format: new ol.format.GeoJSON(),
  });

  const boundaryLayer = new ol.layer.Vector({
    source: boundarySource,
    style: new ol.style.Style({
      stroke: new ol.style.Stroke({ color: "#38bdf8", width: 2.5, lineDash: [4, 4] }),
      fill: new ol.style.Fill({ color: "rgba(56, 189, 248, 0.04)" }),
    }),
    zIndex: 10,
    visible: true,
  });

  // ═══════════════════════════════════════════════════════
  // 5. KHỞI TẠO BẢN ĐỒ OPENLAYERS
  // ═══════════════════════════════════════════════════════
  const map = new ol.Map({
    target: "map-container",
    layers: [basemapLayer, satelliteLayer, boundaryLayer],
    view: new ol.View({
      center: HANOI_CENTER_3857,
      zoom: 10.2,
      minZoom: 8,
      maxZoom: 18,
    }),
    controls: ol.control.defaults.defaults({ zoom: true, rotate: false, attribution: false }),
  });

  // ═══════════════════════════════════════════════════════
  // 6. COORDINATE BAR
  // ═══════════════════════════════════════════════════════
  const coordBar = document.getElementById("coordinate-bar");
  map.on("pointermove", (evt) => {
    const coords = ol.proj.toLonLat(evt.coordinate);
    const zoom = Math.round(map.getView().getZoom());
    coordBar.textContent = `${coords[0].toFixed(4)}°E, ${coords[1].toFixed(4)}°N | Zoom: ${zoom}`;
  });

  // ═══════════════════════════════════════════════════════
  // 7. CÁC CONTROLS CƠ BẢN
  // ═══════════════════════════════════════════════════════

  // Đổi basemap
  document.getElementById("basemap-select").addEventListener("change", (e) => {
    if (basemapSources[e.target.value]) basemapLayer.setSource(basemapSources[e.target.value]);
  });

  // Toggle ranh giới
  document.getElementById("boundary-toggle").addEventListener("change", (e) => {
    boundaryLayer.setVisible(e.target.checked);
  });

  // Opacity slider
  const opacitySlider = document.getElementById("opacity-slider");
  const opacityVal = document.getElementById("opacity-val");
  opacitySlider.addEventListener("input", (e) => {
    satelliteLayer.setOpacity(e.target.value / 100);
    opacityVal.textContent = `${e.target.value}%`;
  });

  // Sidebar toggle
  const sidebar = document.getElementById("sidebar");
  const sidebarToggleIcon = document.getElementById("sidebar-toggle-icon");
  document.getElementById("sidebar-toggle").addEventListener("click", () => {
    sidebar.classList.toggle("collapsed");
    const isCollapsed = sidebar.classList.contains("collapsed");
    sidebarToggleIcon.setAttribute("data-lucide", isCollapsed ? "chevron-right" : "chevron-left");
    lucide.createIcons();
    setTimeout(() => map.updateSize(), 300);
  });

  // Reset view
  document.getElementById("btn-reset-view").addEventListener("click", () => {
    map.getView().animate({ center: HANOI_CENTER_3857, zoom: 10.2, duration: 800 });
  });

  // Fullscreen
  document.getElementById("btn-fullscreen").addEventListener("click", () => {
    if (!document.fullscreenElement) document.documentElement.requestFullscreen();
    else document.exitFullscreen();
  });

  // ═══════════════════════════════════════════════════════
  // 8. PRODUCT MODE (RGB / NDVI)
  // ═══════════════════════════════════════════════════════
  const modeRgbBtn = document.getElementById("mode-rgb");
  const modeNdviBtn = document.getElementById("mode-ndvi");

  function setProductMode(mode) {
    currentProductType = mode;
    modeRgbBtn.classList.toggle("active", mode === "rgb");
    modeNdviBtn.classList.toggle("active", mode === "ndvi");
  }

  modeRgbBtn.addEventListener("click", () => setProductMode("rgb"));
  modeNdviBtn.addEventListener("click", () => setProductMode("ndvi"));

  // ═══════════════════════════════════════════════════════
  // 9. DATE ALERT BANNER (Thông báo ngày thực tế)
  // ═══════════════════════════════════════════════════════
  const dateAlertBanner = document.getElementById("date-alert-banner");
  const dateAlertIcon = document.getElementById("date-alert-icon");
  const dateAlertText = document.getElementById("date-alert-text");

  function showDateAlert(data) {
    if (!dateAlertBanner) return;
    const status = data.date_match_status;
    const infoMsg = data.date_info_message;
    const cloudWarn = data.cloud_warning;

    if (!infoMsg && !cloudWarn) {
      hideDateAlert();
      return;
    }

    dateAlertBanner.style.display = "flex";

    if (status === "nearest") {
      dateAlertBanner.className = "date-alert-banner date-alert-nearest";
      dateAlertIcon.setAttribute("data-lucide", "calendar-x");
      let msg = infoMsg || "";
      if (cloudWarn) msg += (msg ? " | " : "") + cloudWarn;
      dateAlertText.textContent = msg;
    } else if (cloudWarn) {
      dateAlertBanner.className = "date-alert-banner date-alert-cloud";
      dateAlertIcon.setAttribute("data-lucide", "cloud-alert");
      dateAlertText.textContent = cloudWarn;
    } else {
      dateAlertBanner.className = "date-alert-banner date-alert-exact";
      dateAlertIcon.setAttribute("data-lucide", "calendar-check");
      dateAlertText.textContent = infoMsg || "Ảnh đúng ngày yêu cầu";
    }
    lucide.createIcons();
  }

  function hideDateAlert() {
    if (dateAlertBanner) dateAlertBanner.style.display = "none";
  }

  // ═══════════════════════════════════════════════════════
  // 10. PROGRESS CARD
  // ═══════════════════════════════════════════════════════
  const progressCard = document.getElementById("progress-card");
  const progressPercent = document.getElementById("progress-percent");
  const progressBarFill = document.getElementById("progress-bar-fill");
  const progressStatus = document.getElementById("progress-status");

  function showProgress(percent, message) {
    progressCard.style.display = "block";
    targetPercent = Math.min(Math.max(percent, 0), 100);
    if (message) progressStatus.textContent = message;

    if (!progressAnimTimer) {
      progressAnimTimer = setInterval(() => {
        if (currentDisplayPercent < targetPercent) {
          currentDisplayPercent += 1;
        } else if (currentDisplayPercent > targetPercent) {
          currentDisplayPercent = targetPercent;
        }
        progressPercent.textContent = `${currentDisplayPercent}%`;
        progressBarFill.style.width = `${currentDisplayPercent}%`;

        if (currentDisplayPercent >= 100 && targetPercent >= 100) {
          clearInterval(progressAnimTimer);
          progressAnimTimer = null;
        }
      }, 25);
    }
  }

  function hideProgress() {
    if (progressCard) progressCard.style.display = "none";
    if (progressAnimTimer) { clearInterval(progressAnimTimer); progressAnimTimer = null; }
    currentDisplayPercent = 0;
    targetPercent = 0;
  }

  // ═══════════════════════════════════════════════════════
  // 11. LOAD BUTTON (Tải từ MPC - nút topbar)
  // ═══════════════════════════════════════════════════════
  const btnLoad = document.getElementById("btn-load-imagery");
  const dateInput = document.getElementById("date-input");
  const metaCache = document.getElementById("meta-cache");
  const metaCloud = document.getElementById("meta-cloud");
  const metaDate = document.getElementById("meta-date");
  const metaSize = document.getElementById("meta-size");
  const btnDownload = document.getElementById("btn-download-cog");

  function resetLoadButton() {
    btnLoad.disabled = false;
    btnLoad.innerHTML = `<i data-lucide="satellite" style="width:16px;height:16px;"></i><span>Tải từ MPC</span>`;
    lucide.createIcons();
  }

  btnLoad.addEventListener("click", requestImageryFromMPC);

  async function requestImageryFromMPC() {
    const selectedDate = dateInput.value;
    if (!selectedDate) {
      showToast("Vui lòng chọn ngày trước khi tải ảnh!", "warning");
      return;
    }

    if (activePollingInterval) { clearInterval(activePollingInterval); activePollingInterval = null; }
    hideProgress();
    hideDateAlert();

    btnLoad.disabled = true;
    btnLoad.innerHTML = `<i data-lucide="loader" class="animate-spin" style="width:16px;height:16px;"></i><span>Đang kiểm tra...</span>`;
    lucide.createIcons();

    try {
      const cloudVal = document.getElementById("cloud-select")?.value;
      const response = await fetch("/api/imagery/prepare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          date: selectedDate,
          product_type: currentProductType,
          max_cloud: cloudVal ? parseFloat(cloudVal) : 40.0,
          search_window_days: 5,
        }),
      });

      if (!response.ok) {
        const errText = await response.text();
        let errMsg = errText;
        try { const o = JSON.parse(errText); errMsg = o.detail || o.message || errText; } catch (_) {}
        resetLoadButton();
        showToast("Lỗi máy chủ (" + response.status + "): " + errMsg, "error");
        return;
      }

      const data = await response.json();

      // Hiển thị banner thông báo ngày (ngay cả khi cache HIT từ ngày nearest)
      if (data.date_match_status) showDateAlert(data);

      if (data.status === "ready") {
        resetLoadButton();
        onProductReady(data);
      } else if (data.status === "processing") {
        btnLoad.disabled = true;
        btnLoad.innerHTML = `<i data-lucide="loader" class="animate-spin" style="width:16px;height:16px;"></i><span>Đang xử lý...</span>`;
        lucide.createIcons();
        showProgress(data.progress || 10, data.message || "Đang xử lý tác vụ...");
        startPollingJob(data.job_id);
      } else {
        resetLoadButton();
        showToast(data.message || "Không thể tải ảnh cho ngày này.", "warning");
      }
    } catch (err) {
      console.error(err);
      resetLoadButton();
      showToast("Lỗi kết nối tới máy chủ WebGIS: " + err.message, "error");
    }
  }

  // ═══════════════════════════════════════════════════════
  // 12. POLLING JOB STATUS
  // ═══════════════════════════════════════════════════════
  function startPollingJob(jobId) {
    activePollingInterval = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) return;
        const job = await res.json();

        showProgress(job.progress, job.message);

        // Cập nhật banner ngày khi có thông tin từ job
        if (job.date_match_status) showDateAlert(job);

        if (job.status === "completed") {
          clearInterval(activePollingInterval);
          activePollingInterval = null;

          const spinnerIcon = document.getElementById("progress-spinner-icon");
          if (spinnerIcon) {
            spinnerIcon.classList.remove("animate-spin");
            spinnerIcon.setAttribute("data-lucide", "check-circle-2");
            spinnerIcon.style.color = "#10b981";
            lucide.createIcons();
          }

          setTimeout(() => {
            hideProgress();
            if (spinnerIcon) {
              spinnerIcon.classList.add("animate-spin");
              spinnerIcon.setAttribute("data-lucide", "loader");
              spinnerIcon.style.color = "var(--accent-cyan)";
              lucide.createIcons();
            }
          }, 2000);

          resetLoadButton();
          onProductReady({
            product_id: job.product_id,
            cache_status: "MISS (Vừa tạo)",
            tile_url_template: job.tile_url_template,
            cloud_cover: job.cloud_cover,
            bounds: job.bounds,
            actual_date: job.actual_date || job.acquisition_date,
            date_match_status: job.date_match_status,
            date_diff_days: job.date_diff_days,
            date_info_message: job.date_info_message,
          });

          // Reload R2 catalog
          loadR2Catalog();

        } else if (job.status === "failed") {
          clearInterval(activePollingInterval);
          activePollingInterval = null;
          resetLoadButton();
          hideProgress();
          showToast("Xử lý thất bại: " + (job.error || job.message), "error");
        }
      } catch (err) {
        console.error("Lỗi polling job:", err);
      }
    }, 1500);
  }

  // ═══════════════════════════════════════════════════════
  // 13. KHI SẢN PHẨM SẴN SÀNG (Cache HIT hoặc Job hoàn tất)
  // ═══════════════════════════════════════════════════════
  function onProductReady(productData) {
    currentProductId = productData.product_id;

    // 1. Cập nhật tile layer
    if (productData.tile_url_template) {
      satelliteLayer.setSource(new ol.source.XYZ({ url: productData.tile_url_template, maxZoom: 18 }));
      satelliteLayer.setVisible(true);
    }

    // 2. Metadata card
    const cacheStatus = productData.cache_status || "HIT";
    metaCache.innerHTML = cacheStatus.includes("HIT")
      ? `<span class="badge-hit">✓ R2 Cache</span>`
      : `<span class="badge-miss">${cacheStatus}</span>`;

    metaCloud.textContent = productData.cloud_cover !== undefined
      ? `${productData.cloud_cover}%`
      : "-- %";

    if (metaDate) {
      metaDate.textContent = productData.actual_date || "--";
    }

    metaSize.textContent = productData.file_size_bytes
      ? `${(productData.file_size_bytes / (1024 * 1024)).toFixed(1)} MB`
      : "~140 MB";

    // 3. Kích hoạt nút download
    btnDownload.disabled = false;

    // 4. Highlight item đang active trong catalog
    highlightActiveCatalogItem(productData.product_id);

    // 5. Fit bounds nếu có
    if (productData.bounds && productData.bounds.length === 4) {
      const extent = ol.proj.transformExtent(productData.bounds, "EPSG:4326", "EPSG:3857");
      map.getView().fit(extent, { padding: [60, 60, 60, 60], maxZoom: 12, duration: 800 });
    }
  }

  // ═══════════════════════════════════════════════════════
  // 14. DOWNLOAD COG
  // ═══════════════════════════════════════════════════════
  btnDownload.addEventListener("click", async () => {
    if (!currentProductId) return;
    try {
      const res = await fetch(`/api/imagery/${currentProductId}/download-url`);
      const data = await res.json();
      if (data.download_url) window.open(data.download_url, "_blank");
    } catch (err) {
      showToast("Không lấy được đường link tải file: " + err.message, "error");
    }
  });

  // ═══════════════════════════════════════════════════════
  // 15. R2 CATALOG - Danh sách ảnh đã lưu trên R2
  // ═══════════════════════════════════════════════════════
  const r2CatalogList = document.getElementById("r2-catalog-list");
  const r2CatalogCount = document.getElementById("r2-catalog-count");
  const r2CatalogEmpty = document.getElementById("r2-catalog-empty");
  const r2CatalogLoading = document.getElementById("r2-catalog-loading");
  const r2FilterBtns = document.querySelectorAll(".r2-filter-btn");
  let r2CurrentFilter = "all";
  let r2AllItems = [];

  // Filter buttons
  r2FilterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      r2FilterBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      r2CurrentFilter = btn.dataset.filter;
      renderCatalogItems(r2AllItems, r2CurrentFilter);
    });
  });

  async function loadR2Catalog() {
    if (!r2CatalogList) return;

    if (r2CatalogLoading) r2CatalogLoading.style.display = "flex";
    if (r2CatalogEmpty) r2CatalogEmpty.style.display = "none";
    if (r2CatalogList) r2CatalogList.innerHTML = "";

    try {
      const res = await fetch("/api/imagery/r2-catalog");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      r2AllItems = data.items || [];

      if (r2CatalogCount) r2CatalogCount.textContent = r2AllItems.length;
      renderCatalogItems(r2AllItems, r2CurrentFilter);
    } catch (err) {
      console.error("Lỗi tải R2 catalog:", err);
      if (r2CatalogLoading) r2CatalogLoading.style.display = "none";
      if (r2CatalogEmpty) {
        r2CatalogEmpty.style.display = "flex";
        r2CatalogEmpty.innerHTML = `<i data-lucide="wifi-off" style="width:20px;height:20px;opacity:0.4;"></i><span>Không kết nối được kho R2</span>`;
        lucide.createIcons();
      }
    }
  }

  function renderCatalogItems(items, filter) {
    if (!r2CatalogList) return;
    if (r2CatalogLoading) r2CatalogLoading.style.display = "none";

    const filtered = filter === "all" ? items : items.filter(i => i.product_type === filter);
    r2CatalogList.innerHTML = "";

    if (filtered.length === 0) {
      if (r2CatalogEmpty) {
        r2CatalogEmpty.style.display = "flex";
        r2CatalogEmpty.textContent = filter === "all" ? "Chưa có ảnh nào trên R2" : `Chưa có ảnh ${filter.toUpperCase()} trên R2`;
      }
      return;
    }

    if (r2CatalogEmpty) r2CatalogEmpty.style.display = "none";

    filtered.forEach(item => {
      const el = document.createElement("div");
      el.className = "catalog-item";
      el.dataset.productId = item.product_id;

      const typeClass = item.product_type === "ndvi" ? "type-ndvi" : "type-rgb";
      const typeLabel = item.product_type === "ndvi" ? "🌿 NDVI" : "🌈 RGB";
      const cloudColor = item.cloud_cover <= 20 ? "#10b981" : item.cloud_cover <= 40 ? "#f59e0b" : "#f43f5e";
      const sizeTxt = item.file_size_mb ? `${item.file_size_mb} MB` : "--";

      el.innerHTML = `
        <div class="catalog-item-header">
          <div class="catalog-item-date">${item.acquisition_date}</div>
          <div class="catalog-item-type ${typeClass}">${typeLabel}</div>
        </div>
        <div class="catalog-item-meta">
          <span style="color: ${cloudColor};">
            <i data-lucide="cloud" style="width:11px;height:11px;"></i>
            ${item.cloud_cover}%
          </span>
          <span>
            <i data-lucide="hard-drive" style="width:11px;height:11px;"></i>
            ${sizeTxt}
          </span>
        </div>
        <div class="catalog-item-action">
          <button class="catalog-load-btn" title="Hiển thị lên bản đồ">
            <i data-lucide="map-pin" style="width:12px;height:12px;"></i>
            Hiển thị
          </button>
        </div>
      `;

      el.querySelector(".catalog-load-btn").addEventListener("click", (e) => {
        e.stopPropagation();
        loadCatalogItemToMap(item, el);
      });

      el.addEventListener("click", () => loadCatalogItemToMap(item, el));

      r2CatalogList.appendChild(el);
    });

    lucide.createIcons();
  }

  function loadCatalogItemToMap(item, el) {
    if (!item.tile_url_template) {
      showToast("Không có URL tile cho ảnh này.", "warning");
      return;
    }

    // Update product type UI
    setProductMode(item.product_type);

    // Hiển thị lên bản đồ
    onProductReady({
      product_id: item.product_id,
      cache_status: "HIT",
      tile_url_template: item.tile_url_template,
      cloud_cover: item.cloud_cover,
      bounds: item.bounds,
      actual_date: item.acquisition_date,
      date_match_status: "exact",
      date_diff_days: 0,
      date_info_message: null,
      file_size_bytes: item.file_size_bytes,
    });

    // Ẩn date alert vì load thẳng từ R2
    hideDateAlert();

    // Cập nhật date input
    if (dateInput) dateInput.value = item.acquisition_date;

    showToast(`Đã tải ảnh ${item.product_type.toUpperCase()} ngày ${item.acquisition_date} từ R2`, "success");
  }

  function highlightActiveCatalogItem(productId) {
    document.querySelectorAll(".catalog-item").forEach(el => {
      el.classList.toggle("catalog-item-active", el.dataset.productId === productId);
    });
  }

  // ═══════════════════════════════════════════════════════
  // 16. AVAILABLE DATES (Calendar datalist)
  // ═══════════════════════════════════════════════════════
  async function loadAvailableDates() {
    try {
      const today = new Date();
      const cloudVal = document.getElementById("cloud-select")?.value || "40";
      const res = await fetch(
        `/api/imagery/dates?year=${today.getFullYear()}&month=${today.getMonth() + 1}&max_cloud=${cloudVal}`
      );
      const data = await res.json();

      if (data.dates && data.dates.length > 0) {
        const datalist = document.getElementById("available-dates-list");
        if (datalist) {
          datalist.innerHTML = "";
          data.dates.forEach((d) => {
            const opt = document.createElement("option");
            opt.value = d.date;
            const cloudIcon = d.within_cloud_limit ? "✓" : "⚠";
            const cacheIcon = d.is_cached ? " 💾" : "";
            opt.label = `${d.date} ${cloudIcon} Mây ${d.cloud_cover}%${cacheIcon}`;
            datalist.appendChild(opt);
          });
        }

        // Gợi ý ngày có mây ít nhất và thỏa điều kiện
        const withinLimit = data.dates.filter(d => d.within_cloud_limit);
        const pool = withinLimit.length > 0 ? withinLimit : data.dates;
        const cleanest = [...pool].sort((a, b) => a.cloud_cover - b.cloud_cover)[0];
        if (cleanest && !dateInput.value) {
          dateInput.value = cleanest.date;
        }
      }
    } catch (e) {
      console.log("Không tải được ngày khởi tạo:", e);
    }
  }

  // ═══════════════════════════════════════════════════════
  // 17. TOAST NOTIFICATIONS
  // ═══════════════════════════════════════════════════════
  function showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;

    const iconMap = { success: "check-circle-2", error: "alert-circle", warning: "alert-triangle", info: "info" };
    toast.innerHTML = `
      <i data-lucide="${iconMap[type] || "info"}" style="width:16px;height:16px;flex-shrink:0;"></i>
      <span>${message}</span>
    `;

    let container = document.getElementById("toast-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "toast-container";
      document.body.appendChild(container);
    }

    container.appendChild(toast);
    lucide.createIcons();

    // Animate in
    requestAnimationFrame(() => { toast.classList.add("toast-visible"); });

    // Auto remove
    setTimeout(() => {
      toast.classList.remove("toast-visible");
      setTimeout(() => toast.remove(), 400);
    }, 4000);
  }

  // ═══════════════════════════════════════════════════════
  // 18. KHỞI ĐỘNG
  // ═══════════════════════════════════════════════════════
  loadAvailableDates();
  loadR2Catalog();

  // Reload catalog khi đổi filter
  const btnRefreshCatalog = document.getElementById("btn-refresh-catalog");
  if (btnRefreshCatalog) {
    btnRefreshCatalog.addEventListener("click", () => {
      btnRefreshCatalog.disabled = true;
      loadR2Catalog().finally(() => { btnRefreshCatalog.disabled = false; });
    });
  }
});
