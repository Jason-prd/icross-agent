/**
 * Popup script for the iCross Browser Extension.
 * Displays captured product data and provides actions to send to iCross backend.
 */

import { submitCapture, processCapture, listCaptures } from "./lib/api.js";
import { saveCaptureLocally, getCaptureHistory, loadSettings, saveSettings } from "./lib/storage.js";

// ── State ──
let currentCapture = null;
let isProcessing = false;

// ── DOM References ──
const $ = (id) => document.getElementById(id);

const views = {
  noProduct: $("viewNoProduct"),
  product: $("viewProduct"),
  settings: $("viewSettings"),
};

// ── Initialization ──

document.addEventListener("DOMContentLoaded", async () => {
  // Get last capture from background
  const resp = await chrome.runtime.sendMessage({ type: "GET_LAST_CAPTURE" }).catch(() => ({
    capture: null,
  }));
  currentCapture = resp?.capture || null;

  // Also check if we're on a product page by looking at tab URL
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tabs[0]?.url || "";

  const isProductPage =
    url.includes("detail.1688.com") ||
    url.includes("pinduoduo.com/") ||
    url.includes("mobile.yangkeduo.com") ||
    url.includes("detail.tmall.com") ||
    url.includes("item.taobao.com");

  if (currentCapture && isProductPage) {
    // Request fresh capture from content script
    try {
      await chrome.tabs.sendMessage(tabs[0].id, { type: "TRIGGER_CAPTURE" });
      // Wait a moment for the content script to respond
      await new Promise((r) => setTimeout(r, 500));
      const refreshed = await chrome.runtime.sendMessage({ type: "GET_LAST_CAPTURE" });
      if (refreshed?.capture) currentCapture = refreshed.capture;
    } catch {
      // Content script not available, use stored
    }
  }

  if (currentCapture && currentCapture.title) {
    showProduct(currentCapture);
  } else {
    showNoProduct();
  }

  // Bind events
  bindEvents();
});

// ── View switching ──

function showView(viewName) {
  Object.keys(views).forEach((key) => {
    views[key].classList.toggle("hidden", key !== viewName);
  });
}

function showNoProduct() {
  showView("noProduct");
  renderHistory();
}

function showProduct(capture) {
  currentCapture = capture;
  showView("product");
  renderProduct(capture);
}

function showSettings() {
  showView("settings");
  loadSettingsIntoForm();
}

// ── Product Display ──

function renderProduct(capture) {
  // Title
  $("productTitle").textContent = capture.title || "未知产品";

  // Price
  if (capture.price) {
    $("productPrice").textContent = `¥${capture.price.toFixed(2)}`;
  } else {
    $("productPrice").textContent = "价格未知";
  }

  if (capture.originalPrice) {
    $("productOriginalPrice").textContent = `¥${capture.originalPrice.toFixed(2)}`;
    $("productOriginalPrice").style.display = "";
  } else {
    $("productOriginalPrice").style.display = "none";
  }

  // Platform tag
  const platformMap = {
    "1688": "1688",
    pinduoduo: "拼多多",
    taobao: "淘宝",
  };
  $("productPlatform").textContent = platformMap[capture.platform] || capture.platform;

  // Seller
  $("productSeller").textContent = capture.sellerName || "";

  // Images
  const imgContainer = $("productImages");
  imgContainer.innerHTML = "";
  if (capture.images && capture.images.length > 0) {
    capture.images.slice(0, 5).forEach((src) => {
      const img = document.createElement("img");
      img.src = src;
      img.alt = "";
      imgContainer.appendChild(img);
    });
  } else {
    imgContainer.innerHTML = '<div style="padding:16px;color:#999;font-size:12px">暂无图片</div>';
  }

  // Specs
  const specSection = $("specSection");
  const specList = $("specList");
  const attrs = capture.attributes || {};
  const specEntries = Object.entries(attrs);

  if (specEntries.length > 0) {
    specSection.classList.remove("hidden");
    $("specCount").textContent = `(${specEntries.length})`;
    specList.innerHTML = specEntries
      .map(
        ([key, val]) =>
          `<div class="spec-item"><span class="spec-key">${escapeHtml(key)}</span><span class="spec-value">${escapeHtml(val)}</span></div>`
      )
      .join("");
  } else {
    specSection.classList.add("hidden");
  }
}

// ── History ──

async function renderHistory() {
  const list = $("historyList");
  const history = await getCaptureHistory(10);

  if (history.length === 0) {
    list.innerHTML = '<li class="history-empty">暂无捕获记录</li>';
    return;
  }

  list.innerHTML = history
    .map(
      (item) => `
    <li class="history-item" data-capture='${JSON.stringify(item).replace(/'/g, "&apos;")}'>
      <img src="${item.images?.[0] || ""}" alt="" onerror="this.style.display='none'" />
      <div class="history-item-info">
        <div class="history-item-title">${escapeHtml(item.title || "")}</div>
        <div class="history-item-meta">${item.platform || ""} · ¥${item.price?.toFixed(2) || "?"}</div>
      </div>
    </li>
  `
    )
    .join("");

  // Click history item to show product
  list.querySelectorAll(".history-item").forEach((el) => {
    el.addEventListener("click", () => {
      const data = JSON.parse(el.dataset.capture);
      currentCapture = data;
      showProduct(data);
    });
  });
}

// ── Actions ──

async function handleSendToICross(autoProcess = false) {
  if (isProcessing || !currentCapture) return;
  isProcessing = true;
  showLoading("发送到 iCross...");

  try {
    const statusEl = $("statusMessage");
    statusEl.classList.add("hidden");

    // Submit capture to backend
    const result = await submitCapture(currentCapture);

    if (result?.capture?.id) {
      if (autoProcess) {
        showLoading("正在生成 Listing...");
        const processResult = await processCapture(result.capture.id, {
          autoGenerateListing: true,
          autoCalculatePrice: true,
          autoCreateDraft: false,
        });
        showStatus(
          `✅ Listing 生成成功！` + (processResult.listing ? " 可查看俄语标题和描述" : ""),
          "success"
        );
      } else {
        showStatus("✅ 已发送到 iCross！可在 iCross 后台查看和处理", "success");
      }
    } else {
      showStatus("⚠️ 发送成功但未收到确认", "info");
    }
  } catch (err) {
    showStatus(`❌ 发送失败: ${err.message}`, "error");
    // Save to local queue
    await saveCaptureLocally(currentCapture);
  } finally {
    isProcessing = false;
    hideLoading();
  }
}

// ── Settings ──

async function loadSettingsIntoForm() {
  const settings = await loadSettings();
  $("serverUrl").value = settings.serverUrl;
  $("apiKey").value = settings.apiKey;
}

$("btnSaveSettings")?.addEventListener("click", async () => {
  await saveSettings({
    serverUrl: $("serverUrl").value.trim(),
    apiKey: $("apiKey").value.trim(),
  });
  showStatus("✅ 设置已保存", "success");
});

$("btnTestConnection")?.addEventListener("click", async () => {
  const settings = await loadSettings();
  try {
    const resp = await fetch(`${settings.serverUrl}/health`, {
      signal: AbortSignal.timeout(5000),
    });
    if (resp.ok) {
      $("serverStatus").className = "status-dot online";
      $("serverStatusText").textContent = "已连接";
    } else {
      throw new Error(`Status ${resp.status}`);
    }
  } catch (err) {
    $("serverStatus").className = "status-dot offline";
    $("serverStatusText").textContent = `连接失败: ${err.message}`;
  }
});

// ── Event Binding ──

function bindEvents() {
  // Navigation
  $("btnSettings")?.addEventListener("click", showSettings);
  $("btnBack")?.addEventListener("click", () => {
    if (currentCapture?.title) showProduct(currentCapture);
    else showNoProduct();
  });
  $("btnRefresh")?.addEventListener("click", async () => {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tabs[0]?.id) {
      try {
        await chrome.tabs.sendMessage(tabs[0].id, { type: "TRIGGER_CAPTURE" });
        await new Promise((r) => setTimeout(r, 800));
        const resp = await chrome.runtime.sendMessage({ type: "GET_LAST_CAPTURE" });
        if (resp?.capture?.title) {
          currentCapture = resp.capture;
          showProduct(resp.capture);
        }
      } catch {
        // ignore
      }
    }
  });

  // Actions
  $("btnSendToICross")?.addEventListener("click", () => handleSendToICross(false));
  $("btnSendAndProcess")?.addEventListener("click", () => handleSendToICross(true));

  // Test capture
  $("btnTestCapture")?.addEventListener("click", async () => {
    const testData = {
      platform: "1688",
      url: "https://detail.1688.com/offer/test.html",
      title: "测试产品 - 无线蓝牙耳机",
      price: 45.0,
      originalPrice: 68.0,
      brand: "测试品牌",
      category: "蓝牙耳机",
      description: "高品质无线蓝牙耳机测试数据",
      images: [],
      attributes: { 颜色: "黑色", 连接方式: "蓝牙5.3", 续航: "30小时" },
      skus: [],
      stock: 100,
      sellerName: "测试店铺",
      sellerUrl: "",
      specs: [],
      rawHtml: "",
      capturedAt: Date.now(),
    };
    currentCapture = testData;
    showProduct(testData);
  });
}

// ── UI Helpers ──

function showStatus(message, type = "info") {
  const el = $("statusMessage");
  el.textContent = message;
  el.className = `status-message ${type}`;
}

function showLoading(text) {
  $("loadingOverlay").classList.remove("hidden");
  $("loadingText").textContent = text;
}

function hideLoading() {
  $("loadingOverlay").classList.add("hidden");
}

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
