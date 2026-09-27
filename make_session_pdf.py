"""Build a single self-contained PDF of everything done today (2026-09-27).

If this machine disappears, this file is the whole record: the research
findings, the numbers, the rejected ideas with reasons, and the bugs that
produced fake results. Source code lives in the GitHub repos, so the PDF
carries the conclusions and the evidence rather than reprinting 40 files.

No dependencies beyond reportlab, which is already installed.
"""
import os
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, PageBreak,
                                PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "SESSION_2026-09-27.pdf")

ACCENT = colors.HexColor("#1a5fb4")
GOOD = colors.HexColor("#0a7c3f")
BAD = colors.HexColor("#b42318")
MUTED = colors.HexColor("#5c5c5c")
BOX = colors.HexColor("#f2f4f7")
HDR = colors.HexColor("#dde5f0")

DOCS = [
    ("HANDOFF.md", "Who the user is, account facts, the winning strategy, "
                   "the five bugs, and the ranked next steps"),
    ("INTRADAY.md", "15m sweep, all 32 configs, and the 106x cost arithmetic"),
    ("TIMEOFDAY.md", "Hourly movement profile, out-of-sample validated, and "
                     "why trading the peak window still loses"),
    ("FUNDING.md", "Delta-neutral funding carry tested on six years of real "
                   "funding rates, and why it is not deployable"),
    ("SHADOW.md", "What shadow mode is, and how the log gets scored"),
    ("STATE.md", "Live account status and current standings"),
]


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def md_inline(t):
    t = esc(t)
    out, i = [], 0
    while i < len(t):
        if t[i] == "`":
            j = t.find("`", i + 1)
            if j > 0:
                out.append(f'<font face="Courier" size="8.2" backColor="#eceff4">'
                           f'{t[i+1:j]}</font>')
                i = j + 1
                continue
        if t.startswith("**", i):
            j = t.find("**", i + 2)
            if j > 0:
                out.append(f"<b>{t[i+2:j]}</b>")
                i = j + 2
                continue
        out.append(t[i])
        i += 1
    return "".join(out)


def styles():
    ss = getSampleStyleSheet()
    s = {}
    s["title"] = ParagraphStyle("t", parent=ss["Title"], fontSize=20, leading=24,
                                textColor=ACCENT, alignment=TA_LEFT, spaceAfter=2)
    s["sub"] = ParagraphStyle("st", parent=ss["Normal"], fontSize=9.2, leading=12.5,
                              textColor=MUTED, spaceAfter=11)
    s["h1"] = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=13.5, leading=17,
                             textColor=ACCENT, spaceBefore=12, spaceAfter=5)
    s["h2"] = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=10.6, leading=13.5,
                             textColor=colors.HexColor("#10366b"), spaceBefore=8,
                             spaceAfter=2)
    s["h3"] = ParagraphStyle("h3", parent=ss["Heading3"], fontSize=9.2, leading=12,
                             textColor=colors.HexColor("#333"), spaceBefore=6,
                             spaceAfter=1)
    s["body"] = ParagraphStyle("b", parent=ss["Normal"], fontSize=8.8, leading=12,
                               spaceAfter=3)
    s["bullet"] = ParagraphStyle("bu", parent=s["body"], leftIndent=10,
                                 bulletIndent=2, spaceAfter=2)
    s["code"] = ParagraphStyle("c", parent=ss["Normal"], fontName="Courier",
                               fontSize=7.4, leading=9.4, backColor=colors.HexColor("#f7f7f9"),
                               borderPadding=4, spaceAfter=4)
    s["cell"] = ParagraphStyle("ce", parent=ss["Normal"], fontSize=7.4, leading=9.4)
    s["cellb"] = ParagraphStyle("cb", parent=s["cell"], fontName="Courier")
    return s


def render_md(text, st):
    out, bullets, code, in_code = [], [], [], False

    def flush():
        for b in bullets:
            out.append(Paragraph(md_inline(b), st["bullet"], bulletText="•"))
        bullets.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            flush()
            if in_code:
                out.append(Paragraph("<br/>".join(esc(l) or "&nbsp;" for l in code),
                                     st["code"]))
                code, in_code = [], False
            else:
                in_code = True
            continue
        if in_code:
            code.append(line)
            continue
        if not line.strip():
            flush()
            continue
        if line.startswith("#"):
            flush()
            lvl = len(line) - len(line.lstrip("#"))
            out.append(Paragraph(md_inline(line.lstrip("#").strip()),
                                 st["h1"] if lvl <= 1 else
                                 st["h2"] if lvl == 2 else st["h3"]))
            continue
        if line.lstrip().startswith(("- ", "* ")):
            bullets.append(line.lstrip()[2:])
            continue
        if line.lstrip()[:2].rstrip(".").isdigit() and ". " in line:
            n, rest = line.split(". ", 1)
            bullets.append(f"{n}. {rest}")
            continue
        if line.lstrip().startswith("|") and line.count("|") >= 2:
            flush()
            body = line.strip()
            if not set(body.replace("|", "").replace(" ", "")) <= set("-:"):
                out.append(Paragraph(md_inline(body), st["body"]))
            continue
        flush()
        out.append(Paragraph(md_inline(line), st["body"]))
    flush()
    if in_code and code:
        out.append(Paragraph("<br/>".join(esc(l) for l in code), st["code"]))
    return out


def kv(pairs, st, kw=40 * mm):
    data = [[Paragraph(f"<b>{md_inline(k)}</b>", st["cell"]),
             Paragraph(md_inline(v), st["cell"])] for k, v in pairs]
    t = Table(data, colWidths=[kw, 150 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), BOX),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8cdd6")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2),
    ]))
    return t


def deco(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#c8cdd6"))
    canvas.setLineWidth(0.5)
    canvas.line(17 * mm, A4[1] - 13 * mm, A4[0] - 17 * mm, A4[1] - 13 * mm)
    canvas.setFont("Helvetica", 7.2)
    canvas.setFillColor(MUTED)
    canvas.drawString(17 * mm, A4[1] - 11.5 * mm,
                      "Delta Exchange research - session record 2026-09-27")
    canvas.drawRightString(A4[0] - 17 * mm, 9 * mm, f"page {doc.page}")
    canvas.restoreState()


def main():
    st = styles()
    doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=17 * mm, rightMargin=17 * mm,
                          topMargin=17 * mm, bottomMargin=14 * mm,
                          title="Delta Exchange research - session record",
                          author="Hermes Agent")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=deco)])

    s = [Paragraph("Delta Exchange research — session record", st["title"]),
         Paragraph(
             "Everything established on 2026-09-27, including the results that "
             "were negative and the ideas that were rejected. Written to stand "
             "alone if the machine it was produced on is gone. "
             f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.",
             st["sub"])]

    s.append(Paragraph("The one number that matters", st["h2"]))
    s.append(kv([
        ("Best strategy", "Order block (SMC) + sentiment gate, ETHUSD 1d"),
        ("Sharpe, 6y out-of-sample", "<b>0.94</b> — this is the number to quote"),
        ("Quote instead of this", "2.88 — the same strategy on 2 years of data"),
        ("Sharpe at 2x costs", "0.85"),
        ("CAGR / max drawdown", "+18.5% / -14.9%"),
        ("Trades", "129 over six years"),
        ("ETH buy-and-hold, same window", "+8.8%"),
        ("BTC buy-and-hold, same window", "+101% — do NOT use this strategy on BTC"),
    ], st))
    s.append(Spacer(1, 5))
    s.append(Paragraph(
        "Intraday: <b>0 of 32 configurations profitable.</b> 15m round-trip cost is "
        "0.18%; the strategy's gross edge per trade is 0.0017%. Costs exceed the "
        "edge by 106x. On BTC, 10 of 16 configs were gross-positive (best +48.9%) "
        "and every one lost money net.", st["body"]))

    s.append(Paragraph("What was settled today", st["h2"]))
    for line in [
        "<b>Sentiment gating helps, verified on six years.</b> Order block alone "
        "was Sharpe 0.60; gated to extreme Fear &amp; Greed it reached 0.94. The "
        "2.88 result was a two-year artefact.",
        "<b>Intraday does not work on this venue.</b> 32 configs, 15m bars, all "
        "negative. Measured, not assumed.",
        "<b>Time of day is real but insufficient.</b> 13:00-16:59 UTC holds 4 of 4 "
        "out of sample, yet it only halves fees by cutting trade count rather than "
        "adding edge.",
        "<b>Funding carry is real but too small.</b> Positive ~88% of days, 11-12% "
        "annualised, but a delta-neutral book doubles the cost and needs 60-365 days "
        "to clear its own fees.",
        "<b>ETH only.</b> Buy-and-hold beats this strategy on BTC by an order of "
        "magnitude.",
    ]:
        s.append(Paragraph(line, st["bullet"], bulletText="•"))

    s.append(Paragraph("Rejected, with reasons", st["h2"]))
    for line in [
        "Intraday scalping on Delta perps — 0/32 configs profitable, 106x cost drag",
        "Funding carry at retail size — needs 60-365 day holds to clear fees",
        "Time-window restriction alone — halves fees, does not add edge",
        "TradingAgents repo — equities-only, not a perp execution engine",
        "FVG, BOS, CHoCH patterns — 0/22 and 0/15 profitable configs",
        "A YouTube candle-break strategy — 62 configs, 0 profitable",
        "BTC 1d adx_trend_50_200 — Sharpe 1.36 on 21 trades, a meaningless sample",
        "1h timeframe — fees consume it, and sweeps time out on 2 cores",
    ]:
        s.append(Paragraph(line, st["bullet"], bulletText="x"))

    s.append(Paragraph("Bugs that produced fake results", st["h2"]))
    s.append(Paragraph(
        "Every one of these printed a spectacular number first. If a Sharpe above "
        "3 appears, assume a bug until proven otherwise.", st["body"]))
    for line in [
        "Zero-return bars filtered out of the Sharpe denominator — <b>Sharpe 680</b>",
        "Order block tagged at its birth bar while reading 3 future candles — "
        "<b>87% win rate, 1643% CAGR</b>",
        "Pattern signals with no holding period, so fees were never charged",
        "Funding re-charged every bar because the window was bounded by entry_t "
        "not settled_t — 5% drag instead of 0.1%",
        "Epoch <b>seconds</b> read as milliseconds, collapsing dates to 1970 and "
        "printing <b>+8104% annualised</b> funding",
        "A DNS failure returning HTTP 0, which is numerically less than 400 and so "
        "passed a naive reachability check",
    ]:
        s.append(Paragraph(line, st["bullet"], bulletText="!"))

    s.append(Paragraph("Account", st["h2"]))
    s.append(kv([
        ("Balance", "INR 35.01 (~$0.41) — read balance_inr, not balance"),
        ("API key", "was in .env; emptied when Gemini/Groq keys were added"),
        ("Trading permission", "not enabled — /v2/positions returns 400"),
        ("Live trading", "impossible: $0.41 against a ~$10 minimum perp order"),
        ("Shadow mode", "cron 81116a955e5e, every 4h, no orders placed"),
    ], st))
    s.append(Spacer(1, 4))
    s.append(Paragraph(
        "The API key is not needed for any of the research above. Public candles "
        "and Binance funding history are enough. It is only required to read the "
        "account, and to place orders, which is not possible at this balance.",
        st["body"]))

    s.append(Paragraph("Published repos", st["h2"]))
    s.append(kv([
        ("delta-bot", "Backtest engine + strategy. 11/11 engine tests pass. "
                      "github.com/fsix7115-arch/delta-bot"),
        ("freellm-probe", "Which free LLM APIs actually work from your machine. "
                          "Zero dependencies."),
        ("devcheck", "Is the dev machine healthy, not just populated. "
                     "Read-only, CI-safe, exit 1 when unhealthy."),
        ("Profile", "github.com/fsix7115-arch — all three, MIT licensed"),
    ], st))

    for fname, desc in DOCS:
        path = os.path.join(HERE, fname)
        if not os.path.exists(path):
            continue
        s.append(PageBreak())
        s.append(Paragraph(f"{fname}", st["h1"]))
        s.append(Paragraph(desc, st["body"]))
        with open(path) as f:
            s.extend(render_md(f.read(), st))

    doc.build(s)
    print(f"wrote {OUT} ({os.path.getsize(OUT)/1024:.0f} KB)")


if __name__ == "__main__":
    main()
