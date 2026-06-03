/**
 * Shared types for the iCross browser extension.
 * Used by content scripts, background worker, and popup.
 */

/**
 * @typedef {Object} CapturedProduct
 * @property {string} platform - "1688" | "pinduoduo" | "taobao"
 * @property {string} url - Product page URL
 * @property {string} title - Product title
 * @property {number|null} price - Current price (yuan)
 * @property {number|null} originalPrice - Original/listed price
 * @property {string} brand - Brand name
 * @property {string} category - Product category
 * @property {string} description - Product description
 * @property {string[]} images - Image URLs
 * @property {Object<string,string>} attributes - Key-value attributes
 * @property {CapturedSKU[]} skus - SKU variants
 * @property {number} stock - Total stock count
 * @property {string} sellerName - Seller/shop name
 * @property {string} sellerUrl - Seller page URL
 * @property {Object[]} specs - Spec table [{name, value}]
 * @property {string} rawHtml - Raw HTML for fallback parsing
 * @property {number} capturedAt - Timestamp
 */

/**
 * @typedef {Object} CapturedSKU
 * @property {string} name - SKU name
 * @property {Object<string,string>} attributes - SKU attributes
 * @property {number|null} price - SKU price
 * @property {number} stock - SKU stock
 * @property {string[]} images - SKU images
 */

/**
 * @typedef {'captured'|'processing'|'parsed'|'drafted'|'error'} CaptureStatus
 */

/**
 * @typedef {Object} CaptureRecord
 * @property {string} id - Server-side capture ID
 * @property {string} platform
 * @property {string} productUrl
 * @property {string} status - CaptureStatus
 * @property {Object} rawData - Original scraped data
 * @property {Object|null} parsedData - SPU/SKU after processing
 * @property {string|null} draftId - iCross draft ID
 * @property {string|null} error - Error message if failed
 * @property {string} createdAt - ISO date
 */

/**
 * @typedef {Object} AppSettings
 * @property {string} serverUrl - iCross backend URL (default: http://localhost:8000)
 * @property {string} apiKey - API key for authentication
 */

export {};
