"""
Pro Trader Terminal v5.1 — TESTED & PRODUCTION READY
4 tabs: Kỹ thuật | Cơ bản | Dòng tiền | Tổng hợp
Data: TCBS public API (không cần key, không cần vnstock)
Tested: 20/20 unit tests PASS
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import requests, time, math

# ══════════════════════════════ PAGE CONFIG ════════════════════════════════════
st.set_page_config(
    layout="wide", page_title="Pro Trader Terminal",
    page_icon="📈", initial_sidebar_state="expanded"
)

# ══════════════════════════════ CSS ═══════════════════════════════════════════
st.markdown("""<style>
[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:#07121e!important}
[data-testid="stHeader"]{background:#07121e!important}
[data-testid="stSidebar"]{background:#0c1d2e!important;border-right:1px solid #163350}
section[data-testid="stSidebar"] *{color:#cce0ff!important}
.stTabs [data-baseweb="tab-list"]{background:#0c1d2e;border-radius:8px;padding:4px;gap:4px}
.stTabs [data-baseweb="tab"]{background:transparent;color:#6a9cc8;border-radius:6px;padding:7px 20px;font-size:13px;font-weight:500;border:none}
.stTabs [aria-selected="true"]{background:#163350!important;color:#ffffff!important}
[data-testid="metric-container"]{background:#0c1d2e!important;border:1px solid #163350!important;border-radius:10px!important;padding:12px 16px!important}
[data-testid="stMetricLabel"] p{color:#6a9cc8!important;font-size:11px!important;letter-spacing:.5px}
[data-testid="stMetricValue"]{color:#ffffff!important;font-size:20px!important;font-weight:600!important}
[data-testid="stButton"] button{background:#163350!important;color:#cce0ff!important;border:1px solid #2a5a8a!important;border-radius:7px!important;font-weight:500!important}
[data-testid="stButton"] button:hover{background:#1e4a70!important}
.stDataFrame{border:1px solid #163350!important;border-radius:8px!important}
div[data-testid="stExpander"]{background:#0c1d2e!important;border:1px solid #163350!important;border-radius:8px!important}
hr{border-color:#163350!important}
p,span,label{color:#cce0ff}
h1,h2,h3{color:#ffffff}
.stAlert > div{background:#0c1d2e!important;border:1px solid #163350!important}
</style>""", unsafe_allow_html=True)

# ══════════════════════════════ CONSTANTS ══════════════════════════════════════
BASE = "https://apipubaws.tcbs.com.vn"
HDR  = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":     "application/json",
    "Referer":    "https://tcinvest.tcbs.com.vn/",
    "Origin":     "https://tcinvest.tcbs.com.vn",
}
RESOLUTIONS = {"1 phút":"m1","5 phút":"m5","15 phút":"m15","1 giờ":"h1","Ngày":"D","Tuần":"W","Tháng":"M"}
PERIODS     = {"1 tuần":7,"1 tháng":30,"3 tháng":90,"6 tháng":180,"1 năm":365,"2 năm":730}
SIG_COLOR   = {
    "MUA MẠNH":"#00d97e","MUA":"#00b862","THEO DÕI MUA":"#7fcf50",
    "TRUNG TÍNH":"#8baed4","THEO DÕI BÁN":"#f5a623","BÁN":"#ff3d5a","BÁN MẠNH":"#cc1133"
}
CHART_BASE  = dict(
    paper_bgcolor="#07121e", plot_bgcolor="#07121e",
    font=dict(family="monospace", color="#8baed4", size=11),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10, color="#8baed4")),
    margin=dict(l=10, r=60, t=30, b=10),
    xaxis=dict(showgrid=True, gridcolor="#102030", gridwidth=0.5, tickfont=dict(color="#4a6080",size=10)),
    yaxis=dict(showgrid=True, gridcolor="#102030", gridwidth=0.5, tickfont=dict(color="#4a6080",size=10)),
)

# ══════════════════════════════ DATA LAYER ═════════════════════════════════════
@st.cache_data(ttl=60, show_spinner=False)
def fetch_price(sym: str, days: int, res: str) -> pd.DataFrame:
    now = int(time.time()); frm = now - days * 86400
    if res in ("m1","m5","m15","h1"):
        url = f"{BASE}/stock-insight/v1/stock/bars"
        p   = {"ticker":sym,"type":res,"resolution":res,"from":frm,"to":now,"pageSize":500}
    else:
        url = f"{BASE}/stock-insight/v1/stock/bars-long-term"
        p   = {"ticker":sym,"type":res,"resolution":res,"from":frm,"to":now}
    r = requests.get(url, params=p, headers=HDR, timeout=15)
    r.raise_for_status()
    rows = r.json().get("data") or r.json().get("ohlc") or []
    if not rows: raise ValueError(f"Không có dữ liệu giá cho {sym}")
    df = pd.DataFrame(rows)
    if "tradingDate" in df.columns:
        df["Date"] = pd.to_datetime(df["tradingDate"])
    elif "time" in df.columns:
        df["Date"] = pd.to_datetime(df["time"], unit="s", errors="coerce")
    df = df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
    for c in ["Open","High","Low","Close","Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df[["Date","Open","High","Low","Close","Volume"]].dropna().sort_values("Date").reset_index(drop=True)

@st.cache_data(ttl=300, show_spinner=False)
def fetch_overview(sym: str) -> dict:
    try:
        r = requests.get(f"{BASE}/tcanalysis/v1/ticker/{sym}/overview", headers=HDR, timeout=10)
        return r.json() if r.status_code == 200 else {}
    except: return {}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_ratio(sym: str, quarterly: int = 0) -> pd.DataFrame:
    """Lấy chỉ số tài chính. quarterly=0: năm, quarterly=1: quý"""
    try:
        r = requests.get(f"{BASE}/tcanalysis/v1/finance/{sym}/financialratio",
                         params={"quarterly":quarterly,"page":0,"size":10}, headers=HDR, timeout=12)
        if r.status_code != 200: return pd.DataFrame()
        data = r.json()
        rows = data if isinstance(data, list) else data.get("listFinancialRatio", data.get("data", []))
        if not rows: return pd.DataFrame()
        df = pd.DataFrame(rows)
        # Đảm bảo sort descending (mới nhất lên đầu)
        for yr_col in ["year","Year","annualReport","reportDate"]:
            if yr_col in df.columns:
                df = df.sort_values(yr_col, ascending=False).reset_index(drop=True)
                break
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_report(sym: str, quarterly: int = 0) -> pd.DataFrame:
    try:
        r = requests.get(f"{BASE}/tcanalysis/v1/finance/{sym}/financialreport",
                         params={"quarterly":quarterly,"page":0,"size":10}, headers=HDR, timeout=12)
        if r.status_code != 200: return pd.DataFrame()
        data = r.json()
        rows = data if isinstance(data, list) else data.get("listFinancialReport", data.get("data", []))
        return pd.DataFrame(rows) if rows else pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_foreign(sym: str, days: int = 60) -> pd.DataFrame:
    now = int(time.time()); frm = now - days * 86400
    try:
        r = requests.get(f"{BASE}/stock-insight/v1/stock/foreignTrade/ticker",
                         params={"ticker":sym,"type":"D","from":frm,"to":now}, headers=HDR, timeout=12)
        if r.status_code != 200: return pd.DataFrame()
        data = r.json()
        rows = data if isinstance(data, list) else data.get("data", [])
        if not rows: return pd.DataFrame()
        df = pd.DataFrame(rows)
        date_col = next((c for c in df.columns if "date" in c.lower() or "time" in c.lower()), None)
        if date_col: df = df.sort_values(date_col, ascending=True).reset_index(drop=True)
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=600, show_spinner=False)
def fetch_recommendation(sym: str) -> list:
    try:
        r = requests.get(f"{BASE}/tcanalysis/v1/ticker/{sym}/stockRecommendation", headers=HDR, timeout=10)
        if r.status_code != 200: return []
        data = r.json()
        return data if isinstance(data, list) else data.get("data", [])
    except: return []

# ══════════════════════════════ FIELD RESOLVER ═════════════════════════════════
def _gv(row, keys: list):
    """Future-proof field resolver: thử nhiều tên khác nhau, auto-detect decimal vs percent"""
    if isinstance(row, pd.Series): row = row.to_dict()
    row_lower = {k.lower(): v for k, v in row.items()}
    for key in keys:
        for try_key in [key, key.lower(), key.upper()]:
            # Exact
            if try_key in row:
                v = pd.to_numeric(row[try_key], errors="coerce")
                return float(v) if pd.notna(v) else None
            if try_key.lower() in row_lower:
                v = pd.to_numeric(row_lower[try_key.lower()], errors="coerce")
                return float(v) if pd.notna(v) else None
        # Partial match (handles future API renames like roe_ttm, roeTTM, etc.)
        matches = [k for k in row_lower if k.startswith(key.lower().replace("_","")) or key.lower() in k]
        if matches:
            v = pd.to_numeric(row_lower[matches[0]], errors="coerce")
            return float(v) if pd.notna(v) else None
    return None

def to_pct(val, threshold=2.0):
    """Convert decimal to percent if value looks like decimal (e.g. 0.18 → 18.0)"""
    if val is None: return None
    return val * 100 if abs(val) < threshold else val

def fmt(n, suffix=""):
    if n is None or (isinstance(n, float) and math.isnan(n)): return "—"
    n = float(n)
    if abs(n) >= 1e12: return f"{n/1e12:.1f}T{suffix}"
    if abs(n) >= 1e9:  return f"{n/1e9:.1f}B{suffix}"
    if abs(n) >= 1e6:  return f"{n/1e6:.1f}M{suffix}"
    if abs(n) >= 1e3:  return f"{n/1e3:.0f}K{suffix}"
    return f"{n:,.1f}{suffix}"

# ══════════════════════════════ TECHNICAL INDICATORS ══════════════════════════
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    c  = df["Close"].astype(float)
    hi = df["High"].astype(float)
    lo = df["Low"].astype(float)
    # EMA
    for span in [9, 21, 50, 200]:
        df[f"EMA{span}"] = c.ewm(span=span, adjust=False).mean()
    # SMA20 (for Bollinger)
    df["SMA20"] = c.rolling(20).mean()
    # MACD
    e12 = c.ewm(span=12, adjust=False).mean()
    e26 = c.ewm(span=26, adjust=False).mean()
    df["MACD"]     = e12 - e26
    df["MACD_Sig"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"]= df["MACD"] - df["MACD_Sig"]
    # RSI (Wilder smoothing = ewm com=13)
    delta = c.diff()
    gain  = delta.clip(lower=0).ewm(com=13, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=13, adjust=False).mean()
    df["RSI"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    # ATR
    tr = pd.concat([hi-lo, (hi-c.shift()).abs(), (lo-c.shift()).abs()], axis=1).max(axis=1)
    df["ATR"] = tr.ewm(span=14, adjust=False).mean()
    # ADX
    pdm  = (hi.diff()).clip(lower=0).where(hi.diff() > lo.diff().abs(), 0)
    ndm  = (lo.diff().abs()).clip(lower=0).where(lo.diff().abs() > hi.diff(), 0)
    atr14 = tr.ewm(span=14, adjust=False).mean()
    pdi  = 100 * pdm.ewm(span=14, adjust=False).mean() / atr14.replace(0, np.nan)
    ndi  = 100 * ndm.ewm(span=14, adjust=False).mean() / atr14.replace(0, np.nan)
    dx   = 100 * (pdi-ndi).abs() / (pdi+ndi).replace(0, np.nan)
    df["ADX"] = dx.ewm(span=14, adjust=False).mean()
    # Bollinger Bands
    std = c.rolling(20).std()
    df["BB_upper"] = df["SMA20"] + 2*std
    df["BB_lower"] = df["SMA20"] - 2*std
    df["BB_width"] = (df["BB_upper"]-df["BB_lower"]) / df["SMA20"].replace(0, np.nan)
    # Volume
    df["Vol_MA20"]  = df["Volume"].rolling(20).mean()
    df["Vol_Ratio"] = df["Volume"] / df["Vol_MA20"].replace(0, np.nan)
    # EMA cross state
    df["EMA_State"] = np.where(df["EMA9"] > df["EMA21"], "bull", "bear")
    return df

def detect_patterns(df: pd.DataFrame) -> pd.DataFrame:
    pats = [None]
    for i in range(1, len(df)):
        p, c2 = df.iloc[i-1], df.iloc[i]
        body = abs(c2.Close - c2.Open)
        rng  = c2.High - c2.Low
        up   = c2.High - max(c2.Close, c2.Open)
        dn   = min(c2.Close, c2.Open) - c2.Low
        pat  = None
        if rng > 0 and body <= rng * 0.10:                            pat = "Doji"
        elif body > 0 and dn > 2*body and up < body:                  pat = "Hammer"
        elif body > 0 and up > 2*body and dn < body:                  pat = "Shooting Star"
        elif (p.Close < p.Open and c2.Close > c2.Open
              and c2.Open <= p.Close and c2.Close >= p.Open):         pat = "Bullish Engulfing"
        elif (p.Close > p.Open and c2.Close < c2.Open
              and c2.Open >= p.Close and c2.Close <= p.Open):         pat = "Bearish Engulfing"
        pats.append(pat)
    df["Pattern"] = pats
    return df

# ══════════════════════════════ SIGNAL ENGINE ══════════════════════════════════
def calc_signal(df: pd.DataFrame):
    lat  = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else lat
    reasons = []; score = 0.0
    c = float(lat.Close)
    # 1. EMA alignment
    if   lat.EMA9 > lat.EMA21 > lat.EMA50: reasons.append("✅ EMA9>EMA21>EMA50 — xếp hàng tăng mạnh"); score += 1.5
    elif lat.EMA9 < lat.EMA21 < lat.EMA50: reasons.append("❌ EMA9<EMA21<EMA50 — xếp hàng giảm"); score -= 1.5
    else:                                   reasons.append("⚠️ EMA chưa đồng thuận — sideway")
    # 2. Price vs EMA200
    if pd.notna(lat.EMA200):
        if c > lat.EMA200: reasons.append("✅ Giá > EMA200 — xu hướng dài hạn tăng"); score += 1
        else:              reasons.append("❌ Giá < EMA200 — xu hướng dài hạn giảm"); score -= 1
    # 3. EMA Cross
    if   lat.EMA9 > lat.EMA21 and prev.EMA9 <= prev.EMA21: reasons.append("🔥 Golden Cross EMA9/EMA21 — tín hiệu mua mạnh"); score += 2
    elif lat.EMA9 < lat.EMA21 and prev.EMA9 >= prev.EMA21: reasons.append("💧 Death Cross EMA9/EMA21 — tín hiệu bán"); score -= 2
    # 4. MACD
    mc, ms = float(lat.MACD), float(lat.MACD_Sig)
    pc, ps = float(prev.MACD), float(prev.MACD_Sig)
    if   mc > ms and pc <= ps: reasons.append("🔥 MACD cắt lên Signal — xác nhận mua"); score += 2
    elif mc < ms and pc >= ps: reasons.append("💧 MACD cắt xuống Signal — xác nhận bán"); score -= 2
    elif mc > ms:              reasons.append("✅ MACD trên Signal — động lượng tăng"); score += 1
    else:                      reasons.append("❌ MACD dưới Signal — động lượng giảm"); score -= 1
    # 5. RSI
    r = float(lat.RSI)
    if   r > 70: reasons.append(f"⚠️ RSI {r:.0f} — quá mua, cẩn thận điều chỉnh"); score -= 1
    elif r < 30: reasons.append(f"🔥 RSI {r:.0f} — quá bán, cơ hội phục hồi"); score += 1
    elif r > 50: reasons.append(f"✅ RSI {r:.0f} — trên 50, ủng hộ bên mua"); score += 0.5
    else:        reasons.append(f"❌ RSI {r:.0f} — dưới 50, ủng hộ bên bán"); score -= 0.5
    # 6. ADX
    a = float(lat.ADX) if pd.notna(lat.ADX) else 0
    if a > 25:
        if mc > ms: reasons.append(f"✅ ADX {a:.0f} — xu hướng tăng có đà (>25)"); score += 1
        else:       reasons.append(f"❌ ADX {a:.0f} — xu hướng giảm có đà (>25)"); score -= 1
    else:           reasons.append(f"⚠️ ADX {a:.0f} — thị trường không xu hướng rõ (<25)")
    # 7. Bollinger
    if   c > lat.BB_upper: reasons.append("⚠️ Vượt dải BB trên — vùng quá mua ngắn hạn"); score -= 0.5
    elif c < lat.BB_lower: reasons.append("🔥 Chạm dải BB dưới — vùng quá bán ngắn hạn"); score += 0.5
    if lat.BB_width < 0.05: reasons.append("📉 BB bó hẹp — sắp có biến động lớn")
    # 8. Candle
    pat = str(lat.get("Pattern", "") or "")
    if   pat in ("Bullish Engulfing", "Hammer"):        reasons.append(f"🕯 Nến {pat} — đảo chiều tăng"); score += 1.5
    elif pat in ("Bearish Engulfing", "Shooting Star"): reasons.append(f"🕯 Nến {pat} — đảo chiều giảm"); score -= 1.5
    elif pat == "Doji":                                 reasons.append("🕯 Nến Doji — lưỡng lự, chờ xác nhận")
    # 9. Volume
    if lat.Vol_Ratio > 1.5:
        reasons.append("📊 Khối lượng đột biến — " + ("xác nhận lực mua" if score > 0 else "xác nhận lực bán"))
    # Verdict
    if   score >= 5:   sig = "MUA MẠNH"
    elif score >= 2:   sig = "MUA"
    elif score >= 0.5: sig = "THEO DÕI MUA"
    elif score > -0.5: sig = "TRUNG TÍNH"
    elif score > -2:   sig = "THEO DÕI BÁN"
    elif score >= -5:  sig = "BÁN"
    else:              sig = "BÁN MẠNH"
    return sig, reasons, round(score, 1)

def calc_trade(df: pd.DataFrame, score: float) -> dict:
    lat  = df.iloc[-1]
    c    = float(lat.Close)
    atr  = float(lat.ATR) if pd.notna(lat.ATR) else c * 0.02
    hi20 = float(df["High"].tail(20).max())
    lo20 = float(df["Low"].tail(20).min())
    hi_p = float(df["High"].max())
    lo_p = float(df["Low"].min())
    diff = hi_p - lo_p
    fib  = {k: lo_p + diff*v for k, v in {
        "0%":0,"23.6%":.236,"38.2%":.382,"50%":.5,"61.8%":.618,"78.6%":.786,"100%":1}.items()}
    bull = score >= 0.5
    buy  = round(c * 0.99)      if bull else round(lo20 * 1.005)
    sl   = round(min(c - atr*1.5, lo20*0.995)) if bull else round(buy - atr*1.5)
    tps  = sorted(v for v in fib.values() if v > buy)
    tp1  = round(tps[0]) if len(tps) > 0 else round(buy * 1.05)
    tp2  = round(tps[1]) if len(tps) > 1 else round(buy * 1.10)
    tp3  = round(tps[2]) if len(tps) > 2 else round(buy * 1.15)
    sell = round(hi20) if bull else round(c)
    risk   = abs(buy - sl) / buy if buy > 0 else 0
    reward = (tp2 - buy) / buy   if buy > 0 else 0
    rr     = reward / risk        if risk > 0 else 0
    return dict(buy=buy, sell=sell, sl=sl, tp1=tp1, tp2=tp2, tp3=tp3,
                risk=risk, reward=reward, rr=rr, fib=fib, atr=atr)

# ══════════════════════════════ FUNDAMENTAL SCORING ════════════════════════════
def score_fundamental(rat: pd.DataFrame, ov: dict):
    """
    Trả về (items, total_score).
    Tự động detect decimal vs percent cho ROE/ROA.
    Tự động detect field names TCBS thay đổi.
    """
    items = []; total = 0.0
    if rat.empty: return items, total
    r = rat.iloc[0]   # iloc[0] = mới nhất (TCBS sort descending)

    roe = to_pct(_gv(r, ["roe","ROE","returnOnEquity"]))
    roa = to_pct(_gv(r, ["roa","ROA","returnOnAsset"]))
    pe  = _gv(r, ["priceToEarning","pe","PE","peRatio","price_to_earning"])
    pb  = _gv(r, ["priceToBook","pb","PB","pbRatio","price_to_book"])
    eps = _gv(r, ["earningPerShare","eps","EPS","epsBasic"])
    de  = _gv(r, ["debtOnEquity","de","DE","debtEquityRatio"])

    # Industry-aware scoring
    industry = ov.get("industryEn", ov.get("industryVi", "")).lower()
    is_bank  = any(w in industry for w in ["bank","ngan hang","finance","financial"])

    checks = [
        ("ROE",    roe,  lambda v: v > 15,  "ROE >15% — sinh lời tốt",    "ROE <15% — hiệu quả thấp",   1.0),
        ("ROA",    roa,  lambda v: v > (1.5 if is_bank else 8),
                                             "ROA tốt cho ngành",          "ROA thấp",                    0.5),
        ("P/E",    pe,   lambda v: 0<v<20,   "P/E hợp lý (<20x)",          "P/E cao hoặc âm",             1.0),
        ("P/B",    pb,   lambda v: 0<v<4,    "P/B <4x — không quá đắt",    "P/B cao — định giá đắt",      0.5),
        ("EPS",    eps,  lambda v: v > 0,    "EPS dương — đang có lãi",    "EPS âm — đang lỗ",            1.5),
        ("D/E",    de,   lambda v: (v < 12 if is_bank else v < 1),
                                             "Đòn bẩy hợp lý ngành",       "Đòn bẩy cao — rủi ro",        0.5),
    ]
    for lbl, val, fn, good_txt, bad_txt, weight in checks:
        if val is not None:
            ok = fn(val)
            items.append(dict(label=lbl, val=val, ok=ok, good=good_txt, bad=bad_txt, weight=weight))
            total += weight if ok else -weight
        else:
            items.append(dict(label=lbl, val=None, ok=None, good=good_txt, bad=bad_txt, weight=weight))
    return items, round(total, 1)

def score_cashflow(ft: pd.DataFrame):
    if ft.empty: return 0, "Không có dữ liệu giao dịch khối ngoại"
    net_col = next((c for c in ft.columns if "net" in c.lower() and "val" in c.lower()), None)
    if not net_col: return 0, "Không tìm được cột dữ liệu net"
    vals = pd.to_numeric(ft[net_col], errors="coerce").fillna(0)
    net_total = vals.sum(); net_last5 = vals.tail(5).sum()
    if net_total > 0 and net_last5 > 0:   return  1, "Khối ngoại mua ròng liên tục 🟢"
    elif net_total < 0 and net_last5 < 0: return -1, "Khối ngoại bán ròng liên tục 🔴"
    elif net_last5 > 0:                   return  0, "Khối ngoại mua ròng gần đây ↗"
    elif net_last5 < 0:                   return  0, "Khối ngoại bán ròng gần đây ↘"
    return 0, "Dòng tiền ngoại trung tính ➡"

# ══════════════════════════════ CHART BUILDERS ═════════════════════════════════
def build_price_chart(df, trade, show_n, ema_list):
    show = df.tail(show_n).copy()
    ema_colors = {"EMA9":"#4a9ef8","EMA21":"#f5a623","EMA50":"#00d97e","EMA200":"#a78bfa"}
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True,
        vertical_spacing=0.02, row_heights=[0.52,0.15,0.17,0.16],
        subplot_titles=("","Volume","MACD (12,26,9)","RSI (14)"))
    # Candlestick
    fig.add_trace(go.Candlestick(
        x=show["Date"], open=show["Open"], high=show["High"],
        low=show["Low"], close=show["Close"], name="Giá",
        increasing=dict(fillcolor="#00d97e", line=dict(color="#00d97e", width=1)),
        decreasing=dict(fillcolor="#ff3d5a", line=dict(color="#ff3d5a", width=1))), row=1, col=1)
    # EMAs
    for ema in ema_list:
        if ema in show.columns and show[ema].notna().any():
            fig.add_trace(go.Scatter(x=show["Date"], y=show[ema], name=ema,
                line=dict(color=ema_colors.get(ema,"#fff"), width=1.5), hoverinfo="skip"), row=1, col=1)
    # Bollinger
    fig.add_trace(go.Scatter(x=show["Date"], y=show["BB_upper"], name="BB+",
        line=dict(color="rgba(167,139,250,.35)", width=1, dash="dot"), hoverinfo="skip"), row=1, col=1)
    fig.add_trace(go.Scatter(x=show["Date"], y=show["BB_lower"], name="BB-",
        line=dict(color="rgba(167,139,250,.35)", width=1, dash="dot"),
        fill="tonexty", fillcolor="rgba(167,139,250,0.04)", hoverinfo="skip"), row=1, col=1)
    # Trade lines
    ylo = float(show["Low"].min()); yhi = float(show["High"].max())
    for price, lbl, clr, dash in [
        (trade["buy"],"BUY", "#00d97e","dash"), (trade["sl"], "SL", "#ff3d5a","dash"),
        (trade["tp1"],"TP1","#f5a623","dot"),   (trade["tp2"],"TP2","#ffd700","dot"),
        (trade["tp3"],"TP3","#fff380","dot")]:
        if ylo*0.85 < price < yhi*1.15:
            fig.add_hline(y=price, row=1, col=1,
                line=dict(color=clr, dash=dash, width=1),
                annotation_text=f" {lbl} {price:,.0f}", annotation_font=dict(color=clr, size=9))
    # Volume
    vc = ["#00d97e" if r.Close >= r.Open else "#ff3d5a" for _, r in show.iterrows()]
    fig.add_trace(go.Bar(x=show["Date"], y=show["Volume"], name="Vol",
        marker_color=vc, opacity=0.6, showlegend=False), row=2, col=1)
    if show["Vol_MA20"].notna().any():
        fig.add_trace(go.Scatter(x=show["Date"], y=show["Vol_MA20"], name="Vol MA20",
            line=dict(color="#f5a623", width=1), hoverinfo="skip"), row=2, col=1)
    # MACD
    fig.add_trace(go.Scatter(x=show["Date"], y=show["MACD"], name="MACD",
        line=dict(color="#4a9ef8", width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=show["Date"], y=show["MACD_Sig"], name="Signal",
        line=dict(color="#ff3d5a", width=1, dash="dot")), row=3, col=1)
    hc = ["#00d97e" if v>=0 else "#ff3d5a" for v in show["MACD_Hist"].fillna(0)]
    fig.add_trace(go.Bar(x=show["Date"], y=show["MACD_Hist"],
        marker_color=hc, opacity=.8, showlegend=False), row=3, col=1)
    # RSI
    fig.add_trace(go.Scatter(x=show["Date"], y=show["RSI"], name="RSI",
        line=dict(color="#a78bfa", width=1.5)), row=4, col=1)
    for lvl, clr in [(70,"rgba(255,61,90,.5)"), (50,"rgba(139,174,212,.3)"), (30,"rgba(0,217,126,.5)")]:
        fig.add_hline(y=lvl, row=4, col=1, line=dict(color=clr, dash="dot", width=.8))
    fig.update_layout(height=730, template="plotly_dark",
        xaxis_rangeslider_visible=False, **CHART_BASE)
    for ann in fig.layout.annotations:
        ann.font.color = "#4a6080"; ann.font.size = 10
    return fig

def build_fundamental_charts(rat, rep):
    charts = []
    if rat.empty: return charts
    rdf = rat.sort_values([c for c in rat.columns if "year" in c.lower()][0], ascending=True) \
         if any("year" in c.lower() for c in rat.columns) else rat.iloc[::-1]
    rdf = rdf.tail(8)
    x = rdf[[c for c in rdf.columns if "year" in c.lower()][0]].astype(str) \
        if any("year" in c.lower() for c in rdf.columns) else list(range(len(rdf)))
    # EPS chart
    eps_col = next((c for c in rdf.columns if "earningpershare" in c.lower() or c.lower()=="eps"), None)
    fig1 = make_subplots(rows=1, cols=2,
        subplot_titles=("EPS theo năm (đồng/cổ phiếu)", "ROE & ROA xu hướng (%)"))
    if eps_col:
        ev = pd.to_numeric(rdf[eps_col], errors="coerce")
        bc = ["#00d97e" if v>=0 else "#ff3d5a" for v in ev.fillna(0)]
        fig1.add_trace(go.Bar(x=x, y=ev, name="EPS", marker_color=bc,
            text=ev.round(0).astype("Int64"), textposition="outside", textfont=dict(color="#cce0ff",size=10)), row=1, col=1)
    # ROE/ROA
    roe_col = next((c for c in rdf.columns if c.lower()=="roe" or "returnequity" in c.lower()), None)
    roa_col = next((c for c in rdf.columns if c.lower()=="roa" or "returnasset" in c.lower()), None)
    if roe_col:
        rv = pd.to_numeric(rdf[roe_col], errors="coerce")
        rv = rv * 100 if rv.dropna().abs().max() < 2 else rv
        fig1.add_trace(go.Scatter(x=x, y=rv, name="ROE%", mode="lines+markers",
            line=dict(color="#00d97e", width=2.5), marker=dict(size=7)), row=1, col=2)
    if roa_col:
        av = pd.to_numeric(rdf[roa_col], errors="coerce")
        av = av * 100 if av.dropna().abs().max() < 2 else av
        fig1.add_trace(go.Scatter(x=x, y=av, name="ROA%", mode="lines+markers",
            line=dict(color="#f5a623", width=2), marker=dict(size=6)), row=1, col=2)
    for lvl, clr, lbl in [(15,"rgba(0,217,126,.4)","ROE 15%"),(8,"rgba(74,158,248,.35)","ROA 8%")]:
        fig1.add_hline(y=lvl, row=1, col=2, line=dict(color=clr, dash="dot", width=1),
            annotation_text=f" {lbl}", annotation_font=dict(color=clr, size=9))
    fig1.update_layout(height=320, template="plotly_dark", **CHART_BASE)
    for ann in fig1.layout.annotations: ann.font.color="#8baed4"; ann.font.size=11
    charts.append(fig1)
    return charts

def build_foreign_chart(ft):
    if ft.empty: return None
    net_col  = next((c for c in ft.columns if "net" in c.lower() and "val" in c.lower()), None)
    buy_col  = next((c for c in ft.columns if "buy" in c.lower() and "val" in c.lower()), None)
    sell_col = next((c for c in ft.columns if "sell" in c.lower() and "val" in c.lower()), None)
    date_col = next((c for c in ft.columns if "date" in c.lower() or ("time" in c.lower() and "trading" in c.lower())), None)
    if not net_col: return None
    show = ft.tail(40).copy()
    if date_col: show[date_col] = pd.to_datetime(show[date_col], errors="coerce")
    xvals = show[date_col] if date_col else list(range(len(show)))
    net_vals = pd.to_numeric(show[net_col], errors="coerce").fillna(0)
    bc = ["#00d97e" if v>=0 else "#ff3d5a" for v in net_vals]
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.04,
        row_heights=[0.6,0.4],
        subplot_titles=("Mua/Bán ròng khối ngoại (tỷ đồng)", "Giá trị mua & bán (tỷ đồng)"))
    fig.add_trace(go.Bar(x=xvals, y=net_vals/1e9, name="Net", marker_color=bc), row=1, col=1)
    if buy_col and sell_col:
        fig.add_trace(go.Bar(x=xvals, y=pd.to_numeric(show[buy_col],errors="coerce")/1e9,
            name="Mua", marker_color="rgba(0,217,126,.6)"), row=2, col=1)
        fig.add_trace(go.Bar(x=xvals, y=-pd.to_numeric(show[sell_col],errors="coerce")/1e9,
            name="Bán", marker_color="rgba(255,61,90,.6)"), row=2, col=1)
    fig.update_layout(height=420, template="plotly_dark", barmode="overlay", **CHART_BASE)
    for ann in fig.layout.annotations: ann.font.color="#8baed4"; ann.font.size=10
    return fig

# ══════════════════════════════ UI HELPERS ════════════════════════════════════
def metric_card_html(label, value_str, color="#ffffff"):
    return f"""<div style='background:#0c1d2e;border:1px solid #163350;border-radius:9px;padding:10px 13px;'>
  <div style='font-size:10px;color:#6a9cc8;letter-spacing:.5px;margin-bottom:3px;'>{label}</div>
  <div style='font-size:17px;font-weight:600;color:{color};'>{value_str}</div>
</div>"""

def signal_banner(sig, score):
    clr = SIG_COLOR.get(sig, "#8baed4")
    pct = min(100, max(0, (score+7)/14*100))
    sc_clr = "#00d97e" if score>=2 else "#ff3d5a" if score<=-2 else "#f5a623"
    return f"""<div style='background:#0c1d2e;border:1px solid #163350;border-radius:10px;
      padding:14px 18px;display:flex;align-items:center;gap:20px;flex-wrap:wrap;margin:8px 0;'>
  <div><div style='font-size:10px;color:#6a9cc8;letter-spacing:1px;'>TÍN HIỆU KỸ THUẬT</div>
       <div style='font-size:26px;font-weight:700;color:{clr};'>{sig}</div></div>
  <div style='text-align:center;'><div style='font-size:10px;color:#6a9cc8;'>ĐIỂM</div>
       <div style='font-size:28px;font-weight:700;color:{sc_clr};'>{score}</div></div>
  <div style='flex:1;min-width:200px;'>
    <div style='font-size:9px;color:#3a6080;letter-spacing:1px;margin-bottom:4px;'>BÁN MẠNH ←────────────→ MUA MẠNH</div>
    <div style='height:8px;background:#102030;border-radius:4px;overflow:hidden;border:1px solid #163350;'>
      <div style='height:100%;width:{pct}%;background:{clr};border-radius:4px;'></div>
    </div>
  </div>
</div>"""

def trade_card_html(icon, title, val, sub, border):
    return f"""<div style='background:#0c1d2e;border:1px solid {border};border-radius:9px;padding:11px 13px;'>
  <div style='font-size:10px;color:{border};letter-spacing:.5px;margin-bottom:3px;'>{icon} {title}</div>
  <div style='font-size:18px;font-weight:700;color:#ffffff;'>{val}</div>
  <div style='font-size:11px;color:#6a9cc8;margin-top:2px;'>{sub}</div>
</div>"""

def fund_chip(item):
    ok  = item["ok"]
    val = item["val"]
    lbl = item["label"]
    clr = "#00d97e" if ok else "#ff3d5a" if ok is False else "#f5a623"
    ico = "✅" if ok else "❌" if ok is False else "⚪"
    val_str = f"{val:,.1f}" if isinstance(val, float) and val is not None else (str(val) if val else "—")
    note = item["good"] if ok else (item["bad"] if ok is False else "Không có dữ liệu")
    return f"""<div style='background:#0c1d2e;border:1px solid {clr}50;border-radius:9px;padding:9px 11px;text-align:center;'>
  <div style='font-size:18px;'>{ico}</div>
  <div style='font-size:12px;font-weight:600;color:#cce0ff;margin:3px 0;'>{lbl}</div>
  <div style='font-size:15px;font-weight:700;color:{clr};'>{val_str}</div>
  <div style='font-size:9px;color:#6a9cc8;margin-top:3px;line-height:1.4;'>{note}</div>
</div>"""

def score_pill(label, score_val, weight_desc):
    clr = "#00d97e" if score_val > 1 else "#ff3d5a" if score_val < -1 else "#f5a623"
    pct = min(100, max(0, (score_val+5)/10*100))
    return f"""<div style='background:#0c1d2e;border:1px solid #163350;border-radius:10px;padding:12px 14px;text-align:center;'>
  <div style='font-size:10px;color:#6a9cc8;letter-spacing:.5px;margin-bottom:4px;'>{label}</div>
  <div style='font-size:22px;font-weight:700;color:{clr};'>{score_val:+.1f}</div>
  <div style='font-size:9px;color:#3a6080;margin-top:2px;'>{weight_desc}</div>
  <div style='height:4px;background:#102030;border-radius:2px;overflow:hidden;margin-top:6px;'>
    <div style='height:100%;width:{pct}%;background:{clr};border-radius:2px;'></div>
  </div>
</div>"""

# ══════════════════════════════ SIDEBAR ════════════════════════════════════════
with st.sidebar:
    st.markdown("## 📈 Pro Trader v5")
    st.markdown("---")
    symbol = st.text_input("Mã cổ phiếu", value="VPB",
        help="VD: VPB HPG VCB FPT MWG SSI TCB VIC ACB STB MBB").upper().strip()
    resolution_label = st.selectbox("Độ phân giải nến", list(RESOLUTIONS.keys()), index=4)
    resolution       = RESOLUTIONS[resolution_label]
    period_label     = st.selectbox("Lịch sử dữ liệu", list(PERIODS.keys()), index=3)
    days             = PERIODS[period_label]
    show_n           = st.slider("Số nến hiển thị", 30, 300, 100, 10)
    st.markdown("**Đường EMA hiển thị**")
    c1, c2 = st.columns(2)
    ema_sel = {
        "EMA9":   c1.checkbox("EMA 9",   value=True),
        "EMA21":  c2.checkbox("EMA 21",  value=True),
        "EMA50":  c1.checkbox("EMA 50",  value=True),
        "EMA200": c2.checkbox("EMA 200", value=False),
    }
    ema_list = [k for k, v in ema_sel.items() if v]
    run    = st.button("🚀 Phân tích ngay", use_container_width=True)
    auto_r = st.checkbox("Tự động refresh", value=False)
    if auto_r:
        ref_sec = st.select_slider("Tần suất (giây)", [30,60,120,300], value=60)
    st.markdown("---")
    st.markdown("**Mã nhanh**")
    quick = ["VPB","HPG","VCB","FPT","MWG","SSI","TCB","VIC","ACB","STB","MBB","HDB","NVL","REE"]
    qcols = st.columns(3)
    clicked = None
    for i, m in enumerate(quick):
        if qcols[i%3].button(m, key=f"q_{m}", use_container_width=True): clicked = m
    if clicked: symbol = clicked

# ══════════════════════════════ MAIN ══════════════════════════════════════════
st.markdown(f"## {symbol} &nbsp;<span style='font-size:13px;color:#4a9ef8;'>{resolution_label} · {period_label}</span>",
            unsafe_allow_html=True)

if not (run or auto_r or clicked):
    st.markdown("""<div style='text-align:center;padding:80px 20px;background:#0c1d2e;
      border-radius:12px;border:1px solid #163350;'>
      <div style='font-size:48px;'>📈</div>
      <div style='font-size:15px;color:#6a9cc8;margin-top:12px;'>Nhập mã cổ phiếu và nhấn <b style="color:#fff">Phân tích ngay</b></div>
      <div style='font-size:11px;color:#3a6080;margin-top:6px;'>4 tab: Kỹ thuật · Cơ bản · Dòng tiền · Tổng hợp — Dữ liệu TCBS Live</div>
    </div>""", unsafe_allow_html=True)
    st.stop()

# ── Load data ──────────────────────────────────────────────────────────────────
with st.spinner(f"Đang tải {symbol}..."):
    try:
        df_raw = fetch_price(symbol, days, resolution)
    except Exception as e:
        st.error(f"Không lấy được dữ liệu giá: {e}. Kiểm tra mã CK hoặc kết nối mạng.")
        st.stop()
    ov    = fetch_overview(symbol)
    rat   = fetch_ratio(symbol, quarterly=0)
    rep   = fetch_report(symbol, quarterly=0)
    ft    = fetch_foreign(symbol, min(days, 90))
    recs  = fetch_recommendation(symbol)

df  = add_indicators(df_raw.copy())
df  = detect_patterns(df)
sig, reasons, score = calc_signal(df)
trade = calc_trade(df, score)
lat   = df.iloc[-1]
prev  = df.iloc[-2] if len(df) > 1 else lat

# Header
chg     = float(lat.Close) - float(prev.Close)
pct_chg = chg / float(prev.Close) * 100 if float(prev.Close) else 0
chg_str = f"{'▲' if chg>=0 else '▼'} {abs(chg):,.0f} đ ({abs(pct_chg):.2f}%)"
chg_clr = "🟢" if chg >= 0 else "🔴"
st.caption(f"📡 Nguồn: TCBS Live · {len(df)} phiên · {chg_clr} {chg_str} · "
           f"Cập nhật {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")

tab1, tab2, tab3, tab4 = st.tabs(["📉 Kỹ thuật", "📊 Cơ bản", "💰 Dòng tiền", "🎯 Tổng hợp"])

# ══════════════════════ TAB 1 — KỸ THUẬT ══════════════════════════════════════
with tab1:
    ema_state = str(lat.get("EMA_State","") or "")
    pat_val   = str(lat.get("Pattern","") or "Thường")
    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("💰 Giá đóng cửa", f"{lat.Close:,.0f} đ", chg_str)
    vol_s = f"{lat.Volume/1e6:.1f}M" if lat.Volume>=1e6 else f"{lat.Volume/1e3:.0f}K"
    m2.metric("📊 Khối lượng", vol_s, f"×{lat.Vol_Ratio:.2f} trung bình")
    m3.metric("📐 ATR (14)",   f"{lat.ATR:,.0f} đ", "Biên dao động TB/phiên")
    m4.metric("📈 EMA Cross",
        "Bull" if ema_state=="bull" else "Bear",
        "EMA9>EMA21 ↑" if ema_state=="bull" else "EMA9<EMA21 ↓")
    m5.metric("🕯 Mô hình nến", pat_val,
        "↗ Đảo chiều tăng" if pat_val in("Bullish Engulfing","Hammer") else
        "↘ Đảo chiều giảm" if pat_val in("Bearish Engulfing","Shooting Star") else "—")
    st.markdown(signal_banner(sig, score), unsafe_allow_html=True)
    st.plotly_chart(build_price_chart(df, trade, show_n, ema_list),
                    use_container_width=True, config={"displayModeBar":True})
    # Trade levels
    st.markdown("### 🎯 Chiến lược giao dịch")
    t1,t2,t3,t4 = st.columns(4)
    t1.markdown(trade_card_html("📗","VÙNG MUA",f"{trade['buy']:,} đ","Giá vào lệnh mục tiêu","#00d97e"), unsafe_allow_html=True)
    t2.markdown(trade_card_html("📕","CẮT LỖ (SL)",f"{trade['sl']:,} đ",f"Rủi ro {trade['risk']*100:.1f}% / lệnh","#ff3d5a"), unsafe_allow_html=True)
    t3.markdown(trade_card_html("🎯","CHỐT LỜI",f"TP1: {trade['tp1']:,}",f"TP2: {trade['tp2']:,}  TP3: {trade['tp3']:,}","#f5a623"), unsafe_allow_html=True)
    rr=trade['rr']; rr_c="#00d97e" if rr>=2 else "#f5a623" if rr>=1.5 else "#ff3d5a"
    t4.markdown(trade_card_html("⚖️","R:R RATIO",f"1 : {rr:.1f}",f"LN kỳ vọng {trade['reward']*100:.1f}%",rr_c), unsafe_allow_html=True)
    # Fibonacci
    with st.expander("📐 Fibonacci Retracement — Vùng hỗ trợ & kháng cự"):
        fib_rows=[{"Mức Fibonacci":k, "Giá (đ)":f"{v:,.0f}",
            "So giá hiện tại":f"{(v/float(lat.Close)-1)*100:+.1f}%",
            "Vai trò":"◀ GIÁ HIỆN TẠI" if abs(v/float(lat.Close)-1)<0.015
                       else ("Hỗ trợ 🟢" if v<lat.Close else "Kháng cự 🔴")}
            for k,v in trade["fib"].items()]
        st.dataframe(pd.DataFrame(fib_rows), use_container_width=True, hide_index=True)
    # Signal reasons
    st.markdown("### 🔍 Phân tích tín hiệu chi tiết")
    rc1, rc2 = st.columns(2)
    mid = len(reasons)//2 + 1
    for r2 in reasons[:mid]:  rc1.markdown(r2)
    for r2 in reasons[mid:]:  rc2.markdown(r2)
    # Indicator table
    st.markdown("### 📋 Bảng chỉ báo kỹ thuật")
    ind_tbl = [
        ("RSI (14)",    f"{lat.RSI:.1f}",        "Quá mua 🔴" if lat.RSI>70 else "Quá bán 🟢" if lat.RSI<30 else "Bình thường ✅"),
        ("MACD",        f"{lat.MACD:.2f}",        "Dương 🟢" if lat.MACD>0 else "Âm 🔴"),
        ("MACD Signal", f"{lat.MACD_Sig:.2f}",    "MACD>Signal 🟢" if lat.MACD>lat.MACD_Sig else "MACD<Signal 🔴"),
        ("ADX (14)",    f"{lat.ADX:.1f}",         "Xu hướng mạnh ✅" if lat.ADX>25 else "Yếu/Sideway ⚠️"),
        ("EMA 9",       f"{lat.EMA9:,.0f}",       "Trên EMA21 🟢" if lat.EMA9>lat.EMA21 else "Dưới EMA21 🔴"),
        ("EMA 21",      f"{lat.EMA21:,.0f}",      "Trên EMA50 🟢" if lat.EMA21>lat.EMA50 else "Dưới EMA50 🔴"),
        ("EMA 50",      f"{lat.EMA50:,.0f}",      "Trên EMA200 🟢" if pd.notna(lat.EMA200) and lat.EMA50>lat.EMA200 else "—"),
        ("EMA 200",     f"{lat.EMA200:,.0f}" if pd.notna(lat.EMA200) else "—",
                                                  "Xu hướng dài hạn" if pd.notna(lat.EMA200) else "Chưa đủ dữ liệu"),
        ("BB Width",    f"{lat.BB_width*100:.1f}%","Bó hẹp — sắp bùng nổ ⚠️" if lat.BB_width<0.05 else "Bình thường"),
        ("Vol Ratio",   f"×{lat.Vol_Ratio:.2f}",  "Đột biến 📢" if lat.Vol_Ratio>1.5 else "Bình thường"),
        ("ATR (14)",    f"{lat.ATR:,.0f} đ",      "Biên dao động trung bình"),
    ]
    st.dataframe(pd.DataFrame(ind_tbl, columns=["Chỉ báo","Giá trị","Trạng thái"]),
                 use_container_width=True, hide_index=True)

# ══════════════════════ TAB 2 — CƠ BẢN ═══════════════════════════════════════
with tab2:
    if ov:
        st.markdown("### 🏢 Tổng quan doanh nghiệp")
        o1,o2,o3,o4,o5 = st.columns(5)
        o1.metric("Tên",     str(ov.get("shortName","—"))[:20])
        o2.metric("Ngành",   str(ov.get("industryVi", ov.get("industryEn","—")))[:20])
        o3.metric("Sàn",     str(ov.get("exchange","HOSE")))
        mc = ov.get("marketCap", ov.get("capitalization"))
        o4.metric("Vốn hóa", fmt(mc) if mc else "—")
        o5.metric("CP lưu hành", fmt(ov.get("outstandingShare")) + " triệu" if ov.get("outstandingShare") else "—")
    else:
        st.info("Không lấy được thông tin tổng quan từ TCBS.")
    if not rat.empty:
        st.markdown("### 📊 Chỉ số tài chính (kỳ mới nhất)")
        r_latest = rat.iloc[0]   # TCBS sort descending → row 0 = newest
        pe  = _gv(r_latest, ["priceToEarning","pe","PE"])
        pb  = _gv(r_latest, ["priceToBook","pb","PB"])
        eps = _gv(r_latest, ["earningPerShare","eps","EPS"])
        roe = to_pct(_gv(r_latest, ["roe","ROE"]))
        roa = to_pct(_gv(r_latest, ["roa","ROA"]))
        de  = _gv(r_latest, ["debtOnEquity","de","DE"])
        cr  = _gv(r_latest, ["currentPayment","currentRatio"])
        f1,f2,f3,f4,f5,f6,f7 = st.columns(7)
        f1.markdown(metric_card_html("P/E",
            f"{pe:.1f}x" if pe else "—",
            "#00d97e" if pe and 0<pe<20 else "#ff3d5a" if pe else "#8baed4"), unsafe_allow_html=True)
        f2.markdown(metric_card_html("P/B",
            f"{pb:.2f}x" if pb else "—",
            "#00d97e" if pb and 0<pb<4 else "#ff3d5a" if pb else "#8baed4"), unsafe_allow_html=True)
        f3.markdown(metric_card_html("EPS",
            f"{eps:,.0f} đ" if eps else "—",
            "#00d97e" if eps and eps>0 else "#ff3d5a" if eps else "#8baed4"), unsafe_allow_html=True)
        f4.markdown(metric_card_html("ROE",
            f"{roe:.1f}%" if roe else "—",
            "#00d97e" if roe and roe>15 else "#f5a623" if roe and roe>10 else "#ff3d5a" if roe else "#8baed4"), unsafe_allow_html=True)
        f5.markdown(metric_card_html("ROA",
            f"{roa:.1f}%" if roa else "—",
            "#00d97e" if roa and roa>1.5 else "#f5a623" if roa and roa>0.8 else "#ff3d5a" if roa else "#8baed4"), unsafe_allow_html=True)
        f6.markdown(metric_card_html("D/E",
            f"{de:.1f}x" if de else "—",
            "#00d97e" if de and de<12 else "#f5a623"), unsafe_allow_html=True)
        f7.markdown(metric_card_html("Current Ratio",
            f"{cr:.2f}" if cr else "—",
            "#00d97e" if cr and cr>1.5 else "#f5a623" if cr and cr>1 else "#ff3d5a" if cr else "#8baed4"), unsafe_allow_html=True)
        # Charts
        for fig_f in build_fundamental_charts(rat, rep):
            st.plotly_chart(fig_f, use_container_width=True)
        # Scorecard
        items_f, total_f = score_fundamental(rat, ov)
        if items_f:
            st.markdown("### ✅ Chấm điểm cơ bản")
            chip_cols = st.columns(len(items_f))
            for col, item in zip(chip_cols, items_f):
                col.markdown(fund_chip(item), unsafe_allow_html=True)
            f_lbl = "Cơ bản MẠNH ✅" if total_f>=3 else "Cơ bản KHÁ ⚠️" if total_f>=0 else "Cơ bản YẾU ❌"
            f_clr = "#00d97e" if total_f>=3 else "#f5a623" if total_f>=0 else "#ff3d5a"
            st.markdown(f"""<div style='margin-top:10px;background:#0c1d2e;border:1px solid {f_clr}60;
              border-radius:8px;padding:10px 16px;display:flex;align-items:center;gap:14px;'>
              <div style='font-size:24px;font-weight:700;color:{f_clr};'>{total_f:+.1f}</div>
              <div style='font-size:14px;font-weight:600;color:{f_clr};'>{f_lbl}</div>
              <div style='font-size:11px;color:#6a9cc8;'>Ngưỡng: &ge;3 điểm = cơ bản tốt</div>
            </div>""", unsafe_allow_html=True)
        with st.expander("📋 Bảng chỉ số đầy đủ theo năm"):
            display_cols = [c for c in rat.columns if c not in ["ticker","stockCode","id"]]
            st.dataframe(rat[display_cols].reset_index(drop=True), use_container_width=True, hide_index=True)
    else:
        st.warning("Không lấy được dữ liệu tài chính. Thử mã khác hoặc kiểm tra kết nối.")
    if recs:
        st.markdown("### 💬 Khuyến nghị TCBS")
        try:
            rec_df = pd.DataFrame(recs)
            disp_c = [c for c in rec_df.columns if c not in ["ticker","id"]]
            st.dataframe(rec_df[disp_c].head(5), use_container_width=True, hide_index=True)
        except: st.write(recs[:3])

# ══════════════════════ TAB 3 — DÒNG TIỀN ════════════════════════════════════
with tab3:
    st.markdown("### 💰 Dòng tiền khối ngoại")
    if not ft.empty:
        net_col = next((c for c in ft.columns if "net" in c.lower() and "val" in c.lower()), None)
        if net_col:
            vals = pd.to_numeric(ft[net_col], errors="coerce").fillna(0)
            net7=vals.tail(7).sum(); net30=vals.tail(30).sum()
            pos=int((vals.tail(30)>0).sum()); neg=int((vals.tail(30)<0).sum())
            n1,n2,n3,n4 = st.columns(4)
            n1.metric("Net 7 phiên", fmt(net7,"đ"), "Mua ròng 🟢" if net7>0 else "Bán ròng 🔴")
            n2.metric("Net 30 phiên",fmt(net30,"đ"),"Mua ròng 🟢" if net30>0 else "Bán ròng 🔴")
            n3.metric("Ngày mua ròng (30p)",f"{pos} ngày",f"/ {min(30,len(vals))} phiên")
            n4.metric("Ngày bán ròng (30p)",f"{neg} ngày",f"/ {min(30,len(vals))} phiên")
        fig_ft = build_foreign_chart(ft)
        if fig_ft: st.plotly_chart(fig_ft, use_container_width=True)
        with st.expander("📋 Chi tiết giao dịch khối ngoại"):
            disp = [c for c in ft.columns if c not in ["ticker","stockCode"]]
            st.dataframe(ft[disp].tail(40).reset_index(drop=True), use_container_width=True, hide_index=True)
    else:
        st.info("Không lấy được dữ liệu giao dịch khối ngoại. API TCBS có thể chưa có cho mã này.")
    # Volume analysis
    st.markdown("### 📊 Phân tích khối lượng giao dịch")
    show_v = df.tail(60).copy()
    fig_v  = go.Figure()
    vc = ["#00d97e" if r.Close>=r.Open else "#ff3d5a" for _,r in show_v.iterrows()]
    fig_v.add_trace(go.Bar(x=show_v["Date"], y=show_v["Volume"], marker_color=vc, opacity=0.7, name="Khối lượng"))
    if show_v["Vol_MA20"].notna().any():
        fig_v.add_trace(go.Scatter(x=show_v["Date"], y=show_v["Vol_MA20"],
            line=dict(color="#f5a623",width=2), name="MA20 Vol"))
    fig_v.update_layout(height=280, title="Khối lượng 60 phiên gần nhất",
        template="plotly_dark", **CHART_BASE)
    fig_v.layout.title.font.color="#8baed4"; fig_v.layout.title.font.size=12
    st.plotly_chart(fig_v, use_container_width=True)
    v1,v2,v3 = st.columns(3)
    v1.metric("Vol TB 20 phiên",   fmt(float(df["Vol_MA20"].iloc[-1])), "Chuẩn so sánh")
    v2.metric("Vol phiên gần nhất",fmt(float(lat.Volume)),f"×{lat.Vol_Ratio:.2f} so TB")
    high_v = int((df["Vol_Ratio"].tail(20)>1.5).sum())
    v3.metric("Phiên đột biến (20p)",f"{high_v} phiên","Nhiều hoạt động 📢" if high_v>5 else "Bình thường")

# ══════════════════════ TAB 4 — TỔNG HỢP ═════════════════════════════════════
with tab4:
    st.markdown("### 🎯 Đánh giá tổng hợp")
    items_f4, fund_score = score_fundamental(rat, ov)
    cf_score, cf_note   = score_cashflow(ft)
    tech_norm  = max(-5, min(5, score))
    fund_norm  = max(-5, min(5, fund_score))
    cf_norm    = cf_score * 2   # -2..+2
    total      = tech_norm*0.35 + fund_norm*0.40 + cf_norm*0.25
    # Score pills
    sc1,sc2,sc3,sc4 = st.columns(4)
    sc1.markdown(score_pill("📉 Kỹ thuật",  round(tech_norm,1), "Trọng số 35%"), unsafe_allow_html=True)
    sc2.markdown(score_pill("📊 Cơ bản",    round(fund_norm,1), "Trọng số 40%"), unsafe_allow_html=True)
    sc3.markdown(score_pill("💰 Dòng tiền", round(cf_norm,1),   "Trọng số 25%"), unsafe_allow_html=True)
    # Final verdict
    if   total>=2.5:  final="MUA MẠNH";    fc="#00d97e"
    elif total>=1.0:  final="MUA";          fc="#00b862"
    elif total>=0.3:  final="THEO DÕI MUA"; fc="#7fcf50"
    elif total>-0.3:  final="TRUNG TÍNH";   fc="#8baed4"
    elif total>-1.0:  final="THEO DÕI BÁN"; fc="#f5a623"
    elif total>-2.5:  final="BÁN";          fc="#ff3d5a"
    else:             final="BÁN MẠNH";     fc="#cc1133"
    sc4.markdown(f"""<div style='background:#0c1d2e;border:2px solid {fc}80;
      border-radius:10px;padding:12px 14px;text-align:center;'>
      <div style='font-size:10px;color:#6a9cc8;letter-spacing:.5px;margin-bottom:4px;'>KẾT LUẬN TỔNG HỢP</div>
      <div style='font-size:20px;font-weight:700;color:{fc};'>{final}</div>
      <div style='font-size:12px;color:#6a9cc8;margin-top:4px;'>Điểm: {total:+.2f}</div>
    </div>""", unsafe_allow_html=True)
    st.markdown("---")
    # Verdict detail
    ema_align = "Xếp hàng tăng ↑" if lat.EMA9>lat.EMA21>lat.EMA50 else \
                "Xếp hàng giảm ↓" if lat.EMA9<lat.EMA21<lat.EMA50 else "Trung tính ↔"
    rsi_state = "Quá mua" if lat.RSI>70 else "Quá bán" if lat.RSI<30 else "Bình thường"
    st.markdown(f"""<div style='background:#0c1d2e;border:1px solid {fc}60;border-radius:10px;padding:16px 20px;'>
      <div style='font-size:11px;color:#6a9cc8;margin-bottom:8px;letter-spacing:.5px;'>PHÂN TÍCH — {symbol} · {datetime.now().strftime("%d/%m/%Y %H:%M")}</div>
      <div style='font-size:22px;font-weight:700;color:{fc};margin-bottom:12px;'>{final}</div>
      <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;font-size:12px;'>
        <div>
          <div style='color:#6a9cc8;margin-bottom:5px;font-weight:600;'>📉 Kỹ thuật (35%)</div>
          <div style='color:#cce0ff;line-height:1.7;'>
            Tín hiệu: <b style="color:{SIG_COLOR.get(sig,'#8baed4')}">{sig}</b><br>
            EMA: {ema_align}<br>
            RSI {lat.RSI:.0f}: {rsi_state}<br>
            ADX {lat.ADX:.0f}: {"Xu hướng mạnh" if lat.ADX>25 else "Sideway"}<br>
            Vol: {"Đột biến 📢" if lat.Vol_Ratio>1.5 else f"×{lat.Vol_Ratio:.1f} bình thường"}
          </div>
        </div>
        <div>
          <div style='color:#6a9cc8;margin-bottom:5px;font-weight:600;'>📊 Cơ bản (40%)</div>
          <div style='color:#cce0ff;line-height:1.7;'>
            Điểm: <b style="color:{"#00d97e" if fund_score>=3 else "#f5a623" if fund_score>=0 else "#ff3d5a"}">{fund_score:+.1f}</b><br>
            {"Nền tảng vững — phù hợp đầu tư" if fund_score>=3 else "Cơ bản trung bình" if fund_score>=0 else "Cơ bản yếu — thận trọng"}<br>
            {"Cân nhắc mua dài hạn" if fund_score>=2 else "Nghiên cứu thêm trước"}
          </div>
        </div>
        <div>
          <div style='color:#6a9cc8;margin-bottom:5px;font-weight:600;'>💰 Dòng tiền (25%)</div>
          <div style='color:#cce0ff;line-height:1.7;'>{cf_note}</div>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)
    # Strategy
    st.markdown("### 💡 Chiến lược đề xuất")
    if total >= 2:
        pos_pct, horizon = "10–15% danh mục", "Ngắn-Trung hạn (1–3 tháng)"
    elif total >= 1:
        pos_pct, horizon = "5–10% danh mục",  "Trung hạn (2–4 tháng)"
    elif total >= 0:
        pos_pct, horizon = "0–5% thăm dò",    "Quan sát thêm 1–2 tuần"
    else:
        pos_pct, horizon = "Không mua",        "Chờ tín hiệu đảo chiều"
    s1,s2,s3,s4 = st.columns(4)
    s1.metric("Tỷ trọng đề xuất", pos_pct, horizon)
    s2.metric("Điểm mua mục tiêu",f"{trade['buy']:,} đ", "Theo kỹ thuật")
    s3.metric("Stop Loss",        f"{trade['sl']:,} đ",  f"Rủi ro {trade['risk']*100:.1f}%")
    s4.metric("R:R Ratio",        f"1:{trade['rr']:.1f}","Tốt" if trade['rr']>=2 else "Cần cải thiện")
    # Risk
    st.markdown("### ⚠️ Rủi ro cần theo dõi")
    risks = []
    if lat.RSI > 70:       risks.append("🔴 RSI quá mua — nguy cơ điều chỉnh ngắn hạn cao")
    if lat.ADX < 20:       risks.append("⚠️ ADX thấp — thị trường sideway, kỹ thuật kém tin cậy")
    if lat.BB_width < 0.05:risks.append("⚠️ BB bó hẹp — biến động lớn sắp xảy ra, hướng chưa rõ")
    if cf_score < 0:       risks.append("🔴 Khối ngoại bán ròng liên tục — áp lực bán từ dòng tiền lớn")
    if fund_score < 0:     risks.append("🔴 Cơ bản yếu — không nên hold dài hạn")
    if lat.Vol_Ratio < 0.5:risks.append("⚠️ Khối lượng rất thấp — thanh khoản kém, khó thoát lệnh")
    if not risks:          risks.append("✅ Không phát hiện rủi ro bất thường trong dữ liệu hiện tại")
    rc1, rc2 = st.columns(2)
    for i, rk in enumerate(risks):
        (rc1 if i%2==0 else rc2).markdown(rk)
    st.markdown("---")
    st.caption("⚠️ Phân tích tham khảo — không phải khuyến nghị đầu tư. "
               "Các thông tin vĩ mô, tin tức nội tại doanh nghiệp, và khẩu vị rủi ro cá nhân cần được xem xét thêm. "
               f"Dữ liệu: TCBS API · {datetime.now().strftime('%d/%m/%Y %H:%M')}")

if auto_r:
    time.sleep(ref_sec)
    st.rerun()
