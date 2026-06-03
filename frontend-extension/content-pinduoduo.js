/**
 * Content script for Pinduoduo product pages.
 * Covers both PC (pinduoduo.com) and mobile (mobile.yangkeduo.com).
 */

(function () {
  "use strict";

  if (window.__ICROSS_PDD_INJECTED) return;
  window.__ICROSS_PDD_INJECTED = true;

  function parsePrice(str) {
    if (!str) return null;
    const m = str.replace(/,/g, "").match(/(\d+(?:\.\d+)?)/);
    return m ? parseFloat(m[1]) : null;
  }

  function extractProduct() {
    const url = window.location.href;
    const isMobile = url.includes("mobile.yangkeduo.com");
    const isPc = url.includes("pinduoduo.com");

    // ── Title ──
    let title = "";
    if (isMobile) {
      const el = document.querySelector(".product-title") ||
        document.querySelector("[data-name]") ||
        document.querySelector(".item-title");
      title = el?.textContent?.trim() || "";
    } else {
      const el = document.querySelector(".goods-title") ||
        document.querySelector(".product-title") ||
        document.querySelector("h1");
      title = el?.textContent?.trim() || "";
    }
    if (!title) title = document.title.replace(/-\s*拼多多.*/, "").trim();

    // ── Price ──
    let price = null;
    let originalPrice = null;
    if (isMobile) {
      const priceEl = document.querySelector(".product-price") ||
        document.querySelector(".price") ||
        document.querySelector("[data-price]");
      price = parsePrice(priceEl?.textContent?.trim());

      const origEl = document.querySelector(".original-price, .market-price");
      originalPrice = parsePrice(origEl?.textContent?.trim());
    } else {
      const priceEl = document.querySelector(".goods-price") ||
        document.querySelector(".price") ||
        document.querySelector("[data-price]");
      price = parsePrice(priceEl?.textContent?.trim());
    }

    // ── Images ──
    const images = [];
    const seen = new Set();
    const imgSelectors = isMobile
      ? ".product-gallery img, .swiper-slide img, .gallery img, [data-src]"
      : ".goods-gallery img, .product-gallery img, .detail-gallery img, [data-src]";

    document.querySelectorAll(imgSelectors).forEach((img) => {
      const src = img.getAttribute("data-src") || img.getAttribute("src") || "";
      const clean = src.replace(/^\/\//, "https://").split("?")[0];
      if (clean && !seen.has(clean) && !clean.includes("data:image") && !clean.includes(".webp")) {
        seen.add(clean);
        images.push(clean);
      }
    });

    // ── Attributes / Specs ──
    const attributes = {};
    const specSelectors = isMobile
      ? ".spec-item, .attr-item, .product-params tr"
      : ".detail-params tr, .product-param tr, .spec-table tr";

    document.querySelectorAll(specSelectors).forEach((row) => {
      const th = row.querySelector("th, .param-name, .spec-name, .attr-name");
      const td = row.querySelector("td, .param-value, .spec-value, .attr-value");
      if (th && td) {
        const key = th.textContent.trim().replace(/[：:]/g, "");
        const val = td.textContent.trim();
        if (key && val) attributes[key] = val;
      }
    });

    // ── Description ──
    const descEl = document.querySelector(".product-desc, .detail-desc, .goods-desc");
    const description = descEl?.textContent?.trim()?.slice(0, 2000) || "";

    // ── Seller ──
    const sellerEl = document.querySelector(".seller-name, .shop-name, .store-name");
    const sellerName = sellerEl?.textContent?.trim() || "";

    // ── SKUs ──
    const skus = [];
    const skuSelectors = isMobile
      ? ".sku-item, .prop-item, .spec-option, .goods-sku-item"
      : ".sku-option, .prop-item, .goods-spec-item";

    document.querySelectorAll(skuSelectors).forEach((opt) => {
      const label = opt.textContent?.trim() || opt.getAttribute("title") || "";
      if (label) {
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

    return {
      platform: "pinduoduo",
      url,
      title,
      price,
      originalPrice,
      brand: sellerName,
      category: "",
      description,
      images,
      attributes,
      skus,
      stock: 0,
      sellerName,
      sellerUrl: "",
      specs: Object.entries(attributes).map(([name, value]) => ({ name, value })),
      rawHtml: "",
      capturedAt: Date.now(),
    };
  }

  (async () => {
    await new Promise((r) => setTimeout(r, 2000));

    const product = extractProduct();
    if (!product.title && !product.price) {
      console.log("[iCross] Pinduoduo: Could not extract product data");
      return;
    }

    chrome.runtime.sendMessage({
      type: "PRODUCT_CAPTURED",
      payload: product,
    }).catch(() => {});

    console.log("[iCross] Pinduoduo: Product captured", product.title?.slice(0, 50));
  })();
})();
