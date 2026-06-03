"""Ozon product cost & profit calculation engine.

Based on Ozon platform rules:
- Commission rates by category, price tier, and sales model (rFBS/FBP)
- Logistics costs by warehouse and delivery speed
- Customs duties for imports >€200
- Return processing fees
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Literal

# ── Commission rate table ───────────────────────────────────────
# Based on Ozon 各类商品销售佣金标准 (自 2025年8月5日起)
# Format: category -> {price_tier -> {rFBS_rate, FBP_rate}}
# price_tier: "basic"(≤1500), "mid"(1501-5000), "high"(>5000)

COMMISSION_RATES: dict[str, dict[str, dict[str, float]]] = {
    # 美容 - 内衣和袜类产品
    "内衣和袜类产品": {
        "basic":  {"rFBS": 12.0, "FBP": 11.0},
        "mid":    {"rFBS": 14.0, "FBP": 13.0},
        "high":   {"rFBS": 22.5, "FBP": 21.5},
    },
    "季节性内衣和袜类产品": {
        "basic":  {"rFBS": 12.0, "FBP": 11.0},
        "mid":    {"rFBS": 14.0, "FBP": 13.0},
        "high":   {"rFBS": 22.5, "FBP": 21.5},
    },
    "美容设备": {
        "basic":  {"rFBS": 12.0, "FBP": 11.0},
        "mid":    {"rFBS": 14.0, "FBP": 13.0},
        "high":   {"rFBS": 16.0, "FBP": 15.0},
    },
    "美容与健康": {
        "basic":  {"rFBS": 12.0, "FBP": 11.0},
        "mid":    {"rFBS": 14.0, "FBP": 13.0},
        "high":   {"rFBS": 18.0, "FBP": 17.0},
    },
    "鞋类": {
        "basic":  {"rFBS": 12.0, "FBP": 11.0},
        "mid":    {"rFBS": 12.0, "FBP": 11.0},
        "high":   {"rFBS": 12.0, "FBP": 11.0},
    },
    "季节性鞋类": {
        "basic":  {"rFBS": 12.0, "FBP": 11.0},
        "mid":    {"rFBS": 12.0, "FBP": 11.0},
        "high":   {"rFBS": 12.0, "FBP": 11.0},
    },
    "服装和配饰": {
        "basic":  {"rFBS": 12.0, "FBP": 11.0},
        "mid":    {"rFBS": 14.0, "FBP": 13.0},
        "high":   {"rFBS": 20.5, "FBP": 19.5},
    },
    "季节性服装及配饰": {
        "basic":  {"rFBS": 12.0, "FBP": 11.0},
        "mid":    {"rFBS": 14.0, "FBP": 13.0},
        "high":   {"rFBS": 20.5, "FBP": 19.5},
    },
    "外套": {
        "basic":  {"rFBS": 10.0, "FBP": 9.0},
        "mid":    {"rFBS": 10.0, "FBP": 9.0},
        "high":   {"rFBS": 10.0, "FBP": 9.0},
    },
    "专业美容设备": {
        "basic":  {"rFBS": 7.5, "FBP": 6.5},
        "mid":    {"rFBS": 7.5, "FBP": 6.5},
        "high":   {"rFBS": 7.5, "FBP": 6.5},
    },
    # Default for categories not listed
    "__default__": {
        "basic":  {"rFBS": 12.0, "FBP": 11.0},
        "mid":    {"rFBS": 14.0, "FBP": 13.0},
        "high":   {"rFBS": 18.0, "FBP": 17.0},
    },
}

# ── Logistics cost estimation ──────────────────────────────────
# 自营物流配送价格表（CNY）
# 根据重量(g) 和 Ozon 售价(RUB) 匹配仓库，运费 = 票价 + 重量价 × 重量(g)
# Standard 模式

LOGISTICS_TIERS_STANDARD: list[dict] = [
    {"weight_g_min": 0, "weight_g_max": 500,     "price_rub_min": 1, "price_rub_max": 1500,       "warehouse": "Extra Small",    "base_fee": 2.95,  "price_per_g": 0.045},
    {"weight_g_min": 500, "weight_g_max": 250000, "price_rub_min": 1, "price_rub_max": 1500,       "warehouse": "Budget",         "base_fee": 21.85, "price_per_g": 0.025},
    {"weight_g_min": 0,   "weight_g_max": 2000,   "price_rub_min": 1500, "price_rub_max": 7000,   "warehouse": "Small",          "base_fee": 15.2,  "price_per_g": 0.034},
    {"weight_g_min": 2000,"weight_g_max": 250000, "price_rub_min": 1500, "price_rub_max": 7000,   "warehouse": "Big",            "base_fee": 36,    "price_per_g": 0.025},
    {"weight_g_min": 0,   "weight_g_max": 5000,   "price_rub_min": 7000, "price_rub_max": 250000, "warehouse": "Premier Small",  "base_fee": 22,    "price_per_g": 0.035},
    {"weight_g_min": 5000,"weight_g_max": 250000, "price_rub_min": 7000, "price_rub_max": 2500000,"warehouse": "Premier Big",    "base_fee": 62,    "price_per_g": 0.028},
]

LOGISTICS_TIERS_ECONOMY: list[dict] = [
    {"weight_g_min": 0, "weight_g_max": 500,     "price_rub_min": 1, "price_rub_max": 1500,       "warehouse": "Extra Small",    "base_fee": 2.95,  "price_per_g": 0.025},
    {"weight_g_min": 500, "weight_g_max": 250000, "price_rub_min": 1, "price_rub_max": 1500,       "warehouse": "Budget",         "base_fee": 22.4,  "price_per_g": 0.017},
    {"weight_g_min": 0,   "weight_g_max": 2000,   "price_rub_min": 1500, "price_rub_max": 7000,   "warehouse": "Small",          "base_fee": 15.2,  "price_per_g": 0.02375},
    {"weight_g_min": 2000,"weight_g_max": 250000, "price_rub_min": 1500, "price_rub_max": 7000,   "warehouse": "Big",            "base_fee": 36,    "price_per_g": 0.017},
    {"weight_g_min": 0,   "weight_g_max": 5000,   "price_rub_min": 7000, "price_rub_max": 250000, "warehouse": "Premier Small",  "base_fee": 22,    "price_per_g": 0.025},
    {"weight_g_min": 5000,"weight_g_max": 250000, "price_rub_min": 7000, "price_rub_max": 2500000,"warehouse": "Premier Big",    "base_fee": 62,    "price_per_g": 0.023},
]

# 旧常量保留（用于 backward compatibility，但不再被 calculate_max_purchase_price 使用）
LOGISTICS_COST_PER_KG: dict[str, float] = {
    "CEL": 28.0, "GUOO": 26.0, "RETS": 30.0, "UNI": 27.0, "Ural": 29.0, "Xingyuan": 25.0, "JDL": 30.0, "__default__": 28.0,
}
DELIVERY_COST_PER_KG: dict[str, float] = {
    "super_express": 45.0, "express": 35.0, "standard": 28.0, "economy": 20.0, "__default__": 28.0,
}


def detect_delivery_mode(delivery_type: str = "", is_express: bool = False) -> str:
    """Map Ozon delivery_type to internal mode (standard/economy).

    Args:
        delivery_type: Ozon API analytics.delivery_type value
        is_express: Ozon API posting.is_express flag

    Returns:
        "standard" or "economy"
    """
    if is_express:
        return "standard"
    dt = (delivery_type or "").lower()
    if dt in ("economy", "econom"):
        return "economy"
    return "standard"


def get_logistics_cost_cny(weight_g: float, selling_price_rub: float, delivery_mode: str = "standard") -> dict:
    """根据重量(g)和售价(RUB)匹配物流 tier，返回配送费(CNY)明细。

    Returns:
        dict with: cost_cny, warehouse, base_fee, price_per_g, tier_label
    """
    tiers = LOGISTICS_TIERS_STANDARD if delivery_mode == "standard" else LOGISTICS_TIERS_ECONOMY
    for tier in tiers:
        if (tier["weight_g_min"] <= weight_g < tier["weight_g_max"]
                and tier["price_rub_min"] <= selling_price_rub < tier["price_rub_max"]):
            cost_cny = tier["base_fee"] + tier["price_per_g"] * weight_g
            return {
                "cost_cny": round(cost_cny, 2),
                "warehouse": tier["warehouse"],
                "base_fee": tier["base_fee"],
                "price_per_g": tier["price_per_g"],
                "tier_label": f"{tier['warehouse']} ({weight_g}g / {selling_price_rub:.0f}RUB)",
            }
    # Fallback: 最大 tier
    last = tiers[-1]
    cost_cny = last["base_fee"] + last["price_per_g"] * weight_g
    return {
        "cost_cny": round(cost_cny, 2),
        "warehouse": last["warehouse"],
        "base_fee": last["base_fee"],
        "price_per_g": last["price_per_g"],
        "tier_label": f"{last['warehouse']} (fallback)",
    }

# ── Customs duty ──────────────────────────────────────────────
CUSTOMS_FREE_THRESHOLD_EUR = 200
CUSTOMS_FREE_THRESHOLD_KG = 31
CUSTOMS_DUTY_RATE = 0.15  # 15% of exceeding value
CUSTOMS_FIXED_FEE_RUB = 689

# Exchange rate (approximate)
USD_TO_RUB = 90.0
CNY_TO_RUB = 12.5
EUR_TO_RUB = 98.0


@dataclass
class ProductCostInput:
    """Input parameters for cost calculation."""
    # Product info
    purchase_price_cny: float           # 采购成本 (CNY, from 1688)
    weight_kg: float                    # 重量 (kg)
    category_name: str                  # Ozon 类目名称
    sales_model: Literal["rFBS", "FBP"] = "FBP"
    warehouse: str = "UNI"              # FBP warehouse
    delivery_speed: str = "standard"    # delivery speed

    # Additional costs (CNY)
    packaging_cost_cny: float = 2.0     # 包装成本
    return_reserve_pct: float = 2.0     # 退货预备金 (percentage of price)
    other_cost_cny: float = 3.0         # 其他费用 (标签、耗材等)

    # Exchange rate (optional)
    cny_to_rub: float = CNY_TO_RUB


@dataclass
class CostBreakdown:
    """Detailed cost breakdown."""
    purchase_price_rub: float           # 采购成本 (卢布)
    logistics_cost_rub: float           # 物流成本 (头程+尾程)
    commission_rub: float               # 平台佣金
    commission_rate: float              # 佣金率 (%)
    customs_duty_rub: float             # 关税
    return_reserve_rub: float           # 退货预备金
    packaging_cost_rub: float           # 包装成本
    other_cost_rub: float               # 其他费用
    total_cost_rub: float               # 总成本
    profit_rub: float                   # 净利润
    profit_margin_pct: float            # 利润率 (%)
    recommended_price_rub: float        # 建议售价
    price_tier: str = ""               # 价格档位


class OzonCostCalculator:
    """Ozon product cost and profit calculator."""

    def calculate(self, inp: ProductCostInput, target_margin: float = 20.0) -> CostBreakdown:
        """Calculate full cost breakdown and recommend price for target margin."""
        rub_exchange = inp.cny_to_rub

        # 1. Purchase cost in RUB
        purchase_rub = inp.purchase_price_cny * rub_exchange

        # 2. Estimate logistics cost (FBP: warehouse storage + delivery)
        wh_cost = LOGISTICS_COST_PER_KG.get(inp.warehouse, LOGISTICS_COST_PER_KG["__default__"])
        del_cost = DELIVERY_COST_PER_KG.get(inp.delivery_speed, DELIVERY_COST_PER_KG["__default__"])
        logistics_rub = (wh_cost + del_cost) * inp.weight_kg * rub_exchange / CNY_TO_RUB

        # 3. Estimate packaging and other costs
        packaging_rub = inp.packaging_cost_cny * rub_exchange
        other_rub = inp.other_cost_cny * rub_exchange

        # 4. Iterate to find price that achieves target margin
        #    (since commission depends on price tier)
        price = purchase_rub + logistics_rub + packaging_rub + other_rub
        price /= (1 - target_margin / 100)  # initial guess

        for _ in range(5):  # converge
            tier = self._get_price_tier(price)
            comm_rate = self._get_commission_rate(inp.category_name, tier, inp.sales_model)
            comm = price * comm_rate / 100

            customs = self._calc_customs(price)
            return_reserve = price * inp.return_reserve_pct / 100

            total = purchase_rub + logistics_rub + comm + customs + return_reserve + packaging_rub + other_rub
            profit = price - total
            margin = profit / price * 100 if price > 0 else 0

            # Adjust price to hit target margin
            if abs(margin - target_margin) > 0.5:
                price = total / (1 - target_margin / 100)
            else:
                break

        # Final calculation with converged price
        tier = self._get_price_tier(price)
        comm_rate = self._get_commission_rate(inp.category_name, tier, inp.sales_model)
        comm = price * comm_rate / 100
        customs = self._calc_customs(price)
        return_reserve = price * inp.return_reserve_pct / 100
        total = purchase_rub + logistics_rub + comm + customs + return_reserve + packaging_rub + other_rub
        profit = price - total
        margin = profit / price * 100 if price > 0 else 0

        return CostBreakdown(
            purchase_price_rub=round(purchase_rub, 2),
            logistics_cost_rub=round(logistics_rub, 2),
            commission_rub=round(comm, 2),
            commission_rate=comm_rate,
            customs_duty_rub=round(customs, 2),
            return_reserve_rub=round(return_reserve, 2),
            packaging_cost_rub=round(packaging_rub, 2),
            other_cost_rub=round(other_rub, 2),
            total_cost_rub=round(total, 2),
            profit_rub=round(profit, 2),
            profit_margin_pct=round(margin, 2),
            recommended_price_rub=round(price, 2),
            price_tier=tier,
        )

    def calculate_from_price(self, inp: ProductCostInput, selling_price_rub: float) -> CostBreakdown:
        """Calculate profit/margin given a fixed selling price."""
        rub_exchange = inp.cny_to_rub
        purchase_rub = inp.purchase_price_cny * rub_exchange
        wh_cost = LOGISTICS_COST_PER_KG.get(inp.warehouse, LOGISTICS_COST_PER_KG["__default__"])
        del_cost = DELIVERY_COST_PER_KG.get(inp.delivery_speed, DELIVERY_COST_PER_KG["__default__"])
        logistics_rub = (wh_cost + del_cost) * inp.weight_kg * rub_exchange / CNY_TO_RUB
        packaging_rub = inp.packaging_cost_cny * rub_exchange
        other_rub = inp.other_cost_cny * rub_exchange

        tier = self._get_price_tier(selling_price_rub)
        comm_rate = self._get_commission_rate(inp.category_name, tier, inp.sales_model)
        comm = selling_price_rub * comm_rate / 100
        customs = self._calc_customs(selling_price_rub)
        return_reserve = selling_price_rub * inp.return_reserve_pct / 100

        total = purchase_rub + logistics_rub + comm + customs + return_reserve + packaging_rub + other_rub
        profit = selling_price_rub - total
        margin = profit / selling_price_rub * 100 if selling_price_rub > 0 else 0

        return CostBreakdown(
            purchase_price_rub=round(purchase_rub, 2),
            logistics_cost_rub=round(logistics_rub, 2),
            commission_rub=round(comm, 2),
            commission_rate=comm_rate,
            customs_duty_rub=round(customs, 2),
            return_reserve_rub=round(return_reserve, 2),
            packaging_cost_rub=round(packaging_rub, 2),
            other_cost_rub=round(other_rub, 2),
            total_cost_rub=round(total, 2),
            profit_rub=round(profit, 2),
            profit_margin_pct=round(margin, 2),
            recommended_price_rub=round(selling_price_rub, 2),
            price_tier=tier,
        )

    def calculate_max_purchase_price(
        self,
        selling_price_cny: float,
        weight_kg: float,
        category_name: str = "",
        target_margin: float = 20.0,
        sales_model: str = "FBP",
        selling_price_rub: float | None = None,
        delivery_mode: str = "standard",
    ) -> dict:
        """Calculate max purchase price (CNY) for a target margin given selling price.

        针对一件代发场景: 已知 Ozon 售价、重量、类目，
        按自营物流价格表匹配配送费，反推最高采购成本（人民币）。

        Args:
            selling_price_cny: 售价折合人民币
            weight_kg: 重量(kg)
            category_name: Ozon 类目名（用于佣金率）
            target_margin: 目标利润率 %
            sales_model: FBP / rFBS
            selling_price_rub: Ozon 售价（卢布，用于物流 tier 匹配）
            delivery_mode: standard / economy

        Returns:
            dict with max_purchase_price_cny, profit_cny, cost_breakdown, etc.
        """
        rub_exchange = CNY_TO_RUB
        selling_price_rub = selling_price_rub or (selling_price_cny * rub_exchange)
        selling_price_rub = max(selling_price_rub, 1)

        tier = self._get_price_tier(selling_price_rub)
        comm_rate = self._get_commission_rate(category_name, tier, sales_model)
        comm = selling_price_rub * comm_rate / 100
        customs = self._calc_customs(selling_price_rub)
        return_reserve = selling_price_rub * 0.02
        packaging_rub = 2.0 * rub_exchange
        other_rub = 3.0 * rub_exchange

        # 新物流计算：按重量(g)和售价(RUB)匹配仓库 tier
        weight_g = weight_kg * 1000
        logistics_info = get_logistics_cost_cny(weight_g, selling_price_rub, delivery_mode)
        logistics_cny = logistics_info["cost_cny"]
        logistics_rub = logistics_cny * rub_exchange

        fixed_costs_rub = comm + customs + return_reserve + logistics_rub + packaging_rub + other_rub
        target_profit_rub = selling_price_rub * target_margin / 100
        max_purchase_rub = selling_price_rub - fixed_costs_rub - target_profit_rub

        return {
            "selling_price_cny": round(selling_price_cny, 2),
            "max_purchase_price_cny": round(max(0, max_purchase_rub / rub_exchange), 2),
            "max_purchase_price_rub": round(max(0, max_purchase_rub), 2),
            "profit_cny": round(max(0, target_profit_rub / rub_exchange), 2),
            "profit_margin_pct": target_margin,
            "profitable": max_purchase_rub > 0,
            "cost_breakdown": {
                "commission_pct": comm_rate,
                "commission_cny": round(comm / rub_exchange, 2),
                "logistics_cny": round(logistics_cny, 2),
                "customs_cny": round(customs / rub_exchange, 2),
                "return_reserve_cny": round(return_reserve / rub_exchange, 2),
                "packaging_cny": round(packaging_rub / rub_exchange, 2),
            },
            "logistics_detail": logistics_info,
        }

    def _get_price_tier(self, price_rub: float) -> str:
        if price_rub <= 1500:
            return "basic"
        elif price_rub <= 5000:
            return "mid"
        else:
            return "high"

    def _get_commission_rate(self, category: str, tier: str, model: str) -> float:
        """Get commission rate for a category/price tier/sales model."""
        cat_key = self._match_category(category)
        rates = COMMISSION_RATES.get(cat_key, COMMISSION_RATES["__default__"])
        tier_rates = rates.get(tier, rates["basic"])
        return tier_rates.get(model, tier_rates.get("FBP", 12.0))

    def _match_category(self, category: str) -> str:
        """Fuzzy-match the Ozon category name against known rate entries."""
        cat_lower = category.lower()
        for key in COMMISSION_RATES:
            if key == "__default__":
                continue
            if key.lower() in cat_lower or cat_lower in key.lower():
                return key
        return "__default__"

    def _calc_customs(self, price_rub: float) -> float:
        """Calculate customs duty if applicable."""
        price_eur = price_rub / EUR_TO_RUB
        if price_eur > CUSTOMS_FREE_THRESHOLD_EUR:
            excess = price_eur - CUSTOMS_FREE_THRESHOLD_EUR
            duty_eur = excess * CUSTOMS_DUTY_RATE
            duty_rub = duty_eur * EUR_TO_RUB + CUSTOMS_FIXED_FEE_RUB
            return duty_rub
        return 0.0


# Convenience functions for Agent tools

def calculate_product_cost(
    purchase_price_cny: float,
    weight_kg: float,
    category_name: str = "",
    target_margin: float = 20.0,
    sales_model: str = "FBP",
    warehouse: str = "UNI",
    delivery_speed: str = "standard",
) -> str:
    """Calculate product cost breakdown and recommend selling price."""
    calc = OzonCostCalculator()
    inp = ProductCostInput(
        purchase_price_cny=purchase_price_cny,
        weight_kg=weight_kg,
        category_name=category_name,
        sales_model=sales_model,  # type: ignore
        warehouse=warehouse,
        delivery_speed=delivery_speed,
    )
    result = calc.calculate(inp, target_margin)
    return json.dumps(asdict(result), ensure_ascii=False, indent=2)
