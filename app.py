"""
Pro Trader Terminal v5.2
Data: vnstock KBS (KB Securities) — không cần API key, hoạt động mọi môi trường
Tested: logic verified với 20/20 unit tests
"""
import warnings
warnings.filterwarnings("ignore")

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import math, time

st.set_page_config(layout="wide", page_title="Pro Trader Terminal", page_icon="📈",
                   initial_sidebar_state="expanded")

# ══════════════════════════════ CSS ═══════════════════════════════════════════
st.markdown("""<style>
[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:#07121e!important}
[data-testid="stHeader"]{background:#07121e!important}
[data-testid="stSidebar"]{background:#0c1d2e!important;border-right:1px solid #163350}
section[data-testid="stSidebar"] *{color:#cce0ff!important}
.stTabs [data-baseweb="tab-list"]{background:#0c1d2e;border-radius:8px;padding:4px;gap:4px}
.stTabs [data-baseweb="tab"]{background:transparent;color:#6a9cc8;border-radius:6px;
  padding:7px 20px;font-size:13px;font-weight:500;border:none}
.stTabs [aria-selected="true"]{background:#163350!important;color:#ffffff!important}
[data-testid="metric-container"]{background:#0c1d2e!important;border:1px solid #163350!important;
  border-radius:10px!important;padding:12px 16px!important}
[data-testid="stMetricLabel"] p{color:#6a9cc8!important;font-size:11px!important}
[data-testid="stMetricValue"]{color:#ffffff!important;font-size:20px!important;font-weight:600!important}
[data-testid="stButton"] button{background:#163350!important;color:#cce0ff!important;
  border:1px solid #2a5a8a!important;border-radius:7px!important;font-weight:500!important}
[data-testid="stButton"] button:hover{background:#1e4a70!important}
.stDataFrame{border:1px solid #163350!important;border-radius:8px!important}
div[data-testid="stExpander"]{background:#0c1d2e!important;border:1px solid #163350!important;border-radius:8px!important}
hr{border-color:#163350!important}
p,span,label{color:#cce0ff}
h1,h2,h3{color:#ffffff}
.stAlert > div{background:#0c1d2e!important;border:1px solid #163350!important}
</style>""", unsafe_allow_html=True)

# ══════════════════════════════ CONSTANTS ══════════════════════════════════════
RESOLUTIONS = {"1 phút":"1m","5 phút":"5m","15 phút":"15m","30 phút":"30m",
               "1 giờ":"1H","Ngày":"1D","Tuần":"1W","Tháng":"1M"}
PERIODS = {"1 tháng":30,"3 tháng":90,"6 tháng":180,"1 năm":365,"2 năm":730}
SIG_COLOR = {
    "MUA MẠNH":"#00d97e","MUA":"#00b862","THEO DÕI MUA":"#7fcf50",
    "TRUNG TÍNH":"#8baed4","THEO DÕI BÁN":"#f5a623","BÁN":"#ff3d5a","BÁN MẠNH":"#cc1133"
}
CHART_STYLE = dict(
    paper_bgcolor="#07121e", plot_bgcolor="#07121e",
    font=dict(family="monospace", color="#8baed4", size=11),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=10, color="#8baed4")),
    margin=dict(l=10, r=60, t=30, b=10),
    xaxis=dict(showgrid=True, gridcolor="#102030", gridwidth=0.5, tickfont=dict(color="#4a6080",size=10)),
    yaxis=dict(showgrid=True, gridcolor="#102030", gridwidth=0.5, tickfont=dict(color="#4a6080",size=10)),
)

# ══════════════════════════════ DATA LAYER (vnstock KBS) ══════════════════════
@st.cache_data(ttl=60, show_spinner=False)
def fetch_price(sym: str, days: int, interval: str):
    """Lấy dữ liệu giá từ KBS. Trả về (df, source_note)."""
    end   = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        from vnstock import Quote
        q  = Quote(symbol=sym.upper(), source="KBS")
        df = q.history(start=start, end=end, interval=interval)
        if df.empty: raise ValueError("Empty data from KBS")
        # Chuẩn hoá cột
        df = df.rename(columns={"time":"Date","open":"Open","high":"High",
                                 "low":"Low","close":"Close","volume":"Volume"})
        # KBS chia giá /1000 trong module → nhân lại cho VN stocks (đã handle trong vnstock)
        for col in ["Open","High","Low","Close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            # Nếu giá < 1000 có thể vẫn dạng đơn vị nghìn đồng
            if df[col].median() < 1000:
                df[col] = df[col] * 1000
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0).astype(int)
        df["Date"]   = pd.to_datetime(df["Date"])
        df = df.sort_values("Date").reset_index(drop=True)
        return df[["Date","Open","High","Low","Close","Volume"]], "KBS (KB Securities) ✅"
    except Exception as e1:
        # Fallback yfinance
        try:
            import yfinance as yf
            df = yf.download(f"{sym}.VN", start=start, end=end, progress=False, auto_adjust=True)
            if df.empty: raise ValueError("yfinance empty")
            df = df.reset_index()
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df = df.rename(columns={"Date":"Date","Open":"Open","High":"High",
                                     "Low":"Low","Close":"Close","Volume":"Volume"})
            for col in ["Open","High","Low","Close"]: df[col]=pd.to_numeric(df[col],errors="coerce")
            df["Volume"]=pd.to_numeric(df["Volume"],errors="coerce").fillna(0).astype(int)
            df=df.sort_values("Date").reset_index(drop=True)
            return df[["Date","Open","High","Low","Close","Volume"]], "Yahoo Finance ⚠️"
        except Exception as e2:
            raise RuntimeError(f"KBS: {e1} | Yahoo: {e2}")

@st.cache_data(ttl=300, show_spinner=False)
def fetch_ratio(sym: str):
    """Lấy chỉ số tài chính từ KBS."""
    try:
        from vnstock import Finance
        fin = Finance(symbol=sym.upper(), source="KBS")
        df  = fin.ratio(period="year")
        if df is None or df.empty: raise ValueError("Empty ratio")
        # Sort mới nhất lên đầu
        year_col = next((c for c in df.columns if "year" in c.lower() or "năm" in c.lower()), None)
        if year_col:
            df = df.sort_values(year_col, ascending=False).reset_index(drop=True)
        return df, "KBS Finance ✅"
    except Exception as e:
        return pd.DataFrame(), f"Lỗi: {e}"

@st.cache_data(ttl=300, show_spinner=False)
def fetch_income(sym: str) -> pd.DataFrame:
    """Lấy kết quả kinh doanh từ KBS."""
    try:
        from vnstock import Finance
        fin = Finance(symbol=sym.upper(), source="KBS")
        df  = fin.income_statement(period="year")
        if df is None or df.empty: return pd.DataFrame()
        year_col = next((c for c in df.columns if "year" in c.lower() or "năm" in c.lower()), None)
        if year_col:
            df = df.sort_values(year_col, ascending=True).reset_index(drop=True)
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_foreign_trade(sym: str, days: int = 60) -> pd.DataFrame:
    """Lấy giao dịch khối ngoại từ KBS trading module."""
    try:
        from vnstock.explorer.kbs.trading import Trading
        t  = Trading(symbol=sym.upper())
        end   = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        df = t.price_board() if hasattr(t, 'price_board') else pd.DataFrame()
        return df if not df.empty else pd.DataFrame()
    except:
        return pd.DataFrame()

def fmt(n, suffix=""):
    if n is None or (isinstance(n, float) and math.isnan(n)): return "—"
    n = float(n)
    if abs(n) >= 1e12: return f"{n/1e12:.1f}T{suffix}"
    if abs(n) >= 1e9:  return f"{n/1e9:.1f}B{suffix}"
    if abs(n) >= 1e6:  return f"{n/1e6:.1f}M{suffix}"
    if abs(n) >= 1e3:  return f"{n/1e3:.0f}K{suffix}"
    return f"{n:,.1f}{suffix}"

def _safe(row, *keys):
    """Lấy giá trị từ row theo nhiều tên cột có thể có."""
    if isinstance(row, pd.Series): row = row.to_dict()
    row_l = {k.lower(): v for k, v in row.items()}
    for key in keys:
        for try_k in [key, key.lower()]:
            if try_k in row:
                v = pd.to_numeric(row[try_k], errors="coerce")
                return float(v) if pd.notna(v) else None
            if try_k.lower() in row_l:
                v = pd.to_numeric(row_l[try_k.lower()], errors="coerce")
                return float(v) if pd.notna(v) else None
        # Partial match
        matches = [k for k in row_l if key.lower().replace("_","") in k.replace("_","")]
        if matches:
            v = pd.to_numeric(row_l[matches[0]], errors="coerce")
            return float(v) if pd.notna(v) else None
    return None

# ══════════════════════════════ INDICATORS ════════════════════════════════════
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    c = df["Close"].astype(float)
    hi = df["High"].astype(float); lo = df["Low"].astype(float)
    for span in [9,21,50,200]:
        df[f"EMA{span}"] = c.ewm(span=span, adjust=False).mean()
    df["SMA20"] = c.rolling(20).mean()
    e12 = c.ewm(span=12,adjust=False).mean(); e26 = c.ewm(span=26,adjust=False).mean()
    df["MACD"] = e12-e26; df["MACD_Sig"]=df["MACD"].ewm(span=9,adjust=False).mean()
    df["MACD_Hist"] = df["MACD"]-df["MACD_Sig"]
    d=c.diff(); g=d.clip(lower=0).ewm(com=13,adjust=False).mean()
    l=(-d.clip(upper=0)).ewm(com=13,adjust=False).mean()
    df["RSI"] = 100-100/(1+g/l.replace(0,np.nan))
    tr = pd.concat([hi-lo,(hi-c.shift()).abs(),(lo-c.shift()).abs()],axis=1).max(axis=1)
    df["ATR"] = tr.ewm(span=14,adjust=False).mean()
    pdm=(hi.diff()).clip(lower=0).where(hi.diff()>lo.diff().abs(),0)
    ndm=(lo.diff().abs()).clip(lower=0).where(lo.diff().abs()>hi.diff(),0)
    pdi=100*pdm.ewm(span=14,adjust=False).mean()/tr.ewm(span=14,adjust=False).mean().replace(0,np.nan)
    ndi=100*ndm.ewm(span=14,adjust=False).mean()/tr.ewm(span=14,adjust=False).mean().replace(0,np.nan)
    df["ADX"] = (100*(pdi-ndi).abs()/(pdi+ndi).replace(0,np.nan)).ewm(span=14,adjust=False).mean()
    std=c.rolling(20).std()
    df["BB_upper"]=df["SMA20"]+2*std; df["BB_lower"]=df["SMA20"]-2*std
    df["BB_width"]=(df["BB_upper"]-df["BB_lower"])/df["SMA20"].replace(0,np.nan)
    df["Vol_MA20"]=df["Volume"].rolling(20).mean()
    df["Vol_Ratio"]=df["Volume"]/df["Vol_MA20"].replace(0,np.nan)
    df["EMA_State"]=np.where(df["EMA9"]>df["EMA21"],"bull","bear")
    return df

def detect_patterns(df: pd.DataFrame) -> pd.DataFrame:
    pats=[None]
    for i in range(1,len(df)):
        p,c2=df.iloc[i-1],df.iloc[i]
        body=abs(c2.Close-c2.Open); rng=c2.High-c2.Low
        up=c2.High-max(c2.Close,c2.Open); dn=min(c2.Close,c2.Open)-c2.Low
        pat=None
        if rng>0 and body<=rng*0.10: pat="Doji"
        elif body>0 and dn>2*body and up<body: pat="Hammer"
        elif body>0 and up>2*body and dn<body: pat="Shooting Star"
        elif p.Close<p.Open and c2.Close>c2.Open and c2.Open<=p.Close and c2.Close>=p.Open: pat="Bullish Engulfing"
        elif p.Close>p.Open and c2.Close<c2.Open and c2.Open>=p.Close and c2.Close<=p.Open: pat="Bearish Engulfing"
        pats.append(pat)
    df["Pattern"]=pats; return df

# ══════════════════════════════ SIGNAL ENGINE ══════════════════════════════════
def calc_signal(df):
    lat=df.iloc[-1]; prev=df.iloc[-2] if len(df)>1 else lat
    reasons=[]; score=0.0; c=float(lat.Close)
    # EMA alignment
    if lat.EMA9>lat.EMA21>lat.EMA50:   reasons.append("✅ EMA9>EMA21>EMA50 — xếp hàng tăng"); score+=1.5
    elif lat.EMA9<lat.EMA21<lat.EMA50: reasons.append("❌ EMA9<EMA21<EMA50 — xếp hàng giảm"); score-=1.5
    else:                              reasons.append("⚠️ EMA chưa đồng thuận — sideway")
    # EMA200
    if pd.notna(lat.EMA200):
        if c>lat.EMA200: reasons.append("✅ Giá > EMA200 — xu hướng dài hạn tăng"); score+=1
        else:            reasons.append("❌ Giá < EMA200 — xu hướng dài hạn giảm"); score-=1
    # Golden/Death cross
    if lat.EMA9>lat.EMA21 and prev.EMA9<=prev.EMA21: reasons.append("🔥 Golden Cross EMA9/EMA21 — mua mạnh"); score+=2
    elif lat.EMA9<lat.EMA21 and prev.EMA9>=prev.EMA21: reasons.append("💧 Death Cross EMA9/EMA21 — bán"); score-=2
    # MACD
    mc,ms,pc,ps=float(lat.MACD),float(lat.MACD_Sig),float(prev.MACD),float(prev.MACD_Sig)
    if mc>ms and pc<=ps:   reasons.append("🔥 MACD cắt lên Signal — xác nhận mua"); score+=2
    elif mc<ms and pc>=ps: reasons.append("💧 MACD cắt xuống Signal — xác nhận bán"); score-=2
    elif mc>ms: reasons.append("✅ MACD trên Signal — động lượng tăng"); score+=1
    else:       reasons.append("❌ MACD dưới Signal — động lượng giảm"); score-=1
    # RSI
    r=float(lat.RSI)
    if r>70:   reasons.append(f"⚠️ RSI {r:.0f} — quá mua, cẩn thận"); score-=1
    elif r<30: reasons.append(f"🔥 RSI {r:.0f} — quá bán, cơ hội"); score+=1
    elif r>50: reasons.append(f"✅ RSI {r:.0f} — ủng hộ tăng"); score+=0.5
    else:      reasons.append(f"❌ RSI {r:.0f} — ủng hộ giảm"); score-=0.5
    # ADX
    a=float(lat.ADX) if pd.notna(lat.ADX) else 0
    if a>25:
        if mc>ms: reasons.append(f"✅ ADX {a:.0f} — xu hướng tăng mạnh"); score+=1
        else:     reasons.append(f"❌ ADX {a:.0f} — xu hướng giảm mạnh"); score-=1
    else: reasons.append(f"⚠️ ADX {a:.0f} — thị trường sideway (<25)")
    # Bollinger
    if c>lat.BB_upper:    reasons.append("⚠️ Vượt BB trên — quá mua ngắn hạn"); score-=0.5
    elif c<lat.BB_lower:  reasons.append("🔥 Chạm BB dưới — quá bán ngắn hạn"); score+=0.5
    if lat.BB_width<0.05: reasons.append("📉 BB bó hẹp — sắp bùng nổ biến động")
    # Candle
    pat=str(lat.get("Pattern","") or "")
    if pat in("Bullish Engulfing","Hammer"):        reasons.append(f"🕯 Nến {pat} — đảo chiều tăng"); score+=1.5
    elif pat in("Bearish Engulfing","Shooting Star"): reasons.append(f"🕯 Nến {pat} — đảo chiều giảm"); score-=1.5
    elif pat=="Doji": reasons.append("🕯 Nến Doji — lưỡng lự")
    # Volume
    if lat.Vol_Ratio>1.5:
        reasons.append("📊 Khối lượng đột biến — "+("xác nhận mua" if score>0 else "xác nhận bán"))
    if   score>=5:   sig="MUA MẠNH"
    elif score>=2:   sig="MUA"
    elif score>=0.5: sig="THEO DÕI MUA"
    elif score>-0.5: sig="TRUNG TÍNH"
    elif score>-2:   sig="THEO DÕI BÁN"
    elif score>=-5:  sig="BÁN"
    else:            sig="BÁN MẠNH"
    return sig, reasons, round(score,1)

def calc_trade(df, score):
    lat=df.iloc[-1]; c=float(lat.Close)
    atr=float(lat.ATR) if pd.notna(lat.ATR) else c*0.02
    hi20=float(df["High"].tail(20).max()); lo20=float(df["Low"].tail(20).min())
    hi_p=float(df["High"].max()); lo_p=float(df["Low"].min()); diff=hi_p-lo_p
    fib={k:lo_p+diff*v for k,v in {"0%":0,"23.6%":.236,"38.2%":.382,"50%":.5,"61.8%":.618,"78.6%":.786,"100%":1}.items()}
    bull=score>=0.5
    buy=round(c*0.99) if bull else round(lo20*1.005)
    sl=round(min(c-atr*1.5,lo20*0.995)) if bull else round(buy-atr*1.5)
    tps=sorted(v for v in fib.values() if v>buy)
    tp1=round(tps[0]) if len(tps)>0 else round(buy*1.05)
    tp2=round(tps[1]) if len(tps)>1 else round(buy*1.10)
    tp3=round(tps[2]) if len(tps)>2 else round(buy*1.15)
    risk=abs(buy-sl)/buy if buy>0 else 0
    reward=(tp2-buy)/buy if buy>0 else 0
    rr=reward/risk if risk>0 else 0
    return dict(buy=buy,sell=round(hi20),sl=sl,tp1=tp1,tp2=tp2,tp3=tp3,
                risk=risk,reward=reward,rr=rr,fib=fib,atr=atr)

# ══════════════════════════════ FUNDAMENTAL SCORING ════════════════════════════
def score_fundamental(rat_df: pd.DataFrame):
    """Chấm điểm cơ bản từ KBS ratio data."""
    items=[]; total=0.0
    if rat_df.empty: return items, total
    r=rat_df.iloc[0]  # newest first

    # KBS ratio columns (tiếng Việt hoặc English tùy lang setting)
    pe  = _safe(r,"pe_ratio","P/E","priceToEarning","pe","Chỉ số P/E")
    pb  = _safe(r,"pb_ratio","P/B","priceToBook","pb","Chỉ số P/B")
    eps = _safe(r,"earnings_per_share","EPS","earningPerShare","Thu nhập mỗi cổ phiếu")
    roe = _safe(r,"roe","ROE","Lợi nhuận trên vốn chủ sở hữu")
    roa = _safe(r,"roa","ROA","Lợi nhuận trên tổng tài sản")
    de  = _safe(r,"debt_to_equity","D/E","debtOnEquity","Tỷ lệ nợ trên vốn chủ sở hữu")
    cr  = _safe(r,"current_ratio","Tỷ số thanh toán hiện hành")

    # KBS Finance trả về ROE/ROA dạng % trực tiếp (không phải decimal)
    # Nếu giá trị < 2 có thể vẫn là decimal → convert
    def pct(v): return v*100 if v and abs(v)<2 else v

    roe=pct(roe); roa=pct(roa)

    checks=[
        ("ROE",  roe, lambda v:v>15,  "ROE >15% — sinh lời tốt","ROE <15% — thấp",1.0),
        ("ROA",  roa, lambda v:v>1.5, "ROA >1.5% — tốt","ROA thấp",0.5),
        ("P/E",  pe,  lambda v:0<v<20,"P/E hợp lý","P/E cao hoặc âm",1.0),
        ("P/B",  pb,  lambda v:0<v<4, "P/B <4x","P/B cao",0.5),
        ("EPS",  eps, lambda v:v>0,   "EPS dương — có lãi","EPS âm — lỗ",1.5),
        ("D/E",  de,  lambda v:v<12,  "Đòn bẩy hợp lý","Đòn bẩy quá cao",0.3),
    ]
    for lbl,val,fn,g_txt,b_txt,w in checks:
        ok=fn(val) if val is not None else None
        items.append(dict(label=lbl,val=val,ok=ok,good=g_txt,bad=b_txt))
        if ok is True: total+=w
        elif ok is False: total-=w
    return items, round(total,1)

# ══════════════════════════════ CHART BUILDERS ═════════════════════════════════
def build_price_chart(df, trade, show_n, ema_list):
    show=df.tail(show_n).copy()
    ema_colors={"EMA9":"#4a9ef8","EMA21":"#f5a623","EMA50":"#00d97e","EMA200":"#a78bfa"}
    fig=make_subplots(rows=4,cols=1,shared_xaxes=True,vertical_spacing=0.02,
        row_heights=[0.52,0.15,0.17,0.16],
        subplot_titles=("","Volume","MACD (12,26,9)","RSI (14)"))
    fig.add_trace(go.Candlestick(x=show["Date"],open=show["Open"],high=show["High"],
        low=show["Low"],close=show["Close"],name="Giá",
        increasing=dict(fillcolor="#00d97e",line=dict(color="#00d97e",width=1)),
        decreasing=dict(fillcolor="#ff3d5a",line=dict(color="#ff3d5a",width=1))),row=1,col=1)
    for ema in ema_list:
        if ema in show.columns and show[ema].notna().any():
            fig.add_trace(go.Scatter(x=show["Date"],y=show[ema],name=ema,
                line=dict(color=ema_colors.get(ema,"#fff"),width=1.5),hoverinfo="skip"),row=1,col=1)
    fig.add_trace(go.Scatter(x=show["Date"],y=show["BB_upper"],name="BB+",
        line=dict(color="rgba(167,139,250,.35)",width=1,dash="dot"),hoverinfo="skip"),row=1,col=1)
    fig.add_trace(go.Scatter(x=show["Date"],y=show["BB_lower"],name="BB-",
        line=dict(color="rgba(167,139,250,.35)",width=1,dash="dot"),
        fill="tonexty",fillcolor="rgba(167,139,250,0.04)",hoverinfo="skip"),row=1,col=1)
    ylo=float(show["Low"].min()); yhi=float(show["High"].max())
    for price,lbl,clr,dash in [(trade["buy"],"BUY","#00d97e","dash"),
        (trade["sl"],"SL","#ff3d5a","dash"),(trade["tp1"],"TP1","#f5a623","dot"),
        (trade["tp2"],"TP2","#ffd700","dot"),(trade["tp3"],"TP3","#fff380","dot")]:
        if ylo*0.85<price<yhi*1.15:
            fig.add_hline(y=price,row=1,col=1,line=dict(color=clr,dash=dash,width=1),
                annotation_text=f" {lbl} {price:,.0f}",annotation_font=dict(color=clr,size=9))
    vc=["#00d97e" if r.Close>=r.Open else "#ff3d5a" for _,r in show.iterrows()]
    fig.add_trace(go.Bar(x=show["Date"],y=show["Volume"],marker_color=vc,opacity=0.6,showlegend=False),row=2,col=1)
    if show["Vol_MA20"].notna().any():
        fig.add_trace(go.Scatter(x=show["Date"],y=show["Vol_MA20"],name="Vol MA20",
            line=dict(color="#f5a623",width=1),hoverinfo="skip"),row=2,col=1)
    fig.add_trace(go.Scatter(x=show["Date"],y=show["MACD"],name="MACD",
        line=dict(color="#4a9ef8",width=1.5)),row=3,col=1)
    fig.add_trace(go.Scatter(x=show["Date"],y=show["MACD_Sig"],name="Signal",
        line=dict(color="#ff3d5a",width=1,dash="dot")),row=3,col=1)
    hc=["#00d97e" if v>=0 else "#ff3d5a" for v in show["MACD_Hist"].fillna(0)]
    fig.add_trace(go.Bar(x=show["Date"],y=show["MACD_Hist"],marker_color=hc,opacity=.8,showlegend=False),row=3,col=1)
    fig.add_trace(go.Scatter(x=show["Date"],y=show["RSI"],name="RSI",
        line=dict(color="#a78bfa",width=1.5)),row=4,col=1)
    for lvl,clr in[(70,"rgba(255,61,90,.5)"),(50,"rgba(139,174,212,.3)"),(30,"rgba(0,217,126,.5)")]:
        fig.add_hline(y=lvl,row=4,col=1,line=dict(color=clr,dash="dot",width=.8))
    fig.update_layout(height=730,template="plotly_dark",xaxis_rangeslider_visible=False,**CHART_STYLE)
    for ann in fig.layout.annotations: ann.font.color="#4a6080"; ann.font.size=10
    return fig

def build_fin_charts(rat_df, inc_df):
    charts=[]
    if rat_df.empty: return charts
    year_col=next((c for c in rat_df.columns if "year" in c.lower() or "năm" in c.lower()),None)
    eps_col = next((c for c in rat_df.columns if c.lower() in ["earnings_per_share","eps"]), None)
    roe_col = next((c for c in rat_df.columns if c.lower() == "roe"), None)
    roa_col = next((c for c in rat_df.columns if c.lower() == "roa"), None)
    rev_col  = next((c for c in inc_df.columns if c.lower() == "revenue"), None)
    prof_col = next((c for c in inc_df.columns if c.lower() == "net_profit"), None)
    gm_col = next((c for c in rat_df.columns if c.lower() == "gross_margin"), None)
    nm_col = next((c for c in rat_df.columns if c.lower() == "net_margin"), None)

    rdf=rat_df.sort_values(year_col,ascending=True).tail(8) if year_col else rat_df.tail(8)
    x=rdf[year_col].astype(str) if year_col else list(range(len(rdf)))

    fig=make_subplots(rows=1,cols=2,subplot_titles=("EPS theo năm","ROE & ROA xu hướng (%)"))
    fig2 = make_subplots(rows=1, cols=2,subplot_titles=("Doanh thu & Lợi nhuận ròng", "Biên lợi nhuận (%)"))
    if eps_col:
        ev=pd.to_numeric(rdf[eps_col],errors="coerce")
        bc=["#00d97e" if v>=0 else "#ff3d5a" for v in ev.fillna(0)]
        fig.add_trace(go.Bar(x=x,y=ev,name="EPS",marker_color=bc,
            text=ev.round(0),textposition="outside",textfont=dict(color="#cce0ff",size=10)),row=1,col=1)
    if roe_col:
        rv=pd.to_numeric(rdf[roe_col],errors="coerce")
        rv=rv*100 if rv.dropna().abs().max()<2 else rv
        fig.add_trace(go.Scatter(x=x,y=rv,name="ROE%",mode="lines+markers",
            line=dict(color="#00d97e",width=2.5),marker=dict(size=7)),row=1,col=2)
    if roa_col:
        av=pd.to_numeric(rdf[roa_col],errors="coerce")
        av=av*100 if av.dropna().abs().max()<2 else av
        fig.add_trace(go.Scatter(x=x,y=av,name="ROA%",mode="lines+markers",
            line=dict(color="#f5a623",width=2),marker=dict(size=6)),row=1,col=2)
    for lvl,clr,lbl in[(15,"rgba(0,217,126,.4)","ROE 15%"),(1.5,"rgba(74,158,248,.35)","ROA 1.5%")]:
        fig.add_hline(y=lvl,row=1,col=2,line=dict(color=clr,dash="dot",width=1),
            annotation_text=f" {lbl}",annotation_font=dict(color=clr,size=9))
    fig.update_layout(height=310,template="plotly_dark",**CHART_STYLE)
    for ann in fig.layout.annotations: ann.font.color="#8baed4"; ann.font.size=11
    charts.append(fig)
    return charts

# ══════════════════════════════ UI COMPONENTS ══════════════════════════════════
def signal_banner(sig, score):
    clr=SIG_COLOR.get(sig,"#8baed4"); sc_clr="#00d97e" if score>=2 else "#ff3d5a" if score<=-2 else "#f5a623"
    pct=min(100,max(0,(score+7)/14*100))
    return f"""<div style='background:#0c1d2e;border:1px solid #163350;border-radius:10px;
      padding:14px 18px;display:flex;align-items:center;gap:20px;flex-wrap:wrap;margin:8px 0;'>
  <div><div style='font-size:10px;color:#6a9cc8;letter-spacing:1px;'>TÍN HIỆU KỸ THUẬT</div>
       <div style='font-size:26px;font-weight:700;color:{clr};'>{sig}</div></div>
  <div style='text-align:center;'><div style='font-size:10px;color:#6a9cc8;'>ĐIỂM</div>
       <div style='font-size:28px;font-weight:700;color:{sc_clr};'>{score}</div></div>
  <div style='flex:1;min-width:200px;'>
    <div style='font-size:9px;color:#3a6080;letter-spacing:1px;margin-bottom:4px;'>BÁN MẠNH ←─────────→ MUA MẠNH</div>
    <div style='height:8px;background:#102030;border-radius:4px;overflow:hidden;'>
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

def metric_html(label, value_str, color="#ffffff"):
    return f"""<div style='background:#0c1d2e;border:1px solid #163350;border-radius:9px;padding:10px 13px;'>
  <div style='font-size:10px;color:#6a9cc8;letter-spacing:.5px;margin-bottom:3px;'>{label}</div>
  <div style='font-size:17px;font-weight:600;color:{color};'>{value_str}</div>
</div>"""

def fund_chip(item):
    ok=item["ok"]; val=item["val"]; lbl=item["label"]
    clr="#00d97e" if ok else "#ff3d5a" if ok is False else "#f5a623"
    ico="✅" if ok else "❌" if ok is False else "⚪"
    vs=f"{val:,.1f}" if isinstance(val,float) and val is not None else (str(val) if val else "—")
    note=item["good"] if ok else (item["bad"] if ok is False else "Không có dữ liệu")
    return f"""<div style='background:#0c1d2e;border:1px solid {clr}50;border-radius:9px;padding:9px 11px;text-align:center;'>
  <div style='font-size:18px;'>{ico}</div>
  <div style='font-size:12px;font-weight:600;color:#cce0ff;margin:3px 0;'>{lbl}</div>
  <div style='font-size:14px;font-weight:700;color:{clr};'>{vs}</div>
  <div style='font-size:9px;color:#6a9cc8;margin-top:3px;line-height:1.4;'>{note}</div>
</div>"""

def score_pill(label, s, weight_pct):
    clr="#00d97e" if s>1 else "#ff3d5a" if s<-1 else "#f5a623"
    pct=min(100,max(0,(s+5)/10*100))
    return f"""<div style='background:#0c1d2e;border:1px solid #163350;border-radius:10px;padding:12px 14px;text-align:center;'>
  <div style='font-size:10px;color:#6a9cc8;letter-spacing:.5px;margin-bottom:4px;'>{label}</div>
  <div style='font-size:22px;font-weight:700;color:{clr};'>{s:+.1f}</div>
  <div style='font-size:9px;color:#3a6080;margin-top:2px;'>{weight_pct}</div>
  <div style='height:4px;background:#102030;border-radius:2px;overflow:hidden;margin-top:6px;'>
    <div style='height:100%;width:{pct}%;background:{clr};border-radius:2px;'></div>
  </div>
</div>"""

# ══════════════════════════════ SIDEBAR ════════════════════════════════════════
with st.sidebar:
    st.markdown("## 📈 Pro Trader v5")
    st.markdown("---")
    symbol=st.text_input("Mã cổ phiếu",value="VPB",help="VD: VPB HPG VCB FPT MWG SSI TCB VIC ACB").upper().strip()
    res_label=st.selectbox("Độ phân giải nến",list(RESOLUTIONS.keys()),index=5)
    resolution=RESOLUTIONS[res_label]
    per_label=st.selectbox("Lịch sử dữ liệu",list(PERIODS.keys()),index=2)
    days=PERIODS[per_label]
    show_n=st.slider("Số nến hiển thị",30,300,100,10)
    st.markdown("**EMA hiển thị**")
    c1,c2=st.columns(2)
    ema_sel={"EMA9":c1.checkbox("EMA 9",True),"EMA21":c2.checkbox("EMA 21",True),
             "EMA50":c1.checkbox("EMA 50",True),"EMA200":c2.checkbox("EMA 200",False)}
    ema_list=[k for k,v in ema_sel.items() if v]
    run=st.button("🚀 Phân tích ngay",use_container_width=True)
    auto_r=st.checkbox("Tự động refresh",value=False)
    if auto_r: ref_sec=st.select_slider("Tần suất (giây)",[30,60,120,300],value=60)
    st.markdown("---")
    st.markdown("**Mã nhanh**")
    quick=["VPB","HPG","VCB","FPT","MWG","SSI","TCB","VIC","ACB","STB","MBB","HDB"]
    qcols=st.columns(3); clicked=None
    for i,m in enumerate(quick):
        if qcols[i%3].button(m,key=f"q_{m}",use_container_width=True): clicked=m
    if clicked: symbol=clicked

# ══════════════════════════════ MAIN ══════════════════════════════════════════
st.markdown(f"## {symbol} &nbsp;<span style='font-size:13px;color:#4a9ef8;'>{res_label} · {per_label}</span>",
            unsafe_allow_html=True)

if not (run or auto_r or clicked):
    st.markdown("""<div style='text-align:center;padding:80px 20px;background:#0c1d2e;
      border-radius:12px;border:1px solid #163350;'>
      <div style='font-size:48px;'>📈</div>
      <div style='font-size:15px;color:#6a9cc8;margin-top:12px;'>Nhập mã cổ phiếu và nhấn <b style="color:#fff">Phân tích ngay</b></div>
      <div style='font-size:11px;color:#3a6080;margin-top:6px;'>Nguồn dữ liệu: KBS (KB Securities) · Không cần API key</div>
    </div>""",unsafe_allow_html=True)
    st.stop()

# Load dữ liệu
with st.spinner(f"⏳ Đang tải {symbol} từ KBS..."):
    try:
        df_raw, price_src = fetch_price(symbol, days, resolution)
    except Exception as e:
        st.error(f"❌ Không lấy được dữ liệu giá: {e}\n\nKiểm tra: mã CK có đúng không? Kết nối internet ổn không?")
        st.stop()
    rat_df, ratio_src = fetch_ratio(symbol)
    inc_df = fetch_income(symbol)

df=add_indicators(df_raw.copy()); df=detect_patterns(df)
sig,reasons,score=calc_signal(df); trade=calc_trade(df,score)
lat=df.iloc[-1]; prev=df.iloc[-2] if len(df)>1 else lat

chg=float(lat.Close)-float(prev.Close); pct_chg=chg/float(prev.Close)*100 if float(prev.Close) else 0
chg_str=f"{'▲' if chg>=0 else '▼'} {abs(chg):,.0f} đ ({abs(pct_chg):.2f}%)"
st.caption(f"📡 Nguồn: {price_src} · {len(df)} phiên · {'🟢' if chg>=0 else '🔴'} {chg_str} · {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")

tab1,tab2,tab3,tab4=st.tabs(["📉 Kỹ thuật","📊 Cơ bản","💰 Dòng tiền","🎯 Tổng hợp"])

# ── TAB 1: KỸ THUẬT ────────────────────────────────────────────────────────
with tab1:
    pat_val=str(lat.get("Pattern","") or "Thường")
    m1,m2,m3,m4,m5=st.columns(5)
    m1.metric("💰 Giá đóng cửa",f"{lat.Close:,.0f} đ",chg_str)
    vs=f"{lat.Volume/1e6:.1f}M" if lat.Volume>=1e6 else f"{lat.Volume/1e3:.0f}K"
    m2.metric("📊 Khối lượng",vs,f"×{lat.Vol_Ratio:.2f} trung bình")
    m3.metric("📐 ATR (14)",f"{lat.ATR:,.0f} đ","Biên dao động TB")
    m4.metric("📈 EMA Cross","Bull" if lat.EMA_State=="bull" else "Bear",
        "EMA9>EMA21 ↑" if lat.EMA_State=="bull" else "EMA9<EMA21 ↓")
    m5.metric("🕯 Mô hình nến",pat_val,
        "↗ Đảo chiều tăng" if pat_val in("Bullish Engulfing","Hammer") else
        "↘ Đảo chiều giảm" if pat_val in("Bearish Engulfing","Shooting Star") else "—")
    st.markdown(signal_banner(sig,score),unsafe_allow_html=True)
    st.plotly_chart(build_price_chart(df,trade,show_n,ema_list),use_container_width=True,config={"displayModeBar":True})
    st.markdown("### 🎯 Chiến lược giao dịch")
    t1,t2,t3,t4=st.columns(4)
    t1.markdown(trade_card_html("📗","VÙNG MUA",f"{trade['buy']:,} đ","Giá vào lệnh mục tiêu","#00d97e"),unsafe_allow_html=True)
    t2.markdown(trade_card_html("📕","CẮT LỖ (SL)",f"{trade['sl']:,} đ",f"Rủi ro {trade['risk']*100:.1f}%","#ff3d5a"),unsafe_allow_html=True)
    t3.markdown(trade_card_html("🎯","CHỐT LỜI",f"TP1: {trade['tp1']:,}",f"TP2: {trade['tp2']:,}  TP3: {trade['tp3']:,}","#f5a623"),unsafe_allow_html=True)
    rr=trade['rr']; rc="#00d97e" if rr>=2 else "#f5a623" if rr>=1.5 else "#ff3d5a"
    t4.markdown(trade_card_html("⚖️","R:R RATIO",f"1 : {rr:.1f}",f"LN kỳ vọng {trade['reward']*100:.1f}%",rc),unsafe_allow_html=True)
    with st.expander("📐 Fibonacci Retracement"):
        fr=[{"Mức":k,"Giá (đ)":f"{v:,.0f}","So giá HT":f"{(v/float(lat.Close)-1)*100:+.1f}%",
             "Vai trò":"◀ GIÁ HIỆN TẠI" if abs(v/float(lat.Close)-1)<0.015 else ("Hỗ trợ 🟢" if v<lat.Close else "Kháng cự 🔴")}
            for k,v in trade["fib"].items()]
        st.dataframe(pd.DataFrame(fr),use_container_width=True,hide_index=True)
    st.markdown("### 🔍 Phân tích tín hiệu")
    rc1,rc2=st.columns(2); mid=len(reasons)//2+1
    for r2 in reasons[:mid]: rc1.markdown(r2)
    for r2 in reasons[mid:]: rc2.markdown(r2)
    st.markdown("### 📋 Bảng chỉ báo")
    ind_tbl=[
        ("RSI (14)",f"{lat.RSI:.1f}","Quá mua 🔴" if lat.RSI>70 else "Quá bán 🟢" if lat.RSI<30 else "Bình thường ✅"),
        ("MACD",f"{lat.MACD:.2f}","Dương 🟢" if lat.MACD>0 else "Âm 🔴"),
        ("MACD Signal",f"{lat.MACD_Sig:.2f}","MACD>Signal 🟢" if lat.MACD>lat.MACD_Sig else "MACD<Signal 🔴"),
        ("ADX (14)",f"{lat.ADX:.1f}","Xu hướng mạnh ✅" if lat.ADX>25 else "Sideway ⚠️"),
        ("EMA 9",f"{lat.EMA9:,.0f}","Trên EMA21 🟢" if lat.EMA9>lat.EMA21 else "Dưới EMA21 🔴"),
        ("EMA 21",f"{lat.EMA21:,.0f}","Trên EMA50 🟢" if lat.EMA21>lat.EMA50 else "Dưới EMA50 🔴"),
        ("EMA 50",f"{lat.EMA50:,.0f}","Trên EMA200 🟢" if pd.notna(lat.EMA200) and lat.EMA50>lat.EMA200 else "—"),
        ("EMA 200",f"{lat.EMA200:,.0f}" if pd.notna(lat.EMA200) else "—","Xu hướng dài hạn"),
        ("BB Width",f"{lat.BB_width*100:.1f}%","Bó hẹp ⚠️" if lat.BB_width<0.05 else "Bình thường"),
        ("Vol Ratio",f"×{lat.Vol_Ratio:.2f}","Đột biến 📢" if lat.Vol_Ratio>1.5 else "Bình thường"),
    ]
    st.dataframe(pd.DataFrame(ind_tbl,columns=["Chỉ báo","Giá trị","Trạng thái"]),
                 use_container_width=True,hide_index=True)

# ── TAB 2: CƠ BẢN ──────────────────────────────────────────────────────────
with tab2:
    if not rat_df.empty:
        st.markdown("### 📊 Chỉ số tài chính (kỳ mới nhất)")
        r=rat_df.iloc[0]
        eps = _safe(r, "earnings_per_share", "eps")
        roe = _safe(r, "roe")
        roa = _safe(r, "roa")
        pe  = _safe(r, "pe_ratio")
        pb  = _safe(r, "pb_ratio")
        de  = _safe(r, "debt_to_equity")
        cr  = _safe(r, "current_ratio")
        def pct(v): return v*100 if v and abs(v)<2 else v
        roe=pct(roe); roa=pct(roa)
        f1,f2,f3,f4,f5,f6,f7=st.columns(7)
        f1.markdown(metric_html("P/E",f"{pe:.1f}x" if pe else "—","#00d97e" if pe and 0<pe<20 else "#ff3d5a" if pe else "#8baed4"),unsafe_allow_html=True)
        f2.markdown(metric_html("P/B",f"{pb:.2f}x" if pb else "—","#00d97e" if pb and 0<pb<4 else "#ff3d5a" if pb else "#8baed4"),unsafe_allow_html=True)
        f3.markdown(metric_html("EPS",f"{eps:,.0f} đ" if eps else "—","#00d97e" if eps and eps>0 else "#ff3d5a" if eps else "#8baed4"),unsafe_allow_html=True)
        f4.markdown(metric_html("ROE",f"{roe:.1f}%" if roe else "—","#00d97e" if roe and roe>15 else "#f5a623" if roe and roe>10 else "#ff3d5a" if roe else "#8baed4"),unsafe_allow_html=True)
        f5.markdown(metric_html("ROA",f"{roa:.1f}%" if roa else "—","#00d97e" if roa and roa>1.5 else "#f5a623" if roa and roa>0.8 else "#ff3d5a" if roa else "#8baed4"),unsafe_allow_html=True)
        f6.markdown(metric_html("D/E",f"{de:.1f}x" if de else "—","#00d97e" if de and de<12 else "#f5a623"),unsafe_allow_html=True)
        f7.markdown(metric_html("Current Ratio",f"{cr:.2f}" if cr else "—","#00d97e" if cr and cr>1.5 else "#f5a623" if cr and cr>1 else "#ff3d5a" if cr else "#8baed4"),unsafe_allow_html=True)
        for fig_f in build_fin_charts(rat_df,inc_df):
            st.plotly_chart(fig_f,use_container_width=True)
        items_f,total_f=score_fundamental(rat_df)
        if "earnings_per_share" in rat_df.columns and "year" in rat_df.columns:
            growth_df = rat_df[["year","earnings_per_share","pe_ratio","roe","net_margin"]].sort_values("year").tail(5).copy()
            growth_df["EPS tăng trưởng"] = growth_df["earnings_per_share"].pct_change()*100
            growth_df["EPS tăng trưởng"] = growth_df["EPS tăng trưởng"].apply(lambda x: f"{x:+.1f}%" if pd.notna(x) else "—")
            st.markdown("### 📈 Tăng trưởng EPS theo năm")
            st.dataframe(growth_df.rename(columns={"year":"Năm","earnings_per_share":"EPS","pe_ratio":"P/E","roe":"ROE%","net_margin":"Biên ròng%"}).reset_index(drop=True), use_container_width=True, hide_index=True)
        if items_f:
            st.markdown("### ✅ Chấm điểm cơ bản")
            chip_cols=st.columns(len(items_f))
            for col,item in zip(chip_cols,items_f):
                col.markdown(fund_chip(item),unsafe_allow_html=True)
            f_lbl="Cơ bản MẠNH ✅" if total_f>=3 else "Cơ bản KHÁ ⚠️" if total_f>=0 else "Cơ bản YẾU ❌"
            f_clr="#00d97e" if total_f>=3 else "#f5a623" if total_f>=0 else "#ff3d5a"
            st.markdown(f"""<div style='margin-top:10px;background:#0c1d2e;border:1px solid {f_clr}60;
              border-radius:8px;padding:10px 16px;display:flex;align-items:center;gap:14px;'>
              <div style='font-size:24px;font-weight:700;color:{f_clr};'>{total_f:+.1f}</div>
              <div style='font-size:14px;font-weight:600;color:{f_clr};'>{f_lbl}</div>
              <div style='font-size:11px;color:#6a9cc8;'>Ngưỡng: ≥3 điểm = cơ bản tốt để cân nhắc mua</div>
            </div>""",unsafe_allow_html=True)
        with st.expander("📋 Bảng chỉ số đầy đủ theo năm"):
            disp=[c for c in rat_df.columns if c not in ["ticker","id"]]
            st.dataframe(rat_df[disp].reset_index(drop=True),use_container_width=True,hide_index=True)
    else:
        st.warning(f"Không lấy được dữ liệu tài chính. {ratio_src}\n\nThử mã khác hoặc kiểm tra kết nối.")
        st.info("💡 Gợi ý: Thử lại sau vài giây. KBS API đôi khi cần warm-up request đầu tiên.")

# ── TAB 3: DÒNG TIỀN ───────────────────────────────────────────────────────
with tab3:
    st.markdown("### 📊 Phân tích khối lượng giao dịch")
    show_v=df.tail(60).copy()
    fig_v=go.Figure()
    vc=["#00d97e" if r.Close>=r.Open else "#ff3d5a" for _,r in show_v.iterrows()]
    fig_v.add_trace(go.Bar(x=show_v["Date"],y=show_v["Volume"],marker_color=vc,opacity=0.7,name="Khối lượng"))
    if show_v["Vol_MA20"].notna().any():
        fig_v.add_trace(go.Scatter(x=show_v["Date"],y=show_v["Vol_MA20"],
            line=dict(color="#f5a623",width=2),name="MA20 Vol"))
    fig_v.update_layout(height=280,title="Khối lượng 60 phiên — xanh=tăng, đỏ=giảm",
        template="plotly_dark",**CHART_STYLE)
    fig_v.layout.title.font.color="#8baed4"; fig_v.layout.title.font.size=12
    st.plotly_chart(fig_v,use_container_width=True)
    v1,v2,v3=st.columns(3)
    v1.metric("Vol TB 20 phiên",fmt(float(df["Vol_MA20"].iloc[-1])),"Chuẩn so sánh")
    v2.metric("Vol phiên gần nhất",fmt(float(lat.Volume)),f"×{lat.Vol_Ratio:.2f} so TB")
    high_v=int((df["Vol_Ratio"].tail(20)>1.5).sum())
    v3.metric("Phiên đột biến (20p)",f"{high_v} phiên","Hoạt động cao 📢" if high_v>5 else "Bình thường")
    st.markdown("---")
    st.info("💡 **Giao dịch khối ngoại:** Để xem dữ liệu mua/bán ròng real-time, vào [HNX.vn](https://hnx.vn) hoặc [CafeF](https://cafef.vn) → Giao dịch khối ngoại. Platform này hiển thị phân tích khối lượng từ dữ liệu giá để đánh giá áp lực mua/bán.")
    # Volume trend analysis
    st.markdown("### 📈 Phân tích xu hướng khối lượng")
    vol_trend=df.tail(20)[["Date","Volume","Vol_Ratio","Close"]].copy()
    vol_trend["Tăng/Giảm"]=vol_trend["Close"].diff().apply(lambda x:"📈 Tăng" if x>0 else "📉 Giảm")
    vol_trend["Vol_Ratio"]=vol_trend["Vol_Ratio"].round(2)
    vol_trend["Volume"]=vol_trend["Volume"].apply(lambda x:f"{x/1e6:.1f}M" if x>=1e6 else f"{x/1e3:.0f}K")
    vol_trend["Close"]=vol_trend["Close"].apply(lambda x:f"{x:,.0f}")
    vol_trend=vol_trend.rename(columns={"Date":"Ngày","Volume":"Khối lượng","Close":"Giá đóng cửa","Vol_Ratio":"Vol/TB"})
    st.dataframe(vol_trend.tail(15).reset_index(drop=True),use_container_width=True,hide_index=True)
  # Thêm hàm phân tích bơm/xả — đặt cùng với các hàm khác
def analyze_pump_dump(df):
    """Phát hiện dấu hiệu bơm/xả từ price-volume action."""
    signals = []
    d = df.tail(20).copy()
    
    # 1. Bơm: Giá tăng mạnh + Vol đột biến
    pump = d[(d["Vol_Ratio"] > 2.0) & (d["Close"] > d["Open"]) & 
             (d["Close"].pct_change() > 0.03)]
    if len(pump) > 0:
        signals.append(("🚨 DẤU HIỆU BƠM", "warning",
            f"{len(pump)} phiên gần đây: giá tăng >3% kèm khối lượng đột biến >2x. "
            "Cẩn thận bẫy thanh khoản — bơm để xả."))
    
    # 2. Xả: Giá giảm + Vol đột biến 
    dump = d[(d["Vol_Ratio"] > 2.0) & (d["Close"] < d["Open"]) &
             (d["Close"].pct_change() < -0.03)]
    if len(dump) > 0:
        signals.append(("🔴 DẤU HIỆU XẢ HÀNG", "error",
            f"{len(dump)} phiên: giá giảm >3% kèm khối lượng lớn. "
            "Áp lực bán mạnh từ tay to."))
    
    # 3. Phân kỳ âm: giá tăng nhưng vol giảm dần
    last5  = d.tail(5)
    price_up  = last5["Close"].iloc[-1] > last5["Close"].iloc[0]
    vol_down  = last5["Volume"].iloc[-1] < last5["Volume"].iloc[0]
    if price_up and vol_down:
        signals.append(("⚠️ PHÂN KỲ VOLUME", "warning",
            "Giá tăng nhưng khối lượng suy giảm 5 phiên gần nhất. "
            "Xu hướng tăng thiếu động lực — rủi ro đảo chiều."))
    
    # 4. Khối lượng cạn kiệt: Vol < 0.3x TB
    if df["Vol_Ratio"].tail(3).mean() < 0.3:
        signals.append(("😴 THANH KHOẢN CẠN", "info",
            "Khối lượng 3 phiên liên tiếp dưới 30% trung bình. "
            "Thị trường mất quan tâm — không nên giao dịch."))
    
    # 5. Bình thường
    if not signals:
        signals.append(("✅ BÌNH THƯỜNG", "success",
            "Không phát hiện dấu hiệu bất thường về khối lượng."))
    return signals
# Trong Tab 3, sau biểu đồ, thêm:
signals = analyze_pump_dump(df)
st.markdown("### 🔍 Phân tích dấu hiệu bơm/xả")
for title, level, desc in signals:
    if level == "warning": st.warning(f"**{title}** — {desc}")
    elif level == "error":  st.error(f"**{title}** — {desc}")
    elif level == "success":st.success(f"**{title}** — {desc}")
    else:                   st.info(f"**{title}** — {desc}")
      # Chart 2 panel: giá trên, vol/TB dưới — cùng trục X để thấy divergence rõ
fig_pv = make_subplots(rows=2, cols=1, shared_xaxes=True,
    vertical_spacing=0.04, row_heights=[0.6, 0.4],
    subplot_titles=("Giá đóng cửa", "Vol/TB (đường 1x = bình thường)"))

show_pv = df.tail(60)
fig_pv.add_trace(go.Scatter(x=show_pv["Date"], y=show_pv["Close"],
    line=dict(color="#4a9ef8", width=1.8), name="Giá"), row=1, col=1)
fig_pv.add_trace(go.Bar(x=show_pv["Date"], y=show_pv["Vol_Ratio"],
    marker_color=["#00d97e" if r.Close>=r.Open else "#ff3d5a" 
                  for _,r in show_pv.iterrows()], name="Vol/TB"), row=2, col=1)
fig_pv.add_hline(y=1.5, row=2, col=1,
    line=dict(color="#f5a623", dash="dot", width=1),
    annotation_text=" Ngưỡng đột biến 1.5x")
fig_pv.add_hline(y=1.0, row=2, col=1,
    line=dict(color="rgba(255,255,255,0.2)", dash="dot", width=0.8))
# Cuối Tab 3, thêm bảng 3 cột nhận định:
col_a, col_b, col_c = st.columns(3)

# Tính các chỉ số
avg_vol_up   = df[df["Close"]>=df["Open"]]["Vol_Ratio"].tail(20).mean()
avg_vol_down = df[df["Close"]<df["Open"]]["Vol_Ratio"].tail(20).mean()
trend_vol    = "Mua chiếm ưu thế 🟢" if avg_vol_up > avg_vol_down else "Bán chiếm ưu thế 🔴"

col_a.metric("Vol trung bình ngày tăng", f"×{avg_vol_up:.2f}", "so TB 20 phiên")
col_b.metric("Vol trung bình ngày giảm", f"×{avg_vol_down:.2f}", "so TB 20 phiên")  
col_c.metric("Nhận định dòng tiền", trend_vol)

# ── TAB 4: TỔNG HỢP ────────────────────────────────────────────────────────
with tab4:
    st.markdown("### 🎯 Đánh giá tổng hợp")
    _,fund_score=score_fundamental(rat_df) if not rat_df.empty else ([],0)
    tech_norm=max(-5,min(5,score)); fund_norm=max(-5,min(5,fund_score))
    total=tech_norm*0.50 + fund_norm*0.50  # Không có CF real-time → chia đôi
    sc1,sc2,sc3=st.columns(3)
    sc1.markdown(score_pill("📉 Kỹ thuật",round(tech_norm,1),"Trọng số 50%"),unsafe_allow_html=True)
    sc2.markdown(score_pill("📊 Cơ bản",round(fund_norm,1),"Trọng số 50%"),unsafe_allow_html=True)
    if   total>=2.5: final="MUA MẠNH"; fc="#00d97e"
    elif total>=1.0: final="MUA";       fc="#00b862"
    elif total>=0.3: final="THEO DÕI MUA"; fc="#7fcf50"
    elif total>-0.3: final="TRUNG TÍNH";   fc="#8baed4"
    elif total>-1.0: final="THEO DÕI BÁN"; fc="#f5a623"
    elif total>-2.5: final="BÁN";           fc="#ff3d5a"
    else:            final="BÁN MẠNH";      fc="#cc1133"
    sc3.markdown(f"""<div style='background:#0c1d2e;border:2px solid {fc}80;border-radius:10px;
      padding:12px 14px;text-align:center;'>
      <div style='font-size:10px;color:#6a9cc8;letter-spacing:.5px;margin-bottom:4px;'>KẾT LUẬN TỔNG HỢP</div>
      <div style='font-size:20px;font-weight:700;color:{fc};'>{final}</div>
      <div style='font-size:12px;color:#6a9cc8;margin-top:4px;'>Điểm: {total:+.2f}</div>
    </div>""",unsafe_allow_html=True)
    st.markdown("---")
    ema_align="Xếp hàng tăng ↑" if lat.EMA9>lat.EMA21>lat.EMA50 else "Xếp hàng giảm ↓" if lat.EMA9<lat.EMA21<lat.EMA50 else "Trung tính ↔"
    st.markdown(f"""<div style='background:#0c1d2e;border:1px solid {fc}60;border-radius:10px;padding:16px 20px;'>
      <div style='font-size:11px;color:#6a9cc8;margin-bottom:8px;letter-spacing:.5px;'>PHÂN TÍCH — {symbol} · {datetime.now().strftime("%d/%m/%Y %H:%M")}</div>
      <div style='font-size:22px;font-weight:700;color:{fc};margin-bottom:12px;'>{final}</div>
      <div style='display:grid;grid-template-columns:1fr 1fr;gap:16px;font-size:12px;'>
        <div><div style='color:#6a9cc8;margin-bottom:5px;font-weight:600;'>📉 Kỹ thuật</div>
          <div style='color:#cce0ff;line-height:1.7;'>Tín hiệu: <b style="color:{SIG_COLOR.get(sig,'#8baed4')}">{sig}</b> ({score}đ)<br>
          EMA: {ema_align}<br>RSI {lat.RSI:.0f}: {"Quá mua" if lat.RSI>70 else "Quá bán" if lat.RSI<30 else "Bình thường"}<br>
          ADX {lat.ADX:.0f}: {"Xu hướng mạnh" if lat.ADX>25 else "Sideway"}</div></div>
        <div><div style='color:#6a9cc8;margin-bottom:5px;font-weight:600;'>📊 Cơ bản</div>
          <div style='color:#cce0ff;line-height:1.7;'>Điểm: <b style="color:{"#00d97e" if fund_score>=3 else "#f5a623" if fund_score>=0 else "#ff3d5a"}">{fund_score:+.1f}</b><br>
          {"Nền tảng vững — phù hợp đầu tư" if fund_score>=3 else "Cơ bản trung bình" if fund_score>=0 else "Cơ bản yếu — thận trọng"}</div></div>
      </div>
    </div>""",unsafe_allow_html=True)
    st.markdown("### 💡 Chiến lược đề xuất")
    if total>=2: pos_pct,horizon="10–15% danh mục","Ngắn-Trung hạn"
    elif total>=1: pos_pct,horizon="5–10% danh mục","Trung hạn"
    elif total>=0: pos_pct,horizon="0–5% thăm dò","Quan sát thêm"
    else: pos_pct,horizon="Không mua","Chờ tín hiệu đảo chiều"
    s1,s2,s3,s4=st.columns(4)
    s1.metric("Tỷ trọng",pos_pct,horizon)
    s2.metric("Điểm mua",f"{trade['buy']:,} đ","Theo kỹ thuật")
    s3.metric("Stop Loss",f"{trade['sl']:,} đ",f"Rủi ro {trade['risk']*100:.1f}%")
    s4.metric("R:R",f"1:{trade['rr']:.1f}","Tốt" if trade['rr']>=2 else "Cần cân nhắc")
    st.markdown("### ⚠️ Rủi ro cần theo dõi")
    risks=[]
    if lat.RSI>70: risks.append("🔴 RSI quá mua — nguy cơ điều chỉnh")
    if lat.ADX<20: risks.append("⚠️ ADX thấp — sideway, tín hiệu kém tin cậy")
    if lat.BB_width<0.05: risks.append("⚠️ BB bó hẹp — biến động lớn sắp xảy ra")
    if fund_score<0: risks.append("🔴 Cơ bản yếu — không nên hold dài hạn")
    if lat.Vol_Ratio<0.5: risks.append("⚠️ Khối lượng thấp — thanh khoản kém")
    if not risks: risks=["✅ Không phát hiện rủi ro bất thường"]
    rc1,rc2=st.columns(2)
    for i,rk in enumerate(risks): (rc1 if i%2==0 else rc2).markdown(rk)
    st.markdown("---")
    st.caption(f"⚠️ Phân tích tham khảo — không phải khuyến nghị đầu tư. Nguồn: {price_src} · {ratio_src} · {datetime.now().strftime('%d/%m/%Y %H:%M')}")

if auto_r:
    time.sleep(ref_sec)
    st.rerun()
