"""
vn_market.py — Dữ liệu đặc thù thị trường Việt Nam (đã kiểm tra thực tế 15/10/2026).

  • Khớp lệnh từng tick (mua/bán CHỦ ĐỘNG)   : KBS  /trade/history/{mã}        (phiên gần nhất)
  • Bảng giá realtime, khối ngoại, thoả thuận: KBS  /stock/iss                 (POST danh sách mã)
  • Danh sách mã theo sàn/rổ, ngành          : KBS  /index/{nhóm}/stocks, /sector/*
  • Lịch sử khối ngoại, tự doanh, đặt lệnh   : CafeF /du-lieu/Ajax/PageNew/DataHistory/*.ashx

Phần gọi mạng tách khỏi phần xử lý (parse_*) để test được bằng dữ liệu mẫu.
Mọi hàm public đều KHÔNG ném lỗi ra ngoài khi nguồn hỏng — trả DataFrame rỗng/{} để app
vẫn chạy phần còn lại.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from vn_data import KBS_URL, VCI_IQ, http_json

CAFEF = "https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory"
GROUPS = {"HOSE": "HOSE", "HNX": "HNX", "UPCOM": "UPCOM", "VN30": "30", "VN100": "100"}


def _cafef(endpoint: str, symbol: str, page: int = 1, size: int = 30):
    import requests
    r = requests.get(f"{CAFEF}/{endpoint}.ashx", timeout=12,
                     params={"Symbol": symbol.upper(), "StartDate": "", "EndDate": "",
                             "PageIndex": page, "PageSize": size},
                     headers={"User-Agent": "Mozilla/5.0", "Referer": "https://cafef.vn/"})
    r.raise_for_status()
    j = r.json()
    if not j.get("Success"):
        raise RuntimeError(f"CafeF {endpoint}: {j.get('Message')}")
    return j.get("Data") or {}


def _pages(endpoint, symbol, n_pages):
    """Gọi nhiều trang CafeF song song (mỗi trang 30 phiên)."""
    out = [None] * n_pages
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=n_pages) as ex:
            futs = [ex.submit(_cafef, endpoint, symbol, p + 1) for p in range(n_pages)]
            for i, f in enumerate(futs):
                try:
                    out[i] = f.result()
                except Exception:  # noqa: BLE001
                    out[i] = None
    except RuntimeError:
        for p in range(n_pages):
            try:
                out[p] = _cafef(endpoint, symbol, p + 1)
            except Exception:  # noqa: BLE001
                out[p] = None
    return [o for o in out if o]


def _to_date(s):
    return pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")


# ═════════════════════════════ KHỐI NGOẠI / TỰ DOANH / ĐẶT LỆNH ════════════
def parse_foreign(pages: list) -> pd.DataFrame:
    rows = []
    for d in pages:
        rows += d.get("Data") or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "Date": _to_date(df["Ngay"]),
        "buy_vol": pd.to_numeric(df.get("KLMua"), errors="coerce"),
        "sell_vol": pd.to_numeric(df.get("KLBan"), errors="coerce"),
        "buy_val": pd.to_numeric(df.get("GtMua"), errors="coerce"),
        "sell_val": pd.to_numeric(df.get("GtBan"), errors="coerce"),
        "net_vol": pd.to_numeric(df.get("KLGDRong"), errors="coerce"),
        "net_val": pd.to_numeric(df.get("GTDGRong"), errors="coerce"),
        "room_left": pd.to_numeric(df.get("RoomConLai"), errors="coerce"),
        "own_pct": pd.to_numeric(df.get("DangSoHuu"), errors="coerce"),
    })
    return out.dropna(subset=["Date"]).drop_duplicates("Date").sort_values("Date").reset_index(drop=True)


def foreign_history(symbol: str, n_pages: int = 4) -> pd.DataFrame:
    """Giao dịch khối ngoại theo ngày (~30 phiên/trang). symbol='VNINDEX' → toàn sàn HOSE."""
    try:
        return parse_foreign(_pages("GDKhoiNgoai", symbol, n_pages))
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def parse_prop(data: dict) -> pd.DataFrame:
    rows = ((data or {}).get("Data") or {}).get("ListDataTudoanh") or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "Date": _to_date(df["Date"]),
        "buy_vol": pd.to_numeric(df.get("KLcpMua"), errors="coerce"),
        "sell_vol": pd.to_numeric(df.get("KlcpBan"), errors="coerce"),
        "buy_val": pd.to_numeric(df.get("GtMua"), errors="coerce"),
        "sell_val": pd.to_numeric(df.get("GtBan"), errors="coerce"),
    })
    out["net_vol"] = out["buy_vol"] - out["sell_vol"]
    out["net_val"] = out["buy_val"] - out["sell_val"]
    return out.dropna(subset=["Date"]).drop_duplicates("Date").sort_values("Date").reset_index(drop=True)


def prop_history(symbol: str) -> pd.DataFrame:
    """Tự doanh (CTCK tự doanh) theo ngày — CafeF trả ~1 năm trong 1 lần."""
    try:
        return parse_prop(_cafef("GDTuDoanh", symbol, 1, 250))
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def parse_orders(pages: list) -> pd.DataFrame:
    rows = []
    for d in pages:
        rows += d.get("Data") or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    num = lambda c: pd.to_numeric(df.get(c), errors="coerce")  # noqa: E731
    out = pd.DataFrame({
        "Date": _to_date(df["Date"]),
        "n_buy": num("SoLenhMua"), "buy_vol": num("KLDatMua"), "avg_buy": num("KLTB1LenhMua"),
        "n_sell": num("SoLenhDatBan"), "sell_vol": num("KLDatBan"), "avg_sell": num("KLTB1LenhBan"),
    })
    out["imbalance"] = (out["buy_vol"] - out["sell_vol"]) / (out["buy_vol"] + out["sell_vol"])
    return out.dropna(subset=["Date"]).drop_duplicates("Date").sort_values("Date").reset_index(drop=True)


def order_stats(symbol: str, n_pages: int = 3) -> pd.DataFrame:
    """Thống kê ĐẶT lệnh: số lệnh, KL đặt mua/bán, KL trung bình 1 lệnh → cung/cầu & cỡ lệnh."""
    try:
        return parse_orders(_pages("ThongKeDL", symbol, n_pages))
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


# ═════════════════════════════ KHỚP LỆNH TRONG PHIÊN (TICK) ═══════════════════
def parse_ticks(payload: dict) -> pd.DataFrame:
    rows = (payload or {}).get("data") or []
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    out = pd.DataFrame({
        "time": pd.to_datetime(df["TD"] + " " + df["FT"], format="%d/%m/%Y %H:%M:%S", errors="coerce"),
        "price": pd.to_numeric(df["FMP"], errors="coerce"),
        "vol": pd.to_numeric(df["FV"], errors="coerce").fillna(0),
        "side": df["LC"].map({"B": "Mua chủ động", "S": "Bán chủ động"}).fillna("ATO/ATC"),
    })
    out["value"] = out["price"] * out["vol"]
    return out.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)


def intraday_ticks(symbol: str) -> pd.DataFrame:
    """Toàn bộ lệnh khớp của PHIÊN GẦN NHẤT (KBS chỉ trả phiên gần nhất)."""
    try:
        payload = http_json("GET", f"{KBS_URL}/trade/history/{symbol.upper()}", "KBS",
                            retries=1, params={"page": 1, "limit": 20000})
        return parse_ticks(payload)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


# ═════════════════════════════ BẢNG GIÁ / ĐỘ RỘNG / NGÀNH ═════════════════════
def parse_board(rows) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    num = lambda c: pd.to_numeric(df.get(c), errors="coerce")  # noqa: E731
    out = pd.DataFrame({
        "symbol": df.get("SB"), "exchange": df.get("EX"),
        "price": num("CP"), "ref": num("RE"), "ceil": num("CL"), "floor": num("FL"),
        "vol": num("TT"), "value": num("TV"), "f_buy": num("FB"), "f_sell": num("FS"),
        "f_room": num("FR"), "pt_value": num("PTV"), "high": num("HI"), "low": num("LO"), "open": num("OP"),
    })
    out["price"] = out["price"].where(out["price"] > 0, out["ref"])
    out["chg_pct"] = (out["price"] / out["ref"] - 1) * 100
    out["f_net_val"] = (out["f_buy"].fillna(0) - out["f_sell"].fillna(0)) * out["price"]
    return out


def board(symbols) -> pd.DataFrame:
    syms = [s.upper() for s in symbols if s]
    if not syms:
        return pd.DataFrame()
    try:
        rows = http_json("POST", f"{KBS_URL}/stock/iss", "KBS", retries=1, json={"code": ",".join(syms)})
        return parse_board(rows)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def group_symbols(group: str = "HOSE") -> list:
    try:
        j = http_json("GET", f"{KBS_URL}/index/{GROUPS.get(group, group)}/stocks", "KBS", retries=1)
        return list(j.get("data") or []) if isinstance(j, dict) else list(j or [])
    except Exception:  # noqa: BLE001
        return []


def breadth(bd: pd.DataFrame) -> dict:
    """Độ rộng thị trường từ bảng giá: số mã tăng/giảm/đứng, trần/sàn, giá trị, khối ngoại ròng."""
    if bd is None or bd.empty:
        return {}
    live = bd[bd["price"] > 0]
    up = int((live["price"] > live["ref"]).sum()); dn = int((live["price"] < live["ref"]).sum())
    return dict(up=up, down=dn, flat=int(len(live) - up - dn),
                ceil=int((live["price"] >= live["ceil"]).sum()), floor=int((live["price"] <= live["floor"]).sum()),
                value_bn=float(live["value"].sum() / 1e9), foreign_net_bn=float(live["f_net_val"].sum() / 1e9),
                pt_bn=float(live["pt_value"].sum() / 1e9), n=len(live),
                ad_ratio=up / dn if dn else None)


def sectors() -> pd.DataFrame:
    try:
        j = http_json("GET", f"{KBS_URL}/sector/all", "KBS", retries=1)
        df = pd.DataFrame(j or [])
        if not df.empty:
            df["change"] = pd.to_numeric(df["change"], errors="coerce")
        return df
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


def sector_stocks(code) -> tuple:
    try:
        j = http_json("GET", f"{KBS_URL}/sector/stock", "KBS", retries=1, params={"code": code, "l": 1})
        return j.get("name"), [s.get("sb") for s in (j.get("stocks") or []) if s.get("sb")]
    except Exception:  # noqa: BLE001
        return None, []


def sector_map() -> dict:
    """{mã: (code ngành, tên ngành)} cho toàn thị trường — 25 request song song."""
    sec = sectors()
    if sec.empty:
        return {}
    codes = list(sec["code"])
    res = {}
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=10) as ex:
            got = list(ex.map(sector_stocks, codes))
    except RuntimeError:
        got = [sector_stocks(c) for c in codes]
    for c, (name, syms) in zip(codes, got):
        for s in syms:
            res.setdefault(s, (c, name))
    return res


ICB2_NAMES = {"0500": "Dầu khí", "1300": "Hoá chất", "1700": "Tài nguyên cơ bản", "2300": "Xây dựng & vật liệu",
              "2700": "Hàng & dịch vụ công nghiệp", "3300": "Ô tô & phụ tùng", "3500": "Thực phẩm & đồ uống",
              "3700": "Hàng cá nhân & gia dụng", "4500": "Y tế", "5300": "Bán lẻ", "5500": "Truyền thông",
              "5700": "Du lịch & giải trí", "6500": "Viễn thông", "7500": "Tiện ích", "8300": "Ngân hàng",
              "8500": "Bảo hiểm", "8600": "Bất động sản", "8700": "Dịch vụ tài chính", "9500": "Công nghệ"}


def parse_icb_map(rows) -> dict:
    out = {}
    for r in rows or []:
        if r.get("type") != "STOCK" or r.get("board") == "DELISTED" or not r.get("icbCode2"):
            continue
        code = str(r["icbCode2"])
        out[r["symbol"]] = ("ICB" + code, ICB2_NAMES.get(code, f"ICB {code}"))
    return out


def icb_map() -> dict:
    """Dự phòng phân ngành theo ICB cấp 2 (Vietcap) — phủ cả UPCOM, nơi bản đồ ngành KBS còn thiếu."""
    try:
        from vn_data import VCI_TRADING
        return parse_icb_map(http_json("GET", f"{VCI_TRADING}/price/symbols/getAll", "VCI", retries=1))
    except Exception:  # noqa: BLE001
        return {}


def peer_metrics(symbols) -> pd.DataFrame:
    """P/E, P/B, ROE, vốn hoá TTM mới nhất của nhóm mã cùng ngành (Vietcap, song song)."""
    def one(sym):
        try:
            j = http_json("GET", f"{VCI_IQ}/company/{sym}/statistics-financial", "VCI", retries=1)
            rows = [r for r in (j.get("data") if isinstance(j, dict) else j) or [] if r.get("year")]
            if not rows:
                return None
            r = sorted(rows, key=lambda x: (int(x["year"]), int(x.get("quarter") or 0)))[-1]
            return dict(symbol=sym, pe=r.get("pe"), pb=r.get("pb"), roe=r.get("roe"),
                        mcap_bn=(r.get("marketCap") or 0) / 1e9, period=f"{r['year']}Q{r.get('quarter')}")
        except Exception:  # noqa: BLE001
            return None
    syms = list(dict.fromkeys(s.upper() for s in symbols if s))
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as ex:
            got = list(ex.map(one, syms))
    except RuntimeError:
        got = [one(s) for s in syms]
    return pd.DataFrame([g for g in got if g])


# ═════════════════════════════ LỊCH ĐẶC THÙ VN ═══════════════════════════════
def derivatives_expiry(day=None):
    """Ngày đáo hạn HĐ tương lai VN30 tháng hiện tại (thứ Năm tuần thứ 3) — phiên thường biến động mạnh."""
    day = day or datetime.now().date()
    first = day.replace(day=1)
    exp = first + timedelta(days=(3 - first.weekday()) % 7 + 14)
    if day > exp:
        nxt = (first + timedelta(days=32)).replace(day=1)
        exp = nxt + timedelta(days=(3 - nxt.weekday()) % 7 + 14)
    return exp
