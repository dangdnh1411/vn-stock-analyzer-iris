"""
fin_analysis.py — Phân tích BCTC: chỉ số, chấm điểm, nhận định tự động.

Đầu vào là dict từ vn_data.get_financials(). Mọi hàm là hàm thuần (không gọi mạng,
không dùng Streamlit) để test độc lập.

Triết lý: mỗi chỉ số đi kèm "ý nghĩa" (vì sao quan trọng) trước "con số" (bao nhiêu).
Ngưỡng đánh giá là ngưỡng thực hành phổ biến cho thị trường VN — dùng để SÀNG LỌC và
ĐẶT CÂU HỎI, không thay thế việc đọc thuyết minh BCTC.
"""
from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

from vn_data import minority_inside_equity, row_values

# ═════════════════════════════ TIỆN ÍCH ═════════════════════════════════════
def _ok(v):
    return v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))


def _div(a, b):
    if not _ok(a) or not _ok(b) or b == 0:
        return None
    return a / b


def _avg(a, b):
    if _ok(a) and _ok(b):
        return (a + b) / 2
    return a if _ok(a) else (b if _ok(b) else None)


def _growth(cur, prev):
    """Tăng trưởng %; None nếu kỳ trước ≤0 (tăng trưởng từ lỗ không có nghĩa)."""
    if not _ok(cur) or not _ok(prev) or prev <= 0:
        return None
    return (cur / prev - 1) * 100


def _cagr(last, first, n):
    if not _ok(last) or not _ok(first) or first <= 0 or last <= 0 or n <= 0:
        return None
    return ((last / first) ** (1 / n) - 1) * 100


def _sum(vals):
    if not vals or any(not _ok(v) for v in vals):
        return None
    return float(sum(vals))


def _neg(v):
    return -abs(v) if _ok(v) else v


def year_cols(df):
    if df is None or df.empty:
        return []
    return [c for c in df.columns if re.fullmatch(r"\d{4}", str(c))]


def q_cols(df):
    if df is None or df.empty:
        return []
    return [c for c in df.columns if re.fullmatch(r"\d{4}-Q[1-4]", str(c))]


def S(df, iid, cols):
    return row_values(df, iid, cols)


def revenue_series(inc, cols, ctype):
    """Doanh thu theo loại hình: DN/CK = doanh thu thuần (isa3); NH = tổng thu nhập HĐ;
    Bảo hiểm = doanh thu thuần HĐ kinh doanh bảo hiểm (isi64) → phí bảo hiểm (isi103)."""
    if ctype == "NH":
        return S(inc, "total_operating_income", cols)
    for iid in ("net_revenue", "isi64", "isi105", "isi103"):
        vals = S(inc, iid, cols)
        if any(_ok(v) and v != 0 for v in vals):
            return vals
    return [None] * len(cols)


def scale_score(v, pts):
    """Chấm 0-10 theo bảng ngưỡng [(ngưỡng, điểm)] sắp TĂNG dần ngưỡng."""
    if not _ok(v):
        return None
    score = pts[0][1]
    for th, sc in pts:
        if v >= th:
            score = sc
    return score


def _mean(xs):
    xs = [x for x in xs if _ok(x)]
    return sum(xs) / len(xs) if xs else None


def fmt_bn(v):
    if not _ok(v):
        return "—"
    return f"{v/1e9:,.0f} tỷ"


def fmt_pct(v, d=1):
    return f"{v:.{d}f}%" if _ok(v) else "—"


def fmt_x(v, d=1):
    return f"{v:.{d}f}x" if _ok(v) else "—"


# ═════════════════════════════ BẢNG CHỈ SỐ THEO NĂM ═════════════════════════
def annual_metrics(fin: dict) -> pd.DataFrame:
    """Bảng chỉ số tự tính theo năm (hàng = chỉ số, cột = năm). Tự tính từ BCTC gốc
    thay vì chỉ lấy số có sẵn, để biết chính xác công thức đang dùng."""
    inc, bal, cf = fin.get("inc_y"), fin.get("bal_y"), fin.get("cf_y")
    ys = year_cols(inc)
    if not ys:
        return pd.DataFrame()
    bank = fin.get("com_type") == "NH"
    g = lambda iid, df: S(df, iid, ys)  # noqa: E731

    npat = g("attributable_to_parent_company", inc)
    npat_all = g("net_profit_after_tax", inc)
    npat = [p if _ok(p) and p != 0 else a for p, a in zip(npat, npat_all)]
    pbt = g("profit_before_tax", inc)
    ta = g("total_assets", bal); eq = g("owners_equity", bal)
    mi = g("minority_interests", bal) if minority_inside_equity(bal) else [None] * len(ys)
    eq_p = [e - (m or 0) if _ok(e) else None for e, m in zip(eq, mi)]
    cfo = g("net_cash_flows_from_operating_activities", cf)
    rows = {}

    if bank:
        toi = g("total_operating_income", inc); nii = g("net_interest_income", inc)
        fee = g("net_fee_income", inc); opex = g("operating_expenses_bank", inc)
        ppop = g("pre_provision_profit", inc); prov = g("provision_expense", inc)
        loans = g("gross_loans", bal); dep = g("customer_deposits", bal)
        rows["Tổng thu nhập HĐ (TOI)"] = toi
        rows["Thu nhập lãi thuần (NII)"] = nii
        rows["LN trước dự phòng (PPOP)"] = ppop
        rows["Chi phí dự phòng"] = [abs(v) if _ok(v) else None for v in prov]
        rows["LN sau thuế cổ đông mẹ"] = npat
        rows["Dư nợ cho vay"] = loans
        rows["Tiền gửi khách hàng"] = dep
        rows["Tăng trưởng TOI %"] = [None] + [_growth(toi[i], toi[i-1]) for i in range(1, len(ys))]
        rows["Tăng trưởng LNST %"] = [None] + [_growth(npat[i], npat[i-1]) for i in range(1, len(ys))]
        rows["Tăng trưởng tín dụng %"] = [None] + [_growth(loans[i], loans[i-1]) for i in range(1, len(ys))]
        rows["Tỷ trọng NII/TOI %"] = [_div(a, b) * 100 if _div(a, b) is not None else None for a, b in zip(nii, toi)]
        rows["Phí dịch vụ/TOI %"] = [_div(a, b) * 100 if _div(a, b) is not None else None for a, b in zip(fee, toi)]
        rows["CIR %"] = [abs(_div(a, b)) * 100 if _div(a, b) is not None else None for a, b in zip(opex, toi)]
        rows["Dự phòng/PPOP %"] = [abs(_div(a, b)) * 100 if _div(a, b) is not None else None for a, b in zip(prov, ppop)]
        rows["LDR (cho vay/tiền gửi) %"] = [_div(a, b) * 100 if _div(a, b) is not None else None for a, b in zip(loans, dep)]
    else:
        rev = revenue_series(inc, ys, fin.get("com_type")); gp = g("gross_profit", inc)
        # Lãi vay: lấy MAX(chi phí lãi vay trên KQKD, tiền lãi vay đã trả trên LCTT) — doanh nghiệp
        # BĐS/hạ tầng vốn hoá lãi vay vào dự án nên chi phí lãi trên KQKD thấp giả tạo.
        intr_exp = g("interest_expense", inc)
        intr = [max(abs(a or 0), abs(b or 0)) or None
                for a, b in zip(intr_exp, g("cfa14", cf))]
        ebit = [p + abs(i or 0) if _ok(p) else None for p, i in zip(pbt, intr_exp)]
        dep_ = g("depreciation", cf)
        ebitda = [e + (d or 0) if _ok(e) else None for e, d in zip(ebit, dep_)]
        debt = [((a or 0) + (b or 0)) for a, b in zip(g("short_term_borrowings", bal), g("long_term_borrowings", bal))]
        cash = [((a or 0) + (b or 0)) for a, b in zip(g("cash_and_cash_equivalents", bal), g("short_term_investments", bal))]
        ca = g("current_assets", bal); cl = g("current_liabilities", bal)
        inv = g("inventories", bal); rec = g("short_term_receivables", bal)
        cogs = g("cost_of_goods_sold", inc)
        capex = g("purchase_of_fixed_assets", cf)
        divp = g("dividends_paid", cf)
        fcf = [c + (x or 0) if _ok(c) else None for c, x in zip(cfo, capex)]
        rows["Doanh thu thuần"] = rev
        rows["Lợi nhuận gộp"] = gp
        rows["EBIT"] = ebit
        rows["EBITDA"] = ebitda
        rows["LN sau thuế cổ đông mẹ"] = npat
        rows["Dòng tiền HĐKD (CFO)"] = cfo
        rows["Capex"] = [abs(v) if _ok(v) else None for v in capex]
        rows["Dòng tiền tự do (FCF)"] = fcf
        rows["Nợ vay"] = debt
        rows["Tiền + đầu tư ngắn hạn"] = cash
        rows["Tăng trưởng doanh thu %"] = [None] + [_growth(rev[i], rev[i-1]) for i in range(1, len(ys))]
        rows["Tăng trưởng LNST %"] = [None] + [_growth(npat[i], npat[i-1]) for i in range(1, len(ys))]
        rows["Biên gộp %"] = [_div(a, b) * 100 if _div(a, b) is not None else None for a, b in zip(gp, rev)]
        rows["Biên EBIT %"] = [_div(a, b) * 100 if _div(a, b) is not None else None for a, b in zip(ebit, rev)]
        rows["Biên ròng %"] = [_div(a, b) * 100 if _div(a, b) is not None else None for a, b in zip(npat, rev)]
        rows["Nợ vay/VCSH (x)"] = [_div(a, b) for a, b in zip(debt, eq)]
        rows["Nợ vay ròng/EBITDA (x)"] = [_div(d - c, e) if _ok(e) and e > 0 else None for d, c, e in zip(debt, cash, ebitda)]
        rows["Khả năng trả lãi EBIT/lãi vay (x)"] = [_div(e, abs(i)) if _ok(i) and i != 0 else None for e, i in zip(ebit, intr)]
        rows["Thanh toán hiện hành (x)"] = [_div(a, b) for a, b in zip(ca, cl)]
        rows["Thanh toán nhanh (x)"] = [_div((a or 0) - (i or 0), b) if _ok(a) else None for a, i, b in zip(ca, inv, cl)]
        rows["Số ngày phải thu"] = [_div(r, v) * 365 if _div(r, v) is not None else None for r, v in zip(rec, rev)]
        rows["Số ngày tồn kho"] = [_div(i, abs(c)) * 365 if _ok(c) and c != 0 and _ok(i) else None for i, c in zip(inv, cogs)]
        rows["CFO/LNST (x)"] = [_div(c, n) if _ok(n) and n > 0 else None for c, n in zip(cfo, npat)]
        rows["FCF/Doanh thu %"] = [_div(f, r) * 100 if _div(f, r) is not None else None for f, r in zip(fcf, rev)]
        rows["Tỷ lệ chi trả cổ tức tiền %"] = [abs(_div(d, n)) * 100 if _ok(d) and _ok(n) and n > 0 else None for d, n in zip(divp, npat)]
        # ROIC = EBIT*(1-thuế)/(VCSH + nợ vay) bình quân — cách tính thận trọng, không trừ tiền
        # (trừ cả tiền gửi có kỳ hạn sẽ thổi phồng ROIC của DN nhiều tiền như FPT lên >50%)
        tax_rate = []
        for p, t in zip(pbt, g("corporate_income_tax", inc)):
            r = abs(_div(t, p)) if _ok(p) and p > 0 and _ok(t) else 0.2
            tax_rate.append(min(max(r, 0.0), 0.5))
        ic = [(e or 0) + (d or 0) if _ok(e) else None for e, d in zip(eq, debt)]
        roic = [None]
        for i in range(1, len(ys)):
            base = _avg(ic[i], ic[i-1])
            roic.append(ebit[i] * (1 - tax_rate[i]) / base * 100
                        if _ok(ebit[i]) and _ok(base) and base > 0 else None)
        rows["ROIC %"] = roic

    rows["ROE %"] = [None] + [_div(npat[i], _avg(eq_p[i], eq_p[i-1])) * 100
                              if _div(npat[i], _avg(eq_p[i], eq_p[i-1])) is not None else None
                              for i in range(1, len(ys))]
    rows["ROA %"] = [None] + [_div(npat[i], _avg(ta[i], ta[i-1])) * 100
                              if _div(npat[i], _avg(ta[i], ta[i-1])) is not None else None
                              for i in range(1, len(ys))]
    rows["Đòn bẩy TS/VCSH (x)"] = [_div(a, e) for a, e in zip(ta, eq)]
    rows["VCSH/Tổng TS %"] = [_div(e, a) * 100 if _div(e, a) is not None else None for e, a in zip(eq, ta)]
    df = pd.DataFrame(rows, index=ys).T
    df.index.name = "Chỉ số"
    return df


# ═════════════════════════════ TTM & QUÝ ═════════════════════════════════════
def quarterly_snapshot(fin: dict) -> dict:
    """TTM (4 quý gần nhất) + quý gần nhất so với cùng kỳ."""
    inc, bal, cf = fin.get("inc_q"), fin.get("bal_q"), fin.get("cf_q")
    qs = q_cols(inc)
    out = {"quarters": qs, "latest_q": qs[-1] if qs else None}
    if len(qs) < 4:
        return out
    bank = fin.get("com_type") == "NH"
    rev = revenue_series(inc, qs, fin.get("com_type"))
    npat = S(inc, "attributable_to_parent_company", qs)
    npat_all = S(inc, "net_profit_after_tax", qs)
    npat = [p if _ok(p) and p != 0 else a for p, a in zip(npat, npat_all)]
    cfo = S(cf, "net_cash_flows_from_operating_activities", qs) if cf is not None and not cf.empty else [None] * len(qs)
    gp = S(inc, "gross_profit", qs)
    out.update(rev_q=rev, npat_q=npat, gp_q=gp, cfo_q=cfo)
    # Lợi nhuận cốt lõi (TTM) = LN gộp − chi phí bán hàng − chi phí quản lý; so với LN trước thuế
    if fin.get("com_type") == "CT":
        core = [(a or 0) + (b or 0) + (c or 0) if _ok(a) else None for a, b, c in
                zip(gp, S(inc, "selling_expenses", qs), S(inc, "general_admin_expenses", qs))]
        out["core_ttm"] = _sum(core[-4:]); out["pbt_ttm"] = _sum(S(inc, "profit_before_tax", qs)[-4:])
    out["rev_ttm"] = _sum(rev[-4:]); out["npat_ttm"] = _sum(npat[-4:])
    out["cfo_ttm"] = _sum(cfo[-4:])
    if len(qs) >= 8:
        out["rev_ttm_prev"] = _sum(rev[-8:-4]); out["npat_ttm_prev"] = _sum(npat[-8:-4])
        out["rev_ttm_yoy"] = _growth(out["rev_ttm"], out["rev_ttm_prev"])
        out["npat_ttm_yoy"] = _growth(out["npat_ttm"], out["npat_ttm_prev"])
    if len(qs) >= 5:
        out["rev_q_yoy"] = _growth(rev[-1], rev[-5])
        out["npat_q_yoy"] = _growth(npat[-1], npat[-5])
        out["gm_q"] = _div(gp[-1], rev[-1]) * 100 if not bank and _div(gp[-1], rev[-1]) is not None else None
        out["gm_q_prev"] = _div(gp[-5], rev[-5]) * 100 if not bank and _div(gp[-5], rev[-5]) is not None else None
    # bảng cân đối quý gần nhất
    bqs = q_cols(bal)
    if bqs:
        last = bqs[-1]
        out["equity"] = S(bal, "owners_equity", [last])[0]
        out["minority"] = S(bal, "minority_interests", [last])[0] if minority_inside_equity(bal) else None
        out["total_assets"] = S(bal, "total_assets", [last])[0]
        out["debt"] = sum(v or 0 for v in (S(bal, "short_term_borrowings", [last])[0],
                                           S(bal, "long_term_borrowings", [last])[0]))
        out["cash"] = sum(v or 0 for v in (S(bal, "cash_and_cash_equivalents", [last])[0],
                                           S(bal, "short_term_investments", [last])[0]))
        out["bal_q"] = last
    return out


# ═════════════════════════════ ĐỊNH GIÁ ══════════════════════════════════════
def valuation(fin: dict, price: float, snap: dict, ref_rate: float = 5.5) -> dict:
    """Định giá theo giá hiện tại + so với lịch sử P/E, P/B của chính doanh nghiệp."""
    det = fin.get("details") or {}
    stats = fin.get("stats") or []
    shares = det.get("numberOfSharesMktCap") or (stats[-1].get("numberOfSharesMktCap") if stats else None)
    v = {"price": price, "shares": shares}
    if not _ok(price) or not shares:
        return v
    shares = float(shares)
    mcap = price * shares
    v["market_cap"] = mcap
    eps = _div(snap.get("npat_ttm"), shares)
    eq_p = (snap.get("equity") or 0) - (snap.get("minority") or 0) if _ok(snap.get("equity")) else None
    bvps = _div(eq_p, shares)
    v.update(eps_ttm=eps, bvps=bvps)
    v["pe"] = _div(price, eps) if _ok(eps) and eps > 0 else None
    v["pb"] = _div(price, bvps) if _ok(bvps) and bvps > 0 else None
    v["ps"] = _div(mcap, snap.get("rev_ttm")) if _ok(snap.get("rev_ttm")) and snap["rev_ttm"] > 0 else None
    v["earnings_yield"] = _div(100, v["pe"]) if v["pe"] else None
    v["ref_rate"] = ref_rate
    if fin.get("com_type") == "CT":
        last = stats[-1] if stats else {}
        ebitda = last.get("ebitda")
        if _ok(ebitda) and ebitda > 0:
            ev = mcap + (snap.get("debt") or 0) - (snap.get("cash") or 0)
            v["ev"] = ev; v["ev_ebitda"] = ev / ebitda
    # Cổ tức tiền mặt năm gần nhất / vốn hoá
    cfy = fin.get("cf_y"); ys = year_cols(cfy)
    if ys:
        d = S(cfy, "dividends_paid", [ys[-1]])[0]
        if _ok(d) and d != 0:
            v["div_yield"] = abs(d) / mcap * 100
    # Dải P/E – P/B lịch sử (tối đa 20 quý gần nhất) từ dữ liệu TTM của VCI
    hist = [s for s in stats if s.get("year")][-20:]
    pes = [float(s["pe"]) for s in hist if _ok(s.get("pe")) and 0 < float(s["pe"]) < 80]
    pbs = [float(s["pb"]) for s in hist if _ok(s.get("pb")) and 0 < float(s["pb"]) < 20]
    if len(pes) >= 6:
        a = np.array(pes)
        v["pe_hist"] = dict(p25=float(np.percentile(a, 25)), med=float(np.median(a)),
                            p75=float(np.percentile(a, 75)), n=len(pes), series=pes)
        if v["pe"]:
            v["pe_pctile"] = float((a < v["pe"]).mean() * 100)
        if _ok(eps) and eps > 0:
            v["fair_pe"] = dict(low=v["pe_hist"]["p25"] * eps, mid=v["pe_hist"]["med"] * eps,
                                high=v["pe_hist"]["p75"] * eps)
    if len(pbs) >= 6:
        a = np.array(pbs)
        v["pb_hist"] = dict(p25=float(np.percentile(a, 25)), med=float(np.median(a)),
                            p75=float(np.percentile(a, 75)), n=len(pbs), series=pbs)
        if v["pb"]:
            v["pb_pctile"] = float((a < v["pb"]).mean() * 100)
        if _ok(bvps) and bvps > 0:
            v["fair_pb"] = dict(low=v["pb_hist"]["p25"] * bvps, mid=v["pb_hist"]["med"] * bvps,
                                high=v["pb_hist"]["p75"] * bvps)
    v["hist_labels"] = [f"{int(s['year'])}Q{int(s['quarter'])}" for s in hist]
    # Giá mục tiêu của Vietcap (tham khảo — đây là ý kiến bên thứ ba, không phải dữ kiện)
    if det.get("targetPrice"):
        v["analyst_target"] = float(det["targetPrice"])
        v["analyst_rating"] = det.get("rating")
        v["analyst_upside"] = (float(det["targetPrice"]) / price - 1) * 100
    return v


# ═════════════════════════════ PIOTROSKI & ALTMAN ════════════════════════════
def piotroski(fin: dict) -> dict | None:
    """F-Score 0-9 (Piotroski 2000) so sánh năm gần nhất với năm trước.
    Chỉ áp dụng cho doanh nghiệp phi tài chính."""
    if fin.get("com_type") != "CT":
        return None
    inc, bal, cf = fin.get("inc_y"), fin.get("bal_y"), fin.get("cf_y")
    ys = year_cols(inc)
    if len(ys) < 3:
        return None
    y0, y1, y2 = ys[-1], ys[-2], ys[-3]

    def v(df, iid, y):
        return S(df, iid, [y])[0]
    npat0, npat1 = v(inc, "net_profit_after_tax", y0), v(inc, "net_profit_after_tax", y1)
    ta0, ta1, ta2 = v(bal, "total_assets", y0), v(bal, "total_assets", y1), v(bal, "total_assets", y2)
    cfo0 = v(cf, "net_cash_flows_from_operating_activities", y0)
    roa0, roa1 = _div(npat0, ta1), _div(npat1, ta2)
    ltd0, ltd1 = v(bal, "long_term_borrowings", y0) or 0, v(bal, "long_term_borrowings", y1) or 0
    cr0 = _div(v(bal, "current_assets", y0), v(bal, "current_liabilities", y0))
    cr1 = _div(v(bal, "current_assets", y1), v(bal, "current_liabilities", y1))
    # Pha loãng = THU TIỀN từ phát hành cổ phiếu (cfa27) > 5% VCSH (bỏ qua ESOP/góp vốn nhỏ). Không dùng vốn điều lệ vì
    # cổ phiếu thưởng/cổ tức bằng cổ phiếu (rất phổ biến ở VN) làm tăng vốn điều lệ mà không pha loãng.
    iss0 = v(cf, "cfa27", y0) or 0
    eq0 = v(bal, "owners_equity", y0)
    gm0 = _div(v(inc, "gross_profit", y0), v(inc, "net_revenue", y0))
    gm1 = _div(v(inc, "gross_profit", y1), v(inc, "net_revenue", y1))
    at0 = _div(v(inc, "net_revenue", y0), ta1); at1 = _div(v(inc, "net_revenue", y1), ta2)
    checks = [
        ("ROA dương", "Có lãi trên tài sản", _ok(roa0) and roa0 > 0),
        ("CFO dương", "Kinh doanh thu được tiền thật", _ok(cfo0) and cfo0 > 0),
        ("ROA cải thiện", "Hiệu quả dùng tài sản tăng", _ok(roa0) and _ok(roa1) and roa0 > roa1),
        ("CFO > LNST", "Lợi nhuận được hậu thuẫn bằng tiền (chất lượng cao)",
         _ok(cfo0) and _ok(npat0) and cfo0 > npat0),
        ("Nợ dài hạn/TS giảm", "Đòn bẩy dài hạn giảm",
         _ok(ta0) and _ok(ta1) and (ltd0 / ta0) <= (ltd1 / ta1)),
        ("Thanh toán hiện hành tăng", "Thanh khoản ngắn hạn cải thiện", _ok(cr0) and _ok(cr1) and cr0 > cr1),
        ("Không phát hành thêm", "Không huy động vốn mới từ cổ đông (cổ phiếu thưởng không tính)",
         _ok(eq0) and eq0 > 0 and iss0 <= 0.05 * eq0),
        ("Biên gộp tăng", "Sức mạnh định giá/kiểm soát giá vốn tốt hơn", _ok(gm0) and _ok(gm1) and gm0 > gm1),
        ("Vòng quay TS tăng", "Tạo doanh thu từ tài sản hiệu quả hơn", _ok(at0) and _ok(at1) and at0 > at1),
    ]
    score = sum(1 for c in checks if c[2])
    return {"score": score, "year": y0, "base": y1,
            "checks": [{"tiêu chí": c[0], "ý nghĩa": c[1], "đạt": bool(c[2])} for c in checks]}


def altman_z(fin: dict) -> dict | None:
    """Altman Z''-Score bản cho thị trường mới nổi (EMS, 1995): đo nguy cơ kiệt quệ tài chính.
    Z'' = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4. An toàn >2.6 · Vùng xám 1.1–2.6 · Nguy hiểm <1.1."""
    if fin.get("com_type") != "CT":
        return None
    inc, bal = fin.get("inc_y"), fin.get("bal_y")
    ys = year_cols(bal)
    if not ys:
        return None
    y = ys[-1]

    def v(df, iid):
        return S(df, iid, [y])[0]
    ta = v(bal, "total_assets")
    if not _ok(ta) or ta <= 0:
        return None
    x1 = _div((v(bal, "current_assets") or 0) - (v(bal, "current_liabilities") or 0), ta)
    x2 = _div(v(bal, "undistributed_earnings") or 0, ta)
    ebit = (v(inc, "profit_before_tax") or 0) + abs(v(inc, "interest_expense") or 0)
    x3 = _div(ebit, ta)
    x4 = _div(v(bal, "owners_equity"), v(bal, "total_liabilities"))
    if None in (x1, x2, x3, x4):
        return None
    z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    zone = "An toàn" if z > 2.6 else ("Vùng xám" if z >= 1.1 else "Nguy hiểm")
    return {"z": z, "zone": zone, "year": y, "x1": x1, "x2": x2, "x3": x3, "x4": x4}


# ═════════════════════════════ CHẤM ĐIỂM & NHẬN ĐỊNH ════════════════════════
def _last(df, row, n=1):
    if df is None or df.empty or row not in df.index:
        return None if n == 1 else []
    s = [x for x in df.loc[row].tolist() if _ok(x)]
    if n == 1:
        return s[-1] if s else None
    return s[-n:]


def analyze(fin: dict, price: float, ref_rate: float = 5.5) -> dict:
    """Phân tích tổng hợp. Trả về dict gồm bảng chỉ số, điểm 5 trụ cột, điểm mạnh,
    rủi ro, nhận định và các con số định giá."""
    ctype = fin.get("com_type") or "CT"
    am = annual_metrics(fin)
    snap = quarterly_snapshot(fin)
    val = valuation(fin, price, snap, ref_rate)
    pio = piotroski(fin)
    alt = altman_z(fin)
    strengths, risks, pillars = [], [], {}
    ys = list(am.columns) if not am.empty else []
    n = len(ys)

    def cagr_row(row, years=3):
        s = am.loc[row].tolist() if row in am.index else []
        if len(s) > years and _ok(s[-1]) and _ok(s[-1 - years]):
            return _cagr(s[-1], s[-1 - years], years)
        return None

    # ── Trụ cột 1: TĂNG TRƯỞNG ───────────────────────────────────────────
    rev_row = "Tổng thu nhập HĐ (TOI)" if ctype == "NH" else "Doanh thu thuần"
    g_rev3 = cagr_row(rev_row) if n > 3 else None
    g_np3 = cagr_row("LN sau thuế cổ đông mẹ") if n > 3 else None
    g_ttm = snap.get("npat_ttm_yoy"); g_q = snap.get("npat_q_yoy")
    sc = [scale_score(g_rev3, [(-99, 0), (0, 3), (5, 5), (10, 7), (15, 8.5), (20, 10)]),
          scale_score(g_np3, [(-99, 0), (0, 3), (5, 5), (10, 7), (15, 8.5), (20, 10)]),
          scale_score(g_ttm, [(-99, 0), (-10, 2), (0, 4), (10, 7), (20, 9), (30, 10)])]
    pillars["Tăng trưởng"] = dict(score=_mean(sc), notes=[
        f"Doanh thu CAGR 3 năm: {fmt_pct(g_rev3)}", f"LNST CAGR 3 năm: {fmt_pct(g_np3)}",
        f"LNST 4 quý gần nhất so với cùng kỳ: {fmt_pct(g_ttm)}",
        f"LNST quý {snap.get('latest_q') or ''} so với cùng kỳ: {fmt_pct(g_q)}"])
    if _ok(g_np3) and g_np3 >= 15:
        strengths.append(f"Lợi nhuận tăng trưởng bền: CAGR 3 năm {g_np3:.1f}%/năm.")
    if _ok(g_ttm) and g_ttm < -10:
        risks.append(f"Lợi nhuận 4 quý gần nhất giảm {abs(g_ttm):.1f}% so với cùng kỳ — động lực tăng trưởng đang yếu đi.")
    elif _ok(g_ttm) and g_ttm > 150:
        strengths.append(f"Lợi nhuận 4 quý gần nhất gấp {g_ttm/100+1:.1f} lần cùng kỳ — PHỤC HỒI từ nền thấp; "
                         "cần kiểm tra lợi nhuận đến từ kinh doanh cốt lõi hay khoản bất thường.")
    elif _ok(g_ttm) and g_ttm > 20:
        strengths.append(f"Lợi nhuận 4 quý gần nhất tăng {g_ttm:.1f}% so với cùng kỳ — đà tăng trưởng đang mạnh.")
    if _ok(g_q) and _ok(g_ttm) and g_q < 0 < g_ttm:
        risks.append(f"Quý gần nhất LNST giảm {abs(g_q):.1f}% cùng kỳ dù TTM vẫn tăng — theo dõi xem đây là nhiễu hay điểm gãy.")

    # ── Trụ cột 2: SINH LỜI ─────────────────────────────────────────────
    roe = _last(am, "ROE %"); roa = _last(am, "ROA %")
    roe_hist = _last(am, "ROE %", 4)
    if ctype == "NH":
        nim = _ratio_last(fin, "nim"); cir = _ratio_last(fin, "cir")
        sc = [scale_score(roe, [(-99, 0), (8, 3), (12, 5), (15, 7), (18, 8.5), (22, 10)]),
              scale_score(roa, [(-99, 0), (0.8, 3), (1.2, 5), (1.5, 7), (2.0, 9), (2.5, 10)]),
              scale_score(nim * 100 if _ok(nim) else None, [(-99, 0), (2.5, 4), (3.0, 6), (3.5, 7.5), (4.0, 9), (4.5, 10)]),
              scale_score(-(cir * 100) if _ok(cir) else None, [(-99, 0), (-50, 4), (-40, 6), (-35, 8), (-30, 10)])]
        notes = [f"ROE: {fmt_pct(roe)}", f"ROA: {fmt_pct(roa)}",
                 f"NIM (TTM): {fmt_pct(nim*100 if _ok(nim) else None, 2)}", f"CIR (TTM): {fmt_pct(cir*100 if _ok(cir) else None)}"]
    elif ctype in ("CK", "BH"):
        nm = _last(am, "Biên ròng %")
        sc = [scale_score(roe, [(-99, 0), (8, 3), (12, 5), (15, 7), (18, 8.5), (22, 10)])]
        notes = [f"ROE: {fmt_pct(roe)}", f"ROA: {fmt_pct(roa)}", f"Biên ròng: {fmt_pct(nm)}",
                 "Với CTCK/bảo hiểm, ROE là thước đo chính; biên gộp và ROIC không có ý nghĩa như DN sản xuất."]
    else:
        nm = _last(am, "Biên ròng %"); gm = _last(am, "Biên gộp %"); roic = _last(am, "ROIC %")
        sc = [scale_score(roe, [(-99, 0), (5, 2), (10, 4.5), (15, 7), (20, 8.5), (25, 10)]),
              scale_score(roic, [(-99, 0), (5, 3), (10, 6), (15, 8), (20, 10)]),
              scale_score(roa, [(-99, 0), (2, 3), (5, 5.5), (8, 7.5), (12, 10)])]
        notes = [f"ROE: {fmt_pct(roe)}", f"ROIC: {fmt_pct(roic)}", f"ROA: {fmt_pct(roa)}",
                 f"Biên gộp: {fmt_pct(gm)} · Biên ròng: {fmt_pct(nm)}"]
        gm_hist = _last(am, "Biên gộp %", 3)
        if len(gm_hist) == 3 and gm_hist[-1] < gm_hist[0] - 3:
            risks.append(f"Biên gộp thu hẹp từ {gm_hist[0]:.1f}% xuống {gm_hist[-1]:.1f}% trong 3 năm — sức mạnh định giá suy yếu hoặc chi phí đầu vào tăng.")
        if _ok(roic) and roic >= 15:
            strengths.append(f"ROIC {roic:.1f}% — vốn đầu tư vào kinh doanh sinh lời cao, dấu hiệu lợi thế cạnh tranh.")
    pillars["Sinh lời"] = dict(score=_mean(sc), notes=notes)
    if _ok(roe) and roe >= 18:
        strengths.append(f"ROE {roe:.1f}% — mỗi 100 đồng vốn chủ tạo ra {roe:.0f} đồng lãi/năm, vượt xa lãi tiền gửi.")
    elif _ok(roe) and roe < 10:
        risks.append(f"ROE chỉ {roe:.1f}% — hiệu quả dùng vốn thấp, gần bằng gửi tiết kiệm nhưng rủi ro cao hơn.")
    if len(roe_hist) >= 3 and roe_hist[-1] < roe_hist[0] - 4:
        risks.append(f"ROE giảm từ {roe_hist[0]:.1f}% xuống {roe_hist[-1]:.1f}% — hiệu quả sinh lời đi xuống.")

    # ── Trụ cột 3: SỨC KHOẺ TÀI CHÍNH ────────────────────────────────────
    if ctype == "NH":
        npl = _ratio_last(fin, "npl"); cov = _ratio_last(fin, "llr_coverage")
        eqta = _last(am, "VCSH/Tổng TS %"); ldr = _ratio_last(fin, "ldr"); casa = _ratio_last(fin, "casa")
        sc = [scale_score(-(npl * 100) if _ok(npl) else None, [(-99, 0), (-3, 3), (-2, 5), (-1.5, 7), (-1, 9), (-0.7, 10)]),
              scale_score(cov * 100 if _ok(cov) else None, [(-99, 0), (50, 3), (80, 5), (100, 7), (150, 9), (200, 10)]),
              scale_score(eqta, [(-99, 0), (6, 4), (8, 6), (10, 8), (12, 10)]),
              scale_score(casa * 100 if _ok(casa) else None, [(-99, 3), (15, 4), (20, 6), (30, 8), (35, 10)])]
        notes = [f"Nợ xấu NPL: {fmt_pct(npl*100 if _ok(npl) else None, 2)}",
                 f"Bao phủ nợ xấu (LLR): {fmt_pct(cov*100 if _ok(cov) else None, 0)}",
                 f"VCSH/Tổng TS: {fmt_pct(eqta)}", f"LDR: {fmt_pct(ldr*100 if _ok(ldr) else None, 0)}",
                 f"CASA: {fmt_pct(casa*100 if _ok(casa) else None)}"]
        if _ok(npl) and npl > 0.02:
            risks.append(f"Nợ xấu {npl*100:.2f}% vượt ngưỡng 2% — chất lượng tài sản đáng lo.")
        if _ok(cov) and cov >= 1.5:
            strengths.append(f"Bao phủ nợ xấu {cov*100:.0f}% — bộ đệm dự phòng dày, đủ hấp thụ nợ xấu hiện tại.")
        elif _ok(cov) and cov < 0.8:
            risks.append(f"Bao phủ nợ xấu chỉ {cov*100:.0f}% — nếu nợ xấu phải xử lý, lợi nhuận sẽ bị ăn mòn bởi trích lập.")
        if _ok(casa) and casa >= 0.3:
            strengths.append(f"CASA {casa*100:.0f}% — nguồn vốn rẻ, lợi thế về NIM.")
    elif ctype == "CT":
        de = _last(am, "Nợ vay/VCSH (x)"); icr = _last(am, "Khả năng trả lãi EBIT/lãi vay (x)")
        cr = _last(am, "Thanh toán hiện hành (x)"); nd_e = _last(am, "Nợ vay ròng/EBITDA (x)")
        z = alt["z"] if alt else None
        sc = [scale_score(-de if _ok(de) else None, [(-99, 0), (-2, 2), (-1.5, 4), (-1, 6), (-0.5, 8.5), (-0.2, 10)]),
              scale_score(icr if _ok(icr) else (99 if _ok(de) and de < 0.05 else None),
                          [(-99, 0), (1.5, 2), (3, 5), (5, 7), (10, 9), (20, 10)]),
              scale_score(cr, [(-99, 0), (0.8, 2), (1.0, 4), (1.2, 6), (1.5, 8), (2.0, 10)]),
              scale_score(-nd_e if _ok(nd_e) else None, [(-999, 0), (-6, 2), (-4, 4), (-3, 5.5), (-2, 7.5), (-1, 9), (0, 10)]),
              scale_score(z, [(-99, 0), (1.1, 4), (2.6, 7.5), (4, 10)])]
        notes = [f"Nợ vay/VCSH: {fmt_x(de, 2)}", f"Nợ vay ròng/EBITDA: {fmt_x(nd_e)}",
                 f"EBIT/lãi vay: {fmt_x(icr)}", f"Thanh toán hiện hành: {fmt_x(cr, 2)}",
                 "Altman Z'': " + (f"{z:.2f} ({alt['zone']})" if alt else "—")]
        if _ok(nd_e) and nd_e < 0:
            strengths.append("Tiền mặt nhiều hơn nợ vay (nợ ròng âm) — bảng cân đối rất an toàn.")
        if _ok(de) and de > 1.5:
            risks.append(f"Nợ vay gấp {de:.1f} lần vốn chủ — nhạy cảm với lãi suất tăng.")
        if _ok(icr) and icr < 2:
            risks.append(f"EBIT chỉ gấp {icr:.1f} lần chi phí lãi vay — biên an toàn trả nợ mỏng.")
        if _ok(nd_e) and nd_e > 4:
            risks.append(f"Nợ vay ròng gấp {nd_e:.1f} lần EBITDA — cần nhiều năm lợi nhuận mới trả hết nợ, phụ thuộc vào đảo nợ.")
        cfo4 = _last(am, "Dòng tiền HĐKD (CFO)", 3)
        if len(cfo4) == 3 and all(x < 0 for x in cfo4):
            risks.append("Dòng tiền kinh doanh ÂM 3 năm liên tiếp — doanh nghiệp sống bằng vay nợ/huy động, rủi ro thanh khoản cao.")
        if alt and alt["zone"] == "Nguy hiểm":
            risks.append(f"Altman Z'' = {alt['z']:.2f} (<1.1) — cấu trúc tài chính thuộc vùng có nguy cơ kiệt quệ.")
    else:  # Chứng khoán / Bảo hiểm
        eqta = _last(am, "VCSH/Tổng TS %"); lev = _last(am, "Đòn bẩy TS/VCSH (x)")
        # Bảo hiểm luôn có VCSH/TS thấp (phần lớn nguồn vốn là dự phòng nghiệp vụ) → thang riêng
        pts = ([(-99, 0), (5, 3), (8, 5), (12, 7), (15, 9), (20, 10)] if ctype == "BH"
               else [(-99, 0), (15, 3), (25, 5), (35, 7), (50, 9)])
        sc = [scale_score(eqta, pts)]
        notes = [f"VCSH/Tổng TS: {fmt_pct(eqta)}", f"Đòn bẩy TS/VCSH: {fmt_x(lev)}"]
    pillars["Sức khoẻ tài chính"] = dict(score=_mean(sc), notes=notes)

    # ── Trụ cột 4: DÒNG TIỀN & CHẤT LƯỢNG LỢI NHUẬN ───────────────────────
    if ctype == "CT":
        cfo3 = _last(am, "Dòng tiền HĐKD (CFO)", 3); np3 = _last(am, "LN sau thuế cổ đông mẹ", 3)
        conv = _div(sum(cfo3), sum(np3)) if len(cfo3) == 3 and len(np3) == 3 and sum(np3) > 0 else None
        fcf3 = _last(am, "Dòng tiền tự do (FCF)", 3)
        fcf_pos = sum(1 for x in fcf3 if x > 0) if fcf3 else None
        # Phải thu tăng nhanh hơn doanh thu = tô doanh thu bằng bán chịu
        rec_flag = None
        bal = fin.get("bal_y"); inc = fin.get("inc_y"); yy = year_cols(inc)
        if len(yy) >= 2:
            # Dùng PHẢI THU KHÁCH HÀNG (bsa9), không dùng phải thu tổng (có trả trước nhà thầu, cho vay…)
            r0, r1 = S(bal, "trade_receivables_customers", yy[-2:]); s0, s1 = S(inc, "net_revenue", yy[-2:])
            gr, gs = _growth(r1, r0), _growth(s1, s0)
            if _ok(gr) and _ok(gs) and _ok(r1) and _ok(s1) and s1 > 0 and r1 / s1 >= 0.05:
                rec_flag = gr - gs
        sc = [scale_score(conv, [(-99, 0), (0.5, 3), (0.8, 6), (1.0, 8.5), (1.2, 10)]),
              scale_score(fcf_pos, [(0, 2), (1, 4), (2, 7), (3, 10)]),
              scale_score(pio["score"] if pio else None, [(0, 0), (3, 3), (5, 6), (7, 8.5), (8, 10)])]
        notes = [f"CFO/LNST cộng dồn 3 năm: {fmt_x(conv, 2)}",
                 f"Số năm FCF dương (3 năm gần nhất): {fcf_pos if fcf_pos is not None else '—'}/3",
                 f"Piotroski F-Score: {pio['score'] if pio else '—'}/9",
                 f"Phải thu tăng nhanh hơn doanh thu: {fmt_pct(rec_flag) + ' điểm %' if _ok(rec_flag) else '—'}"]
        if _ok(conv) and conv >= 1.0:
            strengths.append(f"3 năm thu về {conv:.2f} đồng tiền mặt cho mỗi đồng lợi nhuận — lợi nhuận 'thật'.")
        elif _ok(conv) and conv < 0.5:
            risks.append(f"3 năm chỉ thu về {conv:.2f} đồng tiền cho mỗi đồng lãi — lợi nhuận chủ yếu nằm trên giấy (phải thu/tồn kho).")
        if _ok(rec_flag) and rec_flag > 20:
            risks.append(f"Phải thu khách hàng tăng nhanh hơn doanh thu {rec_flag:.0f} điểm % — kiểm tra chính sách bán chịu.")
        core, pbt = snap.get("core_ttm"), snap.get("pbt_ttm")
        if _ok(core) and _ok(pbt) and pbt > 0 and core / pbt < 0.5:
            risks.append(f"Chỉ {max(core, 0) / pbt * 100:.0f}% lợi nhuận trước thuế 4 quý gần nhất đến từ kinh doanh cốt lõi — "
                         "phần còn lại là thu nhập tài chính/khác, khó lặp lại.")
        if pio and pio["score"] >= 7:
            strengths.append(f"Piotroski F-Score {pio['score']}/9 — nền tảng tài chính đang cải thiện toàn diện.")
        elif pio and pio["score"] <= 3:
            risks.append(f"Piotroski F-Score {pio['score']}/9 — nhiều chỉ tiêu tài chính đang xấu đi.")
        pillars["Dòng tiền & chất lượng LN"] = dict(score=_mean(sc), notes=notes)
    elif ctype == "NH":
        prov = _last(am, "Dự phòng/PPOP %"); cc = _ratio_last(fin, "credit_cost")
        sc = [scale_score(-prov if _ok(prov) else None, [(-99, 0), (-60, 3), (-45, 5), (-30, 7), (-20, 9), (-10, 10)])]
        notes = [f"Chi phí dự phòng/LN trước dự phòng: {fmt_pct(prov)}",
                 f"Chi phí tín dụng (TTM): {fmt_pct(cc*100 if _ok(cc) else None, 2)}"]
        if _ok(prov) and prov > 50:
            risks.append(f"Dự phòng ăn {prov:.0f}% lợi nhuận trước dự phòng — lợi nhuận phụ thuộc lớn vào chất lượng tài sản.")
        pillars["Chất lượng lợi nhuận"] = dict(score=_mean(sc), notes=notes)

    # ── Trụ cột 5: ĐỊNH GIÁ ─────────────────────────────────────────────
    pe, pb = val.get("pe"), val.get("pb")
    vsc, vnotes = [], []
    if ctype == "NH" or ctype in ("CK", "BH"):
        vsc.append(scale_score(-(val.get("pb_pctile") or 0) if val.get("pb_pctile") is not None else None,
                               [(-100, 0), (-80, 2), (-60, 4), (-40, 6), (-25, 8), (-10, 10)]))
        if _ok(pb) and _ok(roe):
            # P/B hợp lý ≈ ROE / chi phí vốn (12%) → so sánh
            fair_pb = roe / 12.0
            vsc.append(scale_score(_div(fair_pb, pb), [(0, 0), (0.7, 3), (0.9, 5), (1.1, 7), (1.4, 9), (1.8, 10)]))
            vnotes.append(f"P/B hợp lý theo ROE (ROE/12%): {fair_pb:.2f}x so với hiện tại {pb:.2f}x")
    vsc.append(scale_score(-(val.get("pe_pctile")) if val.get("pe_pctile") is not None else None,
                           [(-100, 0), (-80, 2), (-60, 4), (-40, 6), (-25, 8), (-10, 10)]))
    ey = val.get("earnings_yield")
    vsc.append(scale_score(ey - ref_rate if _ok(ey) else None, [(-99, 0), (-3, 2), (0, 5), (2, 7), (4, 9), (6, 10)]))
    peg = _div(pe, g_np3) if _ok(pe) and _ok(g_np3) and g_np3 > 0 else None
    if ctype == "CT":
        vsc.append(scale_score(-peg if _ok(peg) else None, [(-99, 0), (-2.5, 2), (-1.8, 4), (-1.2, 6), (-0.8, 8.5), (-0.5, 10)]))
    vnotes = [f"P/E: {fmt_x(pe)} (rẻ hơn {100 - val['pe_pctile']:.0f}% các quý trong 5 năm)" if val.get("pe_pctile") is not None else f"P/E: {fmt_x(pe)}",
              f"P/B: {fmt_x(pb, 2)}" + (f" (phân vị {val['pb_pctile']:.0f}% lịch sử)" if val.get("pb_pctile") is not None else ""),
              f"Lợi suất lợi nhuận 1/PE: {fmt_pct(ey)} so với lãi suất tham chiếu {ref_rate:.1f}%",
              f"PEG (P/E ÷ CAGR LNST 3 năm): {fmt_x(peg, 2)}"] + vnotes
    pillars["Định giá"] = dict(score=_mean(vsc), notes=vnotes)
    if val.get("pe_pctile") is not None and val["pe_pctile"] <= 25:
        strengths.append(f"P/E {pe:.1f}x nằm ở vùng thấp của 5 năm (phân vị {val['pe_pctile']:.0f}%) — giá đang rẻ so với chính nó.")
    elif val.get("pe_pctile") is not None and val["pe_pctile"] >= 85:
        risks.append(f"P/E {pe:.1f}x ở vùng cao của 5 năm (phân vị {val['pe_pctile']:.0f}%) — kỳ vọng đã phản ánh nhiều vào giá.")
    if _ok(ey) and ey < ref_rate:
        risks.append(f"Lợi suất lợi nhuận {ey:.1f}% thấp hơn lãi suất tham chiếu {ref_rate:.1f}% — cần tăng trưởng cao mới bù được.")
    if not _ok(pe) and _ok(val.get("eps_ttm")) and val["eps_ttm"] <= 0:
        risks.append("EPS 4 quý gần nhất âm — doanh nghiệp đang lỗ, P/E không có ý nghĩa.")

    # ── Tổng hợp ────────────────────────────────────────────────────────
    q_keys = [k for k in pillars if k != "Định giá"]
    quality = _mean([pillars[k]["score"] for k in q_keys])
    value = pillars["Định giá"]["score"]
    if quality is None:
        stance, color = "Không đủ dữ liệu để đánh giá", "#8baed4"
    elif quality >= 6.5 and (value or 0) >= 6:
        stance, color = "Doanh nghiệp tốt · Giá hấp dẫn", "#00d97e"
    elif quality >= 6.5:
        stance, color = "Doanh nghiệp tốt · Giá chưa rẻ — chờ vùng mua", "#7fcf50"
    elif quality >= 4.5 and (value or 0) >= 6:
        stance, color = "Chất lượng trung bình · Giá rẻ — cần lý do để giá phục hồi", "#f5a623"
    elif quality >= 4.5:
        stance, color = "Chất lượng trung bình · Giá không rẻ — chưa hấp dẫn", "#f5a623"
    elif (value or 0) >= 6:
        stance, color = "Rẻ nhưng nền tảng yếu — cẩn thận bẫy giá trị", "#ff8a3d"
    else:
        stance, color = "Nền tảng yếu · Không rẻ — tránh", "#ff3d5a"
    return dict(com_type=ctype, annual=am, snap=snap, val=val, piotroski=pio, altman=alt,
                pillars=pillars, quality=quality, value=value, stance=stance, color=color,
                strengths=strengths, risks=risks)


def _ratio_last(fin, iid):
    """Giá trị TTM mới nhất của 1 chỉ số trong bảng chỉ số quý của VCI."""
    rq = fin.get("ratio_q")
    if rq is None or rq.empty:
        return None
    cols = q_cols(rq)
    vals = row_values(rq, iid, cols)
    vals = [v for v in vals if _ok(v)]
    return vals[-1] if vals else None


# ═════════════════════════════ GIẢI THÍCH CHỈ SỐ ════════════════════════════
GLOSSARY = {
    "ROE": "Lợi nhuận trên vốn chủ. Cứ 100 đồng cổ đông góp, DN tạo ra bao nhiêu đồng lãi/năm. >15% là tốt ở VN; nhưng ROE cao do vay nợ nhiều thì kém bền.",
    "ROIC": "Lợi nhuận hoạt động sau thuế trên vốn đầu tư (vốn chủ + nợ vay). Đo hiệu quả của chính hoạt động kinh doanh, không bị đòn bẩy làm đẹp. ROIC > chi phí vốn (~12%) = DN tạo giá trị.",
    "ROA": "Lợi nhuận trên tổng tài sản — hiệu quả dùng toàn bộ tài sản. Ngân hàng >1.5% là tốt.",
    "Biên gộp": "Phần còn lại sau giá vốn. Biên gộp cao và ổn định = sức mạnh định giá (thương hiệu, công nghệ, vị thế độc quyền).",
    "CFO/LNST": "Bao nhiêu tiền mặt thật thu về cho mỗi đồng lợi nhuận kế toán. <0.8 kéo dài = lợi nhuận nằm ở phải thu/tồn kho, rủi ro 'lãi giả'.",
    "FCF": "Dòng tiền tự do = CFO − Capex. Tiền thật DN có thể dùng trả cổ tức, trả nợ, mua lại cổ phiếu. FCF âm nhiều năm = DN phải liên tục đi vay/phát hành.",
    "Nợ vay/VCSH": "Đòn bẩy tài chính. >1.5x thì lợi nhuận rất nhạy với lãi suất và chu kỳ.",
    "EBIT/lãi vay": "Lợi nhuận hoạt động gấp mấy lần tiền lãi phải trả. <2x là vùng nguy hiểm khi kinh doanh chững lại.",
    "Nợ ròng/EBITDA": "Mất bao nhiêu năm EBITDA để trả hết nợ ròng. <2x an toàn, >4x căng. Âm = tiền nhiều hơn nợ.",
    "Piotroski F-Score": "9 phép thử đúng/sai về sinh lời, đòn bẩy, hiệu quả hoạt động (năm nay so năm trước). 7-9: nền tảng cải thiện; 0-3: suy yếu.",
    "Altman Z''": "Mô hình dự báo nguy cơ phá sản bản cho thị trường mới nổi. >2.6 an toàn; 1.1-2.6 vùng xám; <1.1 nguy cơ kiệt quệ.",
    "P/E": "Giá trả cho 1 đồng lợi nhuận/năm. So với CHÍNH NÓ trong quá khứ (phân vị) và với ngành, không so tuyệt đối.",
    "P/B": "Giá trả cho 1 đồng giá trị sổ sách. Quan trọng nhất với ngân hàng/chứng khoán. P/B hợp lý ≈ ROE / chi phí vốn.",
    "Lợi suất lợi nhuận": "= 1/PE. So với lãi tiết kiệm: thấp hơn lãi suất thì bạn đang trả giá cao cho kỳ vọng tăng trưởng.",
    "PEG": "P/E chia tăng trưởng LNST. <1 = giá rẻ so với tốc độ tăng trưởng; >2 = đắt.",
    "NIM": "Biên lãi ròng của ngân hàng — chênh lệch lãi cho vay và huy động trên tài sản sinh lãi.",
    "CIR": "Chi phí hoạt động/Tổng thu nhập. Thấp = vận hành hiệu quả (<35% là tốt).",
    "NPL": "Tỷ lệ nợ xấu (nhóm 3-5). >2% là đáng lo; cần đọc kèm nợ nhóm 2 và nợ tái cơ cấu trong thuyết minh.",
    "LLR": "Dự phòng/nợ xấu — bộ đệm hấp thụ nợ xấu. >100% là an toàn.",
    "CASA": "Tỷ lệ tiền gửi không kỳ hạn — vốn rẻ. CASA cao giúp NIM cao và ổn định.",
}
