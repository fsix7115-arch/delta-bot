"""Append the source code and key results as a PDF appendix.

The brief alone is not enough for a new agent: it explains WHAT was learned but
not the code that produced it. This appends the files a successor actually
needs -- engine, strategies, tests -- plus the result tables, so the PDF stands
alone if the machine is gone.
"""
import os
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Preformatted,
                                Spacer, Table, TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "DELTA_TRADING_FULL.pdf")

ACCENT = colors.HexColor("#1a5fb4")
MUTED = colors.HexColor("#5c5c5c")
HDRBG = colors.HexColor("#dde5f0")
BOXBG = colors.HexColor("#f2f4f7")

# Order matters: the essentials first, in the order a new agent should read them.
CODE_FILES = [
    ("engine.py", "Backtest engine: no-lookahead fills, fees+slippage on both legs, "
                  "real funding, exact unit-based P&L, degeneracy guard."),
    ("strategies_smc.py", "The winner. Order block, FVG, liquidity grab, BOS/CHoCH."),
    ("strategies_v2.py", "Round 2: SuperTrend, VWAP reversion, sentiment-gated trend, "
                         "F&G divergence, plus the point-in-time sentiment aligner."),
    ("strategies.py", "Round 1: 20 classic signal generators (EMA cross, ADX, Donchian, "
                      "breakout, mean reversion, MACD, RSI)."),
    ("test_engine.py", "11 tests that must pass before any result is believable. "
                       "They pin down the P&L, funding and cost bugs."),
    ("test_lookahead.py", "Regression test for the lookahead leak that produced "
                          "Sharpe 60. Run this after touching any pattern detector."),
    ("monte_carlo.py", "Bootstrap of the trade P&L sequence; reports P(loss), p5 and "
                       "worst drawdown across 2000 resamples."),
    ("shadow.py", "Live shadow mode: fetches Delta candles, prints the current signal, "
                  "places NO orders, appends to results/shadow_log.jsonl."),
    ("check_api.py", "Read-only credential check. Never prints the secret."),
    ("account_dump.py", "Read-only wallet dump. Reads balance_inr, not balance."),
    ("fetch_extended.py", "Pulls 6y Binance candles + real funding-rate history."),
    ("fetch_sentiment.py", "Pulls the Alternative.me Fear & Greed series (2018->now)."),
    ("hybrid.py", "Order block merged with sentiment gating. Contains the untested "
                  "ob_sent_gate variant that is the top open question."),
    ("validate_6y.py", "6-year Binance validation harness with real funding and 2x cost stress."),
    ("vet_hybrid.py", "Guards against believing an implausibly good result: checks cost "
                      "wiring, sentiment leakage, holding length and selection bias."),
    ("resume.sh", "One command: runs the tests, prints the best config and env status."),
]

RESULT_FILES = [
    ("results/orderblock_6y.csv", "6-year Binance validation, 36 configs. THE honest result."),
    ("results/delta_validate.csv", "2-year Delta cross-validation."),
    ("results/monte_carlo.csv", "Bootstrap robustness for the round-1 leaders."),
    ("results/hybrid.csv", "Order block x sentiment merge, ranked by P(loss)."),
    ("results/smc.csv", "SMC pattern grid: FVG, liquidity grab, order block, BOS."),
    ("results/smc_monte_carlo.csv", "Bootstrap on the order block."),
    ("results/round2_delta.csv", "Round-2 strategies (SuperTrend/VWAP/sentiment) on Delta."),
    ("results/round2_monte_carlo.csv", "Bootstrap on round 2."),
    ("results/youtube.csv", "The mechanised Stock Learners candle-break: 0 of 62 viable."),
    ("results/sweep_6y.csv", "Round-1 sweep over 155 configs, 6y data."),
]


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def styles():
    ss = getSampleStyleSheet()
    s = {}
    s["title"] = ParagraphStyle("t", parent=ss["Title"], fontSize=21, leading=25,
                                textColor=ACCENT, alignment=TA_LEFT, spaceAfter=2)
    s["sub"] = ParagraphStyle("st", parent=ss["Normal"], fontSize=9.6, leading=13,
                              textColor=MUTED, spaceAfter=12)
    s["h1"] = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=14.5, leading=18,
                             textColor=ACCENT, spaceBefore=13, spaceAfter=5)
    s["h2"] = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11.4, leading=14.5,
                             textColor=colors.HexColor("#10366b"), spaceBefore=9,
                             spaceAfter=3)
    s["body"] = ParagraphStyle("b", parent=ss["Normal"], fontSize=9.2, leading=12.6,
                               spaceAfter=3.4)
    s["bullet"] = ParagraphStyle("bu", parent=s["body"], leftIndent=11,
                                 bulletIndent=2, spaceAfter=2.4)
    s["fname"] = ParagraphStyle("fn", parent=ss["Heading3"], fontSize=10.4, leading=13,
                                textColor=colors.HexColor("#0a3d91"), spaceBefore=9,
                                spaceAfter=1)
    s["fdesc"] = ParagraphStyle("fd", parent=s["body"], fontSize=8.5, leading=11.4,
                                textColor=MUTED, spaceAfter=3)
    s["code"] = ParagraphStyle("c", parent=ss["Normal"], fontName="Courier",
                               fontSize=6.0, leading=7.4, spaceAfter=4)
    s["cell"] = ParagraphStyle("ce", parent=ss["Normal"], fontSize=6.4, leading=8.2)
    s["cellb"] = ParagraphStyle("cb", parent=s["cell"], fontName="Courier")
    return s


def header(st, story, title, desc, body):
    story.append(PageBreak())
    story.append(Paragraph(title, st["h1"]))
    if desc:
        story.append(Paragraph(desc, st["fdesc"]))
    story.append(body)


def code_flowables(path, st, max_lines=None):
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except Exception:
        return [Paragraph(f"[missing: {os.path.basename(path)}]", st["fdesc"])]
    if max_lines:
        lines = lines[:max_lines]
    body = "\n".join(lines) or "# (empty)"
    # Preformatted keeps spacing but can overflow; keep chunks small
    return [Preformatted(esc(body), st["code"], maxLineLength=118)]


def csv_table(path, st, head_rows=6, max_rows=6, max_cols=9):
    try:
        with open(path) as f:
            lines = [l for l in f.read().splitlines() if l.strip()]
    except Exception:
        return [Paragraph(f"[missing: {os.path.basename(path)}]", st["fdesc"])]
    import csv as _csv
    rows = list(_csv.reader(lines))
    header = rows[0][:max_cols]
    body = [r[:max_cols] for r in rows[1:1 + max_rows]]
    trimmed = len(rows[0]) > max_cols
    data = [[Paragraph(f"<b>{esc(c)}</b>", st["cell"]) for c in header]]
    for r in body:
        data.append([Paragraph(esc(c)[:22], st["cellb"]) for c in r])
    t = Table(data, repeatRows=1)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), HDRBG),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c8cdd6")),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    out = [t, Spacer(1, 2)]
    if trimmed:
        out.append(Paragraph(
            f"(showing the first {max_rows} rows and {max_cols} of "
            f"{len(rows)-1} columns; full file is on the machine)", st["fdesc"]))
    else:
        out.append(Paragraph(f"({len(rows)-1} rows total)", st["fdesc"]))
    return out


def kv(pairs, st, keyw=44 * mm):
    data = [[Paragraph(f"<b>{esc(k)}</b>", st["cell"]), Paragraph(esc(v), st["cell"])]
            for k, v in pairs]
    t = Table(data, colWidths=[keyw, 148 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), BOXBG),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c8cdd6")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    return t


def deco(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#c8cdd6"))
    canvas.setLineWidth(0.5)
    canvas.line(16 * mm, A4[1] - 13 * mm, A4[0] - 16 * mm, A4[1] - 13 * mm)
    canvas.setFont("Helvetica", 7.2)
    canvas.setFillColor(MUTED)
    canvas.drawString(16 * mm, A4[1] - 11.5 * mm,
                      "Delta Exchange Trading - Complete Handoff (brief + source code)")
    canvas.drawRightString(A4[0] - 16 * mm, 9 * mm, f"page {doc.page}")
    canvas.restoreState()


def main():
    st = styles()
    doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                          topMargin=17 * mm, bottomMargin=14 * mm,
                          title="Delta Trading Handoff - complete",
                          author="Hermes Agent")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=deco)])

    story = []
    story.append(Paragraph("Delta Exchange Trading — Complete Handoff", st["title"]))
    story.append(Paragraph(
        "Brief, full source code and every result table in one file. "
        "Self-contained: a new agent can continue the work from this PDF alone, "
        "even if the machine it was built on is gone. Generated "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.",
        st["sub"]))

    story.append(Paragraph("What is in this document", st["h2"]))
    for line in [
        "Part 1 — the brief: who the user is, the account, the winning strategy, "
        "the five bugs that produced fake results, what was rejected, and the "
        "ranked next steps.",
        "Part 2 — the source: every module a successor needs, in reading order, "
        "with a note on what each one is for.",
        "Part 3 — the evidence: the result tables, so the claims can be checked "
        "rather than taken on faith.",
    ]:
        story.append(Paragraph(line, st["bullet"], bulletText="•"))

    story.append(Spacer(1, 6))
    story.append(Paragraph("The one number that matters", st["h2"]))
    story.append(kv([
        ("Strategy", "Order block (SMC), mechanised — ETHUSD 4h, 2% stop"),
        ("Sharpe, 2y Delta", "1.01 over 376 trades — the headline"),
        ("Sharpe, 6y Binance", "0.60 over 78 trades — THE HONEST NUMBER. Quote this one."),
        ("Buy and hold, ETH 6y", "+3.2% CAGR (strategy +14.0%)"),
        ("Buy and hold, BTC 6y", "+29.6% CAGR (strategy +6.5%) — do NOT use this on BTC"),
        ("Account", "INR 35.01 ($0.41), production key, Read scope only"),
        ("Live trading", "Impossible: $0.41 < Delta's ~$10 minimum. Shadow mode only."),
    ], st))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "<b>Sanity rule:</b> if a backtest in this project ever prints a Sharpe "
        "above about 3, treat it as a bug until proven otherwise. Four of the "
        "five bugs listed in Part 1 did exactly that.", st["body"]))

    # ---- Part 1: the brief -------------------------------------------------
    brief = os.path.join(HERE, "HANDOFF.md")
    state = os.path.join(HERE, "STATE.md")
    for path, title in ((brief, "Part 1 — The brief"),
                        (state, "Part 1b — Account state (STATE.md)")):
        if not os.path.exists(path):
            continue
        story.append(PageBreak())
        story.append(Paragraph(title, st["h1"]))
        with open(path) as f:
            for line in f.read().splitlines():
                s = line.rstrip()
                if s.startswith("#"):
                    lvl = len(s) - len(s.lstrip("#"))
                    story.append(Paragraph(esc(s.lstrip("#").strip()),
                                           st["h1"] if lvl <= 1 else
                                           st["h2"] if lvl == 2 else
                                           st["body"]))
                elif s.strip():
                    story.append(Paragraph(esc(s), st["body"]))

    # ---- Part 2: source ----------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("Part 2 — The source code", st["h1"]))
    story.append(Paragraph(
        "Read these in order. engine.py first: every other module depends on its "
        "conventions, and three of the documented bugs lived in exactly it.",
        st["body"]))
    story.append(Spacer(1, 4))
    toc = [[Paragraph(f"<b>{esc(n)}</b>", st["cell"]),
            Paragraph(esc(d), st["cell"])] for n, d in CODE_FILES]
    t = Table(toc, colWidths=[42 * mm, 150 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), BOXBG),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#c8cdd6")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t)

    for fname, desc in CODE_FILES:
        path = os.path.join(HERE, fname)
        if not os.path.exists(path):
            continue
        story.append(PageBreak())
        story.append(Paragraph(fname, st["fname"]))
        story.append(Paragraph(desc, st["fdesc"]))
        story.extend(code_flowables(path, st))

    # ---- Part 3: evidence --------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("Part 3 — The evidence", st["h1"]))
    story.append(Paragraph(
        "Every claim in Part 1 should be checkable against these. The first row "
        "of each table is the single most important line in the project.",
        st["body"]))
    for fname, desc in RESULT_FILES:
        path = os.path.join(HERE, fname)
        if not os.path.exists(path):
            continue
        story.append(Spacer(1, 7))
        story.append(Paragraph(fname, st["fname"]))
        story.append(Paragraph(desc, st["fdesc"]))
        story.extend(csv_table(path, st))

    doc.build(story)
    print(f"wrote {OUT} ({os.path.getsize(OUT)/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()
