"""
bctc_tab.py — Giao diện tab "📑 Phân tích BCTC".

Bố cục (đi từ kết luận → bằng chứng → dữ liệu gốc):
  1. Hồ sơ nhanh  2. Nhận định tổng hợp + 5 trụ cột  3. Điểm mạnh / Rủi ro
  4. Các tab con: Kết quả KD · Cân đối · Dòng tiền · Định giá · Chấm điểm · Báo cáo gốc · Giải thích
"""
from __future__ import annotations

import io
import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import fin_analysis as fa
from vn_data import COM_TYPES, row_values

GREEN, YELLOW, RED, BLUE, PURPLE, CYAN, MUTED = "#00d97e", "#f5a623", "#ff3d5a", "#4a9ef8", "#a78bfa", "#22d3ee", "#8baed4"


def _card(html, border="#163350"):
    st.markdown(f"<div style='background:#0c1d2e;border:1px solid {border};border-radius:10px;"
                f"padding:12px 16px;margin:6px 0;'>{html}</div>", unsafe_allow_html=True)


def _kpi(label, value, sub="", color="#ffffff"):
    return (f"<div style='background:#0c1d2e;border:1px solid #163350;border-radius:8px;padding:8px 10px;'>"
            f"<div style='font-size:11px;color:#6a9cc8;'>{label}</div>"
            f"<div style='font-size:18px;font-weight:700;color:{color};'>{value}</div>"
            f"<div style='font-size:10px;color:#4a6080;'>{sub}</div></div>")


def _score_color(s):
    if s is None:
        return MUTED
    return GREEN if s >= 6.5 else (YELLOW if s >= 4.5 else RED)


def _bn(v):
    return v / 1e9 if v is not None and pd.notna(v) else None


def _style(fig, style, h=330, title=None):
    fig.update_layout(height=h, template="plotly_dark", **style)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(color="#8baed4", size=13)))
    return fig


# ═════════════════════════════ BẢNG BÁO CÁO GỐC ══════════════════════════════
def statement_table(df: pd.DataFrame, n_periods: int = 8) -> pd.DataFrame:
    """Bảng hiển thị: tên chỉ tiêu thụt lề theo cấp, đơn vị tỷ đồng, cột % thay đổi kỳ cuối."""
    if df is None or df.empty:
        return pd.DataFrame()
    per = [c for c in df.columns if re.fullmatch(r"\d{4}(-Q[1-4])?", str(c))][-n_periods:]
    out = pd.DataFrame()
    out["Chỉ tiêu"] = ["    " * (int(lv) - 1) + str(it) for it, lv in zip(df["item"], df["levels"])]
    is_eps = df["field"].isin(["isa23", "isa24"])
    for c in per:
        vals = pd.to_numeric(df[c], errors="coerce")
        out[c] = np.where(is_eps, vals, vals / 1e9)
    if len(per) >= 2:
        # So với cùng kỳ: quý → so với 4 quý trước; năm → so với năm trước
        prev = per[-5] if "-Q" in per[-1] and len(per) >= 5 else per[-2]
        a = pd.to_numeric(df[per[-1]], errors="coerce"); b = pd.to_numeric(df[prev], errors="coerce")
        out[f"Δ% {per[-1]} vs {prev}"] = np.where((b > 0) & a.notna(), (a / b - 1) * 100, np.nan)
    return out


# ═════════════════════════════ BIỂU ĐỒ ═══════════════════════════════════════
def chart_income(fin, res, style):
    figs = []
    am = res["annual"]; bank = res["com_type"] == "NH"
    ys = list(am.columns)
    rev_row = "Tổng thu nhập HĐ (TOI)" if bank else "Doanh thu thuần"
    if rev_row in am.index:
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=ys, y=[_bn(v) for v in am.loc[rev_row]], name=rev_row + " (tỷ)",
                             marker_color=BLUE, opacity=0.85), secondary_y=False)
        fig.add_trace(go.Bar(x=ys, y=[_bn(v) for v in am.loc["LN sau thuế cổ đông mẹ"]],
                             name="LNST cổ đông mẹ (tỷ)", marker_color=GREEN), secondary_y=False)
        gr = "Tăng trưởng TOI %" if bank else "Tăng trưởng doanh thu %"
        if gr in am.index:
            fig.add_trace(go.Scatter(x=ys, y=am.loc[gr], name="Tăng trưởng DT %", mode="lines+markers",
                                     line=dict(color=YELLOW, width=2)), secondary_y=True)
        fig.add_trace(go.Scatter(x=ys, y=am.loc["Tăng trưởng LNST %"], name="Tăng trưởng LNST %",
                                 mode="lines+markers", line=dict(color=PURPLE, width=2, dash="dot")), secondary_y=True)
        fig.update_layout(barmode="group")
        figs.append(_style(fig, style, 360, "Doanh thu & lợi nhuận theo năm (cột: tỷ đồng · đường: % tăng trưởng)"))
    # Theo quý — 12 quý gần nhất
    snap = res["snap"]; qs = snap.get("quarters", [])[-12:]
    if qs:
        k = len(qs)
        rq = snap.get("rev_q", [])[-k:]; nq = snap.get("npat_q", [])[-k:]
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=qs, y=[_bn(v) for v in rq], name=("TOI" if bank else "Doanh thu") + " quý (tỷ)",
                             marker_color=BLUE, opacity=0.8), secondary_y=False)
        fig.add_trace(go.Bar(x=qs, y=[_bn(v) for v in nq], name="LNST quý (tỷ)", marker_color=GREEN), secondary_y=False)
        full_n = snap.get("npat_q", [])
        yoy = []
        for i in range(len(full_n) - k, len(full_n)):
            yoy.append(fa._growth(full_n[i], full_n[i - 4]) if i >= 4 else None)
        fig.add_trace(go.Scatter(x=qs, y=yoy, name="LNST % cùng kỳ", mode="lines+markers",
                                 line=dict(color=YELLOW, width=2)), secondary_y=True)
        fig.update_layout(barmode="group")
        figs.append(_style(fig, style, 340, "12 quý gần nhất — so sánh cùng kỳ quan trọng hơn so với quý liền trước (tính mùa vụ)"))
    # Biên lợi nhuận / chỉ số ngân hàng
    if bank:
        rq_df = fin.get("ratio_q")
        cols = fa.q_cols(rq_df)[-16:]
        if cols:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            for iid, nm, clr, sec in [("nim", "NIM %", GREEN, False), ("cir", "CIR %", YELLOW, True),
                                      ("casa", "CASA %", CYAN, True)]:
                v = row_values(rq_df, iid, cols)
                if any(x is not None for x in v):
                    fig.add_trace(go.Scatter(x=cols, y=[x * 100 if x is not None else None for x in v],
                                             name=nm, mode="lines+markers", line=dict(color=clr, width=2)),
                                  secondary_y=sec)
            figs.append(_style(fig, style, 300, "NIM (trục trái) · CIR & CASA (trục phải) — TTM theo quý"))
    else:
        fig = go.Figure()
        for row, clr in [("Biên gộp %", PURPLE), ("Biên EBIT %", BLUE), ("Biên ròng %", CYAN)]:
            if row in am.index:
                fig.add_trace(go.Scatter(x=ys, y=am.loc[row], name=row, mode="lines+markers", line=dict(color=clr, width=2)))
        figs.append(_style(fig, style, 280, "Biên lợi nhuận (%) — biên ổn định/mở rộng = lợi thế cạnh tranh"))
    # ROE/ROA
    fig = go.Figure()
    for row, clr in [("ROE %", GREEN), ("ROA %", YELLOW)] + ([] if bank else [("ROIC %", PURPLE)]):
        if row in am.index:
            fig.add_trace(go.Scatter(x=ys, y=am.loc[row], name=row, mode="lines+markers", line=dict(color=clr, width=2)))
    fig.add_hline(y=15, line=dict(color="rgba(0,217,126,.35)", dash="dot"), annotation_text=" ROE 15%")
    figs.append(_style(fig, style, 280, "Hiệu quả sinh lời (%) — tính trên vốn/tài sản bình quân"))
    return figs


def chart_balance(fin, res, style):
    figs = []
    bal = fin.get("bal_y"); ys = fa.year_cols(bal)
    if not ys:
        return figs
    g = lambda iid: [_bn(v) for v in row_values(bal, iid, ys)]  # noqa: E731
    if res["com_type"] == "NH":
        fig = go.Figure()
        for iid, nm, clr in [("gross_loans", "Dư nợ cho vay", BLUE), ("customer_deposits", "Tiền gửi KH", CYAN),
                             ("owners_equity", "Vốn chủ sở hữu", GREEN)]:
            fig.add_trace(go.Bar(x=ys, y=g(iid), name=nm, marker_color=clr))
        fig.update_layout(barmode="group")
        figs.append(_style(fig, style, 320, "Quy mô ngân hàng (tỷ đồng)"))
        rq = fin.get("ratio_q"); cols = fa.q_cols(rq)[-16:]
        if cols:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            npl = row_values(rq, "npl", cols); cov = row_values(rq, "llr_coverage", cols)
            fig.add_trace(go.Scatter(x=cols, y=[x * 100 if x is not None else None for x in npl], name="NPL %",
                                     line=dict(color=RED, width=2), mode="lines+markers"), secondary_y=False)
            fig.add_trace(go.Scatter(x=cols, y=[x * 100 if x is not None else None for x in cov], name="Bao phủ nợ xấu %",
                                     line=dict(color=GREEN, width=2), mode="lines+markers"), secondary_y=True)
            figs.append(_style(fig, style, 300, "Chất lượng tài sản: Nợ xấu (trái) & Bao phủ nợ xấu (phải)"))
        return figs
    # Doanh nghiệp: cơ cấu tài sản & nguồn vốn
    ta = g("total_assets")
    cash = [(a or 0) + (b or 0) for a, b in zip(g("cash_and_cash_equivalents"), g("short_term_investments"))]
    rec, inv, fx = g("short_term_receivables"), g("inventories"), g("fixed_assets")
    other = [(t or 0) - c - (r or 0) - (i or 0) - (f or 0) for t, c, r, i, f in zip(ta, cash, rec, inv, fx)]
    fig = go.Figure()
    for vals, nm, clr in [(cash, "Tiền & ĐT ngắn hạn", GREEN), (rec, "Phải thu", YELLOW), (inv, "Tồn kho", PURPLE),
                          (fx, "TSCĐ", BLUE), (other, "Tài sản khác", "#3a5070")]:
        fig.add_trace(go.Bar(x=ys, y=vals, name=nm, marker_color=clr))
    fig.update_layout(barmode="stack")
    figs.append(_style(fig, style, 320, "Cơ cấu tài sản (tỷ đồng) — tiền nhiều, phải thu/tồn kho vừa phải là cơ cấu lành mạnh"))
    debt = [(a or 0) + (b or 0) for a, b in zip(g("short_term_borrowings"), g("long_term_borrowings"))]
    liab = g("total_liabilities"); eq = g("owners_equity")
    other_l = [(l or 0) - d for l, d in zip(liab, debt)]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for vals, nm, clr in [(debt, "Nợ vay", RED), (other_l, "Nợ chiếm dụng (phải trả, người mua trả trước…)", YELLOW),
                          (eq, "Vốn chủ sở hữu", GREEN)]:
        fig.add_trace(go.Bar(x=ys, y=vals, name=nm, marker_color=clr), secondary_y=False)
    am = res["annual"]
    if "Nợ vay/VCSH (x)" in am.index:
        fig.add_trace(go.Scatter(x=ys, y=am.loc["Nợ vay/VCSH (x)"], name="Nợ vay/VCSH (x)", mode="lines+markers",
                                 line=dict(color=CYAN, width=2)), secondary_y=True)
    fig.update_layout(barmode="stack")
    figs.append(_style(fig, style, 320, "Cơ cấu nguồn vốn (tỷ đồng) — nợ chiếm dụng không lãi tốt hơn nợ vay"))
    return figs


def chart_cashflow(fin, res, style):
    figs = []
    am = res["annual"]; ys = list(am.columns)
    cf = fin.get("cf_y")
    if res["com_type"] == "CT" and "Dòng tiền HĐKD (CFO)" in am.index:
        fig = go.Figure()
        fig.add_trace(go.Bar(x=ys, y=[_bn(v) for v in am.loc["LN sau thuế cổ đông mẹ"]], name="LNST", marker_color=BLUE))
        fig.add_trace(go.Bar(x=ys, y=[_bn(v) for v in am.loc["Dòng tiền HĐKD (CFO)"]], name="CFO", marker_color=GREEN))
        fig.add_trace(go.Scatter(x=ys, y=[_bn(v) for v in am.loc["Dòng tiền tự do (FCF)"]], name="FCF",
                                 mode="lines+markers", line=dict(color=YELLOW, width=2.5)))
        fig.update_layout(barmode="group")
        figs.append(_style(fig, style, 330, "Lợi nhuận có thành tiền không? CFO nên ≥ LNST qua nhiều năm (tỷ đồng)"))
    cys = fa.year_cols(cf)
    if cys:
        fig = go.Figure()
        for iid, nm, clr in [("net_cash_flows_from_operating_activities", "HĐ kinh doanh", GREEN),
                             ("net_cash_flows_from_investing_activities", "HĐ đầu tư", PURPLE),
                             ("net_cash_flows_from_financing_activities", "HĐ tài chính", YELLOW)]:
            fig.add_trace(go.Bar(x=cys, y=[_bn(v) for v in row_values(cf, iid, cys)], name=nm, marker_color=clr))
        fig.update_layout(barmode="relative")
        figs.append(_style(fig, style, 300, "3 dòng tiền (tỷ đồng) — mô hình khoẻ: KD dương, đầu tư âm (mở rộng), tài chính âm (trả nợ/cổ tức)"))
    return figs


def chart_valuation(fin, res, style):
    figs = []
    stats = [s for s in (fin.get("stats") or []) if s.get("year")][-24:]
    val = res["val"]
    for key, nm, cur, lim in [("pe", "P/E", val.get("pe"), 80), ("pb", "P/B", val.get("pb"), 20)]:
        pts = [(f"{int(s['year'])}Q{int(s['quarter'])}", float(s[key])) for s in stats
               if s.get(key) is not None and 0 < float(s[key]) < lim]
        if len(pts) < 6:
            continue
        x = [p[0] for p in pts]; y = [p[1] for p in pts]
        a = np.array(y)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=y, name=f"{nm} cuối quý", mode="lines+markers", line=dict(color=BLUE, width=2)))
        for q, clr, lab in [(25, GREEN, "P25 (rẻ)"), (50, MUTED, "Trung vị"), (75, RED, "P75 (đắt)")]:
            fig.add_hline(y=float(np.percentile(a, q)), line=dict(color=clr, dash="dot", width=1),
                          annotation_text=f" {lab} {np.percentile(a, q):.1f}x", annotation_font=dict(color=clr, size=10))
        if cur:
            fig.add_trace(go.Scatter(x=[x[-1]], y=[cur], name=f"{nm} hiện tại {cur:.1f}x", mode="markers",
                                     marker=dict(color=YELLOW, size=14, symbol="star")))
        figs.append(_style(fig, style, 300, f"Dải {nm} lịch sử ({len(pts)} quý) — vị trí hiện tại so với chính nó"))
    return figs


# ═════════════════════════════ RENDER ════════════════════════════════════════
def render(symbol: str, price: float, fin: dict, chart_style: dict):
    if not fin or fin.get("inc_y") is None or fin["inc_y"].empty:
        st.warning("Không lấy được BCTC cho mã này từ Vietcap.")
        if fin and fin.get("errors"):
            with st.expander("Chi tiết lỗi"):
                for e in fin["errors"]:
                    st.code(e)
        return

    det = fin.get("details") or {}
    ctype = fin.get("com_type") or "CT"
    c0, c1 = st.columns([3, 1])
    with c1:
        ref_rate = st.number_input("Lãi suất tham chiếu %/năm", 2.0, 15.0, 5.5, 0.25, key="bctc_ref_rate",
                                   help="Lãi tiết kiệm 12 tháng hoặc lợi suất TPCP. Dùng để so với lợi suất lợi nhuận (1/PE).")
    res = fa.analyze(fin, price, ref_rate)
    val, snap = res["val"], res["snap"]
    with c0:
        name = det.get("viOrganName") or symbol
        st.markdown(f"### 📑 {name}")
        st.caption(f"{COM_TYPES.get(ctype, ctype)} · Ngành: {det.get('sectorVn') or '—'} · "
                   f"BCTC mới nhất: quý {snap.get('latest_q') or '—'} · Nguồn: Vietcap IQ (BCTC hợp nhất, đã kiểm toán/soát xét theo kỳ)")

    # ── Hồ sơ nhanh ─────────────────────────────────────────────────────
    k = st.columns(6)
    k[0].markdown(_kpi("Vốn hoá", f"{val['market_cap']/1e12:,.1f} nghìn tỷ" if val.get("market_cap") else "—",
                       f"{val['shares']/1e6:,.0f} triệu CP" if val.get("shares") else ""), unsafe_allow_html=True)
    k[1].markdown(_kpi("P/E (TTM)", fa.fmt_x(val.get("pe")),
                       f"EPS 4 quý: {val['eps_ttm']:,.0f}đ" if fa._ok(val.get("eps_ttm")) else ""), unsafe_allow_html=True)
    k[2].markdown(_kpi("P/B", fa.fmt_x(val.get("pb"), 2),
                       f"BVPS: {val['bvps']:,.0f}đ" if fa._ok(val.get("bvps")) else ""), unsafe_allow_html=True)
    roe = fa._last(res["annual"], "ROE %")
    k[3].markdown(_kpi("ROE (năm gần nhất)", fa.fmt_pct(roe), "",
                       GREEN if fa._ok(roe) and roe >= 15 else (YELLOW if fa._ok(roe) and roe >= 10 else RED)), unsafe_allow_html=True)
    fp = det.get("foreignerPercentage"); fmax = det.get("maximumForeignPercentage")
    k[4].markdown(_kpi("Sở hữu nước ngoài", f"{fp*100:.1f}%" if fp is not None else "—",
                       f"Room tối đa {fmax*100:.0f}%" if fmax else ""), unsafe_allow_html=True)
    liq = det.get("averageMatchValue1Month")
    k[5].markdown(_kpi("Thanh khoản TB 1 tháng", f"{liq/1e9:,.0f} tỷ/phiên" if liq else "—",
                       f"Đỉnh/đáy 1 năm: {det.get('highestPrice1Year',0):,.0f} / {det.get('lowestPrice1Year',0):,.0f}"),
                  unsafe_allow_html=True)

    # ── Nhận định tổng hợp ──────────────────────────────────────────────
    q, v = res["quality"], res["value"]
    bars = ""
    for nm, p in res["pillars"].items():
        s = p["score"]; w = (s or 0) * 10; clr = _score_color(s)
        bars += (f"<div style='display:flex;align-items:center;gap:10px;margin:5px 0;'>"
                 f"<div style='width:190px;font-size:12px;color:#cce0ff;'>{nm}</div>"
                 f"<div style='flex:1;background:#102030;border-radius:4px;height:10px;'>"
                 f"<div style='width:{w:.0f}%;background:{clr};height:10px;border-radius:4px;'></div></div>"
                 f"<div style='width:46px;text-align:right;font-weight:700;color:{clr};'>{(f'{s:.1f}' if s is not None else '—')}</div></div>")
    _card(f"<div style='display:flex;gap:24px;flex-wrap:wrap;align-items:center;'>"
          f"<div style='min-width:260px;'><div style='font-size:12px;color:#6a9cc8;'>NHẬN ĐỊNH BCTC</div>"
          f"<div style='font-size:20px;font-weight:800;color:{res['color']};margin:4px 0;'>{res['stance']}</div>"
          f"<div style='font-size:12px;color:#8baed4;'>Chất lượng DN: <b style='color:{_score_color(q)}'>{(f'{q:.1f}' if q is not None else '—')}/10</b>"
          f" · Định giá: <b style='color:{_score_color(v)}'>{(f'{v:.1f}' if v is not None else '—')}/10</b></div>"
          f"<div style='font-size:10px;color:#4a6080;margin-top:6px;'>Bộ lọc cơ bản để quyết định CÓ NÊN quan tâm, "
          f"không phải tín hiệu thời điểm mua. Kết hợp tab Kỹ thuật/Quant để chọn điểm vào.</div></div>"
          f"<div style='flex:1;min-width:320px;'>{bars}</div></div>", res["color"] + "80")

    cs, cr = st.columns(2)
    with cs:
        st.markdown("#### ✅ Điểm mạnh")
        for s in res["strengths"] or ["Chưa có điểm nổi bật theo các ngưỡng đang dùng."]:
            st.markdown(f"<div style='border-left:3px solid {GREEN};padding:4px 10px;margin:4px 0;color:#cce0ff;font-size:13px;'>{s}</div>",
                        unsafe_allow_html=True)
    with cr:
        st.markdown("#### ⚠️ Rủi ro cần theo dõi")
        for s in res["risks"] or ["Không phát hiện cảnh báo lớn theo các ngưỡng đang dùng."]:
            st.markdown(f"<div style='border-left:3px solid {RED};padding:4px 10px;margin:4px 0;color:#cce0ff;font-size:13px;'>{s}</div>",
                        unsafe_allow_html=True)
    with st.expander("🔎 Chi tiết từng trụ cột (con số đằng sau điểm)"):
        for nm, p in res["pillars"].items():
            sc_txt = f"{p['score']:.1f}" if p["score"] is not None else "—"
            st.markdown(f"**{nm}** — {sc_txt}/10")
            for n in p["notes"]:
                st.markdown(f"- {n}")

    t = st.tabs(["📈 Kết quả kinh doanh", "🏦 Cân đối kế toán", "💵 Dòng tiền", "💲 Định giá",
                 "🧮 Chấm điểm", "📋 Báo cáo gốc", "📖 Giải thích chỉ số"])
    with t[0]:
        for f in chart_income(fin, res, chart_style):
            st.plotly_chart(f, use_container_width=True)
        g1, g2, g3, g4 = st.columns(4)
        g1.metric("Doanh thu 4 quý (tỷ)", f"{snap['rev_ttm']/1e9:,.0f}" if fa._ok(snap.get("rev_ttm")) else "—",
                  fa.fmt_pct(snap.get("rev_ttm_yoy")) if fa._ok(snap.get("rev_ttm_yoy")) else None)
        g2.metric("LNST 4 quý (tỷ)", f"{snap['npat_ttm']/1e9:,.0f}" if fa._ok(snap.get("npat_ttm")) else "—",
                  fa.fmt_pct(snap.get("npat_ttm_yoy")) if fa._ok(snap.get("npat_ttm_yoy")) else None)
        g3.metric(f"DT quý {snap.get('latest_q','')} vs cùng kỳ", fa.fmt_pct(snap.get("rev_q_yoy")))
        g4.metric(f"LNST quý {snap.get('latest_q','')} vs cùng kỳ", fa.fmt_pct(snap.get("npat_q_yoy")))
    with t[1]:
        for f in chart_balance(fin, res, chart_style):
            st.plotly_chart(f, use_container_width=True)
    with t[2]:
        figs = chart_cashflow(fin, res, chart_style)
        for f in figs:
            st.plotly_chart(f, use_container_width=True)
        if ctype in ("NH", "CK", "BH"):
            st.info("Với ngân hàng/chứng khoán/bảo hiểm, dòng tiền HĐKD biến động theo tiền gửi, cho vay, "
                    "giao dịch chứng khoán — không dùng tiêu chí 'CFO ≥ LNST' như doanh nghiệp thường.")
    with t[3]:
        v1, v2, v3, v4 = st.columns(4)
        v1.markdown(_kpi("Lợi suất lợi nhuận (1/PE)", fa.fmt_pct(val.get("earnings_yield")),
                         f"so với lãi suất {ref_rate:.2f}%",
                         GREEN if fa._ok(val.get("earnings_yield")) and val["earnings_yield"] > ref_rate else YELLOW),
                     unsafe_allow_html=True)
        v2.markdown(_kpi("EV/EBITDA", fa.fmt_x(val.get("ev_ebitda")), "Không áp dụng cho ngân hàng"), unsafe_allow_html=True)
        v3.markdown(_kpi("P/S", fa.fmt_x(val.get("ps"), 2), "Giá/doanh thu 4 quý"), unsafe_allow_html=True)
        v4.markdown(_kpi("Cổ tức tiền mặt/vốn hoá", fa.fmt_pct(val.get("div_yield")), "Theo tiền cổ tức đã trả năm gần nhất"),
                    unsafe_allow_html=True)
        for f in chart_valuation(fin, res, chart_style):
            st.plotly_chart(f, use_container_width=True)
        rows = []
        if val.get("fair_pe"):
            fp_ = val["fair_pe"]
            rows.append(["P/E lịch sử × EPS 4 quý", fp_["low"], fp_["mid"], fp_["high"]])
        if val.get("fair_pb"):
            fb = val["fair_pb"]
            rows.append(["P/B lịch sử × BVPS", fb["low"], fb["mid"], fb["high"]])
        if rows:
            st.markdown("##### Vùng giá tham chiếu theo bội số lịch sử của chính doanh nghiệp")
            tb = pd.DataFrame(rows, columns=["Phương pháp", "Thấp (P25)", "Trung vị", "Cao (P75)"])
            for c in ["Thấp (P25)", "Trung vị", "Cao (P75)"]:
                tb[c] = tb[c].map(lambda x: f"{x:,.0f}")
            st.dataframe(tb, use_container_width=True, hide_index=True)
            st.caption(f"Giá hiện tại: {price:,.0f}đ. Đây là vùng giá NẾU thị trường định giá DN như trung bình 5 năm qua — "
                       "không phải giá mục tiêu. Nếu triển vọng thay đổi (tăng trưởng chậm lại, rủi ro tăng), bội số hợp lý cũng đổi.")
        if val.get("analyst_target"):
            st.caption(f"Tham khảo — Vietcap: {val.get('analyst_rating') or ''} · giá mục tiêu {val['analyst_target']:,.0f}đ "
                       f"({val['analyst_upside']:+.0f}% so với giá hiện tại) · ngày {det.get('ratingAsOf') or ''}. "
                       "Đây là ý kiến của CTCK, không phải dữ kiện.")
    with t[4]:
        pio, alt = res["piotroski"], res["altman"]
        if pio:
            clr = GREEN if pio["score"] >= 7 else (YELLOW if pio["score"] >= 4 else RED)
            st.markdown(f"#### Piotroski F-Score: <span style='color:{clr}'>{pio['score']}/9</span> "
                        f"<span style='font-size:12px;color:#6a9cc8'>(năm {pio['year']} so với {pio['base']})</span>",
                        unsafe_allow_html=True)
            pdf = pd.DataFrame(pio["checks"]); pdf["đạt"] = pdf["đạt"].map({True: "✅", False: "❌"})
            st.dataframe(pdf, use_container_width=True, hide_index=True)
        if alt:
            clr = GREEN if alt["zone"] == "An toàn" else (YELLOW if alt["zone"] == "Vùng xám" else RED)
            st.markdown(f"#### Altman Z''-Score: <span style='color:{clr}'>{alt['z']:.2f} — {alt['zone']}</span> "
                        f"<span style='font-size:12px;color:#6a9cc8'>(năm {alt['year']})</span>", unsafe_allow_html=True)
            st.dataframe(pd.DataFrame([
                ["X1 Vốn lưu động/Tổng TS", alt["x1"], 6.56, "Đệm thanh khoản ngắn hạn"],
                ["X2 LN chưa phân phối/Tổng TS", alt["x2"], 3.26, "Lợi nhuận tích luỹ (DN càng lâu năm, càng có lãi càng cao)"],
                ["X3 EBIT/Tổng TS", alt["x3"], 6.72, "Khả năng sinh lời của tài sản — trọng số lớn nhất"],
                ["X4 VCSH/Nợ phải trả", alt["x4"], 1.05, "Đệm vốn trước khi chủ nợ bị ảnh hưởng"],
            ], columns=["Thành phần", "Giá trị", "Hệ số", "Ý nghĩa"]).round(3), use_container_width=True, hide_index=True)
        if not pio and not alt:
            st.info("Piotroski và Altman được thiết kế cho doanh nghiệp phi tài chính — không áp dụng cho "
                    f"{COM_TYPES.get(ctype, ctype).lower()}. Xem các chỉ số đặc thù ở phần nhận định phía trên.")
        am = res["annual"]
        if not am.empty:
            st.markdown("#### Bảng chỉ số theo năm (tự tính từ BCTC gốc)")
            disp = am.copy()
            for idx in disp.index:
                money = not any(tok in idx for tok in ("%", "(x)", "Số ngày"))
                disp.loc[idx] = [(x / 1e9 if money else x) if fa._ok(x) else None for x in am.loc[idx]]
            disp.index = [i + (" (tỷ)" if not any(tok in i for tok in ("%", "(x)", "Số ngày")) else "") for i in disp.index]
            st.dataframe(disp.round(2), use_container_width=True)
    with t[5]:
        a1, a2, a3 = st.columns([2, 1, 1])
        rep = a1.radio("Báo cáo", ["Kết quả kinh doanh", "Cân đối kế toán", "Lưu chuyển tiền tệ"], horizontal=True, key="bctc_rep")
        per = a2.radio("Kỳ", ["Năm", "Quý"], horizontal=True, key="bctc_per")
        nper = a3.slider("Số kỳ", 4, 12, 8, key="bctc_nper")
        key = {"Kết quả kinh doanh": "inc", "Cân đối kế toán": "bal", "Lưu chuyển tiền tệ": "cf"}[rep] + ("_y" if per == "Năm" else "_q")
        tbl = statement_table(fin.get(key), nper)
        if tbl.empty:
            st.info("Không có dữ liệu.")
        else:
            st.caption("Đơn vị: tỷ đồng (EPS: đồng). Cột cuối: % thay đổi so với cùng kỳ (chỉ tính khi kỳ so sánh dương).")
            num_cols = [c for c in tbl.columns if c != "Chỉ tiêu"]
            st.dataframe(tbl.style.format({c: "{:,.1f}" for c in num_cols}, na_rep="—"),
                         use_container_width=True, hide_index=True, height=520)
            buf = io.StringIO(); tbl.to_csv(buf, index=False)
            st.download_button("⬇️ Tải CSV", buf.getvalue().encode("utf-8-sig"),
                               file_name=f"{symbol}_{key}.csv", mime="text/csv", key="bctc_dl")
    with t[6]:
        st.markdown("Mỗi chỉ số trả lời một câu hỏi về doanh nghiệp. Hiểu câu hỏi trước, rồi mới nhìn con số.")
        for nm, txt in fa.GLOSSARY.items():
            st.markdown(f"**{nm}** — {txt}")
        st.caption("Giới hạn: số liệu là BCTC hợp nhất do Vietcap tổng hợp; chưa đọc thuyết minh (nợ tiềm tàng, giao dịch bên liên quan, "
                   "nợ nhóm 2/tái cơ cấu của ngân hàng). Trước khi giải ngân lớn, hãy đọc thuyết minh và ý kiến kiểm toán.")
