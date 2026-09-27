"""Build a single self-contained PDF handoff from HANDOFF.md + STATE.md.

Everything the user needs if this Cloud Shell disappears. No external files,
no network, readable anywhere.
"""
import os
import re
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (BaseDocTemplate, Frame, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "DELTA_TRADING_HANDOFF.pdf")

ACCENT = colors.HexColor("#1a5fb4")
WARN = colors.HexColor("#b42318")
GOOD = colors.HexColor("#0a7c3f")
MUTED = colors.HexColor("#5c5c5c")
BOXBG = colors.HexColor("#f2f4f7")
CODEBG = colors.HexColor("#f7f7f9")


def esc(t):
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def md_inline(t):
    """Minimal inline markdown -> reportlab markup."""
    t = esc(t)
    t = re.sub(r"`([^`]+)`", r'<font face="Courier" size="8.4" backColor="#eceff4">\1</font>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", t)
    return t


def build_styles():
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
    s["h3"] = ParagraphStyle("h3", parent=ss["Heading3"], fontSize=9.8, leading=13,
                             textColor=colors.HexColor("#333"), spaceBefore=7,
                             spaceAfter=2)
    s["body"] = ParagraphStyle("b", parent=ss["Normal"], fontSize=9.2, leading=12.6,
                               spaceAfter=3.4)
    s["bullet"] = ParagraphStyle("bu", parent=s["body"], leftIndent=11,
                                 bulletIndent=2, spaceAfter=2.6)
    s["code"] = ParagraphStyle("c", parent=ss["Normal"], fontName="Courier",
                               fontSize=7.9, leading=10.4, backColor=CODEBG,
                               borderPadding=4, spaceAfter=5)
    s["cell"] = ParagraphStyle("ce", parent=ss["Normal"], fontSize=7.8, leading=10.2)
    s["cellb"] = ParagraphStyle("cb", parent=s["cell"], fontName="Courier")
    return s


def render_md(text, st):
    """Very small markdown subset -> flowables."""
    out, buf, in_code = [], [], False
    code_lines, bullets = [], []

    def flush_bullets():
        for b in bullets:
            out.append(Paragraph(md_inline(b), st["bullet"], bulletText="•"))
        bullets.clear()

    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip().startswith("```"):
            flush_bullets()
            if in_code:
                out.append(Paragraph("<br/>".join(
                    esc(l) if l else "&nbsp;" for l in code_lines), st["code"]))
                code_lines, in_code = [], False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if not line.strip():
            flush_bullets()
            continue
        if line.startswith("#"):
            flush_bullets()
            lvl = len(line) - len(line.lstrip("#"))
            txt = md_inline(line.lstrip("#").strip())
            out.append(Paragraph(txt, st["h1"] if lvl <= 1 else
                                 st["h2"] if lvl == 2 else st["h3"]))
            continue
        if re.match(r"^\s*[-*]\s+", line):
            bullets.append(re.sub(r"^\s*[-*]\s+", "", line))
            continue
        if re.match(r"^\s*\d+\.\s+", line):
            n, rest = re.match(r"^\s*(\d+)\.\s+(.*)", line).groups()
            bullets.append(f"{n}. {rest}")
            continue
        flush_bullets()
        out.append(Paragraph(md_inline(line), st["body"]))
    flush_bullets()
    if in_code and code_lines:
        out.append(Paragraph("<br/>".join(esc(l) for l in code_lines), st["code"]))
    return out


def kv_table(pairs, st, keyw=40 * mm):
    rows = [[Paragraph(md_inline(k), st["cellb"]), Paragraph(md_inline(v), st["cell"])]
            for k, v in pairs]
    t = Table(rows, colWidths=[keyw, 152 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), BOXBG),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8cdd6")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    return t


def md_table(text, st):
    rows = [r for r in text.splitlines() if r.strip().startswith("|")]
    if len(rows) < 2:
        return None
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    cells = [cells[0]] + [c for c in cells[1:] if not set("".join(c)) <= set("-: ")]
    data = [[Paragraph(md_inline(c), st["cell"]) for c in r] for r in cells]
    n = len(cells[0])
    w = 192 * mm / n
    t = Table(data, colWidths=[w] * n, repeatRows=1)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dde5f0")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8cdd6")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t


def page_deco(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#c8cdd6"))
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, A4[1] - 14 * mm, A4[0] - 18 * mm, A4[1] - 14 * mm)
    canvas.setFont("Helvetica", 7.4)
    canvas.setFillColor(MUTED)
    canvas.drawString(18 * mm, A4[1] - 12 * mm,
                      "Delta Exchange Trading - Handoff Brief")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"page {doc.page}")
    canvas.restoreState()


def main():
    st = build_styles()
    doc = BaseDocTemplate(OUT, pagesize=A4,
                          leftMargin=18 * mm, rightMargin=18 * mm,
                          topMargin=18 * mm, bottomMargin=15 * mm,
                          title="Delta Trading Handoff",
                          author="Hermes Agent")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="f")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=page_deco)])

    story = []
    story.append(Paragraph("Delta Exchange Trading — Handoff Brief", st["title"]))
    story.append(Paragraph(
        "Complete context for any new agent or a new session. "
        "Generated by Hermes Agent on "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}.",
        st["sub"]))

    story.append(Paragraph("Quick start", st["h2"]))
    story.append(Paragraph(
        "Say <b>&quot;Resume delta-bot&quot;</b> in a new Hermes session and it will "
        "read <font face=\"Courier\" size=\"8.4\">STATE.md</font> from "
        "<font face=\"Courier\" size=\"8.4\">~/delta-bot/</font>. The full brief is "
        "<font face=\"Courier\" size=\"8.4\">HANDOFF.md</font>; "
        "<font face=\"Courier\" size=\"8.4\">bash resume.sh</font> prints tests, the "
        "current best strategy and the account status.", st["body"]))
    story.append(Spacer(1, 4))

    story.append(Paragraph("The short version", st["h2"]))
    story.append(kv_table([
        ("Best strategy",
         "Order block (Smart Money Concepts), mechanised — <b>ETHUSD 4h</b>, "
         "2% stop loss"),
        ("Headline number",
         "Sharpe <b>1.01</b> over 376 trades on 2 years of Delta data"),
        ("Number to actually trust",
         "Sharpe <b>0.60</b> on 6 years of Binance data incl. 2020 crash and "
         "2022 bear market. Always quote both."),
        ("Buy and hold, same 6y window",
         "ETH +3.2% CAGR vs strategy +14.0%. On <b>BTC</b> buy-and-hold wins "
         "(+29.6% vs +6.5%) — deploy on ETH only."),
        ("Account",
         "Production key, balance <b>INR 35.01 ($0.41)</b>, Read scope only, "
         "no Trading permission"),
        ("Live trading",
         "<b>Impossible</b> — $0.41 vs Delta's ~$10 minimum perp order. "
         "Running in shadow mode, no orders placed."),
    ], st))

    story.append(PageBreak())

    for name in ("HANDOFF.md", "STATE.md"):
        path = os.path.join(HERE, name)
        if not os.path.exists(path):
            continue
        if name == "STATE.md":
            story.append(PageBreak())
            story.append(Paragraph("Appendix: STATE.md (live account state)",
                                   st["h1"]))
        with open(path) as f:
            body = f.read()
        # strip the YAML-ish header block from HANDOFF if present
        lines = body.splitlines()
        if lines and lines[0].startswith("#"):
            pass
        # render, converting pipe tables into real tables
        i = 0
        while i < len(lines):
            if lines[i].strip().startswith("|"):
                chunk = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    chunk.append(lines[i])
                    i += 1
                t = md_table("\n".join(chunk), st)
                story.append(t if t else Spacer(1, 3))
                story.append(Spacer(1, 5))
                continue
            i += 1
        story.extend(render_md(body, st))

    doc.build(story)
    size = os.path.getsize(OUT)
    print(f"wrote {OUT} ({size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
