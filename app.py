import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import requests, time, json

st.set_page_config(
    layout="wide",
    page_title="VN Stock Analyzer Pro",
    page_icon="📈",
    initial_sidebar_state="expanded"
)

# ── GLOBAL CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Nền tối */
[data-testid="stAppViewContainer"],
[data-testid="stMain"] { background:#081524 !important; }
[data-testid="stHeader"] { background:#081524 !important; }
[data-testid="stSidebar"] { background:#0d1f33 !important; border-right:1px solid #1c3a5c; }

/* Tất cả text sáng rõ */
*, p, span, label, div, li, h1, h2, h3 { color:#e2eeff !important; }
[data-testid="stSidebar"] * { color:#c9deff !important; }

/* Input / select */
input, select, textarea,
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] div {
    background:#0d2035 !important;
    color:#ffffff !important;
    border:1px solid #2a5080 !important;
    border-radius:6px !important;
}

/* Metric cards */
[data-testid="metric-container"] {
    background:#0d2035 !important;
    border:1px solid #1c3a5c !important;
    border-radius:10px !important;
    padding:14px 18px !important;
}
[data-testid="metric-container"] [data-testid="stMetricLabel"] p { color:#7cb8e8 !important; font-size:11px !important; letter-spacing:1px; }
[data-testid="metric-container"] [data-testid="stMetricValue"] { color:#ffffff !important; font-size:22px !important; font-weight:700 !important; }
[data-testid="metric-container"] [data-testid="stMetricDelta"] { color:#00e07a !important; }

/* Buttons */
[data-testid="stButton"] button {
    background:#1a4a7a !important;
    color:#ffffff !important;
    border:1px solid #2a6aaa !important;
    border-radius:8px !important;
    font-weight:600 !important;
}
[data-testid="stButton"] button:hover { background:#2a6aaa !important; }

/* Expander */
[data-testid="stExpander"] {
    background:#0d2035 !important;
    border:1px solid #1c3a5c !important;
    border-radius:8px !important;
}

/* Dataframe */
[data-testid="stDataFrame"] { border:1px solid #1c3a5c !important; border-radius:8px !important; }
iframe { border-radius:8px !important; }

/* Divider */
hr { border-color:#1c3a5c !important; }
.stAlert { background:#0d2035 !important; border:1px solid #1c3a5c !important; }
.stSuccess { border-left:3px solid #00e07a !important; }
.stError   { border-left:3px solid #ff3d5a !important; }
.stInfo    { border-left:3px solid #4a9ef8 !important; }
.stWarning { border-left:3px solid #f5a623 !important; }
</style>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 1. DATA FETCHER — TCBS direct + Yahoo fallback (không cần vnstock)
# ══════════════════════════════════════════════════════════════════════════════
INTERVAL_MAP = {
    "1 phút":  ("1", "m1"),
    "5 phút":  ("5", "m5"),
    "15 phút": ("15", "m15"),
    "1 giờ":   ("60", "h1"),
    "Ngày":    ("D", "D"),
    "Tuần":    ("W", "W"),
    "Tháng":   ("M", "M"),
}

@st.cache_data(ttl=60, show_spinner=False)
def fetch_tcbs(symbol: str, days: int, resolution: str = "D") -> pd.DataFrame:
    """TCBS public API — gọi thẳng không cần vnstock"""
    now = int(time.time())
    frm = now - days * 86400

    # Intraday dùng endpoint khác
    if resolution in ("m1","m5","m15","h1"):
        url = "https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars"
        params = {"ticker": symbol, "type": resolution,
                  "resolution": resolution, "from": frm, "to": now, "pageSize": 500}
    else:
        url = "https://apipubaws.tcbs.com.vn/stock-insight/v1/stock/bars-long-term"
        params = {"ticker": symbol, "type": resolution,
                  "resolution": resolution, "from": frm, "to": now}

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://tcinvest.tcbs.com.vn/",
        "Origin":  "https://tcinvest.tcbs.com.vn",
    }
    r = requests.get(url, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    raw = r.json()

    rows = raw.get("data") or raw.get("ohlc") or []
    if not rows:
        raise ValueError(f"TCBS trả về rỗng cho {symbol}")

    df = pd.DataFrame(rows)
    if "tradingDate" in df.columns:
        df["Date"] = pd.to_datetime(df["tradingDate"])
    elif "time" in df.columns:
        df["Date"] = pd.to_datetime(df["time"], unit="s")
    else:
        raise ValueError("Không tìm thấy cột ngày trong dữ liệu TCBS")

    df = df.rename(columns={"open":"Open","high":"High","low":"Low",
                             "close":"Close","volume":"Volume"})
    df = df[["Date","Open","High","Low","Close","Volume"]].dropna()
    df = df.sort_values("Date").reset_index(drop=True)
    # Ép kiểu số
    for col in ["Open","High","Low","Close","Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df

@st.cache_data(ttl=300, show_spinner=False)
def fetch_yahoo(symbol: str, days: int) -> pd.DataFrame:
    """Yahoo Finance fallback"""
    try:
        import yfinance as yf
        end   = datetime.now()
        start = end - timedelta(days=days)
        df = yf.download(f"{symbol}.VN", start=start, end=end,
                         progress=False, auto_adjust=True)
        if df.empty:
            raise ValueError("Yahoo: empty")
        df = df.reset_index()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.rename(columns={"Date":"Date","Open":"Open","High":"High",
                                "Low":"Low","Close":"Close","Volume":"Volume"})
        for col in ["Open","High","Low","Close","Volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df[["Date","Open","High","Low","Close","Volume"]].dropna()
    except Exception as e:
        raise RuntimeError(f"Yahoo lỗi: {e}")

def get_data(symbol: str, days: int, resolution: str = "D"):
    """Thử TCBS trước, fallback Yahoo"""
    try:
        df = fetch_tcbs(symbol, days, resolution)
        return df, "TCBS Live ✅"
    except Exception as e1:
        try:
            df = fetch_yahoo(symbol, days)
            return df, "Yahoo Finance ⚠️"
        except Exception as e2:
            return pd.DataFrame(), f"Lỗi: TCBS={e1} | Yahoo={e2}"

# ══════════════════════════════════════════════════════════════════════════════
# 2. INDICATORS
# ══════════════════════════════════════════════════════════════════════════════
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    c = df["Close"].astype(float)
    hi, lo = df["High"].astype(float), df["Low"].astype(float)

    for n in [5, 10, 20, 50, 200]:
        df[f"MA{n}"] = c.rolling(n).mean()

    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    df["MACD"]        = ema12 - ema26
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"]   = df["MACD"] - df["MACD_Signal"]

    delta  = c.diff()
    gain   = delta.clip(lower=0).rolling(14).mean()
    loss   = (-delta.clip(upper=0)).rolling(14).mean()
    df["RSI"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))

    tr  = pd.concat([hi-lo, (hi-c.shift()).abs(), (lo-c.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(span=14, adjust=False).mean()
    pdm = (hi.diff()).clip(lower=0).where(hi.diff() > lo.diff().abs(), 0)
    ndm = (lo.diff().abs()).clip(lower=0).where(lo.diff().abs() > hi.diff(), 0)
    pdi = 100 * pdm.ewm(span=14, adjust=False).mean() / atr.replace(0, np.nan)
    ndi = 100 * ndm.ewm(span=14, adjust=False).mean() / atr.replace(0, np.nan)
    dx  = 100 * (pdi-ndi).abs() / (pdi+ndi).replace(0, np.nan)
    df["ADX"] = dx.ewm(span=14, adjust=False).mean()
    df["ATR"] = atr

    df["BB_mid"]   = c.rolling(20).mean()
    std            = c.rolling(20).std()
    df["BB_upper"] = df["BB_mid"] + 2*std
    df["BB_lower"] = df["BB_mid"] - 2*std
    df["BB_width"] = (df["BB_upper"] - df["BB_lower"]) / df["BB_mid"].replace(0, np.nan)

    df["Vol_MA20"]  = df["Volume"].rolling(20).mean()
    df["Vol_Ratio"] = df["Volume"] / df["Vol_MA20"].replace(0, np.nan)
    return df

def detect_patterns(df: pd.DataFrame) -> pd.DataFrame:
    pats = [None]
    for i in range(1, len(df)):
        p, c2 = df.iloc[i-1], df.iloc[i]
        body  = abs(c2.Close - c2.Open)
        up    = c2.High - max(c2.Close, c2.Open)
        dn    = min(c2.Close, c2.Open) - c2.Low
        rng   = c2.High - c2.Low
        pat   = None
        if rng > 0 and body <= rng * 0.10:                          pat = "Doji"
        elif body > 0 and dn > 2*body and up < body:                pat = "Hammer"
        elif body > 0 and up > 2*body and dn < body:                pat = "Shooting Star"
        elif (p.Close < p.Open and c2.Close > c2.Open
              and c2.Open <= p.Close and c2.Close >= p.Open):        pat = "Bullish Engulfing"
        elif (p.Close > p.Open and c2.Close < c2.Open
              and c2.Open >= p.Close and c2.Close <= p.Open):        pat = "Bearish Engulfing"
        pats.append(pat)
    df["Pattern"] = pats
    return df

# ══════════════════════════════════════════════════════════════════════════════
# 3. SIGNAL + TRADE LEVELS
# ══════════════════════════════════════════════════════════════════════════════
def expert_signal(df: pd.DataFrame):
    lat, prev = df.iloc[-1], df.iloc[-2] if len(df)>1 else df.iloc[-1]
    reasons, score = [], 0.0

    checks = [
        (lat.Close > lat.MA50,  "✅ Giá > MA50 — xu hướng tăng trung hạn",  "❌ Giá < MA50 — xu hướng giảm trung hạn", 1),
    ]
    if pd.notna(lat.MA200):
        checks.append((lat.Close > lat.MA200, "✅ Giá > MA200 — xu hướng tăng dài hạn", "❌ Giá < MA200 — xu hướng giảm dài hạn", 1))
    for cond, pos, neg, w in checks:
        reasons.append(pos if cond else neg); score += w if cond else -w

    if lat.MA5 > lat.MA10 > lat.MA20:
        reasons.append("✅ MA5>MA10>MA20 — xếp hàng tăng"); score += 1
    elif lat.MA5 < lat.MA10 < lat.MA20:
        reasons.append("❌ MA5<MA10<MA20 — xếp hàng giảm"); score -= 1
    else:
        reasons.append("⚠️ MA không đồng nhất — sideway")

    mc, ms = lat.MACD, lat.MACD_Signal
    pc, ps = prev.MACD, prev.MACD_Signal
    if mc > ms and pc <= ps:   reasons.append("🔥 MACD cắt lên Signal — MUA mạnh"); score += 2
    elif mc < ms and pc >= ps: reasons.append("💧 MACD cắt xuống Signal — BÁN"); score -= 2
    elif mc > ms:              reasons.append("✅ MACD trên Signal — động lượng tăng"); score += 1
    else:                      reasons.append("❌ MACD dưới Signal — động lượng giảm"); score -= 1

    r = lat.RSI
    if r > 70:   reasons.append(f"⚠️ RSI {r:.0f} — quá mua, cẩn thận"); score -= 1
    elif r < 30: reasons.append(f"🔥 RSI {r:.0f} — quá bán, cơ hội"); score += 1
    elif r > 50: reasons.append(f"✅ RSI {r:.0f} — ủng hộ tăng"); score += 0.5
    else:        reasons.append(f"❌ RSI {r:.0f} — ủng hộ giảm"); score -= 0.5

    if pd.notna(lat.ADX):
        a = lat.ADX
        if a > 25:
            if mc > ms: reasons.append(f"✅ ADX {a:.0f} — xu hướng tăng mạnh"); score += 1
            else:       reasons.append(f"❌ ADX {a:.0f} — xu hướng giảm mạnh"); score -= 1
        else:           reasons.append(f"⚠️ ADX {a:.0f} — chưa có xu hướng rõ")

    if lat.Close > lat.BB_upper:   reasons.append("⚠️ Vượt BB trên — quá mua"); score -= 0.5
    elif lat.Close < lat.BB_lower: reasons.append("🔥 Chạm BB dưới — quá bán"); score += 0.5
    if lat.BB_width < 0.05:        reasons.append("📉 BB bó hẹp — sắp bùng nổ")

    pat = lat.get("Pattern")
    if pat in ("Bullish Engulfing","Hammer"):
        reasons.append(f"🕯️ Nến {pat} — đảo chiều tăng"); score += 1.5
    elif pat in ("Bearish Engulfing","Shooting Star"):
        reasons.append(f"🕯️ Nến {pat} — đảo chiều giảm"); score -= 1.5
    elif pat == "Doji":
        reasons.append("🕯️ Nến Doji — lưỡng lự, chờ xác nhận")

    if lat.Vol_Ratio > 1.5:
        reasons.append("📊 Khối lượng đột biến — " + ("xác nhận mua" if score>0 else "xác nhận bán"))

    if   score >= 5:   sig = "MUA MẠNH"
    elif score >= 1.5: sig = "MUA"
    elif score >= 0.5: sig = "THEO DÕI MUA"
    elif score > -0.5: sig = "TRUNG TÍNH"
    elif score > -1.5: sig = "THEO DÕI BÁN"
    elif score >= -3:  sig = "BÁN"
    else:              sig = "BÁN MẠNH"
    return sig, reasons, round(score, 1)

def calc_trade(df: pd.DataFrame, score: float) -> dict:
    lat   = df.iloc[-1]
    c     = float(lat.Close)
    atr   = float(lat.ATR) if pd.notna(lat.ATR) else c * 0.02
    hi_p  = float(df["High"].max())
    lo_p  = float(df["Low"].min())
    hi20  = float(df["High"].tail(20).max())
    lo20  = float(df["Low"].tail(20).min())
    diff  = hi_p - lo_p

    fib = {
        "0%":    lo_p,
        "23.6%": lo_p + diff*0.236,
        "38.2%": lo_p + diff*0.382,
        "50%":   lo_p + diff*0.500,
        "61.8%": lo_p + diff*0.618,
        "78.6%": lo_p + diff*0.786,
        "100%":  hi_p,
    }
    is_bull = score >= 0.5
    if is_bull:
        buy  = round(c * 0.99)
        sl   = round(min(c - atr*1.5, lo20*0.995))
        tps  = sorted(v for v in fib.values() if v > c)
        sell = round(hi20)
    else:
        buy  = round(lo20 * 1.005)
        sl   = round(buy - atr*1.5)
        tps  = sorted(v for v in fib.values() if v > buy)
        sell = round(c)

    tp1 = round(tps[0]) if len(tps)>0 else round(buy*1.05)
    tp2 = round(tps[1]) if len(tps)>1 else round(buy*1.10)
    tp3 = round(tps[2]) if len(tps)>2 else round(buy*1.15)
    risk   = abs(buy-sl)/buy if buy>0 else 0
    reward = (tp2-buy)/buy   if buy>0 else 0
    rr     = reward/risk      if risk>0 else 0
    return dict(buy=buy,sell=sell,sl=sl,tp1=tp1,tp2=tp2,tp3=tp3,
                risk=risk,reward=reward,rr=rr,fib=fib,atr=atr)

# ══════════════════════════════════════════════════════════════════════════════
# 4. CHART
# ══════════════════════════════════════════════════════════════════════════════
def build_chart(df: pd.DataFrame, symbol: str, trade: dict, show_n=100) -> go.Figure:
    show = df.tail(show_n).copy()
    fig = make_subplots(
        rows=4, cols=1, shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=[0.55, 0.15, 0.15, 0.15],
        subplot_titles=("", "Volume", "MACD", "RSI")
    )
    # ─ Nến ──────────────────────────────────────────────────────────────────
    fig.add_trace(go.Candlestick(
        x=show["Date"], open=show["Open"], high=show["High"],
        low=show["Low"], close=show["Close"], name="Giá",
        increasing=dict(fillcolor="#00e07a", line=dict(color="#00e07a", width=1)),
        decreasing=dict(fillcolor="#ff3d5a", line=dict(color="#ff3d5a", width=1)),
    ), row=1, col=1)

    # ─ MA ───────────────────────────────────────────────────────────────────
    for ma, color, w in [("MA20","#4a9ef8",1.5), ("MA50","#f5a623",1.5), ("MA200","#a78bfa",1)]:
        if show[ma].notna().any():
            fig.add_trace(go.Scatter(x=show["Date"], y=show[ma], name=ma,
                line=dict(color=color,width=w), hoverinfo="skip"), row=1, col=1)

    # ─ Bollinger ────────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(x=show["Date"], y=show["BB_upper"],
        name="BB+", line=dict(color="rgba(167,139,250,0.35)",width=1,dash="dot"),
        hoverinfo="skip"), row=1, col=1)
    fig.add_trace(go.Scatter(x=show["Date"], y=show["BB_lower"],
        name="BB−", line=dict(color="rgba(167,139,250,0.35)",width=1,dash="dot"),
        fill="tonexty", fillcolor="rgba(167,139,250,0.05)", hoverinfo="skip"), row=1, col=1)

    # ─ Đường BUY / SL / TP ─────────────────────────────────────────────────
    ylo = float(show["Low"].min())
    yhi = float(show["High"].max())
    for price, lbl, clr, dash in [
        (trade["buy"], "BUY", "#00e07a", "dash"),
        (trade["sl"],  "SL",  "#ff3d5a", "dash"),
        (trade["tp1"], "TP1", "#f5a623", "dot"),
        (trade["tp2"], "TP2", "#f5c623", "dot"),
        (trade["tp3"], "TP3", "#f5e023", "dot"),
    ]:
        if ylo*0.85 < price < yhi*1.15:
            fig.add_hline(y=price, row=1, col=1,
                line=dict(color=clr, dash=dash, width=1),
                annotation_text=f" {lbl} {price:,.0f}",
                annotation_font=dict(color=clr, size=10))

    # ─ Volume ───────────────────────────────────────────────────────────────
    vol_colors = ["#00e07a" if r.Close>=r.Open else "#ff3d5a" for _,r in show.iterrows()]
    fig.add_trace(go.Bar(x=show["Date"], y=show["Volume"], name="Vol",
        marker_color=vol_colors, opacity=0.6), row=2, col=1)
    if show["Vol_MA20"].notna().any():
        fig.add_trace(go.Scatter(x=show["Date"], y=show["Vol_MA20"], name="Vol MA20",
            line=dict(color="#f5a623",width=1), hoverinfo="skip"), row=2, col=1)

    # ─ MACD ─────────────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(x=show["Date"], y=show["MACD"], name="MACD",
        line=dict(color="#4a9ef8",width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=show["Date"], y=show["MACD_Signal"], name="Signal",
        line=dict(color="#ff3d5a",width=1,dash="dot")), row=3, col=1)
    h_colors = ["#00e07a" if v>=0 else "#ff3d5a" for v in show["MACD_Hist"].fillna(0)]
    fig.add_trace(go.Bar(x=show["Date"], y=show["MACD_Hist"], name="Hist",
        marker_color=h_colors, opacity=0.8), row=3, col=1)

    # ─ RSI ──────────────────────────────────────────────────────────────────
    fig.add_trace(go.Scatter(x=show["Date"], y=show["RSI"], name="RSI",
        line=dict(color="#a78bfa",width=1.5)), row=4, col=1)
    for lvl, clr in [(70,"#ff3d5a"),(50,"#7dafd8"),(30,"#00e07a")]:
        fig.add_hline(y=lvl, row=4, col=1,
            line=dict(color=clr, dash="dot", width=0.8))

    # ─ Layout ───────────────────────────────────────────────────────────────
    fig.update_layout(
        height=750, template="plotly_dark",
        paper_bgcolor="#081524", plot_bgcolor="#081524",
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.01, x=0,
                    font=dict(size=11, color="#c9deff"),
                    bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=10, r=60, t=30, b=10),
        font=dict(family="monospace", color="#c9deff", size=11),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#102030", gridwidth=0.5,
                     tickfont=dict(color="#7cb8e8"))
    fig.update_yaxes(showgrid=True, gridcolor="#102030", gridwidth=0.5,
                     tickfont=dict(color="#7cb8e8"))
    # Subplot titles màu sáng
    for ann in fig.layout.annotations:
        ann.font.color = "#7cb8e8"
        ann.font.size  = 10
    return fig

# ══════════════════════════════════════════════════════════════════════════════
# 5. UI — SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
SIG_COLOR = {
    "MUA MẠNH":     "#00e07a",
    "MUA":          "#00c866",
    "THEO DÕI MUA": "#7fcf50",
    "TRUNG TÍNH":   "#7cb8e8",
    "THEO DÕI BÁN": "#f5a623",
    "BÁN":          "#ff3d5a",
    "BÁN MẠNH":     "#dd1144",
}

with st.sidebar:
    st.markdown("## 📈 Pro Trader")
    st.markdown("---")
    symbol = st.text_input("🔎 Mã cổ phiếu", value="VPB",
                           help="VD: VPB, HPG, VCB, FPT, MWG, SSI...").upper().strip()

    st.markdown("**Khung thời gian biểu đồ**")
    interval_label = st.selectbox("Độ phân giải nến",
        list(INTERVAL_MAP.keys()), index=4,
        help="Ngày: phù hợp phân tích trung-dài hạn\nGiờ/phút: intraday trading")
    res_tcbs = INTERVAL_MAP[interval_label][0]

    period_label = st.selectbox("Lịch sử dữ liệu",
        ["1 tuần","1 tháng","3 tháng","6 tháng","1 năm","2 năm"], index=3)
    period_days = {"1 tuần":7,"1 tháng":30,"3 tháng":90,
                   "6 tháng":180,"1 năm":365,"2 năm":730}[period_label]

    show_n = st.slider("Số nến hiển thị", 30, 300, 100, 10)
    auto_r = st.checkbox("Tự động refresh", value=False)
    if auto_r:
        refresh_sec = st.select_slider("Tần suất (giây)", [30,60,120,300], value=60)

    run_btn = st.button("🚀 Phân tích ngay", use_container_width=True)
    st.markdown("---")

    st.markdown("**Mã gợi ý nhanh**")
    quick_list = ["VPB","HPG","VCB","FPT","MWG","SSI","TCB","VIC","ACB","STB",
                  "MSN","BID","CTG","MBB","HDB","NVL","PDR","DXG","BCM","REE"]
    cols_q = st.columns(4)
    clicked = None
    for i, m in enumerate(quick_list):
        if cols_q[i%4].button(m, key=f"q_{m}", use_container_width=True):
            clicked = m
    if clicked:
        symbol = clicked

# ══════════════════════════════════════════════════════════════════════════════
# 6. UI — MAIN
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(f"## 📊 {symbol}  <span style='font-size:14px;color:#4a9ef8;'>— {interval_label} / {period_label}</span>", 
            unsafe_allow_html=True)

if not (run_btn or auto_r or clicked):
    st.markdown("""
    <div style='text-align:center;padding:60px 20px;background:#0d2035;border-radius:12px;border:1px solid #1c3a5c;'>
      <div style='font-size:48px;'>📈</div>
      <div style='font-size:16px;color:#7cb8e8;margin-top:10px;'>Chọn mã cổ phiếu và nhấn <b style="color:#fff;">Phân tích ngay</b></div>
      <div style='font-size:12px;color:#3a6080;margin-top:6px;'>Dữ liệu từ TCBS · Hỗ trợ ngày / giờ / phút / tuần / tháng</div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# Load data
with st.spinner(f"⏳ Đang tải {symbol} từ TCBS..."):
    df_raw, data_src = get_data(symbol, period_days, res_tcbs)

if df_raw.empty:
    st.error(f"❌ Không lấy được dữ liệu. {data_src}\n\n"
             f"**Kiểm tra:** Mã {symbol} có đúng không? (VD: VPB, HPG, VCB)")
    st.stop()

df = compute_indicators(df_raw.copy())
df = detect_patterns(df)
sig, reasons, score = expert_signal(df)
trade = calc_trade(df, score)
lat  = df.iloc[-1]
prev = df.iloc[-2] if len(df)>1 else lat

st.caption(f"🟢 Nguồn: **{data_src}** · {len(df)} phiên · Cập nhật: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")

# ── Metric cards ──────────────────────────────────────────────────────────────
chg = float(lat.Close) - float(prev.Close)
pct = chg / float(prev.Close) * 100 if prev.Close else 0
col1, col2, col3, col4 = st.columns(4)
col1.metric("💰 Giá đóng cửa",
            f"{lat.Close:,.0f} đ",
            f"{'▲' if chg>=0 else '▼'} {abs(chg):,.0f} ({abs(pct):.2f}%)")
vol_str = f"{lat.Volume/1e6:.2f}M" if lat.Volume>=1e6 else f"{lat.Volume/1e3:.0f}K"
col2.metric("📊 Khối lượng", vol_str, f"×{lat.Vol_Ratio:.2f} trung bình")
col3.metric("📐 ATR (14)", f"{lat.ATR:,.0f} đ", "Biên độ dao động TB")
pat_val = lat.get("Pattern") or "Thường"
pat_dir = ("↗ Tăng" if pat_val in ("Bullish Engulfing","Hammer")
           else "↘ Giảm" if pat_val in ("Bearish Engulfing","Shooting Star")
           else "↔ Neutral")
col4.metric("🕯️ Mô hình nến", pat_val, pat_dir)

# ── Signal bar ────────────────────────────────────────────────────────────────
sig_clr = SIG_COLOR.get(sig, "#7cb8e8")
pct_m   = min(100, max(0, (score+6)/12*100))
sc_clr  = "#00e07a" if score>=1.5 else "#ff3d5a" if score<=-1.5 else "#f5a623"
st.markdown(f"""
<div style='background:#0d2035;border:1px solid #1c3a5c;border-radius:10px;
            padding:14px 20px;margin:10px 0;display:flex;align-items:center;gap:20px;flex-wrap:wrap;'>
  <div>
    <div style='font-size:10px;color:#7cb8e8;letter-spacing:2px;'>TÍN HIỆU TỔNG HỢP</div>
    <div style='font-size:28px;font-weight:700;color:{sig_clr};'>{sig}</div>
  </div>
  <div style='text-align:center;'>
    <div style='font-size:10px;color:#7cb8e8;'>ĐIỂM SỐ</div>
    <div style='font-size:30px;font-weight:700;color:{sc_clr};'>{score}</div>
  </div>
  <div style='flex:1;min-width:180px;'>
    <div style='font-size:9px;color:#3a6080;letter-spacing:1px;margin-bottom:4px;'>BÁN MẠNH ←——→ MUA MẠNH</div>
    <div style='height:8px;background:#0d1f33;border-radius:4px;overflow:hidden;border:1px solid #1c3a5c;'>
      <div style='height:100%;width:{pct_m}%;background:{sig_clr};border-radius:4px;'></div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Trade levels ──────────────────────────────────────────────────────────────
st.markdown("### 🎯 Chiến lược giao dịch")
tc1, tc2, tc3, tc4 = st.columns(4)

def trade_card(col, title, value, sub, bg, border):
    col.markdown(f"""
    <div style='background:{bg};border:{border};border-radius:9px;padding:12px 14px;'>
      <div style='font-size:10px;letter-spacing:1px;margin-bottom:4px;color:#c9deff;'>{title}</div>
      <div style='font-size:19px;font-weight:700;color:#ffffff;'>{value}</div>
      <div style='font-size:11px;color:#9dc8e8;margin-top:3px;'>{sub}</div>
    </div>""", unsafe_allow_html=True)

trade_card(tc1, "📗 VÙNG MUA VÀO",
           f"{trade['buy']:,} đ",
           f"Giá mục tiêu mua",
           "rgba(0,224,122,0.1)", "1px solid rgba(0,224,122,0.4)")

trade_card(tc2, "📕 CẮT LỖ (STOP LOSS)",
           f"{trade['sl']:,} đ",
           f"Rủi ro: {trade['risk']*100:.1f}% / vốn",
           "rgba(255,61,90,0.1)", "1px solid rgba(255,61,90,0.4)")

trade_card(tc3, "🎯 CHỐT LỜI (TP)",
           f"TP1: {trade['tp1']:,}",
           f"TP2: {trade['tp2']:,}  TP3: {trade['tp3']:,}",
           "rgba(245,166,35,0.1)", "1px solid rgba(245,166,35,0.4)")

rr = trade['rr']
rr_clr  = "#00e07a" if rr>=2 else "#f5a623" if rr>=1.5 else "#ff3d5a"
rr_text = "Tuyệt vời ✅" if rr>=2.5 else "Tốt ✅" if rr>=2 else "Chấp nhận ⚠️" if rr>=1.5 else "Rủi ro cao ❌"
trade_card(tc4, "⚖️ TỶ LỆ R:R",
           f"1 : {rr:.1f}",
           f"{rr_text} · LN kỳ vọng {trade['reward']*100:.1f}%",
           "rgba(74,158,248,0.1)", "1px solid rgba(74,158,248,0.4)")

# ── Chart ─────────────────────────────────────────────────────────────────────
st.markdown("### 📉 Biểu đồ kỹ thuật")
fig = build_chart(df, symbol, trade, show_n)
st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":True})

# ── Fibonacci ─────────────────────────────────────────────────────────────────
with st.expander("📐 Fibonacci Retracement — Hỗ trợ & Kháng cự"):
    fib_rows = []
    for lvl, price in trade["fib"].items():
        dist = (price / float(lat.Close) - 1) * 100
        role = "◀ GIÁ HIỆN TẠI" if abs(dist) < 1.5 else ("Hỗ trợ 🟢" if price < lat.Close else "Kháng cự 🔴")
        fib_rows.append({"Mức Fib": lvl, "Giá (đ)": f"{price:,.0f}",
                         "Khoảng cách": f"{dist:+.1f}%", "Vai trò": role})
    st.dataframe(pd.DataFrame(fib_rows), use_container_width=True, hide_index=True)

# ── Indicators + Reasons ──────────────────────────────────────────────────────
ic1, ic2 = st.columns([1, 2])
with ic1:
    st.markdown("**📊 Chỉ báo hiện tại**")
    ind_data = [
        ("RSI (14)",   f"{lat.RSI:.1f}",       "Quá mua 🔴" if lat.RSI>70 else "Quá bán 🟢" if lat.RSI<30 else "Bình thường ✅"),
        ("MACD",       f"{lat.MACD:.2f}",       "Tăng 🟢" if lat.MACD>0 else "Giảm 🔴"),
        ("ADX (14)",   f"{lat.ADX:.1f}",        "Xu hướng mạnh ✅" if lat.ADX>25 else "Yếu ⚠️"),
        ("BB Width",   f"{lat.BB_width*100:.1f}%", "Bó hẹp — bùng nổ sắp!" if lat.BB_width<0.05 else "Bình thường"),
        ("Vol Ratio",  f"×{lat.Vol_Ratio:.2f}", "Đột biến 📢" if lat.Vol_Ratio>1.5 else "Bình thường"),
        ("ATR",        f"{lat.ATR:,.0f} đ",     "Biên độ dao động TB ngày"),
    ]
    st.dataframe(pd.DataFrame(ind_data, columns=["Chỉ báo","Giá trị","Trạng thái"]),
                 use_container_width=True, hide_index=True)

with ic2:
    st.markdown("**🔍 Phân tích tín hiệu chi tiết**")
    for r in reasons:
        st.write(r)

st.markdown("---")
st.caption(f"Pro Trader Terminal · Dữ liệu: {data_src} · {symbol} · {interval_label} · {datetime.now().strftime('%d/%m/%Y %H:%M')}")

if auto_r:
    time.sleep(refresh_sec)
    st.rerun()
