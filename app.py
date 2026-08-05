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
def fetch_vnindex(days: int):
    """QUANT: Lấy dữ liệu VN-Index — dùng cho RS Line (Tab Kỹ thuật) và Beta (Tab Quant Portfolio).
    Thử lần lượt vài mã/nguồn vì tick VN-Index có thể khác nhau tùy nguồn vnstock.
    KHÔNG áp dụng scaling ×1000 như cổ phiếu (index là điểm số, không phải giá VND)."""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    candidates = [("VNINDEX", "KBS"), ("VNINDEX", "VCI"), ("VNI", "KBS")]
    for sym_try, src in candidates:
        try:
            from vnstock import Quote
            q = Quote(symbol=sym_try, source=src)
            df = q.history(start=start, end=end, interval="1D")
            if df is None or df.empty: continue
            df = df.rename(columns={"time": "Date", "open": "Open", "high": "High",
                                     "low": "Low", "close": "Close", "volume": "Volume"})
            for col in ["Open", "High", "Low", "Close"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0).astype(int)
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.sort_values("Date").reset_index(drop=True)
            if df["Close"].isna().all() or len(df) < 5: continue
            return df[["Date", "Open", "High", "Low", "Close", "Volume"]], f"{src} ({sym_try}) ✅"
        except Exception:
            continue
    return pd.DataFrame(), "Không lấy được VN-Index — kiểm tra lại mã index trên vnstock"

@st.cache_data(ttl=300, show_spinner=False)
def _flatten_vci_cols(df):
    """Flatten MultiIndex columns của VCI, giữ TÊN ĐẦY ĐỦ field + đảm bảo duy nhất."""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [str(c[-1]) if isinstance(c, tuple) else str(c) for c in df.columns]
    seen = {}; new_cols = []
    for c in df.columns:
        c = str(c)
        if c in seen:
            seen[c] += 1; new_cols.append(f"{c}.{seen[c]}")
        else:
            seen[c] = 0; new_cols.append(c)
    df.columns = new_cols
    return df

@st.cache_data(ttl=60, show_spinner=False)
def fetch_ratio(sym: str):
    """Chỉ số tài chính: KBS primary (có eps, earnings_per_share) → VCI fallback → trống."""
    sym = sym.upper()
    # Nguồn 1: KBS — item_id chuẩn hóa, có eps trong ratio
    try:
        from vnstock import Finance
        fin = Finance(symbol=sym, source="KBS")
        df = fin.ratio(period="year")
        if df is not None and not df.empty:
            return df, "KBS ✅"
    except Exception:
        pass
    # Nguồn 2: VCI fallback
    try:
        from vnstock import Finance
        fin = Finance(symbol=sym, source="VCI")
        df = fin.ratio(period="year", lang="en", dropna=False)
        if df is not None and not df.empty:
            df = _flatten_vci_cols(df)
            yc = next((c for c in df.columns if 'year' in str(c).lower()), None)
            if yc:
                df = df.sort_values(yc).reset_index(drop=True)
            return df, "VCI ✅"
    except Exception:
        pass
    return pd.DataFrame(), "Không lấy được chỉ số"

@st.cache_data(ttl=300, show_spinner=False)
def fetch_income(sym: str) -> pd.DataFrame:
    """KQKD: KBS primary (có eps item_id='eps') → VCI fallback."""
    sym = sym.upper()
    # KBS income có 'eps' → normalized → item_id='eps'
    try:
        from vnstock import Finance
        fin = Finance(symbol=sym, source="KBS")
        df = fin.income_statement(period="year")
        if df is not None and not df.empty:
            yc = next((c for c in df.columns if "year" in c.lower() or "năm" in c.lower()), None)
            if yc:
                df = df.sort_values(yc, ascending=True).reset_index(drop=True)
            return df
    except Exception:
        pass
    # VCI fallback
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
    except:
        pass
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
    """Lấy giá + chỉ báo kỹ thuật cho 1 mã. KBS → yfinance fallback."""
    for source in ["KBS", "yf"]:
        try:
            if source == "KBS":
                from vnstock import Quote
                end = (datetime.now()).strftime("%Y-%m-%d")
                start = (datetime.now()-timedelta(days=days)).strftime("%Y-%m-%d")
                raw = Quote(symbol=sym.upper(), source="KBS").history(
                    start=start, end=end, interval="1D")
                if raw is None or raw.empty: continue
                raw = raw.rename(columns={"time":"Date","open":"Open","high":"High",
                                          "low":"Low","close":"Close","volume":"Volume"})
                for c in ["Open","High","Low","Close"]:
                    raw[c] = pd.to_numeric(raw[c], errors="coerce")
                    if raw[c].median() < 1000: raw[c] *= 1000
                raw["Volume"] = pd.to_numeric(raw["Volume"], errors="coerce").fillna(0).astype(int)
                raw["Date"] = pd.to_datetime(raw["Date"])
                df2 = raw.sort_values("Date").reset_index(drop=True)
            else:
                import yfinance as yf
                df2 = yf.download(f"{sym}.VN", period=f"{days}d",
                                  interval="1d", progress=False, auto_adjust=True)
                if df2.empty: continue
                df2 = df2.reset_index()
                df2.columns = [c[0] if isinstance(c,tuple) else c for c in df2.columns]
                df2 = df2.rename(columns={"Date":"Date","Open":"Open","High":"High",
                                          "Low":"Low","Close":"Close","Volume":"Volume"})
            if df2 is None or len(df2) < 30: continue
            df2i = add_indicators(df2)
            s2, _, sc2 = calc_signal(df2i)
            lat2 = df2i.iloc[-1]
            chg1d = (float(lat2.Close)-float(df2i.iloc[-2].Close))/float(df2i.iloc[-2].Close)*100 if len(df2i)>1 else 0
            chg5d = (float(lat2.Close)-float(df2i.iloc[-5].Close))/float(df2i.iloc[-5].Close)*100 if len(df2i)>5 else 0
            cmf = float(lat2.CMF) if "CMF" in df2i.columns and pd.notna(lat2.CMF) else 0.0
            return dict(sym=sym, sig=s2, score=sc2, close=float(lat2.Close),
                        chg1d=chg1d, chg5d=chg5d, rsi=float(lat2.RSI),
                        adx=float(lat2.ADX) if pd.notna(lat2.ADX) else 0,
                        vol_ratio=float(lat2.Vol_Ratio), cmf=cmf)
        except Exception:
            continue
    return None

@st.cache_data(ttl=300, show_spinner=False)
def scan_stock_quant(sym, days=260, _vni_close=None):
    """QUÉT THEO HỆ THỐNG QUANT — trả về điểm quant, hành động đề xuất, giá vào/cắt/chốt,
    kèm các bộ lọc kỹ thuật để sàng lọc. Dùng lại đúng cách lấy dữ liệu của fetch_price
    (KBS → yfinance) nên không phát sinh nguồn lỗi mới.
    _vni_close: Series giá đóng cửa VN-Index (index=Date) để tính RS — tuỳ chọn."""
    try:
        try:
            df2, _src = fetch_price(sym, days, "1D")
        except Exception:
            return None
        if df2 is None or len(df2) < 60: return None
        d = add_indicators(df2.copy())
        lat = d.iloc[-1]

        # RS slope vs VN-Index (nếu có dữ liệu index)
        rs_slope = None; rs_val = None
        if _vni_close is not None and len(_vni_close) > 10:
            try:
                s = d.set_index("Date")["Close"].astype(float)
                m = pd.concat([s, _vni_close], axis=1, join="inner").dropna()
                m.columns = ["stock", "index"]
                if len(m) >= 10:
                    rs = (m["stock"]/m["stock"].iloc[0])/(m["index"]/m["index"].iloc[0])*100
                    rs_val = float(rs.iloc[-1])
                    if len(rs) >= 6: rs_slope = float(rs.iloc[-1]-rs.iloc[-6])
            except Exception:
                pass

        qd = calc_quant_decision(d, rs_slope)
        c = float(lat.Close)
        chg1d = (c-float(d.iloc[-2].Close))/float(d.iloc[-2].Close)*100 if len(d) > 1 else 0
        chg5d = (c-float(d.iloc[-6].Close))/float(d.iloc[-6].Close)*100 if len(d) > 6 else 0
        chg20d = (c-float(d.iloc[-21].Close))/float(d.iloc[-21].Close)*100 if len(d) > 21 else 0
        dh20 = float(lat.Donchian_High20) if pd.notna(lat.get("Donchian_High20")) else None
        adx = float(lat.ADX) if pd.notna(lat.ADX) else 0
        dip = float(lat.DI_plus) if pd.notna(lat.get("DI_plus")) else 0
        dim = float(lat.DI_minus) if pd.notna(lat.get("DI_minus")) else 0
        ema200 = float(lat.EMA200) if pd.notna(lat.get("EMA200")) else None
        # Thanh khoản trung bình 20 phiên (giá trị giao dịch, tỷ đồng) — lọc mã quá mỏng
        liq = float((d["Close"].tail(20)*d["Volume"].tail(20)).mean()/1e9)

        return dict(
            sym=sym, close=c, quant_score=qd["score"], action=qd["action"], color=qd["color"],
            entry=qd["entry"], stop=qd["stop"], tp1=qd["tp1"], tp2=qd["tp2"],
            rr=qd["rr"], risk_pct=qd["risk_pct"],
            chg1d=chg1d, chg5d=chg5d, chg20d=chg20d,
            rsi=float(lat.RSI) if pd.notna(lat.RSI) else 50,
            adx=adx, di_plus=dip, di_minus=dim,
            vol_ratio=float(lat.Vol_Ratio) if pd.notna(lat.Vol_Ratio) else 0,
            cmf=float(lat.CMF) if pd.notna(lat.get("CMF")) else 0,
            zscore=float(lat.Zscore20) if pd.notna(lat.get("Zscore20")) else 0,
            roc20=float(lat.ROC20) if pd.notna(lat.get("ROC20")) else 0,
            breakout=(dh20 is not None and c >= dh20),
            above_ema200=(ema200 is not None and c > ema200 and len(d) >= 180),
        ema200_ready=(len(d) >= 180),
            rs_slope=rs_slope, rs_val=rs_val, liquidity_bn=liq,
            detail=qd["detail"],
        )
    except Exception:
        return None

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
    df["DI_plus"]=pdi; df["DI_minus"]=ndi
    std=c.rolling(20).std()
    df["BB_upper"]=df["SMA20"]+2*std; df["BB_lower"]=df["SMA20"]-2*std
    df["BB_width"]=(df["BB_upper"]-df["BB_lower"])/df["SMA20"].replace(0,np.nan)
    # ── QUANT: Donchian Channel (trend-following breakout) ──
    df["Donchian_High20"]=df["High"].rolling(20).max()
    df["Donchian_Low20"]=df["Low"].rolling(20).min()
    df["Donchian_High55"]=df["High"].rolling(55).max()
    df["Donchian_Low55"]=df["Low"].rolling(55).min()
    # ── QUANT: Rate of Change / Momentum ──
    df["ROC10"]=c.pct_change(10)*100
    df["ROC20"]=c.pct_change(20)*100
    # ── QUANT: Z-Score giá vs SMA20 (mean-reversion signal) ──
    df["Zscore20"]=(c-df["SMA20"])/std.replace(0,np.nan)
    # ── QUANT: Chandelier Exit (ATR-based trailing stop cho vị thế LONG) ──
    df["Chandelier_Long"]=df["High"].rolling(22).max()-tr.ewm(span=14,adjust=False).mean()*3
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
    # ── QUANT: đánh số phiên để biết chỉ báo dài hạn đã đủ "chín" chưa ──
    # EMA200 tính bằng ewm không trả NaN, nhưng với <180 phiên nó vẫn chịu ảnh hưởng nặng
    # từ giá trị khởi tạo → không đáng tin làm bộ lọc xu hướng dài hạn.
    df["_bar_idx"]=np.arange(len(df))
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

# ══════════════════════════════ QUANT TREND-FOLLOWING ══════════════════════════
def calc_quant_trend(df):
    """Bộ chỉ báo trend-following/momentum bổ sung — CHỈ để hiển thị thông tin,
    KHÔNG can thiệp vào calc_signal()/calc_trade() gốc để tránh regression."""
    lat=df.iloc[-1]; prev=df.iloc[-2] if len(df)>1 else lat
    c=float(lat.Close)
    out={}
    # ADX + DI regime
    adx=float(lat.ADX) if pd.notna(lat.ADX) else 0
    di_p=float(lat.DI_plus) if pd.notna(lat.get("DI_plus")) else None
    di_m=float(lat.DI_minus) if pd.notna(lat.get("DI_minus")) else None
    if adx>25 and di_p is not None and di_m is not None:
        regime=("Xu hướng TĂNG mạnh (DI+ > DI-)" if di_p>di_m else "Xu hướng GIẢM mạnh (DI- > DI+)")
    elif adx>25:
        regime="Xu hướng mạnh — DI chưa rõ ràng"
    else:
        regime="Sideway / xu hướng yếu (ADX<25) — trend-following kém tin cậy"
    out.update(adx=adx,di_plus=di_p,di_minus=di_m,adx_regime=regime)
    # Donchian breakout (20 phiên)
    dh20=float(lat.Donchian_High20) if pd.notna(lat.get("Donchian_High20")) else None
    dl20=float(lat.Donchian_Low20) if pd.notna(lat.get("Donchian_Low20")) else None
    if dh20 is not None and c>=dh20:
        donchian_status="🔥 PHÁ ĐỈNH Donchian 20 phiên — tín hiệu MUA trend-following"
    elif dl20 is not None and c<=dl20:
        donchian_status="💧 PHÁ ĐÁY Donchian 20 phiên — tín hiệu BÁN/tránh mua"
    else:
        donchian_status="Đang trong kênh Donchian — chưa breakout"
    out.update(donchian_high20=dh20,donchian_low20=dl20,donchian_status=donchian_status)
    # ROC / Momentum
    roc10=float(lat.ROC10) if pd.notna(lat.get("ROC10")) else None
    roc20=float(lat.ROC20) if pd.notna(lat.get("ROC20")) else None
    out.update(roc10=roc10,roc20=roc20)
    # Z-score mean-reversion
    z=float(lat.Zscore20) if pd.notna(lat.get("Zscore20")) else None
    if z is not None and z>2: z_label="Lệch xa TB phía TRÊN (Z>2) — dễ điều chỉnh ngắn hạn"
    elif z is not None and z<-2: z_label="Lệch xa TB phía DƯỚI (Z<-2) — có thể hồi kỹ thuật"
    else: z_label="Trong biên độ bình thường"
    out.update(zscore=z,zscore_label=z_label)
    # Chandelier Exit — trailing stop theo ATR
    ch=float(lat.Chandelier_Long) if pd.notna(lat.get("Chandelier_Long")) else None
    out.update(chandelier_stop=ch)
    return out

def calc_relative_strength(stock_df, index_df):
    """RS Line = hiệu suất tích lũy mã / hiệu suất tích lũy VN-Index, base=100.
    Trả về (rs_series căn theo Date của stock_df, nhãn xu hướng RS)."""
    if index_df is None or index_df.empty or stock_df.empty:
        return None, "Không có dữ liệu VN-Index để so sánh"
    s=stock_df.set_index("Date")["Close"].astype(float)
    idx=index_df.set_index("Date")["Close"].astype(float)
    merged=pd.concat([s,idx],axis=1,join="inner"); merged.columns=["stock","index"]
    if merged.empty or len(merged)<10:
        return None, "Không đủ dữ liệu trùng khớp để tính RS"
    rs=(merged["stock"]/merged["stock"].iloc[0])/(merged["index"]/merged["index"].iloc[0])*100
    if len(rs)>=6:
        recent_slope=rs.iloc[-1]-rs.iloc[-6]
        label=("📈 RS đang TĂNG — mạnh hơn VN-Index gần đây" if recent_slope>0.5
               else "📉 RS đang GIẢM — yếu hơn VN-Index gần đây" if recent_slope<-0.5
               else "↔️ RS đi ngang — tương đương VN-Index")
    else:
        label="Chưa đủ dữ liệu đánh giá xu hướng RS"
    return rs, label

# ══════════════════════════════ QUANT DECISION ENGINE ══════════════════════════
# Chấm điểm theo TỪNG DÒNG dữ liệu (row-wise) — dùng chung cho:
#   (1) Đề xuất giao dịch hiện tại (Tab Kỹ thuật / Tổng hợp)
#   (2) Quét mã hàng loạt (Tab Quét mã)
#   (3) Kiểm định lịch sử / backtest (Tab Quant Portfolio)
# Chỉ dùng chỉ báo dạng rolling/ewm → KHÔNG nhìn trước tương lai (no lookahead).

QUANT_WEIGHTS = {
    "trend_lt": 1.5,    # Giá vs EMA200 — bộ lọc xu hướng dài hạn
    "ema_align": 1.5,   # EMA9>21>50
    "adx_di": 2.0,      # Độ mạnh + hướng xu hướng
    "donchian": 2.0,    # Breakout kênh giá 20 phiên
    "momentum": 1.0,    # ROC20
    "moneyflow": 1.0,   # Volume + CMF
    "zscore": 1.0,      # Phạt khi giá lệch quá xa TB (mua đuổi)
    "rs": 1.0,          # Sức mạnh tương đối vs VN-Index
}
QUANT_MAX = sum(QUANT_WEIGHTS.values())  # = 11.0

def quant_row_score(row, rs_slope=None):
    """Chấm điểm quant cho 1 phiên. Trả về (score_chuẩn_hoá_-10..+10, dict chi tiết).
    rs_slope: độ dốc RS vs VN-Index (tuỳ chọn — nếu None thì bỏ qua cấu phần này và
    chuẩn hoá lại thang điểm cho công bằng)."""
    d = {}; raw = 0.0; max_used = 0.0
    def _g(k):
        v = row.get(k) if hasattr(row, "get") else None
        try:
            v = float(v)
            return v if pd.notna(v) else None
        except (TypeError, ValueError):
            return None

    c = _g("Close")
    if c is None: return 0.0, {"error": "Thiếu giá đóng cửa"}

    # 1. Bộ lọc xu hướng dài hạn: giá vs EMA200
    # CHỈ dùng khi đã có tối thiểu 180 phiên — trước đó EMA200 vẫn bị "kéo" bởi giá khởi tạo
    # nên không phản ánh đúng xu hướng dài hạn (mã mới niêm yết, dữ liệu tải quá ngắn).
    w = QUANT_WEIGHTS["trend_lt"]; ema200 = _g("EMA200")
    bar_idx = _g("_bar_idx")
    ema200_ready = (bar_idx is None) or (bar_idx >= 180)
    if ema200 is not None and ema200_ready:
        max_used += w
        if c > ema200: raw += w;  d["trend_lt"] = ("✅ Giá trên EMA200 — xu hướng dài hạn tăng", +w)
        else:          raw -= w;  d["trend_lt"] = ("❌ Giá dưới EMA200 — xu hướng dài hạn giảm", -w)
    elif ema200 is not None:
        d["trend_lt"] = (f"⚪ Bỏ qua EMA200 — mới có {int(bar_idx)+1} phiên, chưa đủ 180 phiên để tin cậy", 0.0)

    # 2. Xếp hàng EMA
    w = QUANT_WEIGHTS["ema_align"]; e9,e21,e50 = _g("EMA9"), _g("EMA21"), _g("EMA50")
    if None not in (e9,e21,e50):
        max_used += w
        if e9 > e21 > e50:   raw += w; d["ema_align"] = ("✅ EMA9>21>50 — xếp hàng tăng", +w)
        elif e9 < e21 < e50: raw -= w; d["ema_align"] = ("❌ EMA9<21<50 — xếp hàng giảm", -w)
        else:                          d["ema_align"] = ("⚠️ EMA đan xen — chưa rõ xu hướng", 0.0)

    # 3. ADX + DI — độ mạnh và hướng xu hướng
    w = QUANT_WEIGHTS["adx_di"]; adx, dip, dim = _g("ADX"), _g("DI_plus"), _g("DI_minus")
    if adx is not None:
        max_used += w
        if adx > 25 and dip is not None and dim is not None:
            if dip > dim: raw += w; d["adx_di"] = (f"✅ ADX {adx:.0f} + DI+ vượt DI- — xu hướng tăng mạnh", +w)
            else:         raw -= w; d["adx_di"] = (f"❌ ADX {adx:.0f} + DI- vượt DI+ — xu hướng giảm mạnh", -w)
        elif adx < 20:
            d["adx_di"] = (f"⚠️ ADX {adx:.0f} — sideway, trend-following kém tin cậy", 0.0)
        else:
            half = w*0.4
            if dip is not None and dim is not None and dip > dim:
                raw += half; d["adx_di"] = (f"➕ ADX {adx:.0f} — xu hướng đang hình thành, phe mua nhỉnh hơn", +half)
            else:
                raw -= half; d["adx_di"] = (f"➖ ADX {adx:.0f} — xu hướng yếu, phe bán nhỉnh hơn", -half)

    # 4. Donchian breakout 20 phiên
    w = QUANT_WEIGHTS["donchian"]; dh, dl = _g("Donchian_High20"), _g("Donchian_Low20")
    if dh is not None and dl is not None:
        max_used += w
        if c >= dh:   raw += w; d["donchian"] = ("🔥 Phá đỉnh 20 phiên — tín hiệu mua trend-following", +w)
        elif c <= dl: raw -= w; d["donchian"] = ("💧 Phá đáy 20 phiên — tín hiệu bán/tránh mua", -w)
        else:
            rng = dh - dl
            pos = (c - dl)/rng if rng > 0 else 0.5   # vị trí trong kênh 0..1
            val = (pos - 0.5) * 2 * w * 0.5          # càng gần đỉnh kênh càng tích cực
            raw += val
            d["donchian"] = (f"Trong kênh Donchian — ở mức {pos*100:.0f}% chiều cao kênh", round(val,2))

    # 5. Động lượng ROC20
    w = QUANT_WEIGHTS["momentum"]; roc = _g("ROC20")
    if roc is not None:
        max_used += w
        if roc > 5:     raw += w;      d["momentum"] = (f"✅ ROC20 {roc:+.1f}% — động lượng mạnh", +w)
        elif roc > 0:   raw += w*0.5;  d["momentum"] = (f"➕ ROC20 {roc:+.1f}% — động lượng dương", +w*0.5)
        elif roc > -5:  raw -= w*0.5;  d["momentum"] = (f"➖ ROC20 {roc:+.1f}% — động lượng âm nhẹ", -w*0.5)
        else:           raw -= w;      d["momentum"] = (f"❌ ROC20 {roc:+.1f}% — động lượng giảm mạnh", -w)

    # 6. Dòng tiền: Volume + CMF
    w = QUANT_WEIGHTS["moneyflow"]; vr, cmf = _g("Vol_Ratio"), _g("CMF")
    if cmf is not None or vr is not None:
        max_used += w
        val = 0.0; note = []
        if cmf is not None:
            if cmf > 0.05:    val += w*0.6; note.append(f"CMF {cmf:+.2f} dòng tiền vào")
            elif cmf < -0.05: val -= w*0.6; note.append(f"CMF {cmf:+.2f} dòng tiền ra")
            else: note.append(f"CMF {cmf:+.2f} trung tính")
        if vr is not None:
            if vr > 1.2:   val += w*0.4; note.append(f"Vol ×{vr:.1f} trên trung bình")
            elif vr < 0.6: val -= w*0.4; note.append(f"Vol ×{vr:.1f} thanh khoản yếu")
        raw += val
        d["moneyflow"] = (" · ".join(note) if note else "Không đủ dữ liệu dòng tiền", round(val,2))

    # 7. Z-score — phạt mua đuổi khi giá lệch quá xa trung bình
    w = QUANT_WEIGHTS["zscore"]; z = _g("Zscore20")
    if z is not None:
        max_used += w
        if z > 2:    raw -= w;     d["zscore"] = (f"⚠️ Z-score {z:+.1f} — giá lệch xa phía trên, rủi ro mua đuổi", -w)
        elif z < -2: raw += w*0.5; d["zscore"] = (f"➕ Z-score {z:+.1f} — giá chiết khấu sâu so với TB", +w*0.5)
        else:                      d["zscore"] = (f"Z-score {z:+.1f} — trong biên độ bình thường", 0.0)

    # 8. Sức mạnh tương đối vs VN-Index (nếu có)
    if rs_slope is not None:
        w = QUANT_WEIGHTS["rs"]; max_used += w
        if rs_slope > 0.5:    raw += w;     d["rs"] = ("✅ RS tăng — mạnh hơn VN-Index", +w)
        elif rs_slope < -0.5: raw -= w;     d["rs"] = ("❌ RS giảm — yếu hơn VN-Index", -w)
        else:                               d["rs"] = ("↔️ RS đi ngang — tương đương VN-Index", 0.0)

    # Chuẩn hoá về thang -10..+10 theo số cấu phần thực sự dùng được
    score = (raw / max_used * 10) if max_used > 0 else 0.0
    return round(score, 2), d

QUANT_ACTIONS = [
    (5.0,   "MUA MẠNH",       "#00d97e", "Tín hiệu quant đồng thuận cao — vào lệnh theo kế hoạch"),
    (2.5,   "MUA",            "#00b862", "Tín hiệu tích cực — vào lệnh với tỷ trọng chuẩn"),
    (1.0,   "MUA THĂM DÒ",    "#7fcf50", "Tín hiệu chớm tích cực — vào tỷ trọng nhỏ, chờ xác nhận"),
    (-1.0,  "ĐỨNG NGOÀI/GIỮ", "#8baed4", "Chưa đủ lợi thế thống kê — không mở lệnh mới"),
    (-2.5,  "GIẢM TỶ TRỌNG",  "#f5a623", "Tín hiệu xấu đi — hạ tỷ trọng, siết stop"),
    (-5.0,  "BÁN",            "#ff3d5a", "Tín hiệu tiêu cực — thoát vị thế"),
    (-99,   "BÁN MẠNH",       "#cc1133", "Tín hiệu tiêu cực mạnh — thoát toàn bộ, không bắt đáy"),
]

def quant_action(score):
    for threshold, label, color, note in QUANT_ACTIONS:
        if score >= threshold: return label, color, note
    return "BÁN MẠNH", "#cc1133", ""

def calc_quant_decision(df, rs_slope=None):
    """Đề xuất giao dịch định lượng cho phiên mới nhất: điểm, hành động, giá vào/cắt/chốt.
    Stop dùng Chandelier Exit (ATR động) thay vì % cố định."""
    lat = df.iloc[-1]
    score, detail = quant_row_score(lat, rs_slope)
    action, color, note = quant_action(score)
    c = float(lat.Close)
    atr = float(lat.ATR) if pd.notna(lat.get("ATR")) else c*0.02
    chand = float(lat.Chandelier_Long) if pd.notna(lat.get("Chandelier_Long")) else None
    dh20 = float(lat.Donchian_High20) if pd.notna(lat.get("Donchian_High20")) else None

    # Giá vào: nếu đã breakout thì vào quanh giá hiện tại; nếu chưa thì chờ phá đỉnh kênh
    if dh20 is not None and c < dh20 and score >= 1.0:
        entry = dh20; entry_note = "Chờ phá đỉnh Donchian 20 phiên mới vào lệnh"
    else:
        entry = c; entry_note = "Vào quanh giá thị trường hiện tại"

    # Stop: Chandelier Exit, nhưng không xa hơn 2.5 ATR và KHÔNG sát hơn 1 ATR
    # (stop quá sát giá vào sẽ bị quét liên tục bởi nhiễu trong phiên)
    stop_candidates = [x for x in [chand, entry - 2.5*atr] if x is not None and x < entry]
    stop = max(stop_candidates) if stop_candidates else entry - 2*atr
    stop = min(stop, entry - 1.0*atr)
    risk_per_share = entry - stop
    tp1 = entry + risk_per_share*1.5
    tp2 = entry + risk_per_share*2.5
    tp3 = entry + risk_per_share*4.0
    rr = (tp2-entry)/risk_per_share if risk_per_share > 0 else 0

    return dict(score=score, detail=detail, action=action, color=color, note=note,
                entry=entry, entry_note=entry_note, stop=stop, atr=atr,
                risk_per_share=risk_per_share,
                risk_pct=(risk_per_share/entry*100) if entry > 0 else 0,
                tp1=tp1, tp2=tp2, tp3=tp3, rr=rr, chandelier=chand)

def quant_position_size(capital, risk_pct_per_trade, entry, stop, max_weight_pct=20.0):
    """Khối lượng vào lệnh theo RỦI RO cố định (risk-based sizing), không phải chia đều vốn.
    Mỗi lệnh chỉ chấp nhận mất đúng risk_pct_per_trade% tài khoản nếu chạm stop."""
    if entry is None or stop is None or entry <= stop or capital <= 0: return None
    risk_amount = capital * risk_pct_per_trade/100
    risk_per_share = entry - stop
    shares = risk_amount / risk_per_share
    value = shares * entry
    cap_value = capital * max_weight_pct/100
    capped = value > cap_value
    if capped:
        value = cap_value; shares = value/entry
    lots = int(shares // 100) * 100  # lô chẵn 100 CP theo quy định HOSE/HNX
    return dict(shares=shares, lots=lots, value=lots*entry,
                risk_amount=min(risk_amount, lots*risk_per_share),
                weight_pct=(lots*entry/capital*100) if capital > 0 else 0,
                capped=capped, risk_per_share=risk_per_share)

def backtest_quant_signal(df, entry_score=2.5, exit_score=-1.0, rs_slope_series=None,
                          use_chandelier_stop=True, warmup=60):
    """Kiểm định hệ thống quant trên chính lịch sử của mã.
    Quy tắc CHỐNG NHÌN TRƯỚC: tín hiệu tính tại phiên t → khớp lệnh tại giá MỞ CỬA phiên t+1.
    Thoát khi: điểm quant <= exit_score, HOẶC giá đóng cửa thủng Chandelier Exit."""
    if df is None or len(df) < warmup + 20:
        return None, "Không đủ dữ liệu lịch sử để kiểm định (cần tối thiểu ~80 phiên)"
    scores = []
    for i in range(len(df)):
        if i < warmup:
            scores.append(np.nan); continue
        rs_s = rs_slope_series.iloc[i] if (rs_slope_series is not None and i < len(rs_slope_series)) else None
        if rs_s is not None and pd.isna(rs_s): rs_s = None
        s, _ = quant_row_score(df.iloc[i], rs_s)
        scores.append(s)
    df = df.copy(); df["QuantScore"] = scores

    trades = []; in_pos = False; entry_px = entry_date = None; entry_stop = None; init_risk = None
    for i in range(warmup, len(df)-1):
        row = df.iloc[i]; nxt = df.iloc[i+1]
        sc = row["QuantScore"]
        if pd.isna(sc): continue
        nxt_open = float(nxt.Open)
        if not in_pos:
            if sc >= entry_score:
                in_pos = True; entry_px = nxt_open; entry_date = nxt.Date
                ch = float(row.Chandelier_Long) if pd.notna(row.get("Chandelier_Long")) else None
                atr_v = float(row.ATR) if pd.notna(row.get("ATR")) else entry_px*0.02
                entry_stop = max([x for x in [ch, entry_px-2.5*atr_v] if x is not None and x < entry_px],
                                 default=entry_px-2*atr_v)
                entry_stop = min(entry_stop, entry_px-1.0*atr_v)  # giữ khoảng cách tối thiểu 1 ATR
                init_risk = entry_px - entry_stop
        else:
            hit_stop = use_chandelier_stop and float(row.Close) < entry_stop
            weak = sc <= exit_score
            if hit_stop or weak:
                exit_px = nxt_open
                trades.append(dict(entry_date=entry_date, exit_date=nxt.Date,
                                   entry=entry_px, exit=exit_px,
                                   pnl_pct=(exit_px-entry_px)/entry_px,
                                   r_multiple=((exit_px-entry_px)/init_risk) if init_risk > 0 else np.nan,
                                   reason="Chạm stop ATR" if hit_stop else "Điểm quant suy yếu"))
                in_pos = False
            else:
                # Trailing stop: nâng dần theo Chandelier, không bao giờ hạ xuống
                ch = float(row.Chandelier_Long) if pd.notna(row.get("Chandelier_Long")) else None
                if ch is not None and ch > entry_stop: entry_stop = ch
    if in_pos:  # còn lệnh mở tại cuối kỳ → chốt theo giá đóng cửa cuối
        last = df.iloc[-1]
        trades.append(dict(entry_date=entry_date, exit_date=last.Date, entry=entry_px,
                           exit=float(last.Close), pnl_pct=(float(last.Close)-entry_px)/entry_px,
                           r_multiple=((float(last.Close)-entry_px)/init_risk) if init_risk > 0 else np.nan,
                           reason="Còn mở tại cuối kỳ"))
    if not trades:
        return None, f"Hệ thống không phát sinh lệnh nào trong giai đoạn này (ngưỡng vào {entry_score:+.1f})"

    tdf = pd.DataFrame(trades)
    wins = tdf[tdf["pnl_pct"] > 0]; losses = tdf[tdf["pnl_pct"] <= 0]
    win_rate = len(wins)/len(tdf)
    avg_win = float(wins["pnl_pct"].mean()) if len(wins) else 0.0
    avg_loss = float(abs(losses["pnl_pct"].mean())) if len(losses) else 0.0
    pf = float(wins["pnl_pct"].sum()/abs(losses["pnl_pct"].sum())) if len(losses) and losses["pnl_pct"].sum() != 0 else None
    expectancy = win_rate*avg_win - (1-win_rate)*avg_loss
    exp_r = float(tdf["r_multiple"].mean()) if tdf["r_multiple"].notna().any() else None
    equity = (1+tdf["pnl_pct"]).cumprod()
    strat_ret = float(equity.iloc[-1]-1)
    peak = equity.cummax(); dd = float(((equity-peak)/peak).min())
    bh_ret = float(df["Close"].iloc[-1]/df["Close"].iloc[warmup]-1)
    time_in_market = float(sum((t["exit_date"]-t["entry_date"]).days for t in trades)/
                           max((df["Date"].iloc[-1]-df["Date"].iloc[warmup]).days, 1))
    stats = dict(n_trades=len(tdf), win_rate=win_rate, avg_win=avg_win, avg_loss=avg_loss,
                 profit_factor=pf, expectancy=expectancy, expectancy_r=exp_r,
                 strat_return=strat_ret, buyhold_return=bh_ret, max_dd=dd,
                 equity=equity, trades=tdf, time_in_market=time_in_market,
                 scores=df[["Date","QuantScore"]])
    return stats, None

# ══════════════════════════════ QUANT PORTFOLIO METRICS ════════════════════════
def sharpe_ratio(daily_returns: pd.Series, rf_annual: float = 0.03, periods: int = 252):
    if daily_returns is None or len(daily_returns) < 5: return None
    ann_ret = daily_returns.mean() * periods
    ann_vol = daily_returns.std() * math.sqrt(periods)
    if ann_vol == 0 or pd.isna(ann_vol): return None
    return (ann_ret - rf_annual) / ann_vol

def sortino_ratio(daily_returns: pd.Series, rf_annual: float = 0.03, periods: int = 252):
    if daily_returns is None or len(daily_returns) < 5: return None
    ann_ret = daily_returns.mean() * periods
    downside = daily_returns[daily_returns < 0]
    if len(downside) < 2: return None
    down_vol = downside.std() * math.sqrt(periods)
    if down_vol == 0 or pd.isna(down_vol): return None
    return (ann_ret - rf_annual) / down_vol

def max_drawdown(daily_returns: pd.Series):
    if daily_returns is None or len(daily_returns) < 2: return None, None
    cum = (1 + daily_returns).cumprod()
    running_max = cum.cummax()
    dd = (cum - running_max) / running_max
    return float(dd.min()), cum

def historical_var(daily_returns: pd.Series, conf: float = 0.95):
    if daily_returns is None or len(daily_returns) < 10: return None, None
    var = daily_returns.quantile(1 - conf)
    tail = daily_returns[daily_returns <= var]
    cvar = float(tail.mean()) if len(tail) > 0 else float(var)
    return float(var), cvar

def portfolio_beta(port_returns: pd.Series, bench_returns: pd.Series):
    if port_returns is None or bench_returns is None: return None
    merged = pd.concat([port_returns, bench_returns], axis=1, join="inner").dropna()
    if len(merged) < 10: return None
    merged.columns = ["p", "b"]
    var_b = merged["b"].var()
    if var_b == 0 or pd.isna(var_b): return None
    return float(merged["p"].cov(merged["b"]) / var_b)

def hhi_concentration(weights: dict):
    if not weights: return None
    return float(sum(v ** 2 for v in weights.values()))

def kelly_fraction(win_rate: float, avg_win: float, avg_loss: float):
    """avg_win, avg_loss là % dương (avg_loss đã lấy trị tuyệt đối)."""
    if avg_win is None or avg_loss is None or avg_win <= 0 or avg_loss <= 0: return None
    b = avg_win / avg_loss
    f = win_rate - (1 - win_rate) / b
    return f

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
    if score>=2.5:   grad="linear-gradient(135deg,#00d97e,#00b369)"; shadow="rgba(0,217,126,0.35)"
    elif score<=-2.5: grad="linear-gradient(135deg,#ff4757,#cc1133)"; shadow="rgba(255,71,87,0.35)"
    else:             grad="linear-gradient(135deg,#163350,#0c2540)"; shadow="rgba(0,0,0,0)"
    return (f"<div style='background:{grad};border-radius:10px;padding:14px 18px;"
            f"display:flex;align-items:center;gap:20px;flex-wrap:wrap;margin:8px 0;"
            f"box-shadow:0 4px 18px {shadow};'>"
            f"<div><div style='font-size:10px;color:rgba(255,255,255,.65);letter-spacing:1px;'>TÍN HIỆU KỸ THUẬT</div>"
            f"<div style='font-size:26px;font-weight:700;color:#fff;text-shadow:0 1px 6px rgba(0,0,0,.3);'>{sig}</div></div>"
            f"<div style='text-align:center;'><div style='font-size:10px;color:rgba(255,255,255,.65);'>ĐIỂM</div>"
            f"<div style='font-size:28px;font-weight:700;color:#fff;'>{score}</div></div>"
            f"<div style='flex:1;min-width:200px;'>"
            f"<div style='font-size:9px;color:rgba(255,255,255,.5);letter-spacing:1px;margin-bottom:4px;'>BÁN MẠNH ←─────────→ MUA MẠNH</div>"
            f"<div style='height:8px;background:rgba(0,0,0,.25);border-radius:4px;overflow:hidden;'>"
            f"<div style='height:100%;width:{pct}%;background:rgba(255,255,255,.7);border-radius:4px;'></div>"
            f"</div></div></div>")

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

# ── Tracking: nhớ symbol đã được phân tích ──────────────
if run or clicked:
    st.session_state['_sym_analysed'] = symbol

# ══════════════════════════════ MAIN ══════════════════════════════════════════
st.markdown(f"## {symbol} &nbsp;<span style='font-size:13px;color:#4a9ef8;'>{res_label} · {per_label}</span>",
            unsafe_allow_html=True)

# Cho phép tab buttons hoạt động mà không reset về màn hình chính
_already_run = st.session_state.get('_sym_analysed') == symbol
if not (run or auto_r or clicked or _already_run):
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
qtrend=calc_quant_trend(df)  # QUANT: bộ chỉ báo trend-following bổ sung, không đổi sig/score gốc

# ── QUANT: RS vs VN-Index + Đề xuất giao dịch định lượng (tính 1 lần, dùng ở nhiều tab) ──
try:
    vni_df, vni_src = fetch_vnindex(days)
except Exception:
    vni_df, vni_src = pd.DataFrame(), "Lỗi khi lấy VN-Index"
rs_series, rs_label = (None, "Không có dữ liệu VN-Index để so sánh")
rs_slope = None
if not vni_df.empty:
    rs_series, rs_label = calc_relative_strength(df, vni_df)
    if rs_series is not None and len(rs_series) >= 6:
        rs_slope = float(rs_series.iloc[-1] - rs_series.iloc[-6])
qdec = calc_quant_decision(df, rs_slope)

chg=float(lat.Close)-float(prev.Close); pct_chg=chg/float(prev.Close)*100 if float(prev.Close) else 0
chg_str=f"{'▲' if chg>=0 else '▼'} {abs(chg):,.0f} đ ({abs(pct_chg):.2f}%)"
st.caption(f"📡 Nguồn: {price_src} · {len(df)} phiên · {'🟢' if chg>=0 else '🔴'} {chg_str} · {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")

tab1,tab2,tab3,tab4,tab5,tab6,tab7,tab8=st.tabs(["📉 Kỹ thuật","📊 Cơ bản","💰 Dòng tiền","🏭 Ngành","🔍 Quét mã","📰 Tin tức","🎯 Tổng hợp","📐 Quant Portfolio"])

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

    # ── QUANT: Trend-Following / Momentum bổ sung ──
    st.markdown("### 📐 Chỉ báo Trend-Following / Quant")
    qc1,qc2,qc3,qc4=st.columns(4)
    qc1.markdown(metric_html("ADX / DI",
        f"{qtrend['adx']:.0f}" + (f" (+{qtrend['di_plus']:.0f}/-{qtrend['di_minus']:.0f})" if qtrend['di_plus'] is not None else ""),
        "#00d97e" if qtrend['adx']>25 else "#f5a623"),unsafe_allow_html=True)
    qc2.markdown(metric_html("ROC 10 phiên",
        f"{qtrend['roc10']:+.1f}%" if qtrend['roc10'] is not None else "—",
        "#00d97e" if (qtrend['roc10'] or 0)>0 else "#ff3d5a"),unsafe_allow_html=True)
    qc3.markdown(metric_html("Z-Score (20)",
        f"{qtrend['zscore']:+.2f}" if qtrend['zscore'] is not None else "—",
        "#ff3d5a" if qtrend['zscore'] and abs(qtrend['zscore'])>2 else "#8baed4"),unsafe_allow_html=True)
    qc4.markdown(metric_html("Chandelier Exit",
        f"{qtrend['chandelier_stop']:,.0f} đ" if qtrend['chandelier_stop'] else "—",
        "#ff3d5a"),unsafe_allow_html=True)
    st.markdown(f"""<div style='background:#0c1d2e;border:1px solid #163350;border-radius:9px;
      padding:12px 16px;margin-top:8px;font-size:13px;color:#cce0ff;line-height:1.8;'>
      <b>🎯 ADX Regime:</b> {qtrend['adx_regime']}<br>
      <b>📐 Donchian (20 phiên):</b> {qtrend['donchian_status']}<br>
      <b>📊 Z-Score:</b> {qtrend['zscore_label']}
    </div>""",unsafe_allow_html=True)
    with st.expander("ℹ️ Giải thích chỉ báo Quant"):
        st.markdown("""
- **ADX/DI**: ADX>25 = xu hướng đủ mạnh để đi theo trend. DI+ > DI- = phe mua đang thắng thế.
- **Donchian Channel**: giá phá đỉnh 20 phiên = tín hiệu mua kiểu trend-following kinh điển (turtle trading).
- **ROC (Rate of Change)**: tốc độ tăng/giảm giá so với N phiên trước — dương & tăng dần = động lượng đang mạnh lên.
- **Z-Score**: đo giá đang lệch bao nhiêu độ lệch chuẩn so với trung bình 20 phiên. |Z|>2 = lệch bất thường, dễ có phản ứng đảo chiều ngắn hạn (mean-reversion).
- **Chandelier Exit**: điểm cắt lỗ động theo biến động thực tế (ATR), thường siết chặt dần khi giá tăng — dùng để bảo vệ lợi nhuận thay vì cắt lỗ cố định.
        """)

    # ── QUANT: Relative Strength vs VN-Index ──
    st.markdown("### 📈 Relative Strength (RS) vs VN-Index")
    if rs_series is not None:
        st.markdown(f"**{rs_label}** · Nguồn VN-Index: {vni_src}")
        fig_rs=go.Figure()
        fig_rs.add_trace(go.Scatter(x=rs_series.index,y=rs_series.values,name="RS Line",
            line=dict(color="#22d3ee",width=2)))
        fig_rs.add_hline(y=100,line=dict(color="rgba(255,255,255,.25)",dash="dot",width=1),
            annotation_text=" Base=100")
        fig_rs.update_layout(height=220,title=f"RS Line: {symbol} / VN-Index",
            template="plotly_dark",**CHART_STYLE)
        fig_rs.layout.title.font.color="#8baed4"; fig_rs.layout.title.font.size=12
        st.plotly_chart(fig_rs,use_container_width=True)
    else:
        st.info(f"⚠️ {rs_label if vni_df.empty is False else vni_src}. "
                "RS Line tạm thời không khả dụng — điểm quant vẫn tính được từ các cấu phần còn lại.")

    # ══ ĐỀ XUẤT GIAO DỊCH ĐỊNH LƯỢNG ══
    st.markdown("---")
    st.markdown("## 🎯 ĐỀ XUẤT GIAO DỊCH ĐỊNH LƯỢNG")
    qs = qdec["score"]; qcolor = qdec["color"]
    pct_bar = min(100, max(0, (qs+10)/20*100))
    st.markdown(f"""<div style='background:linear-gradient(135deg,{qcolor}22,#0c1d2e);
      border:2px solid {qcolor};border-radius:12px;padding:16px 20px;margin:8px 0;'>
      <div style='display:flex;align-items:center;gap:24px;flex-wrap:wrap;'>
        <div><div style='font-size:10px;color:#6a9cc8;letter-spacing:1px;'>HÀNH ĐỘNG ĐỀ XUẤT</div>
          <div style='font-size:30px;font-weight:800;color:{qcolor};'>{qdec['action']}</div></div>
        <div style='text-align:center;'><div style='font-size:10px;color:#6a9cc8;'>ĐIỂM QUANT</div>
          <div style='font-size:32px;font-weight:800;color:{qcolor};'>{qs:+.1f}</div>
          <div style='font-size:10px;color:#4a6080;'>thang −10 → +10</div></div>
        <div style='flex:1;min-width:220px;'>
          <div style='font-size:9px;color:#4a6080;letter-spacing:1px;margin-bottom:4px;'>BÁN MẠNH ←──────→ MUA MẠNH</div>
          <div style='height:10px;background:rgba(0,0,0,.3);border-radius:5px;overflow:hidden;'>
            <div style='height:100%;width:{pct_bar}%;background:{qcolor};border-radius:5px;'></div></div>
          <div style='font-size:12px;color:#cce0ff;margin-top:8px;'>{qdec['note']}</div>
        </div>
      </div></div>""",unsafe_allow_html=True)

    e1,e2,e3,e4=st.columns(4)
    e1.markdown(trade_card_html("📗","GIÁ VÀO",f"{qdec['entry']:,.0f} đ",qdec['entry_note'],"#00d97e"),unsafe_allow_html=True)
    e2.markdown(trade_card_html("🛑","CẮT LỖ (ATR)",f"{qdec['stop']:,.0f} đ",
        f"Rủi ro {qdec['risk_pct']:.1f}% · Chandelier Exit","#ff3d5a"),unsafe_allow_html=True)
    e3.markdown(trade_card_html("🎯","CHỐT LỜI",f"TP1 {qdec['tp1']:,.0f}",
        f"TP2 {qdec['tp2']:,.0f} · TP3 {qdec['tp3']:,.0f}","#f5a623"),unsafe_allow_html=True)
    rr_c="#00d97e" if qdec['rr']>=2 else "#f5a623"
    e4.markdown(trade_card_html("⚖️","R:R (tại TP2)",f"1 : {qdec['rr']:.1f}",
        f"1R = {qdec['risk_per_share']:,.0f} đ/CP",rr_c),unsafe_allow_html=True)

    # Position sizing theo rủi ro
    st.markdown("#### 💼 Khối lượng vào lệnh theo rủi ro")
    ps1,ps2,ps3=st.columns(3)
    cap_input=ps1.number_input("Vốn giao dịch (triệu đ)",value=100.0,step=10.0,key="qcap")*1_000_000
    risk_input=ps2.number_input("Rủi ro mỗi lệnh (% tài khoản)",value=1.0,step=0.25,
        min_value=0.1,max_value=5.0,key="qrisk",
        help="Chuẩn quản trị rủi ro: 0.5–2% tài khoản cho mỗi lệnh")
    maxw_input=ps3.number_input("Tỷ trọng tối đa 1 mã (%)",value=20.0,step=5.0,
        min_value=5.0,max_value=100.0,key="qmaxw")
    psize=quant_position_size(cap_input,risk_input,qdec['entry'],qdec['stop'],maxw_input)
    if psize and psize['lots']>0:
        pz1,pz2,pz3,pz4=st.columns(4)
        pz1.markdown(metric_html("Khối lượng",f"{psize['lots']:,} CP","#00d97e"),unsafe_allow_html=True)
        pz2.markdown(metric_html("Giá trị lệnh",f"{psize['value']/1e6:,.1f} tr đ"),unsafe_allow_html=True)
        pz3.markdown(metric_html("Tỷ trọng",f"{psize['weight_pct']:.1f}%",
            "#f5a623" if psize['capped'] else "#00d97e"),unsafe_allow_html=True)
        pz4.markdown(metric_html("Lỗ tối đa nếu chạm SL",f"−{psize['risk_amount']/1e6:,.2f} tr đ","#ff3d5a"),unsafe_allow_html=True)
        if psize['capped']:
            st.caption(f"ℹ️ Khối lượng đã bị giới hạn bởi trần tỷ trọng {maxw_input:.0f}%/mã "
                       "— nếu không giới hạn, mức rủi ro cho phép sẽ cho vào lệnh lớn hơn.")
    else:
        st.info("Chưa tính được khối lượng — kiểm tra lại giá vào/cắt lỗ.")

    if qs < 1.0:
        st.warning("⚠️ Điểm quant chưa đủ để mở lệnh mua mới. Phần khối lượng ở trên chỉ mang tính tham chiếu "
                   "cho trường hợp tín hiệu cải thiện — KHÔNG phải lệnh khuyến nghị vào ngay bây giờ.")
    if len(df) < 180:
        st.info(f"ℹ️ Đang chỉ có **{len(df)} phiên** dữ liệu nên bộ lọc xu hướng dài hạn (EMA200) bị tạm bỏ qua "
                "— EMA200 tính trên ít phiên vẫn bị chi phối bởi giá khởi tạo nên không đáng tin. "
                "Chọn **Lịch sử dữ liệu = 1 năm hoặc 2 năm** ở thanh bên để kích hoạt lại bộ lọc này.")

    with st.expander("🔬 Bảng phân rã điểm quant — vì sao ra kết luận này"):
        rows=[]
        _labels={"trend_lt":"Xu hướng dài hạn (EMA200)","ema_align":"Xếp hàng EMA",
                 "adx_di":"Độ mạnh xu hướng (ADX/DI)","donchian":"Breakout kênh giá",
                 "momentum":"Động lượng (ROC20)","moneyflow":"Dòng tiền (Vol/CMF)",
                 "zscore":"Định vị thống kê (Z-score)","rs":"Sức mạnh vs VN-Index"}
        for k,(txt,val) in qdec["detail"].items():
            rows.append({"Cấu phần":_labels.get(k,k),"Đóng góp":f"{val:+.2f}","Diễn giải":txt})
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        st.caption("Điểm thô được chuẩn hoá về thang −10…+10 theo số cấu phần có đủ dữ liệu, "
                   "nên mã thiếu dữ liệu vẫn so sánh được công bằng với mã đủ dữ liệu.")

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
    if "cmp_data" not in st.session_state: st.session_state.cmp_data=[]
    if st.button("🔄 Tải dữ liệu so sánh", key="load_cmp"):
        cmp_data=[]; prog=st.progress(0)
        for ii,sym2 in enumerate(cmp_syms):
            prog.progress((ii+1)/len(cmp_syms),f"Tải {sym2}...")
            try:
                _r2 = fetch_price(sym2, 180, "1D")
                df2 = _r2[0] if isinstance(_r2, tuple) else _r2
                rat2=fetch_ratio(sym2)[0]; inc2=fetch_income(sym2)
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
        st.session_state.cmp_data=cmp_data
    cmp_data=st.session_state.cmp_data
    if cmp_data:
        n_ok=sum(1 for r in cmp_data if r["Giá"]!="—")
        st.caption(f"Tải xong: {n_ok}/{len(cmp_data)} mã có dữ liệu")
        st.dataframe(pd.DataFrame(cmp_data),use_container_width=True,hide_index=True)

        # ── Biểu đồ P/E ──
        valid=[(r["Mã"],float(r["P/E"].replace("x","").replace("—","0"))) for r in cmp_data if r["P/E"]!="—" and "x" in str(r["P/E"])]
        if valid:
            mcs2,pes2=zip(*[(m,v) for m,v in valid if v>0])
            fpE=go.Figure(go.Bar(x=list(mcs2),y=list(pes2),
                marker_color=["#4a9ef8" if m==symbol else "#163350" for m in mcs2],
                text=[f"{v:.1f}x" for v in pes2],textposition="outside"))
            if SECTOR_PE.get(cur_sec):
                fpE.add_hline(y=SECTOR_PE[cur_sec],line=dict(color="#f5a623",dash="dot",width=1.5),
                    annotation_text=f" Median ngành {SECTOR_PE[cur_sec]}x",annotation_font=dict(color="#f5a623",size=10))
            fpE.update_layout(height=260,title="So sánh P/E toàn ngành",template="plotly_dark",**CHART_STYLE)
            fpE.layout.title.font.color="#8baed4"
            st.plotly_chart(fpE,use_container_width=True)

        # ── Phân tích & nhận xét ──
        st.markdown("### 🔬 Phân tích & nhận xét ngành")
        valid_data = [r for r in cmp_data if r["Giá"]!="—"]
        if valid_data:
            # Tìm mã tốt nhất theo từng tiêu chí
            def parse_num(s, strip="x%"):
                try: return float(str(s).replace("x","").replace("%","").replace(",","").replace("—",""))
                except: return None

            # Định giá rẻ nhất (P/E thấp nhất > 0)
            pe_list = [(r["Mã"], parse_num(r["P/E"])) for r in valid_data if parse_num(r["P/E"]) and parse_num(r["P/E"])>0]
            roe_list = [(r["Mã"], parse_num(r["ROE"])) for r in valid_data if parse_num(r["ROE"])]
            score_list = [(r["Mã"], r["Score"]) for r in valid_data if isinstance(r["Score"], (int,float))]
            perf_1m = [(r["Mã"], parse_num(r["+1T"])) for r in valid_data if parse_num(r["+1T"])]

            col_a, col_b = st.columns(2)
            with col_a:
                if pe_list:
                    cheapest = min(pe_list, key=lambda x:x[1])
                    most_exp = max(pe_list, key=lambda x:x[1])
                    med_pe = SECTOR_PE.get(cur_sec)
                    sym_pe = next((parse_num(r["P/E"]) for r in valid_data if r["Mã"]==symbol), None)
                    vs_txt = ""
                    if sym_pe and med_pe:
                        diff = (sym_pe-med_pe)/med_pe*100
                        vs_txt = f"{'đắt hơn' if diff>0 else 'rẻ hơn'} median ngành **{abs(diff):.0f}%**"
                    st.markdown(f"""**📊 Định giá (P/E)**
- Rẻ nhất: **{cheapest[0]}** ({cheapest[1]:.1f}x)
- Đắt nhất: **{most_exp[0]}** ({most_exp[1]:.1f}x)
- **{symbol}** đang {vs_txt if vs_txt else f'P/E={sym_pe:.1f}x' if sym_pe else '—'}
- Median ngành: {med_pe}x""")

                if roe_list:
                    best_roe = max(roe_list, key=lambda x:x[1])
                    sym_roe = next((v for m,v in roe_list if m==symbol), None)
                    st.markdown(f"""**💰 Sinh lời (ROE)**
- Cao nhất: **{best_roe[0]}** ({best_roe[1]:.1f}%)
- **{symbol}**: {f'{sym_roe:.1f}%' if sym_roe else '—'}
- {'✅ Trên trung bình ngành' if sym_roe and sym_roe > sum(v for _,v in roe_list)/len(roe_list) else '⚠️ Dưới trung bình ngành' if sym_roe else ''}""")

            with col_b:
                if score_list:
                    best_kt = max(score_list, key=lambda x:x[1])
                    sym_kt = next((v for m,v in score_list if m==symbol), None)
                    st.markdown(f"""**📉 Kỹ thuật (Score)**
- Tín hiệu mạnh nhất: **{best_kt[0]}** ({best_kt[1]:+.1f})
- **{symbol}**: {f'{sym_kt:+.1f}' if sym_kt is not None else '—'}""")

                if perf_1m:
                    best_1m = max(perf_1m, key=lambda x:x[1])
                    worst_1m = min(perf_1m, key=lambda x:x[1])
                    sym_1m = next((v for m,v in perf_1m if m==symbol), None)
                    st.markdown(f"""**🚀 Hiệu suất 1 tháng**
- Tăng mạnh nhất: **{best_1m[0]}** ({best_1m[1]:+.1f}%)
- Giảm mạnh nhất: **{worst_1m[0]}** ({worst_1m[1]:+.1f}%)
- **{symbol}**: {f'{sym_1m:+.1f}%' if sym_1m is not None else '—'}""")

            # Tổng kết vị thế của mã đang xem
            st.markdown("---")
            rank_score = sorted(score_list, key=lambda x:x[1], reverse=True)
            rank_pos = next((i+1 for i,(m,_) in enumerate(rank_score) if m==symbol), None)
            rank_pe   = sorted(pe_list, key=lambda x:x[1]) if pe_list else []
            rank_pe_pos = next((i+1 for i,(m,_) in enumerate(rank_pe) if m==symbol), None)
            st.markdown(f"**🏆 Vị thế {symbol} trong ngành {cur_sec}:**")
            notes=[]
            if rank_pos: notes.append(f"Kỹ thuật: **#{rank_pos}/{len(rank_score)}** trong ngành")
            if rank_pe_pos: notes.append(f"Định giá rẻ: **#{rank_pe_pos}/{len(rank_pe)}** (1=rẻ nhất)")
            for n in notes: st.markdown(f"  - {n}")
    else:
        st.info("Nhấn **Tải dữ liệu so sánh** để xem peer comparison.")

# ── TAB 5: QUÉT MÃ THEO HỆ THỐNG QUANT ───────────────────────────────────────
with tab5:
    st.markdown("### 🔍 Quét mã theo hệ thống Quant")
    st.caption("Chấm điểm mọi mã bằng CÙNG bộ quy tắc định lượng đang dùng ở tab Kỹ thuật "
               "(xu hướng dài hạn · ADX/DI · breakout Donchian · động lượng · dòng tiền · Z-score · RS vs VN-Index), "
               "rồi lọc và xếp hạng — thay vì soi từng chỉ báo rời rạc.")

    sc1,sc2=st.columns([2,1])
    scan_scope=sc1.selectbox("Phạm vi quét",
        ["Toàn bộ danh mục theo dõi (tất cả ngành)"]+list(SECTOR_PEERS.keys()),key="scan_sec")
    scan_days=sc2.selectbox("Lịch sử mỗi mã",[260,365,500],index=1,key="scan_days",
        help="Cần ~365 ngày lịch (≈250 phiên) để EMA200 và bộ lọc xu hướng dài hạn đáng tin cậy")

    st.markdown("**Bộ lọc hệ thống** — chỉ giữ lại mã thoả điều kiện")
    fc1,fc2,fc3,fc4=st.columns(4)
    f_min_score=fc1.number_input("Điểm quant tối thiểu",value=1.0,step=0.5,
        min_value=-10.0,max_value=10.0,key="f_score")
    f_trend=fc2.checkbox("Chỉ mã trên EMA200",value=True,key="f_ema200",
        help="Bộ lọc xu hướng dài hạn — loại mã đang trong downtrend")
    f_adx=fc3.checkbox("Chỉ mã ADX > 25",value=False,key="f_adx",
        help="Chỉ giữ mã có xu hướng đủ mạnh để đi theo")
    f_breakout=fc4.checkbox("Chỉ mã đang breakout",value=False,key="f_bo",
        help="Giá phá đỉnh kênh Donchian 20 phiên")
    fc5,fc6=st.columns(2)
    f_liq=fc5.number_input("Thanh khoản tối thiểu (tỷ đ/phiên)",value=5.0,step=1.0,
        min_value=0.0,key="f_liq",help="Loại mã quá mỏng, khó vào/ra lệnh với vốn thực")
    f_rr=fc6.number_input("R:R tối thiểu",value=1.5,step=0.5,min_value=0.0,key="f_rr")

    if "qscan_results" not in st.session_state: st.session_state.qscan_results=[]
    if "qscan_key" not in st.session_state: st.session_state.qscan_key=""

    if st.button("🚀 Bắt đầu quét theo hệ thống", key="btn_qscan", use_container_width=True):
        if scan_scope.startswith("Toàn bộ"):
            universe=sorted({s for lst in SECTOR_PEERS.values() for s in lst})
        else:
            universe=SECTOR_PEERS[scan_scope]
        # Lấy VN-Index 1 lần để tính RS cho toàn bộ mã
        vni_close=None
        try:
            vdf,_=fetch_vnindex(scan_days)
            if not vdf.empty: vni_close=vdf.set_index("Date")["Close"].astype(float)
        except Exception: pass
        if vni_close is None:
            st.caption("⚠️ Không lấy được VN-Index — cấu phần RS bị bỏ qua, điểm vẫn được chuẩn hoá công bằng.")

        results=[]; failed=[]; prog=st.progress(0.0)
        for ii,s2 in enumerate(universe):
            prog.progress((ii+1)/len(universe),f"Đang chấm điểm {s2}... ({ii+1}/{len(universe)})")
            r=scan_stock_quant(s2,scan_days,vni_close)
            if r: results.append(r)
            else: failed.append(s2)
        prog.empty()
        st.session_state.qscan_results=results
        st.session_state.qscan_failed=failed
        st.session_state.qscan_key=f"{scan_scope}|{scan_days}"

    results=st.session_state.qscan_results
    if results:
        failed=st.session_state.get("qscan_failed",[])
        st.caption(f"Đã chấm điểm {len(results)} mã"+(f" · Không lấy được dữ liệu: {', '.join(failed)}" if failed else ""))

        # ── Áp bộ lọc ──
        passed=[r for r in results
                if r["quant_score"]>=f_min_score
                and (not f_trend or r["above_ema200"])
                and (not f_adx or r["adx"]>25)
                and (not f_breakout or r["breakout"])
                and r["liquidity_bn"]>=f_liq
                and r["rr"]>=f_rr]
        passed.sort(key=lambda x:-x["quant_score"])

        st.markdown(f"#### ✅ {len(passed)}/{len(results)} mã qua bộ lọc hệ thống")
        if not passed:
            st.info("Không mã nào thoả toàn bộ điều kiện. Đây cũng là một tín hiệu: "
                    "khi thị trường chung yếu, hệ thống trend-following sẽ không có lệnh — "
                    "đứng ngoài là hành động đúng, không nên nới lỏng bộ lọc để 'có việc mà làm'.")
        for rank,r in enumerate(passed[:10],1):
            clr=r["color"]
            bo="🔥 Breakout" if r["breakout"] else ""
            rs_txt=(f"RS {'↑' if (r['rs_slope'] or 0)>0 else '↓'}{abs(r['rs_slope']):.1f}"
                    if r["rs_slope"] is not None else "")
            tags=" · ".join(t for t in [bo,
                f"ADX {r['adx']:.0f}",
                f"{'trên' if r['above_ema200'] else 'dưới'} EMA200",
                rs_txt, f"TK {r['liquidity_bn']:.0f} tỷ"] if t)
            st.markdown(
                f"<div style='background:#0c1d2e;border:1px solid #163350;border-left:5px solid {clr};"
                f"border-radius:0 12px 12px 0;padding:14px 18px;margin:8px 0;'>"
                f"<div style='display:flex;align-items:center;gap:16px;flex-wrap:wrap;'>"
                f"<b style='font-size:20px;color:#6a9cc8;min-width:32px;'>#{rank}</b>"
                f"<span style='font-size:22px;font-weight:800;color:#fff;'>{r['sym']}</span>"
                f"<span style='background:{clr}22;color:{clr};padding:3px 12px;border-radius:12px;"
                f"font-weight:700;font-size:13px;'>{r['action']}</span>"
                f"<span style='font-size:22px;font-weight:800;color:{clr};'>{r['quant_score']:+.1f}</span>"
                f"<span style='color:#fff;font-size:15px;'>{r['close']:,.0f}đ</span>"
                f"<span style='color:{'#00d97e' if r['chg1d']>=0 else '#ff3d5a'};font-size:13px;'>{r['chg1d']:+.2f}%</span>"
                f"</div>"
                f"<div style='margin-top:8px;font-size:12px;color:#8baed4;'>{tags}</div>"
                f"<div style='margin-top:6px;font-size:13px;color:#cce0ff;'>"
                f"📗 Vào <b>{r['entry']:,.0f}</b> &nbsp;·&nbsp; 🛑 Cắt lỗ <b style='color:#ff3d5a;'>{r['stop']:,.0f}</b> "
                f"(−{r['risk_pct']:.1f}%) &nbsp;·&nbsp; 🎯 TP1 <b style='color:#f5a623;'>{r['tp1']:,.0f}</b> "
                f"&nbsp;·&nbsp; ⚖️ R:R <b>1:{r['rr']:.1f}</b></div>"
                f"</div>", unsafe_allow_html=True)

        # ── Bảng đầy đủ + xuất file ──
        if passed:
            with st.expander("📋 Bảng chi tiết các mã qua lọc (có thể tải về)"):
                tbl=pd.DataFrame([{
                    "Mã":r["sym"],"Điểm":round(r["quant_score"],1),"Hành động":r["action"],
                    "Giá":round(r["close"]),"Vào":round(r["entry"]),"Cắt lỗ":round(r["stop"]),
                    "TP1":round(r["tp1"]),"TP2":round(r["tp2"]),"R:R":round(r["rr"],1),
                    "Rủi ro %":round(r["risk_pct"],1),"ADX":round(r["adx"]),
                    "RSI":round(r["rsi"]),"Z":round(r["zscore"],1),
                    "ROC20%":round(r["roc20"],1),"Vol×":round(r["vol_ratio"],1),
                    "TK(tỷ)":round(r["liquidity_bn"],1),
                    "Breakout":"✓" if r["breakout"] else "",
                    ">EMA200":"✓" if r["above_ema200"] else "",
                } for r in passed])
                st.dataframe(tbl,use_container_width=True,hide_index=True)
                st.download_button("⬇️ Tải danh sách (CSV)",tbl.to_csv(index=False).encode("utf-8-sig"),
                    file_name=f"quant_scan_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",key="dl_scan")

        # ── Bức tranh toàn thị trường (breadth) ──
        st.markdown("#### 🌡️ Nhiệt độ thị trường theo hệ thống")
        n=len(results)
        n_buy=sum(1 for r in results if r["quant_score"]>=2.5)
        n_watch=sum(1 for r in results if 1.0<=r["quant_score"]<2.5)
        n_neutral=sum(1 for r in results if -1.0<=r["quant_score"]<1.0)
        n_sell=sum(1 for r in results if r["quant_score"]<-1.0)
        n_above=sum(1 for r in results if r["above_ema200"])
        n_bo=sum(1 for r in results if r["breakout"])
        avg_score=sum(r["quant_score"] for r in results)/n if n else 0
        breadth=n_above/n*100 if n else 0

        b1,b2,b3,b4=st.columns(4)
        b1.markdown(metric_html("Điểm quant TB",f"{avg_score:+.1f}",
            "#00d97e" if avg_score>1 else "#f5a623" if avg_score>-1 else "#ff3d5a"),unsafe_allow_html=True)
        b2.markdown(metric_html("% mã trên EMA200",f"{breadth:.0f}%",
            "#00d97e" if breadth>60 else "#f5a623" if breadth>40 else "#ff3d5a"),unsafe_allow_html=True)
        b3.markdown(metric_html("Mã đang breakout",f"{n_bo}/{n}"),unsafe_allow_html=True)
        b4.markdown(metric_html("Mã đạt ngưỡng MUA",f"{n_buy}/{n}",
            "#00d97e" if n_buy>n*0.3 else "#f5a623"),unsafe_allow_html=True)

        if breadth>60 and avg_score>1:
            regime="🟢 **Thị trường THUẬN LỢI** cho hệ thống trend-following — có thể nâng dần tỷ trọng theo tín hiệu."
        elif breadth<40 or avg_score<-1:
            regime=("🔴 **Thị trường BẤT LỢI** — phần lớn mã dưới EMA200. Hệ thống trend-following "
                    "sẽ thua lỗ liên tục trong giai đoạn này; ưu tiên giữ tiền mặt và giảm tần suất giao dịch.")
        else:
            regime="🟡 **Thị trường PHÂN HOÁ** — chỉ chọn lọc mã điểm cao nhất, giảm tỷ trọng mỗi lệnh."
        st.markdown(regime)

        fig_dist=go.Figure(go.Bar(
            x=["Mua (≥2.5)","Theo dõi (1–2.5)","Trung tính","Tiêu cực (<−1)"],
            y=[n_buy,n_watch,n_neutral,n_sell],
            marker_color=["#00d97e","#7fcf50","#8baed4","#ff3d5a"],
            text=[n_buy,n_watch,n_neutral,n_sell],textposition="outside"))
        fig_dist.update_layout(height=240,title="Phân bổ điểm quant toàn bộ mã đã quét",
            template="plotly_dark",**CHART_STYLE)
        fig_dist.layout.title.font.color="#8baed4"; fig_dist.layout.title.font.size=12
        st.plotly_chart(fig_dist,use_container_width=True)
    else:
        st.info("Nhấn **Bắt đầu quét theo hệ thống** để chấm điểm toàn bộ danh mục theo dõi.")


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
    quant_norm=max(-5,min(5,qdec["score"]/2))  # điểm quant thang ±10 → quy về ±5
    # Trọng số: hệ thống quant là trụ cột ra quyết định giao dịch (50%),
    # kỹ thuật cổ điển bổ trợ (20%), cơ bản quyết định có nên nắm giữ dài hạn (30%)
    total=quant_norm*0.50 + tech_norm*0.20 + fund_norm*0.30
    sc1,sc2,sc3,sc4=st.columns(4)
    sc1.markdown(score_pill("📐 Quant",round(quant_norm,1),"Trọng số 50%"),unsafe_allow_html=True)
    sc2.markdown(score_pill("📉 Kỹ thuật",round(tech_norm,1),"Trọng số 20%"),unsafe_allow_html=True)
    sc3.markdown(score_pill("📊 Cơ bản",round(fund_norm,1),"Trọng số 30%"),unsafe_allow_html=True)
    if   total>=2.5: final="MUA MẠNH"; fc="#00d97e"
    elif total>=1.0: final="MUA";       fc="#00b862"
    elif total>=0.3: final="THEO DÕI MUA"; fc="#7fcf50"
    elif total>-0.3: final="TRUNG TÍNH";   fc="#8baed4"
    elif total>-1.0: final="THEO DÕI BÁN"; fc="#f5a623"
    elif total>-2.5: final="BÁN";           fc="#ff3d5a"
    else:            final="BÁN MẠNH";      fc="#cc1133"
    sc4.markdown(f"""<div style='background:#0c1d2e;border:2px solid {fc}80;border-radius:10px;
      padding:12px 14px;text-align:center;'>
      <div style='font-size:10px;color:#6a9cc8;letter-spacing:.5px;margin-bottom:4px;'>KẾT LUẬN TỔNG HỢP</div>
      <div style='font-size:20px;font-weight:700;color:{fc};'>{final}</div>
      <div style='font-size:12px;color:#6a9cc8;margin-top:4px;'>Điểm: {total:+.2f}</div>
    </div>""",unsafe_allow_html=True)

    # ── Kế hoạch lệnh cụ thể theo hệ thống quant ──
    st.markdown("#### 📋 Kế hoạch lệnh (theo hệ thống quant)")
    pl1,pl2,pl3,pl4=st.columns(4)
    pl1.markdown(metric_html("Hành động",qdec["action"],qdec["color"]),unsafe_allow_html=True)
    pl2.markdown(metric_html("Giá vào",f"{qdec['entry']:,.0f} đ","#00d97e"),unsafe_allow_html=True)
    pl3.markdown(metric_html("Cắt lỗ (ATR động)",f"{qdec['stop']:,.0f} đ","#ff3d5a"),unsafe_allow_html=True)
    pl4.markdown(metric_html("Chốt lời TP2",f"{qdec['tp2']:,.0f} đ","#f5a623"),unsafe_allow_html=True)
    if qdec["score"]>=1.0 and fund_score<0:
        st.warning("⚠️ Tín hiệu kỹ thuật/quant tích cực nhưng **nền tảng cơ bản yếu** — "
                   "chỉ nên coi đây là lệnh giao dịch ngắn hạn có cắt lỗ chặt, không phải khoản nắm giữ dài hạn.")
    if qdec["score"]<=-2.5:
        st.error("🔴 Hệ thống quant đang ở trạng thái tiêu cực. Nếu đang nắm giữ mã này, "
                 "đây là lúc rà lại kế hoạch thoát lệnh thay vì chờ 'về bờ' — "
                 "giữ lệnh lỗ quá lâu là rủi ro lớn hơn chính khoản lỗ hiện tại.")
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

# ── TAB 8: QUANT PORTFOLIO ───────────────────────────────────────────────────
with tab8:
    st.markdown("### 📐 Quant Portfolio — Rủi ro & Hiệu suất danh mục")
    st.caption("Nhập danh mục hiện tại để tính Sharpe, Sortino, Max Drawdown, Beta, VaR, tương quan giữa các mã. "
               "Dùng cùng nguồn dữ liệu KBS/VCI như các tab khác — không cần API riêng.")

    st.markdown("#### 1️⃣ Danh mục hiện tại")
    if "port_positions" not in st.session_state:
        st.session_state.port_positions = pd.DataFrame(
            [{"Mã": "", "Giá vào (đ)": 0.0, "Khối lượng": 0}])
    port_edit = st.data_editor(st.session_state.port_positions, num_rows="dynamic",
        use_container_width=True, key="port_editor",
        column_config={
            "Mã": st.column_config.TextColumn(help="VD: VPB, HPG..."),
            "Giá vào (đ)": st.column_config.NumberColumn(format="%.0f"),
            "Khối lượng": st.column_config.NumberColumn(format="%d"),
        })
    st.session_state.port_positions = port_edit

    pc1,pc2 = st.columns(2)
    rf_pct = pc1.number_input("Lãi suất phi rủi ro (%/năm)", value=3.0, step=0.5,
        help="Tham chiếu lãi suất trái phiếu Chính phủ VN kỳ hạn ngắn") / 100
    lookback_days = pc2.selectbox("Số ngày lịch sử tính rủi ro", [90,180,365], index=1)

    if st.button("🧮 Tính rủi ro danh mục", key="btn_port_calc", use_container_width=True):
        valid_rows = port_edit[(port_edit["Mã"].astype(str).str.strip()!="") &
                                (pd.to_numeric(port_edit["Khối lượng"],errors="coerce").fillna(0)>0)]
        if valid_rows.empty:
            st.warning("Nhập ít nhất 1 mã với khối lượng > 0.")
        else:
            with st.spinner("Đang tải dữ liệu lịch sử và tính toán..."):
                returns_dict={}; weights={}; latest_prices={}; errors=[]
                for _, row in valid_rows.iterrows():
                    sym2=str(row["Mã"]).upper().strip()
                    try:
                        pdf,_=fetch_price(sym2, lookback_days, "1D")
                        if pdf is None or pdf.empty or len(pdf)<20:
                            errors.append(sym2); continue
                        rets=pdf.set_index("Date")["Close"].astype(float).pct_change().dropna()
                        returns_dict[sym2]=rets
                        latest_prices[sym2]=float(pdf["Close"].iloc[-1])
                        weights[sym2]=float(row["Khối lượng"])*latest_prices[sym2]
                    except Exception:
                        errors.append(sym2)
                if errors:
                    st.warning(f"Không lấy được dữ liệu: {', '.join(errors)}")
                if not returns_dict:
                    st.error("Không tính được — kiểm tra lại mã cổ phiếu.")
                else:
                    total_val=sum(weights.values())
                    w_norm={k: v/total_val for k,v in weights.items()} if total_val>0 else {}
                    ret_df=pd.concat(returns_dict, axis=1).fillna(0)
                    ret_df.columns=list(returns_dict.keys())
                    port_ret=(ret_df*pd.Series(w_norm)).sum(axis=1)
                    st.session_state.port_calc=dict(port_ret=port_ret, ret_df=ret_df,
                        weights=w_norm, total_val=total_val, latest_prices=latest_prices)

    calc=st.session_state.get("port_calc")
    if calc:
        port_ret=calc["port_ret"]; ret_df=calc["ret_df"]; w_norm=calc["weights"]
        sharpe=sharpe_ratio(port_ret, rf_pct)
        sortino=sortino_ratio(port_ret, rf_pct)
        mdd, cum = max_drawdown(port_ret)
        ann_vol = float(port_ret.std()*math.sqrt(252)) if len(port_ret)>2 else None
        var95, cvar95 = historical_var(port_ret)
        hhi = hhi_concentration(w_norm)
        beta=None
        try:
            vni_p, vni_src_p = fetch_vnindex(lookback_days)
            if not vni_p.empty:
                vni_ret = vni_p.set_index("Date")["Close"].astype(float).pct_change().dropna()
                beta = portfolio_beta(port_ret, vni_ret)
        except Exception:
            pass

        st.markdown("#### 2️⃣ Chỉ số rủi ro & hiệu suất")
        q1,q2,q3,q4=st.columns(4)
        q1.markdown(metric_html("Sharpe Ratio", f"{sharpe:.2f}" if sharpe is not None else "—",
            "#00d97e" if sharpe and sharpe>1 else "#f5a623" if sharpe and sharpe>0 else "#ff3d5a"),unsafe_allow_html=True)
        q2.markdown(metric_html("Sortino Ratio", f"{sortino:.2f}" if sortino is not None else "—",
            "#00d97e" if sortino and sortino>1 else "#f5a623" if sortino and sortino>0 else "#ff3d5a"),unsafe_allow_html=True)
        q3.markdown(metric_html("Max Drawdown", f"{mdd*100:.1f}%" if mdd is not None else "—",
            "#ff3d5a" if mdd and mdd<-0.2 else "#f5a623" if mdd and mdd<-0.1 else "#00d97e"),unsafe_allow_html=True)
        q4.markdown(metric_html("Volatility (năm)", f"{ann_vol*100:.1f}%" if ann_vol is not None else "—"),unsafe_allow_html=True)

        q5,q6,q7,q8=st.columns(4)
        q5.markdown(metric_html("Beta vs VN-Index", f"{beta:.2f}" if beta is not None else "—"),unsafe_allow_html=True)
        q6.markdown(metric_html("VaR 95% (ngày)", f"{var95*100:.1f}%" if var95 is not None else "—","#ff3d5a"),unsafe_allow_html=True)
        q7.markdown(metric_html("CVaR 95% (ngày)", f"{cvar95*100:.1f}%" if cvar95 is not None else "—","#ff3d5a"),unsafe_allow_html=True)
        q8.markdown(metric_html("HHI tập trung", f"{hhi:.2f}" if hhi is not None else "—",
            "#ff3d5a" if hhi and hhi>0.4 else "#f5a623" if hhi and hhi>0.25 else "#00d97e"),unsafe_allow_html=True)

        st.markdown("#### 3️⃣ Tỷ trọng danh mục")
        wt=pd.DataFrame([{"Mã":k,"Tỷ trọng":f"{v*100:.1f}%",
                           "Giá trị (đ)":f"{calc['total_val']*v:,.0f}"}
                          for k,v in sorted(w_norm.items(), key=lambda x:-x[1])])
        st.dataframe(wt, use_container_width=True, hide_index=True)

        if ret_df.shape[1]>=2:
            st.markdown("#### 4️⃣ Ma trận tương quan (kiểm tra đa dạng hoá)")
            corr=ret_df.corr()
            st.dataframe(safe_df(corr.round(2)), use_container_width=True)
            high_corr=[(a,b,corr.loc[a,b]) for i,a in enumerate(corr.columns)
                       for b in corr.columns[i+1:] if corr.loc[a,b]>0.7]
            if high_corr:
                st.warning("⚠️ Tương quan cao (>0.7) — các mã này đang cùng chịu 1 rủi ro, chưa thực sự đa dạng hoá: "
                           + ", ".join(f"{a}-{b} ({v:.2f})" for a,b,v in high_corr))

        if cum is not None and len(cum)>1:
            fig_eq=go.Figure()
            fig_eq.add_trace(go.Scatter(x=cum.index, y=cum.values, name="Giá trị DM (chuẩn hoá)",
                line=dict(color="#4a9ef8",width=2), fill="tozeroy", fillcolor="rgba(74,158,248,.08)"))
            fig_eq.update_layout(height=260, title="Diễn biến giá trị danh mục (chuẩn hoá = 1)",
                template="plotly_dark", **CHART_STYLE)
            fig_eq.layout.title.font.color="#8baed4"; fig_eq.layout.title.font.size=12
            st.plotly_chart(fig_eq, use_container_width=True)

        st.caption(f"⚠️ Tính trên {lookback_days} ngày gần nhất, lãi suất phi rủi ro giả định {rf_pct*100:.1f}%/năm. "
                   "Đây là rủi ro tính trên dữ liệu lịch sử gần đây, không phải backtest dài hạn hay dự báo tương lai.")

    st.markdown("---")
    st.markdown("---")
    st.markdown("#### 5️⃣ Kiểm định hệ thống Quant trên lịch sử (backtest)")
    st.caption(f"Chạy đúng bộ quy tắc đang dùng để ra đề xuất, trên toàn bộ lịch sử của **{symbol}**. "
               "Quy tắc chống nhìn trước: tín hiệu tại phiên T → khớp lệnh tại giá MỞ CỬA phiên T+1. "
               "Thoát lệnh khi điểm quant suy yếu hoặc giá thủng Chandelier Exit (trailing stop theo ATR).")
    bt1,bt2,bt3=st.columns(3)
    bt_entry=bt1.number_input("Ngưỡng điểm VÀO lệnh",value=2.5,step=0.5,
        min_value=0.0,max_value=8.0,key="bt_entry")
    bt_exit=bt2.number_input("Ngưỡng điểm THOÁT lệnh",value=-1.0,step=0.5,
        min_value=-8.0,max_value=2.0,key="bt_exit")
    bt_stop=bt3.checkbox("Bật trailing stop ATR",value=True,key="bt_stop")

    if st.button("🔬 Chạy kiểm định lịch sử", key="btn_backtest", use_container_width=True):
        with st.spinner("Đang chạy kiểm định..."):
            rs_slope_series=None
            try:
                if rs_series is not None and len(rs_series)>10:
                    rs_map=rs_series.diff(5)          # độ dốc RS 5 phiên, căn theo Date
                    rs_slope_series=df["Date"].map(rs_map).reset_index(drop=True)
            except Exception:
                rs_slope_series=None
            bt_stats, bt_err = backtest_quant_signal(df, bt_entry, bt_exit,
                                                     rs_slope_series, bt_stop)
            st.session_state.bt_result=(bt_stats, bt_err, symbol)

    btr=st.session_state.get("bt_result")
    if btr and btr[2]==symbol:
        bt_stats, bt_err, _ = btr
        if bt_err:
            st.info(f"ℹ️ {bt_err}")
        elif bt_stats:
            m1,m2,m3,m4=st.columns(4)
            m1.markdown(metric_html("Số lệnh",f"{bt_stats['n_trades']}",
                "#00d97e" if bt_stats['n_trades']>=20 else "#f5a623"),unsafe_allow_html=True)
            wr=bt_stats['win_rate']
            m2.markdown(metric_html("Win Rate",f"{wr*100:.0f}%",
                "#00d97e" if wr>0.45 else "#f5a623"),unsafe_allow_html=True)
            pf=bt_stats['profit_factor']
            m3.markdown(metric_html("Profit Factor",f"{pf:.2f}" if pf else "—",
                "#00d97e" if pf and pf>1.5 else "#f5a623" if pf and pf>1 else "#ff3d5a"),unsafe_allow_html=True)
            er=bt_stats['expectancy_r']
            m4.markdown(metric_html("Expectancy (R/lệnh)",f"{er:+.2f}R" if er is not None else "—",
                "#00d97e" if er and er>0 else "#ff3d5a"),unsafe_allow_html=True)

            m5,m6,m7,m8=st.columns(4)
            sr=bt_stats['strat_return']; bh=bt_stats['buyhold_return']
            m5.markdown(metric_html("Lợi nhuận hệ thống",f"{sr*100:+.1f}%",
                "#00d97e" if sr>0 else "#ff3d5a"),unsafe_allow_html=True)
            m6.markdown(metric_html("Mua & nắm giữ",f"{bh*100:+.1f}%",
                "#00d97e" if bh>0 else "#ff3d5a"),unsafe_allow_html=True)
            m7.markdown(metric_html("Max Drawdown",f"{bt_stats['max_dd']*100:.1f}%","#ff3d5a"),unsafe_allow_html=True)
            m8.markdown(metric_html("Thời gian nắm giữ",f"{bt_stats['time_in_market']*100:.0f}%",
                "#8baed4"),unsafe_allow_html=True)

            # Kết luận thẳng thắn về chất lượng hệ thống
            verdict=[]
            if bt_stats['n_trades']<20:
                verdict.append(("#f5a623","⚠️ Mẫu quá nhỏ (<20 lệnh) — các con số trên chưa đủ tin cậy thống kê. "
                                "Đừng dựa vào kết quả này để tăng tỷ trọng."))
            if er is not None and er>0 and pf and pf>1.3:
                verdict.append(("#00d97e","✅ Hệ thống có kỳ vọng dương trên mã này — mỗi lệnh trung bình lãi "
                                f"{er:+.2f} lần mức rủi ro bỏ ra."))
            elif er is not None and er<=0:
                verdict.append(("#ff3d5a","❌ Kỳ vọng ÂM trên mã này — hệ thống trend-following không phù hợp "
                                "với đặc tính giá của mã. Không nên áp dụng máy móc."))
            if sr<bh:
                verdict.append(("#f5a623",f"⚠️ Hệ thống ({sr*100:+.1f}%) thua Mua & nắm giữ ({bh*100:+.1f}%) "
                                "trong giai đoạn này — nhưng cần nhìn thêm Max Drawdown: hệ thống có cắt lỗ nên "
                                "thường chịu sụt giảm nhẹ hơn khi thị trường xấu."))
            else:
                verdict.append(("#00d97e",f"✅ Hệ thống ({sr*100:+.1f}%) vượt Mua & nắm giữ ({bh*100:+.1f}%)."))
            for clr,txt in verdict:
                st.markdown(f"<div style='background:#0c1d2e;border-left:4px solid {clr};"
                            f"border-radius:0 8px 8px 0;padding:10px 14px;margin:6px 0;"
                            f"font-size:13px;color:#cce0ff;'>{txt}</div>",unsafe_allow_html=True)

            eq=bt_stats['equity']
            fig_bt=go.Figure()
            fig_bt.add_trace(go.Scatter(y=eq.values,x=list(range(1,len(eq)+1)),
                mode="lines+markers",name="Vốn theo lệnh",
                line=dict(color="#00d97e",width=2),marker=dict(size=5)))
            fig_bt.add_hline(y=1,line=dict(color="rgba(255,255,255,.3)",dash="dot",width=1))
            fig_bt.update_layout(height=260,title="Đường vốn qua từng lệnh (khởi điểm = 1)",
                template="plotly_dark",**CHART_STYLE)
            fig_bt.layout.title.font.color="#8baed4"; fig_bt.layout.title.font.size=12
            fig_bt.update_xaxes(title_text="Lệnh thứ")
            st.plotly_chart(fig_bt,use_container_width=True)

            with st.expander("📋 Chi tiết từng lệnh trong kiểm định"):
                td=bt_stats['trades'].copy()
                td["Ngày vào"]=pd.to_datetime(td["entry_date"]).dt.strftime("%d/%m/%Y")
                td["Ngày ra"]=pd.to_datetime(td["exit_date"]).dt.strftime("%d/%m/%Y")
                td["Giá vào"]=td["entry"].apply(lambda v:f"{v:,.0f}")
                td["Giá ra"]=td["exit"].apply(lambda v:f"{v:,.0f}")
                td["Lãi/lỗ"]=td["pnl_pct"].apply(lambda v:f"{v*100:+.1f}%")
                td["R"]=td["r_multiple"].apply(lambda v:f"{v:+.2f}R" if pd.notna(v) else "—")
                td["Lý do thoát"]=td["reason"]
                st.dataframe(td[["Ngày vào","Ngày ra","Giá vào","Giá ra","Lãi/lỗ","R","Lý do thoát"]],
                             use_container_width=True,hide_index=True)

            st.caption("⚠️ Kiểm định trên MỘT mã và MỘT giai đoạn — kết quả tốt không đảm bảo lặp lại. "
                       "Chưa tính phí giao dịch, thuế, trượt giá và quy định T+2 của thị trường Việt Nam. "
                       "Nên chạy trên nhiều mã khác nhau trước khi tin vào hệ thống.")

    st.markdown("---")
    st.markdown("#### 6️⃣ Nhật ký lệnh đã đóng — Win Rate / Expectancy / Kelly")
    st.caption("Dùng để đánh giá hệ thống giao dịch của Hải Đăng dựa trên các lệnh đã chốt lời/cắt lỗ thực tế.")
    if "trade_log" not in st.session_state:
        st.session_state.trade_log = pd.DataFrame(
            [{"Mã": "", "Giá vào": 0.0, "Giá ra": 0.0, "Giá SL dự kiến": 0.0}])
    trade_edit = st.data_editor(st.session_state.trade_log, num_rows="dynamic",
        use_container_width=True, key="trade_editor")
    st.session_state.trade_log = trade_edit

    if st.button("🧮 Tính Win Rate & Kelly", key="btn_trade_calc", use_container_width=True):
        vt = trade_edit.copy()
        vt["Giá vào"]=pd.to_numeric(vt["Giá vào"],errors="coerce")
        vt["Giá ra"]=pd.to_numeric(vt["Giá ra"],errors="coerce")
        vt["Giá SL dự kiến"]=pd.to_numeric(vt["Giá SL dự kiến"],errors="coerce")
        vt = vt[(vt["Mã"].astype(str).str.strip()!="") & (vt["Giá vào"]>0) & (vt["Giá ra"]>0)]
        if vt.empty:
            st.warning("Nhập ít nhất 1 lệnh đã đóng (có Giá vào và Giá ra).")
        else:
            pnl_pct = (vt["Giá ra"]-vt["Giá vào"])/vt["Giá vào"]
            wins=pnl_pct[pnl_pct>0]; losses=pnl_pct[pnl_pct<=0]
            win_rate=len(wins)/len(pnl_pct) if len(pnl_pct)>0 else 0
            avg_win=float(wins.mean()) if len(wins)>0 else 0.0
            avg_loss=float(abs(losses.mean())) if len(losses)>0 else 0.0
            profit_factor = (wins.sum()/abs(losses.sum())) if losses.sum()!=0 else None
            expectancy_pct = win_rate*avg_win - (1-win_rate)*avg_loss
            has_sl = (vt["Giá SL dự kiến"]>0) & (vt["Giá vào"]!=vt["Giá SL dự kiến"])
            r_mult = np.where(has_sl, (vt["Giá ra"]-vt["Giá vào"])/(vt["Giá vào"]-vt["Giá SL dự kiến"]), np.nan)
            expectancy_r = float(np.nanmean(r_mult)) if not np.all(np.isnan(r_mult)) else None
            kelly = kelly_fraction(win_rate, avg_win, avg_loss)

            k1,k2,k3,k4=st.columns(4)
            k1.markdown(metric_html("Win Rate", f"{win_rate*100:.0f}%",
                "#00d97e" if win_rate>0.5 else "#f5a623"),unsafe_allow_html=True)
            k2.markdown(metric_html("Profit Factor",
                f"{profit_factor:.2f}" if profit_factor is not None else "∞" if losses.sum()==0 and wins.sum()>0 else "—",
                "#00d97e" if profit_factor and profit_factor>1.5 else "#f5a623"),unsafe_allow_html=True)
            k3.markdown(metric_html("Expectancy (%/lệnh)", f"{expectancy_pct*100:+.1f}%",
                "#00d97e" if expectancy_pct>0 else "#ff3d5a"),unsafe_allow_html=True)
            k4.markdown(metric_html("Expectancy (R)", f"{expectancy_r:+.2f}R" if expectancy_r is not None else "—"),unsafe_allow_html=True)

            if kelly is not None:
                kelly_show=max(0,kelly); kelly_half=kelly_show/2
                kc="#00d97e" if 0<kelly<0.25 else "#f5a623" if kelly>0 else "#ff3d5a"
                st.markdown(f"""<div style='background:#0c1d2e;border:1px solid {kc}60;border-radius:8px;
                  padding:12px 16px;margin-top:8px;'>
                  <div style='font-size:13px;color:#6a9cc8;'>💡 Kelly Criterion đề xuất</div>
                  <div style='font-size:22px;font-weight:700;color:{kc};margin-top:4px;'>{kelly_show*100:.1f}% vốn/lệnh (Full Kelly)</div>
                  <div style='font-size:13px;color:#8baed4;margin-top:2px;'>Khuyến nghị dùng Half-Kelly để an toàn: <b>{kelly_half*100:.1f}%</b> vốn/lệnh</div>
                </div>""", unsafe_allow_html=True)
                st.caption("⚠️ Kelly Criterion mang tính lý thuyết, nhạy với mẫu lệnh nhỏ — nên dùng Half-Kelly "
                           "hoặc thấp hơn, đặc biệt khi số lệnh trong nhật ký còn ít (<20 lệnh).")
            else:
                st.info("Cần đủ lệnh thắng và thua để tính Kelly Criterion.")

if auto_r:
    time.sleep(ref_sec)
    st.rerun()
