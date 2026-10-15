"""
flow_analysis.py — Phân tích DÒNG TIỀN & VOLUME (hàm thuần, không gọi mạng).

Câu hỏi cần trả lời: tiền lớn đang GOM hay XẢ? Phiên nào là phiên kéo giá thật, phiên nào
vol lớn nhưng giá không đi (chuyển tay/phân phối), phiên nào cạn cung, phiên nào rũ bỏ?

Nguyên tắc đọc volume (VSA/Wyckoff, điều chỉnh cho VN):
  • Nỗ lực (volume) phải tương xứng kết quả (biên độ giá). Vol lớn + giá không đi = có người
    đang bán ra cho bên mua (ở vùng cao) hoặc gom hàng bên bán (ở vùng thấp).
  • Vị trí quyết định ý nghĩa: cùng một cây nến vol lớn, ở đỉnh là phân phối, ở đáy là hấp thụ.
  • Đặc thù VN: biên độ HOSE ±7%; hàng mua về tài khoản chiều T+2 → áp lực chốt lời
    thường xuất hiện 2-3 phiên sau phiên kéo vol lớn; phiên ATC dễ bị "kéo/đạp" chỉ số.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

# ═════════════════════════════ ĐẶC TRƯNG TỪNG PHIÊN ═══════════════════════════
def session_features(df: pd.DataFrame) -> pd.DataFrame:
    """df: Date, Open, High, Low, Close, Volume (đồng). Trả thêm các cột đặc trưng."""
    d = df.copy().reset_index(drop=True)
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["ret"] = d["Close"].pct_change() * 100
    d["value_bn"] = d["Close"] * d["Volume"] / 1e9
    d["vol_ma20"] = d["Volume"].rolling(20, min_periods=10).mean().shift(1)   # so với 20 phiên TRƯỚC
    d["vr"] = d["Volume"] / d["vol_ma20"]
    rng = (d["High"] - d["Low"]).replace(0, np.nan)
    d["clv"] = ((d["Close"] - d["Low"]) / rng).fillna(0.5)                 # 1 = đóng cửa ở đỉnh phiên
    d["upper_wick"] = ((d["High"] - d[["Open", "Close"]].max(axis=1)) / rng).fillna(0)
    d["lower_wick"] = ((d[["Open", "Close"]].min(axis=1) - d["Low"]) / rng).fillna(0)
    tr = pd.concat([d["High"] - d["Low"], (d["High"] - d["Close"].shift()).abs(),
                    (d["Low"] - d["Close"].shift()).abs()], axis=1).max(axis=1)
    d["atr"] = tr.rolling(14, min_periods=5).mean()
    d["range_atr"] = (d["High"] - d["Low"]) / d["atr"]
    hi60 = d["High"].rolling(60, min_periods=20).max(); lo60 = d["Low"].rolling(60, min_periods=20).min()
    d["pos60"] = ((d["Close"] - lo60) / (hi60 - lo60)).clip(0, 1)            # 0 = đáy 60 phiên, 1 = đỉnh
    d["ret20"] = d["Close"].pct_change(20) * 100
    d["ema20"] = d["Close"].ewm(span=20, adjust=False).mean()
    d["ema50"] = d["Close"].ewm(span=50, adjust=False).mean()
    d["low20_prev"] = d["Low"].rolling(20, min_periods=10).min().shift(1)
    return d


# ═════════════════════════════ PHÂN LOẠI PHIÊN ════════════════════════════════
# (mã, nhãn, hướng: +1 tích cực / -1 tiêu cực / 0 trung tính, ý nghĩa)
EVENT_INFO = {
    "markup":       ("🚀 Kéo giá có dòng tiền", +1,
                     "Giá tăng mạnh, vol vượt trung bình, đóng cửa gần đỉnh phiên — tiền thật đẩy giá, bên bán yếu."),
    "weak_rally":   ("🎈 Tăng giá thiếu vol", -1,
                     "Giá tăng nhưng vol thấp hơn trung bình — thiếu lực cầu thật, dễ là nhịp hồi kỹ thuật/bẫy."),
    "churn_top":    ("⚠️ Vol lớn – giá không tăng (vùng cao)", -1,
                     "Vol gấp đôi bình thường nhưng giá đứng/đóng cửa thấp, ở vùng cao 60 phiên — dấu hiệu PHÂN PHỐI: "
                     "có người bán lớn cho đám đông mua đuổi."),
    "churn":        ("🔁 Vol lớn – giá không đi", 0,
                     "Nỗ lực lớn nhưng kết quả nhỏ — hàng đang chuyển tay mạnh. Theo dõi phiên kế tiếp để xác định ai thắng."),
    "upthrust":     ("🪤 Rút râu trên vol lớn", -1,
                     "Giá vọt lên rồi bị đạp xuống (râu trên dài) với vol lớn — cung chặn ở trên, thường là bẫy tăng giá."),
    "distribution": ("🔻 Bán ra có vol", -1,
                     "Giá giảm ≥2% với vol vượt trung bình — áp lực bán chủ động của tiền lớn."),
    "shakeout":     ("🧲 Rũ bỏ / hấp thụ", +1,
                     "Giá bị đạp thủng đáy gần rồi kéo lên đóng cửa cao (râu dưới dài) với vol lớn — "
                     "lực cầu hấp thụ hết hàng bán tháo."),
    "no_supply":    ("🌵 Cạn cung", +1,
                     "Phiên giảm nhẹ, biên độ hẹp, vol rất thấp trong xu hướng tăng — người nắm giữ không muốn bán, "
                     "điều kiện tốt cho nhịp tăng tiếp."),
    "sell_climax":  ("💥 Bán tháo cực điểm", 0,
                     "Giảm mạnh với vol bùng nổ sau chuỗi giảm sâu — hoảng loạn; thường gần đáy ngắn hạn nhưng CẦN "
                     "phiên xác nhận (không thủng đáy này) trước khi mua."),
    "buy_climax":   ("🔥 Hưng phấn cực điểm", -1,
                     "Tăng mạnh với vol bùng nổ sau khi đã tăng nóng — đám đông FOMO, tiền lớn thường tranh thủ chốt."),
    "pump_dump":    ("🎭 Kéo – xả", -1,
                     "Phiên kéo vol lớn bị xoá trong ≤3 phiên sau đó, kèm vol lớn — mẫu hình kéo lên để xả hàng."),
}


def classify_sessions(d: pd.DataFrame) -> pd.DataFrame:
    """Gắn nhãn sự kiện cho từng phiên (mỗi phiên tối đa 1 nhãn — ưu tiên nhãn đặc biệt hơn)."""
    ev = pd.Series([None] * len(d), index=d.index, dtype=object)
    vr, ret, clv, pos = d["vr"], d["ret"], d["clv"], d["pos60"]
    for i in d.index:
        if pd.isna(vr[i]) or pd.isna(ret[i]):
            continue
        r, v, c, p = ret[i], vr[i], clv[i], pos[i] if not pd.isna(pos[i]) else 0.5
        tag = None
        if r <= -4 and v >= 2.5 and (d.at[i, "ret20"] <= -12 if not pd.isna(d.at[i, "ret20"]) else False):
            tag = "sell_climax"
        elif r >= 4 and v >= 2.5 and ((d.at[i, "ret20"] >= 20 if not pd.isna(d.at[i, "ret20"]) else False) or p >= 0.95):
            tag = "buy_climax"
        elif v >= 1.5 and d.at[i, "upper_wick"] >= 0.55 and c <= 0.4 and p >= 0.6:
            tag = "upthrust"
        elif v >= 1.3 and d.at[i, "lower_wick"] >= 0.5 and c >= 0.6 and \
                (not pd.isna(d.at[i, "low20_prev"]) and d.at[i, "Low"] <= d.at[i, "low20_prev"] * 1.01 or r > 0):
            tag = "shakeout"
        elif v >= 2.0 and -1.0 <= r <= 1.0:
            tag = "churn_top" if p >= 0.7 else "churn"
        elif r >= 2 and v >= 1.5 and c >= 0.65:
            tag = "markup"
        elif r <= -2 and v >= 1.5:
            tag = "distribution"
        elif r >= 2 and v < 0.8:
            tag = "weak_rally"
        elif -2 < r <= 0 and v <= 0.6 and (d.at[i, "range_atr"] <= 0.8 if not pd.isna(d.at[i, "range_atr"]) else False) \
                and d.at[i, "Close"] >= d.at[i, "ema50"]:
            tag = "no_supply"
        ev[i] = tag
    # Kéo – xả: phiên kéo vol lớn bị đóng cửa dưới giá mở cửa của nó trong 3 phiên kế, có vol
    for i in d.index:
        if ev[i] in ("markup", "buy_climax") and d.at[i, "vr"] >= 2:
            for j in range(i + 1, min(i + 4, len(d))):
                if d.at[j, "Close"] < d.at[i, "Open"] and (d.at[j, "vr"] or 0) >= 1.3:
                    ev[i] = "pump_dump"
                    break
    out = d.copy()
    out["event"] = ev
    return out


def event_table(d: pd.DataFrame, last_n: int = 60) -> pd.DataFrame:
    sub = d.tail(last_n)
    sub = sub[sub["event"].notna()]
    rows = []
    for _, r in sub.iterrows():
        lab, bias, mean = EVENT_INFO[r["event"]]
        rows.append({"Ngày": r["Date"].strftime("%d/%m/%Y") if hasattr(r["Date"], "strftime") else str(r["Date"])[:10],
                     "Tín hiệu": lab, "% giá": round(r["ret"], 2), "Vol / TB20": round(r["vr"], 2),
                     "Giá trị (tỷ)": round(r["value_bn"], 1), "Vị trí 60 phiên": f"{r['pos60']*100:.0f}%" if not pd.isna(r["pos60"]) else "—",
                     "Ý nghĩa": mean, "_bias": bias, "_code": r["event"]})
    return pd.DataFrame(rows[::-1])


# ═════════════════════════════ CHỈ BÁO DÒNG TIỀN ══════════════════════════════
def money_flow(d: pd.DataFrame) -> pd.DataFrame:
    x = d.copy()
    sign = np.sign(x["Close"].diff()).fillna(0)
    x["obv"] = (sign * x["Volume"]).cumsum()
    mfm = ((x["Close"] - x["Low"]) - (x["High"] - x["Close"])) / (x["High"] - x["Low"]).replace(0, np.nan)
    mfv = mfm.fillna(0) * x["Volume"]
    x["ad"] = mfv.cumsum()
    x["cmf20"] = mfv.rolling(20, min_periods=10).sum() / x["Volume"].rolling(20, min_periods=10).sum()
    tp = (x["High"] + x["Low"] + x["Close"]) / 3
    rmf = tp * x["Volume"]
    pos = rmf.where(tp > tp.shift(), 0).rolling(14, min_periods=7).sum()
    neg = rmf.where(tp < tp.shift(), 0).rolling(14, min_periods=7).sum()
    x["mfi14"] = 100 - 100 / (1 + pos / neg.replace(0, np.nan))
    x["vwap20"] = rmf.rolling(20, min_periods=10).sum() / x["Volume"].rolling(20, min_periods=10).sum()
    x["val_ma20"] = x["value_bn"].rolling(20, min_periods=10).mean()
    x["val_ma60"] = x["value_bn"].rolling(60, min_periods=20).mean()
    return x


def _slope(s: pd.Series, n: int):
    s = s.dropna().tail(n)
    if len(s) < max(5, n // 2):
        return None
    y = s.values.astype(float); xx = np.arange(len(y))
    sd = np.std(y)
    if sd == 0:
        return 0.0
    return float(np.polyfit(xx, (y - y.mean()) / sd, 1)[0] * len(y))   # thay đổi chuẩn hoá trên cửa sổ


def volume_profile(d: pd.DataFrame, n: int = 120, bins: int = 24) -> dict:
    """Phân bổ khối lượng theo vùng giá (n phiên gần nhất). POC = vùng giá khớp nhiều nhất — hỗ trợ/
    kháng cự mạnh; Value Area = vùng chứa 70% khối lượng."""
    sub = d.tail(n)
    if len(sub) < 20:
        return {}
    lo, hi = float(sub["Low"].min()), float(sub["High"].max())
    if hi <= lo:
        return {}
    edges = np.linspace(lo, hi, bins + 1)
    vol = np.zeros(bins)
    for _, r in sub.iterrows():
        a, b = float(r["Low"]), float(r["High"])
        if b <= a:
            k = min(np.searchsorted(edges, a, side="right") - 1, bins - 1); vol[max(k, 0)] += r["Volume"]; continue
        for k in range(bins):
            ov = max(0.0, min(b, edges[k + 1]) - max(a, edges[k]))
            if ov > 0:
                vol[k] += r["Volume"] * ov / (b - a)
    mids = (edges[:-1] + edges[1:]) / 2
    poc_i = int(vol.argmax())
    order = np.argsort(vol)[::-1]; acc = 0; tot = vol.sum(); va = []
    for k in order:
        va.append(k); acc += vol[k]
        if acc >= 0.7 * tot:
            break
    return dict(mids=mids.tolist(), vol=vol.tolist(), poc=float(mids[poc_i]),
                va_low=float(edges[min(va)]), va_high=float(edges[max(va) + 1]), n=len(sub))


# ═════════════════════════════ PHÂN TÍCH TRONG PHIÊN (TICK) ═══════════════════
def intraday_analysis(ticks: pd.DataFrame, big_value_bn: float | None = None) -> dict:
    """Mua/bán CHỦ ĐỘNG, lệnh lớn, phân bổ theo thời gian, hiệu ứng ATC — phiên gần nhất."""
    if ticks is None or ticks.empty:
        return {}
    t = ticks.copy()
    tot_v = float(t["vol"].sum()); tot_val = float(t["value"].sum())
    by = t.groupby("side")["vol"].sum().to_dict(); byv = t.groupby("side")["value"].sum().to_dict()
    buy, sell = by.get("Mua chủ động", 0.0), by.get("Bán chủ động", 0.0)
    # Lệnh lớn: ≥ max(1 tỷ, phân vị 99 giá trị lệnh) — "tiền to"
    thr = big_value_bn * 1e9 if big_value_bn else max(1e9, float(t["value"].quantile(0.99)))
    big = t[t["value"] >= thr]
    bb = float(big.loc[big["side"] == "Mua chủ động", "value"].sum())
    bs = float(big.loc[big["side"] == "Bán chủ động", "value"].sum())
    # Delta tích luỹ theo thời gian
    t["delta"] = np.where(t["side"] == "Mua chủ động", t["vol"], np.where(t["side"] == "Bán chủ động", -t["vol"], 0))
    t["cum_delta"] = t["delta"].cumsum()
    # ATC: so giá khớp ATC với lệnh liên tục cuối cùng trước 14:30
    atc = t[(t["time"].dt.hour == 14) & (t["time"].dt.minute >= 30) & (t["side"] == "ATO/ATC")]
    cont = t[(t["time"].dt.hour < 14) | ((t["time"].dt.hour == 14) & (t["time"].dt.minute < 30))]
    cont = cont[cont["side"] != "ATO/ATC"]
    atc_info = {}
    if not atc.empty and not cont.empty:
        p_last, p_atc = float(cont["price"].iloc[-1]), float(atc["price"].iloc[-1])
        atc_info = dict(last_continuous=p_last, atc_price=p_atc, atc_chg_pct=(p_atc / p_last - 1) * 100,
                        atc_vol_share=float(atc["vol"].sum()) / tot_v * 100 if tot_v else 0)
    # Phân bổ theo khung giờ
    t["slot"] = t["time"].dt.strftime("%H:") + (t["time"].dt.minute // 30 * 30).astype(str).str.zfill(2)
    prof = t.groupby(["slot", "side"])["vol"].sum().unstack(fill_value=0)
    # Phân bổ khối lượng theo mức giá trong phiên
    pv = t.groupby(["price", "side"])["vol"].sum().unstack(fill_value=0)
    return dict(total_vol=tot_v, total_val=tot_val, buy_vol=buy, sell_vol=sell,
                buy_val=byv.get("Mua chủ động", 0.0), sell_val=byv.get("Bán chủ động", 0.0),
                atoatc_vol=by.get("ATO/ATC", 0.0),
                buy_ratio=buy / (buy + sell) * 100 if (buy + sell) else None,
                big_thr_bn=thr / 1e9, big_buy_bn=bb / 1e9, big_sell_bn=bs / 1e9, big_n=len(big),
                big_orders=big.sort_values("value", ascending=False).head(15),
                series=t[["time", "price", "cum_delta"]], time_profile=prof, price_profile=pv, atc=atc_info,
                session=t["time"].dt.date.iloc[-1])


# ═════════════════════════════ NHẬN ĐỊNH TỔNG HỢP ════════════════════════════
def _net_sum(df, col, n):
    if df is None or df.empty or col not in df.columns:
        return None
    return float(df[col].tail(n).sum())


def analyze_flow(price_df: pd.DataFrame, foreign=None, prop=None, orders=None, intraday=None) -> dict:
    """Ghép mọi nguồn → giai đoạn (gom/kéo/phân phối/xả), điểm dòng tiền −10..+10, danh sách dấu hiệu."""
    if price_df is None or len(price_df) < 30:
        return {}
    d = classify_sessions(session_features(price_df))
    mf = money_flow(d)
    last = mf.iloc[-1]
    signals = []   # (hướng, tiêu đề, bằng chứng)
    score = 0.0

    # 1) Đếm phiên gom/xả 25 phiên gần nhất (khái niệm "distribution days" của W. O'Neil)
    recent = d.tail(25)
    pos_ev = recent["event"].map(lambda e: EVENT_INFO[e][1] if e else 0)
    n_pos, n_neg = int((pos_ev > 0).sum()), int((pos_ev < 0).sum())
    n_dist = int(recent["event"].isin(["distribution", "churn_top", "upthrust", "pump_dump"]).sum())
    if n_dist >= 4:
        signals.append((-1, f"{n_dist} phiên phân phối/xả trong 25 phiên",
                        "Tích tụ ≥4 phiên bán có vol trong 5 tuần là cảnh báo đỉnh kinh điển (O'Neil)."))
        score -= 2.5
    if n_pos - n_neg >= 2:
        signals.append((+1, f"Phiên tích cực áp đảo ({n_pos} vs {n_neg})", "Số phiên kéo giá/cạn cung/hấp thụ nhiều hơn phiên xả."))
        score += 1.5
    elif n_neg - n_pos >= 2:
        signals.append((-1, f"Phiên tiêu cực áp đảo ({n_neg} vs {n_pos})", "Số phiên xả/vol lớn không tăng nhiều hơn phiên kéo."))
        score -= 1.5

    # 2) OBV/A-D so với giá 20 phiên — phân kỳ
    s_px, s_obv, s_ad = _slope(mf["Close"], 20), _slope(mf["obv"], 20), _slope(mf["ad"], 20)
    if s_px is not None and s_obv is not None:
        if s_px > 0.5 and s_obv < -0.3:
            signals.append((-1, "Phân kỳ âm: giá tăng nhưng OBV giảm", "Giá đi lên bằng vol phiên tăng nhỏ, vol phiên giảm lớn — tiền đang rút dần."))
            score -= 2
        elif s_px < -0.5 and s_obv > 0.3:
            signals.append((+1, "Phân kỳ dương: giá giảm nhưng OBV tăng", "Giá giảm nhưng vol tập trung ở phiên tăng — có lực gom âm thầm."))
            score += 2
        elif s_px > 0.5 and s_obv > 0.5:
            signals.append((+1, "Giá và OBV cùng tăng", "Xu hướng tăng được dòng tiền xác nhận."))
            score += 1
        elif s_px < -0.5 and s_obv < -0.5:
            signals.append((-1, "Giá và OBV cùng giảm", "Xu hướng giảm được dòng tiền xác nhận — chưa có dấu hiệu gom."))
            score -= 1
    cmf, mfi = last.get("cmf20"), last.get("mfi14")
    if cmf is not None and not pd.isna(cmf):
        if cmf >= 0.1:
            signals.append((+1, f"CMF(20) = {cmf:+.2f}", "Đa số phiên đóng cửa ở nửa trên biên độ với vol — áp lực mua chiếm ưu thế."))
            score += 1
        elif cmf <= -0.1:
            signals.append((-1, f"CMF(20) = {cmf:+.2f}", "Đa số phiên đóng cửa ở nửa dưới biên độ — áp lực bán chiếm ưu thế."))
            score -= 1
    if mfi is not None and not pd.isna(mfi):
        if mfi >= 80:
            signals.append((-1, f"MFI(14) = {mfi:.0f} — quá mua có dòng tiền", "Dòng tiền vào quá nóng, rủi ro chốt lời ngắn hạn."))
            score -= 0.5
        elif mfi <= 20:
            signals.append((+1, f"MFI(14) = {mfi:.0f} — quá bán", "Dòng tiền rút cạn, thường gần vùng hồi kỹ thuật."))
            score += 0.5
    # 3) Thanh khoản (giá trị) tăng/giảm — tiền có đang quan tâm mã này?
    v20, v60 = last.get("val_ma20"), last.get("val_ma60")
    liq_chg = (v20 / v60 - 1) * 100 if v20 and v60 and not pd.isna(v20) and not pd.isna(v60) else None
    if liq_chg is not None:
        if liq_chg >= 30:
            signals.append((0, f"Thanh khoản tăng {liq_chg:.0f}% (TB20 vs TB60)", "Tiền đang đổ vào mã này nhiều hơn — đọc kèm hướng giá để biết là gom hay xả."))
        elif liq_chg <= -30:
            signals.append((0, f"Thanh khoản giảm {abs(liq_chg):.0f}% (TB20 vs TB60)", "Mã đang bị lãng quên — vol cạn ở nền giá là tốt, cạn khi đang giảm là thiếu cầu."))
    # 4) Vị trí so với VWAP20 & POC
    vp = volume_profile(d)
    px = float(last["Close"])
    if not pd.isna(last.get("vwap20")):
        if px >= last["vwap20"] * 1.02:
            signals.append((+1, f"Giá trên VWAP20 ({last['vwap20']:,.0f})", "Người mua 20 phiên qua đang có lãi trung bình — ít áp lực bán gỡ hoà vốn."))
            score += 0.5
        elif px <= last["vwap20"] * 0.98:
            signals.append((-1, f"Giá dưới VWAP20 ({last['vwap20']:,.0f})", "Đa số người mua 20 phiên qua đang lỗ — mỗi nhịp hồi lên VWAP dễ gặp hàng bán gỡ vốn."))
            score -= 0.5
    # 5) Khối ngoại, tự doanh, cung cầu đặt lệnh
    fn5, fn20 = _net_sum(foreign, "net_val", 5), _net_sum(foreign, "net_val", 20)
    if fn20 is not None:
        tot_val20 = float(d["value_bn"].tail(20).sum()) * 1e9
        share = fn20 / tot_val20 * 100 if tot_val20 else 0
        if abs(share) >= 3:
            signals.append(((1 if fn20 > 0 else -1), f"Khối ngoại {'mua' if fn20 > 0 else 'bán'} ròng {abs(fn20)/1e9:,.0f} tỷ / 20 phiên",
                            f"Bằng {abs(share):.1f}% giá trị giao dịch — {'lực đỡ' if fn20 > 0 else 'nguồn cung'} đáng kể. 5 phiên gần nhất: {fn5/1e9:+,.0f} tỷ."))
            score += 1.5 if fn20 > 0 else -1.5
    pn20 = _net_sum(prop, "net_val", 20)
    if pn20 is not None and abs(pn20) >= 1e9:
        signals.append(((1 if pn20 > 0 else -1), f"Tự doanh {'mua' if pn20 > 0 else 'bán'} ròng {abs(pn20)/1e9:,.0f} tỷ / 20 phiên",
                        "Tự doanh CTCK có thông tin & tiền lớn; thường đi trước khi có ETF/phái sinh đáo hạn."))
        score += 0.75 if pn20 > 0 else -0.75
    if orders is not None and not orders.empty:
        imb5 = float(orders["imbalance"].tail(5).mean())
        ab = orders["avg_buy"].tail(5).mean(); as_ = orders["avg_sell"].tail(5).mean()
        if abs(imb5) >= 0.1:
            signals.append(((1 if imb5 > 0 else -1), f"Dư {'mua' if imb5 > 0 else 'bán'} đặt lệnh {abs(imb5)*100:.0f}% (5 phiên)",
                            "KL đặt mua vs đặt bán — cầu/cung chờ trên sổ lệnh."))
            score += 0.5 if imb5 > 0 else -0.5
        if ab and as_ and not pd.isna(ab) and not pd.isna(as_) and as_ > 0:
            ratio = ab / as_
            if ratio >= 1.3:
                signals.append((+1, f"Lệnh mua trung bình lớn gấp {ratio:.1f} lần lệnh bán", "Bên mua cỡ lệnh lớn (tổ chức) — bên bán nhỏ lẻ."))
                score += 0.5
            elif ratio <= 0.77:
                signals.append((-1, f"Lệnh bán trung bình lớn gấp {1/ratio:.1f} lần lệnh mua", "Bên bán là tiền lớn, bên mua nhỏ lẻ — dấu hiệu phân phối."))
                score -= 0.5
    # 6) Trong phiên gần nhất
    if intraday:
        br = intraday.get("buy_ratio")
        if br is not None:
            if br >= 58:
                signals.append((+1, f"Mua chủ động {br:.0f}% phiên gần nhất", "Người mua chấp nhận trả giá cao (quét lệnh bán) — cầu chủ động mạnh."))
                score += 0.75
            elif br <= 42:
                signals.append((-1, f"Bán chủ động {100-br:.0f}% phiên gần nhất", "Người bán chấp nhận bán giá thấp (đập lệnh mua) — cung chủ động mạnh."))
                score -= 0.75
        bb, bs = intraday.get("big_buy_bn", 0), intraday.get("big_sell_bn", 0)
        if bb + bs >= 2:
            net = bb - bs
            signals.append(((1 if net > 0 else -1), f"Lệnh lớn ≥{intraday['big_thr_bn']:.1f} tỷ: mua {bb:,.1f} · bán {bs:,.1f} tỷ",
                            "Tiền lớn trong phiên nghiêng về " + ("mua." if net > 0 else "bán.")))
            score += 0.75 if net > 0 else -0.75
        atc = intraday.get("atc") or {}
        if atc and abs(atc.get("atc_chg_pct", 0)) >= 1:
            up = atc["atc_chg_pct"] > 0
            signals.append((-1 if up else 0, f"{'Kéo' if up else 'Đạp'} giá phiên ATC {atc['atc_chg_pct']:+.1f}%",
                            f"Giá ATC {atc['atc_price']:,.0f} so với lệnh liên tục cuối {atc['last_continuous']:,.0f} "
                            f"({atc['atc_vol_share']:.0f}% KL phiên). Kéo/đạp ATC thường để làm đẹp giá đóng cửa — "
                            "không phản ánh cung cầu thật, phiên sau hay đảo chiều."))
    # 7) Áp lực hàng về T+2.5 sau phiên kéo vol lớn
    last3 = d.tail(4).head(3)
    hot = last3[(last3["event"].isin(["markup", "buy_climax"])) & (last3["vr"] >= 2)]
    if not hot.empty:
        dt = hot.iloc[-1]["Date"]
        signals.append((0, f"Hàng về T+2.5 từ phiên kéo {dt:%d/%m}", "Lượng lớn cổ phiếu mua phiên đó sắp/đã về tài khoản — "
                        "áp lực chốt lời ngắn hạn thường xuất hiện; giữ được giá qua T+3 là dấu hiệu mạnh."))

    # Giai đoạn (Wyckoff giản lược)
    pos60 = float(last["pos60"]) if not pd.isna(last["pos60"]) else 0.5
    trend_up = px > float(last["ema50"]) and float(last["ema20"]) > float(last["ema50"])
    if score >= 2 and pos60 <= 0.5:
        phase = ("TÍCH LUỸ / GOM HÀNG", "#00d97e", "Giá ở nửa dưới vùng 60 phiên nhưng dòng tiền tích cực — tiền lớn có dấu hiệu gom.")
    elif score >= 2 and trend_up:
        phase = ("KÉO GIÁ (MARKUP)", "#00b862", "Xu hướng tăng được dòng tiền xác nhận — ưu tiên nắm giữ, dời cắt lỗ theo xu hướng.")
    elif score <= -2 and pos60 >= 0.6:
        phase = ("PHÂN PHỐI", "#ff8a3d", "Giá còn ở vùng cao nhưng dòng tiền rút ra — tiền lớn có dấu hiệu bán cho nhỏ lẻ. Hạn chế mua mới.")
    elif score <= -2:
        phase = ("XẢ / GIẢM GIÁ (MARKDOWN)", "#ff3d5a", "Dòng tiền rút ra trong xu hướng giảm — chưa có dấu hiệu tạo đáy.")
    else:
        phase = ("CHƯA RÕ XU HƯỚNG DÒNG TIỀN", "#8baed4", "Tín hiệu gom và xả đan xen — chờ thêm phiên xác nhận.")
    return dict(d=mf, events=event_table(d), score=max(-10, min(10, score)), phase=phase,
                signals=signals, vp=vp, liq_chg=liq_chg, n_pos=n_pos, n_neg=n_neg,
                foreign=foreign, prop=prop, orders=orders, intraday=intraday)


FLOW_GLOSSARY = {
    "Vol / TB20": "Khối lượng phiên chia trung bình 20 phiên TRƯỚC đó. ≥1.5 là đáng chú ý, ≥2.5 là bùng nổ.",
    "Vị trí 60 phiên": "0% = đóng cửa ở đáy 60 phiên, 100% = ở đỉnh. Cùng một phiên vol lớn: ở đỉnh là phân phối, ở đáy là hấp thụ.",
    "OBV": "Cộng vol phiên tăng, trừ vol phiên giảm. OBV đi ngược giá = phân kỳ — giá thường đi theo OBV sau đó.",
    "CMF": "Chaikin Money Flow: dòng tiền dựa trên vị trí đóng cửa trong biên độ × vol. >+0.1 áp lực mua, <−0.1 áp lực bán.",
    "MFI": "RSI có trọng số vol. >80 quá mua có dòng tiền, <20 quá bán.",
    "VWAP20": "Giá vốn trung bình (theo vol) của người mua 20 phiên qua. Giá dưới VWAP = đa số đang lỗ → dễ có áp lực bán gỡ.",
    "POC": "Mức giá khớp nhiều vol nhất 120 phiên — hỗ trợ/kháng cự mạnh nhất vì nhiều người có giá vốn ở đó.",
    "Mua/bán chủ động": "Lệnh khớp do người mua quét giá bán (mua chủ động) hay người bán đập giá mua (bán chủ động) — đo sự nóng vội của mỗi bên.",
    "Lệnh lớn": "Lệnh khớp có giá trị ≥ max(1 tỷ, top 1% lệnh trong phiên) — dấu vết của tổ chức/tay to.",
    "Kéo/đạp ATC": "Giá đóng cửa bị đẩy mạnh trong phiên ATC 14:30-14:45 so với giá khớp liên tục. Hay dùng để làm đẹp NAV, ảnh hưởng chỉ số, đáo hạn phái sinh.",
    "T+2.5": "Cổ phiếu mua ngày T về tài khoản chiều T+2. Sau phiên kéo vol lớn, 2-3 phiên sau thường có áp lực chốt lời.",
}
