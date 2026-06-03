/**
 * Local storage wrapper for the extension using chrome.storage.local.
 */

const KEYS = {
  CAPTURES: "captures",
  SETTINGS: "settings",
  LAST_CAPTURE: "lastCapture",
};

/**
 * Save a capture to local history.
 * @param {import('./types.js').CapturedProduct} product
 * @returns {Promise<void>}
 */
export async function saveCaptureLocally(product) {
  const { captures = [] } = await chrome.storage.local.get([KEYS.CAPTURES]);

  captures.unshift({
    ...product,
    capturedAt: Date.now(),
    localId: `local_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
  });

  // Keep only latest 50
  if (captures.length > 50) captures.length = 50;

  await chrome.storage.local.set({
    [KEYS.CAPTURES]: captures,
    [KEYS.LAST_CAPTURE]: captures[0],
  });
}

/**
 * Get capture history.
 * @param {number} limit
 * @returns {Promise<import('./types.js').CapturedProduct[]>}
 */
export async function getCaptureHistory(limit = 20) {
  const { captures = [] } = await chrome.storage.local.get([KEYS.CAPTURES]);
  return captures.slice(0, limit);
}

/**
 * Get the last captured product.
 * @returns {Promise<import('./types.js').CapturedProduct|null>}
 */
export async function getLastCapture() {
  const { lastCapture = null } = await chrome.storage.local.get([KEYS.LAST_CAPTURE]);
  return lastCapture;
}

/**
 * Save settings.
 * @param {Partial<import('./types.js').AppSettings>} settings
 * @returns {Promise<void>}
 */
export async function saveSettings(settings) {
  const existing = await chrome.storage.local.get([KEYS.SETTINGS]);
  const merged = { ...(existing.settings || {}), ...settings };
  await chrome.storage.local.set({ [KEYS.SETTINGS]: merged });
}

/**
 * Load settings.
 * @returns {Promise<import('./types.js').AppSettings>}
 */
export async function loadSettings() {
  const { settings = {} } = await chrome.storage.local.get([KEYS.SETTINGS]);
  return {
    serverUrl: settings.serverUrl || "http://localhost:8000",
    apiKey: settings.apiKey || "",
  };
}

/**
 * Update the server-side capture ID for a local capture.
 * @param {string} localId
 * @param {string} serverCaptureId
 * @returns {Promise<void>}
 */
export async function linkServerCapture(localId, serverCaptureId) {
  const { captures = [] } = await chrome.storage.local.get([KEYS.CAPTURES]);
  const updated = captures.map((c) =>
    c.localId === localId ? { ...c, serverCaptureId } : c
  );
  await chrome.storage.local.set({ [KEYS.CAPTURES]: updated });
}
