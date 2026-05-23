import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time

st.set_page_config(layout="wide", page_title="VN Stock Analyzer Pro", page_icon="📈")

# ── CSS tối màu terminal ──────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background: #0b1929; }
[data-testid="stHeader"] { background: #0b1929; }
[data-testid="stSidebar"] { background: #0f2236; }
[data-testid="stSidebar"] * { color: #dbeafe !important; }
div[data-testid="metric-container"] {
    background: #0f2236; border: 1px solid #1c3a5c;
    border-radius: 8px; padding: 12px 16px;
}
div[data-testid="metric-container"] label { color: #7dafd8 !important; }
div[data-testid="metric-container"] div { color: #dbeafe !important; }
.signal-box {
    padding: 16px 20px; border-radius: 10px;
    border: 1px solid #1c3a5c; background: #0f2236;
    margin-bottom: 12px;
}
.trade-card {
    border-radius: 8px; padding: 12px 14px; margin-bottom: 8px;
}
.stAlert { background: #0f2236 !important; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 1. DATA FETCHER
# ══════════════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=60)
def fetch_data(symbol: str, days: int = 180, interval: str = "1D") -> pd.DataFrame:
    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        from vnstock import Vnstock
        df = Vnstock().stock(symbol=symbol, source="TCBS").quote.history(
            start=start, end=end, interval=interval
        )
        df = df.reset_index()
        # chuẩn hoá tên cột
        col_map = {"time":"Date","open":"Open","high":"High",
                   "low":"Low","close":"Close","volume":"Volume"}
        df.rename(columns={k:v for k,v in col_map.items() if k in df.columns}, inplace=True)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").reset_index(drop=True)
        return df
    except Exception as e:
        st.error(f"Lỗi lấy dữ liệu {symbol}: {e}")
        return pd.DataFrame()

# ══════════════════════════════════════════════════════════════════════════════
# 2. INDICATORS
# ══════════════════════════════════════════════════════════════════════════════
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    c = df["Close"]
    # Moving Averages
    for n in [5, 10, 20, 50, 200]:
        df[f"MA{n}"] = c.rolling(n).mean()
    # MACD
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    df["MACD"]        = ema12 - ema26
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"]   = df["MACD"] - df["MACD_Signal"]
    # RSI
    delta = c.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, np.nan)
    df["RSI"] = 100 - 100 / (1 + rs)
    # ADX
    hi, lo = df["High"], df["Low"]
    tr  = pd.concat([hi-lo, (hi-c.shift()).abs(), (lo-c.shift()).abs()], axis=1).max(axis=1)
    pdm = (hi.diff().clip(lower=0)).where(hi.diff() > lo.diff().abs(), 0)
    ndm = (lo.diff().abs().clip(lower=0)).where(lo.diff().abs() > hi.diff(), 0)
    atr14  = tr.rolling(14).mean()
    pdi    = 100 * pdm.rolling(14).mean() / atr14.replace(0, np.nan)
    ndi    = 100 * ndm.rolling(14).mean() / atr14.replace(0, np.nan)
    dx     = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
    df["ADX"] = dx.rolling(14).mean()
    df["ATR"] = atr14
    # Bollinger Bands
    df["BB_mid"]   = c.rolling(20).mean()
    bb_std         = c.rolling(20).std()
    df["BB_upper"] = df["BB_mid"] + 2*bb_std
    df["BB_lower"] = df["BB_mid"] - 2*bb_std
    df["BB_width"] = (df["BB_upper"] - df["BB_lower"]) / df["BB_mid"]
    # Volume ratio
    df["Vol_MA20"]  = df["Volume"].rolling(20).mean()
    df["Vol_Ratio"] = df["Volume"] / df["Vol_MA20"].replace(0, np.nan)
    return df

def detect_candle_patterns(df: pd.DataFrame) -> pd.DataFrame:
    pats = [None]
    for i in range(1, len(df)):
        p, c2 = df.iloc[i-1], df.iloc[i]
        body   = abs(c2.Close - c2.Open)
        upper  = c2.High - max(c2.Close, c2.Open)
        lower  = min(c2.Close, c2.Open) - c2.Low
        rng    = c2.High - c2.Low
        pat = None
        if body <= rng * 0.1:
            pat = "Doji"
        elif lower > 2*body and upper < body:
            pat = "Hammer"
        elif upper > 2*body and lower < body:
            pat = "Shooting Star"
        elif (p.Close < p.Open and c2.Close > c2.Open
              and c2.Open <= p.Close and c2.Close >= p.Open):
            pat = "Bullish Engulfing"
        elif (p.Close > p.Open and c2.Close < c2.Open
              and c2.Open >= p.Close and c2.Close <= p.Open):
            pat = "Bearish Engulfing"
        pats.append(pat)
    df["Pattern"] = pats
    return df

# ══════════════════════════════════════════════════════════════════════════════
# 3. SIGNAL ENGINE
# ══════════════════════════════════════════════════════════════════════════════
def expert_signal(df: pd.DataFrame):
    lat  = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else lat
    reasons, score = [], 0.0

    if lat.Close > lat.MA50:
        reasons.append("✅ Giá > MA50 — xu hướng tăng trung hạn"); score += 1
    else:
        reasons.append("❌ Giá < MA50 — xu hướng giảm trung hạn"); score -= 1

    if pd.notna(lat.MA200):
        if lat.Close > lat.MA200:
            reasons.append("✅ Giá > MA200 — xu hướng tăng dài hạn"); score += 1
        else:
            reasons.append("❌ Giá < MA200 — xu hướng giảm dài hạn"); score -= 1

    if lat.MA5 > lat.MA10 > lat.MA20:
        reasons.append("✅ MA5>MA10>MA20 — xếp hàng tăng"); score += 1
    elif lat.MA5 < lat.MA10 < lat.MA20:
        reasons.append("❌ MA5<MA10<MA20 — xếp hàng giảm"); score -= 1
    else:
        reasons.append("⚠️ MA không đồng nhất — sideway")

    if lat.MACD > lat.MACD_Signal and prev.MACD <= prev.MACD_Signal:
        reasons.append("🔥 MACD vừa cắt lên Signal — MUA"); score += 2
    elif lat.MACD < lat.MACD_Signal and prev.MACD >= prev.MACD_Signal:
        reasons.append("💧 MACD vừa cắt xuống Signal — BÁN"); score -= 2
    elif lat.MACD > lat.MACD_Signal:
        reasons.append("✅ MACD trên Signal — động lượng tăng"); score += 1
    else:
        reasons.append("❌ MACD dưới Signal — động lượng giảm"); score -= 1

    rsi = lat.RSI
    if rsi > 70:
        reasons.append(f"⚠️ RSI {rsi:.0f} — quá mua"); score -= 1
    elif rsi < 30:
        reasons.append(f"🔥 RSI {rsi:.0f} — quá bán, cơ hội"); score += 1
    elif rsi > 50:
        reasons.append(f"✅ RSI {rsi:.0f} — ủng hộ tăng"); score += 0.5
    else:
        reasons.append(f"❌ RSI {rsi:.0f} — ủng hộ giảm"); score -= 0.5

    adx = lat.ADX
    if pd.notna(adx):
        if adx > 25:
            if lat.MACD > lat.MACD_Signal:
                reasons.append(f"✅ ADX {adx:.0f} — xu hướng tăng mạnh"); score += 1
            else:
                reasons.append(f"❌ ADX {adx:.0f} — xu hướng giảm mạnh"); score -= 1
        else:
            reasons.append(f"⚠️ ADX {adx:.0f} — chưa có xu hướng rõ")

    if lat.Close > lat.BB_upper:
        reasons.append("⚠️ Vượt BB trên — vùng quá mua"); score -= 0.5
    elif lat.Close < lat.BB_lower:
        reasons.append("🔥 Chạm BB dưới — vùng quá bán"); score += 0.5
    if lat.BB_width < 0.05:
        reasons.append("📉 BB bó hẹp — sắp bùng nổ")

    pat = lat.get("Pattern")
    if pat in ("Bullish Engulfing", "Hammer"):
        reasons.append(f"🕯️ Nến {pat} — đảo chiều tăng"); score += 1.5
    elif pat in ("Bearish Engulfing", "Shooting Star"):
        reasons.append(f"🕯️ Nến {pat} — đảo chiều giảm"); score -= 1.5
    elif pat == "Doji":
        reasons.append("🕯️ Nến Doji — lưỡng lự")

    if lat.Vol_Ratio > 1.5:
        reasons.append("📊 Khối lượng đột biến — " + ("xác nhận mua" if score > 0 else "xác nhận bán"))

    if   score >= 5:   sig = "MUA MẠNH"
    elif score >= 1.5: sig = "MUA"
    elif score >= 0.5: sig = "THEO DÕI MUA"
    elif score > -0.5: sig = "TRUNG TÍNH"
    elif score > -1.5: sig = "THEO DÕI BÁN"
    elif score >= -3:  sig = "BÁN"
    else:              sig = "BÁN MẠNH"

    return sig, reasons, score

def calc_trade_levels(df: pd.DataFrame, sig: str, score: float):
    lat = df.iloc[-1]
    c   = lat.Close
    atr = lat.ATR if pd.notna(lat.ATR) else c * 0.02

    hi_period = df["High"].max()
    lo_period = df["Low"].min()
    hi20 = df["High"].tail(20).max()
    lo20 = df["Low"].tail(20).min()
    fib_diff = hi_period - lo_period

    fib = {
        "0%":   lo_period,
        "23.6%": lo_period + fib_diff * 0.236,
        "38.2%": lo_period + fib_diff * 0.382,
        "50%":   lo_period + fib_diff * 0.500,
        "61.8%": lo_period + fib_diff * 0.618,
        "78.6%": lo_period + fib_diff * 0.786,
        "100%":  hi_period,
    }

    is_bull = score >= 0.5
    if is_bull:
        buy    = round(c * 0.99)
        sl     = round(min(c - atr * 1.5, lo20 * 0.995))
        tp_targets = sorted([v for v in fib.values() if v > c])
        tp1 = round(tp_targets[0]) if len(tp_targets) > 0 else round(c * 1.05)
        tp2 = round(tp_targets[1]) if len(tp_targets) > 1 else round(c * 1.10)
        tp3 = round(tp_targets[2]) if len(tp_targets) > 2 else round(c * 1.15)
        sell   = round(hi20)
    else:
        buy    = round(lo20 * 1.005)
        sl     = round(buy * (1 - atr / buy * 1.5))
        fib_r  = sorted([v for v in fib.values() if v > buy])
        tp1 = round(fib_r[0]) if len(fib_r) > 0 else round(buy * 1.05)
        tp2 = round(fib_r[1]) if len(fib_r) > 1 else round(buy * 1.10)
        tp3 = round(fib_r[2]) if len(fib_r) > 2 else round(buy * 1.15)
        sell = round(c)

    risk   = abs(buy - sl) / buy
    reward = (tp2 - buy) / buy
    rr     = reward / risk if risk > 0 else 0

    return dict(buy=buy, sell=sell, sl=sl, tp1=tp1, tp2=tp2, tp3=tp3,
                risk=risk, reward=reward, rr=rr, fib=fib, atr=atr)

# ══════════════════════════════════════════════════════════════════════════════
# 4. CHART
# ══════════════════════════════════════════════════════════════════════════════
def build_chart(df: pd.DataFrame, symbol: str, trade: dict) -> go.Figure:
    show = df.tail(80)
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True,
        vertical_spacing=0.03, row_heights=[0.60, 0.20, 0.20]
    )
    # Nến
    fig.add_trace(go.Candlestick(
        x=show["Date"], open=show["Open"], high=show["High"],
        low=show["Low"], close=show["Close"], name="Giá",
        increasing_fillcolor="#00e07a", increasing_line_color="#00e07a",
        decreasing_fillcolor="#ff3d5a", decreasing_line_color="#ff3d5a",
    ), row=1, col=1)
    # MA
    for ma, color in [("MA20","#4a9ef8"), ("MA50","#f5a623")]:
        fig.add_trace(go.Scatter(x=show["Date"], y=show[ma], name=ma,
            line=dict(color=color, width=1.5), hoverinfo="skip"), row=1, col=1)
    # Bollinger
    fig.add_trace(go.Scatter(x=show["Date"], y=show["BB_upper"], name="BB+",
        line=dict(color="rgba(167,139,250,0.4)", width=1, dash="dot"),
        fill=None, hoverinfo="skip"), row=1, col=1)
    fig.add_trace(go.Scatter(x=show["Date"], y=show["BB_lower"], name="BB−",
        line=dict(color="rgba(167,139,250,0.4)", width=1, dash="dot"),
        fill="tonexty", fillcolor="rgba(167,139,250,0.04)", hoverinfo="skip"), row=1, col=1)
    # Đường BUY / SL / TP
    levels = [
        (trade["buy"],  "BUY",  "#00e07a", "dash"),
        (trade["sl"],   "SL",   "#ff3d5a", "dash"),
        (trade["tp1"],  "TP1",  "#f5a623", "dot"),
        (trade["tp2"],  "TP2",  "#f5a623", "dot"),
        (trade["tp3"],  "TP3",  "#f5a623", "dot"),
    ]
    ymin = show["Low"].min()
    ymax = show["High"].max()
    for price, lbl, color, dash in levels:
        if ymin * 0.9 < price < ymax * 1.1:
            fig.add_hline(y=price, line_color=color, line_dash=dash,
                          line_width=1, annotation_text=f" {lbl} {price:,.0f}",
                          annotation_font_color=color, row=1, col=1)
    # Volume
    colors = ["#00e07a" if r.Close >= r.Open else "#ff3d5a" for _, r in show.iterrows()]
    fig.add_trace(go.Bar(x=show["Date"], y=show["Volume"], name="Vol",
        marker_color=colors, opacity=0.5), row=2, col=1)
    # MACD
    fig.add_trace(go.Scatter(x=show["Date"], y=show["MACD"], name="MACD",
        line=dict(color="#4a9ef8", width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=show["Date"], y=show["MACD_Signal"], name="Signal",
        line=dict(color="#ff3d5a", width=1.2, dash="dot")), row=3, col=1)
    hist_colors = ["#00e07a" if v >= 0 else "#ff3d5a" for v in show["MACD_Hist"].fillna(0)]
    fig.add_trace(go.Bar(x=show["Date"], y=show["MACD_Hist"], name="Hist",
        marker_color=hist_colors, opacity=0.7), row=3, col=1)

    fig.update_layout(
        height=650, template="plotly_dark",
        paper_bgcolor="#0b1929", plot_bgcolor="#0b1929",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02, x=0, font_size=11),
        margin=dict(l=10, r=10, t=10, b=10),
        font=dict(family="monospace", color="#dbeafe"),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#1c3a5c", gridwidth=0.5)
    fig.update_yaxes(showgrid=True, gridcolor="#1c3a5c", gridwidth=0.5)
    return fig

# ══════════════════════════════════════════════════════════════════════════════
# 5. UI
# ══════════════════════════════════════════════════════════════════════════════
SIG_COLOR = {
    "MUA MẠNH":     "#00e07a",
    "MUA":          "#00b862",
    "THEO DÕI MUA": "#65a30d",
    "TRUNG TÍNH":   "#7dafd8",
    "THEO DÕI BÁN": "#f5a623",
    "BÁN":          "#ff3d5a",
    "BÁN MẠNH":     "#cc0033",
}

st.markdown("## 📈 Pro Trader Terminal — VN Stock Analyzer")

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Cấu hình")
    symbol   = st.text_input("Mã cổ phiếu", value="VPB").upper().strip()
    period   = st.selectbox("Khung thời gian dữ liệu",
                            ["3 tháng","6 tháng","1 năm","2 năm"], index=1)
    interval = st.selectbox("Độ phân giải", ["1D","1W"], index=0)
    refresh  = st.slider("Tự động refresh (giây)", 30, 300, 60)
    auto_ref = st.checkbox("Bật tự động refresh", value=True)
    run_btn  = st.button("🔍 Phân tích ngay", use_container_width=True)
    st.markdown("---")
    st.markdown("**Gợi ý mã:**")
    quick = ["VPB","HPG","VCB","FPT","MWG","SSI","TCB","VIC","ACB","STB"]
    cols2 = st.columns(2)
    for i, m in enumerate(quick):
        if cols2[i%2].button(m, key=f"q{m}"):
            symbol = m

period_map = {"3 tháng":90, "6 tháng":180, "1 năm":365, "2 năm":730}
days = period_map[period]

# Main
if run_btn or auto_ref:
    with st.spinner(f"Đang tải {symbol}..."):
        df = fetch_data(symbol, days, interval)

    if df.empty:
        st.error("Không lấy được dữ liệu. Kiểm tra mã cổ phiếu.")
        st.stop()

    df = compute_indicators(df)
    df = detect_candle_patterns(df)
    sig, reasons, score = expert_signal(df)
    trade = calc_trade_levels(df, sig, score)
    lat = df.iloc[-1]
    prev = df.iloc[-2]

    # ── Metrics ──────────────────────────────────────────────────────────────
    chg = lat.Close - prev.Close
    pct = chg / prev.Close * 100
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Giá đóng cửa",
              f"{lat.Close:,.0f} đ",
              f"{'▲' if chg>=0 else '▼'} {abs(chg):,.0f} ({abs(pct):.2f}%)")
    c2.metric("Khối lượng",
              f"{lat.Volume/1e6:.1f}M" if lat.Volume>=1e6 else f"{lat.Volume/1e3:.0f}K",
              f"×{lat.Vol_Ratio:.2f} trung bình")
    c3.metric("ATR (14)", f"{lat.ATR:,.0f} đ", "Biên độ trung bình ngày")
    pat = lat.get("Pattern") or df["Pattern"].dropna().iloc[-1] if df["Pattern"].notna().any() else "—"
    c4.metric("Mô hình nến", pat or "—",
              "↗ Tăng" if pat in ("Bullish Engulfing","Hammer") else
              "↘ Giảm" if pat in ("Bearish Engulfing","Shooting Star") else "")

    # ── Tín hiệu ─────────────────────────────────────────────────────────────
    sig_color = SIG_COLOR.get(sig, "#7dafd8")
    pct_meter = min(100, max(0, (score + 6) / 12 * 100))
    st.markdown(f"""
    <div class="signal-box">
      <div style="display:flex;align-items:center;gap:20px;flex-wrap:wrap;">
        <div>
          <div style="font-size:11px;color:#7dafd8;letter-spacing:2px;">TÍN HIỆU TỔNG HỢP</div>
          <div style="font-size:26px;font-weight:700;color:{sig_color};">{sig}</div>
        </div>
        <div style="text-align:center;">
          <div style="font-size:11px;color:#7dafd8;">ĐIỂM</div>
          <div style="font-size:28px;font-weight:700;color:#f5a623;">{score:.1f}</div>
        </div>
        <div style="flex:1;min-width:200px;">
          <div style="font-size:10px;color:#7dafd8;letter-spacing:1px;margin-bottom:4px;">THƯỚC ĐO XU HƯỚNG</div>
          <div style="height:8px;background:#1c3a5c;border-radius:4px;overflow:hidden;">
            <div style="height:100%;width:{pct_meter}%;background:{sig_color};border-radius:4px;transition:width .5s;"></div>
          </div>
          <div style="display:flex;justify-content:space-between;font-size:9px;color:#3a6080;margin-top:2px;">
            <span style="color:#ff3d5a;">Bán mạnh</span><span>Trung tính</span><span style="color:#00e07a;">Mua mạnh</span>
          </div>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Chiến lược giao dịch ─────────────────────────────────────────────────
    st.markdown("### 🎯 Chiến lược giao dịch")
    t1, t2, t3, t4 = st.columns(4)
    t1.markdown(f"""<div class="trade-card" style="background:rgba(0,224,122,0.08);border:1px solid rgba(0,224,122,0.3);">
        <div style="font-size:10px;color:#00e07a;letter-spacing:1px;">VÙNG MUA</div>
        <div style="font-size:20px;font-weight:700;color:#00e07a;">{trade['buy']:,} đ</div>
        <div style="font-size:11px;color:#7dafd8;">Giá mua vào mục tiêu</div>
    </div>""", unsafe_allow_html=True)
    t2.markdown(f"""<div class="trade-card" style="background:rgba(255,61,90,0.08);border:1px solid rgba(255,61,90,0.3);">
        <div style="font-size:10px;color:#ff3d5a;letter-spacing:1px;">CẮT LỖ (SL)</div>
        <div style="font-size:20px;font-weight:700;color:#ff3d5a;">{trade['sl']:,} đ</div>
        <div style="font-size:11px;color:#7dafd8;">Rủi ro: {trade['risk']*100:.1f}%</div>
    </div>""", unsafe_allow_html=True)
    t3.markdown(f"""<div class="trade-card" style="background:rgba(245,166,35,0.08);border:1px solid rgba(245,166,35,0.3);">
        <div style="font-size:10px;color:#f5a623;letter-spacing:1px;">CHỐT LỜI</div>
        <div style="font-size:14px;font-weight:700;color:#f5a623;">
            TP1: {trade['tp1']:,}<br>TP2: {trade['tp2']:,}<br>TP3: {trade['tp3']:,}
        </div>
    </div>""", unsafe_allow_html=True)
    rr = trade['rr']
    rr_color = "#00e07a" if rr>=2 else "#f5a623" if rr>=1.5 else "#ff3d5a"
    rr_text  = "Tuyệt vời" if rr>=2.5 else "Tốt" if rr>=2 else "Chấp nhận" if rr>=1.5 else "Rủi ro cao"
    t4.markdown(f"""<div class="trade-card" style="background:rgba(75,156,248,0.08);border:1px solid rgba(75,156,248,0.3);">
        <div style="font-size:10px;color:#4a9ef8;letter-spacing:1px;">R:R RATIO</div>
        <div style="font-size:20px;font-weight:700;color:{rr_color};">1 : {rr:.1f}</div>
        <div style="font-size:11px;color:#7dafd8;">{rr_text} · LN kỳ vọng: {trade['reward']*100:.1f}%</div>
    </div>""", unsafe_allow_html=True)

    # ── Fibonacci ─────────────────────────────────────────────────────────────
    with st.expander("📐 Fibonacci Retracement — Vùng hỗ trợ & kháng cự"):
        fib_df = pd.DataFrame([
            {"Mức": k, "Giá (đ)": f"{v:,.0f}",
             "Khoảng cách": f"{(v/lat.Close-1)*100:+.1f}%",
             "Vai trò": "◀ GIÁ HIỆN TẠI" if abs(v/lat.Close-1)<0.02
                        else ("Hỗ trợ" if v < lat.Close else "Kháng cự")}
            for k, v in trade["fib"].items()
        ])
        st.dataframe(fib_df, use_container_width=True, hide_index=True)

    # ── Biểu đồ ──────────────────────────────────────────────────────────────
    fig = build_chart(df, symbol, trade)
    st.plotly_chart(fig, use_container_width=True)

    # ── Chỉ báo + Lý do ──────────────────────────────────────────────────────
    i1, i2 = st.columns([1, 2])
    with i1:
        st.markdown("**Chỉ báo hiện tại**")
        ind_df = pd.DataFrame({
            "Chỉ báo": ["RSI (14)","MACD","ADX (14)","BB Width","Vol Ratio"],
            "Giá trị":  [f"{lat.RSI:.1f}", f"{lat.MACD:.2f}", f"{lat.ADX:.1f}",
                        f"{lat.BB_width*100:.1f}%", f"×{lat.Vol_Ratio:.2f}"],
            "Trạng thái": [
                "Quá mua" if lat.RSI>70 else "Quá bán" if lat.RSI<30 else "Bình thường",
                "Tăng" if lat.MACD>0 else "Giảm",
                "Xu hướng mạnh" if lat.ADX>25 else "Yếu",
                "Bó hẹp" if lat.BB_width<0.05 else "Bình thường",
                "Đột biến" if lat.Vol_Ratio>1.5 else "Bình thường",
            ]
        })
        st.dataframe(ind_df, use_container_width=True, hide_index=True)

    with i2:
        st.markdown("**Phân tích tín hiệu chi tiết**")
        for r in reasons:
            st.write(r)

    st.caption(f"Nguồn: TCBS via vnstock · {symbol} · Cập nhật: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")

    # Auto refresh
    if auto_ref:
        time.sleep(refresh)
        st.rerun()
else:
    st.info("👈 Nhập mã cổ phiếu và nhấn **Phân tích ngay** ở thanh bên trái.")
