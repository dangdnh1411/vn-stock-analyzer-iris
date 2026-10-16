"""
swing_setups.py — Thiết lập LƯỚT SÓNG theo dòng tiền & volume (hàm thuần, không gọi mạng).

Hai câu hỏi thực chiến:
  A. "Cổ phiếu xấu nhưng XẢ ĐÃ CẠN — bắt dần được chưa?"
     Chuỗi Wyckoff giản lược, mỗi bước phải có bằng chứng volume:
       1 Xả mạnh   — đã có đợt bán có vol (nguồn cung lộ diện)
       2 Xả cạn    — vol phiên giảm teo lại, biên độ co, không còn đáy mới sâu, tiền không rút thêm
       3 Test cung — giá thử lại đáy trên VOL THẤP và đóng cửa nửa trên (không còn ai muốn bán ở đáy)
       4 Cầu vào   — phiên tăng có vol, đóng cửa cao / vượt đỉnh nền (cầu thật xuất hiện)
       5 Giữ nhịp  — nhịp chỉnh sau đó vol thấp và không thủng nửa thân phiên cầu vào
     Bắt DẦN: mỗi bước xác nhận mới thêm một phần vốn; thủng đáy test có vol = sai, thoát.

  B. "Giá được BƠM lên nhưng có BÊN MUA THẬT không?"
     Giá tăng nóng mà: phiên tăng vol thấp, đóng cửa xa đỉnh phiên, A/D – OBV không đi theo,
     có phiên vol lớn giá không tiến, thanh khoản mỏng, giá xa VWAP; trong phiên bán chủ động áp đảo,
     lệnh lớn bán ròng, kéo ATC, khối ngoại/tự doanh bán vào lực kéo → tiền lớn đang XẢ cho người mua đuổi.

Mọi ngưỡng là quy tắc kinh nghiệm, không phải chân lý — hàm `setup_history` đo lại chính các tín hiệu này
trên lịch sử của mã để biết chúng có từng hiệu quả hay không.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ROUND_TRIP_COST = 0.004          # phí mua 0.15% + phí bán 0.15% + thuế 0.1%

STAGES = ["Chưa có", "Xả cạn", "Test cung", "Cầu vào", "Giữ nhịp"]
STAGE_NOTE = {
    0: "Chưa hình thành chuỗi xả cạn — đứng ngoài, chưa có gì để bắt.",
    1: "Vol bán đã teo nhưng chưa có phiên test đáy. Theo dõi, CHƯA mua.",
    2: "Đã test đáy trên vol thấp và giữ được — có thể mua phần 1 (thăm dò), cắt lỗ ngay dưới đáy test.",
    3: "Cầu thật đã vào (phiên tăng có vol). Có thể mua phần 2 nếu đã có phần 1, hoặc mua phần 1 nếu chưa vào.",
    4: "Nhịp chỉnh sau phiên cầu vào giữ được trên vol thấp — điểm mua phần 3 an toàn nhất, dời cắt lỗ lên.",
}


def _num(s):
    return pd.to_numeric(s, errors="coerce")


# ═════════════════════════════ A. XẢ CẠN → BẮT DẦN ════════════════════════════
def exhaustion_series(d: pd.DataFrame) -> pd.DataFrame:
    """d = output của flow_analysis.money_flow(classify_sessions(session_features(px))).
    Trả thêm các cột điều kiện theo TỪNG PHIÊN để dùng cho hiện tại lẫn kiểm định lịch sử."""
    x = d.copy()
    c, h, l, v = x["Close"], x["High"], x["Low"], x["Volume"]
    ev = x["event"].fillna("")
    x["ret60"] = c.pct_change(60) * 100
    x["dd120"] = c / h.rolling(120, min_periods=40).max() - 1
    # Bối cảnh "xấu": dưới EMA50 và đã giảm sâu (60 phiên −15% hoặc cách đỉnh 120 phiên −25%)
    x["weak_ctx"] = (c < x["ema50"]) & ((x["ret60"] <= -15) | (x["dd120"] <= -0.25))
    x["weak_recent"] = x["weak_ctx"].astype(int).rolling(20, min_periods=1).max().astype(bool)
    # 1) Đã có đợt xả mạnh trong 40 phiên
    vol60_prev = v.rolling(60, min_periods=30).mean().shift(1)
    heavy = ev.isin(["distribution", "sell_climax"]) | ((x["ret"] <= -2) & (v >= 1.4 * vol60_prev))
    x["sell_wave"] = heavy.astype(int).rolling(40, min_periods=1).max().astype(bool)
    x["last_climax_low"] = l.where(heavy).ffill(limit=40)
    # 2) Năm điều kiện XẢ CẠN
    vol60 = v.rolling(60, min_periods=30).mean()
    x["dry_vol_ratio"] = v.rolling(5, min_periods=3).mean() / vol60
    x["c_dry_vol"] = x["dry_vol_ratio"] <= 0.6
    down = x["ret"] < 0
    x["down_vr8"] = x["vr"].where(down).rolling(8, min_periods=1).mean()
    heavy_down8 = ((x["ret"] <= -2) & (x["vr"] >= 1.3)).astype(int).rolling(8, min_periods=1).sum()
    x["c_down_quiet"] = (x["down_vr8"].fillna(0) <= 0.8) & (heavy_down8 == 0)
    rng = h - l
    x["range_ratio"] = rng.rolling(5, min_periods=3).mean() / rng.rolling(30, min_periods=15).mean()
    x["c_range_tight"] = x["range_ratio"] <= 0.7
    prior_low = l.shift(6).rolling(20, min_periods=10).min()
    x["c_no_new_low"] = l.rolling(6, min_periods=3).min() >= prior_low * 0.97
    px10 = c / c.shift(10) - 1
    x["cmf_chg10"] = x["cmf20"] - x["cmf20"].shift(10)
    x["obv_chg10"] = x["obv"] - x["obv"].shift(10)
    x["c_money_turn"] = (x["cmf_chg10"] >= 0.05) | \
                        ((px10 <= 0.01) & ((x["obv"] - x["obv"].shift(10)) > 0))
    conds = ["c_dry_vol", "c_down_quiet", "c_range_tight", "c_no_new_low", "c_money_turn"]
    x["dry_score"] = x[conds].fillna(False).astype(int).sum(axis=1)
    # 3–4) Test cung, Cầu vào, thủng nền
    x["base_low"] = l.rolling(20, min_periods=10).min().shift(1)
    x["base_high"] = h.rolling(10, min_periods=5).max().shift(1)
    probe = l <= l.rolling(5, min_periods=3).min().shift(1)          # thực sự thử xuống đáy gần
    x["is_test"] = ((probe & (l <= x["base_low"] * 1.02) & (l >= x["base_low"] * 0.97) &
                     (x["vr"] <= 0.9) & (x["clv"] >= 0.5)) |
                    ((l < x["base_low"]) & (c > x["base_low"]) & (x["vr"] < 1.5) & (x["clv"] >= 0.5)) |
                    (ev == "shakeout"))
    x["is_sos"] = (((x["ret"] >= 2.5) & (x["vr"] >= 1.5) & (x["clv"] >= 0.6)) |
                   ((c > x["base_high"]) & (x["vr"] >= 1.3) & (x["clv"] >= 0.5) & (x["ret"] > 0)))
    x["is_breakdown"] = (c < x["base_low"] * 0.99) & (x["vr"] >= 1.3) & (x["ret"] <= -2)
    return x


def run_stage_machine(x: pd.DataFrame) -> pd.DataFrame:
    """Máy trạng thái đi qua từng phiên → giai đoạn 0–4 + nhật ký sự kiện (dùng cả cho lịch sử)."""
    n = len(x)
    stage = np.zeros(n, dtype=int)
    tag = [None] * n
    st, since = 0, 0
    test_low = sos_low = sos_mid = lps_low = sos_vol = None
    ref = {}
    refs = [dict() for _ in range(n)]
    for i in range(n):
        r = x.iloc[i]
        ds = int(r["dry_score"]) if not pd.isna(r["dry_score"]) else 0
        ok_ctx = bool(r["weak_recent"]) and bool(r["sell_wave"])
        since += 1
        if st == 0:
            if ok_ctx and ds >= 3:
                st, since = 1, 0; tag[i] = "dry"
                ref = dict(base_low=float(r["base_low"]) if not pd.isna(r["base_low"]) else float(r["Low"]))
        elif st == 1:
            if bool(r["is_breakdown"]):
                st, since = 0, 0; tag[i] = "fail"; ref = {}
            elif bool(r["is_test"]):
                st, since = 2, 0; tag[i] = "test"; test_low = float(r["Low"])
                ref.update(test_low=test_low, test_date=r["Date"], test_close=float(r["Close"]))
            elif bool(r["is_sos"]) and ds >= 2:
                st, since = 3, 0; tag[i] = "sos"; sos_low = float(r["Low"]); sos_mid = float((r["High"] + r["Low"]) / 2); sos_vol = float(r["Volume"])
                ref.update(test_low=ref.get("base_low"), sos_low=sos_low, sos_mid=sos_mid, sos_date=r["Date"],
                           sos_close=float(r["Close"]))
            elif since > 25 and ds < 2:
                st, since = 0, 0; ref = {}
        elif st == 2:
            if float(r["Close"]) < (test_low or 0) * 0.99 and r["vr"] >= 1.2:
                st, since = 0, 0; tag[i] = "fail"; ref = {}
            elif bool(r["is_sos"]):
                st, since = 3, 0; tag[i] = "sos"; sos_low = float(r["Low"]); sos_mid = float((r["High"] + r["Low"]) / 2); sos_vol = float(r["Volume"])
                ref.update(sos_low=sos_low, sos_mid=sos_mid, sos_date=r["Date"], sos_close=float(r["Close"]))
            elif since > 20:
                st, since = (1 if ds >= 3 else 0), 0
                if st == 0:
                    ref = {}
        elif st == 3:
            if float(r["Close"]) < (sos_low or 0):
                st, since = 0, 0; tag[i] = "fail"; ref = {}
            elif 2 <= since <= 10 and r["ret"] < 0.5 and float(r["Volume"]) <= 0.55 * (sos_vol or 0) \
                    and float(r["Low"]) >= (sos_mid or 0) * 0.99:
                st, since = 4, 0; tag[i] = "lps"; lps_low = float(r["Low"])
                ref.update(lps_low=lps_low, lps_date=r["Date"])
            elif since > 12:
                st, since = 0, 0; ref = {}
        elif st == 4:
            if float(r["Close"]) < (lps_low or 0) * 0.99:
                st, since = 0, 0; tag[i] = "fail"; ref = {}
            elif since > 10:
                st, since = 0, 0; ref = {}
        stage[i] = st
        refs[i] = dict(ref)
    out = x.copy()
    out["stage"] = stage
    out["stage_tag"] = tag
    out["_ref"] = refs
    return out


def _fmt_date(dt):
    return dt.strftime("%d/%m") if hasattr(dt, "strftime") else str(dt)[:10]


def exhaustion_checklist(r: pd.Series) -> list:
    """5 điều kiện xả cạn của phiên mới nhất: (đạt?, tên, bằng chứng)."""
    f = lambda v, p=2: "—" if v is None or pd.isna(v) else f"{v:.{p}f}"  # noqa: E731
    return [
        (bool(r["c_dry_vol"]), "Vol teo lại",
         f"Vol TB 5 phiên = {f(r['dry_vol_ratio'])}× TB 60 phiên (cần ≤ 0.60)"),
        (bool(r["c_down_quiet"]), "Phiên giảm không còn vol",
         f"Vol TB các phiên giảm 8 phiên gần = {f(r['down_vr8'])}× (cần ≤ 0.80), không có phiên giảm ≥2% vol lớn"),
        (bool(r["c_range_tight"]), "Biên độ co hẹp",
         f"Biên độ TB 5 phiên = {f(r['range_ratio'])}× TB 30 phiên (cần ≤ 0.70)"),
        (bool(r["c_no_new_low"]), "Không còn đáy mới sâu",
         "6 phiên gần không thủng đáy 20 phiên trước đó quá 3%"),
        (bool(r["c_money_turn"]), "Tiền ngừng rút",
         f"CMF20 = {f(r['cmf20'])}, thay đổi 10 phiên {f(r['cmf_chg10'])} (cần ≥ +0.05) "
         f"hoặc OBV tăng khi giá đi ngang (OBV 10 phiên {'tăng' if (r['obv_chg10'] or 0) > 0 else 'giảm'})"),
    ]


def plan_tranches(state: dict, price: float, atr: float, capital: float, risk_pct: float,
                  vwap: float | None, ema50: float | None, poc: float | None, max_weight_pct: float = 20.0) -> dict:
    """Kế hoạch mua 3 phần theo giai đoạn. Tổng rủi ro = risk_pct% vốn, chia 30/30/40;
    tổng giá trị cả 3 phần không vượt max_weight_pct% vốn (mã xấu → không dồn tiền)."""
    if not price or price <= 0:
        return {}
    atr = atr if atr and atr > 0 else price * 0.03
    budget = capital * risk_pct / 100
    base_low = state.get("base_low") or price - 2 * atr
    test_low = state.get("test_low") or base_low
    stop1 = min(test_low, base_low) - 0.3 * atr
    sos_close = state.get("sos_close")
    sos_mid = state.get("sos_mid")
    lps_low = state.get("lps_low")
    st = state.get("stage", 0)
    rows = []

    cap_value = capital * max_weight_pct / 100

    def _q(entry, stop, w):
        risk_ps = entry - stop
        if risk_ps <= 0 or entry <= 0:
            return 0, 0.0
        q = min(budget * w / risk_ps, cap_value * w / entry)
        q = int(q // 100 * 100)
        return q, q * risk_ps

    e1 = price if st == 2 else (state.get("test_close") or price)
    q1, r1 = _q(e1, stop1, 0.3)
    rows.append(dict(Phan="1 — Thăm dò", Khi="Có phiên TEST CUNG (vol thấp, đóng cửa nửa trên, giữ đáy)",
                     Gia=e1, CatLo=stop1, KL=q1, RuiRo=r1, TrangThai="Đủ điều kiện" if st >= 2 else "Chờ"))
    e2 = sos_close if sos_close else max(price, (state.get("base_high") or price))
    stop2 = max(stop1, (test_low - 0.3 * atr))
    q2, r2 = _q(e2, stop2, 0.3)
    rows.append(dict(Phan="2 — Gia tăng", Khi="Có phiên CẦU VÀO (tăng ≥2.5% vol ≥1.5× hoặc vượt đỉnh nền 10 phiên)",
                     Gia=e2, CatLo=stop2, KL=q2, RuiRo=r2, TrangThai="Đủ điều kiện" if st >= 3 else "Chờ"))
    e3 = price if st == 4 else (sos_mid or e2)
    stop3 = (lps_low - 0.3 * atr) if lps_low else ((state.get("sos_low") or stop2) - 0.3 * atr)
    q3, r3 = _q(e3, stop3, 0.4)
    rows.append(dict(Phan="3 — Hoàn tất", Khi="Nhịp chỉnh sau cầu vào vol thấp, giữ trên nửa thân phiên cầu vào",
                     Gia=e3, CatLo=stop3, KL=q3, RuiRo=r3, TrangThai="Đủ điều kiện" if st >= 4 else "Chờ"))
    targets = sorted({round(t, -1) for t in (vwap, ema50, poc) if t and t > price * 1.01})
    tp1 = targets[0] if targets else price + 2 * atr
    tp2 = targets[1] if len(targets) > 1 else tp1 + 1.5 * atr
    avg_entry = np.average([e1, e2, e3], weights=[0.3, 0.3, 0.4])
    rr = (tp1 - avg_entry) / max(avg_entry - stop1, 1e-9)
    return dict(rows=rows, tp1=tp1, tp2=tp2, budget=budget, rr=rr, stop_all=stop1)


# ═════════════════════════════ B. BƠM THIẾU CẦU THẬT ══════════════════════════
def pump_series(d: pd.DataFrame) -> pd.DataFrame:
    """Cờ cảnh báo 'bơm không có bên mua thật' theo từng phiên (chỉ dữ liệu giá/khối lượng)."""
    x = d.copy()
    c, v = x["Close"], x["Volume"]
    ev = x["event"].fillna("")
    run5 = c / c.shift(5) - 1
    run10 = c / c.shift(10) - 1
    hot = ((x["ret"] >= 6.5).astype(int).rolling(5, min_periods=1).sum() >= 2)
    x["pump_ctx"] = (run5 >= 0.08) | (run10 >= 0.15) | hot
    up = x["ret"] > 0
    x["up_vr5"] = x["vr"].where(up).rolling(5, min_periods=1).mean()
    x["up_clv5"] = x["clv"].where(up).rolling(5, min_periods=1).mean()
    x["f_lowvol"] = x["up_vr5"] < 1.0
    x["f_weakclose"] = x["up_clv5"] < 0.55
    x["f_ad_div"] = (x["ad"] - x["ad"].shift(5) < 0) & (run5 > 0.03)
    x["f_obv_div"] = (x["obv"] - x["obv"].shift(10) <= 0) & (run10 > 0.05)
    x["f_badevent"] = ev.isin(["upthrust", "churn_top", "pump_dump", "buy_climax"]).astype(int).rolling(10, min_periods=1).sum() >= 1
    x["f_thin"] = (x["value_bn"].rolling(5, min_periods=3).mean() < 3) | (x["val_ma20"] < 2)
    x["f_ext"] = ((c - x["vwap20"]) / x["vwap20"] >= 0.10) | ((c - x["ema20"]) / x["atr"] >= 2.5)
    flags = ["f_lowvol", "f_weakclose", "f_ad_div", "f_obv_div", "f_badevent", "f_thin", "f_ext"]
    x["pump_flags"] = x[flags].fillna(False).astype(int).sum(axis=1)
    # Bằng chứng cầu thật
    x["n_markup5"] = (ev == "markup").astype(int).rolling(5, min_periods=1).sum()
    x["real_demand"] = (x["up_vr5"] >= 1.3) & (x["up_clv5"] >= 0.65)
    return x


PUMP_FLAG_TEXT = {
    "f_lowvol": ("Phiên tăng không cần vol", "Vol TB các phiên tăng 5 phiên = {up_vr5:.2f}× — giá lên vì ít người bán, không phải vì nhiều người mua."),
    "f_weakclose": ("Đóng cửa xa đỉnh phiên", "Vị trí đóng cửa TB các phiên tăng = {up_clv5:.0%} biên độ — bị bán ra trong phiên mỗi khi kéo."),
    "f_ad_div": ("A/D đi xuống khi giá đi lên", "Tích luỹ/phân phối 5 phiên giảm trong lúc giá tăng — tiền thật đang rút ra."),
    "f_obv_div": ("OBV không xác nhận", "Giá tăng >5% trong 10 phiên nhưng OBV không tăng — vol phiên giảm lớn hơn phiên tăng."),
    "f_badevent": ("Có phiên phân phối gần đây", "Trong 10 phiên có rút râu trên / vol lớn giá không tăng / kéo–xả / hưng phấn cực điểm."),
    "f_thin": ("Thanh khoản mỏng", "Giá trị GD TB 5 phiên {val5:.1f} tỷ — mã mỏng rất dễ bị kéo bằng ít tiền và xả khó thoát."),
    "f_ext": ("Giá quá xa giá vốn trung bình", "Giá cách VWAP20 {ext:+.0%} — người mua 20 phiên qua đang lãi lớn, động cơ chốt cao."),
}


def pump_check(x_last: pd.Series, intraday: dict | None = None, foreign=None, prop=None, orders=None,
               session_ret: float | None = None) -> dict:
    """Kết luận cho phiên mới nhất: dữ liệu giá/vol + trong phiên + khối ngoại/tự doanh/sổ lệnh."""
    flags, positives = [], []
    fmt = dict(up_vr5=x_last.get("up_vr5") or 0, up_clv5=x_last.get("up_clv5") or 0,
               val5=float(x_last.get("value_bn") or 0),
               ext=((x_last["Close"] - x_last["vwap20"]) / x_last["vwap20"]) if x_last.get("vwap20") else 0)
    for k, (title, why) in PUMP_FLAG_TEXT.items():
        if bool(x_last.get(k)):
            try:
                flags.append((title, why.format(**fmt)))
            except (KeyError, ValueError):
                flags.append((title, why))
    if x_last.get("n_markup5", 0) >= 2:
        positives.append(("Có ≥2 phiên kéo giá có vol trong 5 phiên", "Tiền thật đẩy giá, đóng cửa gần đỉnh."))
    if bool(x_last.get("real_demand")):
        positives.append(("Phiên tăng có vol và đóng cửa cao", f"Vol TB phiên tăng {fmt['up_vr5']:.2f}×, đóng cửa ở {fmt['up_clv5']:.0%} biên độ."))
    if intraday:
        br = intraday.get("buy_ratio")
        if br is not None and session_ret is not None and session_ret > 0 and br < 50:
            flags.append(("Giá tăng nhưng BÁN chủ động áp đảo", f"Phiên gần nhất giá {session_ret:+.1f}% nhưng chỉ {br:.0f}% là mua chủ động — "
                                                             "giá được giữ bằng lệnh đặt sẵn, người bán chủ động xả vào."))
        elif br is not None and br >= 58:
            positives.append(("Mua chủ động áp đảo", f"{br:.0f}% khối lượng là người mua quét lệnh bán."))
        bb, bs = intraday.get("big_buy_bn", 0) or 0, intraday.get("big_sell_bn", 0) or 0
        if bs - bb >= 1 and bs > bb * 1.3:
            flags.append(("Lệnh lớn bán ròng", f"Lệnh ≥{intraday.get('big_thr_bn', 1):.1f} tỷ: bán {bs:,.1f} tỷ vs mua {bb:,.1f} tỷ — tay to đang ra hàng."))
        elif bb - bs >= 1 and bb > bs * 1.3:
            positives.append(("Lệnh lớn mua ròng", f"Mua {bb:,.1f} tỷ vs bán {bs:,.1f} tỷ."))
        atc = intraday.get("atc") or {}
        if atc and atc.get("atc_chg_pct", 0) >= 1:
            flags.append(("Kéo giá phiên ATC", f"Giá ATC cao hơn khớp liên tục cuối {atc['atc_chg_pct']:+.1f}% — làm đẹp giá đóng cửa."))
    for name, df in (("Khối ngoại", foreign), ("Tự doanh", prop)):
        if df is not None and not getattr(df, "empty", True) and "net_val" in df.columns:
            n5 = float(df["net_val"].tail(5).sum())
            if n5 <= -1e9:
                flags.append((f"{name} bán ròng vào lực kéo", f"{n5/1e9:+,.1f} tỷ trong 5 phiên."))
            elif n5 >= 1e9:
                positives.append((f"{name} mua ròng", f"{n5/1e9:+,.1f} tỷ trong 5 phiên."))
    if orders is not None and not getattr(orders, "empty", True):
        ab, as_ = orders["avg_buy"].tail(5).mean(), orders["avg_sell"].tail(5).mean()
        if as_ and not pd.isna(ab) and not pd.isna(as_) and as_ > 0 and ab / as_ <= 0.77:
            flags.append(("Cỡ lệnh bán lớn hơn lệnh mua", f"Lệnh bán TB lớn gấp {as_/ab:.1f} lần lệnh mua — tiền lớn bán, nhỏ lẻ mua."))
    ctx = bool(x_last.get("pump_ctx"))
    nf = len(flags)
    if not ctx:
        level, color, verdict = 0, "#8baed4", "Giá chưa ở trạng thái tăng nóng — kiểm tra này chỉ để tham khảo."
    elif nf >= 5 or (nf >= 4 and len(positives) == 0):
        level, color, verdict = 3, "#ff3d5a", ("BƠM THIẾU CẦU THẬT — giá tăng nhưng dấu vết dòng tiền cho thấy đang có người xả. "
                                              "Không mua đuổi; đang giữ thì chốt dần, dời cắt lỗ sát.")
    elif nf >= 3:
        level, color, verdict = 2, "#f5a623", "CẦU YẾU — tăng chưa được tiền thật xác nhận đầy đủ. Không mua đuổi, chờ nhịp chỉnh vol thấp."
    elif len(positives) >= 2:
        level, color, verdict = 1, "#00d97e", "TĂNG CÓ CẦU THẬT — vol và vị trí đóng cửa xác nhận. Vẫn tránh mua khi giá quá xa VWAP."
    else:
        level, color, verdict = 1, "#7fcf50", "Chưa thấy dấu hiệu bơm rỗng rõ ràng."
    return dict(ctx=ctx, level=level, color=color, verdict=verdict, flags=flags, positives=positives)


# ═════════════════════════════ C. KIỂM CHỨNG TRÊN LỊCH SỬ ═════════════════════
def _forward(x: pd.DataFrame, idx: list, horizons=(5, 10, 20)) -> pd.DataFrame:
    rows = []
    o, c, lo = x["Open"].values, x["Close"].values, x["Low"].values
    n = len(x)
    for i in idx:
        if i + 1 >= n:
            continue
        entry = o[i + 1] if o[i + 1] > 0 else c[i]
        row = {"Ngày": x["Date"].iloc[i], "Giá vào": entry}
        for hh in horizons:
            j = i + hh
            row[f"{hh}p"] = (c[j] / entry - 1 - ROUND_TRIP_COST) * 100 if j < n else np.nan
        j10 = min(i + 10, n - 1)
        row["Sụt sâu nhất 10p"] = (lo[i + 1:j10 + 1].min() / entry - 1) * 100 if j10 > i else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _dedupe(idx, gap=10):
    out, last = [], -10**9
    for i in idx:
        if i - last >= gap:
            out.append(i); last = i
    return out


def _summ(fw: pd.DataFrame, col="10p") -> dict:
    s = fw[col].dropna() if not fw.empty and col in fw else pd.Series(dtype=float)
    if s.empty:
        return dict(n=0)
    return dict(n=int(len(s)), win=float((s > 0).mean() * 100), avg=float(s.mean()), med=float(s.median()),
                worst=float(s.min()), mae=float(fw["Sụt sâu nhất 10p"].dropna().mean()) if "Sụt sâu nhất 10p" in fw else None)


def setup_history(xs: pd.DataFrame, xp: pd.DataFrame) -> dict:
    """Đo lại hiệu quả: sau các lần TEST / CẦU VÀO (trong chuỗi xả cạn) và các lần CẢNH BÁO BƠM,
    giá 5/10/20 phiên sau đi thế nào (đã trừ phí 0.4%)."""
    tags = [t if isinstance(t, str) else None for t in xs["stage_tag"].tolist()]
    test_idx = _dedupe([i for i, t in enumerate(tags) if t == "test"])
    sos_idx = _dedupe([i for i, t in enumerate(tags) if t == "sos"])
    pump_idx = _dedupe([i for i in range(len(xp)) if bool(xp["pump_ctx"].iloc[i]) and xp["pump_flags"].iloc[i] >= 4])
    out = {}
    for key, idx in (("test", test_idx), ("sos", sos_idx), ("pump", pump_idx)):
        fw = _forward(xs if key != "pump" else xp, idx)
        out[key] = dict(table=fw, stats=_summ(fw))
    return out


# ═════════════════════════════ GHÉP LẠI ═══════════════════════════════════════
def analyze_swing(flow_d: pd.DataFrame, intraday=None, foreign=None, prop=None, orders=None, vp=None) -> dict:
    """flow_d = res['d'] từ flow_analysis.analyze_flow (đã có sự kiện + chỉ báo dòng tiền)."""
    if flow_d is None or len(flow_d) < 60:
        return {}
    xs = run_stage_machine(exhaustion_series(flow_d))
    xp = pump_series(flow_d)
    last = xs.iloc[-1]
    stage = int(last["stage"])
    state = dict(last["_ref"] or {})
    state.update(stage=stage, base_high=float(last["base_high"]) if not pd.isna(last["base_high"]) else None)
    if not state.get("base_low"):
        state["base_low"] = float(last["base_low"]) if not pd.isna(last["base_low"]) else None
    # Phiên gần nhất có đóng vai trò gì trong chuỗi?
    recent_tags = [(xs["Date"].iloc[i], t) for i, t in enumerate(xs["stage_tag"].tolist()[-30:], start=len(xs) - 30)
                   if isinstance(t, str)]
    pc = pump_check(xp.iloc[-1], intraday, foreign, prop, orders, session_ret=float(last["ret"]) if not pd.isna(last["ret"]) else None)
    # Cộng điểm xác nhận cầu chủ động cho chuỗi bắt đáy
    confirms = []
    if intraday:
        br = intraday.get("buy_ratio")
        if br is not None and br >= 55:
            confirms.append(f"Mua chủ động {br:.0f}% phiên gần nhất")
        if (intraday.get("big_buy_bn") or 0) - (intraday.get("big_sell_bn") or 0) >= 1:
            confirms.append("Lệnh lớn mua ròng trong phiên")
    if foreign is not None and not getattr(foreign, "empty", True) and float(foreign["net_val"].tail(5).sum()) > 0:
        confirms.append("Khối ngoại mua ròng 5 phiên")
    if orders is not None and not getattr(orders, "empty", True):
        ab, as_ = orders["avg_buy"].tail(5).mean(), orders["avg_sell"].tail(5).mean()
        if as_ and not pd.isna(ab) and ab / as_ >= 1.3:
            confirms.append("Cỡ lệnh mua TB lớn hơn lệnh bán ≥1.3 lần")
    return dict(xs=xs, xp=xp, stage=stage, stage_name=STAGES[stage], stage_note=STAGE_NOTE[stage], state=state,
                weak_ctx=bool(last["weak_recent"]), sell_wave=bool(last["sell_wave"]), dry_score=int(last["dry_score"]),
                checklist=exhaustion_checklist(last), recent_tags=recent_tags, confirms=confirms,
                pump=pc, history=setup_history(xs, xp), vp=vp)


TAG_INFO = {
    "dry": ("🌵 Bắt đầu xả cạn", "#22d3ee"),
    "test": ("🧪 Test cung thành công", "#22d3ee"),
    "sos": ("⭐ Cầu vào", "#00d97e"),
    "lps": ("🪜 Giữ nhịp chỉnh", "#00d97e"),
    "fail": ("✖ Thất bại — thủng nền", "#ff3d5a"),
}
