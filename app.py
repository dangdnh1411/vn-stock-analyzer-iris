"""
Pro Trader Terminal v7 — Production Ready
7 tabs: Kỹ thuật | Cơ bản | Dòng tiền | So sánh ngành | Quét mã | Tin tức | Tổng hợp
Data: KBS primary + TCBS fallback + Claude AI news
"""
import warnings; warnings.filterwarnings("ignore")
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import math, time, re, json, urllib.request

st.set_page_config(layout="wide", page_title="Pro Trader v7", page_icon="📈",
                   initial_sidebar_state="expanded")

# ══ CSS ═══════════════════════════════════════════════════════════════════════
st.markdown("""<style>
[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:#07121e!important}
[data-testid="stHeader"]{background:#07121e!important}
[data-testid="stSidebar"]{background:#0c1d2e!important;border-right:1px solid #163350}
section[data-testid="stSidebar"] *{color:#cce0ff!important;font-size:14px!important}
.stTabs [data-baseweb="tab-list"]{background:#0c1d2e;border-radius:10px;padding:5px;gap:4px}
.stTabs [data-baseweb="tab"]{background:transparent;color:#6a9cc8;border-radius:7px;
  padding:9px 16px;font-size:13px;font-weight:500;border:none}
.stTabs [aria-selected="true"]{background:#163350!important;color:#fff!important;font-weight:600!important}
[data-testid="metric-container"]{background:#0c1d2e!important;border:1px solid #163350!important;
  border-radius:12px!important;padding:14px 18px!important}
[data-testid="stMetricLabel"] p{color:#6a9cc8!important;font-size:12px!important;font-weight:500!important}
[data-testid="stMetricValue"]{color:#fff!important;font-size:24px!important;font-weight:700!important}
[data-testid="stButton"] button{background:#163350!important;color:#cce0ff!important;
  border:1px solid #2a5a8a!important;border-radius:8px!important;font-size:13px!important}
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

# ══ CONSTANTS ═════════════════════════════════════════════════════════════════
RESOLUTIONS = {"Ngày":"1D","Tuần":"1W","Tháng":"1M","1 giờ":"1H","15 phút":"15m","5 phút":"5m"}
PERIODS     = {"1 tháng":30,"3 tháng":90,"6 tháng":180,"1 năm":365,"2 năm":730}
SIG_COLOR   = {"MUA MẠNH":"#00d97e","MUA":"#00b862","THEO DÕI MUA":"#7fcf50",
               "TRUNG TÍNH":"#8baed4","THEO DÕI BÁN":"#f5a623","BÁN":"#ff3d5a","BÁN MẠNH":"#cc1133"}
CHART_STYLE = dict(
    paper_bgcolor="#07121e", plot_bgcolor="#07121e",
    font=dict(family="monospace",color="#8baed4",size=11),
    legend=dict(bgcolor="rgba(0,0,0,0)",font=dict(size=11,color="#8baed4")),
    margin=dict(l=10,r=60,t=30,b=10),
    xaxis=dict(showgrid=True,gridcolor="#102030",gridwidth=0.5,tickfont=dict(color="#4a6080",size=10)),
    yaxis=dict(showgrid=True,gridcolor="#102030",gridwidth=0.5,tickfont=dict(color="#4a6080",size=10)),
)
SECTOR_PEERS = {
    "Ngân hàng":    ["VCB","TCB","MBB","ACB","VPB","BID","CTG","STB","HDB","TPB","MSB","OCB","SHB"],
    "Bất động sản": ["VIC","VHM","NVL","DXG","KDH","PDR","DIG","BCM","HDG","CEO"],
    "Thép & KLB":   ["HPG","NKG","HSG","TIS","VGS","POM"],
    "Chứng khoán":  ["SSI","VND","HCM","MBS","VCI","FTS","BSI","CTS"],
    "Bán lẻ":       ["MWG","FRT","PNJ","DGW"],
    "Công nghệ":    ["FPT","CMG","ELC","VGI"],
    "Dầu khí":      ["GAS","PLX","PVD","PVS","BSR"],
    "Dược":         ["DHG","IMP","DMC","TRA","DBD"],
    "Tiêu dùng":    ["SAB","BHN","VNM","MCH","MSN","QNS"],
    "Điện":         ["REE","PC1","GEG","PGV","NT2"],
}
SECTOR_PE   = {"Ngân hàng":8.5,"Bất động sản":15.0,"Thép & KLB":10.0,
               "Chứng khoán":12.0,"Bán lẻ":20.0,"Công nghệ":18.0,
               "Dầu khí":9.0,"Dược":16.0,"Tiêu dùng":22.0,"Điện":14.0}
_META = ['item','item_id','item_en','unit','levels','row_number']

# ══ FIELD HELPERS ════════════════════════════════════════════════════════════
def ycols(df):
    """Cột năm — xử lý '2024' và '2024-Năm'."""
    if df is None or df.empty: return []
    return sorted([c for c in df.columns
                   if c not in _META and bool(re.search(r'\d{4}', str(c)))])

_ALIASES = {
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
    'book_value_per_share':['book_value_per_share','bvps'],
    'revenue':            ['revenue','net_revenue'],
    'net_profit':         ['net_profit','net_profit_after_tax'],
    'operating_cashflow': ['operating_cashflow','cash_from_operations'],
}

def sg(iid, *dfs_yrs):
    """Smart get từ nhiều DataFrame. dfs_yrs = [(df,yr), ...]"""
    for alias in _ALIASES.get(iid, [iid]):
        for df, yr in dfs_yrs:
            if df is None or df.empty or yr is None: continue
            if 'item_id' not in df.columns: continue
            row = df[df['item_id'] == alias]
            if not row.empty:
                v = pd.to_numeric(row[yr].values[0], errors='coerce')
                if pd.notna(v): return float(v)
    return None

def gs(iid, df, yc):
    """Lấy series theo năm từ long-format DataFrame."""
    if df is None or df.empty or not yc: return None
    for alias in _ALIASES.get(iid, [iid]):
        if 'item_id' not in df.columns: continue
        row = df[df['item_id'] == alias]
        if not row.empty:
            vals = pd.to_numeric(row[yc].values[0], errors='coerce')
            return pd.Series(vals, index=yc)
    return None

def pct(v): return v*100 if v is not None and abs(v) < 2 else v

def fmt(n, s=""):
    if n is None or (isinstance(n, float) and math.isnan(n)): return "—"
    n = float(n)
    if abs(n)>=1e12: return f"{n/1e12:.1f}T{s}"
    if abs(n)>=1e9:  return f"{n/1e9:.1f}B{s}"
    if abs(n)>=1e6:  return f"{n/1e6:.1f}M{s}"
    if abs(n)>=1e3:  return f"{n/1e3:.0f}K{s}"
    return f"{n:,.1f}{s}"

def to_pct_arr(arr):
    if arr is None: return None
    nz = arr.dropna()
    return arr * 100 if len(nz) > 0 and nz.abs().max() < 2 else arr

def cagr(s, e, yrs):
    if s and e and yrs > 0 and s > 0: return ((e/s)**(1/yrs)-1)*100
    return None

# ══ DATA LAYER ════════════════════════════════════════════════════════════════
@st.cache_data(ttl=60, show_spinner=False)
def fetch_price(sym, days, interval="1D"):
    end   = datetime.now().strftime("%Y-%m-%d")
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
        df["Date"]   = pd.to_datetime(df["Date"])
        return df.sort_values("Date").reset_index(drop=True)[["Date","Open","High","Low","Close","Volume"]]
    except:
        import yfinance as yf
        df = yf.download(f"{sym}.VN", start=start, end=end, progress=False, auto_adjust=True)
        if df.empty: raise RuntimeError(f"No data for {sym}")
        df = df.reset_index()
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        df = df.rename(columns={"Date":"Date","Open":"Open","High":"High","Low":"Low","Close":"Close","Volume":"Volume"})
        return df.sort_values("Date").reset_index(drop=True)[["Date","Open","High","Low","Close","Volume"]]

@st.cache_data(ttl=300, show_spinner=False)
def fetch_kbs_ratio(sym):
    try:
        from vnstock import Finance
        df = Finance(symbol=sym, source="KBS").ratio(period="year")
        return df if df is not None and not df.empty else pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_kbs_income(sym):
    try:
        from vnstock import Finance
        df = Finance(symbol=sym, source="KBS").income_statement(period="year")
        return df if df is not None and not df.empty else pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_kbs_balance(sym):
    try:
        from vnstock import Finance
        df = Finance(symbol=sym, source="KBS").balance_sheet(period="year")
        return df if df is not None and not df.empty else pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_kbs_cashflow(sym):
    try:
        from vnstock import Finance
        df = Finance(symbol=sym, source="KBS").cash_flow(period="year")
        return df if df is not None and not df.empty else pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_tcbs_data(sym):
    """TCBS làm source thứ 2."""
    out = {}
    base = "https://apipubaws.tcbs.com.vn"
    hdrs = {"User-Agent":"Mozilla/5.0","Accept":"application/json",
            "Referer":"https://tcinvest.tcbs.com.vn/","Origin":"https://tcinvest.tcbs.com.vn"}
    try:
        import requests as _r
        resp = _r.get(f"{base}/tcanalysis/v1/finance/{sym}/financialratio",
                      params={"quarterly":0,"page":0,"size":8}, headers=hdrs, timeout=10)
        if resp.status_code == 200:
            d = resp.json()
            rows = d if isinstance(d,list) else d.get("listFinancialRatio", d.get("data",[]))
            if rows: out['ratio'] = pd.DataFrame(rows)
    except: pass
    try:
        import requests as _r
        resp = _r.get(f"{base}/tcanalysis/v1/ticker/{sym}/overview", headers=hdrs, timeout=8)
        if resp.status_code == 200: out['overview'] = resp.json()
    except: pass
    try:
        import requests as _r
        resp = _r.get(f"{base}/tcanalysis/v1/ticker/{sym}/priceTarget", headers=hdrs, timeout=8)
        if resp.status_code == 200:
            d = resp.json()
            rows = d if isinstance(d,list) else d.get("data",[])
            if rows: out['price_target'] = rows
    except: pass
    return out

@st.cache_data(ttl=300, show_spinner=False)
def fetch_tcbs_news(sym):
    try:
        import requests as _r
        hdrs = {"User-Agent":"Mozilla/5.0","Accept":"application/json",
                "Referer":"https://tcinvest.tcbs.com.vn/","Origin":"https://tcinvest.tcbs.com.vn"}
        resp = _r.get(f"https://apipubaws.tcbs.com.vn/tcanalysis/v1/ticker/{sym}/activity-news",
                      params={"page":0,"size":15}, headers=hdrs, timeout=10)
        if resp.status_code == 200:
            d = resp.json()
            items = d if isinstance(d,list) else d.get("listActivityNews", d.get("data",[]))
            return items[:15]
    except: pass
    return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_news_ai(sym, sector=""):
    """Claude API + web_search cho tin tức."""
    prompt = (
        f"Search for latest news about {sym} stock Vietnam (HOSE/HNX) in last 7 days. "
        f"Find: earnings, analyst ratings, business events, regulatory news. Sector: {sector}. "
        f"Return ONLY valid JSON: "
        f'{{"news":[{{"date":"2025-05-28","title":"Title here","summary":"1-2 sentence summary","sentiment":"positive"}}],'
        f'"analyst_consensus":{{"action":"Buy","target_price":25000,"num_analysts":3}},'
        f'"key_events":["Event 1","Event 2"]}}'
    )
    try:
        payload = json.dumps({
            "model":"claude-haiku-4-5-20251001","max_tokens":2000,
            "tools":[{"type":"web_search_20250305","name":"web_search"}],
            "messages":[{"role":"user","content":prompt}]
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=payload,
            headers={"Content-Type":"application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=45) as resp:
            result = json.loads(resp.read())
        text = " ".join(c.get("text","") for c in result.get("content",[]) if c.get("type")=="text")
        # Extract largest valid JSON
        candidates = []; depth = 0; start = -1
        for i, ch in enumerate(text):
            if ch == '{':
                if depth == 0: start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start >= 0: candidates.append(text[start:i+1])
        candidates.sort(key=len, reverse=True)
        for c in candidates:
            try:
                d = json.loads(c)
                if "news" in d: return d
            except: pass
    except: pass
    return {"news":[], "analyst_consensus":{}, "key_events":[]}

@st.cache_data(ttl=300, show_spinner=False)
def scan_stock(sym, days=90):
    try:
        df = fetch_price(sym, days)
        if df.empty or len(df) < 30: return None
        df = add_indicators(df)
        sig, _, score = calc_signal(df)
        lat = df.iloc[-1]
        chg1d = (float(lat.Close)-float(df.iloc[-2].Close))/float(df.iloc[-2].Close)*100 if len(df)>1 else 0
        chg5d = (float(lat.Close)-float(df.iloc[-5].Close))/float(df.iloc[-5].Close)*100 if len(df)>5 else 0
        return dict(sym=sym, sig=sig, score=score, close=float(lat.Close),
                    chg1d=chg1d, chg5d=chg5d, rsi=float(lat.RSI),
                    vol_ratio=float(lat.Vol_Ratio), adx=float(lat.ADX) if pd.notna(lat.ADX) else 0,
                    cmf=float(lat.CMF) if pd.notna(lat.CMF) else 0,
                    mfi=float(lat.MFI) if pd.notna(lat.MFI) else 50)
    except: return None

# ══ TECHNICAL INDICATORS ═════════════════════════════════════════════════════
def add_indicators(df):
    c=df["Close"].astype(float); hi=df["High"].astype(float)
    lo=df["Low"].astype(float);  v=df["Volume"].astype(float)
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
    # Stoch RSI
    rmin=df["RSI"].rolling(14).min(); rmax=df["RSI"].rolling(14).max()
    stoch=(df["RSI"]-rmin)/(rmax-rmin).replace(0,np.nan)
    df["StochRSI_K"]=stoch.rolling(3).mean()*100
    df["StochRSI_D"]=df["StochRSI_K"].rolling(3).mean()
    # ATR & ADX
    tr=pd.concat([hi-lo,(hi-c.shift()).abs(),(lo-c.shift()).abs()],axis=1).max(axis=1)
    df["ATR"]=tr.ewm(span=14,adjust=False).mean()
    pdm=(hi.diff()).clip(lower=0).where(hi.diff()>lo.diff().abs(),0)
    ndm=(lo.diff().abs()).clip(lower=0).where(lo.diff().abs()>hi.diff(),0)
    a14=tr.ewm(span=14,adjust=False).mean()
    pdi=100*pdm.ewm(span=14,adjust=False).mean()/a14.replace(0,np.nan)
    ndi=100*ndm.ewm(span=14,adjust=False).mean()/a14.replace(0,np.nan)
    df["ADX"]=(100*(pdi-ndi).abs()/(pdi+ndi).replace(0,np.nan)).ewm(span=14,adjust=False).mean()
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
        obv.append(obv[-1]+df["Volume"].iloc[i] if df["Close"].iloc[i]>df["Close"].iloc[i-1]
                   else obv[-1]-df["Volume"].iloc[i] if df["Close"].iloc[i]<df["Close"].iloc[i-1]
                   else obv[-1])
    df["OBV"]=obv; df["OBV_EMA"]=pd.Series(obv,index=df.index).ewm(span=20,adjust=False).mean()
    # CMF
    mfm=((c-lo)-(hi-c))/(hi-lo).replace(0,np.nan)
    df["CMF"]=(mfm*v).rolling(20).sum()/v.rolling(20).sum()
    # MFI
    tp2=(hi+lo+c)/3; mf=tp2*v
    pos=mf.where(tp2>tp2.shift(1),0); neg=mf.where(tp2<tp2.shift(1),0)
    mfr=pos.rolling(14).sum()/neg.rolling(14).sum().replace(0,np.nan)
    df["MFI"]=100-100/(1+mfr)
    # A/D Line
    clv=((c-lo)-(hi-c))/(hi-lo).replace(0,np.nan)
    df["AD_Line"]=(clv*v).cumsum()
    # Ichimoku
    df["Ichi_Tenkan"]=(hi.rolling(9).max()+lo.rolling(9).min())/2
    df["Ichi_Kijun"] =(hi.rolling(26).max()+lo.rolling(26).min())/2
    df["Ichi_SpanA"] =((df["Ichi_Tenkan"]+df["Ichi_Kijun"])/2).shift(26)
    df["Ichi_SpanB"] =((hi.rolling(52).max()+lo.rolling(52).min())/2).shift(26)
    # Parabolic SAR
    try:
        psar=np.zeros(len(df)); bull=True; ep=float(lo.iloc[0]); af=0.02
        psar[0]=float(hi.iloc[0])
        for i in range(1,len(df)):
            if bull:
                psar[i]=psar[i-1]+af*(ep-psar[i-1])
                psar[i]=min(psar[i],float(lo.iloc[i-1]),float(lo.iloc[i-2]) if i>1 else float(lo.iloc[0]))
                if float(hi.iloc[i])>ep: ep=float(hi.iloc[i]); af=min(af+0.02,0.2)
                if float(lo.iloc[i])<psar[i]: bull=False; psar[i]=ep; ep=float(lo.iloc[i]); af=0.02
            else:
                psar[i]=psar[i-1]+af*(ep-psar[i-1])
                psar[i]=max(psar[i],float(hi.iloc[i-1]),float(hi.iloc[i-2]) if i>1 else float(hi.iloc[0]))
                if float(lo.iloc[i])<ep: ep=float(lo.iloc[i]); af=min(af+0.02,0.2)
                if float(hi.iloc[i])>psar[i]: bull=True; psar[i]=ep; ep=float(hi.iloc[i]); af=0.02
        df["PSAR"]=psar; df["PSAR_Bull"]=bool(bull)
    except: df["PSAR"]=np.nan; df["PSAR_Bull"]=True
    # Pivot Points
    if len(df)>1:
        prev=df.iloc[-2]
        ph,pl,pc=float(prev.High),float(prev.Low),float(prev.Close)
        pp=(ph+pl+pc)/3
        df["PP"]=pp; df["R1"]=2*pp-pl; df["R2"]=pp+(ph-pl)
        df["S1"]=2*pp-ph; df["S2"]=pp-(ph-pl)
    # 52-week
    df["H52"]=df["Close"].expanding(min_periods=1).max() if len(df)<252 else df["Close"].rolling(252).max()
    df["L52"]=df["Close"].expanding(min_periods=1).min() if len(df)<252 else df["Close"].rolling(252).min()
    # Volume
    df["Vol_MA20"]=v.rolling(20).mean()
    df["Vol_Ratio"]=v/df["Vol_MA20"].replace(0,np.nan)
    df["EMA_State"]=np.where(df["EMA9"]>df["EMA21"],"bull","bear")
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

def auto_sr(df, n=3):
    hi=df["High"]; lo=df["Low"]
    phi=[i for i in range(1,len(df)-1) if hi.iloc[i]>=hi.iloc[i-1] and hi.iloc[i]>=hi.iloc[i+1]]
    pli=[i for i in range(1,len(df)-1) if lo.iloc[i]<=lo.iloc[i-1] and lo.iloc[i]<=lo.iloc[i+1]]
    return sorted([hi.iloc[i] for i in phi],reverse=True)[:n], sorted([lo.iloc[i] for i in pli])[:n]

# ══ SIGNAL ENGINE ════════════════════════════════════════════════════════════
def calc_signal(df):
    lat=df.iloc[-1]; prev=df.iloc[-2] if len(df)>1 else lat
    reasons=[]; score=0.0; c=float(lat.Close)
    # EMA alignment
    if lat.EMA9>lat.EMA21>lat.EMA50:   reasons.append("✅ EMA9>21>50 — xếp hàng tăng"); score+=1.5
    elif lat.EMA9<lat.EMA21<lat.EMA50: reasons.append("❌ EMA9<21<50 — xếp hàng giảm"); score-=1.5
    else:                               reasons.append("⚠️ EMA không đồng thuận — sideway")
    if pd.notna(lat.EMA200):
        if c>lat.EMA200: reasons.append("✅ Giá > EMA200 — uptrend dài hạn"); score+=1
        else:            reasons.append("❌ Giá < EMA200 — downtrend dài hạn"); score-=1
    # Golden/Death cross
    if lat.EMA9>lat.EMA21 and prev.EMA9<=prev.EMA21: reasons.append("🔥 Golden Cross EMA9/21"); score+=2
    elif lat.EMA9<lat.EMA21 and prev.EMA9>=prev.EMA21: reasons.append("💧 Death Cross EMA9/21"); score-=2
    # MACD
    mc,ms=float(lat.MACD),float(lat.MACD_Sig); pc,ps=float(prev.MACD),float(prev.MACD_Sig)
    if mc>ms and pc<=ps:   reasons.append("🔥 MACD cắt lên Signal — mua"); score+=2
    elif mc<ms and pc>=ps: reasons.append("💧 MACD cắt xuống Signal — bán"); score-=2
    elif mc>ms: reasons.append("✅ MACD trên Signal"); score+=1
    else:       reasons.append("❌ MACD dưới Signal"); score-=1
    # RSI
    r=float(lat.RSI)
    if r>75:   reasons.append(f"⚠️ RSI={r:.0f} quá mua"); score-=1.5
    elif r<25: reasons.append(f"🔥 RSI={r:.0f} quá bán"); score+=1.5
    elif r>50: reasons.append(f"✅ RSI={r:.0f} ủng hộ tăng"); score+=0.5
    else:      reasons.append(f"❌ RSI={r:.0f} ủng hộ giảm"); score-=0.5
    # ADX
    a=float(lat.ADX) if pd.notna(lat.ADX) else 0
    if a>25:
        if mc>ms: reasons.append(f"✅ ADX={a:.0f} xu hướng tăng có đà"); score+=1
        else:     reasons.append(f"❌ ADX={a:.0f} xu hướng giảm có đà"); score-=1
    else: reasons.append(f"⚠️ ADX={a:.0f} sideway (<25)")
    # Bollinger
    if c>lat.BB_upper: reasons.append("⚠️ Vượt BB trên — quá mua"); score-=0.5
    elif c<lat.BB_lower: reasons.append("🔥 Chạm BB dưới — quá bán"); score+=0.5
    if lat.BB_width<0.05: reasons.append("📉 BB bó hẹp — sắp bùng nổ")
    # VWAP
    if pd.notna(lat.VWAP):
        if c>lat.VWAP: reasons.append(f"✅ Giá > VWAP"); score+=0.5
        else:          reasons.append(f"❌ Giá < VWAP"); score-=0.5
    # CMF
    if pd.notna(lat.CMF):
        cmf=float(lat.CMF)
        if cmf>0.1:   reasons.append(f"✅ CMF={cmf:.2f} dòng tiền vào"); score+=0.5
        elif cmf<-0.1: reasons.append(f"❌ CMF={cmf:.2f} dòng tiền ra"); score-=0.5
    # MFI
    if pd.notna(lat.MFI):
        mfi=float(lat.MFI)
        if mfi>75:   reasons.append(f"⚠️ MFI={mfi:.0f} quá mua"); score-=0.5
        elif mfi<25: reasons.append(f"🔥 MFI={mfi:.0f} quá bán"); score+=0.5
    # Candle
    pat=str(lat.get("Pattern","") or "")
    if pat in("Bullish Engulfing","Hammer","Bullish Marubozu"): reasons.append(f"🕯 {pat} — đảo chiều tăng"); score+=1.5
    elif pat in("Bearish Engulfing","Shooting Star"):           reasons.append(f"🕯 {pat} — đảo chiều giảm"); score-=1.5
    elif pat=="Doji": reasons.append("🕯 Doji — lưỡng lự")
    # Volume
    if lat.Vol_Ratio>1.5:
        reasons.append(f"📊 Vol đột biến ×{lat.Vol_Ratio:.1f} — "+("xác nhận mua" if score>0 else "xác nhận bán"))
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
    tp1=round(tps[0]) if tps else round(buy*1.05)
    tp2=round(tps[1]) if len(tps)>1 else round(buy*1.10)
    tp3=round(tps[2]) if len(tps)>2 else round(buy*1.15)
    risk=abs(buy-sl)/buy if buy>0 else 0
    reward=(tp2-buy)/buy if buy>0 else 0
    rr=reward/risk if risk>0 else 0
    return dict(buy=buy,sl=sl,tp1=tp1,tp2=tp2,tp3=tp3,risk=risk,reward=reward,rr=rr,fib=fib,atr=atr)

# ══ FUNDAMENTAL ENGINE ═══════════════════════════════════════════════════════
def build_fundamental(rat, inc, bal, cf, price=None):
    """Phân tích cơ bản toàn diện — trả dict."""
    ryc=ycols(rat); iyc=ycols(inc); byc=ycols(bal); cyc=ycols(cf)
    rl=ryc[-1] if ryc else None; il=iyc[-1] if iyc else None
    bl=byc[-1] if byc else None; cl=cyc[-1] if cyc else None

    def gv(iid): return sg(iid,(rat,rl),(inc,il),(bal,bl),(cf,cl))

    pe=gv('pe_ratio'); pb=gv('pb_ratio'); eps=gv('earnings_per_share')
    roe=pct(gv('roe')); roa=pct(gv('roa'))
    gm=pct(gv('gross_margin')); nm=pct(gv('net_margin'))
    de=gv('debt_to_equity'); cr=gv('current_ratio')
    eq_ta=pct(gv('equity_total_assets')) if de is None else None
    ldr=pct(gv('ldr')) if cr is None else None
    bvps=gv('book_value_per_share')
    is_bank = de is None and eq_ta is not None

    # Series
    rev_s=gs('revenue',inc,iyc); net_s=gs('net_profit',inc,iyc)
    _eps_r=gs('earnings_per_share',rat,ryc); _eps_i=gs('earnings_per_share',inc,iyc)
    eps_s=_eps_r if (_eps_r is not None and not _eps_r.empty) else _eps_i
    gm_s=to_pct_arr(gs('gross_margin',rat,ryc)); nm_s=to_pct_arr(gs('net_margin',rat,ryc))
    roe_s=to_pct_arr(gs('roe',rat,ryc)); roa_s=to_pct_arr(gs('roa',rat,ryc))

    yrs = max(len(ryc)-1, len(iyc)-1, 1)
    rev_cagr=None; eps_cagr=None
    if rev_s is not None and len(rev_s.dropna())>=2:
        rv=rev_s.dropna()
        rev_cagr=cagr(float(rv.iloc[0]),float(rv.iloc[-1]),len(rv)-1)
    if eps_s is not None and len(eps_s.dropna())>=2:
        ev=eps_s.dropna()
        eps_cagr=cagr(abs(float(ev.iloc[0])),abs(float(ev.iloc[-1])),len(ev)-1)

    ocf=gv('operating_cashflow'); net_p=gv('net_profit')
    fcf_quality=ocf/net_p if ocf and net_p and net_p!=0 else None

    # Graham & PEG
    graham_n=round((22.5*eps*bvps)**0.5,0) if eps and bvps and eps>0 and bvps>0 else None
    peg=round(pe/eps_cagr,2) if pe and eps_cagr and eps_cagr>0 else None

    # Du Pont
    dupont={}
    if not is_bank and roe and nm:
        ta=gv('total_assets') or sg('total_assets',(bal,bl))
        eq=gv('equity') or sg('equity',(bal,bl))
        if rev_s is not None and not rev_s.empty and ta and ta>0 and eq and eq>0:
            rv_val=float(rev_s.dropna().iloc[-1])
            at=rv_val/ta; em=ta/eq
            dupont={'net_margin':nm,'asset_turnover':at,'equity_multiplier':em,
                    'roe_check':nm/100*at*em*100,
                    'driver':max([('Biên LN ròng',nm),('Hiệu quả TS',at*10),('Đòn bẩy TC',em*3)],key=lambda x:x[1])[0]}

    # Altman Z (phi ngân hàng)
    z_score=None; z_zone=None
    if not is_bank:
        ta=gv('total_assets'); ebit=gv('ebit') or sg('ebit',(inc,il))
        tl=gv('total_debt') or sg('total_debt',(bal,bl))
        if all(v is not None for v in [ta,ebit,tl]) and ta>0:
            x1=(gv('current_ratio') or 1)*0.1/ta; x2=0.05; x3=ebit/ta
            x4=(price or ta*0.3)/max(tl,1); x5=(float(rev_s.dropna().iloc[-1])/ta if rev_s is not None and not rev_s.empty else 0.3)
            z=1.2*x1+1.4*x2+3.3*x3+0.6*x4+x5
            z_score=round(z,2)
            z_zone="An toàn 🟢" if z>2.99 else "Vùng xám ⚠️" if z>1.81 else "Nguy hiểm 🔴"

    # Narrative
    narrative=[]
    if rev_cagr is not None:
        if rev_cagr>15:   narrative.append(("✅","Tăng trưởng doanh thu",f"CAGR {rev_cagr:.1f}%/năm — tăng trưởng mạnh","#00d97e"))
        elif rev_cagr>5:  narrative.append(("⚠️","Tăng trưởng doanh thu",f"CAGR {rev_cagr:.1f}%/năm — tăng ổn định","#f5a623"))
        else:             narrative.append(("❌","Tăng trưởng doanh thu",f"CAGR {rev_cagr:.1f}%/năm — tăng trưởng yếu","#ff3d5a"))
    if eps_cagr is not None:
        if eps_cagr>15:   narrative.append(("✅","Tăng trưởng EPS",f"CAGR {eps_cagr:.1f}%/năm — lợi nhuận/CP tăng tốt","#00d97e"))
        elif eps_cagr>0:  narrative.append(("⚠️","Tăng trưởng EPS",f"CAGR {eps_cagr:.1f}%/năm — tăng chậm","#f5a623"))
        else:             narrative.append(("❌","Tăng trưởng EPS","EPS giảm — lợi nhuận xấu đi","#ff3d5a"))
    if roe is not None:
        if roe>18:   narrative.append(("✅","Sinh lời vốn chủ (ROE)",f"ROE={roe:.1f}% — xuất sắc","#00d97e"))
        elif roe>12: narrative.append(("⚠️","Sinh lời vốn chủ (ROE)",f"ROE={roe:.1f}% — tốt","#f5a623"))
        else:        narrative.append(("❌","Sinh lời vốn chủ (ROE)",f"ROE={roe:.1f}% — dưới kỳ vọng","#ff3d5a"))
    if fcf_quality is not None:
        if fcf_quality>1.0:  narrative.append(("✅","Chất lượng lợi nhuận",f"OCF/Net={fcf_quality:.1f}x — tiền mặt thực > LN ghi nhận","#00d97e"))
        elif fcf_quality>0.5: narrative.append(("⚠️","Chất lượng lợi nhuận",f"OCF/Net={fcf_quality:.1f}x — chấp nhận được","#f5a623"))
        else:                 narrative.append(("❌","Chất lượng lợi nhuận",f"OCF/Net={fcf_quality:.1f}x — LN kém chất lượng","#ff3d5a"))
    if pe:
        if 0<pe<12:   narrative.append(("✅","Định giá P/E",f"P/E={pe:.1f}x — rẻ so thị trường","#00d97e"))
        elif pe<20:   narrative.append(("⚠️","Định giá P/E",f"P/E={pe:.1f}x — hợp lý","#f5a623"))
        elif pe>0:    narrative.append(("❌","Định giá P/E",f"P/E={pe:.1f}x — đắt","#ff3d5a"))
    if gm_s is not None and nm_s is not None:
        gm_clean=gm_s.dropna(); nm_clean=nm_s.dropna()
        if len(nm_clean)>=2:
            trend_dir="MỞ RỘNG" if nm_clean.iloc[-1]>nm_clean.iloc[-2] else "THU HẸP"
            t_clr="#00d97e" if trend_dir=="MỞ RỘNG" else "#ff3d5a"
            narrative.append(("📊","Biên lợi nhuận",f"Biên ròng đang {trend_dir}: {nm_clean.iloc[-2]:.1f}% → {nm_clean.iloc[-1]:.1f}%",t_clr))

    return dict(pe=pe,pb=pb,eps=eps,roe=roe,roa=roa,gm=gm,nm=nm,
                de=de,eq_ta=eq_ta,cr=cr,ldr=ldr,bvps=bvps,is_bank=is_bank,
                rev_s=rev_s,net_s=net_s,eps_s=eps_s,gm_s=gm_s,nm_s=nm_s,
                roe_s=roe_s,roa_s=roa_s,
                rev_cagr=rev_cagr,eps_cagr=eps_cagr,
                ocf=ocf,fcf_quality=fcf_quality,
                graham_n=graham_n,peg=peg,
                dupont=dupont,z_score=z_score,z_zone=z_zone,
                narrative=narrative,ryc=ryc,iyc=iyc)

def fund_score(fa):
    total=0; items=[]
    def chk(lbl,val,fn,g,b,w):
        nonlocal total
        ok=fn(val) if val is not None else None
        items.append(dict(label=lbl,val=val,ok=ok,good=g,bad=b))
        if ok is True: total+=w
        elif ok is False: total-=w
    chk("ROE",fa['roe'],lambda v:v>15,"ROE>15%","ROE<15%",1.0)
    chk("ROA",fa['roa'],lambda v:v>1.5 if fa['is_bank'] else v>8,"ROA tốt","ROA thấp",0.5)
    chk("P/E",fa['pe'],lambda v:0<v<18,"P/E hợp lý","P/E cao/âm",1.0)
    chk("P/B",fa['pb'],lambda v:0<v<3.5,"P/B<3.5x","P/B cao",0.5)
    chk("EPS",fa['eps'],lambda v:v>0,"EPS dương","EPS âm",1.5)
    if fa['is_bank'] and fa['eq_ta']:
        chk("VCSH/TS",fa['eq_ta'],lambda v:v>6,"VCSH/TS>6%","Vốn mỏng",0.3)
    elif fa['de']:
        chk("D/E",fa['de'],lambda v:v<1.5,"D/E<1.5x","Đòn bẩy cao",0.3)
    if fa['rev_cagr']:
        chk("Rev CAGR",fa['rev_cagr'],lambda v:v>10,"Doanh thu tăng tốt","Tăng trưởng trì trệ",0.5)
    if fa['fcf_quality']:
        chk("Cash Quality",fa['fcf_quality'],lambda v:v>0.8,"OCF>LN — tiền thật","LN kém thực",0.7)
    return items, round(total,1)

# ══ UI HELPERS ════════════════════════════════════════════════════════════════
def card(label, val_str, color="#fff", note=""):
    return (f"<div style='background:#0c1d2e;border:1px solid #163350;border-radius:12px;padding:14px 16px;'>"
            f"<div style='font-size:12px;color:#6a9cc8;letter-spacing:.5px;margin-bottom:6px;font-weight:500;'>{label}</div>"
            f"<div style='font-size:22px;font-weight:700;color:{color};line-height:1.2;'>{val_str}</div>"
            +(f"<div style='font-size:11px;color:#4a6080;margin-top:4px;'>{note}</div>" if note else "")
            +"</div>")

def sig_banner(sig, score):
    clr=SIG_COLOR.get(sig,"#8baed4"); sc_clr="#00d97e" if score>=2 else "#ff3d5a" if score<=-2 else "#f5a623"
    pct_val=min(100,max(0,(score+9)/18*100))
    return (f"<div style='background:#0c1d2e;border:1px solid #163350;border-radius:12px;"
            f"padding:16px 20px;display:flex;align-items:center;gap:24px;flex-wrap:wrap;margin:10px 0;'>"
            f"<div><div style='font-size:12px;color:#6a9cc8;font-weight:500;'>TÍN HIỆU KỸ THUẬT</div>"
            f"<div style='font-size:30px;font-weight:700;color:{clr};'>{sig}</div></div>"
            f"<div style='text-align:center;'><div style='font-size:12px;color:#6a9cc8;'>ĐIỂM</div>"
            f"<div style='font-size:32px;font-weight:700;color:{sc_clr};'>{score:+.1f}</div></div>"
            f"<div style='flex:1;min-width:200px;'>"
            f"<div style='font-size:10px;color:#3a6080;margin-bottom:5px;'>BÁN MẠNH ←──────────────→ MUA MẠNH</div>"
            f"<div style='height:10px;background:#102030;border-radius:5px;overflow:hidden;'>"
            f"<div style='height:100%;width:{pct_val}%;background:{clr};border-radius:5px;'></div>"
            f"</div></div></div>")

def trade_card(icon, title, val, sub, border):
    return (f"<div style='background:#0c1d2e;border:1px solid {border};border-radius:12px;padding:14px 16px;'>"
            f"<div style='font-size:12px;color:{border};letter-spacing:.5px;margin-bottom:6px;font-weight:500;'>{icon} {title}</div>"
            f"<div style='font-size:22px;font-weight:700;color:#fff;'>{val}</div>"
            f"<div style='font-size:13px;color:#6a9cc8;margin-top:4px;'>{sub}</div></div>")

def fund_chip(item):
    ok=item["ok"]; val=item["val"]; lbl=item["label"]
    clr="#00d97e" if ok else "#ff3d5a" if ok is False else "#f5a623"
    ico="✅" if ok else "❌" if ok is False else "⚪"
    vs=(f"{val:,.1f}" if isinstance(val,float) else str(val)) if val is not None else "—"
    note=item["good"] if ok else (item["bad"] if ok is False else "N/A")
    return (f"<div style='background:#0c1d2e;border:1px solid {clr}50;border-radius:12px;padding:12px;text-align:center;'>"
            f"<div style='font-size:20px;'>{ico}</div>"
            f"<div style='font-size:13px;font-weight:600;color:#cce0ff;margin:4px 0;'>{lbl}</div>"
            f"<div style='font-size:18px;font-weight:700;color:{clr};'>{vs}</div>"
            f"<div style='font-size:11px;color:#6a9cc8;margin-top:4px;line-height:1.4;'>{note}</div></div>")

def score_pill(label, s, note=""):
    clr="#00d97e" if s>1 else "#ff3d5a" if s<-1 else "#f5a623"
    pct_val=min(100,max(0,(s+7)/14*100))
    return (f"<div style='background:#0c1d2e;border:1px solid #163350;border-radius:12px;padding:14px;text-align:center;'>"
            f"<div style='font-size:12px;color:#6a9cc8;letter-spacing:.5px;margin-bottom:4px;'>{label}</div>"
            f"<div style='font-size:24px;font-weight:700;color:{clr};'>{s:+.1f}</div>"
            f"<div style='font-size:11px;color:#3a6080;margin-top:3px;'>{note}</div>"
            f"<div style='height:4px;background:#102030;border-radius:2px;overflow:hidden;margin-top:7px;'>"
            f"<div style='height:100%;width:{pct_val}%;background:{clr};border-radius:2px;'></div></div></div>")

def narrative_card(ico, title, desc, clr):
    return (f"<div style='background:#0c1d2e;border-left:3px solid {clr};"
            f"border-radius:0 10px 10px 0;padding:10px 14px;margin:5px 0;display:flex;gap:10px;'>"
            f"<span style='font-size:18px;'>{ico}</span>"
            f"<div><div style='font-size:13px;font-weight:600;color:{clr};'>{title}</div>"
            f"<div style='font-size:12px;color:#8baed4;margin-top:2px;'>{desc}</div></div></div>")

# ══ CHART BUILDERS ════════════════════════════════════════════════════════════
def build_price_chart(df, trade, show_n, ema_list, show_ichi=False):
    show=df.tail(show_n).copy()
    ema_colors={"EMA9":"#4a9ef8","EMA21":"#f5a623","EMA50":"#00d97e","EMA200":"#a78bfa"}
    fig=make_subplots(rows=5,cols=1,shared_xaxes=True,vertical_spacing=0.015,
        row_heights=[0.45,0.12,0.14,0.14,0.15],
        subplot_titles=("","Volume","MACD","RSI + StochRSI","CMF + MFI"))
    # Candles
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
    # Bollinger
    fig.add_trace(go.Scatter(x=show["Date"],y=show["BB_upper"],name="BB+",
        line=dict(color="rgba(167,139,250,.3)",width=1,dash="dot"),hoverinfo="skip"),row=1,col=1)
    fig.add_trace(go.Scatter(x=show["Date"],y=show["BB_lower"],name="BB-",
        line=dict(color="rgba(167,139,250,.3)",width=1,dash="dot"),
        fill="tonexty",fillcolor="rgba(167,139,250,0.03)",hoverinfo="skip"),row=1,col=1)
    # Ichimoku (optional)
    if show_ichi and "Ichi_SpanA" in show.columns and show["Ichi_SpanA"].notna().any():
        fig.add_trace(go.Scatter(x=show["Date"],y=show["Ichi_SpanA"],name="Kumo A",
            line=dict(color="rgba(0,217,126,.2)",width=0.5),hoverinfo="skip"),row=1,col=1)
        fig.add_trace(go.Scatter(x=show["Date"],y=show["Ichi_SpanB"],name="Kumo B",
            line=dict(color="rgba(255,61,90,.2)",width=0.5),
            fill="tonexty",fillcolor="rgba(0,100,50,0.05)",hoverinfo="skip"),row=1,col=1)
        fig.add_trace(go.Scatter(x=show["Date"],y=show["Ichi_Tenkan"],name="Tenkan",
            line=dict(color="#ff6b6b",width=1,dash="dot"),hoverinfo="skip"),row=1,col=1)
        fig.add_trace(go.Scatter(x=show["Date"],y=show["Ichi_Kijun"],name="Kijun",
            line=dict(color="#4a9ef8",width=1,dash="dash"),hoverinfo="skip"),row=1,col=1)
    # PSAR
    if "PSAR" in show.columns and show["PSAR"].notna().any():
        fig.add_trace(go.Scatter(x=show["Date"],y=show["PSAR"],name="PSAR",
            mode="markers",marker=dict(symbol="circle",size=3,color="#ff9f43"),
            hoverinfo="skip"),row=1,col=1)
    # Pivot lines
    for pname,pclr in [("PP","rgba(255,255,255,0.5)"),("R1","rgba(255,107,107,0.6)"),
                        ("R2","rgba(255,61,90,0.5)"),("S1","rgba(105,211,102,0.6)"),("S2","rgba(0,217,126,0.5)")]:
        if pname in show.columns:
            pv=float(show[pname].iloc[-1])
            ylo,yhi=float(show["Low"].min()),float(show["High"].max())
            if ylo*0.9<pv<yhi*1.1:
                fig.add_hline(y=pv,row=1,col=1,line=dict(color=pclr,dash="dot",width=0.7),
                    annotation_text=f" {pname}",annotation_font=dict(color=pclr,size=8))
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
    if "StochRSI_K" in show.columns and show["StochRSI_K"].notna().any():
        fig.add_trace(go.Scatter(x=show["Date"],y=show["StochRSI_K"],name="StochK",line=dict(color="#22d3ee",width=1)),row=4,col=1)
    for lvl,clr_l in[(80,"rgba(255,61,90,.5)"),(50,"rgba(139,174,212,.25)"),(20,"rgba(0,217,126,.5)")]:
        fig.add_hline(y=lvl,row=4,col=1,line=dict(color=clr_l,dash="dot",width=.8))
    # CMF + MFI
    if "CMF" in show.columns and show["CMF"].notna().any():
        fig.add_trace(go.Scatter(x=show["Date"],y=show["CMF"],name="CMF",line=dict(color="#00d97e",width=1.5)),row=5,col=1)
        fig.add_hline(y=0.1,row=5,col=1,line=dict(color="rgba(0,217,126,.4)",dash="dot",width=0.8))
        fig.add_hline(y=-0.1,row=5,col=1,line=dict(color="rgba(255,61,90,.4)",dash="dot",width=0.8))
        fig.add_hline(y=0,row=5,col=1,line=dict(color="rgba(255,255,255,.15)",width=0.8))
    if "MFI" in show.columns and show["MFI"].notna().any():
        fig.add_trace(go.Scatter(x=show["Date"],y=show["MFI"]/100*0.4-0.2,name="MFI(scaled)",
            line=dict(color="#f5a623",width=1,dash="dot")),row=5,col=1)
    fig.update_layout(height=820,template="plotly_dark",xaxis_rangeslider_visible=False,**CHART_STYLE)
    for ann in fig.layout.annotations: ann.font.color="#4a6080"; ann.font.size=10
    return fig

def build_cashflow_chart(df):
    show=df.tail(60)
    fig=make_subplots(rows=3,cols=1,shared_xaxes=True,vertical_spacing=0.04,
        row_heights=[0.4,0.3,0.3],
        subplot_titles=("OBV — Tích lũy / Phân phối","CMF (Chaikin Money Flow)","MFI (Money Flow Index)"))
    if "OBV" in show.columns:
        fig.add_trace(go.Scatter(x=show["Date"],y=show["OBV"]/1e6,name="OBV(M)",
            line=dict(color="#4a9ef8",width=2),fill="tozeroy",fillcolor="rgba(74,158,248,.08)"),row=1,col=1)
        if "OBV_EMA" in show.columns:
            fig.add_trace(go.Scatter(x=show["Date"],y=show["OBV_EMA"]/1e6,name="OBV EMA",
                line=dict(color="#f5a623",width=1.5,dash="dot")),row=1,col=1)
    if "CMF" in show.columns:
        cmf_clr=["#00d97e" if v>=0 else "#ff3d5a" for v in show["CMF"].fillna(0)]
        fig.add_trace(go.Bar(x=show["Date"],y=show["CMF"],name="CMF",marker_color=cmf_clr,opacity=0.8),row=2,col=1)
        for lvl,clr2,txt in [(0.1,"rgba(0,217,126,.5)"," +0.1"),(-0.1,"rgba(255,61,90,.5)"," -0.1"),
                              (0,"rgba(255,255,255,.15)","")]:
            fig.add_hline(y=lvl,row=2,col=1,line=dict(color=clr2,dash="dot",width=0.8),
                annotation_text=txt,annotation_font=dict(color=clr2,size=9))
    if "MFI" in show.columns:
        fig.add_trace(go.Scatter(x=show["Date"],y=show["MFI"],name="MFI",
            line=dict(color="#a78bfa",width=2)),row=3,col=1)
        for lvl,clr2 in[(80,"rgba(255,61,90,.5)"),(50,"rgba(139,174,212,.25)"),(20,"rgba(0,217,126,.5)")]:
            fig.add_hline(y=lvl,row=3,col=1,line=dict(color=clr2,dash="dot",width=.8))
    fig.update_layout(height=520,template="plotly_dark",**CHART_STYLE)
    for ann in fig.layout.annotations: ann.font.color="#8baed4"; ann.font.size=10
    return fig

def build_fin_charts(fa):
    charts=[]
    # EPS + ROE/ROA
    fig1=make_subplots(rows=1,cols=2,subplot_titles=("EPS theo năm (đ/CP)","ROE & ROA (%)"),horizontal_spacing=0.12)
    eps_s=fa['eps_s']; ryc=fa['ryc']
    if eps_s is not None and not eps_s.empty:
        bc=["#00d97e" if v>=0 else "#ff3d5a" for v in eps_s.fillna(0)]
        fig1.add_trace(go.Bar(x=list(eps_s.index),y=eps_s.values,name="EPS",marker_color=bc,
            text=[f"{v:,.0f}" for v in eps_s.values],textposition="outside",
            textfont=dict(color="#cce0ff",size=11)),row=1,col=1)
    if fa['roe_s'] is not None and not fa['roe_s'].empty:
        fig1.add_trace(go.Scatter(x=list(fa['roe_s'].index),y=fa['roe_s'].values,name="ROE%",
            mode="lines+markers",line=dict(color="#00d97e",width=2.5),marker=dict(size=9)),row=1,col=2)
    if fa['roa_s'] is not None and not fa['roa_s'].empty:
        fig1.add_trace(go.Scatter(x=list(fa['roa_s'].index),y=fa['roa_s'].values,name="ROA%",
            mode="lines+markers",line=dict(color="#f5a623",width=2),marker=dict(size=8)),row=1,col=2)
    for lvl,clr,lbl in[(15,"rgba(0,217,126,.4)","ROE 15%"),(1.5,"rgba(74,158,248,.3)","ROA 1.5%")]:
        fig1.add_hline(y=lvl,row=1,col=2,line=dict(color=clr,dash="dot",width=1),
            annotation_text=f" {lbl}",annotation_font=dict(color=clr,size=10))
    fig1.update_layout(height=320,template="plotly_dark",**CHART_STYLE)
    for ann in fig1.layout.annotations: ann.font.color="#8baed4"; ann.font.size=12
    charts.append(fig1)
    # Revenue & Net Profit
    if fa['rev_s'] is not None and fa['net_s'] is not None:
        fig2=go.Figure()
        fig2.add_trace(go.Bar(x=list(fa['rev_s'].index),y=fa['rev_s'].values/1e9,
            name="Doanh thu (tỷ)",marker_color="#4a9ef8",opacity=0.7))
        fig2.add_trace(go.Scatter(x=list(fa['net_s'].index),y=fa['net_s'].values/1e9,
            name="Lợi nhuận (tỷ)",mode="lines+markers",line=dict(color="#00d97e",width=2.5),marker=dict(size=8)))
        fig2.update_layout(height=270,title="Doanh thu & Lợi nhuận (tỷ đồng)",template="plotly_dark",**CHART_STYLE)
        fig2.layout.title.font.color="#8baed4"; fig2.layout.title.font.size=12
        charts.append(fig2)
    # Biên lợi nhuận
    if fa['gm_s'] is not None or fa['nm_s'] is not None:
        fig3=go.Figure()
        if fa['gm_s'] is not None and not fa['gm_s'].empty:
            fig3.add_trace(go.Scatter(x=list(fa['gm_s'].index),y=fa['gm_s'].values,name="Biên gộp%",
                mode="lines+markers",line=dict(color="#a78bfa",width=2),marker=dict(size=8)))
        if fa['nm_s'] is not None and not fa['nm_s'].empty:
            fig3.add_trace(go.Scatter(x=list(fa['nm_s'].index),y=fa['nm_s'].values,name="Biên ròng%",
                mode="lines+markers",line=dict(color="#22d3ee",width=2),marker=dict(size=8)))
            nm_clean=fa['nm_s'].dropna()
            if len(nm_clean)>=2:
                trend="MỞ RỘNG" if nm_clean.iloc[-1]>nm_clean.iloc[-2] else "THU HẸP"
                t_clr="#00d97e" if trend=="MỞ RỘNG" else "#ff3d5a"
                fig3.add_annotation(x=list(fa['nm_s'].index)[-1],y=float(nm_clean.iloc[-1]),
                    text=f" Biên {trend}",font=dict(color=t_clr,size=11),showarrow=False,xanchor="left")
        fig3.update_layout(height=240,title="Biên lợi nhuận (%)",template="plotly_dark",**CHART_STYLE)
        fig3.layout.title.font.color="#8baed4"; fig3.layout.title.font.size=12
        charts.append(fig3)
    return charts

# ══ SIDEBAR ═══════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 📈 Pro Trader v7")
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
    show_ichi=st.checkbox("Ichimoku Cloud",False)
    run=st.button("🚀 Phân tích ngay",use_container_width=True)
    auto_r=st.checkbox("Tự động refresh",False)
    if auto_r: ref_sec=st.select_slider("Tần suất",[30,60,120,300],value=60)
    st.markdown("---")
    st.markdown("**Mã nhanh**")
    quick=["VPB","HPG","VCB","FPT","MWG","SSI","TCB","VIC","ACB","STB","MBB","HDB"]
    qcols=st.columns(3); clicked=None
    for i,m in enumerate(quick):
        if qcols[i%3].button(m,key=f"q_{m}",use_container_width=True): clicked=m
    if clicked: symbol=clicked

# ══ MAIN ══════════════════════════════════════════════════════════════════════
st.markdown(f"## {symbol} &nbsp;<span style='font-size:14px;color:#4a9ef8;'>{res_label} · {per_label}</span>",
            unsafe_allow_html=True)

if not (run or clicked):
    st.markdown(("<div style='text-align:center;padding:80px 20px;background:#0c1d2e;"
                 "border-radius:14px;border:1px solid #163350;'>"
                 "<div style='font-size:52px;'>📈</div>"
                 "<div style='font-size:17px;color:#6a9cc8;margin-top:14px;'>Nhập mã và nhấn <b style=\"color:#fff\">Phân tích ngay</b></div>"
                 "<div style='font-size:13px;color:#3a6080;margin-top:8px;'>7 tab: Kỹ thuật · Cơ bản · Dòng tiền · So sánh ngành · Quét mã · Tin tức · Tổng hợp</div>"
                 "</div>"), unsafe_allow_html=True)
    st.stop()

with st.spinner(f"⏳ Đang tải {symbol}..."):
    try:
        df_raw = fetch_price(symbol, days, resolution)
    except Exception as e:
        st.error(f"❌ {e}"); st.stop()
    rat = fetch_kbs_ratio(symbol)
    inc = fetch_kbs_income(symbol)
    bal = fetch_kbs_balance(symbol)
    cf  = fetch_kbs_cashflow(symbol)
    # TCBS fallback
    tcbs = fetch_tcbs_data(symbol)
    if rat.empty and 'ratio' in tcbs and not tcbs['ratio'].empty:
        rat = tcbs['ratio']
    tcbs_ov = tcbs.get('overview', {})
    tcbs_pt = tcbs.get('price_target', [])

df=add_indicators(df_raw.copy()); df=detect_patterns(df)
sig,reasons,score=calc_signal(df); trade=calc_trade(df,score)
fa=build_fundamental(rat,inc,bal,cf,float(df["Close"].iloc[-1]))
f_items,f_score=fund_score(fa)
lat=df.iloc[-1]; prev=df.iloc[-2] if len(df)>1 else lat
struct,struct_clr=detect_market_structure(df)

chg=float(lat.Close)-float(prev.Close); pct_chg=chg/float(prev.Close)*100 if prev.Close else 0
chg_str=f"{'▲' if chg>=0 else '▼'} {abs(chg):,.0f} đ ({abs(pct_chg):.2f}%)"
st.caption(f"📡 KBS Live · {len(df)} phiên · {'🟢' if chg>=0 else '🔴'} {chg_str} · "
           f"Cấu trúc: <span style='color:{struct_clr}'>{struct}</span> · {datetime.now().strftime('%H:%M %d/%m/%Y')}",
           unsafe_allow_html=True)

tab1,tab2,tab3,tab4,tab5,tab6,tab7=st.tabs([
    "📉 Kỹ thuật","📊 Cơ bản","💰 Dòng tiền",
    "🏭 So sánh ngành","🔍 Quét mã","📰 Tin tức","🎯 Tổng hợp"])

# ── TAB 1: KỸ THUẬT ──────────────────────────────────────────────────────────
with tab1:
    m1,m2,m3,m4,m5,m6,m7=st.columns(7)
    m1.metric("💰 Giá",f"{lat.Close:,.0f}đ",chg_str)
    m2.metric("📐 ATR",f"{lat.ATR:,.0f}đ","Biên dao động")
    m3.metric("📊 RSI",f"{lat.RSI:.0f}","OB>75 / OS<25")
    m4.metric("💧 MFI",f"{lat.MFI:.0f}" if pd.notna(lat.MFI) else "—","Money Flow Index")
    m5.metric("📈 ADX",f"{lat.ADX:.0f}" if pd.notna(lat.ADX) else "—","Xu hướng")
    h52v=float(lat.H52) if 'H52' in df.columns and pd.notna(lat.get('H52',np.nan)) else 0
    pct_h=((float(lat.Close)-h52v)/h52v*100) if h52v>0 else 0
    m6.metric("52W High",f"{h52v:,.0f}",f"{pct_h:+.1f}% vs now")
    psar_v=float(lat.PSAR) if 'PSAR' in df.columns and pd.notna(lat.get('PSAR',np.nan)) else 0
    m7.metric("PSAR",f"{psar_v:,.0f}" if psar_v else "—",
        "Bull ✅" if lat.get('PSAR_Bull',True) else "Bear ❌")
    st.markdown(sig_banner(sig,score),unsafe_allow_html=True)
    st.plotly_chart(build_price_chart(df,trade,show_n,ema_list,show_ichi),use_container_width=True,
                    config={"displayModeBar":True})
    st.markdown("### 🎯 Chiến lược giao dịch")
    t1,t2,t3,t4=st.columns(4)
    t1.markdown(trade_card("📗","VÙNG MUA",f"{trade['buy']:,}đ","Giá vào lệnh","#00d97e"),unsafe_allow_html=True)
    t2.markdown(trade_card("📕","STOP LOSS",f"{trade['sl']:,}đ",f"Rủi ro {trade['risk']*100:.1f}%","#ff3d5a"),unsafe_allow_html=True)
    t3.markdown(trade_card("🎯","CHỐT LỜI",f"TP1 {trade['tp1']:,}",f"TP2 {trade['tp2']:,} | TP3 {trade['tp3']:,}","#f5a623"),unsafe_allow_html=True)
    rr=trade['rr']; rc="#00d97e" if rr>=2 else "#f5a623" if rr>=1.5 else "#ff3d5a"
    t4.markdown(trade_card("⚖️","R:R RATIO",f"1:{rr:.1f}",f"LN kỳ vọng {trade['reward']*100:.1f}%",rc),unsafe_allow_html=True)
    res_lvls,sup_lvls=auto_sr(df)
    with st.expander("📐 Hỗ trợ & Kháng cự + Fibonacci"):
        sa,sb=st.columns(2)
        with sa:
            st.markdown("**Kháng cự**"); [st.markdown(f"  `{r2:,.0f}đ`") for r2 in res_lvls]
            st.markdown("**Hỗ trợ**");   [st.markdown(f"  `{s2:,.0f}đ`") for s2 in sup_lvls]
        with sb:
            fib_rows=[{"Mức":k,"Giá":f"{v:,.0f}","So HT":f"{(v/float(lat.Close)-1)*100:+.1f}%",
                "Vai trò":"◀ HIỆN TẠI" if abs(v/float(lat.Close)-1)<0.015 else ("Hỗ trợ 🟢" if v<lat.Close else "Kháng cự 🔴")}
                for k,v in trade["fib"].items()]
            st.dataframe(pd.DataFrame(fib_rows),use_container_width=True,hide_index=True)
    st.markdown("### 🔍 Phân tích tín hiệu")
    rc1,rc2=st.columns(2); mid=len(reasons)//2+1
    for r2 in reasons[:mid]: rc1.markdown(r2)
    for r2 in reasons[mid:]: rc2.markdown(r2)
    ind_tbl=[
        ("RSI(14)",f"{lat.RSI:.1f}","OB🔴" if lat.RSI>75 else "OS🟢" if lat.RSI<25 else "OK✅"),
        ("StochRSI K",f"{lat.StochRSI_K:.1f}" if pd.notna(lat.StochRSI_K) else "—",""),
        ("MACD",f"{lat.MACD:.2f}","+" if lat.MACD>lat.MACD_Sig else "-"),
        ("ADX",f"{lat.ADX:.1f}","Xu hướng✅" if lat.ADX>25 else "Sideway⚠️"),
        ("VWAP",f"{lat.VWAP:,.0f}","Trên✅" if lat.Close>lat.VWAP else "Dưới❌"),
        ("OBV",fmt(lat.OBV),"Tích lũy✅" if lat.OBV>lat.OBV_EMA else "Phân phối❌"),
        ("CMF",f"{lat.CMF:.3f}" if pd.notna(lat.CMF) else "—","Vào🟢" if lat.CMF>0.1 else "Ra🔴" if lat.CMF<-0.1 else "Trung tính"),
        ("MFI",f"{lat.MFI:.1f}" if pd.notna(lat.MFI) else "—","OB🔴" if lat.MFI>75 else "OS🟢" if lat.MFI<25 else "BT"),
        ("BB Width",f"{lat.BB_width*100:.1f}%","Bó hẹp⚠️" if lat.BB_width<0.05 else "BT"),
        ("Vol/TB",f"×{lat.Vol_Ratio:.2f}","Đột biến📢" if lat.Vol_Ratio>1.5 else "BT"),
        ("EMA9",f"{lat.EMA9:,.0f}","Trên EMA21✅" if lat.EMA9>lat.EMA21 else "Dưới EMA21❌"),
        ("EMA200",f"{lat.EMA200:,.0f}" if pd.notna(lat.EMA200) else "—","Trên✅" if pd.notna(lat.EMA200) and lat.Close>lat.EMA200 else "Dưới❌"),
    ]
    st.dataframe(pd.DataFrame(ind_tbl,columns=["Chỉ báo","Giá trị","Trạng thái"]),
                 use_container_width=True,hide_index=True)

# ── TAB 2: CƠ BẢN ────────────────────────────────────────────────────────────
with tab2:
    if not rat.empty or not inc.empty:
        st.markdown("### 📊 Chỉ số tài chính (kỳ mới nhất)")
        f1,f2,f3,f4,f5,f6,f7=st.columns(7)
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

        # Growth metrics
        st.markdown("### 📈 Tăng trưởng & Chất lượng lợi nhuận")
        ga,gb,gc,gd=st.columns(4)
        ga.metric("Doanh thu CAGR",f"{fa['rev_cagr']:.1f}%/năm" if fa['rev_cagr'] else "—",
            "Tốt✅" if fa['rev_cagr'] and fa['rev_cagr']>10 else "")
        gb.metric("EPS CAGR",f"{fa['eps_cagr']:.1f}%/năm" if fa['eps_cagr'] else "—",
            "Tốt✅" if fa['eps_cagr'] and fa['eps_cagr']>10 else "")
        gc.metric("Chất lượng LN (OCF/Net)",f"{fa['fcf_quality']:.2f}x" if fa['fcf_quality'] else "—",
            "Cao✅" if fa['fcf_quality'] and fa['fcf_quality']>1 else "Thấp⚠️" if fa['fcf_quality'] else "")
        gd.metric("Altman Z-Score",
            f"{fa['z_score']}" if fa['z_score'] else ("N/A (ngân hàng)" if fa['is_bank'] else "—"),
            fa['z_zone'] if fa['z_zone'] else "")

        # Valuation deep dive
        st.markdown("### 💎 Định giá chuyên sâu")
        va1,va2,va3,va4=st.columns(4)
        sym_sector=next((s for s,ps in SECTOR_PEERS.items() if symbol in ps),None)
        sector_pe=SECTOR_PE.get(sym_sector)
        pe_vs=((fa['pe']-sector_pe)/sector_pe*100) if fa['pe'] and sector_pe else None
        va1.markdown(card("P/E vs Ngành",
            ("Rẻ hơn" if pe_vs and pe_vs<-10 else "Đắt hơn" if pe_vs and pe_vs>20 else "Hợp lý") if pe_vs is not None else "—",
            "#00d97e" if pe_vs and pe_vs<-10 else "#ff3d5a" if pe_vs and pe_vs>20 else "#f5a623",
            f"P/E={fa['pe']:.1f}x vs ngành {sector_pe}x ({pe_vs:+.0f}%)" if pe_vs is not None else f"Ngành: {sym_sector or '—'}"),
            unsafe_allow_html=True)
        va2.markdown(card("PEG Ratio",
            f"{fa['peg']:.2f}" if fa['peg'] else "—",
            "#00d97e" if fa['peg'] and fa['peg']<1 else "#f5a623" if fa['peg'] and fa['peg']<2 else "#ff3d5a" if fa['peg'] else "#8baed4",
            "<1: Hấp dẫn" if fa['peg'] and fa['peg']<1 else "<2: Hợp lý" if fa['peg'] and fa['peg']<2 else ">2: Đắt" if fa['peg'] else "Cần EPS CAGR"),
            unsafe_allow_html=True)
        va3.markdown(card("Graham Number",
            f"{fa['graham_n']:,.0f}đ" if fa['graham_n'] else "—",
            "#00d97e" if fa['graham_n'] and float(lat.Close)<fa['graham_n'] else "#ff3d5a" if fa['graham_n'] else "#8baed4",
            "Giá < Graham: Rẻ" if fa['graham_n'] and float(lat.Close)<fa['graham_n'] else "Giá > Graham: Đắt" if fa['graham_n'] else "Cần EPS & BVPS"),
            unsafe_allow_html=True)
        if tcbs_pt:
            try:
                pt_avg=sum(p.get('targetPrice',p.get('priceTarget',0)) for p in tcbs_pt[:5])/min(5,len(tcbs_pt))
                pt_up=(pt_avg-float(lat.Close))/float(lat.Close)*100
                va4.metric("Price Target (TCBS)",f"{pt_avg:,.0f}đ",f"Upside {pt_up:+.1f}%")
            except: va4.markdown(card("Price Target","—","#8baed4"),unsafe_allow_html=True)
        else:
            mc_val=tcbs_ov.get('marketCap') if tcbs_ov else None
            va4.markdown(card("Vốn hóa (TCBS)",fmt(mc_val) if mc_val else "—"),unsafe_allow_html=True)

        # Du Pont
        if fa['dupont']:
            st.markdown("### 🔩 Du Pont — Phân rã ROE")
            dp=fa['dupont']
            da,db,dc,dd=st.columns(4)
            da.metric("Biên LN ròng",f"{dp['net_margin']:.1f}%","Profitability")
            db.metric("Vòng quay TS",f"{dp['asset_turnover']:.2f}x","Efficiency")
            dc.metric("Đòn bẩy TC",f"{dp['equity_multiplier']:.1f}x","Leverage")
            dd.metric("Driver chính ROE",dp['driver'],"Nguồn tăng")
            st.caption(f"ROE ≈ {dp['net_margin']:.1f}% × {dp['asset_turnover']:.2f} × {dp['equity_multiplier']:.1f} = {dp['roe_check']:.1f}%")

        # Scorecard
        if f_items:
            st.markdown("### ✅ Chấm điểm cơ bản")
            chip_cols=st.columns(len(f_items))
            for col,item in zip(chip_cols,f_items):
                col.markdown(fund_chip(item),unsafe_allow_html=True)
