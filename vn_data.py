"""
vn_data.py — Lớp dữ liệu chứng khoán Việt Nam KHÔNG phụ thuộc vnstock.

Vì sao có file này: tháng 9-10/2026 PyPI gỡ "vnstock" và khoá "vnai", mọi app
"pip install vnstock" đều sập. File này gọi thẳng các API công khai mà vnstock
từng gọi, nên không còn phụ thuộc gói bên thứ ba.

Nguồn (đã kiểm tra thực tế 15/10/2026):
  • Giá OHLCV  : KBS  kbbuddywts.kbsec.com.vn/iis-server/investment  (đơn vị: đồng)
  • BCTC + chỉ số TTM + hồ sơ DN + tin tức : Vietcap IQ  iq.vietcap.com.vn
  • Bảng giá nhiều mã + danh sách mã/ngành : Vietcap trading.vietcap.com.vn
  • Dự phòng giá : Yahoo Finance (yfinance) — mã HOSE dạng 'FPT.VN', chỉ số '^VNINDEX.VN'

Thiết kế: phần GỌI MẠNG (http_*) tách khỏi phần XỬ LÝ (parse_*) — các hàm parse là
hàm thuần, nhận JSON thô và trả DataFrame, nên test được độc lập với mạng.
Đơn vị tiền trong BCTC: ĐỒNG (VND) nguyên bản như API trả về.
"""
from __future__ import annotations

import random
import re
import time
from datetime import datetime, timedelta

import pandas as pd

TIMEOUT = 12
KBS_URL = "https://kbbuddywts.kbsec.com.vn/iis-server/investment"
VCI_TRADING = "https://trading.vietcap.com.vn/api"
VCI_IQ = "https://iq.vietcap.com.vn/api/iq-insight-service/v1"

INDICES = {"VNINDEX", "HNXINDEX", "UPCOMINDEX", "VN30", "HNX30", "VN100"}
KBS_INTERVALS = {"1m": "1P", "5m": "5P", "15m": "15P", "30m": "30P", "1H": "60P",
                 "1D": "day", "1W": "week", "1M": "month"}

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


# ═════════════════════════════ HTTP ═════════════════════════════════════════
def _headers(source: str) -> dict:
    h = {"Accept": "application/json, text/plain, */*", "User-Agent": _UA,
         "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8"}
    if source == "VCI":
        dev = f"{random.getrandbits(64):016x}"
        h.update({"Referer": "https://trading.vietcap.com.vn/",
                  "Origin": "https://trading.vietcap.com.vn",
                  "Device-Id": dev})
    elif source == "KBS":
        h.update({"Referer": "https://kbbuddywts.kbsec.com.vn/",
                  "Origin": "https://kbbuddywts.kbsec.com.vn"})
    return h


def http_json(method: str, url: str, source: str, retries: int = 2, **kw):
    """Gọi API, thử lại khi lỗi mạng/5xx. Trả JSON hoặc ném lỗi có thông điệp rõ."""
    import requests
    last = None
    for attempt in range(retries + 1):
        try:
            r = requests.request(method, url, headers=_headers(source), timeout=TIMEOUT, **kw)
            if r.status_code >= 500 or r.status_code == 429:
                last = RuntimeError(f"{source} HTTP {r.status_code}")
                time.sleep(0.6 * (attempt + 1)); continue
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"{source}: {type(last).__name__}: {last}")


# ═════════════════════════════ GIÁ (KBS → Yahoo) ════════════════════════════
def parse_kbs_bars(payload: dict, key: str, interval: str) -> pd.DataFrame:
    """JSON KBS → DataFrame Date/Open/High/Low/Close/Volume, cũ→mới.
    Lưu ý thực tế: KBS trả mới→cũ; phiên gần nhất đôi khi có 2 dòng (dòng SAU là
    dòng đã chốt) và giá phiên đang chạy có thể ở dạng chuỗi."""
    rows = (payload or {}).get(key) or []
    if not rows:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])
    df = pd.DataFrame(rows)
    df = df.rename(columns={"t": "Date", "o": "Open", "h": "High", "l": "Low",
                            "c": "Close", "v": "Volume"})
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    if interval in ("1D", "1W", "1M"):
        df["Date"] = df["Date"].dt.normalize()
    df = df.dropna(subset=["Date"]).drop_duplicates("Date", keep="last")
    for c in ["Open", "High", "Low", "Close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0).astype("int64")
    df = df.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)
    return df[["Date", "Open", "High", "Low", "Close", "Volume"]]


def kbs_history(symbol: str, start: datetime, end: datetime, interval: str = "1D") -> pd.DataFrame:
    sym = symbol.upper()
    key = f"data_{KBS_INTERVALS.get(interval, 'day')}"
    path = "index" if sym in INDICES else "stocks"
    payload = http_json("GET", f"{KBS_URL}/{path}/{sym}/{key}", "KBS", params={
        "sdate": start.strftime("%d-%m-%Y"), "edate": end.strftime("%d-%m-%Y")})
    df = parse_kbs_bars(payload, key, interval)
    if df.empty:
        raise ValueError(f"KBS không có dữ liệu {sym} ({interval})")
    return df


def yahoo_history(symbol: str, start: datetime, end: datetime, interval: str = "1D") -> pd.DataFrame:
    import yfinance as yf
    sym = symbol.upper()
    ticker = "^VNINDEX.VN" if sym == "VNINDEX" else f"{sym}.VN"
    yi = {"1D": "1d", "1W": "1wk", "1M": "1mo", "1H": "60m", "30m": "30m",
          "15m": "15m", "5m": "5m", "1m": "1m"}.get(interval, "1d")
    df = yf.download(ticker, start=start.strftime("%Y-%m-%d"),
                     end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
                     interval=yi, progress=False, auto_adjust=True)
    if df is None or df.empty:
        raise ValueError(f"Yahoo không có dữ liệu {ticker}")
    df = df.reset_index()
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    dcol = "Datetime" if "Datetime" in df.columns else "Date"
    df = df.rename(columns={dcol: "Date"})
    df["Date"] = pd.to_datetime(df["Date"])
    try:
        df["Date"] = df["Date"].dt.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    for c in ["Open", "High", "Low", "Close"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0).astype("int64")
    df = df.dropna(subset=["Close"]).drop_duplicates("Date", keep="last")
    return df.sort_values("Date").reset_index(drop=True)[["Date", "Open", "High", "Low", "Close", "Volume"]]


def get_history(symbol: str, days: int, interval: str = "1D"):
    """Giá lịch sử: KBS (chính) → Yahoo (dự phòng). Trả (df, nhãn nguồn)."""
    end = datetime.now()
    start = end - timedelta(days=int(days))
    errs = []
    try:
        return kbs_history(symbol, start, end, interval), "KBS (KB Securities) ✅"
    except Exception as e:  # noqa: BLE001
        errs.append(f"KBS: {e}")
    try:
        return yahoo_history(symbol, start, end, interval), "Yahoo Finance ⚠️ (dự phòng)"
    except Exception as e:  # noqa: BLE001
        errs.append(f"Yahoo: {e}")
    raise RuntimeError(" | ".join(errs))


# ═════════════════════════════ BẢNG GIÁ / DANH SÁCH MÃ ══════════════════════
def parse_vci_board(rows) -> dict:
    out = {}
    for row in rows or []:
        li = row.get("listingInfo") or {}
        mp = row.get("matchPrice") or {}
        sym = (li.get("symbol") or "").upper()
        if not sym:
            continue
        price = mp.get("matchPrice") or mp.get("price") or None
        ref = li.get("refPrice") or mp.get("referencePrice") or None
        try:
            price = float(price) if price else None
            ref = float(ref) if ref else None
        except (TypeError, ValueError):
            price, ref = None, None
        if not price:
            price = ref  # chưa khớp lệnh trong phiên → dùng giá tham chiếu
        chg = (price - ref) / ref * 100 if (price and ref) else 0.0
        out[sym] = {"price": price, "chg": chg, "ref": ref,
                    "volume": mp.get("accumulatedVolume"),
                    "value_bn": (mp.get("accumulatedValue") or 0) / 1e3 if mp.get("accumulatedValue") else None}
    return out


def price_board(symbols) -> dict:
    syms = [s.upper() for s in symbols if s]
    if not syms:
        return {}
    rows = http_json("POST", f"{VCI_TRADING}/price/symbols/getList", "VCI", json={"symbols": syms})
    return parse_vci_board(rows)


def list_symbols() -> pd.DataFrame:
    """Toàn bộ mã cổ phiếu niêm yết: symbol, board, icbCode2, tên."""
    rows = http_json("GET", f"{VCI_TRADING}/price/symbols/getAll", "VCI")
    df = pd.DataFrame(rows or [])
    if df.empty:
        return df
    df = df[(df.get("type") == "STOCK") & (df.get("board") != "DELISTED")]
    return df[["symbol", "board", "icbCode2", "organName", "organShortName"]].reset_index(drop=True)


# ═════════════════════════════ BCTC — VIETCAP IQ ════════════════════════════
SECTIONS = {"IS": "INCOME_STATEMENT", "BS": "BALANCE_SHEET", "CF": "CASH_FLOW"}

# Mã chỉ tiêu VCI → item_id CHUẨN mà phần còn lại của app (Tab Cơ bản, Chất lượng lợi
# nhuận…) đang tìm. Những chỉ tiêu khác dùng tên tiếng Anh dạng snake_case.
CANON = {
    # Kết quả kinh doanh
    "isa3": "net_revenue", "isa4": "cost_of_goods_sold", "isa5": "gross_profit",
    "isa6": "financial_income", "isa7": "financial_expenses", "isa8": "interest_expense",
    "isa9": "selling_expenses", "isa10": "general_admin_expenses",
    "isa11": "operating_profit", "isa16": "profit_before_tax", "isa19": "corporate_income_tax",
    "isa20": "net_profit_after_tax", "isa21": "minority_interest_profit",
    "isa22": "attributable_to_parent_company", "isa23": "eps", "isa24": "diluted_eps",
    # Ngân hàng
    "isb25": "interest_income", "isb26": "interest_expenses_bank", "isb27": "net_interest_income",
    "isb30": "net_fee_income", "isb38": "total_operating_income", "isb39": "operating_expenses_bank",
    "isb40": "pre_provision_profit", "isb41": "provision_expense",
    # Cân đối kế toán
    "bsa1": "current_assets", "bsa2": "cash_and_cash_equivalents", "bsa5": "short_term_investments",
    "bsa8": "short_term_receivables", "bsa9": "trade_receivables_customers", "bsa15": "inventories",
    "bsa23": "long_term_assets", "bsa29": "fixed_assets", "bsa53": "total_assets",
    "bsa54": "total_liabilities", "bsa55": "current_liabilities", "bsa56": "short_term_borrowings",
    "bsa57": "trade_payables", "bsa58": "advances_from_customers", "bsa67": "long_term_liabilities",
    "bsa71": "long_term_borrowings", "bsa78": "owners_equity", "bsa80": "paid_in_capital",
    "bsa90": "undistributed_earnings", "bsa96": "total_resources", "bsa210": "minority_interests",
    "bsb103": "loans_to_customers", "bsb104": "gross_loans", "bsb105": "loan_loss_reserve",
    "bsb113": "customer_deposits", "bsb116": "valuable_papers_issued",
    # Lưu chuyển tiền tệ
    "cfa2": "depreciation", "cfa18": "net_cash_flows_from_operating_activities",
    "cfa19": "purchase_of_fixed_assets", "cfa26": "net_cash_flows_from_investing_activities",
    "cfa32": "dividends_paid", "cfa34": "net_cash_flows_from_financing_activities",
    "cfa35": "net_change_in_cash", "cfa36": "cash_and_cash_equivalents_at_beginning_of_the_period",
    "cfa38": "cash_and_cash_equivalents_at_end_of_the_period",
}
COM_TYPES = {"CT": "Doanh nghiệp", "NH": "Ngân hàng", "CK": "Chứng khoán", "BH": "Bảo hiểm"}


def _snake(s) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", str(s or "")).strip("_").lower()
    return s or "item"


def iq_get(path: str, params: dict | None = None):
    j = http_json("GET", f"{VCI_IQ}/{path}", "VCI", params=params or {})
    if isinstance(j, dict) and "data" in j:
        if j.get("successful") is False and j.get("data") is None:
            raise RuntimeError(f"VCI: {j.get('msg')}")
        return j["data"]
    return j


def parse_statement(raw: dict, metrics: list, period: str = "year") -> pd.DataFrame:
    """Báo cáo dạng DÀI: mỗi dòng 1 chỉ tiêu, mỗi cột 1 kỳ.
    raw     : data của /financial-statement?section=… ({years:[…], quarters:[…]})
    metrics : danh sách chỉ tiêu của section đó (từ /financial-statement/metrics)
    period  : 'year' → cột '2024'; 'quarter' → cột '2024-Q3'."""
    recs = (raw or {}).get("years" if period == "year" else "quarters") or []
    if not recs or not metrics:
        return pd.DataFrame()
    recs = [r for r in recs if r.get("yearReport")]
    if period == "year":
        recs = sorted(recs, key=lambda r: int(r["yearReport"]))
        labels = [str(int(r["yearReport"])) for r in recs]
    else:
        recs = [r for r in recs if 1 <= int(r.get("lengthReport") or 0) <= 4]
        recs = sorted(recs, key=lambda r: (int(r["yearReport"]), int(r["lengthReport"])))
        labels = [f"{int(r['yearReport'])}-Q{int(r['lengthReport'])}" for r in recs]
    # khử kỳ trùng (giữ bản xuất hiện sau — thường là bản cập nhật)
    uniq = {}
    for lab, r in zip(labels, recs):
        uniq[lab] = r
    labels = list(uniq.keys()); recs = list(uniq.values())

    rows, seen_ids = [], {}
    for m in metrics:
        field = m.get("field")
        if not field or field == "null":
            continue
        vals = [r.get(field) for r in recs]
        if all(v in (None, 0, 0.0) for v in vals):
            continue
        iid = CANON.get(field) or _snake(m.get("titleEn") or m.get("titleVi"))
        if iid in seen_ids:
            seen_ids[iid] += 1; iid = f"{iid}_{seen_ids[iid]}"
        else:
            seen_ids[iid] = 0
        row = {"item": m.get("titleVi") or field, "item_en": m.get("titleEn") or field,
               "item_id": iid, "field": field, "levels": int(m.get("level") or 1)}
        for lab, v in zip(labels, vals):
            try:
                row[lab] = float(v) if v is not None else None
            except (TypeError, ValueError):
                row[lab] = None
        rows.append(row)
    df = pd.DataFrame(rows)
    df.attrs["periods"] = labels
    df.attrs["period"] = period
    return df


# Chỉ số TTM của VCI → item_id app đang dùng (_GV_ALIASES ở app.py)
RATIO_MAP = {
    "pe": "pe_ratio", "pb": "pb_ratio", "ps": "ps_ratio", "priceToCashFlow": "price_to_cash_flow",
    "evToEbitda": "ev_to_ebitda", "roe": "roe", "roa": "roa", "roic": "roic",
    "grossMargin": "gross_margin", "ebitMargin": "ebit_margin",
    "preTaxProfitMargin": "pretax_margin", "afterTaxProfitMargin": "net_margin",
    "currentRatio": "current_ratio", "quickRatio": "quick_ratio", "cashRatio": "cash_ratio",
    "debtToEquity": "liabilities_to_equity", "debtPerEquity": "debt_to_equity",
    "assetTurnover": "asset_turnover", "fixedAssetTurnover": "fixed_asset_turnover",
    "daySaleOutstanding": "days_sales_outstanding", "daysInventoryOutstanding": "days_inventory",
    "daysPayableOutstanding": "days_payable", "cashCycle": "cash_conversion_cycle",
    "dividendYield": "dividend_yield", "marketCap": "market_cap",
    "numberOfSharesMktCap": "shares_outstanding", "ebitda": "ebitda", "ebit": "ebit",
    # Ngân hàng
    "netInterestMargin": "nim", "averageYieldOnEarningAssets": "yield_on_earning_assets",
    "averageCostOfFinancing": "cost_of_funds", "nonAndInterestIncome": "non_interest_income_share",
    "cir": "cir", "loansGrowth": "loan_growth", "depositGrowth": "deposit_growth",
    "totalEquityTotalAsset": "equity_total_assets", "ldrLoanDepositRatio": "ldr",
    "npl": "npl", "loansLossReservesToNPLs": "llr_coverage",
    "loansLossReserveToLoans": "llr_to_loans", "provisionToOutstandingLoans": "credit_cost",
    "casaRatio": "casa",
}
RATIO_LABELS = {
    "pe_ratio": "P/E", "pb_ratio": "P/B", "ps_ratio": "P/S", "price_to_cash_flow": "P/CF",
    "ev_to_ebitda": "EV/EBITDA", "roe": "ROE", "roa": "ROA", "roic": "ROIC",
    "gross_margin": "Biên lãi gộp", "ebit_margin": "Biên EBIT", "pretax_margin": "Biên LN trước thuế",
    "net_margin": "Biên LN ròng", "current_ratio": "Thanh toán hiện hành",
    "quick_ratio": "Thanh toán nhanh", "cash_ratio": "Thanh toán tiền mặt",
    "liabilities_to_equity": "Nợ phải trả/VCSH", "debt_to_equity": "Nợ vay/VCSH",
    "asset_turnover": "Vòng quay tài sản", "fixed_asset_turnover": "Vòng quay TSCĐ",
    "days_sales_outstanding": "Số ngày phải thu", "days_inventory": "Số ngày tồn kho",
    "days_payable": "Số ngày phải trả", "cash_conversion_cycle": "Chu kỳ tiền mặt (ngày)",
    "dividend_yield": "Tỷ suất cổ tức", "market_cap": "Vốn hoá", "shares_outstanding": "Số CP lưu hành",
    "ebitda": "EBITDA (TTM)", "ebit": "EBIT (TTM)", "nim": "NIM", "yield_on_earning_assets": "Lợi suất TS sinh lãi",
    "cost_of_funds": "Chi phí vốn", "non_interest_income_share": "Tỷ trọng thu nhập ngoài lãi",
    "cir": "CIR", "loan_growth": "Tăng trưởng tín dụng", "deposit_growth": "Tăng trưởng tiền gửi",
    "equity_total_assets": "VCSH/Tổng TS", "ldr": "LDR", "npl": "Nợ xấu (NPL)",
    "llr_coverage": "Bao phủ nợ xấu (LLR)", "llr_to_loans": "Dự phòng/Dư nợ",
    "credit_cost": "Chi phí tín dụng", "casa": "CASA",
    "earnings_per_share": "EPS (TTM)", "book_value_per_share": "BVPS",
}
# Chỉ số mà API trả âm theo quy ước kế toán → lấy trị tuyệt đối khi hiển thị
_ABS_RATIOS = {"cir", "cost_of_funds", "llr_coverage", "credit_cost"}


def parse_ratios(stats: list, period: str = "year") -> pd.DataFrame:
    """Bảng chỉ số TTM dạng DÀI. period='year' lấy dòng Q4 mỗi năm (= cả năm) và thêm
    1 cột TTM mới nhất nếu quý gần nhất chưa phải Q4 (VD '2026Q2·TTM')."""
    if not stats:
        return pd.DataFrame()
    rows = sorted([s for s in stats if s.get("year")],
                  key=lambda s: (int(s["year"]), int(s.get("quarter") or 0)))
    if period == "year":
        pick = {}
        for s in rows:
            if int(s.get("quarter") or 0) == 4:
                pick[str(int(s["year"]))] = s
        last = rows[-1]
        if int(last.get("quarter") or 0) != 4:
            pick[f"{int(last['year'])}Q{int(last['quarter'])}·TTM"] = last
    else:
        pick = {f"{int(s['year'])}-Q{int(s['quarter'])}": s for s in rows}
    labels = list(pick.keys())
    out = []
    for src, iid in RATIO_MAP.items():
        vals = []
        for lab in labels:
            v = pick[lab].get(src)
            try:
                v = float(v) if v is not None else None
            except (TypeError, ValueError):
                v = None
            if v is not None and iid in _ABS_RATIOS:
                v = abs(v)
            vals.append(v)
        if all(v in (None, 0.0) for v in vals):
            continue
        row = {"item": RATIO_LABELS.get(iid, iid), "item_en": src, "item_id": iid, "field": src, "levels": 1}
        row.update(dict(zip(labels, vals)))
        out.append(row)
    df = pd.DataFrame(out)
    df.attrs["periods"] = labels
    return df


def add_per_share_rows(ratio_df: pd.DataFrame, inc_q: pd.DataFrame, bal_q: pd.DataFrame,
                       shares_by_col: dict) -> pd.DataFrame:
    """Bổ sung EPS(TTM) và BVPS vào bảng chỉ số năm — app cũ cần 2 dòng này."""
    if ratio_df is None or ratio_df.empty:
        return ratio_df
    cols = [c for c in ratio_df.columns if c not in ("item", "item_en", "item_id", "field", "levels")]
    eps_row = {"item": RATIO_LABELS["earnings_per_share"], "item_en": "EPS TTM",
               "item_id": "earnings_per_share", "field": "eps_ttm", "levels": 1}
    bv_row = {"item": RATIO_LABELS["book_value_per_share"], "item_en": "BVPS",
              "item_id": "book_value_per_share", "field": "bvps", "levels": 1}
    qcols = [c for c in (inc_q.columns if inc_q is not None and not inc_q.empty else [])
             if re.match(r"^\d{4}-Q[1-4]$", str(c))]
    for c in cols:
        m = re.match(r"^(\d{4})(?:Q([1-4]))?", str(c))
        if not m:
            continue
        y, q = int(m.group(1)), int(m.group(2) or 4)
        end = f"{y}-Q{q}"
        sh = shares_by_col.get(c)
        eps = bv = None
        if end in qcols and sh:
            i = qcols.index(end)
            if i >= 3:
                last4 = qcols[i - 3:i + 1]
                npat = row_values(inc_q, "attributable_to_parent_company", last4)
                if not any(v is None for v in npat):
                    eps = sum(npat) / sh
            eq = row_values(bal_q, "owners_equity", [end])[0] if bal_q is not None else None
            mi = (row_values(bal_q, "minority_interests", [end])[0]
                  if bal_q is not None and minority_inside_equity(bal_q) else None)
            if eq is not None:
                bv = (eq - (mi or 0)) / sh
        eps_row[c] = eps; bv_row[c] = bv
    return pd.concat([ratio_df, pd.DataFrame([eps_row, bv_row])], ignore_index=True)


def minority_inside_equity(bal: pd.DataFrame) -> bool:
    """Lợi ích CĐ thiểu số (bsa210) nằm TRONG vốn chủ (cấp 2 — doanh nghiệp thường theo
    chuẩn mực từ 2015) hay TÁCH RIÊNG ngoài vốn chủ (cấp 1 — mẫu báo cáo ngân hàng).
    Quyết định có trừ nó khỏi VCSH khi tính VCSH của cổ đông mẹ hay không."""
    if bal is None or bal.empty or "field" not in bal.columns:
        return True
    hit = bal[bal["field"] == "bsa210"]
    return hit.empty or int(hit.iloc[0].get("levels") or 1) >= 2


def row_values(df: pd.DataFrame, item_id: str, cols) -> list:
    """Giá trị 1 chỉ tiêu (theo item_id CHUẨN hoặc theo mã field VCI) qua các cột kỳ."""
    if df is None or df.empty:
        return [None for _ in cols]
    hit = df[(df["item_id"] == item_id) | (df.get("field", pd.Series(dtype=str)) == item_id)]
    if hit.empty:
        return [None for _ in cols]
    r = hit.iloc[0]
    out = []
    for c in cols:
        v = r.get(c) if c in hit.columns else None
        out.append(float(v) if v is not None and pd.notna(v) else None)
    return out


def get_financials(symbol: str) -> dict:
    """Tải trọn bộ BCTC + chỉ số + hồ sơ của 1 mã (≈6 request).
    Trả dict: inc_y, bal_y, cf_y, inc_q, bal_q, cf_q, ratio_y, ratio_q, details, com_type, errors."""
    sym = symbol.upper()
    out = {k: pd.DataFrame() for k in ("inc_y", "bal_y", "cf_y", "inc_q", "bal_q", "cf_q", "ratio_y", "ratio_q")}
    out.update(details={}, com_type="CT", errors=[], source="Vietcap IQ")
    # 6 request chạy SONG SONG: tổng thời gian ≈ request chậm nhất thay vì cộng dồn
    jobs = {"metrics": (f"company/{sym}/financial-statement/metrics", None),
            "details": ("company/details", {"ticker": sym}),
            "stats": (f"company/{sym}/statistics-financial", None)}
    for sec in SECTIONS.values():
        jobs[sec] = (f"company/{sym}/financial-statement", {"section": sec})
    got, errs = {}, {}
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=len(jobs)) as ex:
            futs = {k: ex.submit(iq_get, *v) for k, v in jobs.items()}
            for k, f in futs.items():
                try:
                    got[k] = f.result()
                except Exception as e:  # noqa: BLE001
                    errs[k] = e
    except RuntimeError:  # môi trường không hỗ trợ thread → chạy tuần tự
        for k, v in jobs.items():
            try:
                got[k] = iq_get(*v)
            except Exception as e:  # noqa: BLE001
                errs[k] = e
    metrics = got.get("metrics") or {}
    if "metrics" in errs:
        out["errors"].append(f"metrics: {errs['metrics']}")
    for short, sec in SECTIONS.items():
        try:
            if sec in errs:
                raise errs[sec]
            raw = got.get(sec)
            key = {"IS": "inc", "BS": "bal", "CF": "cf"}[short]
            out[f"{key}_y"] = parse_statement(raw, metrics.get(sec) or [], "year")
            out[f"{key}_q"] = parse_statement(raw, metrics.get(sec) or [], "quarter")
        except Exception as e:  # noqa: BLE001
            out["errors"].append(f"{sec}: {e}")
    try:
        if "details" in errs:
            raise errs["details"]
        details = dict(got.get("details") or {})
        details.pop("profile", None); details.pop("enProfile", None)
        out["details"] = details
        out["com_type"] = details.get("comTypeCode") or "CT"
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"details: {e}")
    try:
        if "stats" in errs:
            raise errs["stats"]
        stats = got.get("stats") or []
        out["stats"] = stats
        ry = parse_ratios(stats, "year")
        rq = parse_ratios(stats, "quarter")
        # số CP theo từng kỳ để tính EPS/BVPS
        sh_by_col = {}
        rows = {f"{int(s['year'])}-Q{int(s['quarter'])}": s for s in stats if s.get("year")}
        for c in ry.columns:
            m = re.match(r"^(\d{4})(?:Q([1-4]))?", str(c))
            if m:
                s = rows.get(f"{m.group(1)}-Q{m.group(2) or 4}")
                if s and s.get("numberOfSharesMktCap"):
                    sh_by_col[c] = float(s["numberOfSharesMktCap"])
        out["ratio_y"] = add_per_share_rows(ry, out["inc_q"], out["bal_q"], sh_by_col)
        out["ratio_q"] = rq
    except Exception as e:  # noqa: BLE001
        out["errors"].append(f"ratios: {e}"); out["stats"] = []
    return out


def get_news(symbol: str, days: int = 120, size: int = 15) -> list:
    to = datetime.now(); fr = to - timedelta(days=days)
    data = iq_get("news", {"ticker": symbol.upper(), "fromDate": fr.strftime("%Y%m%d"),
                           "toDate": to.strftime("%Y%m%d"), "languageId": 1,
                           "page": 0, "size": size}) or {}
    items = data.get("content", []) if isinstance(data, dict) else data
    return [{"title": (it.get("newsTitle") or "").strip(), "date": str(it.get("publicDate") or "")[:10],
             "url": it.get("newsSourceLink")} for it in items if it.get("newsTitle")]


def get_events(symbol: str, days_back: int = 400, days_fwd: int = 120) -> list:
    to = datetime.now() + timedelta(days=days_fwd); fr = datetime.now() - timedelta(days=days_back)
    data = iq_get("events", {"ticker": symbol.upper(), "fromDate": fr.strftime("%Y%m%d"),
                             "toDate": to.strftime("%Y%m%d"), "eventCode": "DIV,ISS",
                             "page": 0, "size": 20}) or {}
    items = data.get("content", []) if isinstance(data, dict) else data
    return [{"title": it.get("eventTitleVi") or it.get("eventNameVi"),
             "exright": str(it.get("exrightDate") or "")[:10],
             "record": str(it.get("recordDate") or "")[:10],
             "ratio": it.get("exerciseRatio"), "code": it.get("eventCode")} for it in items]
