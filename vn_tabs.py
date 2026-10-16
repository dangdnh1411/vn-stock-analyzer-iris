"""
vn_tabs.py — Giao diện 3 tab: 🌊 Dòng tiền & Volume · 🇻🇳 Thị trường VN · 📒 Nhật ký lệnh.
Mỗi khối dữ liệu có try/except riêng: một nguồn hỏng chỉ làm trống khối đó, không sập tab.
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

import flow_analysis as fl
import journal as jr
import swing_setups as ss
import vn_data as vnd
import vn_market as vm

GREEN, YELLOW, RED, BLUE, PURPLE, CYAN, MUTED = "#00d97e", "#f5a623", "#ff3d5a", "#4a9ef8", "#a78bfa", "#22d3ee", "#8baed4"


# ═════════════════════════════ CACHE DỮ LIỆU ══════════════════════════════════
@st.cache_data(ttl=300, show_spinner=False)
def _hist(sym, days=420):
    try:
        df, _ = vnd.get_history(sym, days, "1D")
        return df
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def _foreign(sym, pages=4):
    return vm.foreign_history(sym, pages)


@st.cache_data(ttl=900, show_spinner=False)
def _prop(sym):
    return vm.prop_history(sym)


@st.cache_data(ttl=900, show_spinner=False)
def _orders(sym):
    return vm.order_stats(sym)


@st.cache_data(ttl=120, show_spinner=False)
def _ticks(sym):
    return vm.intraday_ticks(sym)


@st.cache_data(ttl=120, show_spinner=False)
def _board(syms: tuple):
    return vm.board(list(syms))


@st.cache_data(ttl=86400, show_spinner=False)
def _group(g):
    return vm.group_symbols(g)


@st.cache_data(ttl=86400, show_spinner=False)
def _sector_map():
    return vm.sector_map()


@st.cache_data(ttl=86400, show_spinner=False)
def _icb_map():
    return vm.icb_map()


@st.cache_data(ttl=300, show_spinner=False)
def _sectors():
    return vm.sectors()


@st.cache_data(ttl=3600, show_spinner=False)
def _peers(syms: tuple):
    return vm.peer_metrics(list(syms))


@st.cache_data(ttl=900, show_spinner=False)
def _scan_swing(group: str, top_n: int = 120):
    """Quét nhóm mã: giai đoạn xả cạn & cảnh báo bơm. Gọi thẳng nguồn dữ liệu trong luồng phụ (không qua cache)."""
    from concurrent.futures import ThreadPoolExecutor
    syms = vm.group_symbols(group)
    if group in ("HOSE", "HNX", "UPCOM") and len(syms) > top_n:
        bd = vm.board(syms)
        if not bd.empty:
            syms = bd.sort_values("value", ascending=False)["symbol"].head(top_n).tolist()
        else:
            syms = syms[:top_n]

    def one(sym):
        try:
            px, _ = vnd.get_history(sym, 420, "1D")
            if px is None or len(px) < 80:
                return None
            res = fl.analyze_flow(px)
            sw = ss.analyze_swing(res["d"])
            if not sw:
                return None
            last = res["d"].iloc[-1]
            tags = sw["recent_tags"]
            lt = f"{ss.TAG_INFO[tags[-1][1]][0]} {tags[-1][0]:%d/%m}" if tags else ""
            return {"Mã": sym, "Giai đoạn": sw["stage"], "Tên giai đoạn": sw["stage_name"],
                    "Điểm xả cạn (0–5)": sw["dry_score"], "Bối cảnh xấu": "Có" if sw["weak_ctx"] else "",
                    "Mốc gần nhất": lt, "Cảnh báo bơm": sw["pump"]["level"] if sw["pump"]["ctx"] else 0,
                    "Số cờ bơm": len(sw["pump"]["flags"]),
                    "Giá": float(last["Close"]), "% 5 phiên": float((last["Close"] / res["d"]["Close"].iloc[-6] - 1) * 100),
                    "GTGD TB20 (tỷ)": float(last["val_ma20"]) if not pd.isna(last["val_ma20"]) else 0.0}
        except Exception:  # noqa: BLE001
            return None

    with ThreadPoolExecutor(max_workers=8) as ex:
        rows = [r for r in ex.map(one, syms) if r]
    return pd.DataFrame(rows)


def _style(fig, style, h=320, title=None):
    fig.update_layout(height=h, template="plotly_dark", **style)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(color="#8baed4", size=13)))
    return fig


def _card(html, border="#163350"):
    st.markdown(f"<div style='background:#0c1d2e;border:1px solid {border};border-radius:10px;"
                f"padding:12px 16px;margin:6px 0;'>{html}</div>", unsafe_allow_html=True)


def _kpi(label, value, sub="", color="#ffffff"):
    return (f"<div style='background:#0c1d2e;border:1px solid #163350;border-radius:8px;padding:8px 10px;'>"
            f"<div style='font-size:11px;color:#6a9cc8;'>{label}</div>"
            f"<div style='font-size:18px;font-weight:700;color:{color};'>{value}</div>"
            f"<div style='font-size:10px;color:#4a6080;'>{sub}</div></div>")


def _signal_html(bias, title, why):
    clr = GREEN if bias > 0 else (RED if bias < 0 else YELLOW)
    ico = "▲" if bias > 0 else ("▼" if bias < 0 else "●")
    return (f"<div style='border-left:3px solid {clr};padding:4px 10px;margin:4px 0;'>"
            f"<span style='color:{clr};font-weight:700;'>{ico} {title}</span>"
            f"<div style='font-size:12px;color:#8baed4;'>{why}</div></div>")


# ═════════════════════════════ TAB 🌊 DÒNG TIỀN & VOLUME ══════════════════════
def render_flow(symbol: str, chart_style: dict):
    sym = symbol.upper()
    with st.spinner("Đang tải lịch sử giá, khối ngoại, tự doanh, sổ lệnh và khớp lệnh trong phiên..."):
        px = _hist(sym)
        fr, pr, od, tk = _foreign(sym), _prop(sym), _orders(sym), _ticks(sym)
    if px is None or len(px) < 30:
        st.warning("Không đủ dữ liệu giá để phân tích dòng tiền.")
        return
    intr = fl.intraday_analysis(tk) if tk is not None and not tk.empty else {}
    res = fl.analyze_flow(px, fr, pr, od, intr)
    d = res["d"]
    ph, ph_clr, ph_txt = res["phase"]
    sc = res["score"]
    srcs = [n for n, x in [("khối ngoại", fr), ("tự doanh", pr), ("sổ lệnh", od), ("khớp lệnh phiên", tk)]
            if x is not None and not x.empty]
    w = (sc + 10) / 20 * 100
    _card(f"<div style='display:flex;gap:24px;flex-wrap:wrap;align-items:center;'>"
          f"<div style='min-width:280px;'><div style='font-size:12px;color:#6a9cc8;'>GIAI ĐOẠN DÒNG TIỀN</div>"
          f"<div style='font-size:22px;font-weight:800;color:{ph_clr};margin:4px 0;'>{ph}</div>"
          f"<div style='font-size:12px;color:#8baed4;'>{ph_txt}</div></div>"
          f"<div style='flex:1;min-width:280px;'><div style='font-size:12px;color:#6a9cc8;'>ĐIỂM DÒNG TIỀN "
          f"<b style='color:{ph_clr};font-size:18px;'>{sc:+.1f}</b> / ±10</div>"
          f"<div style='background:linear-gradient(90deg,#ff3d5a,#f5a623 50%,#00d97e);height:10px;border-radius:5px;position:relative;margin-top:8px;'>"
          f"<div style='position:absolute;left:calc({w:.0f}% - 6px);top:-4px;width:12px;height:18px;background:#fff;border-radius:3px;'></div></div>"
          f"<div style='font-size:10px;color:#4a6080;margin-top:6px;'>25 phiên gần nhất: {res['n_pos']} phiên tích cực · {res['n_neg']} phiên tiêu cực · "
          f"Nguồn: giá KBS{(' + ' + ', '.join(srcs)) if srcs else ''}</div></div></div>", ph_clr + "80")

    st.markdown("#### 🔎 Dấu hiệu nhận định")
    sigs = sorted(res["signals"], key=lambda s: -abs(s[0]))
    c1, c2 = st.columns(2)
    for i, s in enumerate(sigs):
        (c1 if i % 2 == 0 else c2).markdown(_signal_html(*s), unsafe_allow_html=True)
    if not sigs:
        st.info("Chưa có dấu hiệu dòng tiền nổi bật.")

    sw = {}
    try:
        sw = ss.analyze_swing(d, intr, fr, pr, od, res.get("vp"))
    except Exception as e:  # noqa: BLE001
        st.warning(f"Không tính được thiết lập lướt sóng: {type(e).__name__}: {e}")
    if sw:
        _render_swing(sym, sw, d, res, chart_style)

    # ── Biểu đồ nến + volume gắn nhãn sự kiện ─────────────────────────────
    show = d.tail(120)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.68, 0.32], vertical_spacing=0.03)
    fig.add_trace(go.Candlestick(x=show["Date"], open=show["Open"], high=show["High"], low=show["Low"], close=show["Close"],
                                 name="Giá", increasing_line_color=GREEN, decreasing_line_color=RED), row=1, col=1)
    fig.add_trace(go.Scatter(x=show["Date"], y=show["vwap20"], name="VWAP20", line=dict(color=YELLOW, width=1.4, dash="dot")), row=1, col=1)
    if res["vp"]:
        fig.add_hline(y=res["vp"]["poc"], line=dict(color=PURPLE, width=1, dash="dash"), row=1, col=1,
                      annotation_text=f" POC {res['vp']['poc']:,.0f}", annotation_font=dict(color=PURPLE, size=10))
    ev = show[show["event"].notna()]
    for code, grp in ev.groupby("event"):
        lab, bias, _ = fl.EVENT_INFO[code]
        clr = GREEN if bias > 0 else (RED if bias < 0 else YELLOW)
        ypos = grp["High"] * 1.015 if bias >= 0 else grp["Low"] * 0.985
        fig.add_trace(go.Scatter(x=grp["Date"], y=ypos, mode="markers", name=lab,
                                 marker=dict(symbol="triangle-down" if bias < 0 else "triangle-up", size=11, color=clr,
                                             line=dict(color="#fff", width=0.5)),
                                 hovertext=[f"{lab}<br>{r.ret:+.1f}% · vol x{r.vr:.1f}" for r in grp.itertuples()],
                                 hoverinfo="text"), row=1, col=1)
    if sw:
        tg = sw["xs"].tail(120)
        tg = tg[tg["stage_tag"].apply(lambda t: isinstance(t, str))]
        sym_map = {"dry": "circle-open", "test": "diamond", "sos": "star", "lps": "triangle-up-open", "fail": "x"}
        for code, grp in tg.groupby("stage_tag"):
            lab, clr = ss.TAG_INFO[code]
            fig.add_trace(go.Scatter(x=grp["Date"], y=grp["Low"] * 0.965, mode="markers", name=lab,
                                     marker=dict(symbol=sym_map.get(code, "circle"), size=13, color=clr,
                                                 line=dict(color="#fff", width=1)),
                                     hovertext=[f"{lab}<br>{r.Date:%d/%m/%Y} · {r.ret:+.1f}% · vol x{r.vr:.1f}" for r in grp.itertuples()],
                                     hoverinfo="text"), row=1, col=1)
    vcol = []
    for r in show.itertuples():
        if r.event:
            b = fl.EVENT_INFO[r.event][1]; vcol.append(GREEN if b > 0 else (RED if b < 0 else YELLOW))
        else:
            vcol.append("#2a4a6a")
    fig.add_trace(go.Bar(x=show["Date"], y=show["Volume"], marker_color=vcol, name="Volume", showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=show["Date"], y=show["vol_ma20"], name="Vol TB20", line=dict(color=MUTED, width=1)), row=2, col=1)
    fig.update_layout(xaxis_rangeslider_visible=False)
    st.plotly_chart(_style(fig, chart_style, 560, "120 phiên: tam giác = loại phiên · ◆ test cung · ★ cầu vào · ✖ thủng nền · cột vol tô màu theo loại phiên"),
                    use_container_width=True)

    st.markdown("#### 📅 Các phiên đáng chú ý (60 phiên gần nhất)")
    et = res["events"]
    if et.empty:
        st.info("Không có phiên bất thường về volume trong 60 phiên.")
    else:
        st.dataframe(et.drop(columns=["_bias", "_code"]), use_container_width=True, hide_index=True,
                     height=min(420, 38 + 35 * len(et)))

    t = st.tabs(["📊 Chỉ báo dòng tiền", "🧱 Vùng giá khối lượng", "🌏 Khối ngoại", "🏦 Tự doanh",
                 "📝 Sổ lệnh cung/cầu", "⏱️ Trong phiên", "📖 Giải thích"])
    with t[0]:
        s = d.tail(120)
        f2 = make_subplots(specs=[[{"secondary_y": True}]])
        f2.add_trace(go.Scatter(x=s["Date"], y=s["Close"], name="Giá", line=dict(color=BLUE, width=2)), secondary_y=False)
        f2.add_trace(go.Scatter(x=s["Date"], y=s["obv"], name="OBV", line=dict(color=GREEN, width=1.5)), secondary_y=True)
        f2.add_trace(go.Scatter(x=s["Date"], y=s["ad"], name="A/D", line=dict(color=PURPLE, width=1.2, dash="dot")), secondary_y=True)
        st.plotly_chart(_style(f2, chart_style, 300, "Giá vs OBV & A/D — hai đường đi ngược nhau = phân kỳ dòng tiền"), use_container_width=True)
        f3 = make_subplots(specs=[[{"secondary_y": True}]])
        f3.add_trace(go.Bar(x=s["Date"], y=s["cmf20"], name="CMF(20)",
                            marker_color=[GREEN if v >= 0 else RED for v in s["cmf20"].fillna(0)]), secondary_y=False)
        f3.add_trace(go.Scatter(x=s["Date"], y=s["mfi14"], name="MFI(14)", line=dict(color=YELLOW, width=1.5)), secondary_y=True)
        st.plotly_chart(_style(f3, chart_style, 260, "CMF (cột) & MFI (đường, 80 quá mua / 20 quá bán)"), use_container_width=True)
        f4 = go.Figure()
        f4.add_trace(go.Bar(x=s["Date"], y=s["value_bn"], name="Giá trị GD (tỷ)", marker_color="#2a4a6a"))
        f4.add_trace(go.Scatter(x=s["Date"], y=s["val_ma20"], name="TB20", line=dict(color=CYAN, width=1.5)))
        f4.add_trace(go.Scatter(x=s["Date"], y=s["val_ma60"], name="TB60", line=dict(color=MUTED, width=1.2, dash="dot")))
        st.plotly_chart(_style(f4, chart_style, 240, "Thanh khoản (tỷ đồng) — TB20 cắt lên TB60 = tiền đang chú ý mã này"), use_container_width=True)
    with t[1]:
        vp = res["vp"]
        if vp:
            last = float(d["Close"].iloc[-1])
            clrs = [PURPLE if abs(m - vp["poc"]) < 1e-6 else (BLUE if vp["va_low"] <= m <= vp["va_high"] else "#2a4a6a") for m in vp["mids"]]
            f5 = go.Figure(go.Bar(x=vp["vol"], y=vp["mids"], orientation="h", marker_color=clrs, name="KL"))
            f5.add_hline(y=last, line=dict(color=YELLOW, width=1.5), annotation_text=f" Giá hiện tại {last:,.0f}")
            st.plotly_chart(_style(f5, chart_style, 420, f"Volume Profile {vp['n']} phiên — tím: POC {vp['poc']:,.0f} · xanh: vùng 70% KL "
                                                      f"{vp['va_low']:,.0f}–{vp['va_high']:,.0f}"), use_container_width=True)
            where = ("TRÊN vùng giá trị — người mua đều có lãi, vùng VA là hỗ trợ" if last > vp["va_high"] else
                     "DƯỚI vùng giá trị — nhiều người đang kẹt hàng, VA là kháng cự" if last < vp["va_low"] else
                     "TRONG vùng giá trị — giá đang ở vùng cân bằng")
            st.info(f"Giá hiện tại nằm {where}.")
    with t[2]:
        if fr is None or fr.empty:
            st.info("Không lấy được dữ liệu khối ngoại (CafeF).")
        else:
            f6 = make_subplots(specs=[[{"secondary_y": True}]])
            f6.add_trace(go.Bar(x=fr["Date"], y=fr["net_val"] / 1e9, name="Mua/bán ròng (tỷ)",
                                marker_color=[GREEN if v >= 0 else RED for v in fr["net_val"]]), secondary_y=False)
            f6.add_trace(go.Scatter(x=fr["Date"], y=(fr["net_val"].cumsum()) / 1e9, name="Luỹ kế (tỷ)",
                                    line=dict(color=YELLOW, width=2)), secondary_y=True)
            st.plotly_chart(_style(f6, chart_style, 320, "Khối ngoại mua/bán ròng theo ngày & luỹ kế"), use_container_width=True)
            k = st.columns(4)
            for col, n in zip(k[:3], (5, 20, len(fr))):
                v = fr["net_val"].tail(n).sum() / 1e9
                col.markdown(_kpi(f"Ròng {n} phiên", f"{v:+,.0f} tỷ", "", GREEN if v >= 0 else RED), unsafe_allow_html=True)
            last = fr.iloc[-1]
            k[3].markdown(_kpi("Sở hữu NN / Room còn", f"{last['own_pct']:.2f}%" if pd.notna(last["own_pct"]) else "—",
                               f"Room còn {last['room_left']/1e6:,.1f} triệu CP" if pd.notna(last["room_left"]) else ""), unsafe_allow_html=True)
            if pd.notna(last["room_left"]) and last["room_left"] <= 0:
                st.warning("Hết room ngoại — khối ngoại chỉ có thể bán, không mua thêm được (trừ khi có người bán ra).")
    with t[3]:
        if pr is None or pr.empty:
            st.info("Không lấy được dữ liệu tự doanh (CafeF).")
        else:
            p = pr.tail(120)
            f7 = make_subplots(specs=[[{"secondary_y": True}]])
            f7.add_trace(go.Bar(x=p["Date"], y=p["net_val"] / 1e9, name="Tự doanh ròng (tỷ)",
                                marker_color=[GREEN if v >= 0 else RED for v in p["net_val"]]), secondary_y=False)
            f7.add_trace(go.Scatter(x=p["Date"], y=p["net_val"].cumsum() / 1e9, name="Luỹ kế", line=dict(color=YELLOW, width=2)), secondary_y=True)
            st.plotly_chart(_style(f7, chart_style, 320, "Tự doanh CTCK mua/bán ròng (120 phiên)"), use_container_width=True)
            st.caption("Tự doanh hay giao dịch theo rổ ETF/phái sinh — mua/bán ròng mạnh quanh ngày đáo hạn phái sinh "
                       f"(gần nhất: {vm.derivatives_expiry():%d/%m/%Y}) thường là giao dịch kỹ thuật, không hẳn là quan điểm về doanh nghiệp.")
    with t[4]:
        if od is None or od.empty:
            st.info("Không lấy được thống kê đặt lệnh (CafeF).")
        else:
            f8 = make_subplots(specs=[[{"secondary_y": True}]])
            f8.add_trace(go.Bar(x=od["Date"], y=od["imbalance"] * 100, name="Dư mua/bán đặt lệnh %",
                                marker_color=[GREEN if v >= 0 else RED for v in od["imbalance"].fillna(0)]), secondary_y=False)
            f8.add_trace(go.Scatter(x=od["Date"], y=od["avg_buy"], name="KL TB 1 lệnh MUA", line=dict(color=GREEN, width=1.5)), secondary_y=True)
            f8.add_trace(go.Scatter(x=od["Date"], y=od["avg_sell"], name="KL TB 1 lệnh BÁN", line=dict(color=RED, width=1.5)), secondary_y=True)
            st.plotly_chart(_style(f8, chart_style, 320, "Cung/cầu trên sổ lệnh: dư đặt mua/bán (cột) & cỡ lệnh trung bình (đường)"),
                            use_container_width=True)
            st.caption("Cỡ lệnh MUA trung bình tăng vọt so với lệnh BÁN = tay to đang mua, nhỏ lẻ đang bán (và ngược lại).")
    with t[5]:
        if not intr:
            st.info("Không lấy được dữ liệu khớp lệnh trong phiên.")
        else:
            st.caption(f"Phiên {intr['session']:%d/%m/%Y} · {len(tk):,} lệnh khớp · {intr['total_vol']:,.0f} CP · {intr['total_val']/1e9:,.1f} tỷ")
            k = st.columns(4)
            br = intr["buy_ratio"]
            k[0].markdown(_kpi("Mua chủ động", f"{intr['buy_vol']:,.0f}", f"{intr['buy_val']/1e9:,.1f} tỷ", GREEN), unsafe_allow_html=True)
            k[1].markdown(_kpi("Bán chủ động", f"{intr['sell_vol']:,.0f}", f"{intr['sell_val']/1e9:,.1f} tỷ", RED), unsafe_allow_html=True)
            k[2].markdown(_kpi("Tỷ lệ mua chủ động", f"{br:.0f}%" if br is not None else "—", "ATO/ATC không tính",
                               GREEN if br and br >= 55 else (RED if br and br <= 45 else "#fff")), unsafe_allow_html=True)
            k[3].markdown(_kpi(f"Lệnh lớn ≥{intr['big_thr_bn']:.1f} tỷ", f"{intr['big_buy_bn']-intr['big_sell_bn']:+,.1f} tỷ ròng",
                               f"Mua {intr['big_buy_bn']:,.1f} · Bán {intr['big_sell_bn']:,.1f} · {intr['big_n']} lệnh"), unsafe_allow_html=True)
            ser = intr["series"]
            f9 = make_subplots(specs=[[{"secondary_y": True}]])
            f9.add_trace(go.Scatter(x=ser["time"], y=ser["price"], name="Giá khớp", line=dict(color=BLUE, width=1.5)), secondary_y=False)
            f9.add_trace(go.Scatter(x=ser["time"], y=ser["cum_delta"], name="Delta luỹ kế (mua − bán chủ động)",
                                    line=dict(color=YELLOW, width=1.5), fill="tozeroy", fillcolor="rgba(245,166,35,0.08)"), secondary_y=True)
            st.plotly_chart(_style(f9, chart_style, 320, "Giá vs delta luỹ kế — giá tăng mà delta giảm = bị bán chủ động vào lực kéo"),
                            use_container_width=True)
            prof = intr["time_profile"]
            f10 = go.Figure()
            for side, clr in [("Mua chủ động", GREEN), ("Bán chủ động", RED), ("ATO/ATC", YELLOW)]:
                if side in prof.columns:
                    f10.add_trace(go.Bar(x=prof.index, y=prof[side], name=side, marker_color=clr))
            f10.update_layout(barmode="stack")
            st.plotly_chart(_style(f10, chart_style, 260, "Khối lượng theo khung 30 phút"), use_container_width=True)
            if intr["atc"]:
                a = intr["atc"]
                st.markdown(f"**ATC:** giá {a['atc_price']:,.0f} so với lệnh liên tục cuối {a['last_continuous']:,.0f} "
                            f"(**{a['atc_chg_pct']:+.2f}%**), chiếm {a['atc_vol_share']:.0f}% khối lượng phiên.")
            if not intr["big_orders"].empty:
                st.markdown("##### Lệnh lớn nhất phiên")
                bo = intr["big_orders"].copy()
                bo["time"] = bo["time"].dt.strftime("%H:%M:%S"); bo["value"] = (bo["value"] / 1e9).round(2)
                st.dataframe(bo.rename(columns={"time": "Giờ", "price": "Giá", "vol": "KL", "side": "Bên", "value": "Giá trị (tỷ)"}),
                             use_container_width=True, hide_index=True)
    with t[6]:
        for k_, v in fl.FLOW_GLOSSARY.items():
            st.markdown(f"**{k_}** — {v}")
        st.markdown("**Các loại phiên:**")
        for code, (lab, bias, mean) in fl.EVENT_INFO.items():
            st.markdown(f"- **{lab}** — {mean}")
        st.caption("Lưu ý: đây là đọc dấu vết dòng tiền từ dữ liệu công khai, không xác định được danh tính người mua/bán. "
                   "Dùng để đặt câu hỏi và xác nhận, không dùng một mình để ra quyết định.")

    _render_swing_scanner()


# ═════════════════════════════ THIẾT LẬP LƯỚT SÓNG ════════════════════════════
def _stepper(sw):
    done = [sw["sell_wave"], sw["stage"] >= 1, sw["stage"] >= 2, sw["stage"] >= 3, sw["stage"] >= 4]
    names = ["Xả mạnh", "Xả cạn", "Test cung", "Cầu vào", "Giữ nhịp"]
    cells = []
    for i, (n, ok) in enumerate(zip(names, done)):
        clr = GREEN if ok else "#2a4a6a"
        cells.append(f"<div style='flex:1;text-align:center;padding:6px 2px;border-radius:6px;background:{clr}22;"
                     f"border:1px solid {clr};color:{'#fff' if ok else '#6a8aaa'};font-size:12px;font-weight:{700 if ok else 400};'>"
                     f"{'✔' if ok else i + 1} {n}</div>")
    return "<div style='display:flex;gap:6px;margin:8px 0;'>" + "".join(cells) + "</div>"


def _render_swing(sym, sw, d, res, chart_style):
    st.markdown("#### 🎯 Thiết lập lướt sóng theo dòng tiền")
    st.caption("Hai câu hỏi: (1) mã xấu đã XẢ CẠN chưa — bắt dần được chưa? (2) đợt tăng có BÊN MUA THẬT không hay đang bơm để xả?")
    a, b = st.columns([3, 2])
    with a:
        stg = sw["stage"]
        ctx = ("Bối cảnh phù hợp: mã đang xấu (dưới EMA50, đã giảm sâu) và đã có đợt xả có vol." if sw["weak_ctx"] and sw["sell_wave"]
               else "Mã chưa ở bối cảnh 'bị xả mạnh rồi cạn' — thiết lập này chủ yếu dành cho mã đã giảm sâu." if not sw["weak_ctx"]
               else "Mã đang xấu nhưng CHƯA thấy đợt xả có vol rõ ràng — nguồn cung chưa lộ diện hết.")
        clr = GREEN if stg >= 3 else (CYAN if stg >= 1 else MUTED)
        _card(f"<div style='font-size:12px;color:#6a9cc8;'>BẮT ĐÁY KHI XẢ CẠN · giai đoạn</div>"
              f"<div style='font-size:20px;font-weight:800;color:{clr};'>{stg}/4 — {sw['stage_name'].upper()}</div>"
              + _stepper(sw) +
              f"<div style='font-size:12px;color:#cce0ff;'>{sw['stage_note']}</div>"
              f"<div style='font-size:11px;color:#6a8aaa;margin-top:4px;'>{ctx}</div>", clr + "80")
        st.markdown(f"**Điều kiện xả cạn — đạt {sw['dry_score']}/5** (cần ≥3 để vào giai đoạn 1)")
        for ok, name, ev_ in sw["checklist"]:
            st.markdown(f"{'✅' if ok else '⬜'} **{name}** — <span style='color:#8baed4;font-size:12px;'>{ev_}</span>",
                        unsafe_allow_html=True)
        if sw["recent_tags"]:
            st.markdown("**Các mốc trong 30 phiên:** " + " → ".join(f"{ss.TAG_INFO[t][0]} ({dt:%d/%m})" for dt, t in sw["recent_tags"]))
        if sw["confirms"] and stg >= 1:
            st.success("Xác nhận cầu chủ động: " + " · ".join(sw["confirms"]))
    with b:
        pc = sw["pump"]
        _card(f"<div style='font-size:12px;color:#6a9cc8;'>KIỂM TRA BƠM GIÁ · cầu có thật không?</div>"
              f"<div style='font-size:14px;font-weight:700;color:{pc['color']};margin:4px 0;'>{pc['verdict']}</div>"
              f"<div style='font-size:11px;color:#6a8aaa;'>{len(pc['flags'])} dấu hiệu cầu rỗng · {len(pc['positives'])} dấu hiệu cầu thật</div>",
              pc["color"] + "80")
        for t_, why in pc["flags"]:
            st.markdown(_signal_html(-1, t_, why), unsafe_allow_html=True)
        for t_, why in pc["positives"]:
            st.markdown(_signal_html(+1, t_, why), unsafe_allow_html=True)

    last = d.iloc[-1]
    with st.expander("📋 Kế hoạch bắt dần 3 phần (tính theo rủi ro)", expanded=sw["stage"] >= 2):
        k = st.columns(3)
        cap = k[0].number_input("Vốn (triệu đ)", min_value=1.0, value=100.0, step=10.0, key="sw_cap") * 1e6
        rp = k[1].number_input("Tổng rủi ro cho thiết lập (% vốn)", 0.1, 3.0, 0.5, 0.1, key="sw_rp",
                               help="Mã xấu → nên bằng một nửa lệnh thường. 0.5% vốn = mất tối đa 500 nghìn với vốn 100 triệu nếu sai.")
        mw = k[2].number_input("Tỷ trọng tối đa cả 3 phần (% vốn)", 5.0, 50.0, 20.0, 5.0, key="sw_mw")
        vp = res.get("vp") or {}
        pl = ss.plan_tranches(sw["state"], float(last["Close"]), float(last["atr"]) if not pd.isna(last["atr"]) else None,
                              cap, rp, float(last["vwap20"]) if not pd.isna(last["vwap20"]) else None,
                              float(last["ema50"]) if not pd.isna(last["ema50"]) else None, vp.get("poc"), mw)
        if pl:
            tb = pd.DataFrame(pl["rows"]).rename(columns={"Phan": "Phần", "Khi": "Mua khi", "Gia": "Giá mua (dự kiến)",
                                                           "CatLo": "Cắt lỗ", "KL": "Khối lượng", "RuiRo": "Mất nếu sai (đ)",
                                                           "TrangThai": "Trạng thái"})
            st.dataframe(tb.style.format({"Giá mua (dự kiến)": "{:,.0f}", "Cắt lỗ": "{:,.0f}", "Khối lượng": "{:,}",
                                          "Mất nếu sai (đ)": "{:,.0f}"}), use_container_width=True, hide_index=True)
            st.markdown(f"**Mục tiêu:** TP1 {pl['tp1']:,.0f} · TP2 {pl['tp2']:,.0f} (VWAP20 / EMA50 / POC phía trên — nơi người kẹt hàng chờ bán) · "
                        f"**R:R ước tính** ≈ 1 : {pl['rr']:.1f} · **Ngân sách rủi ro** {pl['budget']:,.0f} đ")
            st.caption("Quy tắc: (1) chỉ mua phần kế tiếp khi bước trước đã xác nhận; (2) đóng cửa thủng đáy test kèm vol "
                       "→ bán HẾT, không bình quân giá; (3) 15 phiên chưa tới TP1 → thoát, đây là lệnh lướt hồi chứ không phải đầu tư; "
                       "(4) hàng về sau T+2.5 — mã yếu hay bị đạp đúng phiên hàng về; (5) mã nền tảng xấu: chốt phần lớn ở TP1.")

    with st.expander(f"📜 Các tín hiệu này từng hiệu quả trên {sym} không?"):
        st.caption("Đo lại trên lịch sử chính mã này: mua giá mở cửa phiên sau tín hiệu, xem lãi/lỗ sau 5/10/20 phiên (đã trừ phí 0.4%). "
                   "Bấm nút để tải 4 năm dữ liệu — mẫu ít (<5 lần) thì chỉ để tham khảo.")
        if st.button("🔬 Kiểm chứng trên 4 năm lịch sử", key="sw_hist_btn"):
            long_px = _hist(sym, 1460)
            if long_px is None or len(long_px) < 200:
                st.info("Không đủ dữ liệu lịch sử dài.")
            else:
                lr = fl.analyze_flow(long_px)
                lsw = ss.analyze_swing(lr["d"])
                st.session_state["sw_hist"] = (sym, lsw.get("history") if lsw else None, len(long_px))
        hh = st.session_state.get("sw_hist")
        if hh and hh[0] == sym and hh[1]:
            st.caption(f"{hh[2]} phiên dữ liệu.")
            names = {"test": "🧪 Sau phiên TEST CUNG", "sos": "⭐ Sau phiên CẦU VÀO", "pump": "🎭 Sau CẢNH BÁO BƠM (≥4 cờ)"}
            cols = st.columns(3)
            for col, key in zip(cols, ("test", "sos", "pump")):
                s_ = hh[1][key]["stats"]
                if not s_.get("n"):
                    col.markdown(_kpi(names[key], "Chưa từng xuất hiện", ""), unsafe_allow_html=True)
                    continue
                good = (s_["avg"] > 0) if key != "pump" else (s_["avg"] < 0)
                col.markdown(_kpi(names[key], f"{s_['n']} lần · TB 10 phiên {s_['avg']:+.1f}%",
                                  f"Thắng {s_['win']:.0f}% · trung vị {s_['med']:+.1f}% · sụt sâu TB {s_['mae']:.1f}%",
                                  GREEN if good else RED), unsafe_allow_html=True)
            for key in ("test", "sos", "pump"):
                tb = hh[1][key]["table"]
                if not tb.empty:
                    st.markdown(f"**{names[key]}**")
                    tb = tb.copy(); tb["Ngày"] = pd.to_datetime(tb["Ngày"]).dt.strftime("%d/%m/%Y")
                    st.dataframe(tb.style.format({"Giá vào": "{:,.0f}", "5p": "{:+.1f}%", "10p": "{:+.1f}%", "20p": "{:+.1f}%",
                                                  "Sụt sâu nhất 10p": "{:+.1f}%"}, na_rep="—"),
                                 use_container_width=True, hide_index=True)
            st.caption("Với cảnh báo bơm, kết quả ÂM nghĩa là cảnh báo đúng (giá giảm sau đó).")


def _render_swing_scanner():
    st.markdown("---")
    st.markdown("#### 🔎 Quét nhóm mã: ai đang xả cạn, ai đang bị bơm rỗng")
    c = st.columns([2, 1, 1])
    grp = c[0].selectbox("Nhóm mã", ["VN30", "VN100", "HOSE", "HNX", "UPCOM"], index=1, key="sw_grp",
                         help="HOSE/HNX/UPCOM: lấy 120 mã có giá trị giao dịch hôm nay lớn nhất")
    min_val = c[1].number_input("GTGD TB20 tối thiểu (tỷ)", 0.0, 500.0, 1.0, 1.0, key="sw_minval")
    go_ = c[2].button("🔎 Quét", key="sw_scan_btn", use_container_width=True)
    if go_:
        with st.spinner("Đang tải và phân tích từng mã (1–2 phút)..."):
            st.session_state["sw_scan"] = (grp, _scan_swing(grp))
    sc = st.session_state.get("sw_scan")
    if not sc:
        st.caption("Chọn nhóm và bấm Quét. Kết quả lưu 15 phút.")
        return
    g, df = sc
    if df is None or df.empty:
        st.info("Không quét được mã nào (nguồn dữ liệu lỗi).")
        return
    df = df[df["GTGD TB20 (tỷ)"] >= min_val]
    st.caption(f"Nhóm {g}: {len(df)} mã đạt thanh khoản ≥ {min_val:.0f} tỷ/phiên.")
    fmt = {"Giá": "{:,.0f}", "% 5 phiên": "{:+.1f}%", "GTGD TB20 (tỷ)": "{:,.1f}"}
    cand = df[df["Giai đoạn"] >= 2].sort_values(["Giai đoạn", "Điểm xả cạn (0–5)"], ascending=False)
    watch = df[df["Giai đoạn"] == 1].sort_values("Điểm xả cạn (0–5)", ascending=False)
    pump = df[df["Cảnh báo bơm"] >= 2].sort_values(["Cảnh báo bơm", "Số cờ bơm"], ascending=False)
    st.markdown(f"**🟢 Ứng viên bắt dần (đã test cung / cầu vào / giữ nhịp): {len(cand)} mã**")
    if cand.empty:
        st.caption("Không có mã nào.")
    else:
        st.dataframe(cand.style.format(fmt), use_container_width=True, hide_index=True)
    st.markdown(f"**🔵 Đang xả cạn — theo dõi, chưa mua: {len(watch)} mã**")
    if not watch.empty:
        st.dataframe(watch.style.format(fmt), use_container_width=True, hide_index=True)
    st.markdown(f"**🔴 Tăng nóng nhưng cầu yếu/rỗng — không mua đuổi: {len(pump)} mã**")
    if not pump.empty:
        st.dataframe(pump.style.format(fmt), use_container_width=True, hide_index=True)
    st.caption("Bấm vào mã ở sidebar để xem chi tiết. Cột 'Cảnh báo bơm': 2 = cầu yếu, 3 = bơm thiếu cầu thật. "
               "Quét chỉ dùng dữ liệu giá/khối lượng; dữ liệu khối ngoại, tự doanh, trong phiên chỉ có khi xem từng mã.")


# ═════════════════════════════ TAB 🇻🇳 THỊ TRƯỜNG VN ══════════════════════════
def render_market(symbol: str, chart_style: dict):
    sym = symbol.upper()
    with st.spinner("Đang tải bảng giá toàn sàn, khối ngoại, tự doanh, ngành..."):
        hose = _group("HOSE"); vn30 = _group("VN30")
        bd = _board(tuple(hose)) if hose else pd.DataFrame()
        mf = _foreign("VNINDEX", 3); mp = _prop("VNINDEX"); secs = _sectors()
    b = vm.breadth(bd)
    st.markdown("### 🇻🇳 Bức tranh thị trường hôm nay (HOSE)")
    if b:
        k = st.columns(6)
        k[0].markdown(_kpi("Tăng / Giảm / Đứng", f"{b['up']} / {b['down']} / {b['flat']}",
                           f"Tỷ lệ A/D {b['ad_ratio']:.2f}" if b["ad_ratio"] else "", GREEN if b["up"] > b["down"] else RED), unsafe_allow_html=True)
        k[1].markdown(_kpi("Trần / Sàn", f"{b['ceil']} / {b['floor']}", "Nhiều mã trần = hưng phấn; nhiều sàn = hoảng loạn"), unsafe_allow_html=True)
        k[2].markdown(_kpi("Giá trị khớp lệnh", f"{b['value_bn']:,.0f} tỷ", f"Thoả thuận {b['pt_bn']:,.0f} tỷ"), unsafe_allow_html=True)
        k[3].markdown(_kpi("Khối ngoại ròng", f"{b['foreign_net_bn']:+,.0f} tỷ", "Ước tính từ bảng giá", GREEN if b["foreign_net_bn"] >= 0 else RED),
                      unsafe_allow_html=True)
        if vn30 and not bd.empty:
            v30 = bd[bd["symbol"].isin(vn30)]
            up30 = int((v30["price"] > v30["ref"]).sum())
            k[4].markdown(_kpi("VN30 tăng", f"{up30}/{len(v30)}", "Độ lan toả của nhóm trụ"), unsafe_allow_html=True)
        exp = vm.derivatives_expiry()
        dleft = len(pd.bdate_range(date.today(), exp)) - 1
        k[5].markdown(_kpi("Đáo hạn phái sinh", f"{exp:%d/%m}", f"còn {dleft} phiên — biến động mạnh trước ATC"), unsafe_allow_html=True)
        # Trạng thái thị trường
        msgs = []
        if b["ad_ratio"] and b["ad_ratio"] >= 1.5: msgs.append((+1, "Độ rộng tốt: số mã tăng gấp ≥1.5 lần mã giảm."))
        if b["ad_ratio"] and b["ad_ratio"] <= 0.67: msgs.append((-1, "Độ rộng xấu: số mã giảm áp đảo."))
        if b["floor"] >= 15: msgs.append((-1, f"{b['floor']} mã giảm sàn — tâm lý hoảng loạn, ưu tiên quản trị rủi ro."))
        if b["ceil"] >= 15: msgs.append((+1, f"{b['ceil']} mã tăng trần — dòng tiền đầu cơ hưng phấn."))
        if mf is not None and not mf.empty:
            n10 = mf["net_val"].tail(10).sum() / 1e9
            msgs.append((1 if n10 > 0 else -1, f"Khối ngoại {'mua' if n10 > 0 else 'bán'} ròng {abs(n10):,.0f} tỷ trên HOSE 10 phiên gần nhất."))
        for m in msgs:
            st.markdown(_signal_html(m[0], m[1], ""), unsafe_allow_html=True)
    else:
        st.info("Không lấy được bảng giá toàn sàn.")

    c1, c2 = st.columns(2)
    with c1:
        if mf is not None and not mf.empty:
            f = make_subplots(specs=[[{"secondary_y": True}]])
            f.add_trace(go.Bar(x=mf["Date"], y=mf["net_val"] / 1e9, name="Ròng (tỷ)",
                               marker_color=[GREEN if v >= 0 else RED for v in mf["net_val"]]), secondary_y=False)
            f.add_trace(go.Scatter(x=mf["Date"], y=mf["net_val"].cumsum() / 1e9, name="Luỹ kế", line=dict(color=YELLOW, width=2)), secondary_y=True)
            st.plotly_chart(_style(f, chart_style, 300, "Khối ngoại toàn HOSE (tỷ đồng)"), use_container_width=True)
    with c2:
        if mp is not None and not mp.empty:
            p = mp.tail(90)
            f = make_subplots(specs=[[{"secondary_y": True}]])
            f.add_trace(go.Bar(x=p["Date"], y=p["net_val"] / 1e9, name="Ròng (tỷ)",
                               marker_color=[GREEN if v >= 0 else RED for v in p["net_val"]]), secondary_y=False)
            f.add_trace(go.Scatter(x=p["Date"], y=p["net_val"].cumsum() / 1e9, name="Luỹ kế", line=dict(color=YELLOW, width=2)), secondary_y=True)
            st.plotly_chart(_style(f, chart_style, 300, "Tự doanh toàn thị trường 90 phiên (tỷ đồng)"), use_container_width=True)

    if not bd.empty:
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("##### 🌏 Khối ngoại hôm nay — mua ròng mạnh nhất")
            tb = bd.nlargest(8, "f_net_val")[["symbol", "price", "chg_pct", "f_net_val"]]
            tb["f_net_val"] = (tb["f_net_val"] / 1e9).round(1)
            st.dataframe(tb.rename(columns={"symbol": "Mã", "price": "Giá", "chg_pct": "%", "f_net_val": "Ròng (tỷ)"}).round(2),
                         use_container_width=True, hide_index=True)
        with c4:
            st.markdown("##### 🌏 Khối ngoại hôm nay — bán ròng mạnh nhất")
            tb = bd.nsmallest(8, "f_net_val")[["symbol", "price", "chg_pct", "f_net_val"]]
            tb["f_net_val"] = (tb["f_net_val"] / 1e9).round(1)
            st.dataframe(tb.rename(columns={"symbol": "Mã", "price": "Giá", "chg_pct": "%", "f_net_val": "Ròng (tỷ)"}).round(2),
                         use_container_width=True, hide_index=True)
        st.markdown("##### 💰 Dòng tiền tập trung — 10 mã giá trị giao dịch lớn nhất")
        tv = bd.nlargest(10, "value")[["symbol", "price", "chg_pct", "value"]]
        tv["value"] = (tv["value"] / 1e9).round(0)
        tv["% thanh khoản sàn"] = (tv["value"] / b["value_bn"] * 100).round(1) if b else None
        st.dataframe(tv.rename(columns={"symbol": "Mã", "price": "Giá", "chg_pct": "%", "value": "Giá trị (tỷ)"}).round(2),
                     use_container_width=True, hide_index=True)

    if secs is not None and not secs.empty:
        s = secs.sort_values("change")
        f = go.Figure(go.Bar(x=s["change"], y=s["name"], orientation="h",
                             marker_color=[GREEN if v >= 0 else RED for v in s["change"]]))
        st.plotly_chart(_style(f, chart_style, 560, "Biến động theo ngành hôm nay (%) — dòng tiền đang luân chuyển vào đâu"),
                        use_container_width=True)

    # ── So sánh định giá cùng ngành ──────────────────────────────────────
    st.markdown(f"### 🏭 {sym} so với các mã cùng ngành")
    smap = _sector_map()
    sec = smap.get(sym)
    if not sec:                      # mã chưa có trong bản đồ ngành KBS (thường là UPCOM) → dùng ICB của Vietcap
        smap = _icb_map()
        sec = smap.get(sym)
    if not sec:
        st.info("Không xác định được ngành của mã này.")
        return
    peers = [s for s, v in smap.items() if v[0] == sec[0]]
    pb = _board(tuple(peers)) if peers else pd.DataFrame()
    if not pb.empty:
        top = list(pb.nlargest(9, "value")["symbol"])
        if sym not in top:
            top = [sym] + top[:8]
        pm = _peers(tuple(top))
        if not pm.empty:
            pm["roe"] = pm["roe"] * 100
            med = pm[pm["symbol"] != sym][["pe", "pb", "roe"]].median(numeric_only=True)
            me = pm[pm["symbol"] == sym]
            st.caption(f"Ngành: **{sec[1]}** · {len(peers)} mã · so sánh với {len(pm)-1} mã thanh khoản cao nhất")
            if not me.empty:
                m = me.iloc[0]
                k = st.columns(3)
                for col, key, lab, fmt_ in [(k[0], "pe", "P/E", "{:.1f}x"), (k[1], "pb", "P/B", "{:.2f}x"), (k[2], "roe", "ROE", "{:.1f}%")]:
                    mv, pv = m[key], med.get(key)
                    if pd.notna(mv) and pd.notna(pv) and pv:
                        diff = (mv / pv - 1) * 100
                        good = diff < 0 if key in ("pe", "pb") else diff > 0
                        col.markdown(_kpi(f"{lab} {sym} vs trung vị ngành", f"{fmt_.format(mv)} vs {fmt_.format(pv)}",
                                          f"{diff:+.0f}% so với ngành", GREEN if good else YELLOW), unsafe_allow_html=True)
            tbl = pm.rename(columns={"symbol": "Mã", "pe": "P/E", "pb": "P/B", "roe": "ROE %", "mcap_bn": "Vốn hoá (tỷ)", "period": "Kỳ"})
            st.dataframe(tbl.round(2), use_container_width=True, hide_index=True)
            f = go.Figure()
            for r in pm.itertuples():
                if pd.notna(r.pb) and pd.notna(r.roe):
                    f.add_trace(go.Scatter(x=[r.roe], y=[r.pb], mode="markers+text", text=[r.symbol], textposition="top center",
                                           marker=dict(size=14 if r.symbol == sym else 9, color=YELLOW if r.symbol == sym else BLUE),
                                           showlegend=False))
            f.update_xaxes(title="ROE %"); f.update_yaxes(title="P/B")
            st.plotly_chart(_style(f, chart_style, 360, "P/B theo ROE — mã nằm DƯỚI đám đông (ROE cao, P/B thấp) là đang rẻ tương đối"),
                            use_container_width=True)


# ═════════════════════════════ TAB 📒 NHẬT KÝ LỆNH ════════════════════════════
def _store():
    try:
        sec = st.secrets
        tok, repo = sec.get("GITHUB_TOKEN"), sec.get("JOURNAL_REPO")
        if tok and repo:
            return jr.GitHubStore(tok, repo, sec.get("JOURNAL_PATH", "journal.json"))
    except Exception:  # noqa: BLE001
        pass
    return jr.FileStore()


def _pin():
    try:
        return st.secrets.get("JOURNAL_PIN")
    except Exception:  # noqa: BLE001
        return None


def _save(store, trades, msg):
    st.session_state["jr_trades"] = trades
    if st.session_state.get("jr_mode") == "session":
        return True
    try:
        store.save(trades, msg)
        return True
    except Exception as e:  # noqa: BLE001
        st.error(f"Không lưu được vào {store.label}: {type(e).__name__}: {e}. Dữ liệu vẫn còn trong phiên — hãy tải bản sao lưu.")
        return False


def render_journal(chart_style: dict):
    st.markdown("### 📒 Nhật ký lệnh")
    pin = _pin(); store = _store()
    if "jr_trades" not in st.session_state:
        if pin:
            p = st.text_input("Nhập mã PIN để mở nhật ký", type="password", key="jr_pin")
            if p != pin:
                st.info("Nhật ký được bảo vệ bằng PIN vì app đang công khai trên Internet.")
                return
            try:
                st.session_state["jr_trades"] = store.load(); st.session_state["jr_mode"] = "store"
            except Exception as e:  # noqa: BLE001
                st.error(f"Không đọc được nhật ký từ {store.label}: {e}")
                st.session_state["jr_trades"] = []; st.session_state["jr_mode"] = "session"
        else:
            st.session_state["jr_trades"] = []; st.session_state["jr_mode"] = "session"
    trades = st.session_state["jr_trades"]
    mode = st.session_state.get("jr_mode")
    if mode == "session":
        st.warning("**Chế độ tạm thời:** nhật ký chỉ sống trong phiên trình duyệt này. Tải bản sao lưu (cuối trang) sau mỗi lần "
                   "ghi, lần sau khôi phục lại. Để lưu VĨNH VIỄN và riêng tư, xem mục **⚙️ Cài đặt lưu trữ**.")
    else:
        st.caption(f"💾 Lưu tại: {store.label}")

    # ── Vị thế đang mở + cảnh báo ─────────────────────────────────────────
    opens = [t for t in trades if t.get("status") == "OPEN"]
    syms = tuple(sorted({t["symbol"] for t in opens}))
    prices, atr, hi22 = {}, {}, {}
    if syms:
        bd = _board(syms)
        if not bd.empty:
            prices = dict(zip(bd["symbol"], bd["price"]))
        for s in syms:
            h = _hist(s, 90)
            if h is not None and len(h) > 22:
                tr = pd.concat([h["High"] - h["Low"], (h["High"] - h["Close"].shift()).abs(), (h["Low"] - h["Close"].shift()).abs()], axis=1).max(axis=1)
                atr[s] = float(tr.tail(14).mean()); hi22[s] = float(h["High"].tail(22).max())
                prices.setdefault(s, float(h["Close"].iloc[-1]))
    stt = jr.stats(trades)
    op = jr.open_positions(trades, prices, atr, hi22, avg_win_days=stt.get("hold_win") if stt else None)
    if not op.empty:
        n_alert = int(op["_alert"].sum())
        tot = op["Lãi/lỗ (đ, sau phí)"].sum(skipna=True)
        k = st.columns(4)
        k[0].markdown(_kpi("Vị thế đang mở", f"{len(op)}", ", ".join(syms)), unsafe_allow_html=True)
        k[1].markdown(_kpi("Lãi/lỗ tạm tính", f"{tot:+,.0f} đ", "Sau phí & thuế bán", GREEN if tot >= 0 else RED), unsafe_allow_html=True)
        k[2].markdown(_kpi("Giá trị danh mục", f"{(op['Giá hiện tại'] * op['KL']).sum():,.0f} đ"), unsafe_allow_html=True)
        k[3].markdown(_kpi("Cần xử lý", f"{n_alert}", "lệnh có cảnh báo", RED if n_alert else GREEN), unsafe_allow_html=True)
        for _, r in op[op["_alert"]].iterrows():
            px_txt = f"giá {r['Giá hiện tại']:,.0f} · {r['Lãi/lỗ %']:+.1f}%" if pd.notna(r["Giá hiện tại"]) else "chưa có giá"
            st.error(f"**{r['Mã']}** · {px_txt} · {r['Cảnh báo']}")
        disp = op.drop(columns=["id", "_alert"]).copy()
        st.dataframe(disp.style.format({"Giá vốn": "{:,.0f}", "Giá hiện tại": "{:,.0f}", "Lãi/lỗ %": "{:+.2f}%",
                                        "Lãi/lỗ (đ, sau phí)": "{:+,.0f}", "R": "{:+.2f}", "Cắt lỗ": "{:,.0f}",
                                        "Mục tiêu": "{:,.0f}", "KL": "{:,}"}, na_rep="—"),
                     use_container_width=True, hide_index=True)
        with st.expander("✏️ Đóng lệnh / dời cắt lỗ"):
            labels = {f"{t['symbol']} · {t['open_date']} · {t['qty']:,} CP @ {t['entry']:,.0f}": t["id"] for t in opens}
            pick = st.selectbox("Chọn lệnh", list(labels.keys()), key="jr_pick")
            tid = labels[pick]; tr_ = next(t for t in trades if t["id"] == tid)
            a, b_ = st.columns(2)
            with a:
                st.markdown("**Đóng lệnh**")
                xp = st.number_input("Giá bán", min_value=0.0, value=float(prices.get(tr_["symbol"], tr_["entry"])), step=50.0, key="jr_xp")
                xd = st.date_input("Ngày bán", value=date.today(), key="jr_xd")
                xr = st.selectbox("Lý do thoát", jr.EXIT_REASONS, key="jr_xr")
                if st.button("✅ Đóng lệnh", key="jr_close"):
                    tr_.update(status="CLOSED", exit=float(xp), close_date=str(xd), exit_reason=xr,
                               updated_at=pd.Timestamp.now().isoformat(timespec="seconds"))
                    if _save(store, trades, f"Đóng {tr_['symbol']}"):
                        st.success("Đã đóng lệnh."); st.rerun()
            with b_:
                st.markdown("**Dời cắt lỗ**")
                ns = st.number_input("Cắt lỗ mới", min_value=0.0, value=float(tr_.get("stop") or 0), step=50.0, key="jr_ns")
                if ns and tr_.get("stop") and ns < tr_["stop"]:
                    st.warning("Dời cắt lỗ XUỐNG là nới rủi ro — chỉ làm khi có lý do mới, không phải vì không muốn chịu lỗ.")
                if st.button("💾 Cập nhật cắt lỗ", key="jr_upd"):
                    tr_["stop"] = float(ns) if ns else None
                    if not tr_.get("initial_stop"):
                        tr_["initial_stop"] = tr_["stop"]
                    if _save(store, trades, f"Dời SL {tr_['symbol']}"):
                        st.success("Đã cập nhật."); st.rerun()
    else:
        st.info("Chưa có vị thế đang mở.")

    # ── Ghi lệnh mới + tính khối lượng theo rủi ro ───────────────────────
    with st.expander("➕ Ghi lệnh mua mới (kèm tính khối lượng theo rủi ro)", expanded=not trades):
        c = st.columns(4)
        sym = c[0].text_input("Mã", key="jr_sym").upper().strip()
        en = c[1].number_input("Giá mua", min_value=0.0, step=50.0, key="jr_en")
        sl = c[2].number_input("Cắt lỗ (bắt buộc)", min_value=0.0, step=50.0, key="jr_sl")
        tg = c[3].number_input("Mục tiêu", min_value=0.0, step=50.0, key="jr_tg")
        c2_ = st.columns(4)
        cap = c2_[0].number_input("Vốn (đ)", min_value=0.0, value=float(st.session_state.get("jr_cap", 100_000_000)), step=1e6, key="jr_cap")
        rp = c2_[1].number_input("Rủi ro tối đa/lệnh (% vốn)", 0.1, 5.0, 1.0, 0.1, key="jr_rp")
        ps = jr.position_size(cap, rp, en, sl) if en and sl else None
        if ps:
            c2_[2].markdown(_kpi("KL gợi ý", f"{ps['qty']:,} CP", f"{ps['value']:,.0f} đ · {ps['weight']:.0f}% vốn"), unsafe_allow_html=True)
            c2_[3].markdown(_kpi("Mất nếu chạm SL", f"{ps['risk']:,.0f} đ", f"{ps['risk_pct_real']:.2f}% vốn", YELLOW), unsafe_allow_html=True)
        c3_ = st.columns(4)
        qty = c3_[0].number_input("Khối lượng mua", min_value=0, step=100, value=int(ps["qty"]) if ps else 0, key="jr_qty")
        od_ = c3_[1].date_input("Ngày mua", value=date.today(), key="jr_od")
        setup = c3_[2].selectbox("Chiến lược", jr.SETUPS, key="jr_setup")
        reason = c3_[3].text_input("Lý do vào lệnh (1 câu)", key="jr_reason")
        if en and sl and sl >= en:
            st.error("Cắt lỗ phải THẤP hơn giá mua.")
        if en and tg and sl and tg > en > sl:
            st.caption(f"R:R kế hoạch = 1 : {(tg - en) / (en - sl):.1f}" + (" — dưới 1:2, cân nhắc lại." if (tg - en) / (en - sl) < 2 else ""))
        if st.button("💾 Ghi lệnh", key="jr_add"):
            if not sym or not en or not qty or not sl or sl >= en:
                st.error("Cần đủ: mã, giá mua, khối lượng và cắt lỗ thấp hơn giá mua. Không có cắt lỗ thì không có kế hoạch.")
            else:
                trades.append(jr.new_trade(sym, od_, en, qty, sl, tg or None, setup, reason))
                if _save(store, trades, f"Mua {sym}"):
                    st.success(f"Đã ghi lệnh mua {sym}."); st.rerun()

    # ── Thống kê kỷ luật ─────────────────────────────────────────────────
    st.markdown("### 📈 Hiệu quả & kỷ luật giao dịch")
    if not stt:
        st.info("Chưa có lệnh đã đóng để thống kê.")
    else:
        k = st.columns(6)
        k[0].markdown(_kpi("Số lệnh / Tỷ lệ thắng", f"{stt['n']} / {stt['win_rate']:.0f}%"), unsafe_allow_html=True)
        k[1].markdown(_kpi("Lãi TB / Lỗ TB", f"{stt['avg_win']:+.1f}% / -{stt['avg_loss']:.1f}%",
                           f"Payoff {stt['payoff']:.2f}" if stt["payoff"] else ""), unsafe_allow_html=True)
        k[2].markdown(_kpi("Profit factor", f"{stt['profit_factor']:.2f}" if stt["profit_factor"] else "—", ">1.5 là tốt",
                           GREEN if (stt["profit_factor"] or 0) >= 1.5 else YELLOW), unsafe_allow_html=True)
        k[3].markdown(_kpi("Kỳ vọng/lệnh", f"{stt['expectancy_pct']:+.2f}%",
                           f"{stt['expectancy_r']:+.2f}R" if stt["expectancy_r"] is not None else "",
                           GREEN if stt["expectancy_pct"] > 0 else RED), unsafe_allow_html=True)
        k[4].markdown(_kpi("Giữ lệnh lãi / lỗ", f"{stt['hold_win'] or 0:.0f} / {stt['hold_loss'] or 0:.0f} phiên",
                           "Lỗ giữ lâu hơn lãi = gồng lỗ", RED if (stt["hold_loss"] or 0) > (stt["hold_win"] or 0) * 1.3 else GREEN),
                      unsafe_allow_html=True)
        k[5].markdown(_kpi("Tổng lãi/lỗ", f"{stt['total_pnl']:+,.0f} đ", f"Sụt giảm tối đa {stt['max_dd']:,.0f} đ · chuỗi thua {stt['max_loss_streak']}",
                           GREEN if stt["total_pnl"] >= 0 else RED), unsafe_allow_html=True)
        for kind, txt in stt["insights"]:
            (st.error if kind == "bad" else st.success if kind == "good" else st.info)(txt)
        f = go.Figure(go.Scatter(x=list(range(1, len(stt["equity"]) + 1)), y=stt["equity"], mode="lines+markers",
                                 line=dict(color=GREEN, width=2)))
        f.update_xaxes(title="Lệnh thứ"); f.update_yaxes(title="Lãi/lỗ luỹ kế (đ)")
        st.plotly_chart(_style(f, chart_style, 280, "Đường vốn theo lệnh đã đóng"), use_container_width=True)
        st.markdown("##### Theo chiến lược")
        st.dataframe(stt["by_setup"].round(2), use_container_width=True, hide_index=True)
        with st.expander("📜 Lịch sử lệnh đã đóng"):
            st.dataframe(stt["df"].drop(columns=["id"]).round(2), use_container_width=True, hide_index=True)

    # ── Sao lưu / khôi phục / cài đặt ────────────────────────────────────
    st.markdown("### 💾 Sao lưu & khôi phục")
    c = st.columns(3)
    c[0].download_button("⬇️ Tải bản sao lưu (JSON)", json.dumps(trades, ensure_ascii=False, indent=1).encode("utf-8"),
                         file_name=f"nhat_ky_lenh_{date.today():%Y%m%d}.json", mime="application/json", key="jr_dl")
    c[1].download_button("⬇️ Xuất Excel/CSV", jr.to_csv(trades), file_name=f"nhat_ky_lenh_{date.today():%Y%m%d}.csv",
                         mime="text/csv", key="jr_dlc")
    up = c[2].file_uploader("Khôi phục từ file JSON", type=["json"], key="jr_up")
    if up is not None and st.button("♻️ Khôi phục (ghi đè nhật ký hiện tại)", key="jr_restore"):
        try:
            data = json.loads(up.getvalue().decode("utf-8"))
            assert isinstance(data, list)
            if _save(store, data, "Khôi phục nhật ký"):
                st.success(f"Đã khôi phục {len(data)} lệnh."); st.rerun()
        except Exception as e:  # noqa: BLE001
            st.error(f"File không hợp lệ: {e}")
    with st.expander("⚙️ Cài đặt lưu trữ vĩnh viễn & riêng tư (làm 1 lần, ~5 phút)"):
        st.markdown(
            "App đang công khai — ai có link cũng mở được. Để nhật ký **riêng tư và không mất**:\n\n"
            "1. Trên GitHub tạo repo **Private** mới, ví dụ **trading-journal**.\n"
            "2. GitHub → Settings → Developer settings → **Fine-grained tokens** → Generate: chỉ chọn repo **trading-journal**, "
            "quyền **Contents: Read and write**. Sao chép token.\n"
            "3. share.streamlit.io → app → **Settings → Secrets**, dán:")
        st.code('GITHUB_TOKEN = "github_pat_..."\nJOURNAL_REPO = "dangdnh1411/trading-journal"\nJOURNAL_PIN = "dat-ma-PIN-rieng"',
                language="toml")
        st.markdown("4. Lưu → app tự khởi động lại. Từ đó nhật ký lưu vào repo riêng tư, mở bằng PIN.")
