"""LCDに表示する内容。ここを自由に書き換える。

render(size) は PIL Image を返す関数。main.py が INTERVAL 秒ごとに呼び出してLCDへ送る。

サイトのアクセス数のページ (リアルタイム / 今日の数字) は、同じフォルダに admin_stats.php があるときだけ出す。
admin_stats.php は README の「サイトの数字を出す」にある形の JSON を出力するスクリプト。無ければサーバーのページだけを出す。
"""
import json
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path

import psutil
from PIL import Image, ImageDraw, ImageFont

INTERVAL = 2  # 再描画の間隔(秒)。全画面転送は1回あたり数百ミリ秒かかる
PORTRAIT = True  # 縦向き (170x320)
PAGE_SECONDS = 8  # 1ページを表示する秒数
STATS_SECONDS = 6  # 管理サイトの数字を取り直す間隔(秒)。リアルタイム画面は3秒ごと

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_JA = "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf"
STATS_SCRIPT = Path(__file__).with_name("admin_stats.php")

BG = (12, 14, 20)
FG = (230, 232, 238)
DIM = (120, 126, 140)
LINE = (40, 44, 56)
ACCENT = (80, 170, 255)
ACCENT_SOFT = (55, 75, 110)
GOOD = (90, 220, 130)
WARN = (255, 170, 60)
CRIT = (255, 80, 80)

_fonts = {}


def font(size, bold=False, ja=False):
    key = (size, bold, ja)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(FONT_JA if ja else FONT_BOLD if bold else FONT, size)
    return _fonts[key]


def _is_ja(ch):
    return ord(ch) > 0x2E7F  # かな・漢字・全角記号など


def jtext(d, xy, text, size, fill, anchor="la"):
    """日本語は Droid Sans Fallback、英数字は DejaVu Sans で描く (Droid には英数字が無い)"""
    runs = []
    for ch in text:
        ja = _is_ja(ch)
        if runs and runs[-1][0] == ja:
            runs[-1][1] += ch
        else:
            runs.append([ja, ch])
    width = sum(font(size, ja=ja).getlength(t) for ja, t in runs)
    x, y = xy
    x -= {"l": 0, "m": width / 2, "r": width}[anchor[0]]
    base = y + font(size).getmetrics()[0]  # 上端揃え: DejaVu のアセントで基準線を決める
    for ja, t in runs:
        d.text((x, base), t, font=font(size, ja=ja), fill=fill, anchor="ls")
        x += font(size, ja=ja).getlength(t)


def level_color(pct):
    return CRIT if pct >= 90 else WARN if pct >= 70 else ACCENT


def bar(d, x, y, w, h, pct, color=None):
    d.rounded_rectangle((x, y, x + w, y + h), radius=h // 2, fill=LINE)
    if pct > 0:
        fw = max(h, int(w * min(pct, 100) / 100))
        d.rounded_rectangle((x, y, x + fw, y + h), radius=h // 2, fill=color or level_color(pct))


def cpu_temp():
    temps = psutil.sensors_temperatures()
    for key in ("coretemp", "x86_pkg_temp", "k10temp"):
        if temps.get(key):
            return temps[key][0].current
    return None


def lan_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "-"


def uptime():
    sec = int(time.time() - psutil.boot_time())
    d, sec = divmod(sec, 86400)
    h, sec = divmod(sec, 3600)
    return f"{d}日 {h}時間 {sec // 60}分"


_stats = {"t": 0.0, "data": None, "error": None}


def admin_stats():
    if time.monotonic() - _stats["t"] >= STATS_SECONDS:
        _stats["t"] = time.monotonic()
        try:
            out = subprocess.run(
                ["php", str(STATS_SCRIPT)], capture_output=True, text=True, timeout=10, check=True
            )
            _stats["data"] = json.loads(out.stdout)
            _stats["error"] = None
        except (subprocess.SubprocessError, OSError, ValueError) as e:
            _stats["error"] = str(e)[:60]
    return _stats["data"]


# ---- ページ共通 ----

def header(d, w, title):
    jtext(d, (8, 6), title, 15, FG)
    d.text((w - 8, 8), datetime.now().strftime("%H:%M"), font=font(13, True), fill=DIM, anchor="ra")
    d.line((8, 28, w - 8, 28), fill=LINE)


def page_dots(d, w, h, index, count):
    gap = 10
    x = w // 2 - (count - 1) * gap // 2
    for i in range(count):
        r = 3 if i == index else 2
        d.ellipse((x - r, h - 8 - r, x + r, h - 8 + r), fill=FG if i == index else DIM)
        x += gap


def big_number(d, x, y, label, value, color, size=44):
    jtext(d, (x, y), label, 12, DIM, "ma")
    d.text((x, y + 16), f"{value:,}", font=font(size, True), fill=color, anchor="ma")


def stat_row(d, w, y, label, value, sub=None):
    jtext(d, (10, y), label, 12, DIM)
    d.text((w - 10, y - 2), value, font=font(15, True), fill=FG, anchor="ra")
    if sub:
        jtext(d, (w - 10, y + 16), sub, 10, DIM, "ra")


def no_data(d, w, h):
    msg = _stats["error"] or "読み込み中…"
    jtext(d, (w // 2, h // 2), "数字を取得できません", 13, WARN, "mm")
    d.text((w // 2, h // 2 + 20), msg, font=font(9), fill=DIM, anchor="mm")


# ---- 各ページ ----

def page_live(d, w, h, s):
    """管理サイト「リアルタイム」と同じ数字"""
    header(d, w, "リアルタイム")
    if not s:
        return no_data(d, w, h)
    live = s["live"]
    big_number(d, w // 2, 38, "接続中の人 (5分)", live["human"], GOOD if live["human"] else DIM, 52)
    jtext(d, (w // 2, 112), f"IP {live['ips']}  ・  リクエスト {live['requests']}", 11, DIM, "ma")
    d.line((8, 134, w - 8, 134), fill=LINE)

    u = live["users30"]
    stat_row(d, w, 144, "過去30分のユーザー", f"{u['human'] + u['other']:,}",
             f"人 {u['human']} ・ ボットなど {u['other']}")

    # 1分あたりのユーザー (30本。濃い色が人、薄い色がボットなど)
    jtext(d, (10, 186), "1分あたりのユーザー", 11, DIM)
    top, bottom = 204, 270
    mins = live["minutes"]
    peak = max(max((a + b for a, b in mins), default=0), 1)
    bw = (w - 20) / len(mins)
    for i, (human, other) in enumerate(mins):
        x0 = 10 + i * bw
        x1 = x0 + max(bw - 1.5, 1)
        hh = (bottom - top) * human / peak
        oh = (bottom - top) * other / peak
        if human + other == 0:
            d.line((x0, bottom, x1, bottom), fill=LINE)
            continue
        d.rectangle((x0, bottom - hh - oh, x1, bottom - hh), fill=ACCENT_SOFT)
        if human:
            d.rectangle((x0, bottom - hh, x1, bottom), fill=ACCENT)
    jtext(d, (10, bottom + 4), "-30分", 9, DIM)
    jtext(d, (w - 10, bottom + 4), "いま", 9, DIM, "ra")
    if live["bad"]:
        jtext(d, (w // 2, bottom + 4), f"攻撃・ブロック {live['bad']}", 9, CRIT, "ma")


def page_today(d, w, h, s):
    """管理サイト ホーム「今日の数字」と同じ数字"""
    header(d, w, "今日の数字")
    if not s:
        return no_data(d, w, h)
    big_number(d, w // 2, 36, "ページビュー", s["pvToday"], FG, 44)
    updated = s.get("accessUpdatedAt") or ""
    jtext(d, (w // 2, 100), f"毎時5分に更新 ({updated[11:16] or '-'})", 9, DIM, "ma")

    # セクション別 PV (多い順に4つ)
    # 日付が変わった直後は集計がまだ無い (古い admin_stats.php だと [] で届く)
    by_section = s.get("pvBySection") if isinstance(s.get("pvBySection"), dict) else {}
    secs = sorted(by_section.items(), key=lambda kv: -kv[1])[:4]
    if not secs:
        jtext(d, (w // 2, 160), "まだ集計がありません", 10, DIM, "ma")
    peak = max((n for _, n in secs), default=1) or 1
    y = 118
    for key, n in secs:
        label = (s.get("sectionLabels") or {}).get(key, key)
        jtext(d, (10, y), label, 10, DIM)
        d.text((w - 10, y - 1), str(n), font=font(11, True), fill=FG, anchor="ra")
        bar(d, 10, y + 15, w - 20, 4, 100 * n / peak, ACCENT)
        y += 25
    d.line((8, 222, w - 8, 222), fill=LINE)

    stat_row(d, w, 234, "価格コンペアの検索", f"{s['searches']:,}", f"利用者 {s['searchUsers']} 人")
    stat_row(d, w, 274, "検索エンジンから", f"{s['searchEngineToday']:,}")


def page_server(d, w, h, _s):
    header(d, w, "サーバー")
    d.text((10, 36), socket.gethostname(), font=font(16, True), fill=FG)
    d.text((10, 58), lan_ip(), font=font(11), fill=DIM)
    jtext(d, (10, 74), "稼働 " + uptime(), 11, DIM)

    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    temp = cpu_temp()
    y = 100
    for label, pct in (("CPU", cpu), ("メモリ", mem), ("ディスク", disk)):
        jtext(d, (10, y), label, 12, DIM)
        d.text((w - 10, y - 1), f"{pct:.0f}%", font=font(14, True), fill=FG, anchor="ra")
        bar(d, 10, y + 20, w - 20, 8, pct)
        y += 42
    if temp is not None:
        tc = CRIT if temp >= 85 else WARN if temp >= 70 else FG
        jtext(d, (10, y), "CPU温度", 12, DIM)
        d.text((w - 10, y - 1), f"{temp:.0f}°C", font=font(14, True), fill=tc, anchor="ra")
    d.text((w // 2, y + 30), datetime.now().strftime("%Y/%m/%d (%a)"), font=font(11), fill=DIM, anchor="ma")


PAGES = [page_live, page_today, page_server] if STATS_SCRIPT.exists() else [page_server]


def _wrap(text, width):
    return [text[i:i + width] for i in range(0, len(text), width)] or [""]


def render(size):
    w, h = size
    img = Image.new("RGB", size, BG)
    d = ImageDraw.Draw(img)
    stats = admin_stats()
    index = int(time.time() // PAGE_SECONDS) % len(PAGES)
    try:
        PAGES[index](d, w, h, stats)
    except Exception as e:  # 1 ページの不具合でサービスごと落ちないよう、画面にエラーを出して続ける
        d.rectangle((0, 0, w, h), fill=BG)
        header(d, w, "表示エラー")
        jtext(d, (w // 2, h // 2 - 10), "このページを描けません", 12, WARN, "ma")
        d.multiline_text((10, h // 2 + 14), "\n".join(_wrap(f"{type(e).__name__}: {e}", 26)[:6]), font=font(9), fill=DIM)
    page_dots(d, w, h, index, len(PAGES))
    return img
