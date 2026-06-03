/**
 * API client for communicating with the iCross backend.
 */

const DEFAULTS = {
  serverUrl: "http://localhost:8000",
  timeout: 15000,
};

/**
 * @returns {Promise<{serverUrl: string, apiKey: string}>}
 */
async function getSettings() {
  return new Promise((resolve) => {
    chrome.storage.local.get(["serverUrl", "apiKey"], (items) => {
      resolve({
        serverUrl: items.serverUrl || DEFAULTS.serverUrl,
        apiKey: items.apiKey || "",
      });
    });
  });
}

/**
 * Submit a captured product to the iCross backend.
 * @param {import('./types.js').CapturedProduct} product
 * @returns {Promise<{success: boolean, capture: import('./types.js').CaptureRecord}>}
 */
export async function submitCapture(product) {
  const { serverUrl, apiKey } = await getSettings();

  const body = {
    platform: product.platform,
    product_url: product.url,
    title: product.title || "",
    price: product.price,
    original_price: product.originalPrice,
    brand: product.brand || "",
    category: product.category || "",
    description: product.description || "",
    images: product.images || [],
    attributes: product.attributes || {},
    skus: product.skus || [],
    stock: product.stock || 0,
    seller_name: product.sellerName || "",
    seller_url: product.sellerUrl || "",
    specs: product.specs || [],
    raw_html: product.rawHtml || "",
  };

  const headers = { "Content-Type": "application/json" };
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

  const resp = await fetch(`${serverUrl}/api/extension/capture`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(DEFAULTS.timeout),
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Server ${resp.status}: ${text.slice(0, 200)}`);
  }

  return resp.json();
}

/**
 * Get capture details by ID.
 * @param {string} captureId
 * @returns {Promise<import('./types.js').CaptureRecord>}
 */
export async function getCapture(captureId) {
  const { serverUrl, apiKey } = await getSettings();
  const headers = {};
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

  const resp = await fetch(`${serverUrl}/api/extension/captures/${captureId}`, {
    headers,
    signal: AbortSignal.timeout(DEFAULTS.timeout),
  });

  if (!resp.ok) throw new Error(`Failed to get capture: ${resp.status}`);
  return resp.json();
}

/**
 * Process a capture (trigger pipeline).
 * @param {string} captureId
 * @param {Object} options
 * @returns {Promise<Object>}
 */
export async function processCapture(captureId, options = {}) {
  const { serverUrl, apiKey } = await getSettings();
  const headers = { "Content-Type": "application/json" };
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

  const body = {
    auto_generate_listing: options.autoGenerateListing ?? true,
    auto_calculate_price: options.autoCalculatePrice ?? true,
    auto_create_draft: options.autoCreateDraft ?? false,
  };

  const resp = await fetch(
    `${serverUrl}/api/extension/captures/${captureId}/process`,
    {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(DEFAULTS.timeout),
    }
  );

  if (!resp.ok) throw new Error(`Failed to process: ${resp.status}`);
  return resp.json();
}

/**
 * List captures with optional filters.
 * @param {Object} filters
 * @returns {Promise<{captures: import('./types.js').CaptureRecord[], total: number}>}
 */
export async function listCaptures(filters = {}) {
  const { serverUrl, apiKey } = await getSettings();
  const headers = {};
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;

  const params = new URLSearchParams();
  if (filters.platform) params.set("platform", filters.platform);
  if (filters.status) params.set("status", filters.status);
  if (filters.limit) params.set("limit", String(filters.limit));

  const url = `${serverUrl}/api/extension/captures?${params}`;
  const resp = await fetch(url, {
    headers,
    signal: AbortSignal.timeout(DEFAULTS.timeout),
  });

  if (!resp.ok) throw new Error(`Failed to list captures: ${resp.status}`);
  return resp.json();
}
