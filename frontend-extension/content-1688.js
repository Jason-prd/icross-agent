/**
 * Content script for 1688.com product pages (detail.1688.com).
 * Extracts product data from the DOM and sends it to the background worker.
 */

(function () {
  "use strict";

  if (window.__ICROSS_1688_INJECTED) return;
  window.__ICROSS_1688_INJECTED = true;

  /**
   * Wait for an element to appear in the DOM.
   * @param {string} selector
   * @param {number} timeout
   * @returns {Promise<Element|null>}
   */
  function waitForElement(selector, timeout = 5000) {
    return new Promise((resolve) => {
      const el = document.querySelector(selector);
      if (el) return resolve(el);

      const observer = new MutationObserver(() => {
        const found = document.querySelector(selector);
        if (found) {
          observer.disconnect();
          resolve(found);
        }
      });
      observer.observe(document.body, { childList: true, subtree: true });

      setTimeout(() => {
        observer.disconnect();
        resolve(null);
      }, timeout);
    });
  }

  /**
   * Extract numeric price from a string.
   * @param {string} str
   * @returns {number|null}
   */
  function parsePrice(str) {
    if (!str) return null;
    const m = str.replace(/,/g, "").match(/(\d+(?:\.\d+)?)/);
    return m ? parseFloat(m[1]) : null;
  }

  /**
   * Extract product data from 1688 detail page.
   * @returns {import('./lib/types.js').CapturedProduct}
   */
  function extractProduct() {
    const url = window.location.href;

    // ── Title ──
    const titleEl =
      document.querySelector(".detail-title") ||
      document.querySelector(".title-text") ||
      document.querySelector("h1.title") ||
      document.querySelector("[data-title]") ||
      document.querySelector(".mod-detail-title .d-title");
    const title = titleEl?.textContent?.trim() || document.title.replace(/_1688.*/, "").trim() || "";

    // ── Price ──
    const priceEl =
      document.querySelector(".price-range") ||
      document.querySelector(".detail-price") ||
      document.querySelector("[data-price]") ||
      document.querySelector(".price .price-num");
    const priceText = priceEl?.textContent?.trim() || priceEl?.getAttribute("data-price") || "";
    const price = parsePrice(priceText);

    const originalPriceEl =
      document.querySelector(".original-price") ||
      document.querySelector(".detail-original-price");
    const originalPrice = parsePrice(originalPriceEl?.textContent?.trim());

    // ── Images ──
    const imageEls =
      document.querySelectorAll(".detail-gallery img, .mod-detail-gallery img, " +
        ".nav-image-gallery img, .detail-gallery-item img, " +
        "[data-image-url], .tb-img img, .img-content img");
    const images = [];
    const seen = new Set();
    imageEls.forEach((img) => {
      const src =
        img.getAttribute("data-image-url") ||
        img.getAttribute("data-src") ||
        img.getAttribute("src") ||
        img.getAttribute("data-lazy-src") ||
        "";
      const clean = src.replace(/^\/\//, "https://").split("?")[0];
      if (clean && !seen.has(clean) && !clean.includes("data:image")) {
        seen.add(clean);
        images.push(clean);
      }
    });

    // ── Attributes / Specs ──
    const attributes = {};
    const specRows =
      document.querySelectorAll(".detail-attributes tr, .mod-detail-attributes tr, " +
        ".spec-item, .attr-item, .tab-content tr, .attributes-table tr");
    specRows.forEach((row) => {
      const th = row.querySelector("th, .attr-name, .spec-name");
      const td = row.querySelector("td, .attr-value, .spec-value");
      if (th && td) {
        const key = th.textContent.trim().replace(/[：:]/g, "");
        const val = td.textContent.trim();
        if (key && val) attributes[key] = val;
      }
    });

    // ── Description ──
    const descEl =
      document.querySelector(".detail-desc") ||
      document.querySelector(".mod-detail-desc") ||
      document.querySelector("[data-description]");
    const description = descEl?.textContent?.trim()?.slice(0, 2000) || "";

    // ── Seller info ──
    const sellerEl =
      document.querySelector(".company-name a, .seller-name a, .shop-name a, " +
        ".mod-company .company-name, .store-name a");
    const sellerName = sellerEl?.textContent?.trim() || "";
    const sellerUrl = sellerEl?.getAttribute("href") || "";

    // ── SKUs (spec options) ──
    const skus = [];
    const skuOptions = document.querySelectorAll(".sku-attr, .prop-option, .sku-item, " +
      ".offer-sku-item, .sku-option, .attr-option");
    if (skuOptions.length > 0) {
      const seenSkus = new Set();
      skuOptions.forEach((opt) => {
        const label =
          opt.querySelector("label, .sku-name, .prop-name")?.textContent?.trim() ||
          opt.getAttribute("title") ||
          opt.textContent?.trim() ||
          "";
        if (label && !seenSkus.has(label)) {
          seenSkus.add(label);
          const skuPrice = parsePrice(
            opt.querySelector(".price, .sku-price")?.textContent?.trim()
          );
          skus.push({
            name: label,
            attributes: { 规格: label },
            price: skuPrice,
            stock: 0,
            images: [],
          });
        }
      });
    }

    // ── Stock ──
    const stockEl =
      document.querySelector(".stock-number, .detail-stock, [data-stock]");
    const stock = parseInt(stockEl?.textContent?.trim() || stockEl?.getAttribute("data-stock") || "0", 10) || 0;

    // ── Category ──
    const breadcrumbLinks = document.querySelectorAll(".breadcrumb a, .detail-breadcrumb a, " +
      ".mod-breadcrumb a");
    let category = "";
    breadcrumbLinks.forEach((a) => {
      const t = a.textContent.trim();
      if (t && !t.includes("首页") && !t.includes("全部")) {
        category = t; // last non-home breadcrumb
      }
    });

    return {
      platform: "1688",
      url,
      title,
      price,
      originalPrice,
      brand: sellerName,
      category,
      description,
      images,
      attributes,
      skus,
      stock,
      sellerName,
      sellerUrl,
      specs: Object.entries(attributes).map(([name, value]) => ({ name, value })),
      rawHtml: "",
      capturedAt: Date.now(),
    };
  }

  // ── Send to background on page load ──
  (async () => {
    // Wait a moment for dynamic content to settle
    await new Promise((r) => setTimeout(r, 1500));
    await waitForElement(".detail-title, .title-text, .price-range", 4000);

    const product = extractProduct();
    if (!product.title && !product.price) {
      console.log("[iCross] 1688: Could not extract product data");
      return;
    }

    // Notify background script (fire-and-forget)
    chrome.runtime.sendMessage({
      type: "PRODUCT_CAPTURED",
      payload: product,
    }).catch(() => {
      // Background may not be listening
    });

    console.log("[iCross] 1688: Product captured", product.title?.slice(0, 50));
  })();
})();
