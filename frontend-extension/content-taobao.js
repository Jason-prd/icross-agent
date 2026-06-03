/**
 * Content script for Taobao/Tmall product pages.
 * Covers detail.tmall.com and item.taobao.com.
 */

(function () {
  "use strict";

  if (window.__ICROSS_TB_INJECTED) return;
  window.__ICROSS_TB_INJECTED = true;

  function parsePrice(str) {
    if (!str) return null;
    const m = str.replace(/,/g, "").match(/(\d+(?:\.\d+)?)/);
    return m ? parseFloat(m[1]) : null;
  }

  function extractProduct() {
    const url = window.location.href;
    const isTmall = url.includes("tmall.com");

    // ── Title ──
    let title = "";
    if (isTmall) {
      const el = document.querySelector(".tb-detail-hd h1") ||
        document.querySelector(".product-title h1") ||
        document.querySelector("[data-title]");
      title = el?.textContent?.trim() || "";
    } else {
      const el = document.querySelector(".tb-main-title") ||
        document.querySelector("h1.tb-item-title") ||
        document.querySelector(".item-title");
      title = el?.textContent?.trim() || el?.getAttribute("title")?.trim() || "";
    }
    if (!title) {
      title = document.title
        .replace(/-[\s\S]*$/, "")
        .replace(/\[淘\d*\]/, "")
        .trim();
    }

    // ── Price ──
    let price = null;
    let originalPrice = null;
    if (isTmall) {
      const priceEl = document.querySelector(".tm-price, .tb-rmb-num, [data-price]");
      price = parsePrice(priceEl?.textContent?.trim());
      const origEl = document.querySelector(".tm-original-price, .tb-original-price");
      originalPrice = parsePrice(origEl?.textContent?.trim());
    } else {
      const priceEl = document.querySelector(".tb-rmb-num, .price .tb-rmb, [data-price]");
      price = parsePrice(priceEl?.textContent?.trim());
    }

    // ── Images ──
    const images = [];
    const seen = new Set();
    const imgSelectors = isTmall
      ? "#J_ImgBooth img, .tb-gallery img, .detail-gallery img, .product-gallery img, [data-src]"
      : "#J_ImgBooth img, .tb-gallery img, .detail-gallery img, .product-img-box img";

    document.querySelectorAll(imgSelectors).forEach((img) => {
      const src = img.getAttribute("data-src") ||
        img.getAttribute("src") ||
        img.getAttribute("data-ks-lazyload") ||
        "";
      // Tmall uses // prefix
      const clean = src.replace(/^\/\//, "https://").split("?")[0];
      // Filter thumbnails: get the full-size version
      const full = clean.replace(/_\d+x\d+\.jpg/, ".jpg").replace(/_\d+x\d+\.webp/, ".webp");
      if (full && !seen.has(full) && !full.includes("data:image")) {
        seen.add(full);
        images.push(full);
      }
    });

    // ── Attributes / Specs ──
    const attributes = {};
    const specSelectors = isTmall
      ? ".tb-attributes tr, .attributes-table tr, .Ptable tr, .spec-table tr"
      : ".attributes tr, .J_AttrTable tr, .spec-table tr, .item-attributes tr";

    document.querySelectorAll(specSelectors).forEach((row) => {
      const th = row.querySelector("th, .attr-name, .spec-name, .tb-attribute-name");
      const td = row.querySelector("td, .attr-value, .spec-value, .tb-attribute-value");
      if (th && td) {
        const key = th.textContent.trim().replace(/[：:]/g, "");
        const val = td.textContent.trim();
        if (key && val) attributes[key] = val;
      }
    });

    // ── Description ──
    const descEl = document.querySelector("#description, .detail-desc, .tb-detail-desc");
    const description = descEl?.textContent?.trim()?.slice(0, 2000) || "";

    // ── Seller ──
    const sellerEl = document.querySelector(".seller-name a, .J_ShopInfo a, .shop-name a, " +
      ".tb-shop-name a, .shop-nick a");
    const sellerName = sellerEl?.textContent?.trim() || sellerEl?.getAttribute("title")?.trim() || "";

    // ── SKUs ──
    const skus = [];
    const skuSelectors = isTmall
      ? ".tb-sku .sku-item, .J_TSaleProp li, .prop-item, .sku-option"
      : ".J_TSaleProp li, .sku-item, .prop-item";

    document.querySelectorAll(skuSelectors).forEach((opt) => {
      const label = opt.textContent?.trim() || opt.getAttribute("title") || "";
      const isActive = opt.classList.contains("active") || opt.classList.contains("selected");
      if (label && isActive) {
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

    // ── Category ──
    const breadcrumbLinks = document.querySelectorAll(".breadcrumb a, .tb-breadcrumb a, " +
      ".detail-breadcrumb a");
    let category = "";
    breadcrumbLinks.forEach((a) => {
      const t = a.textContent.trim();
      if (t && !t.includes("首页") && !t.includes("所有分类")) {
        category = t;
      }
    });

    return {
      platform: "taobao",
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
      stock: 0,
      sellerName,
      sellerUrl: "",
      specs: Object.entries(attributes).map(([name, value]) => ({ name, value })),
      rawHtml: "",
      capturedAt: Date.now(),
    };
  }

  (async () => {
    await new Promise((r) => setTimeout(r, 1500));

    const product = extractProduct();
    if (!product.title && !product.price) {
      console.log("[iCross] Taobao: Could not extract product data");
      return;
    }

    chrome.runtime.sendMessage({
      type: "PRODUCT_CAPTURED",
      payload: product,
    }).catch(() => {});

    console.log("[iCross] Taobao: Product captured", product.title?.slice(0, 50));
  })();
})();
