"""
journal.py — Nhật ký lệnh: lưu trữ + tính toán vị thế + cảnh báo + thống kê kỷ luật.

Vì sao cần: điểm yếu lớn nhất của nhà đầu tư cá nhân không nằm ở chọn mã mà ở KỶ LUẬT —
giữ lệnh lỗ quá lâu, chốt lời quá sớm (disposition effect), không đặt/không tôn trọng cắt lỗ.
Nhật ký biến những thói quen đó thành CON SỐ để tự soi.

Lưu trữ (theo thứ tự ưu tiên):
  1. GitHub (repo RIÊNG TƯ) — bền vững, miễn phí. Cần Secrets: GITHUB_TOKEN, JOURNAL_REPO.
  2. File trên máy chủ Streamlit — mất khi app ngủ/khởi động lại → luôn có nút tải/khôi phục JSON.
Bảo mật: app công khai trên Internet → bắt buộc JOURNAL_PIN để mở nhật ký khi lưu trên máy chủ.
"""
from __future__ import annotations

import base64
import json
import math
import os
import uuid
from datetime import date, datetime

import pandas as pd

BUY_FEE = 0.0015        # phí mua (môi giới online phổ biến)
SELL_FEE = 0.0025       # phí bán 0.15% + thuế TNCN 0.1%
SETUPS = ["Breakout nền giá", "Pullback về hỗ trợ/MA", "Bắt đáy", "Đầu tư cơ bản dài hạn", "Theo tin/sự kiện", "Khác"]
EXIT_REASONS = ["Chạm cắt lỗ", "Chốt lời theo kế hoạch", "Tín hiệu thoát (kỹ thuật/quant)",
                "Cắt lỗ chủ động (trước SL)", "Cần tiền/cơ cấu danh mục", "Khác"]
FIELDS = ["id", "symbol", "open_date", "entry", "qty", "stop", "initial_stop", "target", "setup", "reason",
          "status", "close_date", "exit", "exit_reason", "notes", "updated_at"]


# ═════════════════════════════ LƯU TRỮ ════════════════════════════════════════
class GitHubStore:
    """Đọc/ghi 1 file JSON trong repo GitHub (nên để repo RIÊNG TƯ) qua Contents API."""
    def __init__(self, token, repo, path="journal.json", branch=None):
        self.token, self.repo, self.path, self.branch = token, repo, path, branch
        self.sha = None
        self.label = f"GitHub · {repo}/{path}"

    def _h(self):
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28"}

    def load(self):
        import requests
        params = {"ref": self.branch} if self.branch else {}
        r = requests.get(f"https://api.github.com/repos/{self.repo}/contents/{self.path}",
                         headers=self._h(), params=params, timeout=12)
        if r.status_code == 404:
            self.sha = None
            return []
        r.raise_for_status()
        j = r.json(); self.sha = j.get("sha")
        return json.loads(base64.b64decode(j["content"]).decode("utf-8") or "[]")

    def save(self, trades, msg="Cập nhật nhật ký lệnh"):
        import requests
        body = {"message": msg, "content": base64.b64encode(
            json.dumps(trades, ensure_ascii=False, indent=1).encode("utf-8")).decode()}
        if self.sha:
            body["sha"] = self.sha
        if self.branch:
            body["branch"] = self.branch
        r = requests.put(f"https://api.github.com/repos/{self.repo}/contents/{self.path}",
                         headers=self._h(), json=body, timeout=15)
        if r.status_code == 409:   # có thay đổi ở nơi khác → đọc lại sha rồi ghi
            self.load(); body["sha"] = self.sha
            r = requests.put(f"https://api.github.com/repos/{self.repo}/contents/{self.path}",
                             headers=self._h(), json=body, timeout=15)
        r.raise_for_status()
        self.sha = r.json()["content"]["sha"]


class FileStore:
    def __init__(self, path="journal_data.json"):
        self.path = path
        self.label = "File trên máy chủ (TẠM — mất khi app khởi động lại, hãy tải bản sao lưu)"

    def load(self):
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def save(self, trades, msg=None):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(trades, f, ensure_ascii=False, indent=1)


def new_trade(symbol, open_date, entry, qty, stop, target=None, setup="Khác", reason="", notes=""):
    return {"id": uuid.uuid4().hex[:10], "symbol": symbol.upper().strip(), "open_date": str(open_date),
            "entry": float(entry), "qty": int(qty), "stop": float(stop) if stop else None,
            "initial_stop": float(stop) if stop else None, "target": float(target) if target else None,
            "setup": setup, "reason": reason, "status": "OPEN", "close_date": None, "exit": None,
            "exit_reason": None, "notes": notes, "updated_at": datetime.now().isoformat(timespec="seconds")}


def _ok(v):
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def _bdays(a, b):
    try:
        return int(len(pd.bdate_range(pd.to_datetime(a), pd.to_datetime(b))) - 1)
    except Exception:  # noqa: BLE001
        return None


# ═════════════════════════════ VỊ THẾ ĐANG MỞ ════════════════════════════════
def open_positions(trades, prices: dict, atr: dict | None = None, hi22: dict | None = None,
                   today=None, avg_win_days=None) -> pd.DataFrame:
    """prices: {mã: giá hiện tại}; atr/hi22: {mã: ATR14 / đỉnh 22 phiên} để gợi ý dời cắt lỗ."""
    today = today or date.today()
    rows = []
    for t in trades:
        if t.get("status") != "OPEN":
            continue
        sym, e, q = t["symbol"], float(t["entry"]), int(t["qty"])
        px = prices.get(sym)
        sl = t.get("stop"); isl = t.get("initial_stop") or sl
        risk_ps = e - isl if _ok(isl) and isl < e else None
        pnl_pct = (px / e - 1) * 100 if px else None
        pnl = (px * (1 - SELL_FEE) - e * (1 + BUY_FEE)) * q if px else None
        r_mult = (px - e) / risk_ps if px and risk_ps else None
        days = _bdays(t["open_date"], today)
        flags = []
        if not _ok(sl):
            flags.append("❗ CHƯA ĐẶT CẮT LỖ")
        elif px and px <= sl:
            flags.append("🛑 ĐÃ THỦNG CẮT LỖ — thoát theo kế hoạch")
        elif px and (px / sl - 1) * 100 <= 2:
            flags.append("⚠️ Sát điểm cắt lỗ (<2%)")
        if pnl_pct is not None and pnl_pct < 0 and days is not None:
            lim = max(10, int((avg_win_days or 10) * 1.5))
            if days >= lim:
                flags.append(f"⏳ Lỗ đã {days} phiên — giữ lệnh lỗ lâu hơn ngưỡng {lim} phiên")
        if r_mult is not None and r_mult <= -1.2 and _ok(sl) and px and px > sl:
            flags.append("🔻 Lỗ vượt 1R nhưng chưa chạm SL — cắt lỗ đã bị dời xa?")
        if days is not None and days < 2:
            flags.append("📦 Chưa về tài khoản (T+2.5)")
        sug = None
        if r_mult is not None and r_mult >= 1 and _ok(sl) and sl < e:
            sug = f"Dời cắt lỗ lên giá vốn {e:,.0f} (đã lãi ≥1R)"
        if r_mult is not None and r_mult >= 2 and atr and hi22 and sym in atr and sym in hi22:
            ch = hi22[sym] - 3 * atr[sym]
            if ch > (sl or 0):
                sug = f"Dời cắt lỗ theo Chandelier: {ch:,.0f} (đỉnh 22 phiên − 3×ATR)"
        if t.get("target") and px and px >= t["target"]:
            flags.append("🎯 Đã chạm mục tiêu")
        rows.append({"id": t["id"], "Mã": sym, "Ngày mua": t["open_date"], "Giá vốn": e, "KL": q,
                     "Giá hiện tại": px, "Lãi/lỗ %": pnl_pct, "Lãi/lỗ (đ, sau phí)": pnl, "R": r_mult,
                     "Cắt lỗ": sl, "Mục tiêu": t.get("target"), "Số phiên giữ": days,
                     "Cảnh báo": " · ".join(flags) if flags else "✅ Trong kế hoạch",
                     "Gợi ý": sug or "", "Chiến lược": t.get("setup"), "_alert": bool([f for f in flags if f[0] in "🛑❗⏳🔻⚠"])})
    return pd.DataFrame(rows)


# ═════════════════════════════ THỐNG KÊ LỆNH ĐÃ ĐÓNG ═════════════════════════
def closed_df(trades) -> pd.DataFrame:
    rows = []
    for t in trades:
        if t.get("status") != "CLOSED" or not _ok(t.get("exit")):
            continue
        e, x, q = float(t["entry"]), float(t["exit"]), int(t["qty"])
        isl = t.get("initial_stop")
        risk_ps = e - isl if _ok(isl) and isl < e else None
        net_ret = (x * (1 - SELL_FEE)) / (e * (1 + BUY_FEE)) - 1
        rows.append({"id": t["id"], "Mã": t["symbol"], "Ngày mua": t["open_date"], "Ngày bán": t["close_date"],
                     "Giá vốn": e, "Giá bán": x, "KL": q, "Lãi/lỗ %": net_ret * 100,
                     "Lãi/lỗ (đ)": (x * (1 - SELL_FEE) - e * (1 + BUY_FEE)) * q,
                     "R": (x - e) / risk_ps if risk_ps else None,
                     "Số phiên giữ": _bdays(t["open_date"], t["close_date"]),
                     "Chiến lược": t.get("setup"), "Lý do thoát": t.get("exit_reason")})
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("Ngày bán").reset_index(drop=True)
    return df


def stats(trades) -> dict:
    df = closed_df(trades)
    if df.empty:
        return {}
    win = df[df["Lãi/lỗ (đ)"] > 0]; loss = df[df["Lãi/lỗ (đ)"] <= 0]
    n = len(df); wr = len(win) / n
    aw = win["Lãi/lỗ %"].mean() if len(win) else 0.0
    al = abs(loss["Lãi/lỗ %"].mean()) if len(loss) else 0.0
    pf = win["Lãi/lỗ (đ)"].sum() / abs(loss["Lãi/lỗ (đ)"].sum()) if len(loss) and loss["Lãi/lỗ (đ)"].sum() != 0 else None
    exp_pct = wr * aw - (1 - wr) * al
    rr = df["R"].dropna()
    exp_r = float(rr.mean()) if len(rr) else None
    payoff = aw / al if al else None
    kelly = (wr - (1 - wr) / payoff) if payoff else None
    eq = df["Lãi/lỗ (đ)"].cumsum()
    dd = float((eq - eq.cummax()).min())
    # chuỗi thua dài nhất
    streak = mx = 0
    for v in df["Lãi/lỗ (đ)"]:
        streak = streak + 1 if v <= 0 else 0; mx = max(mx, streak)
    dw = win["Số phiên giữ"].mean() if len(win) else None
    dl = loss["Số phiên giữ"].mean() if len(loss) else None
    # Kỷ luật: lệnh lỗ vượt quá rủi ro dự kiến (R < −1.2) = không tôn trọng cắt lỗ
    over = int((rr < -1.2).sum()); n_loss_r = int((rr <= 0).sum())
    by_setup = df.groupby("Chiến lược").agg(Lệnh=("id", "count"),
                                            Thắng=("Lãi/lỗ (đ)", lambda s: f"{(s > 0).mean()*100:.0f}%"),
                                            TB_lãi_lỗ_pct=("Lãi/lỗ %", "mean"),
                                            Tổng_lãi_lỗ=("Lãi/lỗ (đ)", "sum")).reset_index()
    insights = []
    if dw and dl and dl > dw * 1.3:
        insights.append(("bad", f"Giữ lệnh LỖ trung bình {dl:.0f} phiên, lệnh LÃI chỉ {dw:.0f} phiên — "
                                "đúng mẫu 'gồng lỗ, chốt non' (disposition effect). Đây là thói quen bào mòn tài khoản nhiều nhất."))
    if n_loss_r and over / n_loss_r >= 0.3:
        insights.append(("bad", f"{over}/{n_loss_r} lệnh lỗ vượt quá 1.2R — cắt lỗ thường không được tôn trọng. "
                                "Lỗ thực tế lớn hơn kế hoạch làm sai mọi tính toán tỷ trọng."))
    if payoff and payoff < 1 and wr < 0.6:
        insights.append(("bad", f"Lãi TB/lỗ TB = {payoff:.2f} < 1 với tỷ lệ thắng {wr*100:.0f}% — kỳ vọng âm. "
                                "Cần để lệnh lãi chạy dài hơn hoặc cắt lỗ sớm hơn."))
    if exp_pct > 0 and pf and pf >= 1.5:
        insights.append(("good", f"Hệ thống đang có lợi thế: Profit factor {pf:.2f}, kỳ vọng {exp_pct:+.2f}%/lệnh."))
    if n < 20:
        insights.append(("info", f"Mới có {n} lệnh đóng — cần ≥20-30 lệnh để các con số có ý nghĩa thống kê."))
    return dict(n=n, win_rate=wr * 100, avg_win=aw, avg_loss=al, payoff=payoff, profit_factor=pf,
                expectancy_pct=exp_pct, expectancy_r=exp_r, kelly=kelly * 100 if kelly is not None else None,
                total_pnl=float(df["Lãi/lỗ (đ)"].sum()), max_dd=dd, max_loss_streak=mx,
                hold_win=dw, hold_loss=dl, over_risk=over, equity=eq, df=df, by_setup=by_setup, insights=insights)


def position_size(capital, risk_pct, entry, stop, max_weight_pct=25, lot=100):
    """Khối lượng sao cho nếu chạm cắt lỗ chỉ mất risk_pct% vốn; làm tròn lô 100, trần tỷ trọng."""
    if not (capital and entry and stop) or stop >= entry:
        return None
    risk_ps = entry * (1 + BUY_FEE) - stop * (1 - SELL_FEE)
    q = capital * risk_pct / 100 / risk_ps
    q = min(q, capital * max_weight_pct / 100 / entry)
    q = int(q // lot * lot)
    return dict(qty=q, value=q * entry, risk=q * risk_ps, weight=q * entry / capital * 100,
                risk_pct_real=q * risk_ps / capital * 100)


def to_csv(trades) -> bytes:
    return pd.DataFrame(trades, columns=FIELDS).to_csv(index=False).encode("utf-8-sig")
