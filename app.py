"""
IRISSS v6.0 — Full Professional Edition
6 tabs: Kỹ thuật | Cơ bản | Dòng tiền | So sánh ngành | Quét mã | Tổng hợp
"""
import warnings; warnings.filterwarnings("ignore")
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import math, time, re, json, urllib.request

st.set_page_config(layout="wide", page_title="Pro Trader v6", page_icon="📈",
                   initial_sidebar_state="expanded")

# ══════════════════════════════ CSS ═══════════════════════════════════════════
st.markdown("""<style>
[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:#07121e!important}
[data-testid="stHeader"]{background:#07121e!important}
[data-testid="stSidebar"]{background:#0c1d2e!important;border-right:1px solid #163350}
section[data-testid="stSidebar"] *{color:#cce0ff!important;font-size:14px!important}
.stTabs [data-baseweb="tab-list"]{background:#0c1d2e;border-radius:10px;padding:5px;gap:4px}
.stTabs [data-baseweb="tab"]{background:transparent;color:#6a9cc8;border-radius:7px;
  padding:9px 18px;font-size:14px;font-weight:500;border:none}
.stTabs [aria-selected="true"]{background:#163350!important;color:#fff!important;font-weight:600!important}
[data-testid="metric-container"]{background:#0c1d2e!important;border:1px solid #163350!important;
  border-radius:12px!important;padding:14px 18px!important}
[data-testid="stMetricLabel"] p{color:#6a9cc8!important;font-size:12px!important;font-weight:500!important}
[data-testid="stMetricValue"]{color:#fff!important;font-size:24px!important;font-weight:700!important}
[data-testid="stMetricDelta"]{font-size:13px!important}
[data-testid="stButton"] button{background:#163350!important;color:#cce0ff!important;
  border:1px solid #2a5a8a!important;border-radius:8px!important;font-size:13px!important;padding:6px 14px!important}
[data-testid="stButton"] button:hover{background:#1e4a70!important}
.stDataFrame{border:1px solid #163350!important;border-radius:10px!important}
.stDataFrame td,.stDataFrame th{font-size:13px!important}
div[data-testid="stExpander"]{background:#0c1d2e!important;border:1px solid #163350!important;border-radius:10px!important}
hr{border-color:#163350!important}
p,span,label{color:#cce0ff;font-size:14px}
h1{color:#fff;font-size:26px!important;font-weight:700!important}
h2{color:#fff;font-size:20px!important;font-weight:600!important}
h3{color:#fff;font-size:17px!important;font-weight:600!important}
.stAlert > div{background:#0c1d2e!important;border:1px solid #163350!important;font-size:14px!important}
</style>""", unsafe_allow_html=True)

# ══════════════════════════════ CONSTANTS ══════════════════════════════════════
RESOLUTIONS = {"Ngày":"1D","Tuần":"1W","Tháng":"1M","1 giờ":"1H","15 phút":"15m","5 phút":"5m"}
PERIODS     = {"1 tháng":30,"3 tháng":90,"6 tháng":180,"1 năm":365,"2 năm":730}
SIG_COLOR   = {"MUA MẠNH":"#00d97e","MUA":"#00b862","THEO DÕI MUA":"#7fcf50",
               "TRUNG TÍNH":"#8baed4","THEO DÕI BÁN":"#f5a623","BÁN":"#ff3d5a","BÁN MẠNH":"#cc1133"}
CHART_STYLE = dict(
    paper_bgcolor="#07121e", plot_bgcolor="#07121e",
    font=dict(family="monospace", color="#8baed4", size=11),
    legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11, color="#8baed4")),
    margin=dict(l=10, r=60, t=30, b=10),
    xaxis=dict(showgrid=True, gridcolor="#102030", gridwidth=0.5, tickfont=dict(color="#4a6080",size=10)),
    yaxis=dict(showgrid=True, gridcolor="#102030", gridwidth=0.5, tickfont=dict(color="#4a6080",size=10)),
)

# Ngành và mã cùng ngành
SECTOR_PEERS = {
    "Ngân hàng":   ["VCB","TCB","MBB","ACB","VPB","BID","CTG","STB","HDB","TPB","MSB","OCB","SHB"],
    "Bất động sản":["VIC","VHM","NVL","DXG","KDH","PDR","DIG","BCM","HDG","CEO"],
    "Thép & KLB":  ["HPG","NKG","HSG","TIS","VGS","POM"],
    "Chứng khoán": ["SSI","VND","HCM","MBS","VCI","FTS","BSI","CTS"],
    "Bán lẻ":      ["MWG","FRT","PNJ","DGW"],
    "Công nghệ":   ["FPT","CMG","ELC","VGI"],
    "Dầu khí":     ["GAS","PLX","PVD","PVS","BSR"],
    "Dược":        ["DHG","IMP","DMC","TRA","DBD"],
    "Tiêu dùng":   ["SAB","BHN","VNM","MCH","MSN","QNS"],
    "Điện":        ["REE","PC1","GEG","PGV","NT2"],
}

SECTOR_PE_MEDIAN = {
    "Ngân hàng":8.5,"Bất động sản":15.0,"Thép & KLB":10.0,
    "Chứng khoán":12.0,"Bán lẻ":20.0,"Công nghệ":18.0,
    "Dầu khí":9.0,"Dược":16.0,"Tiêu dùng":22.0,"Điện":14.0,
}

_META = ['item','item_id','item_en','unit','levels','row_number']

# ══════════════════════════════ DATA LAYER ═════════════════════════════════════
@st.cache_data(ttl=60, show_spinner=False)
def fetch_price(sym, days, interval="1D"):
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        from vnstock import Quote
        df = Quote(symbol=sym, source="KBS").history(start=start, end=end, interval=interval)
        if df.empty: raise ValueError("empty")
        df = df.rename(columns={"time":"Date","open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
        for c in ["Open","High","Low","Close"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
            if df[c].median() < 1000: df[c] *= 1000
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0).astype(int)
        df["Date"] = pd.to_datetime(df["Date"])
        return df.sort_values("Date").reset_index(drop=True)[["Date","Open","High","Low","Close","Volume"]]
    except:
        try:
            import yfinance as yf
            df = yf.download(f"{sym}.VN", start=start, end=end, progress=False, auto_adjust=True)
            if df.empty: raise
            df = df.reset_index()
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df = df.rename(columns={"Date":"Date","Open":"Open","High":"High","Low":"Low","Close":"Close","Volume":"Volume"})
            return df.sort_values("Date").reset_index(drop=True)[["Date","Open","High","Low","Close","Volume"]]
        except Exception as e:
            raise RuntimeError(str(e))

@st.cache_data(ttl=300, show_spinner=False)
def fetch_ratio(sym):
    try:
        from vnstock import Finance
        df = Finance(symbol=sym, source="KBS").ratio(period="year")
        return df if df is not None and not df.empty else pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_income(sym):
    try:
        from vnstock import Finance
        df = Finance(symbol=sym, source="KBS").income_statement(period="year")
        return df if df is not None and not df.empty else pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_balance(sym):
    try:
        from vnstock import Finance
        df = Finance(symbol=sym, source="KBS").balance_sheet(period="year")
        return df if df is not None and not df.empty else pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_cashflow(sym):
    try:
        from vnstock import Finance
        df = Finance(symbol=sym, source="KBS").cash_flow(period="year")
        return df if df is not None and not df.empty else pd.DataFrame()
    except: return pd.DataFrame()
@st.cache_data(ttl=300, show_spinner=False)
def fetch_tcbs_financial(sym):
    """TCBS financial data làm source thứ 2."""
    results = {}
    base = "https://apipubaws.tcbs.com.vn"
    hdrs = {"User-Agent":"Mozilla/5.0","Accept":"application/json",
            "Referer":"https://tcinvest.tcbs.com.vn/","Origin":"https://tcinvest.tcbs.com.vn"}
    try:
        import requests as _req
        r = _req.get(f"{base}/tcanalysis/v1/finance/{sym}/financialratio",
                     params={"quarterly":0,"page":0,"size":8}, headers=hdrs, timeout=10)
        if r.status_code == 200:
            data = r.json()
            rows = data if isinstance(data, list) else data.get("listFinancialRatio", data.get("data",[]))
            if rows: results['ratio'] = pd.DataFrame(rows)
    except: pass
    try:
        import requests as _req
        r = _req.get(f"{base}/tcanalysis/v1/ticker/{sym}/overview", headers=hdrs, timeout=8)
        if r.status_code == 200: results['overview'] = r.json()
    except: pass
    try:
        import requests as _req
        r = _req.get(f"{base}/tcanalysis/v1/ticker/{sym}/priceTarget", headers=hdrs, timeout=8)
        if r.status_code == 200:
            data = r.json()
            rows = data if isinstance(data, list) else data.get("data",[])
            if rows: results['price_target'] = rows
    except: pass
    return results

@st.cache_data(ttl=180, show_spinner=False)
def fetch_news_ai(sym, sector=""):
    """Lấy tin tức qua Claude API + web search."""
    prompt = (
        f"Search for latest news about {sym} stock on Vietnam stock exchange (HOSE/HNX). "
        f"Find news from last 7 days: earnings results, analyst ratings, major events, "
        f"regulatory news, business developments. Sector: {sector}. "
        f"Return ONLY valid JSON, no explanation: "
        f'{{"news":[{{"date":"2025-05-28","title":"Tieu de tin","summary":"Tom tat ngan 1-2 cau","sentiment":"positive"}}],'
        f'"analyst_consensus":{{"action":"Buy","target_price":25000,"num_analysts":3}},'
        f'"key_events":["Su kien 1","Su kien 2"]}}'
    )
    try:
        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 2000,
            "tools": [{"type":"web_search_20250305","name":"web_search"}],
            "messages": [{"role":"user","content": prompt}]
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={"Content-Type":"application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read())
        text = " ".join(
            c.get("text","") for c in result.get("content",[])
            if c.get("type") == "text"
        )
        # Extract JSON
        candidates = []
        depth = 0; start = -1
        for i, ch in enumerate(text):
            if ch == '{':
                if depth == 0: start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    candidates.append(text[start:i+1])
        candidates.sort(key=len, reverse=True)
        for c in candidates:
            try:
                data = json.loads(c)
                if "news" in data: return data
            except: pass
    except: pass
    return {"news":[], "analyst_consensus":{}, "key_events":[]}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_tcbs_news(sym):
    """Tin tức từ TCBS activity feed."""
    try:
        import requests as _req
        hdrs = {"User-Agent":"Mozilla/5.0","Accept":"application/json",
                "Referer":"https://tcinvest.tcbs.com.vn/","Origin":"https://tcinvest.tcbs.com.vn"}
        r = _req.get(
            f"https://apipubaws.tcbs.com.vn/tcanalysis/v1/ticker/{sym}/activity-news",
            params={"page":0,"size":15}, headers=hdrs, timeout=10)
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data,list) else data.get("listActivityNews", data.get("data",[]))
            return items[:15]
    except: pass
    return []



# ══════════════════════════════ FIELD HELPERS ══════════════════════════════════
def ycols(df):
    if df is None or df.empty: return []
    return sorted([c for c in df.columns if c not in _META and bool(re.search(r'\d{4}', str(c)))])

_AL = {
    'pe_ratio':           ['pe_ratio','p_e'],
    'pb_ratio':           ['pb_ratio','p_b'],
    'roe':                ['roe'],
    'roa':                ['roa'],
    'earnings_per_share': ['earnings_per_share','eps','basic_eps'],
    'debt_to_equity':     ['debt_to_equity','debt_equity'],
    'current_ratio':      ['current_ratio'],
    'gross_margin':       ['gross_margin','gross_profit_margin'],
    'net_margin':         ['net_margin','net_profit_margin'],
    'equity_total_assets':['equity_total_assets','equity_deposits_from_custom'],
    'ldr':                ['outstanding_loans_customer_','outstanding_loans_customer_deposits'],
    'revenue':            ['revenue','net_revenue','operating_income'],
    'net_profit':         ['net_profit','net_profit_after_tax'],
    'eps':                ['eps','earnings_per_share','basic_eps'],
    'operating_cashflow': ['operating_cashflow','cash_from_operations','net_cash_from_operating'],
    'capex':              ['capex','capital_expenditure'],
    'total_assets':       ['total_assets'],
    'equity':             ['equity','owners_equity','stockholders_equity'],
    'total_debt':         ['total_debt','short_long_term_debt'],
    'ebit':               ['ebit','operating_profit'],
    'retained_earnings':  ['retained_earnings','undistributed_earnings'],
}

def sg(iid, *dfs_yrs):
    """Smart get từ nhiều df. dfs_yrs = [(df1,yr1),(df2,yr2)...]"""
    for alias in _AL.get(iid, [iid]):
        for df, yr in dfs_yrs:
            if df is None or df.empty or yr is None: continue
            if 'item_id' not in df.columns: continue
            row = df[df['item_id'] == alias]
            if not row.empty:
                v = pd.to_numeric(row[yr].values[0], errors='coerce')
                if pd.notna(v): return float(v)
    return None

def gs(iid, df, yc, prefer_yc=None):
    """Get series theo năm."""
    cols = prefer_yc if prefer_yc else yc
    for alias in _AL.get(iid, [iid]):
        if 'item_id' not in df.columns: continue
        row = df[df['item_id'] == alias]
        if not row.empty:
            vals = pd.to_numeric(row[cols].values[0], errors='coerce')
            return pd.Series(vals, index=cols)
    return None

def pct(v): return v*100 if v is not None and abs(v)<2 else v
def fmt(n, s=""):
    if n is None or (isinstance(n,float) and math.isnan(n)): return "—"
    n=float(n)
    if abs(n)>=1e12: return f"{n/1e12:.1f}T{s}"
    if abs(n)>=1e9:  return f"{n/1e9:.1f}B{s}"
    if abs(n)>=1e6:  return f"{n/1e6:.1f}M{s}"
    if abs(n)>=1e3:  return f"{n/1e3:.0f}K{s}"
    return f"{n:,.1f}{s}"

# ══════════════════════════════ TECHNICAL INDICATORS ══════════════════════════
def add_indicators(df):
    c=df["Close"].astype(float); hi=df["High"].astype(float); lo=df["Low"].astype(float)
    v=df["Volume"].astype(float)
    # EMAs
    for span in [9,21,50,200]: df[f"EMA{span}"]=c.ewm(span=span,adjust=False).mean()
    df["SMA20"]=c.rolling(20).mean()
    # MACD
    e12=c.ewm(span=12,adjust=False).mean(); e26=c.ewm(span=26,adjust=False).mean()
    df["MACD"]=e12-e26; df["MACD_Sig"]=df["MACD"].ewm(span=9,adjust=False).mean()
    df["MACD_Hist"]=df["MACD"]-df["MACD_Sig"]
    # RSI
    d=c.diff(); g=d.clip(lower=0).ewm(com=13,adjust=False).mean()
    ls=(-d.clip(upper=0)).ewm(com=13,adjust=False).mean()
    df["RSI"]=100-100/(1+g/ls.replace(0,np.nan))
    # Stochastic RSI
    rsi_min=df["RSI"].rolling(14).min(); rsi_max=df["RSI"].rolling(14).max()
    stoch=(df["RSI"]-rsi_min)/(rsi_max-rsi_min).replace(0,np.nan)
    df["StochRSI_K"]=stoch.rolling(3).mean()*100
    df["StochRSI_D"]=df["StochRSI_K"].rolling(3).mean()
    # ATR & ADX
    tr=pd.concat([hi-lo,(hi-c.shift()).abs(),(lo-c.shift()).abs()],axis=1).max(axis=1)
    df["ATR"]=tr.ewm(span=14,adjust=False).mean()
    pdm=(hi.diff()).clip(lower=0).where(hi.diff()>lo.diff().abs(),0)
    ndm=(lo.diff().abs()).clip(lower=0).where(lo.diff().abs()>hi.diff(),0)
    atr14=tr.ewm(span=14,adjust=False).mean()
    pdi=100*pdm.ewm(span=14,adjust=False).mean()/atr14.replace(0,np.nan)
    ndi=100*ndm.ewm(span=14,adjust=False).mean()/atr14.replace(0,np.nan)
    df["ADX"]=(100*(pdi-ndi).abs()/(pdi+ndi).replace(0,np.nan)).ewm(span=14,adjust=False).mean()
    df["PDI"]=pdi; df["NDI"]=ndi
    # Bollinger
    std=c.rolling(20).std()
    df["BB_upper"]=df["SMA20"]+2*std; df["BB_lower"]=df["SMA20"]-2*std
    df["BB_width"]=(df["BB_upper"]-df["BB_lower"])/df["SMA20"].replace(0,np.nan)
    # VWAP
    tp=(hi+lo+c)/3
    df["VWAP"]=(tp*v).cumsum()/v.cumsum()
    # OBV
    obv=[0]
    for i in range(1,len(df)):
        if df["Close"].iloc[i]>df["Close"].iloc[i-1]: obv.append(obv[-1]+df["Volume"].iloc[i])
        elif df["Close"].iloc[i]<df["Close"].iloc[i-1]: obv.append(obv[-1]-df["Volume"].iloc[i])
        else: obv.append(obv[-1])
    df["OBV"]=obv; df["OBV_EMA"]=pd.Series(obv,index=df.index).ewm(span=20,adjust=False).mean()
    # CMF
    mfm=((c-lo)-(hi-c))/(hi-lo).replace(0,np.nan)
    df["CMF"]=(mfm*v).rolling(20).sum()/v.rolling(20).sum()
    # MFI
    tp2=(hi+lo+c)/3; mf=tp2*v
    pos=mf.where(tp2>tp2.shift(1),0); neg=mf.where(tp2<tp2.shift(1),0)
    mfr=pos.rolling(14).sum()/neg.rolling(14).sum().replace(0,np.nan)
    df["MFI"]=100-100/(1+mfr)
    # Volume
    df["Vol_MA20"]=v.rolling(20).mean()
    df["Vol_Ratio"]=v/df["Vol_MA20"].replace(0,np.nan)
    df["EMA_State"]=np.where(df["EMA9"]>df["EMA21"],"bull","bear")
    # Ichimoku
    df["Ichi_Tenkan"]=(hi.rolling(9).max()+lo.rolling(9).min())/2
    df["Ichi_Kijun"] =(hi.rolling(26).max()+lo.rolling(26).min())/2
    df["Ichi_SpanA"] =((df["Ichi_Tenkan"]+df["Ichi_Kijun"])/2).shift(26)
    df["Ichi_SpanB"] =((hi.rolling(52).max()+lo.rolling(52).min())/2).shift(26)
    # Parabolic SAR
    try:
        psar_vals=np.zeros(len(df)); bull_s=True; ep_s=float(lo.iloc[0]); af_s=0.02
        psar_vals[0]=float(hi.iloc[0])
        for _i in range(1,len(df)):
            if bull_s:
                psar_vals[_i]=psar_vals[_i-1]+af_s*(ep_s-psar_vals[_i-1])
                psar_vals[_i]=min(psar_vals[_i],float(lo.iloc[_i-1]),float(lo.iloc[_i-2]) if _i>1 else float(lo.iloc[_i-1]))
                if float(hi.iloc[_i])>ep_s: ep_s=float(hi.iloc[_i]); af_s=min(af_s+0.02,0.2)
                if float(lo.iloc[_i])<psar_vals[_i]: bull_s=False; psar_vals[_i]=ep_s; ep_s=float(lo.iloc[_i]); af_s=0.02
            else:
                psar_vals[_i]=psar_vals[_i-1]+af_s*(ep_s-psar_vals[_i-1])
                psar_vals[_i]=max(psar_vals[_i],float(hi.iloc[_i-1]),float(hi.iloc[_i-2]) if _i>1 else float(hi.iloc[_i-1]))
                if float(lo.iloc[_i])<ep_s: ep_s=float(lo.iloc[_i]); af_s=min(af_s+0.02,0.2)
                if float(hi.iloc[_i])>psar_vals[_i]: bull_s=True; psar_vals[_i]=ep_s; ep_s=float(hi.iloc[_i]); af_s=0.02
        df["PSAR"]=psar_vals
        df["PSAR_Bull"]=bool(bull_s)
    except: df["PSAR"]=np.nan; df["PSAR_Bull"]=True
    # A/D Line
    clv=((c-lo)-(hi-c))/(hi-lo).replace(0,np.nan)
    df["AD_Line"]=(clv*v).cumsum()
    # Pivot Points (từ phiên hôm qua)
    if len(df)>1:
        prev=df.iloc[-2]; ph=float(prev.High); pl=float(prev.Low); pc=float(prev.Close)
        pp=(ph+pl+pc)/3
        df["PP"]=pp; df["R1"]=2*pp-pl; df["R2"]=pp+(ph-pl); df["S1"]=2*pp-ph; df["S2"]=pp-(ph-pl)
    # 52-week high/low (expanding window nếu data < 252 bars)
    w52 = min(252, len(df))
    df["H52"] = df["Close"].expanding(min_periods=1).max() if len(df)<252 else df["Close"].rolling(252).max()
    df["L52"] = df["Close"].expanding(min_periods=1).min() if len(df)<252 else df["Close"].rolling(252).min()
    return df

def detect_patterns(df):
    pats=[None]
    for i in range(1,len(df)):
        p,c2=df.iloc[i-1],df.iloc[i]
        body=abs(c2.Close-c2.Open); rng=c2.High-c2.Low
        up=c2.High-max(c2.Close,c2.Open); dn=min(c2.Close,c2.Open)-c2.Low
        pat=None
        if rng>0 and body<=rng*0.10: pat="Doji"
        elif body>0 and dn>2*body and up<body*0.5: pat="Hammer"
        elif body>0 and up>2*body and dn<body*0.5: pat="Shooting Star"
        elif p.Close<p.Open and c2.Close>c2.Open and c2.Open<=p.Close and c2.Close>=p.Open: pat="Bullish Engulfing"
        elif p.Close>p.Open and c2.Close<c2.Open and c2.Open>=p.Close and c2.Close<=p.Open: pat="Bearish Engulfing"
        elif body>0 and c2.Close>c2.Open and body>abs(p.Close-p.Open)*1.5: pat="Bullish Marubozu"
        pats.append(pat)
    df["Pattern"]=pats; return df

def detect_market_structure(df, lb=5):
    highs=df["High"].rolling(lb*2+1,center=True).max()
    lows=df["Low"].rolling(lb*2+1,center=True).min()
    ph=df["High"][df["High"]==highs].tail(4).values
    pl=df["Low"][df["Low"]==lows].tail(4).values
    if len(ph)>=2 and len(pl)>=2:
        if ph[-1]>ph[-2] and pl[-1]>pl[-2]: return "Uptrend (HH+HL)","#00d97e"
        elif ph[-1]<ph[-2] and pl[-1]<pl[-2]: return "Downtrend (LH+LL)","#ff3d5a"
    return "Sideway/Tích lũy","#f5a623"

def auto_support_resistance(df, n=3):
    """Tìm vùng hỗ trợ/kháng cự từ price action."""
    hi=df["High"]; lo=df["Low"]
    ph_idx=[i for i in range(1,len(df)-1) if hi.iloc[i]>=hi.iloc[i-1] and hi.iloc[i]>=hi.iloc[i+1]]
    pl_idx=[i for i in range(1,len(df)-1) if lo.iloc[i]<=lo.iloc[i-1] and lo.iloc[i]<=lo.iloc[i+1]]
    res=sorted([hi.iloc[i] for i in ph_idx],reverse=True)[:n]
    sup=sorted([lo.iloc[i] for i in pl_idx])[:n]
    return res, sup

# ══════════════════════════════ SIGNAL ENGINE ══════════════════════════════════
def calc_signal(df):
    lat=df.iloc[-1]; prev=df.iloc[-2] if len(df)>1 else lat
    reasons=[]; score=0.0; c=float(lat.Close)
    # EMA alignment
    if lat.EMA9>lat.EMA21>lat.EMA50: reasons.append("✅ EMA9>21>50 — xếp hàng tăng"); score+=1.5
    elif lat.EMA9<lat.EMA21<lat.EMA50: reasons.append("❌ EMA9<21<50 — xếp hàng giảm"); score-=1.5
    else: reasons.append("⚠️ EMA không đồng thuận — sideway")
    if pd.notna(lat.EMA200):
        if c>lat.EMA200: reasons.append("✅ Giá > EMA200 — uptrend dài hạn"); score+=1
        else: reasons.append("❌ Giá < EMA200 — downtrend dài hạn"); score-=1
    if lat.EMA9>lat.EMA21 and prev.EMA9<=prev.EMA21: reasons.append("🔥 Golden Cross EMA9/21"); score+=2
    elif lat.EMA9<lat.EMA21 and prev.EMA9>=prev.EMA21: reasons.append("💧 Death Cross EMA9/21"); score-=2
    # MACD
    mc,ms=float(lat.MACD),float(lat.MACD_Sig); pc,ps=float(prev.MACD),float(prev.MACD_Sig)
    if mc>ms and pc<=ps: reasons.append("🔥 MACD cắt lên Signal — mua"); score+=2
    elif mc<ms and pc>=ps: reasons.append("💧 MACD cắt xuống Signal — bán"); score-=2
    elif mc>ms: reasons.append("✅ MACD trên Signal"); score+=1
    else: reasons.append("❌ MACD dưới Signal"); score-=1
    # RSI
    r=float(lat.RSI)
    if r>75: reasons.append(f"⚠️ RSI={r:.0f} quá mua"); score-=1.5
    elif r<25: reasons.append(f"🔥 RSI={r:.0f} quá bán"); score+=1.5
    elif r>50: reasons.append(f"✅ RSI={r:.0f} ủng hộ tăng"); score+=0.5
    else: reasons.append(f"❌ RSI={r:.0f} ủng hộ giảm"); score-=0.5
    # Stochastic RSI
    if pd.notna(lat.StochRSI_K):
        sk=float(lat.StochRSI_K)
        if sk>80: reasons.append(f"⚠️ StochRSI={sk:.0f} quá mua"); score-=0.5
        elif sk<20: reasons.append(f"🔥 StochRSI={sk:.0f} quá bán"); score+=0.5
    # ADX
    a=float(lat.ADX) if pd.notna(lat.ADX) else 0
    if a>25:
        if mc>ms: reasons.append(f"✅ ADX={a:.0f} xu hướng tăng có đà"); score+=1
        else: reasons.append(f"❌ ADX={a:.0f} xu hướng giảm có đà"); score-=1
    else: reasons.append(f"⚠️ ADX={a:.0f} sideway (<25)")
    # Bollinger
    if c>lat.BB_upper: reasons.append("⚠️ Vượt BB trên — quá mua"); score-=0.5
    elif c<lat.BB_lower: reasons.append("🔥 Chạm BB dưới — quá bán"); score+=0.5
    if lat.BB_width<0.05: reasons.append("📉 BB bó hẹp — sắp bùng nổ")
    # VWAP
    if pd.notna(lat.VWAP):
        if c>lat.VWAP: reasons.append(f"✅ Giá > VWAP ({lat.VWAP:,.0f})"); score+=0.5
        else: reasons.append(f"❌ Giá < VWAP ({lat.VWAP:,.0f})"); score-=0.5
    # MFI (dòng tiền tích hợp volume)
    if pd.notna(lat.MFI):
        mfi=float(lat.MFI)
        if mfi>75: reasons.append(f"⚠️ MFI={mfi:.0f} dòng tiền quá mua"); score-=0.5
        elif mfi<25: reasons.append(f"🔥 MFI={mfi:.0f} dòng tiền quá bán"); score+=0.5
    # CMF
    if pd.notna(lat.CMF):
        cmf=float(lat.CMF)
        if cmf>0.1: reasons.append(f"✅ CMF={cmf:.2f} dòng tiền vào"); score+=0.5
        elif cmf<-0.1: reasons.append(f"❌ CMF={cmf:.2f} dòng tiền ra"); score-=0.5
    # Candle pattern
    pat=str(lat.get("Pattern","") or "")
    if pat in("Bullish Engulfing","Hammer","Bullish Marubozu"): reasons.append(f"🕯 {pat} — đảo chiều tăng"); score+=1.5
    elif pat in("Bearish Engulfing","Shooting Star"): reasons.append(f"🕯 {pat} — đảo chiều giảm"); score-=1.5
    elif pat=="Doji": reasons.append("🕯 Doji — lưỡng lự")
    # Volume
    if lat.Vol_Ratio>1.5: reasons.append(f"📊 Vol đột biến ×{lat.Vol_Ratio:.1f} — "+("xác nhận mua" if score>0 else "xác nhận bán"))
    if   score>=6:   sig="MUA MẠNH"
    elif score>=2.5: sig="MUA"
    elif score>=0.5: sig="THEO DÕI MUA"
    elif score>-0.5: sig="TRUNG TÍNH"
    elif score>-2.5: sig="THEO DÕI BÁN"
    elif score>=-6:  sig="BÁN"
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
    return dict(buy=buy,sl=sl,tp1=tp1,tp2=tp2,tp3=tp3,risk=risk,reward=reward,rr=rr,fib=fib,atr=atr)

# ══════════════════════════════ FUNDAMENTAL ENGINE ══════════════════════════════
def calc_cagr(s, e, years):
    if s and e and years>0 and s>0: return ((e/s)**(1/years)-1)*100
    return None

def fundamental_analysis(rat_df, inc_df, bal_df, cf_df, current_price=None):
    """Phân tích cơ bản toàn diện — trả về dict."""
    ryc=ycols(rat_df); iyc=ycols(inc_df); byc=ycols(bal_df); cyc=ycols(cf_df)
    rl=ryc[-1] if ryc else None; il=iyc[-1] if iyc else None
    bl=byc[-1] if byc else None; cl=cyc[-1] if cyc else None

    def gv(*ids): return sg(ids[0], (rat_df,rl),(inc_df,il),(bal_df,bl),(cf_df,cl)) if ids else None

    # Chỉ số định giá
    pe=gv('pe_ratio'); pb=gv('pb_ratio')
    eps_raw=gv('earnings_per_share'); eps=eps_raw

    # Chỉ số sinh lời
    roe=pct(gv('roe')); roa=pct(gv('roa'))
    gm=pct(gv('gross_margin')); nm=pct(gv('net_margin'))

    # Cân đối nợ
    de=gv('debt_to_equity')
    eq_ta=pct(gv('equity_total_assets')) if de is None else None
    cr=gv('current_ratio')
    ldr=pct(gv('ldr')) if cr is None else None
    is_bank = de is None and eq_ta is not None

    # Doanh thu & lợi nhuận series
    rev_s = gs('revenue', inc_df, iyc) if not inc_df.empty else None
    net_s = gs('net_profit', inc_df, iyc) if not inc_df.empty else None
    eps_s = gs('eps', inc_df, iyc) or gs('earnings_per_share', rat_df, ryc) if not (inc_df.empty and rat_df.empty) else None
    if eps_s is None and not inc_df.empty: eps_s = gs('eps', inc_df, iyc)

    # CAGR
    years = len(ryc) - 1 if len(ryc) > 1 else 1
    rev_cagr = None; eps_cagr = None
    if rev_s is not None and len(rev_s) >= 2:
        rev_cagr = calc_cagr(float(rev_s.iloc[0]), float(rev_s.iloc[-1]), years)
    if eps_s is not None and len(eps_s) >= 2:
        eps_cagr = calc_cagr(abs(float(eps_s.iloc[0])), abs(float(eps_s.iloc[-1])), years)

    # Operating cashflow
    ocf = gv('operating_cashflow')
    net_p = gv('net_profit')
    fcf_quality = None
    if ocf and net_p and net_p != 0:
        fcf_quality = ocf / net_p  # >1 = chất lượng lợi nhuận tốt

    # Du Pont phân rã ROE
    dupont = {}
    if not is_bank and roe and nm and rev_s is not None and not rev_s.empty:
        ta = gv('total_assets'); eq = gv('equity')
        if ta and ta>0 and eq and eq>0:
            rev_val = float(rev_s.iloc[-1])
            asset_turnover = rev_val / ta
            eq_mult = ta / eq
            dupont = {
                'net_margin': nm,
                'asset_turnover': asset_turnover,
                'equity_multiplier': eq_mult,
                'roe_check': nm/100 * asset_turnover * eq_mult * 100,
                'driver': max([('Biên LN ròng',nm),('Hiệu quả TS',asset_turnover*10),('Đòn bẩy TC',eq_mult*3)],key=lambda x:x[1])[0]
            }

    # Altman Z-Score (phi ngân hàng)
    z_score = None; z_zone = None
    if not is_bank:
        wc = gv('current_ratio'); ta2 = gv('total_assets'); re = gv('retained_earnings')
        ebit_v = gv('ebit'); mc = current_price; tl = gv('total_debt')
        rev_v = float(rev_s.iloc[-1]) if rev_s is not None and not rev_s.empty else None
        if all(v is not None for v in [ta2,ebit_v,tl,rev_v]) and ta2>0:
            x1=(wc or 0)/ta2; x2=(re or 0)/ta2; x3=ebit_v/ta2
            x4=(mc or ta2*0.3)/max(tl,1); x5=rev_v/ta2
            z = 1.2*x1+1.4*x2+3.3*x3+0.6*x4+x5
            z_score=round(z,2)
            z_zone="An toàn 🟢" if z>2.99 else "Vùng xám ⚠️" if z>1.81 else "Nguy hiểm 🔴"

    # Narrative analysis
    narrative = []
    if rev_cagr is not None:
        if rev_cagr > 15: narrative.append(("✅","Tăng trưởng doanh thu",f"CAGR {rev_cagr:.1f}%/năm — tăng trưởng mạnh","#00d97e"))
        elif rev_cagr > 5: narrative.append(("⚠️","Tăng trưởng doanh thu",f"CAGR {rev_cagr:.1f}%/năm — tăng trưởng ổn định","#f5a623"))
        else: narrative.append(("❌","Tăng trưởng doanh thu",f"CAGR {rev_cagr:.1f}%/năm — tăng trưởng yếu","#ff3d5a"))
    if eps_cagr is not None:
        if eps_cagr > 15: narrative.append(("✅","Tăng trưởng EPS",f"CAGR {eps_cagr:.1f}%/năm — lợi nhuận trên mỗi CP tăng tốt","#00d97e"))
        elif eps_cagr > 0: narrative.append(("⚠️","Tăng trưởng EPS",f"CAGR {eps_cagr:.1f}%/năm — tăng chậm","#f5a623"))
        else: narrative.append(("❌","Tăng trưởng EPS","EPS suy giảm — lợi nhuận đang xấu đi","#ff3d5a"))
    if roe is not None:
        if roe>18: narrative.append(("✅","Sinh lời vốn chủ (ROE)",f"ROE={roe:.1f}% — xuất sắc (top doanh nghiệp)","#00d97e"))
        elif roe>12: narrative.append(("⚠️","Sinh lời vốn chủ (ROE)",f"ROE={roe:.1f}% — tốt","#f5a623"))
        else: narrative.append(("❌","Sinh lời vốn chủ (ROE)",f"ROE={roe:.1f}% — dưới kỳ vọng","#ff3d5a"))
    if fcf_quality is not None:
        if fcf_quality>1.0: narrative.append(("✅","Chất lượng lợi nhuận",f"OCF/Net={fcf_quality:.1f}x — tiền mặt thực > LN ghi nhận","#00d97e"))
        elif fcf_quality>0.5: narrative.append(("⚠️","Chất lượng lợi nhuận",f"OCF/Net={fcf_quality:.1f}x — chấp nhận được","#f5a623"))
        else: narrative.append(("❌","Chất lượng lợi nhuận",f"OCF/Net={fcf_quality:.1f}x — LN kém chất lượng","#ff3d5a"))
    if pe is not None:
        if 0<pe<12: narrative.append(("✅","Định giá P/E",f"P/E={pe:.1f}x — rẻ so với thị trường","#00d97e"))
        elif pe<20: narrative.append(("⚠️","Định giá P/E",f"P/E={pe:.1f}x — định giá hợp lý","#f5a623"))
        elif pe>0: narrative.append(("❌","Định giá P/E",f"P/E={pe:.1f}x — định giá đắt","#ff3d5a"))

    return dict(pe=pe,pb=pb,eps=eps,roe=roe,roa=roa,gm=gm,nm=nm,
                de=de,eq_ta=eq_ta,cr=cr,ldr=ldr,is_bank=is_bank,
                rev_s=rev_s,net_s=net_s,eps_s=eps_s,
                rev_cagr=rev_cagr,eps_cagr=eps_cagr,
                ocf=ocf,fcf_quality=fcf_quality,
                dupont=dupont,z_score=z_score,z_zone=z_zone,
                narrative=narrative,ryc=ryc,iyc=iyc)

def fund_score(fa):
    """Chấm điểm cơ bản từ kết quả fundamental_analysis."""
    total=0; items=[]
    def chk(lbl,val,fn,g,b,w):
        nonlocal total
        ok=fn(val) if val is not None else None
        items.append(dict(label=lbl,val=val,ok=ok,good=g,bad=b))
        if ok is True: total+=w
        elif ok is False: total-=w

    chk("ROE",fa['roe'],lambda v:v>15,"ROE>15% — sinh lời tốt","ROE<15% — thấp",1.0)
    chk("ROA",fa['roa'],lambda v:v>1.5 if fa['is_bank'] else v>8,"ROA tốt","ROA thấp",0.5)
    chk("P/E",fa['pe'],lambda v:0<v<18,"P/E hợp lý","P/E cao/âm",1.0)
    chk("P/B",fa['pb'],lambda v:0<v<3.5,"P/B<3.5x","P/B cao",0.5)
    chk("EPS",fa['eps'],lambda v:v>0,"EPS dương","EPS âm",1.5)
    if fa['is_bank'] and fa['eq_ta']:
        chk("VCSH/TS",fa['eq_ta'],lambda v:v>6,"VCSH/TS>6% — vốn đệm tốt","Vốn mỏng",0.3)
    elif fa['de']:
        chk("D/E",fa['de'],lambda v:v<1.5,"D/E<1.5x — nợ tốt","Đòn bẩy cao",0.3)
    if fa['rev_cagr']:
        chk("Rev CAGR",fa['rev_cagr'],lambda v:v>10,"Doanh thu tăng tốt","Doanh thu trì trệ",0.5)
    if fa['fcf_quality']:
        chk("Cash Quality",fa['fcf_quality'],lambda v:v>0.8,"OCF>LN — tiền thật","Lợi nhuận kém thực",0.7)
    return items, round(total,1)

# ══════════════════════════════ SCREENER ═══════════════════════════════════════
@st.cache_data(ttl=300, show_spinner=False)
def scan_stock(sym, days=90):
    """Scan 1 mã và trả về dict điểm kỹ thuật."""
    try:
        df = fetch_price(sym, days)
        if df.empty or len(df)<30: return None
        df = add_indicators(df)
        sig, _, score = calc_signal(df)
        lat = df.iloc[-1]
        chg1d = (float(lat.Close)-float(df.iloc[-2].Close))/float(df.iloc[-2].Close)*100 if len(df)>1 else 0
        chg5d = (float(lat.Close)-float(df.iloc[-5].Close))/float(df.iloc[-5].Close)*100 if len(df)>5 else 0
        return dict(sym=sym, sig=sig, score=score,
                    close=float(lat.Close), chg1d=chg1d, chg5d=chg5d,
                    rsi=float(lat.RSI), vol_ratio=float(lat.Vol_Ratio),
                    cmf=float(lat.CMF) if pd.notna(lat.CMF) else 0,
                    mfi=float(lat.MFI) if pd.notna(lat.MFI) else 50,
                    adx=float(lat.ADX) if pd.notna(lat.ADX) else 0)
    except: return None

# ══════════════════════════════ UI HELPERS ═════════════════════════════════════
def card(label, val_str, color="#fff", note=""):
    return f"""<div style='background:#0c1d2e;border:1px solid #163350;border-radius:12px;padding:14px 16px;'>
  <div style='font-size:12px;color:#6a9cc8;letter-spacing:.5px;margin-bottom:6px;font-weight:500;'>{label}</div>
  <div style='font-size:22px;font-weight:700;color:{color};line-height:1.2;'>{val_str}</div>
  {'<div style="font-size:11px;color:#4a6080;margin-top:4px;">'+note+'</div>' if note else ''}
</div>"""

def sig_banner(sig, score):
    clr=SIG_COLOR.get(sig,"#8baed4"); sc_clr="#00d97e" if score>=2 else "#ff3d5a" if score<=-2 else "#f5a623"
    pct_val=min(100,max(0,(score+9)/18*100))
    return f"""<div style='background:#0c1d2e;border:1px solid #163350;border-radius:12px;
      padding:16px 20px;display:flex;align-items:center;gap:24px;flex-wrap:wrap;margin:10px 0;'>
  <div><div style='font-size:12px;color:#6a9cc8;letter-spacing:1px;font-weight:500;'>TÍN HIỆU KỸ THUẬT</div>
       <div style='font-size:30px;font-weight:700;color:{clr};'>{sig}</div></div>
  <div style='text-align:center;'><div style='font-size:12px;color:#6a9cc8;font-weight:500;'>ĐIỂM</div>
       <div style='font-size:32px;font-weight:700;color:{sc_clr};'>{score:+.1f}</div></div>
  <div style='flex:1;min-width:220px;'>
    <div style='font-size:10px;color:#3a6080;letter-spacing:1px;margin-bottom:5px;'>BÁN MẠNH ←──────────────→ MUA MẠNH</div>
    <div style='height:10px;background:#102030;border-radius:5px;overflow:hidden;border:1px solid #163350;'>
      <div style='height:100%;width:{pct_val}%;background:{clr};border-radius:5px;'></div>
    </div>
  </div>
</div>"""

def trade_card(icon, title, val, sub, border):
    return f"""<div style='background:#0c1d2e;border:1px solid {border};border-radius:12px;padding:14px 16px;'>
  <div style='font-size:12px;color:{border};letter-spacing:.5px;margin-bottom:6px;font-weight:500;'>{icon} {title}</div>
  <div style='font-size:22px;font-weight:700;color:#fff;line-height:1.2;'>{val}</div>
  <div style='font-size:13px;color:#6a9cc8;margin-top:4px;'>{sub}</div>
</div>"""

def fund_chip(item):
    ok=item["ok"]; val=item["val"]; lbl=item["label"]
    clr="#00d97e" if ok else "#ff3d5a" if ok is False else "#f5a623"
    ico="✅" if ok else "❌" if ok is False else "⚪"
    vs=(f"{val:,.1f}" if isinstance(val,float) else str(val)) if val is not None else "—"
    note=item["good"] if ok else (item["bad"] if ok is False else "N/A")
    return f"""<div style='background:#0c1d2e;border:1px solid {clr}50;border-radius:12px;padding:12px;text-align:center;'>
  <div style='font-size:20px;'>{ico}</div>
  <div style='font-size:13px;font-weight:600;color:#cce0ff;margin:4px 0;'>{lbl}</div>
  <div style='font-size:18px;font-weight:700;color:{clr};'>{vs}</div>
  <div style='font-size:11px;color:#6a9cc8;margin-top:4px;line-height:1.4;'>{note}</div>
</div>"""

def score_pill(label, s, note=""):
    clr="#00d97e" if s>1 else "#ff3d5a" if s<-1 else "#f5a623"
    pct_val=min(100,max(0,(s+7)/14*100))
    return f"""<div style='background:#0c1d2e;border:1px solid #163350;border-radius:12px;padding:14px;text-align:center;'>
  <div style='font-size:12px;color:#6a9cc8;letter-spacing:.5px;margin-bottom:4px;'>{label}</div>
  <div style='font-size:24px;font-weight:700;color:{clr};'>{s:+.1f}</div>
  <div style='font-size:11px;color:#3a6080;margin-top:3px;'>{note}</div>
  <div style='height:4px;background:#102030;border-radius:2px;overflow:hidden;margin-top:7px;'>
    <div style='height:100%;width:{pct_val}%;background:{clr};border-radius:2px;'></div>
  </div>
</div>"""

def narrative_card(ico, title, desc, clr):
    return f"""<div style='background:#0c1d2e;border-left:3px solid {clr};border-radius:0 10px 10px 0;
      padding:10px 14px;margin:5px 0;display:flex;gap:10px;align-items:flex-start;'>
  <span style='font-size:18px;'>{ico}</span>
  <div>
    <div style='font-size:13px;font-weight:600;color:{clr};'>{title}</div>
    <div style='font-size:12px;color:#8baed4;margin-top:2px;'>{desc}</div>
  </div>
</div>"""

# ══════════════════════════════ CHART BUILDERS ════════════════════════════════
def build_price_chart(df, trade, show_n, ema_list):
    show=df.tail(show_n).copy()
    ema_colors={"EMA9":"#4a9ef8","EMA21":"#f5a623","EMA50":"#00d97e","EMA200":"#a78bfa"}
    fig=make_subplots(rows=5,cols=1,shared_xaxes=True,vertical_spacing=0.015,
        row_heights=[0.45,0.12,0.14,0.14,0.15],
        subplot_titles=("","Volume","MACD","RSI + StochRSI","CMF + MFI"))
    # Nến
    fig.add_trace(go.Candlestick(x=show["Date"],open=show["Open"],high=show["High"],
        low=show["Low"],close=show["Close"],name="Giá",
        increasing=dict(fillcolor="#00d97e",line=dict(color="#00d97e",width=1)),
        decreasing=dict(fillcolor="#ff3d5a",line=dict(color="#ff3d5a",width=1))),row=1,col=1)
    # EMAs
    for ema in ema_list:
        if ema in show.columns and show[ema].notna().any():
            fig.add_trace(go.Scatter(x=show["Date"],y=show[ema],name=ema,
                line=dict(color=ema_colors.get(ema,"#fff"),width=1.5),hoverinfo="skip"),row=1,col=1)
    # VWAP
    if "VWAP" in show.columns:
        fig.add_trace(go.Scatter(x=show["Date"],y=show["VWAP"],name="VWAP",
            line=dict(color="#ff9f43",width=1.2,dash="dot"),hoverinfo="skip"),row=1,col=1)
    # BB
    fig.add_trace(go.Scatter(x=show["Date"],y=show["BB_upper"],name="BB+",
        line=dict(color="rgba(167,139,250,.3)",width=1,dash="dot"),hoverinfo="skip"),row=1,col=1)
    fig.add_trace(go.Scatter(x=show["Date"],y=show["BB_lower"],name="BB-",
        line=dict(color="rgba(167,139,250,.3)",width=1,dash="dot"),
        fill="tonexty",fillcolor="rgba(167,139,250,0.03)",hoverinfo="skip"),row=1,col=1)
    # Ichimoku Cloud
    if "Ichi_SpanA" in show.columns and show["Ichi_SpanA"].notna().any():
        fig.add_trace(go.Scatter(x=show["Date"],y=show["Ichi_SpanA"],name="Kumo A",
            line=dict(color="rgba(0,217,126,.2)",width=0.5),hoverinfo="skip"),row=1,col=1)
        fig.add_trace(go.Scatter(x=show["Date"],y=show["Ichi_SpanB"],name="Kumo B",
            line=dict(color="rgba(255,61,90,.2)",width=0.5),
            fill="tonexty",fillcolor="rgba(0,100,50,0.06)",hoverinfo="skip"),row=1,col=1)
    if "Ichi_Tenkan" in show.columns and show["Ichi_Tenkan"].notna().any():
        fig.add_trace(go.Scatter(x=show["Date"],y=show["Ichi_Tenkan"],name="Tenkan",
            line=dict(color="#ff6b6b",width=1,dash="dot"),hoverinfo="skip"),row=1,col=1)
        fig.add_trace(go.Scatter(x=show["Date"],y=show["Ichi_Kijun"],name="Kijun",
            line=dict(color="#4a9ef8",width=1,dash="dash"),hoverinfo="skip"),row=1,col=1)
    # Parabolic SAR
    if "PSAR" in show.columns and show["PSAR"].notna().any():
        psar_clr=["#00d97e" if show["PSAR_Bull"].iloc[0] else "#ff3d5a"]
        fig.add_trace(go.Scatter(x=show["Date"],y=show["PSAR"],name="PSAR",
            mode="markers",marker=dict(symbol="circle",size=3,color="#ff9f43"),
            hoverinfo="skip"),row=1,col=1)
    # Pivot Lines
    if "PP" in show.columns:
        pp_val=float(show["PP"].iloc[-1])
        ylo2=float(show["Low"].min()); yhi2=float(show["High"].max())
        for pname,pcol in [("PP","#ffffff"),("R1","#ff6b6b"),("R2","#ff3d5a"),("S1","#69d366"),("S2","#00d97e")]:
            if pname in show.columns:
                pv=float(show[pname].iloc[-1])
                if ylo2*0.9<pv<yhi2*1.1:
                    fig.add_hline(y=pv,row=1,col=1,line=dict(color=pcol,dash="dot",width=0.6),
                        annotation_text=f" {pname}",annotation_font=dict(color=pcol,size=8))
    # Trade lines
    ylo=float(show["Low"].min()); yhi=float(show["High"].max())
    for price,lbl,clr,dash in [(trade["buy"],"BUY","#00d97e","dash"),
        (trade["sl"],"SL","#ff3d5a","dash"),(trade["tp1"],"TP1","#f5a623","dot"),
        (trade["tp2"],"TP2","#ffd700","dot"),(trade["tp3"],"TP3","#fff380","dot")]:
        if ylo*0.85<price<yhi*1.15:
            fig.add_hline(y=price,row=1,col=1,line=dict(color=clr,dash=dash,width=1),
                annotation_text=f" {lbl} {price:,.0f}",annotation_font=dict(color=clr,size=9))
    # Volume
    vc=["#00d97e" if r.Close>=r.Open else "#ff3d5a" for _,r in show.iterrows()]
    fig.add_trace(go.Bar(x=show["Date"],y=show["Volume"],marker_color=vc,opacity=0.6,showlegend=False),row=2,col=1)
    if show["Vol_MA20"].notna().any():
        fig.add_trace(go.Scatter(x=show["Date"],y=show["Vol_MA20"],name="Vol MA20",
            line=dict(color="#f5a623",width=1),hoverinfo="skip"),row=2,col=1)
    # MACD
    fig.add_trace(go.Scatter(x=show["Date"],y=show["MACD"],name="MACD",line=dict(color="#4a9ef8",width=1.5)),row=3,col=1)
    fig.add_trace(go.Scatter(x=show["Date"],y=show["MACD_Sig"],name="Signal",line=dict(color="#ff3d5a",width=1,dash="dot")),row=3,col=1)
    hc=["#00d97e" if v>=0 else "#ff3d5a" for v in show["MACD_Hist"].fillna(0)]
    fig.add_trace(go.Bar(x=show["Date"],y=show["MACD_Hist"],marker_color=hc,opacity=.8,showlegend=False),row=3,col=1)
    # RSI + StochRSI
    fig.add_trace(go.Scatter(x=show["Date"],y=show["RSI"],name="RSI",line=dict(color="#a78bfa",width=1.5)),row=4,col=1)
    if "StochRSI_K" in show.columns:
        fig.add_trace(go.Scatter(x=show["Date"],y=show["StochRSI_K"],name="StochK",line=dict(color="#22d3ee",width=1)),row=4,col=1)
    for lvl,clr_l in[(80,"rgba(255,61,90,.5)"),(50,"rgba(139,174,212,.25)"),(20,"rgba(0,217,126,.5)")]:
        fig.add_hline(y=lvl,row=4,col=1,line=dict(color=clr_l,dash="dot",width=.8))
    # CMF + MFI
    if "CMF" in show.columns:
        fig.add_trace(go.Scatter(x=show["Date"],y=show["CMF"],name="CMF",line=dict(color="#00d97e",width=1.5)),row=5,col=1)
        fig.add_hline(y=0,row=5,col=1,line=dict(color="rgba(255,255,255,.2)",dash="dot",width=.8))
    if "MFI" in show.columns:
        fig.add_trace(go.Scatter(x=show["Date"],y=show["MFI"]/100*0.4-0.2,name="MFI(scaled)",
            line=dict(color="#f5a623",width=1,dash="dot")),row=5,col=1)
    fig.update_layout(height=820,template="plotly_dark",xaxis_rangeslider_visible=False,**CHART_STYLE)
    for ann in fig.layout.annotations: ann.font.color="#4a6080"; ann.font.size=10
    return fig

def build_fin_charts(fa):
    charts=[]
    ryc=fa['ryc']; iyc=fa['iyc']
    # EPS + ROE/ROA
    eps_s=fa['eps_s']; roe_s=None; roa_s=None
    # (series đã trong fa)
    fig1=make_subplots(rows=1,cols=2,subplot_titles=("EPS theo năm (đ/CP)","ROE & ROA xu hướng (%)"),horizontal_spacing=0.12)
    if eps_s is not None and not eps_s.empty:
        bc=["#00d97e" if v>=0 else "#ff3d5a" for v in eps_s.fillna(0)]
        fig1.add_trace(go.Bar(x=list(eps_s.index),y=eps_s.values,name="EPS",marker_color=bc,
            text=[f"{v:,.0f}" for v in eps_s.values],textposition="outside",
            textfont=dict(color="#cce0ff",size=11)),row=1,col=1)
    fig1.update_layout(height=320,template="plotly_dark",**CHART_STYLE)
    for ann in fig1.layout.annotations: ann.font.color="#8baed4"; ann.font.size=12
    charts.append(fig1)
    # Doanh thu & Lợi nhuận
    if fa['rev_s'] is not None and fa['net_s'] is not None:
        fig2=make_subplots(rows=1,cols=1,specs=[[{"secondary_y":True}]])
        fig2.add_trace(go.Bar(x=list(fa['rev_s'].index),y=fa['rev_s'].values/1e9,
            name="Doanh thu (tỷ)",marker_color="#4a9ef8",opacity=0.7),secondary_y=False)
        fig2.add_trace(go.Scatter(x=list(fa['net_s'].index),y=fa['net_s'].values/1e9,
            name="Lợi nhuận (tỷ)",mode="lines+markers",line=dict(color="#00d97e",width=2.5),marker=dict(size=8)),secondary_y=False)
        fig2.update_layout(height=280,title="Doanh thu & Lợi nhuận (tỷ đồng)",template="plotly_dark",**CHART_STYLE)
        fig2.layout.title.font.color="#8baed4"; fig2.layout.title.font.size=12
        charts.append(fig2)
    return charts

def build_cashflow_chart(df):
    if df.empty: return None
    yc=ycols(df)
    if not yc: return None
    obv_series=None; cmf_series=None; mfi_series=None
    if not df.empty:
        obv_series=df["OBV"].tail(60) if "OBV" in df.columns else None
        cmf_series=df["CMF"].tail(60) if "CMF" in df.columns else None
        mfi_series=df["MFI"].tail(60) if "MFI" in df.columns else None
    fig=make_subplots(rows=3,cols=1,shared_xaxes=True,vertical_spacing=0.04,
        row_heights=[0.4,0.3,0.3],
        subplot_titles=("OBV — Tích lũy / Phân phối","CMF (Chaikin Money Flow)","MFI (Money Flow Index)"))
    if obv_series is not None and not obv_series.empty:
        fig.add_trace(go.Scatter(x=df["Date"].tail(60),y=obv_series/1e6,name="OBV(M)",
            line=dict(color="#4a9ef8",width=2),fill="tozeroy",fillcolor="rgba(74,158,248,.1)"),row=1,col=1)
        obv_ema=df["OBV_EMA"].tail(60) if "OBV_EMA" in df.columns else None
        if obv_ema is not None:
            fig.add_trace(go.Scatter(x=df["Date"].tail(60),y=obv_ema/1e6,name="OBV EMA",
                line=dict(color="#f5a623",width=1.5,dash="dot")),row=1,col=1)
    if cmf_series is not None:
        cmf_colors=["#00d97e" if v>=0 else "#ff3d5a" for v in cmf_series.fillna(0)]
        fig.add_trace(go.Bar(x=df["Date"].tail(60),y=cmf_series,name="CMF",marker_color=cmf_colors,opacity=0.8),row=2,col=1)
        fig.add_hline(y=0.1,row=2,col=1,line=dict(color="rgba(0,217,126,.5)",dash="dot",width=1),annotation_text=" +0.1")
        fig.add_hline(y=-0.1,row=2,col=1,line=dict(color="rgba(255,61,90,.5)",dash="dot",width=1),annotation_text=" -0.1")
        fig.add_hline(y=0,row=2,col=1,line=dict(color="rgba(255,255,255,.2)",width=0.8))
    if mfi_series is not None:
        fig.add_trace(go.Scatter(x=df["Date"].tail(60),y=mfi_series,name="MFI",
            line=dict(color="#a78bfa",width=2)),row=3,col=1)
        for lvl,clr_l in[(80,"rgba(255,61,90,.5)"),(50,"rgba(139,174,212,.25)"),(20,"rgba(0,217,126,.5)")]:
            fig.add_hline(y=lvl,row=3,col=1,line=dict(color=clr_l,dash="dot",width=.8))
    fig.update_layout(height=520,template="plotly_dark",**CHART_STYLE)
    for ann in fig.layout.annotations: ann.font.color="#8baed4"; ann.font.size=10
    return fig

# ══════════════════════════════ SIDEBAR ════════════════════════════════════════
with st.sidebar:
    st.markdown("## 📈 Pro Trader v6")
    st.markdown("---")
    symbol=st.text_input("Mã cổ phiếu",value="VPB").upper().strip()
    res_label=st.selectbox("Độ phân giải",list(RESOLUTIONS.keys()),index=0)
    resolution=RESOLUTIONS[res_label]
    per_label=st.selectbox("Lịch sử",list(PERIODS.keys()),index=2)
    days=PERIODS[per_label]
    show_n=st.slider("Số nến hiển thị",30,300,100,10)
    st.markdown("**EMA hiển thị**")
    c1,c2=st.columns(2)
    ema_sel={"EMA9":c1.checkbox("EMA 9",True),"EMA21":c2.checkbox("EMA 21",True),
             "EMA50":c1.checkbox("EMA 50",True),"EMA200":c2.checkbox("EMA 200",False)}
    ema_list=[k for k,v in ema_sel.items() if v]
    run=st.button("🚀 Phân tích ngay",use_container_width=True)
    st.markdown("---")
    st.markdown("**Mã nhanh**")
    quick=["VPB","HPG","VCB","FPT","MWG","SSI","TCB","VIC","ACB","STB","MBB","HDB"]
    qcols=st.columns(3); clicked=None
    for i,m in enumerate(quick):
        if qcols[i%3].button(m,key=f"q_{m}",use_container_width=True): clicked=m
    if clicked: symbol=clicked

# ══════════════════════════════ MAIN ══════════════════════════════════════════
st.markdown(f"## {symbol} &nbsp;<span style='font-size:14px;color:#4a9ef8;'>{res_label} · {per_label}</span>",
            unsafe_allow_html=True)

if not (run or clicked):
    st.markdown("""<div style='text-align:center;padding:80px 20px;background:#0c1d2e;border-radius:14px;border:1px solid #163350;'>
      <div style='font-size:52px;'>📈</div>
      <div style='font-size:17px;color:#6a9cc8;margin-top:14px;'>Nhập mã cổ phiếu và nhấn <b style="color:#fff">Phân tích ngay</b></div>
      <div style='font-size:13px;color:#3a6080;margin-top:8px;'>6 tab: Kỹ thuật · Cơ bản · Dòng tiền · So sánh ngành · Quét mã · Tổng hợp</div>
    </div>""",unsafe_allow_html=True)
    st.stop()

with st.spinner(f"⏳ Đang tải {symbol}..."):
    try:
        df_raw = fetch_price(symbol, days, resolution)
    except Exception as e:
        st.error(f"❌ Không lấy được dữ liệu giá: {e}"); st.stop()
    rat = fetch_ratio(symbol)
    inc = fetch_income(symbol)
    bal = fetch_balance(symbol)
    cf  = fetch_cashflow(symbol)
    tcbs_data = fetch_tcbs_financial(symbol)
    # Merge TCBS ratio nếu KBS thiếu
    if rat.empty and 'ratio' in tcbs_data and not tcbs_data['ratio'].empty:
        rat = tcbs_data['ratio']
    tcbs_ov = tcbs_data.get('overview', {})
    tcbs_pt = tcbs_data.get('price_target', [])

df = add_indicators(df_raw.copy())
df = detect_patterns(df)
sig, reasons, score = calc_signal(df)
trade = calc_trade(df, score)
fa = fundamental_analysis(rat, inc, bal, cf, float(df["Close"].iloc[-1]))
f_items, f_score = fund_score(fa)
lat = df.iloc[-1]; prev = df.iloc[-2] if len(df)>1 else lat

chg = float(lat.Close)-float(prev.Close)
pct_chg = chg/float(prev.Close)*100 if prev.Close else 0
chg_str = f"{'▲' if chg>=0 else '▼'} {abs(chg):,.0f} đ ({abs(pct_chg):.2f}%)"
struct, struct_clr = detect_market_structure(df)
st.caption(f"📡 KBS Live · {len(df)} phiên · {'🟢' if chg>=0 else '🔴'} {chg_str} · Cấu trúc: <span style='color:{struct_clr}'>{struct}</span> · {datetime.now().strftime('%H:%M %d/%m/%Y')}",
           unsafe_allow_html=True)

tab1,tab2,tab3,tab4,tab5,tab6,tab7 = st.tabs([
    "📉 Kỹ thuật","📊 Cơ bản","💰 Dòng tiền",
    "🏭 So sánh ngành","🔍 Quét mã","📰 Tin tức","🎯 Tổng hợp"])

# ── TAB 1: KỸ THUẬT ─────────────────────────────────────────────────────────
with tab1:
    m1,m2,m3,m4,m5,m6,m7,m8 = st.columns(8)
    m1.metric("💰 Giá",f"{lat.Close:,.0f} đ",chg_str)
    m2.metric("📐 ATR",f"{lat.ATR:,.0f} đ","Biên dao động")
    m3.metric("📊 RSI",f"{lat.RSI:.0f}","OB>75 | OS<25")
    m4.metric("💧 MFI",f"{lat.MFI:.0f}" if pd.notna(lat.MFI) else "—","Money Flow")
    m5.metric("📈 ADX",f"{lat.ADX:.0f}" if pd.notna(lat.ADX) else "—","Xu hướng")
    h52v=float(lat.H52) if pd.notna(lat.get('H52',np.nan)) else 0
    l52v=float(lat.L52) if pd.notna(lat.get('L52',np.nan)) else 0
    pct_h=((float(lat.Close)-h52v)/h52v*100) if h52v>0 else 0
    m6.metric("📅 52W High",f"{h52v:,.0f}",f"{pct_h:+.1f}% vs now")
    psar_v=float(lat.PSAR) if pd.notna(lat.get('PSAR',np.nan)) else 0
    m7.metric("🎯 PSAR",f"{psar_v:,.0f}" if psar_v else "—",
        "Bull ✅" if lat.get('PSAR_Bull',True) else "Bear ❌")
    m8.metric("🏗️ Cấu trúc",struct.split(" ")[0],"Market structure")
    st.markdown(sig_banner(sig,score),unsafe_allow_html=True)
    st.plotly_chart(build_price_chart(df,trade,show_n,ema_list),use_container_width=True,config={"displayModeBar":True})
    # Trade levels
    st.markdown("### 🎯 Chiến lược giao dịch")
    t1,t2,t3,t4 = st.columns(4)
    t1.markdown(trade_card("📗","VÙNG MUA",f"{trade['buy']:,} đ","Giá vào lệnh","#00d97e"),unsafe_allow_html=True)
    t2.markdown(trade_card("📕","STOP LOSS",f"{trade['sl']:,} đ",f"Rủi ro {trade['risk']*100:.1f}%","#ff3d5a"),unsafe_allow_html=True)
    t3.markdown(trade_card("🎯","CHỐT LỜI",f"TP1 {trade['tp1']:,}",f"TP2 {trade['tp2']:,} | TP3 {trade['tp3']:,}","#f5a623"),unsafe_allow_html=True)
    rr=trade['rr']; rrc="#00d97e" if rr>=2 else "#f5a623" if rr>=1.5 else "#ff3d5a"
    t4.markdown(trade_card("⚖️","R:R RATIO",f"1:{rr:.1f}",f"LN kỳ vọng {trade['reward']*100:.1f}%",rrc),unsafe_allow_html=True)
    # Support/Resistance
    res_levels, sup_levels = auto_support_resistance(df)
    with st.expander("📐 Hỗ trợ & Kháng cự tự động + Fibonacci"):
        sa,sb = st.columns(2)
        with sa:
            st.markdown("**🔴 Kháng cự**")
            for r2 in res_levels: st.markdown(f"  `{r2:,.0f} đ`")
            st.markdown("**🟢 Hỗ trợ**")
            for s2 in sup_levels: st.markdown(f"  `{s2:,.0f} đ`")
        with sb:
            fib_rows=[{"Mức":k,"Giá (đ)":f"{v:,.0f}","So HT":f"{(v/float(lat.Close)-1)*100:+.1f}%",
                "Vai trò":"◀ HIỆN TẠI" if abs(v/float(lat.Close)-1)<0.015 else ("Hỗ trợ 🟢" if v<lat.Close else "Kháng cự 🔴")}
                for k,v in trade["fib"].items()]
            st.dataframe(pd.DataFrame(fib_rows),use_container_width=True,hide_index=True)
    # Signal reasons
    st.markdown("### 🔍 Phân tích tín hiệu")
    rc1,rc2 = st.columns(2); mid=len(reasons)//2+1
    for r2 in reasons[:mid]: rc1.markdown(r2)
    for r2 in reasons[mid:]: rc2.markdown(r2)
    # Indicator table
    ind_tbl=[
        ("RSI(14)",f"{lat.RSI:.1f}","Quá mua🔴" if lat.RSI>75 else "Quá bán🟢" if lat.RSI<25 else "Bình thường✅"),
        ("StochRSI K",f"{lat.StochRSI_K:.1f}" if pd.notna(lat.StochRSI_K) else "—",""),
        ("MACD",f"{lat.MACD:.2f}","+" if lat.MACD>lat.MACD_Sig else "-"),
        ("ADX",f"{lat.ADX:.1f}","Xu hướng✅" if lat.ADX>25 else "Sideway⚠️"),
        ("VWAP",f"{lat.VWAP:,.0f}","Trên✅" if lat.Close>lat.VWAP else "Dưới❌"),
        ("CMF",f"{lat.CMF:.3f}" if pd.notna(lat.CMF) else "—","Vào🟢" if lat.CMF>0.1 else "Ra🔴" if lat.CMF<-0.1 else "Trung tính"),
        ("MFI",f"{lat.MFI:.1f}" if pd.notna(lat.MFI) else "—","OB🔴" if lat.MFI>75 else "OS🟢" if lat.MFI<25 else "Bình thường"),
        ("OBV",fmt(lat.OBV),"Tích lũy✅" if lat.OBV>lat.OBV_EMA else "Phân phối❌"),
        ("BB Width",f"{lat.BB_width*100:.1f}%","Bó hẹp⚠️" if lat.BB_width<0.05 else "BT"),
        ("Vol/TB",f"×{lat.Vol_Ratio:.2f}","Đột biến📢" if lat.Vol_Ratio>1.5 else "BT"),
        ("EMA9",f"{lat.EMA9:,.0f}","Tren EMA21 OK" if lat.EMA9>lat.EMA21 else "Duoi EMA21"),
        ("EMA200",f"{lat.EMA200:,.0f}" if pd.notna(lat.EMA200) else "—","Trên✅" if pd.notna(lat.EMA200) and lat.Close>lat.EMA200 else "Dưới❌"),
    ]
    st.dataframe(pd.DataFrame(ind_tbl,columns=["Chỉ báo","Giá trị","Trạng thái"]),
                 use_container_width=True,hide_index=True)

# ── TAB 2: CƠ BẢN ───────────────────────────────────────────────────────────
with tab2:
    if not rat.empty or not inc.empty:
        # Metrics row
        st.markdown("### 📊 Chỉ số tài chính (kỳ mới nhất)")
        f1,f2,f3,f4,f5,f6,f7 = st.columns(7)
        f1.markdown(card("P/E",f"{fa['pe']:.1f}x" if fa['pe'] else "—",
            "#00d97e" if fa['pe'] and 0<fa['pe']<15 else "#f5a623" if fa['pe'] and fa['pe']<22 else "#ff3d5a"),unsafe_allow_html=True)
        f2.markdown(card("P/B",f"{fa['pb']:.2f}x" if fa['pb'] else "—",
            "#00d97e" if fa['pb'] and 0<fa['pb']<2.5 else "#f5a623" if fa['pb'] and fa['pb']<4 else "#ff3d5a"),unsafe_allow_html=True)
        f3.markdown(card("EPS",f"{fa['eps']:,.0f}đ" if fa['eps'] else "—",
            "#00d97e" if fa['eps'] and fa['eps']>0 else "#ff3d5a"),unsafe_allow_html=True)
        f4.markdown(card("ROE",f"{fa['roe']:.1f}%" if fa['roe'] else "—",
            "#00d97e" if fa['roe'] and fa['roe']>15 else "#f5a623" if fa['roe'] and fa['roe']>10 else "#ff3d5a"),unsafe_allow_html=True)
        f5.markdown(card("ROA",f"{fa['roa']:.1f}%" if fa['roa'] else "—",
            "#00d97e" if fa['roa'] and fa['roa']>1.5 else "#f5a623" if fa['roa'] and fa['roa']>0.8 else "#ff3d5a"),unsafe_allow_html=True)
        # D/E hoặc VCSH/TS
        de_show=fa['de'] if fa['de'] else fa['eq_ta']
        de_lbl="D/E" if fa['de'] else "VCSH/TS%"
        de_str=(f"{de_show:.2f}x" if fa['de'] else f"{de_show:.1f}%") if de_show else "—"
        de_clr="#00d97e" if de_show and (de_show<1.5 if fa['de'] else de_show>6) else "#f5a623"
        f6.markdown(card(de_lbl,de_str,de_clr),unsafe_allow_html=True)
        cr_show=fa['cr'] if fa['cr'] else fa['ldr']
        cr_lbl="Current Ratio" if fa['cr'] else "LDR%"
        cr_str=(f"{cr_show:.2f}" if fa['cr'] else f"{cr_show:.0f}%") if cr_show else "—"
        cr_clr="#00d97e" if cr_show and (cr_show>1.5 if fa['cr'] else 50<cr_show<90) else "#f5a623"
        f7.markdown(card(cr_lbl,cr_str,cr_clr),unsafe_allow_html=True)

        # Charts
        for fig_f in build_fin_charts(fa):
            st.plotly_chart(fig_f,use_container_width=True)

        # Narrative analysis
        st.markdown("### 🔬 Phân tích sức khỏe tài chính")
        if fa['narrative']:
            for ico,title,desc,clr in fa['narrative']:
                st.markdown(narrative_card(ico,title,desc,clr),unsafe_allow_html=True)
        else:
            st.info("Chưa đủ dữ liệu để phân tích narrative.")

        # Growth & CAGR
        st.markdown("### 📈 Tăng trưởng")
        ga,gb,gc,gd = st.columns(4)
        ga.metric("Doanh thu CAGR",f"{fa['rev_cagr']:.1f}%/năm" if fa['rev_cagr'] else "—",
            "Tốt✅" if fa['rev_cagr'] and fa['rev_cagr']>10 else "Trung bình⚠️" if fa['rev_cagr'] else "—")
        gb.metric("EPS CAGR",f"{fa['eps_cagr']:.1f}%/năm" if fa['eps_cagr'] else "—",
            "Tốt✅" if fa['eps_cagr'] and fa['eps_cagr']>10 else "")
        gc.metric("Chất lượng LN (OCF/Net)",
            f"{fa['fcf_quality']:.2f}x" if fa['fcf_quality'] else "—",
            "Cao✅" if fa['fcf_quality'] and fa['fcf_quality']>1 else "Thấp⚠️" if fa['fcf_quality'] else "")
        gd.metric("Altman Z-Score",
            f"{fa['z_score']}" if fa['z_score'] else "N/A (ngân hàng)" if fa['is_bank'] else "—",
            fa['z_zone'] if fa['z_zone'] else "")

        # Du Pont
        if fa['dupont']:
            st.markdown("### 🔩 Du Pont — Phân rã ROE")
            dp = fa['dupont']
            da,db,dc,dd = st.columns(4)
            da.metric("Biên LN ròng",f"{dp['net_margin']:.1f}%","Sinh lời")
            db.metric("Vòng quay TS",f"{dp['asset_turnover']:.2f}x","Hiệu quả")
            dc.metric("Đòn bẩy tài chính",f"{dp['equity_multiplier']:.1f}x","Leverage")
            dd.metric("Driver chính",dp['driver'],"Nguồn tăng ROE")
            st.caption(f"ROE ≈ {dp['net_margin']:.1f}% × {dp['asset_turnover']:.2f} × {dp['equity_multiplier']:.1f} = {dp['roe_check']:.1f}%")

        # Scorecard
        if f_items:
            st.markdown("### ✅ Chấm điểm cơ bản")
            chip_cols=st.columns(len(f_items))
            for col,item in zip(chip_cols,f_items):
                col.markdown(fund_chip(item),unsafe_allow_html=True)
            flbl="Cơ bản MẠNH ✅" if f_score>=3 else "Cơ bản KHÁ ⚠️" if f_score>=0 else "Cơ bản YẾU ❌"
            fclr="#00d97e" if f_score>=3 else "#f5a623" if f_score>=0 else "#ff3d5a"
            st.markdown(f"""<div style='margin-top:10px;background:#0c1d2e;border:1px solid {fclr}60;
              border-radius:10px;padding:12px 18px;display:flex;align-items:center;gap:16px;'>
              <div style='font-size:28px;font-weight:700;color:{fclr};'>{f_score:+.1f}</div>
              <div style='font-size:16px;font-weight:600;color:{fclr};'>{flbl}</div>
              <div style='font-size:13px;color:#6a9cc8;'>≥3 điểm = nền tảng đủ tốt để cân nhắc mua</div>
            </div>""",unsafe_allow_html=True)

        # ── Graham Number & PEG ──
        bvps = sg('book_value_per_share',(rat,fa['ryc'][-1] if fa['ryc'] else None),(inc,fa['iyc'][-1] if fa['iyc'] else None)) if fa['ryc'] or fa['iyc'] else None
        graham_n = None
        if fa['eps'] and bvps and fa['eps']>0 and bvps>0:
            graham_n = round((22.5 * fa['eps'] * bvps)**0.5, 0)
        peg = round(fa['pe']/fa['eps_cagr'],2) if fa['pe'] and fa['eps_cagr'] and fa['eps_cagr']>0 else None

        # ── TCBS analyst data ──
        tcbs_ov_local = tcbs_ov if tcbs_ov else {}
        pt_data = tcbs_pt if tcbs_pt else []

        # ── Valuation analysis ──
        st.markdown("### 💎 Định giá chuyên sâu")
        va1,va2,va3,va4 = st.columns(4)

        # Sector P/E context
        sym_sector = next((s for s,ps in SECTOR_PEERS.items() if symbol in ps), None)
        sector_pe = SECTOR_PE_MEDIAN.get(sym_sector, None)
        pe_vs_sector = None
        if fa['pe'] and sector_pe:
            pe_vs_sector = (fa['pe'] - sector_pe) / sector_pe * 100

        va1.markdown(f"""<div style='background:#0c1d2e;border:1px solid #163350;border-radius:12px;padding:14px;'>
          <div style='font-size:12px;color:#6a9cc8;margin-bottom:5px;'>P/E vs Ngành ({sym_sector or "—"})</div>
          <div style='font-size:20px;font-weight:700;color:{"#00d97e" if pe_vs_sector and pe_vs_sector<-10 else "#ff3d5a" if pe_vs_sector and pe_vs_sector>20 else "#f5a623"};'>
            {"Rẻ hơn" if pe_vs_sector and pe_vs_sector<-10 else "Đắt hơn" if pe_vs_sector and pe_vs_sector>20 else "Hợp lý"}
          </div>
          <div style='font-size:13px;color:#6a9cc8;'>P/E={fa["pe"]:.1f}x vs Ngành {sector_pe}x ({pe_vs_sector:+.0f}%)</div>
        </div>""" if fa['pe'] and sector_pe else f"""<div style='background:#0c1d2e;border:1px solid #163350;border-radius:12px;padding:14px;'>
          <div style='font-size:12px;color:#6a9cc8;'>P/E vs Ngành</div><div style='font-size:18px;color:#8baed4;'>—</div>
        </div>""", unsafe_allow_html=True)

        va2.markdown(f"""<div style='background:#0c1d2e;border:1px solid #163350;border-radius:12px;padding:14px;'>
          <div style='font-size:12px;color:#6a9cc8;margin-bottom:5px;'>PEG Ratio</div>
          <div style='font-size:20px;font-weight:700;color:{"#00d97e" if peg and peg<1 else "#f5a623" if peg and peg<2 else "#ff3d5a"};'>
            {f"{peg:.2f}" if peg else "—"}</div>
          <div style='font-size:12px;color:#6a9cc8;'>{"<1: Định giá hấp dẫn" if peg and peg<1 else "<2: Hợp lý" if peg and peg<2 else ">2: Đắt" if peg else "Cần EPS CAGR"}</div>
        </div>""", unsafe_allow_html=True)

        va3.markdown(f"""<div style='background:#0c1d2e;border:1px solid #163350;border-radius:12px;padding:14px;'>
          <div style='font-size:12px;color:#6a9cc8;margin-bottom:5px;'>Graham Number</div>
          <div style='font-size:20px;font-weight:700;color:{"#00d97e" if graham_n and fa["pe"] and float(lat.Close)<graham_n else "#ff3d5a" if graham_n else "#8baed4"};'>
            {f"{graham_n:,.0f}đ" if graham_n else "—"}</div>
          <div style='font-size:12px;color:#6a9cc8;'>{"Giá < Graham: Rẻ" if graham_n and float(lat.Close)<graham_n else "Giá > Graham: Đắt" if graham_n else "Cần EPS & BVPS"}</div>
        </div>""", unsafe_allow_html=True)

        # TCBS price target
        if pt_data:
            try:
                pt_avg = sum(p.get('targetPrice', p.get('priceTarget', 0)) for p in pt_data[:5]) / min(5,len(pt_data))
                pt_upside = (pt_avg - float(lat.Close)) / float(lat.Close) * 100
                va4.metric("🎯 Price Target (TCBS)", f"{pt_avg:,.0f}đ",
                    f"Upside {pt_upside:+.1f}%" if pt_upside else "")
            except: va4.markdown("", unsafe_allow_html=True)
        elif tcbs_ov_local:
            mc_val = tcbs_ov_local.get('marketCap', tcbs_ov_local.get('capitalization'))
            va4.metric("Vốn hóa (TCBS)", fmt(mc_val) if mc_val else "—")

        # Margin trend chart
        gm_s=gs('gross_margin',rat,fa['ryc']); nm_s=gs('net_margin',rat,fa['ryc'])
        def tp2(a):
            if a is None: return None
            return a*100 if a.dropna().abs().max()<2 else a
        gm_s=tp2(gm_s); nm_s=tp2(nm_s)
        if gm_s is not None or nm_s is not None:
            fig_mg=go.Figure()
            if gm_s is not None:
                fig_mg.add_trace(go.Scatter(x=list(gm_s.index),y=gm_s.values,name="Biên gộp%",
                    mode="lines+markers",line=dict(color="#a78bfa",width=2),marker=dict(size=8)))
            if nm_s is not None:
                fig_mg.add_trace(go.Scatter(x=list(nm_s.index),y=nm_s.values,name="Biên ròng%",
                    mode="lines+markers",line=dict(color="#22d3ee",width=2),marker=dict(size=8)))
            # Add trend annotation
            if nm_s is not None and len(nm_s.dropna())>=2:
                nm_clean=nm_s.dropna()
                trend="Biên ròng đang MỞ RỘNG" if nm_clean.iloc[-1]>nm_clean.iloc[-2] else "Biên ròng đang THU HẸP"
                trend_clr="#00d97e" if "MỞ" in trend else "#ff3d5a"
                fig_mg.add_annotation(x=list(nm_s.index)[-1],y=float(nm_clean.iloc[-1]),
                    text=f" {trend}",font=dict(color=trend_clr,size=11),showarrow=False,xanchor="left")
            fig_mg.update_layout(height=240,title="Xu hướng biên lợi nhuận (%)",template="plotly_dark",**CHART_STYLE)
            fig_mg.layout.title.font.color="#8baed4"
            st.plotly_chart(fig_mg,use_container_width=True)

        with st.expander("📋 Raw data — Bảng chỉ số đầy đủ"):
            disp=[c for c in rat.columns if c not in ["ticker","id"]]
            st.dataframe(rat[disp].reset_index(drop=True),use_container_width=True,hide_index=True)
    else:
        st.warning("Không lấy được dữ liệu tài chính từ KBS. Kiểm tra mã hoặc kết nối.")

# ── TAB 3: DÒNG TIỀN ────────────────────────────────────────────────────────
with tab3:
    st.markdown("### 💰 Phân tích dòng tiền (OBV · CMF · MFI)")
    # Key metrics
    d1,d2,d3,d4 = st.columns(4)
    obv_trend = "Tích lũy🟢" if lat.OBV>lat.OBV_EMA else "Phân phối🔴"
    cmf_val = float(lat.CMF) if pd.notna(lat.CMF) else 0
    mfi_val = float(lat.MFI) if pd.notna(lat.MFI) else 50
    d1.metric("OBV vs EMA",obv_trend,"Tích lũy khi OBV>EMA")
    d2.metric("CMF (20 phiên)",f"{cmf_val:.3f}","Dòng vào🟢" if cmf_val>0.1 else "Dòng ra🔴" if cmf_val<-0.1 else "Trung tính")
    d3.metric("MFI (14 phiên)",f"{mfi_val:.0f}","OB>75🔴" if mfi_val>75 else "OS<25🟢" if mfi_val<25 else "Bình thường")
    avg_up=df[df["Close"]>=df["Open"]]["Vol_Ratio"].tail(20).mean()
    avg_dn=df[df["Close"]< df["Open"]]["Vol_Ratio"].tail(20).mean()
    d4.metric("Vol TB: tăng vs giảm",f"×{avg_up:.2f} / ×{avg_dn:.2f}","Mua ưu thế🟢" if avg_up>avg_dn else "Bán ưu thế🔴")

    # Chart
    fig_cf = build_cashflow_chart(df)
    if fig_cf: st.plotly_chart(fig_cf,use_container_width=True)

    # Pump/dump detection
    st.markdown("### 🔍 Phát hiện bơm/xả")
    d20=df.tail(20).copy()
    pump=d20[(d20["Vol_Ratio"]>2.0)&(d20["Close"]>d20["Open"])&(d20["Close"].pct_change()>0.03)]
    dump=d20[(d20["Vol_Ratio"]>2.0)&(d20["Close"]<d20["Open"])&(d20["Close"].pct_change()<-0.03)]
    last5=d20.tail(5)
    price_up=float(last5["Close"].iloc[-1])>float(last5["Close"].iloc[0])
    vol_down_5=float(last5["Volume"].iloc[-1])<float(last5["Volume"].iloc[0])
    obv_div = price_up and bool(df["OBV"].tail(5).iloc[-1]<df["OBV"].tail(5).iloc[0])
    cmf_neg = cmf_val < -0.05
    no_signal = True
    if len(pump)>0:
        st.warning(f"**🚨 DẤU HIỆU BƠM** — {len(pump)} phiên trong 20 phiên gần nhất: giá tăng >3% + volume >2x TB. Cẩn thận bẫy thanh khoản, tay to có thể đang xả hàng ở vùng cao.")
        no_signal=False
    if len(dump)>0:
        st.error(f"**🔴 DẤU HIỆU XẢ MẠNH** — {len(dump)} phiên: giá giảm >3% + volume >2x TB. Áp lực bán lớn, tránh bắt đáy vội.")
        no_signal=False
    if obv_div:
        st.warning("**⚠️ PHÂN KỲ OBV/GIÁ** — Giá tăng nhưng OBV giảm 5 phiên gần nhất. Thiếu dòng tiền thực — rủi ro đảo chiều cao.")
        no_signal=False
    if price_up and vol_down_5:
        st.warning("**⚠️ PHÂN KỲ VOLUME** — Giá tăng nhưng khối lượng giảm dần. Xu hướng tăng đang suy yếu — không đủ lực để tiếp diễn.")
        no_signal=False
    if cmf_neg:
        st.info(f"**📉 CMF ÂM ({cmf_val:.3f})** — Dòng tiền đang rời khỏi cổ phiếu. Áp lực bán ngầm dù giá chưa giảm mạnh.")
        no_signal=False
    if df["Vol_Ratio"].tail(3).mean()<0.3:
        st.info("**😴 THANH KHOẢN CẠN** — Volume 3 phiên liên tiếp <30% TB. Thị trường mất quan tâm — không nên giao dịch.")
        no_signal=False
    if no_signal:
        st.success("**✅ DÒNG TIỀN BÌNH THƯỜNG** — Không phát hiện dấu hiệu bơm/xả bất thường. Volume ổn định, không có tích lũy/phân phối cực đoan.")

    # Volume trend table
    st.markdown("### 📊 Bảng khối lượng 15 phiên gần nhất")
    vt=df.tail(15)[["Date","Close","Volume","Vol_Ratio","OBV","CMF"]].copy()
    vt["Xu hướng"]=vt["Close"].diff().apply(lambda x:"📈" if x>0 else "📉")
    vt["Volume"]=vt["Volume"].apply(lambda x:f"{x/1e6:.1f}M")
    vt["Vol/TB"]=vt["Vol_Ratio"].apply(lambda x:f"×{x:.2f}")
    vt["OBV"]=vt["OBV"].apply(lambda x:fmt(x))
    vt["CMF"]=vt["CMF"].apply(lambda x:f"{x:.3f}" if pd.notna(x) else "—")
    vt["Close"]=vt["Close"].apply(lambda x:f"{x:,.0f}")
    vt["Date"]=vt["Date"].dt.strftime("%d/%m")
    st.dataframe(vt[["Date","Close","Xu hướng","Volume","Vol/TB","OBV","CMF"]].reset_index(drop=True),
                 use_container_width=True,hide_index=True)

# ── TAB 4: SO SÁNH NGÀNH ────────────────────────────────────────────────────
with tab4:
    st.markdown("### 🏭 So sánh với cùng ngành")
    # Tìm ngành của mã
    current_sector = None
    for sector, peers in SECTOR_PEERS.items():
        if symbol in peers:
            current_sector = sector; break
    if current_sector is None: current_sector = st.selectbox("Chọn ngành",list(SECTOR_PEERS.keys()))
    else: st.info(f"**Ngành:** {current_sector}")

    peers = [p for p in SECTOR_PEERS[current_sector] if p != symbol]
    selected_peers = st.multiselect("Chọn mã so sánh",peers,default=peers[:4])
    compare_syms = [symbol] + selected_peers

    if st.button("🔄 Tải dữ liệu so sánh",use_container_width=False):
        compare_data = []
        prog = st.progress(0)
        for i, sym2 in enumerate(compare_syms):
            prog.progress((i+1)/len(compare_syms), f"Đang tải {sym2}...")
            try:
                df2 = fetch_price(sym2, 180)
                rat2 = fetch_ratio(sym2)
                inc2 = fetch_income(sym2)
                fa2 = fundamental_analysis(rat2, inc2, pd.DataFrame(), pd.DataFrame())
                df2i = add_indicators(df2)
                sig2,_,sc2 = calc_signal(df2i)
                chg_1m = (float(df2i["Close"].iloc[-1])/float(df2i["Close"].iloc[-22])-1)*100 if len(df2i)>22 else 0
                chg_3m = (float(df2i["Close"].iloc[-1])/float(df2i["Close"].iloc[-66])-1)*100 if len(df2i)>66 else 0
                compare_data.append({
                    "Mã":sym2, "Giá":f"{df2i['Close'].iloc[-1]:,.0f}",
                    "+/-1T":f"{chg_1m:+.1f}%", "+/-3T":f"{chg_3m:+.1f}%",
                    "P/E":f"{fa2['pe']:.1f}x" if fa2['pe'] else "—",
                    "P/B":f"{fa2['pb']:.2f}x" if fa2['pb'] else "—",
                    "ROE":f"{fa2['roe']:.1f}%" if fa2['roe'] else "—",
                    "EPS CAGR":f"{fa2['eps_cagr']:.1f}%" if fa2['eps_cagr'] else "—",
                    "Tín hiệu KT":sig2,
                    "⭐":round(sc2,1)
                })
            except: compare_data.append({"Mã":sym2,"Giá":"—","+/-1T":"—","+/-3T":"—","P/E":"—","P/B":"—","ROE":"—","EPS CAGR":"—","Tín hiệu KT":"—","⭐":"—"})
        prog.empty()
        if compare_data:
            cdf = pd.DataFrame(compare_data)
            # Highlight mã hiện tại
            st.dataframe(cdf,use_container_width=True,hide_index=True,
                column_config={"⭐":st.column_config.NumberColumn("Điểm KT",format="%.1f")})
            # Chart P/E comparison
            valid = [(r["Mã"],float(r["P/E"].replace("x","").replace("—","0"))) for r in compare_data if r["P/E"]!="—"]
            if valid:
                mcs,pes=zip(*[(m,v) for m,v in valid if v>0])
                fig_pe=go.Figure(go.Bar(x=list(mcs),y=list(pes),
                    marker_color=["#4a9ef8" if m==symbol else "#163350" for m in mcs],
                    text=[f"{v:.1f}x" for v in pes],textposition="outside"))
                fig_pe.update_layout(height=280,title="So sánh P/E",template="plotly_dark",**CHART_STYLE)
                fig_pe.layout.title.font.color="#8baed4"
                st.plotly_chart(fig_pe,use_container_width=True)
    else:
        st.info("Nhấn **Tải dữ liệu so sánh** để xem bảng peer comparison.")

# ── TAB 5: QUÉT MÃ ──────────────────────────────────────────────────────────
with tab5:
    st.markdown("### 🔍 Quét mã tiềm năng — Top 5 dấu hiệu tăng")
    scan_sector = st.selectbox("Quét ngành",list(SECTOR_PEERS.keys()),key="scan_sec")
    scan_peers = SECTOR_PEERS[scan_sector]
    if st.button("🚀 Bắt đầu quét",use_container_width=False):
        results = []
        prog2 = st.progress(0)
        for i, sym2 in enumerate(scan_peers):
            prog2.progress((i+1)/len(scan_peers), f"Quét {sym2}...")
            r2 = scan_stock(sym2)
            if r2: results.append(r2)
        prog2.empty()
        if results:
            # Sort: điểm cao + RSI 35-65 + CMF dương + Vol tăng
            def composite_score(r2):
                s = r2['score']
                if 35<=r2['rsi']<=65: s+=1
                if r2['cmf']>0.05: s+=0.8
                if r2['mfi']<60: s+=0.5
                if r2['vol_ratio']>1.2: s+=0.7
                if r2['adx']>20: s+=0.5
                return s
            results.sort(key=composite_score, reverse=True)
            top5 = results[:5]
            st.markdown("#### 🌟 Top 5 mã tiềm năng tuần này")
            for rank, r2 in enumerate(top5, 1):
                clr=SIG_COLOR.get(r2['sig'],"#8baed4")
                chg_clr="#00d97e" if r2['chg1d']>=0 else "#ff3d5a"
                flags_str = "  |  ".join(flags)
                rank_str = "Top " + str(rank)
                st.markdown(
                    f"<div style='background:#0c1d2e;border:1px solid #163350;"
                    f"border-left:3px solid {clr};"
                    "border-radius:0 12px 12px 0;padding:12px 16px;margin:6px 0;"
                    "display:flex;align-items:center;gap:16px;flex-wrap:wrap;'>"
                    f"<b style='font-size:18px;color:#6a9cc8;'>{rank_str}</b>"
                    f"<span style='font-size:20px;font-weight:700;color:#fff;'>{r2['sym']}</span>"
                    f"<span style='color:{clr};font-weight:600;'>{r2['sig']} ({r2['score']:+.1f})</span>"
                    f"<span style='color:#fff;'>{r2['close']:,.0f}đ &nbsp;"
                    f"{r2['chg1d']:+.2f}%</span>"
                    f"<span style='color:#6a9cc8;font-size:12px;'>RSI {r2['rsi']:.0f} "
                    f"ADX {r2['adx']:.0f} CMF {r2['cmf']:.2f}</span>"
                    f"<span style='color:#22d3ee;font-size:12px;'>{flags_str}</span>"
                    "</div>",
                    unsafe_allow_html=True
                )
            # Full table
            with st.expander("📋 Bảng đầy đủ tất cả mã đã quét"):
                scan_tbl=[{"Mã":r2['sym'],"Giá":f"{r2['close']:,.0f}","1D":f"{r2['chg1d']:+.1f}%",
                    "5D":f"{r2['chg5d']:+.1f}%","Tín hiệu":r2['sig'],"Score":r2['score'],
                    "RSI":f"{r2['rsi']:.0f}","ADX":f"{r2['adx']:.0f}","CMF":f"{r2['cmf']:.3f}",
                    "MFI":f"{r2['mfi']:.0f}","Vol/TB":f"×{r2['vol_ratio']:.1f}"} for r2 in results]
                st.dataframe(pd.DataFrame(scan_tbl),use_container_width=True,hide_index=True)
        else:
            st.warning("Không quét được dữ liệu. Kiểm tra kết nối mạng.")
    else:
        st.info("Nhấn **Bắt đầu quét** để tìm 5 mã tiềm năng nhất trong ngành.")

# ── TAB 6: TIN TỨC ──────────────────────────────────────────────────────────
with tab6:
    st.markdown(f"### 📰 Tin tức & Sự kiện — {symbol}")
    sym_sector_news = next((s for s,ps in SECTOR_PEERS.items() if symbol in ps), "")

    col_news1, col_news2 = st.columns([3,2])
    with col_news1:
        st.markdown("#### 🔍 Tin tức từ web (AI search)")
        if st.button("🔄 Tải tin tức mới nhất", key="load_news"):
            with st.spinner("Đang tìm kiếm tin tức..."):
                news_data = fetch_news_ai(symbol, sym_sector_news)
        else:
            news_data = {"news":[], "analyst_consensus":{}, "key_events":[]}

        news_items = news_data.get("news", [])
        if news_items:
            for item in news_items[:8]:
                sent = item.get("sentiment","neutral")
                sent_clr = "#00d97e" if sent=="positive" else "#ff3d5a" if sent=="negative" else "#8baed4"
                sent_ico = "📈" if sent=="positive" else "📉" if sent=="negative" else "➡️"
                st.markdown(
                    f"<div style='background:#0c1d2e;border-left:3px solid {sent_clr};"
                    f"border-radius:0 10px 10px 0;padding:10px 14px;margin:6px 0;'>"
                    f"<div style='font-size:11px;color:#4a6080;'>{item.get('date','')}</div>"
                    f"<div style='font-size:14px;font-weight:600;color:#fff;margin:3px 0;'>"
                    f"{sent_ico} {item.get('title','')}</div>"
                    f"<div style='font-size:12px;color:#8baed4;'>{item.get('summary','')}</div>"
                    f"</div>",
                    unsafe_allow_html=True)
        else:
            st.info("Nhấn **Tải tin tức mới nhất** để AI tìm kiếm tin tức cho mã này.")

        # Key events
        key_events = news_data.get("key_events", [])
        if key_events:
            st.markdown("#### 📌 Sự kiện quan trọng")
            for ev in key_events:
                st.markdown(f"- {ev}")

    with col_news2:
        # TCBS activity news
        st.markdown("#### 📡 Tin từ TCBS Activity")
        tcbs_news_items = fetch_tcbs_news(symbol)
        if tcbs_news_items:
            for item in tcbs_news_items[:8]:
                title = item.get('title', item.get('name', item.get('content','—')))[:80]
                date_str = item.get('publishDate', item.get('date', ''))[:10]
                st.markdown(
                    f"<div style='background:#0c1d2e;border:1px solid #163350;"
                    f"border-radius:8px;padding:8px 12px;margin:4px 0;'>"
                    f"<div style='font-size:11px;color:#4a6080;'>{date_str}</div>"
                    f"<div style='font-size:13px;color:#cce0ff;'>{title}</div>"
                    f"</div>",
                    unsafe_allow_html=True)
        else:
            st.info("Không có tin từ TCBS. TCBS API có thể đang giới hạn.")

        # Analyst consensus
        analyst = news_data.get("analyst_consensus", {})
        if analyst:
            st.markdown("#### 💬 Khuyến nghị phân tích viên")
            action = analyst.get("action","—")
            target = analyst.get("target_price")
            n_analysts = analyst.get("num_analysts",0)
            action_clr = "#00d97e" if action in ("Buy","Strong Buy") else "#ff3d5a" if action in ("Sell","Strong Sell") else "#f5a623"
            st.markdown(
                f"<div style='background:#0c1d2e;border:1px solid #163350;border-radius:10px;padding:14px;'>"
                f"<div style='font-size:18px;font-weight:700;color:{action_clr};'>{action}</div>"
                f"<div style='font-size:14px;color:#cce0ff;'>Target: {target:,.0f}đ</div>" if target else
                f"<div style='font-size:14px;color:#cce0ff;'>Target: —</div>"
                f"<div style='font-size:12px;color:#6a9cc8;'>{n_analysts} analysts</div>"
                f"</div>",
                unsafe_allow_html=True)

        # TCBS analyst recommendations
        if tcbs_pt:
            st.markdown("#### 🎯 Price Targets (TCBS)")
            pt_df = pd.DataFrame(tcbs_pt[:5])
            disp_cols = [c for c in ['analyst','firm','targetPrice','priceTarget','action','date'] if c in pt_df.columns]
            if disp_cols:
                st.dataframe(pt_df[disp_cols], use_container_width=True, hide_index=True)


# ── TAB 7: TỔNG HỢP ─────────────────────────────────────────────────────────
with tab7:
    st.markdown("### 🎯 Đánh giá tổng hợp")
    obv_trend = "Tích lũy🟢" if lat.OBV>lat.OBV_EMA else "Phân phối🔴"
    cmf_val = float(lat.CMF) if pd.notna(lat.CMF) else 0
    mfi_val = float(lat.MFI) if pd.notna(lat.MFI) else 50
    avg_up=df[df["Close"]>=df["Open"]]["Vol_Ratio"].tail(20).mean()
    avg_dn=df[df["Close"]< df["Open"]]["Vol_Ratio"].tail(20).mean()
    obv_score = 1 if lat.OBV>lat.OBV_EMA else -1
    cmf_score = 1 if cmf_val>0.1 else -1 if cmf_val<-0.1 else 0
    mfi_score = -1 if mfi_val>75 else 1 if mfi_val<25 else 0
    cf_total = (obv_score+cmf_score+mfi_score)/3*5
    tech_n = max(-7,min(7,score))
    fund_n = max(-5,min(5,f_score))
    cf_n   = max(-5,min(5,cf_total))
    total  = tech_n*0.40 + fund_n*0.35 + cf_n*0.25
    sc1,sc2,sc3,sc4 = st.columns(4)
    sc1.markdown(score_pill("📉 Kỹ thuật",round(tech_n,1),"Trọng số 40%"),unsafe_allow_html=True)
    sc2.markdown(score_pill("📊 Cơ bản",round(fund_n,1),"Trọng số 35%"),unsafe_allow_html=True)
    sc3.markdown(score_pill("💰 Dòng tiền",round(cf_n,1),"Trọng số 25%"),unsafe_allow_html=True)
    if   total>=3:   final="MUA MẠNH"; fc="#00d97e"
    elif total>=1.2: final="MUA";       fc="#00b862"
    elif total>=0.4: final="THEO DÕI MUA"; fc="#7fcf50"
    elif total>-0.4: final="TRUNG TÍNH"; fc="#8baed4"
    elif total>-1.2: final="THEO DÕI BÁN"; fc="#f5a623"
    elif total>-3:   final="BÁN"; fc="#ff3d5a"
    else:            final="BÁN MẠNH"; fc="#cc1133"
    sc4.markdown(
        f"<div style='background:#0c1d2e;border:2px solid {fc}80;border-radius:12px;padding:14px;text-align:center;'>"
        f"<div style='font-size:12px;color:#6a9cc8;font-weight:500;margin-bottom:4px;'>KẾT LUẬN TỔNG HỢP</div>"
        f"<div style='font-size:22px;font-weight:700;color:{fc};'>{final}</div>"
        f"<div style='font-size:13px;color:#6a9cc8;margin-top:4px;'>Điểm: {total:+.2f}</div></div>",
        unsafe_allow_html=True)
    st.markdown("---")
    struct, struct_clr = detect_market_structure(df)
    ema_align="Xếp hàng tăng" if lat.EMA9>lat.EMA21>lat.EMA50 else "Xếp hàng giảm" if lat.EMA9<lat.EMA21<lat.EMA50 else "Trung tính"
    st.markdown(
        f"<div style='background:#0c1d2e;border:1px solid {fc}60;border-radius:12px;padding:18px 22px;'>"
        f"<div style='font-size:12px;color:#6a9cc8;margin-bottom:10px;'>PHÂN TÍCH — {symbol} · {datetime.now().strftime('%d/%m/%Y %H:%M')}</div>"
        f"<div style='font-size:24px;font-weight:700;color:{fc};margin-bottom:14px;'>{final}</div>"
        "<div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:18px;font-size:13px;'>"
        "<div>"
        "<div style='color:#6a9cc8;margin-bottom:6px;font-weight:600;'>📉 KỸ THUẬT (40%)</div>"
        f"<div style='color:#cce0ff;line-height:1.8;'>Tín hiệu: {sig}<br>"
        f"EMA: {ema_align}<br>RSI {lat.RSI:.0f} · ADX {lat.ADX:.0f}<br>"
        f"Cấu trúc: {struct}</div></div>"
        "<div>"
        "<div style='color:#6a9cc8;margin-bottom:6px;font-weight:600;'>📊 CƠ BẢN (35%)</div>"
        f"<div style='color:#cce0ff;line-height:1.8;'>Điểm: {f_score:+.1f}<br>"
        f"{'Nền tảng vững' if f_score>=3 else 'Trung bình' if f_score>=0 else 'Yếu — thận trọng'}<br>"
        f"Rev CAGR: {f"{fa['rev_cagr']:.1f}%" if fa['rev_cagr'] else '—'}</div></div>"
        "<div>"
        "<div style='color:#6a9cc8;margin-bottom:6px;font-weight:600;'>💰 DÒNG TIỀN (25%)</div>"
        f"<div style='color:#cce0ff;line-height:1.8;'>OBV: {obv_trend}<br>"
        f"CMF: {cmf_val:+.3f}<br>MFI: {mfi_val:.0f}<br>"
        f"Vol: {'Mua uu the' if avg_up>avg_dn else 'Ban uu the'}</div></div>"
        "</div></div>",
        unsafe_allow_html=True)
    st.markdown("### 💡 Chiến lược đề xuất")
    if total>=2.5: pos,hz="15-20% danh mục","Trung hạn 2-4 tháng"
    elif total>=1.2: pos,hz="8-12% danh mục","Ngắn-Trung hạn"
    elif total>=0.4: pos,hz="3-5% thăm dò","Quan sát 1-2 tuần"
    else: pos,hz="Không mua","Chờ tín hiệu đảo chiều"
    s1,s2,s3,s4 = st.columns(4)
    s1.metric("Tỷ trọng đề xuất",pos,hz)
    s2.metric("Điểm vào",f"{trade['buy']:,} đ","Theo kỹ thuật")
    s3.metric("Stop Loss",f"{trade['sl']:,} đ",f"Rủi ro {trade['risk']*100:.1f}%")
    s4.metric("R:R",f"1:{trade['rr']:.1f}","Tot" if trade['rr']>=2 else "Can xem xet")
    st.markdown("### ⚠️ Rủi ro cần theo dõi")
    risks=[]
    if lat.RSI>75: risks.append("RSI quá mua — nguy cơ điều chỉnh")
    if lat.ADX<15: risks.append("ADX rất thấp — tín hiệu kỹ thuật kém tin cậy")
    if lat.BB_width<0.05: risks.append("BB bó hẹp — biến động lớn sắp xảy ra")
    if cmf_val<-0.1: risks.append("CMF âm — dòng tiền đang rút")
    if f_score<0: risks.append("Cơ bản yếu — không nên hold dài hạn")
    if fa.get('z_score') and fa['z_score']<1.81: risks.append(f"Altman Z={fa['z_score']} — rủi ro tài chính cao")
    if not risks: risks=["Không phát hiện rủi ro bất thường"]
    rc1,rc2=st.columns(2)
    for i,rk in enumerate(risks): (rc1 if i%2==0 else rc2).markdown(rk)
    st.markdown("---")
    st.caption(f"Phan tich tham khao — khong phai khuyen nghi dau tu. Du lieu: KBS · {datetime.now().strftime('%d/%m/%Y %H:%M')}")
