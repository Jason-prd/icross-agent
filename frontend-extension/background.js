/**
 * Background service worker for the iCross Browser Extension.
 *
 * Responsibilities:
 *   - Listen for PRODUCT_CAPTURED messages from content scripts
 *   - Store captures locally via chrome.storage
 *   - Sync captures to iCross backend
 *   - Manage context menus
 *   - Handle offline queue (retry failed syncs)
 */

import { submitCapture } from "./lib/api.js";
import { saveCaptureLocally, linkServerCapture, getLastCapture } from "./lib/storage.js";

// ── Context Menus ───────────────────────────────────────────────────

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "icross-capture",
    title: "发送到 iCross 选品",
    contexts: ["link", "image", "page"],
  });

  chrome.contextMenus.create({
    id: "icross-capture-link",
    title: "抓取此链接产品",
    contexts: ["link"],
  });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === "icross-capture" && tab?.id) {
    chrome.tabs.sendMessage(tab.id, { type: "TRIGGER_CAPTURE" }).catch(() => {});
  }
  if (info.menuItemId === "icross-capture-link" && info.linkUrl) {
    // Open link in new tab to capture
    chrome.tabs.create({ url: info.linkUrl, active: false }, (newTab) => {
      // Wait for page to load, then trigger capture
      const listener = (tabId, changeInfo) => {
        if (tabId === newTab.id && changeInfo.status === "complete") {
          chrome.tabs.sendMessage(tabId, { type: "TRIGGER_CAPTURE" }).catch(() => {});
          chrome.tabs.onUpdated.removeListener(listener);
        }
      };
      chrome.tabs.onUpdated.addListener(listener);
    });
  }
});

// ── Message Handler ─────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case "PRODUCT_CAPTURED":
      handleProductCaptured(message.payload, sender)
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ error: err.message }));
      return true; // Keep channel open for async response

    case "GET_LAST_CAPTURE":
      getLastCapture().then((c) => sendResponse({ capture: c })).catch(() => sendResponse({ capture: null }));
      return true;

    case "SYNC_NOW":
      syncPendingCaptures()
        .then((r) => sendResponse(r))
        .catch((e) => sendResponse({ error: e.message }));
      return true;
  }
});

// ── Capture Handling ────────────────────────────────────────────────

/**
 * Handle a newly captured product from a content script.
 * 1. Save locally
 * 2. Attempt to sync to iCross backend
 * 3. Queue if sync fails
 */
async function handleProductCaptured(product, sender) {
  // Save locally
  await saveCaptureLocally(product);

  // Try to sync to iCross backend
  try {
    const result = await submitCapture(product);
    if (result?.capture?.id) {
      await linkServerCapture(product.localId, result.capture.id);
      await triggerNotification(product, result.capture);
    }
    return { success: true, captureId: result?.capture?.id };
  } catch (err) {
    console.warn("[iCross] Failed to sync capture to server:", err.message);
    // Queue for later retry
    await queueForRetry(product);
    return { success: false, queued: true, error: err.message };
  }
}

// ── Offline Queue ───────────────────────────────────────────────────

const QUEUE_KEY = "pendingSync";

async function queueForRetry(product) {
  const { [QUEUE_KEY]: queue = [] } = await chrome.storage.local.get(QUEUE_KEY);
  queue.push({
    ...product,
    queuedAt: Date.now(),
    retries: 0,
  });
  // Keep max 100
  if (queue.length > 100) queue.splice(0, queue.length - 100);
  await chrome.storage.local.set({ [QUEUE_KEY]: queue });
}

async function syncPendingCaptures() {
  const { [QUEUE_KEY]: queue = [] } = await chrome.storage.local.get(QUEUE_KEY);
  if (queue.length === 0) return { synced: 0, total: 0 };

  const remaining = [];
  let synced = 0;

  for (const item of queue) {
    if (item.retries >= 5) {
      remaining.push(item); // Give up after 5 retries
      continue;
    }
    try {
      const result = await submitCapture(item);
      if (result?.capture?.id) {
        synced++;
      } else {
        item.retries++;
        remaining.push(item);
      }
    } catch {
      item.retries++;
      remaining.push(item);
    }
  }

  await chrome.storage.local.set({ [QUEUE_KEY]: remaining });
  return { synced, total: queue.length, remaining: remaining.length };
}

// ── Notification ────────────────────────────────────────────────────

async function triggerNotification(product, capture) {
  try {
    await chrome.notifications.create({
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: "iCross 选品助手",
      message: `已捕获: ${(product.title || "").slice(0, 40)}`,
      contextMessage: capture.status === "parsed" ? "自动解析完成" : "已发送到 iCross",
    });
  } catch {
    // Notifications API may not be available
  }
}

// ── Periodic sync ───────────────────────────────────────────────────

// Retry queued captures every 5 minutes
chrome.alarms.create("syncPending", { periodInMinutes: 5 });

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "syncPending") {
    syncPendingCaptures().then((r) => {
      if (r.synced > 0) {
        console.log(`[iCross] Synced ${r.synced} pending captures`);
      }
    });
  }
});
