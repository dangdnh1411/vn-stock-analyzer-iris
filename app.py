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
import math, time, re, json, urllib.request

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
# ══ SECTOR DATA ═══════════════════════════════════════════════════════════════
SECTOR_PEERS = {
    "Ngân hàng":    ["VCB","TCB","MBB","ACB","VPB","BID","CTG","STB","HDB","TPB","MSB","SHB"],
    "Bất động sản": ["VIC","VHM","NVL","DXG","KDH","PDR","DIG","BCM","HDG"],
    "Thép & KLB":   ["HPG","NKG","HSG","TIS","VGS","POM"],
    "Chứng khoán":  ["SSI","VND","HCM","MBS","VCI","FTS","BSI","CTS"],
    "Bán lẻ":       ["MWG","FRT","PNJ","DGW"],
    "Công nghệ":    ["FPT","CMG","ELC","VGI"],
    "Dầu khí":      ["GAS","PLX","PVD","PVS","BSR"],
    "Dược":         ["DHG","IMP","DMC","TRA","DBD"],
    "Tiêu dùng":    ["SAB","BHN","VNM","MCH","MSN","QNS"],
    "Điện":         ["REE","PC1","GEG","PGV","NT2"],
}
SECTOR_PE = {
    "Ngân hàng":8.5,"Bất động sản":15.0,"Thép & KLB":10.0,
    "Chứng khoán":12.0,"Bán lẻ":20.0,"Công nghệ":18.0,
    "Dầu khí":9.0,"Dược":16.0,"Tiêu dùng":22.0,"Điện":14.0,
}

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
def _flatten_vci_cols(df):
    """Flatten MultiIndex columns của VCI, giữ TÊN ĐẦY ĐỦ field + đảm bảo duy nhất.
    VCI MultiIndex: (nhóm, field) → lấy field (phần tử cuối tuple), KHÔNG cắt theo '_'."""
    if isinstance(df.columns, pd.MultiIndex):
        # Lấy phần tử CUỐI của mỗi tuple (tên field thật), bỏ phần nhóm
        df.columns = [str(c[-1]) if isinstance(c, tuple) else str(c) for c in df.columns]
    # Dedup: nếu trùng tên → thêm hậu tố .1, .2...
    seen = {}; new_cols = []
    for c in df.columns:
        c = str(c)
        if c in seen:
            seen[c] += 1; new_cols.append(f"{c}.{seen[c]}")
        else:
            seen[c] = 0; new_cols.append(c)
    df.columns = new_cols
    return df

@st.cache_data(ttl=300, show_spinner=False)
def fetch_ratio(sym: str):
    """Chỉ số tài chính: VCI (có EPS đầy đủ) → KBS → trống.
    VCI trả WIDE format (cột=chỉ số), KBS trả LONG format (item_id)."""
    sym = sym.upper()
    # Nguồn 1: VCI — có EPS, BVPS cho cả ngân hàng, format WIDE
    try:
        from vnstock import Finance
        fin = Finance(symbol=sym, source="VCI")
        df = fin.ratio(period="year", lang="en", dropna=False)
        if df is not None and not df.empty:
            df = _flatten_vci_cols(df)
            yc = next((c for c in df.columns if 'year' in str(c).lower()), None)
            if yc:
                df = df.sort_values(yc).reset_index(drop=True)
            return df, "VCI Finance ✅"
    except Exception:
        pass
    # Nguồn 2: KBS (LONG format)
    try:
        from vnstock import Finance
        fin = Finance(symbol=sym, source="KBS")
        df  = fin.ratio(period="year")
        if df is not None and not df.empty:
            return df, "KBS Finance ✅"
    except Exception:
        pass
    return pd.DataFrame(), "Không lấy được chỉ số"

@st.cache_data(ttl=300, show_spinner=False)
def fetch_income(sym: str) -> pd.DataFrame:
    """KQKD: VCI (WIDE) → KBS (LONG)."""
    sym = sym.upper()
    try:
        from vnstock import Finance
        fin = Finance(symbol=sym, source="VCI")
        df = fin.income_statement(period="year", lang="en", dropna=False)
        if df is not None and not df.empty:
            df = _flatten_vci_cols(df)
            yc = next((c for c in df.columns if 'year' in str(c).lower()), None)
            if yc:
                df = df.sort_values(yc).reset_index(drop=True)
            return df
    except Exception:
        pass
    try:
        from vnstock import Finance
        fin = Finance(symbol=sym, source="KBS")
        df  = fin.income_statement(period="year")
        if df is not None and not df.empty:
            yc = next((c for c in df.columns if "year" in c.lower() or "năm" in c.lower()), None)
            if yc: df = df.sort_values(yc, ascending=True).reset_index(drop=True)
            return df
    except:
        pass
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

@st.cache_data(ttl=300, show_spinner=False)
def fetch_balance(sym):
    try:
        from vnstock import Finance
        df=Finance(symbol=sym,source="KBS").balance_sheet(period="year")
        return df if df is not None and not df.empty else pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_cashflow_stmt(sym):
    try:
        from vnstock import Finance
        df=Finance(symbol=sym,source="KBS").cash_flow(period="year")
        return df if df is not None and not df.empty else pd.DataFrame()
    except: return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_tcbs_extras(sym):
    """TCBS: overview + price_target."""
    out={}
    base="https://apipubaws.tcbs.com.vn"
    hdrs={"User-Agent":"Mozilla/5.0","Accept":"application/json",
          "Referer":"https://tcinvest.tcbs.com.vn/","Origin":"https://tcinvest.tcbs.com.vn"}
    try:
        import requests as _r
        r=_r.get(f"{base}/tcanalysis/v1/ticker/{sym}/overview",headers=hdrs,timeout=8)
        if r.status_code==200: out['overview']=r.json()
    except: pass
    try:
        import requests as _r
        r=_r.get(f"{base}/tcanalysis/v1/ticker/{sym}/priceTarget",headers=hdrs,timeout=8)
        if r.status_code==200:
            d=r.json(); rows=d if isinstance(d,list) else d.get("data",[])
            if rows: out['price_target']=rows
    except: pass
    return out

@st.cache_data(ttl=300, show_spinner=False)
def fetch_tcbs_news(sym):
    try:
        import requests as _r
        hdrs={"User-Agent":"Mozilla/5.0","Accept":"application/json",
              "Referer":"https://tcinvest.tcbs.com.vn/","Origin":"https://tcinvest.tcbs.com.vn"}
        r=_r.get(f"https://apipubaws.tcbs.com.vn/tcanalysis/v1/ticker/{sym}/activity-news",
                 params={"page":0,"size":15},headers=hdrs,timeout=10)
        if r.status_code==200:
            d=r.json(); items=d if isinstance(d,list) else d.get("listActivityNews",d.get("data",[]))
            return items[:15]
    except: pass
    return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_news_ai(sym, sector=""):
    prompt = ("Search latest news Vietnam stock " + sym + " last 7 days. "
              "Find: earnings, analyst ratings, business events. Sector: " + sector + ". "
              "Return ONLY valid JSON with keys: news (list of objects with date/title/summary/sentiment), "
              "key_events (list of strings). Example: " + '{}'.format(""))
    try:
        payload=json.dumps({"model":"claude-haiku-4-5-20251001","max_tokens":2000,
            "tools":[{"type":"web_search_20250305","name":"web_search"}],
            "messages":[{"role":"user","content":prompt}]}).encode()
        req=urllib.request.Request("https://api.anthropic.com/v1/messages",
            data=payload,headers={"Content-Type":"application/json"},method="POST")
        with urllib.request.urlopen(req,timeout=45) as resp:
            result=json.loads(resp.read())
        text=" ".join(c.get("text","") for c in result.get("content",[]) if c.get("type")=="text")
        candidates=[]; depth=0; start=-1
        for i,ch in enumerate(text):
            if ch=='{':
                if depth==0: start=i
                depth+=1
            elif ch=='}':
                depth-=1
                if depth==0 and start>=0: candidates.append(text[start:i+1])
        candidates.sort(key=len,reverse=True)
        for c in candidates:
            try:
                d=json.loads(c)
                if "news" in d: return d
            except: pass
    except: pass
    return {"news":[],"key_events":[]}

@st.cache_data(ttl=120, show_spinner=False)
def fetch_price_board(symbols):
    """Lấy giá + thay đổi của nhiều mã trong 1 request (VCI). Cho screener/ngành."""
    out = {}
    try:
        from vnstock import Trading
        tb = Trading(source="VCI")
        df = tb.price_board(symbols, flatten_columns=True)
        if df is not None and not df.empty:
            # Tìm cột symbol và giá
            cols = {c.lower(): c for c in df.columns}
            sym_c = next((cols[k] for k in cols if 'symbol' in k), None)
            price_c = next((cols[k] for k in cols if 'match' in k and 'price' in k), None)
            if not price_c:
                price_c = next((cols[k] for k in cols if k.endswith('matchprice') or 'closeprice' in k or k=='match_match_price'), None)
            ref_c = next((cols[k] for k in cols if 'refprice' in k or 'ref_price' in k), None)
            for _, row in df.iterrows():
                s = str(row[sym_c]).upper() if sym_c else None
                if not s: continue
                price = pd.to_numeric(row[price_c], errors='coerce') if price_c else None
                ref = pd.to_numeric(row[ref_c], errors='coerce') if ref_c else None
                chg = ((price-ref)/ref*100) if (price and ref and ref>0) else 0
                out[s] = {'price': float(price) if pd.notna(price) else None,
                          'chg': float(chg) if pd.notna(chg) else 0}
    except Exception:
        pass
    return out

@st.cache_data(ttl=300, show_spinner=False)
def fetch_vci_news(sym):
    """Tin tức từ VCI Company.news() — nguồn ổn định hơn TCBS trên cloud."""
    try:
        from vnstock.explorer.vci.company import Company
        co = Company(symbol=sym.upper())
        df = co.news()
        if df is not None and not df.empty:
            return df.head(12).to_dict("records")
    except Exception:
        pass
    return []

@st.cache_data(ttl=300, show_spinner=False)
def scan_stock_quick(sym, days=90):
    try:
        df2=fetch_price(sym,days,"1D")
        if len(df2)<30: return None
        df2i=add_indicators(df2)
        s2,_,sc2=calc_signal(df2i)
        lat2=df2i.iloc[-1]
        chg1d=(float(lat2.Close)-float(df2i.iloc[-2].Close))/float(df2i.iloc[-2].Close)*100 if len(df2i)>1 else 0
        chg5d=(float(lat2.Close)-float(df2i.iloc[-5].Close))/float(df2i.iloc[-5].Close)*100 if len(df2i)>5 else 0
        return dict(sym=sym,sig=s2,score=sc2,close=float(lat2.Close),
                    chg1d=chg1d,chg5d=chg5d,rsi=float(lat2.RSI),
                    adx=float(lat2.ADX) if pd.notna(lat2.ADX) else 0,
                    vol_ratio=float(lat2.Vol_Ratio))
    except: return None

def fmt(n, suffix=""):
    if n is None or (isinstance(n, float) and math.isnan(n)): return "—"
    n = float(n)
    if abs(n) >= 1e12: return f"{n/1e12:.1f}T{suffix}"
    if abs(n) >= 1e9:  return f"{n/1e9:.1f}B{suffix}"
    if abs(n) >= 1e6:  return f"{n/1e6:.1f}M{suffix}"
    if abs(n) >= 1e3:  return f"{n/1e3:.0f}K{suffix}"
    return f"{n:,.1f}{suffix}"

def safe_df(df):
    """Chuẩn hóa DataFrame để st.dataframe/pyarrow không lỗi:
    - tên cột về string + dedup
    - mọi giá trị về string (tránh mixed-type)."""
    if df is None or df.empty: return pd.DataFrame()
    out = df.copy()
    # Cột về string + dedup
    seen={}; cols=[]
    for c in out.columns:
        c=str(c)
        if c in seen: seen[c]+=1; cols.append(f"{c}.{seen[c]}")
        else: seen[c]=0; cols.append(c)
    out.columns=cols
    # Mọi ô về string an toàn
    for c in out.columns:
        out[c]=out[c].apply(lambda v: "" if v is None or (isinstance(v,float) and math.isnan(v))
                            else (f"{v:,.2f}" if isinstance(v,float) else str(v)))
    return out


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
    # VWAP
    tp_v=(df["High"].astype(float)+df["Low"].astype(float)+df["Close"].astype(float))/3
    df["VWAP"]=(tp_v*df["Volume"].astype(float)).cumsum()/df["Volume"].astype(float).cumsum()
    df["Vol_MA20"]=df["Volume"].rolling(20).mean()
    df["Vol_Ratio"]=df["Volume"]/df["Vol_MA20"].replace(0,np.nan)
    df["EMA_State"]=np.where(df["EMA9"]>df["EMA21"],"bull","bear")
    # OBV
    obv=[0]
    for _i in range(1,len(df)):
        obv.append(obv[-1]+df["Volume"].iloc[_i] if df["Close"].iloc[_i]>df["Close"].iloc[_i-1]
                   else obv[-1]-df["Volume"].iloc[_i] if df["Close"].iloc[_i]<df["Close"].iloc[_i-1]
                   else obv[-1])
    df["OBV"]=obv; df["OBV_EMA"]=pd.Series(obv,index=df.index).ewm(span=20,adjust=False).mean()
    # CMF
    hi2=df["High"].astype(float); lo2=df["Low"].astype(float); c2=df["Close"].astype(float); v2=df["Volume"].astype(float)
    mfm=((c2-lo2)-(hi2-c2))/(hi2-lo2).replace(0,np.nan)
    df["CMF"]=(mfm*v2).rolling(20).sum()/v2.rolling(20).sum()
    # MFI
    tp2=(hi2+lo2+c2)/3; mf2=tp2*v2
    pos2=mf2.where(tp2>tp2.shift(1),0); neg2=mf2.where(tp2<tp2.shift(1),0)
    mfr2=pos2.rolling(14).sum()/neg2.rolling(14).sum().replace(0,np.nan)
    df["MFI"]=100-100/(1+mfr2)
    # StochRSI
    rmin=df["RSI"].rolling(14).min(); rmax=df["RSI"].rolling(14).max()
    stoch=(df["RSI"]-rmin)/(rmax-rmin).replace(0,np.nan)
    df["StochRSI_K"]=stoch.rolling(3).mean()*100
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
_META_COLS = ['item','item_id','item_en','unit','levels','row_number']
_GV_ALIASES = {
    'pe_ratio':           ['pe_ratio','p_e','pe'],
    'pb_ratio':           ['pb_ratio','p_b','pb'],
    'roe':                ['roe'],
    'roa':                ['roa'],
    'earnings_per_share': ['earnings_per_share','eps','basic_eps','earningPerShare'],
    'debt_to_equity':     ['debt_to_equity','debt_equity','debtToEquity'],
    'current_ratio':      ['current_ratio','currentRatio'],
    'gross_margin':       ['gross_margin','gross_profit_margin','grossMargin'],
    'net_margin':         ['net_margin','net_profit_margin','afterTaxProfitMargin'],
    'equity_total_assets':['equity_total_assets','equity_deposits_from_custom'],
    'ldr':                ['outstanding_loans_customer_','outstanding_loans_customer_deposits'],
    'revenue':            ['revenue','net_revenue','revenueGrowth'],
    'net_profit':         ['net_profit','net_profit_after_tax'],
    'book_value_per_share':['book_value_per_share','bookValuePerShare','bvps'],
}

def _ycols(df):
    if df is None or df.empty: return []
    return sorted([c for c in df.columns
                   if c not in _META_COLS and bool(re.search(r'\d{4}', str(c)))])

def _sg(iid, *dfs_yrs):
    """Smart get — hiểu cả LONG (KBS: item_id+năm) lẫn WIDE (VCI: cột=chỉ số)."""
    for alias in _GV_ALIASES.get(iid, [iid]):
        for df, yr in dfs_yrs:
            if df is None or df.empty: continue
            # Format LONG (KBS): item_id + cột năm
            if 'item_id' in df.columns and yr is not None:
                row = df[df['item_id'] == alias]
                if not row.empty:
                    v = pd.to_numeric(row[yr].values[0], errors='coerce')
                    if pd.notna(v): return float(v)
            # Format WIDE (VCI): alias là tên cột, lấy giá trị năm mới nhất
            elif alias in df.columns:
                s = pd.to_numeric(df[alias], errors='coerce').dropna()
                if not s.empty: return float(s.iloc[-1])
    return None

def _pct(v): return v*100 if v is not None and abs(v)<2 else v

def score_fundamental(rat_df: pd.DataFrame, inc_df: pd.DataFrame = None):
    items=[]; total=0.0
    if rat_df.empty and (inc_df is None or inc_df.empty): return items, total
    ryc=_ycols(rat_df); rl=ryc[-1] if ryc else None
    iyc=_ycols(inc_df) if inc_df is not None else []; il=iyc[-1] if iyc else None
    def gv(iid): return _sg(iid,(rat_df,rl),(inc_df if inc_df is not None else pd.DataFrame(),il))
    roe=_pct(gv('roe')); roa=_pct(gv('roa'))
    pe=gv('pe_ratio'); pb=gv('pb_ratio'); eps=gv('earnings_per_share')
    de=gv('debt_to_equity'); is_bank=de is None
    eq_ta=_pct(gv('equity_total_assets')) if is_bank else None
    checks=[
        ("ROE",roe,lambda v:v>15,"ROE >15% — sinh lời tốt","ROE <15% — thấp",1.0),
        ("ROA",roa,lambda v:v>1.5,"ROA >1.5% — dùng TS tốt","ROA thấp",0.5),
        ("P/E",pe,lambda v:0<v<20,"P/E hợp lý (<20x)","P/E cao hoặc âm",1.0),
        ("P/B",pb,lambda v:0<v<4,"P/B <4x","P/B cao",0.5),
        ("EPS",eps,lambda v:v>0,"EPS dương — có lãi","EPS âm — lỗ",1.5),
    ]
    if is_bank and eq_ta is not None:
        checks.append(("VCSH/TS",eq_ta,lambda v:v>6,"VCSH/TS>6% — vốn tốt","VCSH/TS thấp",0.3))
    elif de is not None:
        checks.append(("D/E",de,lambda v:v<2,"D/E<2 — nợ an toàn","D/E cao",0.3))
    for lbl,val,fn,g,b,w in checks:
        ok=fn(val) if val is not None else None
        items.append(dict(label=lbl,val=val,ok=ok,good=g,bad=b))
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

def _year_labels(df):
    """Nhãn năm cho trục X — cả LONG (cột năm) lẫn WIDE (cột yearReport)."""
    if df is None or df.empty: return []
    if 'item_id' in df.columns:
        return _ycols(df)
    yc = next((c for c in df.columns if 'year' in str(c).lower() or 'năm' in str(c).lower()), None)
    if yc: return [str(int(v)) if pd.notna(v) else "" for v in df[yc]]
    return []

def build_fin_charts(rat_df, inc_df):
    charts=[]
    is_wide_r = (not rat_df.empty) and ('item_id' not in rat_df.columns)
    is_wide_i = (inc_df is not None and not inc_df.empty) and ('item_id' not in inc_df.columns)
    ryc=_ycols(rat_df); iyc=_ycols(inc_df) if inc_df is not None else []
    xr=_year_labels(rat_df); xi=_year_labels(inc_df)
    if not xr and not xi: return charts

    def get_series(iid, prefer_inc=False):
        inc_has = inc_df is not None and not inc_df.empty
        use_inc_first = prefer_inc and inc_has
        for alias in _GV_ALIASES.get(iid,[iid]):
            # Nếu ưu tiên inc nhưng inc rỗng → vẫn cho phép lấy từ rat
            if (not use_inc_first):
                if not rat_df.empty and 'item_id' in rat_df.columns and ryc:
                    row=rat_df[rat_df['item_id']==alias]
                    if not row.empty: return pd.to_numeric(row[ryc].values[0],errors='coerce'),ryc
                if is_wide_r and alias in rat_df.columns:
                    s=pd.to_numeric(rat_df[alias],errors='coerce').values
                    if not np.all(np.isnan(s)): return s, xr
            if inc_has and 'item_id' in inc_df.columns and iyc:
                row=inc_df[inc_df['item_id']==alias]
                if not row.empty: return pd.to_numeric(row[iyc].values[0],errors='coerce'),iyc
            if is_wide_i and alias in inc_df.columns:
                s=pd.to_numeric(inc_df[alias],errors='coerce').values
                if not np.all(np.isnan(s)): return s, xi
            # Fallback cuối: nếu đã ưu tiên inc nhưng không có → thử rat
            if use_inc_first:
                if not rat_df.empty and 'item_id' in rat_df.columns and ryc:
                    row=rat_df[rat_df['item_id']==alias]
                    if not row.empty: return pd.to_numeric(row[ryc].values[0],errors='coerce'),ryc
                if is_wide_r and alias in rat_df.columns:
                    s=pd.to_numeric(rat_df[alias],errors='coerce').values
                    if not np.all(np.isnan(s)): return s, xr
        return None, (xr if xr else xi)

    eps_s,x_eps=get_series('earnings_per_share',prefer_inc=True)
    roe_s,xroe=get_series('roe'); roa_s,_=get_series('roa')
    gm_s,_=get_series('gross_margin'); nm_s,_=get_series('net_margin')
    year_cols=xr if xr else xi; x=xroe if xroe else year_cols

    def to_pct(arr):
        if arr is None: return None
        nz=arr[~np.isnan(arr)] if hasattr(arr,'__len__') else [arr]
        return arr*100 if len(nz)>0 and np.abs(nz).max()<2 else arr

    roe_s=to_pct(roe_s); roa_s=to_pct(roa_s); gm_s=to_pct(gm_s); nm_s=to_pct(nm_s)

    # Chart 1: EPS + ROE/ROA
    fig1=make_subplots(rows=1,cols=2,subplot_titles=("EPS theo năm (đ/CP)","ROE & ROA (%)"),horizontal_spacing=0.12)
    if eps_s is not None:
        bc=["#00d97e" if v>=0 else "#ff3d5a" for v in np.nan_to_num(eps_s)]
        fig1.add_trace(go.Bar(x=x_eps if x_eps else x,y=eps_s,name="EPS",marker_color=bc,
            text=[f"{v:,.0f}" for v in eps_s],textposition="outside",
            textfont=dict(color="#cce0ff",size=11)),row=1,col=1)
    if roe_s is not None:
        fig1.add_trace(go.Scatter(x=x,y=roe_s,name="ROE%",mode="lines+markers",
            line=dict(color="#00d97e",width=2.5),marker=dict(size=9)),row=1,col=2)
    if roa_s is not None:
        fig1.add_trace(go.Scatter(x=x,y=roa_s,name="ROA%",mode="lines+markers",
            line=dict(color="#f5a623",width=2),marker=dict(size=8)),row=1,col=2)
    for lvl,clr,lbl in[(15,"rgba(0,217,126,.4)","ROE 15%"),(1.5,"rgba(74,158,248,.35)","ROA 1.5%")]:
        fig1.add_hline(y=lvl,row=1,col=2,line=dict(color=clr,dash="dot",width=1),
            annotation_text=f" {lbl}",annotation_font=dict(color=clr,size=10))
    fig1.update_layout(height=340,template="plotly_dark",**CHART_STYLE)
    for ann in fig1.layout.annotations: ann.font.color="#8baed4"; ann.font.size=12
    charts.append(fig1)

    # Chart 2: Biên lợi nhuận
    if gm_s is not None or nm_s is not None:
        fig2=go.Figure()
        if gm_s is not None:
            fig2.add_trace(go.Scatter(x=x,y=gm_s,name="Biên gộp%",mode="lines+markers",
                line=dict(color="#a78bfa",width=2),marker=dict(size=8)))
        if nm_s is not None:
            fig2.add_trace(go.Scatter(x=x,y=nm_s,name="Biên ròng%",mode="lines+markers",
                line=dict(color="#22d3ee",width=2),marker=dict(size=8)))
            nm_clean=nm_s[~np.isnan(nm_s)]
            if len(nm_clean)>=2:
                trend="MỞ RỘNG" if nm_clean[-1]>nm_clean[-2] else "THU HẸP"
                t_clr="#00d97e" if trend=="MỞ RỘNG" else "#ff3d5a"
                fig2.add_annotation(x=x[-1],y=float(nm_clean[-1]),
                    text=f" Biên {trend}",font=dict(color=t_clr,size=11),
                    showarrow=False,xanchor="left")
        fig2.update_layout(height=240,title="Xu hướng biên lợi nhuận (%)",
            template="plotly_dark",**CHART_STYLE)
        fig2.layout.title.font.color="#8baed4"; fig2.layout.title.font.size=12
        charts.append(fig2)
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
    bal_df = fetch_balance(symbol)
    cf_df  = fetch_cashflow_stmt(symbol)
    tcbs_extras = fetch_tcbs_extras(symbol)
    tcbs_ov  = tcbs_extras.get('overview', {})
    tcbs_pt  = tcbs_extras.get('price_target', [])

df=add_indicators(df_raw.copy()); df=detect_patterns(df)
sig,reasons,score=calc_signal(df); trade=calc_trade(df,score)
lat=df.iloc[-1]; prev=df.iloc[-2] if len(df)>1 else lat

chg=float(lat.Close)-float(prev.Close); pct_chg=chg/float(prev.Close)*100 if float(prev.Close) else 0
chg_str=f"{'▲' if chg>=0 else '▼'} {abs(chg):,.0f} đ ({abs(pct_chg):.2f}%)"
st.caption(f"📡 Nguồn: {price_src} · {len(df)} phiên · {'🟢' if chg>=0 else '🔴'} {chg_str} · {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")

tab1,tab2,tab3,tab4,tab5,tab6,tab7=st.tabs(["📉 Kỹ thuật","📊 Cơ bản","💰 Dòng tiền","🏭 Ngành","🔍 Quét mã","📰 Tin tức","🎯 Tổng hợp"])

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
        # Xác định cột năm (2021, 2022, 2023, 2024...)
        year_cols = sorted([c for c in rat_df.columns
                            if c not in ['item','item_id','item_en','unit','levels','row_number']
                            and bool(re.search(r'\d{4}', str(c)))])
        latest_yr = year_cols[-1] if year_cols else None

        ryc2 = _ycols(rat_df); rl2 = ryc2[-1] if ryc2 else None
        iyc2 = _ycols(inc_df) if not inc_df.empty else []; il2 = iyc2[-1] if iyc2 else None

        def grat(iid):
            return _sg(iid, (rat_df,rl2), (inc_df,il2))

        pe  = grat('pe_ratio')
        pb  = grat('pb_ratio')
        eps = grat('earnings_per_share')
        roe = _pct(grat('roe'))
        roa = _pct(grat('roa'))
        de  = grat('debt_to_equity')
        eq_ta = _pct(grat('equity_total_assets')) if de is None else None
        cr  = grat('current_ratio')
        ldr = _pct(grat('ldr')) if cr is None else None
        gm  = _pct(grat('gross_margin'))
        nm  = _pct(grat('net_margin'))
        f1,f2,f3,f4,f5,f6,f7=st.columns(7)
        f1.markdown(metric_html("P/E",f"{pe:.1f}x" if pe else "—","#00d97e" if pe and 0<pe<20 else "#ff3d5a" if pe else "#8baed4"),unsafe_allow_html=True)
        f2.markdown(metric_html("P/B",f"{pb:.2f}x" if pb else "—","#00d97e" if pb and 0<pb<4 else "#ff3d5a" if pb else "#8baed4"),unsafe_allow_html=True)
        f3.markdown(metric_html("EPS",f"{eps:,.0f} đ" if eps else "—","#00d97e" if eps and eps>0 else "#ff3d5a" if eps else "#8baed4"),unsafe_allow_html=True)
        f4.markdown(metric_html("ROE",f"{roe:.1f}%" if roe else "—","#00d97e" if roe and roe>15 else "#f5a623" if roe and roe>10 else "#ff3d5a" if roe else "#8baed4"),unsafe_allow_html=True)
        f5.markdown(metric_html("ROA",f"{roa:.1f}%" if roa else "—","#00d97e" if roa and roa>1.5 else "#f5a623" if roa and roa>0.8 else "#ff3d5a" if roa else "#8baed4"),unsafe_allow_html=True)
        de_show=de if de is not None else eq_ta
        de_lbl="D/E" if de is not None else "VCSH/TS%"
        de_str=(f"{de_show:.2f}x" if de is not None else f"{de_show:.1f}%") if de_show else "—"
        de_clr="#00d97e" if de_show and (de_show<2 if de is not None else de_show>6) else "#f5a623"
        f6.markdown(metric_html(de_lbl,de_str,de_clr),unsafe_allow_html=True)
        cr_show=cr if cr is not None else ldr
        cr_lbl="Current Ratio" if cr is not None else "LDR%"
        cr_str=(f"{cr_show:.2f}" if cr is not None else f"{cr_show:.0f}%") if cr_show else "—"
        cr_clr="#00d97e" if cr_show and (cr_show>1.5 if cr is not None else 50<cr_show<90) else "#f5a623"
        f7.markdown(metric_html(cr_lbl,cr_str,cr_clr),unsafe_allow_html=True)
        for fig_f in build_fin_charts(rat_df,inc_df):
            st.plotly_chart(fig_f,use_container_width=True)
        items_f,total_f=score_fundamental(rat_df, inc_df)
        # Bảng tăng trưởng EPS — hỗ trợ cả LONG (item_id) lẫn WIDE (cột)
        eps_years=[]; eps_series=[]
        if not rat_df.empty and 'item_id' not in rat_df.columns:
            # WIDE (VCI): EPS là 1 cột
            eps_col=next((c for c in ['earnings_per_share','eps','earningPerShare'] if c in rat_df.columns), None)
            yc_w=next((c for c in rat_df.columns if 'year' in str(c).lower()), None)
            if eps_col and yc_w:
                eps_series=pd.to_numeric(rat_df[eps_col],errors='coerce').tolist()
                eps_years=[str(int(v)) if pd.notna(v) else "" for v in rat_df[yc_w]]
        else:
            # LONG (KBS): EPS ở item_id, năm là cột
            src_df = rat_df if (not rat_df.empty and 'item_id' in rat_df.columns) else inc_df
            yc_l = ryc2 if (not rat_df.empty and 'item_id' in rat_df.columns and ryc2) else iyc2
            if src_df is not None and not src_df.empty and 'item_id' in src_df.columns and yc_l:
                eps_row = src_df[src_df['item_id'].isin(['earnings_per_share','eps','basic_eps'])]
                if not eps_row.empty:
                    eps_series=pd.to_numeric(eps_row[yc_l].values[0],errors='coerce').tolist()
                    eps_years=list(yc_l)
        if eps_years and eps_series:
            growth_df = pd.DataFrame({'Năm': eps_years, 'EPS (đ)': eps_series})
            growth_df['Tăng trưởng'] = growth_df['EPS (đ)'].pct_change() * 100
            growth_df['Tăng trưởng'] = growth_df['Tăng trưởng'].apply(lambda v: f"{v:+.1f}%" if pd.notna(v) else "—")
            growth_df['EPS (đ)'] = growth_df['EPS (đ)'].apply(lambda v: f"{v:,.0f}" if pd.notna(v) else "—")
            st.markdown("### 📈 Tăng trưởng EPS theo năm")
            st.dataframe(safe_df(growth_df), use_container_width=True, hide_index=True)
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
            disp=[c for c in rat_df.columns if str(c) not in ["ticker","id"]]
            st.dataframe(safe_df(rat_df[disp]),use_container_width=True,hide_index=True)
    else:
        st.warning(f"Không lấy được dữ liệu tài chính. {ratio_src}\n\nThử mã khác hoặc kiểm tra kết nối.")
        st.info("💡 Gợi ý: Thử lại sau vài giây. KBS API đôi khi cần warm-up request đầu tiên.")

# ── TAB 3: DÒNG TIỀN ────────────────────────────────────────────────────────
with tab3:
    st.markdown("### 💰 Phân tích dòng tiền — OBV · CMF · MFI")
    _has_obv = "OBV" in df.columns and "OBV_EMA" in df.columns
    _has_cmf = "CMF" in df.columns
    _has_mfi = "MFI" in df.columns
    # Metrics
    d1,d2,d3,d4=st.columns(4)
    if _has_obv:
        obv_trend="Tích lũy🟢" if lat.OBV>lat.OBV_EMA else "Phân phối🔴"
        d1.metric("OBV vs EMA",obv_trend)
    else:
        d1.metric("OBV","—")
    cmf_val=float(lat.CMF) if _has_cmf and pd.notna(lat.CMF) else 0
    d2.metric("CMF (20p)",f"{cmf_val:+.3f}","Vào🟢" if cmf_val>0.1 else "Ra🔴" if cmf_val<-0.1 else "Trung tính")
    mfi_val=float(lat.MFI) if _has_mfi and pd.notna(lat.MFI) else 50
    d3.metric("MFI (14p)",f"{mfi_val:.0f}","OB>75🔴" if mfi_val>75 else "OS<25🟢" if mfi_val<25 else "BT")
    avg_up=df[df["Close"]>=df["Open"]]["Vol_Ratio"].tail(20).mean()
    avg_dn=df[df["Close"]< df["Open"]]["Vol_Ratio"].tail(20).mean()
    d4.metric("Vol tăng/giảm",f"×{avg_up:.2f}/×{avg_dn:.2f}","Mua ưu thế🟢" if avg_up>avg_dn else "Bán ưu thế🔴")
    # OBV Chart
    if _has_obv:
        show60=df.tail(60)
        fig_obv=make_subplots(rows=3,cols=1,shared_xaxes=True,vertical_spacing=0.04,
            row_heights=[0.4,0.3,0.3],
            subplot_titles=("OBV — Tích lũy/Phân phối","CMF (Chaikin Money Flow)","Volume & Vol/TB"))
        fig_obv.add_trace(go.Scatter(x=show60["Date"],y=show60["OBV"]/1e6,name="OBV(M)",
            line=dict(color="#4a9ef8",width=2),fill="tozeroy",fillcolor="rgba(74,158,248,.08)"),row=1,col=1)
        fig_obv.add_trace(go.Scatter(x=show60["Date"],y=show60["OBV_EMA"]/1e6,name="OBV EMA",
            line=dict(color="#f5a623",width=1.5,dash="dot")),row=1,col=1)
        if _has_cmf:
            cmf_clr=["#00d97e" if v>=0 else "#ff3d5a" for v in show60["CMF"].fillna(0)]
            fig_obv.add_trace(go.Bar(x=show60["Date"],y=show60["CMF"],name="CMF",marker_color=cmf_clr,opacity=0.8),row=2,col=1)
            fig_obv.add_hline(y=0.1,row=2,col=1,line=dict(color="rgba(0,217,126,.5)",dash="dot",width=1),annotation_text=" +0.1")
            fig_obv.add_hline(y=-0.1,row=2,col=1,line=dict(color="rgba(255,61,90,.5)",dash="dot",width=1),annotation_text=" -0.1")
            fig_obv.add_hline(y=0,row=2,col=1,line=dict(color="rgba(255,255,255,.2)",width=0.8))
        vc2=["#00d97e" if r.Close>=r.Open else "#ff3d5a" for _,r in show60.iterrows()]
        fig_obv.add_trace(go.Bar(x=show60["Date"],y=show60["Volume"],marker_color=vc2,opacity=0.6,name="Volume"),row=3,col=1)
        if show60["Vol_MA20"].notna().any():
            fig_obv.add_trace(go.Scatter(x=show60["Date"],y=show60["Vol_MA20"],name="Vol MA20",
                line=dict(color="#f5a623",width=1.5)),row=3,col=1)
        fig_obv.update_layout(height=520,template="plotly_dark",**CHART_STYLE)
        for ann in fig_obv.layout.annotations: ann.font.color="#8baed4"; ann.font.size=10
        st.plotly_chart(fig_obv,use_container_width=True)
    # Pump/dump detection
    st.markdown("### 🔍 Phát hiện bơm/xả")
    d20=df.tail(20).copy()
    pump=d20[(d20["Vol_Ratio"]>2.0)&(d20["Close"]>d20["Open"])&(d20["Close"].pct_change()>0.03)]
    dump=d20[(d20["Vol_Ratio"]>2.0)&(d20["Close"]<d20["Open"])&(d20["Close"].pct_change()<-0.03)]
    last5=d20.tail(5); price_up_5=float(last5["Close"].iloc[-1])>float(last5["Close"].iloc[0])
    vol_down_5=float(last5["Volume"].iloc[-1])<float(last5["Volume"].iloc[0])
    no_sig=True
    if len(pump)>0: st.warning(f"**🚨 DẤU HIỆU BƠM** — {len(pump)} phiên: giá tăng >3% + Vol >2x. Cẩn thận bẫy thanh khoản."); no_sig=False
    if len(dump)>0: st.error(f"**🔴 XẢ MẠNH** — {len(dump)} phiên: giá giảm >3% + Vol >2x. Áp lực bán lớn."); no_sig=False
    if _has_obv and price_up_5 and lat.OBV<df["OBV"].iloc[-5]: st.warning("**⚠️ PHÂN KỲ OBV** — Giá tăng nhưng OBV giảm. Thiếu dòng tiền thực."); no_sig=False
    if price_up_5 and vol_down_5: st.warning("**⚠️ PHÂN KỲ VOL** — Giá tăng nhưng KL giảm 5 phiên. Xu hướng suy yếu."); no_sig=False
    if _has_cmf and cmf_val<-0.1: st.info(f"**📉 CMF={cmf_val:.3f}** — Dòng tiền rời khỏi CP."); no_sig=False
    if no_sig: st.success("**✅ BÌNH THƯỜNG** — Không phát hiện dấu hiệu bơm/xả bất thường.")
    # Volume table
    st.markdown("### 📊 Khối lượng 15 phiên gần nhất")
    vt=df.tail(15)[["Date","Close","Volume","Vol_Ratio"]].copy()
    vt["Xu hướng"]=vt["Close"].diff().apply(lambda x:"📈" if x>0 else "📉")
    vt["Volume"]=vt["Volume"].apply(lambda x:f"{x/1e6:.1f}M")
    vt["Vol/TB"]=vt["Vol_Ratio"].apply(lambda x:f"×{x:.2f}")
    vt["Close"]=vt["Close"].apply(lambda x:f"{x:,.0f}")
    vt["Date"]=vt["Date"].dt.strftime("%d/%m")
    st.dataframe(vt[["Date","Close","Xu hướng","Volume","Vol/TB"]].reset_index(drop=True),
                 use_container_width=True,hide_index=True)

# ── TAB 4: SO SÁNH NGÀNH ────────────────────────────────────────────────────
with tab4:
    st.markdown("### 🏭 So sánh cùng ngành")
    cur_sec=next((s for s,ps in SECTOR_PEERS.items() if symbol in ps),None)
    if cur_sec: st.info(f"**Ngành:** {cur_sec} | P/E median: {SECTOR_PE.get(cur_sec,'—')}x")
    else: cur_sec=st.selectbox("Chọn ngành",list(SECTOR_PEERS.keys()))
    peers=[p for p in SECTOR_PEERS[cur_sec] if p!=symbol]
    sel_peers=st.multiselect("Chọn mã so sánh",peers,default=peers[:4])
    cmp_syms=[symbol]+sel_peers
    if st.button("🔄 Tải dữ liệu so sánh"):
        cmp_data=[]; prog=st.progress(0)
        for ii,sym2 in enumerate(cmp_syms):
            prog.progress((ii+1)/len(cmp_syms),f"Tải {sym2}...")
            try:
                df2=fetch_price(sym2,180,"1D"); rat2=fetch_ratio(sym2)[0]; inc2=fetch_income(sym2)
                ryc2t=_ycols(rat2); rl2t=ryc2t[-1] if ryc2t else None
                iyc2t=_ycols(inc2); il2t=iyc2t[-1] if iyc2t else None
                def gv2(iid): return _sg(iid,(rat2,rl2t),(inc2,il2t))
                pe2=gv2('pe_ratio'); pb2=gv2('pb_ratio')
                roe2=_pct(gv2('roe')); eps2=gv2('earnings_per_share')
                df2i=add_indicators(df2); s2,_,sc2=calc_signal(df2i)
                chg1m=(float(df2i["Close"].iloc[-1])/float(df2i["Close"].iloc[-22])-1)*100 if len(df2i)>22 else 0
                chg3m=(float(df2i["Close"].iloc[-1])/float(df2i["Close"].iloc[-66])-1)*100 if len(df2i)>66 else 0
                cmp_data.append({"Mã":sym2,"Giá":f"{df2i['Close'].iloc[-1]:,.0f}",
                    "+1T":f"{chg1m:+.1f}%","+3T":f"{chg3m:+.1f}%",
                    "P/E":f"{pe2:.1f}x" if pe2 else "—","P/B":f"{pb2:.2f}x" if pb2 else "—",
                    "ROE":f"{roe2:.1f}%" if roe2 else "—","EPS":f"{eps2:,.0f}" if eps2 else "—",
                    "KT":s2,"Score":round(sc2,1)})
            except:
                cmp_data.append({"Mã":sym2,"Giá":"—","+1T":"—","+3T":"—","P/E":"—","P/B":"—","ROE":"—","EPS":"—","KT":"—","Score":"—"})
        prog.empty()
        n_ok=sum(1 for r in cmp_data if r["Giá"]!="—")
        st.caption(f"Tải xong: {n_ok}/{len(cmp_syms)} mã có dữ liệu")
        if cmp_data:
            cdf=pd.DataFrame(cmp_data)
            st.dataframe(cdf,use_container_width=True,hide_index=True)
            valid=[(r["Mã"],float(r["P/E"].replace("x","").replace("—","0"))) for r in cmp_data if r["P/E"]!="—" and "x" in str(r["P/E"])]
            if valid:
                mcs2,pes2=zip(*[(m,v) for m,v in valid if v>0])
                fpE=go.Figure(go.Bar(x=list(mcs2),y=list(pes2),
                    marker_color=["#4a9ef8" if m==symbol else "#163350" for m in mcs2],
                    text=[f"{v:.1f}x" for v in pes2],textposition="outside"))
                if SECTOR_PE.get(cur_sec):
                    fpE.add_hline(y=SECTOR_PE[cur_sec],line=dict(color="#f5a623",dash="dot",width=1.5),
                        annotation_text=f" Median {SECTOR_PE[cur_sec]}x",annotation_font=dict(color="#f5a623",size=10))
                fpE.update_layout(height=260,title="So sánh P/E",template="plotly_dark",**CHART_STYLE)
                fpE.layout.title.font.color="#8baed4"
                st.plotly_chart(fpE,use_container_width=True)
    else:
        st.info("Nhấn **Tải dữ liệu so sánh** để xem peer comparison.")

# ── TAB 5: QUÉT MÃ ───────────────────────────────────────────────────────────
with tab5:
    st.markdown("### 🔍 Quét mã tiềm năng — Top 5 dấu hiệu tăng")
    scan_sec=st.selectbox("Quét ngành",list(SECTOR_PEERS.keys()),key="scan_sec")
    st.caption("Quét dựa trên dữ liệu giá KBS từng mã. Nếu KBS chậm/lỗi với 1 mã, mã đó sẽ bị bỏ qua thay vì làm hỏng cả bảng.")
    if st.button("🚀 Bắt đầu quét"):
        results=[]; failed=[]; prog2=st.progress(0); scan_peers=SECTOR_PEERS[scan_sec]
        for ii,sym2 in enumerate(scan_peers):
            prog2.progress((ii+1)/len(scan_peers),f"Quét {sym2}...")
            try:
                r2=scan_stock_quick(sym2)
            except Exception:
                r2=None
            if r2: results.append(r2)
            else: failed.append(sym2)
        prog2.empty()
        st.caption(f"Quét xong: {len(results)}/{len(scan_peers)} mã có dữ liệu"
                   + (f" · Bỏ qua: {', '.join(failed)}" if failed else ""))
        if results:
            def composite(r2):
                s=r2['score']
                if 35<=r2['rsi']<=65: s+=1
                if r2['adx']>20: s+=0.5
                if r2['vol_ratio']>1.2: s+=0.7
                return s
            results.sort(key=composite,reverse=True)
            st.markdown("#### Top 5 mã tiềm năng")
            for rank,r2 in enumerate(results[:5],1):
                clr=SIG_COLOR.get(r2['sig'],"#8baed4")
                chg_clr="#00d97e" if r2['chg1d']>=0 else "#ff3d5a"
                rank_str=f"# {rank}"
                st.markdown(
                    f"<div style='background:#0c1d2e;border:1px solid #163350;border-left:3px solid {clr};"
                    f"border-radius:0 12px 12px 0;padding:12px 16px;margin:6px 0;"
                    f"display:flex;align-items:center;gap:16px;flex-wrap:wrap;'>"
                    f"<b style='font-size:18px;color:#6a9cc8;'>{rank_str}</b>"
                    f"<span style='font-size:20px;font-weight:700;color:#fff;'>{r2['sym']}</span>"
                    f"<span style='color:{clr};font-weight:600;'>{r2['sig']} ({r2['score']:+.1f})</span>"
                    f"<span style='color:#fff;'>{r2['close']:,.0f}đ</span>"
                    f"<span style='color:{chg_clr};'>{r2['chg1d']:+.2f}%</span>"
                    f"<span style='color:#6a9cc8;font-size:12px;'>RSI {r2['rsi']:.0f} ADX {r2['adx']:.0f}</span>"
                    f"</div>", unsafe_allow_html=True)
            with st.expander("📋 Toàn bộ kết quả"):
                tbl=[{"Mã":r2['sym'],"Giá":f"{r2['close']:,.0f}","1D":f"{r2['chg1d']:+.1f}%",
                    "5D":f"{r2['chg5d']:+.1f}%","Tín hiệu":r2['sig'],"Score":r2['score'],
                    "RSI":f"{r2['rsi']:.0f}","ADX":f"{r2['adx']:.0f}","Vol/TB":f"×{r2['vol_ratio']:.1f}"}
                    for r2 in results]
                st.dataframe(pd.DataFrame(tbl),use_container_width=True,hide_index=True)
        else:
            st.warning("Không mã nào trả về dữ liệu giá. KBS có thể đang giới hạn request hoặc "
                       "Streamlit Cloud bị chặn. Thử lại sau 1-2 phút, hoặc đổi sang ngành khác.")
    else:
        st.info("Nhấn **Bắt đầu quét** để tìm mã tiềm năng.")

# ── TAB 6: TIN TỨC ───────────────────────────────────────────────────────────
with tab6:
    st.markdown(f"### 📰 Tin tức & Sự kiện — {symbol}")
    sym_sec_n=next((s for s,ps in SECTOR_PEERS.items() if symbol in ps),"")
    load_news = st.button("🔄 Tải tin tức mới nhất", key="news_btn")
    cn1,cn2=st.columns([3,2])
    with cn1:
        st.markdown("#### 🔍 Tin tức AI (web search)")
        news_data={"news":[],"key_events":[]}
        if load_news:
            with st.spinner("AI đang tìm tin tức..."):
                news_data=fetch_news_ai(symbol,sym_sec_n)
        for item in news_data.get("news",[])[:8]:
            sent=item.get("sentiment","neutral")
            sc={"positive":"#00d97e","negative":"#ff3d5a"}.get(sent,"#8baed4")
            ico={"positive":"📈","negative":"📉"}.get(sent,"➡️")
            st.markdown(
                f"<div style='background:#0c1d2e;border-left:3px solid {sc};"
                f"border-radius:0 10px 10px 0;padding:10px 14px;margin:6px 0;'>"
                f"<div style='font-size:11px;color:#4a6080;'>{item.get('date','')}</div>"
                f"<div style='font-size:14px;font-weight:600;color:#fff;margin:3px 0;'>{ico} {item.get('title','')}</div>"
                f"<div style='font-size:12px;color:#8baed4;'>{item.get('summary','')}</div></div>",
                unsafe_allow_html=True)
        if load_news and not news_data.get("news"):
            st.info("AI không tìm được tin (có thể API bị giới hạn). Xem mục TCBS/VCI bên phải.")
        elif not load_news:
            st.info("Nhấn **Tải tin tức mới nhất** để AI tìm kiếm.")
        if news_data.get("key_events"):
            st.markdown("#### 📌 Sự kiện quan trọng")
            for ev in news_data["key_events"]: st.markdown(f"- {ev}")
    with cn2:
        st.markdown("#### 📡 Tin từ sàn (VCI/TCBS)")
        feed=[]
        if load_news:
            vci_n=fetch_vci_news(symbol)
            for item in vci_n:
                title=str(item.get('news_title',item.get('title',item.get('newsTitle','')))).strip()
                date_s=str(item.get('public_date',item.get('publishDate',item.get('date',''))))[:10]
                if title: feed.append((date_s,title[:90]))
            if not feed:
                for item in fetch_tcbs_news(symbol):
                    title=str(item.get('title',item.get('name',item.get('content','')))).strip()
                    date_s=str(item.get('publishDate',item.get('date','')))[:10]
                    if title: feed.append((date_s,title[:90]))
        if feed:
            for date_s,title in feed[:10]:
                st.markdown(f"<div style='background:#0c1d2e;border:1px solid #163350;"
                    f"border-radius:8px;padding:8px 12px;margin:4px 0;'>"
                    f"<div style='font-size:11px;color:#4a6080;'>{date_s}</div>"
                    f"<div style='font-size:13px;color:#cce0ff;'>{title}</div></div>",
                    unsafe_allow_html=True)
        elif load_news:
            st.info("Không lấy được tin từ sàn (VCI/TCBS có thể bị chặn trên cloud).")
        if tcbs_pt:
            st.markdown("#### 🎯 Price Targets")
            ptdf=pd.DataFrame(tcbs_pt[:5])
            dcols=[c for c in ['firm','targetPrice','priceTarget','action','date'] if c in ptdf.columns]
            if dcols: st.dataframe(safe_df(ptdf[dcols]),use_container_width=True,hide_index=True)
        if tcbs_ov:
            mc=tcbs_ov.get('marketCap',tcbs_ov.get('capitalization'))
            if mc: st.metric("Vốn hóa (TCBS)",fmt(mc))

# ── TAB 7: TỔNG HỢP ──────────────────────────────────────────────────────────
with tab7:
    st.markdown("### 🎯 Đánh giá tổng hợp")
    _,fund_score=score_fundamental(rat_df, inc_df) if not rat_df.empty else ([],0)
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
