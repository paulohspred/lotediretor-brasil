from __future__ import annotations

import math
from typing import Any

FINANCE_SOLVER_VERSION = 'aitec-finance-v20.1'


def _percent(value: float, name: str) -> float:
    value = float(value)
    if value < 0 or value > 100:
        raise ValueError(f'{name} must be between 0 and 100')
    return value / 100.0


def _npv(cash_flows: list[dict], annual_discount_rate_percent: float) -> float:
    annual = float(annual_discount_rate_percent) / 100.0
    if annual <= -1:
        raise ValueError('annual discount rate must be > -100%')
    monthly = (1.0 + annual) ** (1.0 / 12.0) - 1.0
    total = 0.0
    for item in cash_flows:
        month = int(item['month'])
        amount = float(item['amount'])
        if month < 0:
            raise ValueError('cash flow month must be >= 0')
        total += amount / ((1.0 + monthly) ** month)
    return total


def _irr_monthly(cash_flows: list[dict]) -> float | None:
    flows_by_month: dict[int, float] = {}
    for item in cash_flows:
        month = int(item['month'])
        if month < 0:
            raise ValueError('cash flow month must be >= 0')
        flows_by_month[month] = flows_by_month.get(month, 0.0) + float(item['amount'])
    if not flows_by_month or not any(v < 0 for v in flows_by_month.values()) or not any(v > 0 for v in flows_by_month.values()):
        return None

    def value(rate: float) -> float:
        return sum(amount / ((1.0 + rate) ** month) for month, amount in flows_by_month.items())

    low = -0.999999
    high = 10.0
    f_low = value(low)
    f_high = value(high)
    if f_low == 0:
        return low
    if f_high == 0:
        return high
    if f_low * f_high > 0:
        return None
    for _ in range(160):
        mid = (low + high) / 2.0
        f_mid = value(mid)
        if abs(f_mid) <= 1e-9:
            return mid
        if f_low * f_mid <= 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
    return (low + high) / 2.0


def calculate_project_finance(
    unit_types: list[dict],
    construction_area_m2: float,
    land_cost: float,
    hard_cost_per_m2: float,
    soft_cost_percent_of_hard: float,
    contingency_percent_of_hard_soft: float,
    taxes_percent_of_vgv: float,
    sales_commission_percent_of_vgv: float,
    market_snapshot_id: str,
    cost_snapshot_id: str,
    other_capex: float = 0.0,
    cash_flows: list[dict] | None = None,
    annual_discount_rate_percent: float | None = None,
    min_margin_percent: float | None = None,
    max_total_cost: float | None = None,
) -> dict[str, Any]:
    """Calculate explicit-input development VGV/CAPEX and optional cash-flow metrics.

    Market and cost snapshot identifiers are mandatory provenance anchors. The
    solver never invents unit prices, construction costs, taxes, commission or
    discount rates.
    """
    if not str(market_snapshot_id).strip() or not str(cost_snapshot_id).strip():
        raise ValueError('market_snapshot_id and cost_snapshot_id are required')
    if construction_area_m2 <= 0 or land_cost < 0 or hard_cost_per_m2 < 0 or other_capex < 0:
        raise ValueError('invalid construction/cost input')
    soft_rate = _percent(soft_cost_percent_of_hard, 'soft_cost_percent_of_hard')
    contingency_rate = _percent(contingency_percent_of_hard_soft, 'contingency_percent_of_hard_soft')
    tax_rate = _percent(taxes_percent_of_vgv, 'taxes_percent_of_vgv')
    commission_rate = _percent(sales_commission_percent_of_vgv, 'sales_commission_percent_of_vgv')

    unit_results = []
    vgv = 0.0
    saleable_area = 0.0
    total_units = 0
    for index, raw in enumerate(unit_types):
        name = str(raw.get('name') or f'TYPE-{index + 1}')
        count = int(raw.get('count') or 0)
        area = float(raw.get('saleable_area_m2') or raw.get('area_m2') or 0)
        price_per_m2 = raw.get('price_per_m2')
        price_per_unit = raw.get('price_per_unit')
        if count < 0 or area <= 0:
            raise ValueError(f'invalid unit input:{name}')
        if price_per_m2 is None and price_per_unit is None:
            raise ValueError(f'unit {name} requires explicit price_per_m2 or price_per_unit')
        if price_per_unit is None:
            unit_price = area * float(price_per_m2)
        else:
            unit_price = float(price_per_unit)
        if unit_price < 0:
            raise ValueError(f'unit {name} price cannot be negative')
        revenue = count * unit_price
        vgv += revenue
        saleable_area += count * area
        total_units += count
        unit_results.append({
            'name': name,
            'count': count,
            'saleable_area_m2': area,
            'unit_price': round(unit_price, 2),
            'revenue': round(revenue, 2),
            'price_basis': 'price_per_unit' if price_per_unit is not None else 'price_per_m2',
        })

    hard_cost = float(construction_area_m2) * float(hard_cost_per_m2)
    soft_cost = hard_cost * soft_rate
    contingency = (hard_cost + soft_cost) * contingency_rate
    development_capex = float(land_cost) + hard_cost + soft_cost + contingency + float(other_capex)
    taxes = vgv * tax_rate
    commission = vgv * commission_rate
    total_cost = development_capex + taxes + commission
    profit = vgv - total_cost
    margin_percent = (profit / vgv * 100.0) if vgv > 0 else None
    saleable_efficiency = saleable_area / float(construction_area_m2)

    hard_results = []
    if min_margin_percent is not None:
        observed = -math.inf if margin_percent is None else margin_percent
        hard_results.append({
            'code': 'MIN_PROJECT_MARGIN',
            'status': 'PASS' if observed + 1e-9 >= float(min_margin_percent) else 'FAIL',
            'observed_percent': None if margin_percent is None else round(margin_percent, 6),
            'minimum_percent': float(min_margin_percent),
        })
    if max_total_cost is not None:
        hard_results.append({
            'code': 'MAX_TOTAL_COST',
            'status': 'PASS' if total_cost <= float(max_total_cost) + 1e-9 else 'FAIL',
            'observed': round(total_cost, 2),
            'maximum': float(max_total_cost),
        })

    cashflow_result = {'status': 'NOT_PROVIDED', 'npv': None, 'irr_monthly': None, 'irr_annual_percent': None}
    if cash_flows is not None:
        normalized = [{'month': int(item['month']), 'amount': float(item['amount'])} for item in cash_flows]
        irr_monthly = _irr_monthly(normalized)
        npv_value = None
        if annual_discount_rate_percent is not None:
            npv_value = _npv(normalized, float(annual_discount_rate_percent))
        irr_annual = None if irr_monthly is None else ((1.0 + irr_monthly) ** 12.0 - 1.0) * 100.0
        cashflow_result = {
            'status': 'CALCULATED',
            'npv': None if npv_value is None else round(npv_value, 2),
            'annual_discount_rate_percent': annual_discount_rate_percent,
            'irr_monthly': None if irr_monthly is None else round(irr_monthly, 8),
            'irr_annual_percent': None if irr_annual is None else round(irr_annual, 6),
            'cash_flows': normalized,
        }

    failed = any(item['status'] == 'FAIL' for item in hard_results)
    status = 'FAIL' if failed else ('PASS' if hard_results else 'CALCULATED')
    return {
        'status': status,
        'solver_version': FINANCE_SOLVER_VERSION,
        'provenance': {'market_snapshot_id': str(market_snapshot_id), 'cost_snapshot_id': str(cost_snapshot_id)},
        'unit_types': unit_results,
        'total_units': total_units,
        'saleable_area_m2': round(saleable_area, 2),
        'construction_area_m2': round(float(construction_area_m2), 2),
        'saleable_efficiency': round(saleable_efficiency, 6),
        'vgv': round(vgv, 2),
        'capex': {
            'land': round(float(land_cost), 2),
            'hard_cost': round(hard_cost, 2),
            'soft_cost': round(soft_cost, 2),
            'contingency': round(contingency, 2),
            'other': round(float(other_capex), 2),
            'development_capex': round(development_capex, 2),
            'taxes_on_vgv': round(taxes, 2),
            'sales_commission': round(commission, 2),
            'total_cost': round(total_cost, 2),
        },
        'profit': round(profit, 2),
        'margin_percent': None if margin_percent is None else round(margin_percent, 6),
        'cashflow': cashflow_result,
        'pareto_metrics': {
            'vgv': round(vgv, 2),
            'profit': round(profit, 2),
            'margin_percent': None if margin_percent is None else round(margin_percent, 6),
            'total_cost': round(total_cost, 2),
            'saleable_efficiency': round(saleable_efficiency, 6),
        },
        'hard_results': hard_results,
        'limitations': [
            'Memória financeira determinística sobre preços, custos, impostos e taxas explicitamente fornecidos.',
            'Os snapshot IDs são âncoras de proveniência; o motor não inventa dados de mercado nem custo.',
            'Não substitui orçamento executivo, avaliação imobiliária, análise tributária, funding, curva de vendas ou due diligence financeira profissional.',
        ],
    }
