#!/usr/bin/env python3
"""
DTIClaw PDF Writer
Generate a clean .pdf from a markdown file using ReportLab.
Supports: # / ## / ### headings, - / * bullets, numbered lists,
**bold** inline, and paragraphs.

Usage:
  python3 pdf_writer.py --title "Laporan" --author "Atok Tajuddin" \
      --input content.md --output report.pdf
"""
import argparse
import os
import re
import sys
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    ListFlowable, ListItem, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
    Table, TableStyle,
)

NAVY = colors.HexColor("#1A3C6E")
GREY = colors.HexColor("#666666")


def md_inline(text):
    # Escape XML, then re-apply **bold** as ReportLab <b> tags.
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)


def build(title, author, content_file, output_file):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("DTITitle", parent=styles["Title"], fontSize=24, textColor=NAVY, spaceAfter=18))
    styles.add(ParagraphStyle("DTIMeta", parent=styles["Normal"], fontSize=11, textColor=GREY, alignment=TA_CENTER))
    styles.add(ParagraphStyle("H1", parent=styles["Heading1"], textColor=NAVY, spaceBefore=14, spaceAfter=8))
    styles.add(ParagraphStyle("H2", parent=styles["Heading2"], textColor=NAVY, spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle("H3", parent=styles["Heading3"], spaceBefore=8, spaceAfter=4))
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=11, leading=16, spaceAfter=6)

    story = [Spacer(1, 5 * cm), Paragraph(md_inline(title), styles["DTITitle"])]
    for line in (f"Author: {author}", f"Tanggal: {datetime.now().strftime('%d %B %Y')}", "Dihasilkan oleh DTIClaw 🦞"):
        story.append(Paragraph(line, styles["DTIMeta"]))
    story.append(PageBreak())

    if content_file and os.path.exists(content_file):
        with open(content_file, encoding="utf-8") as f:
            lines = f.read().split("\n")
        bullets, trows = [], []
        cell = ParagraphStyle("Cell", parent=body, fontSize=9, leading=12, spaceAfter=0)
        chead = ParagraphStyle("CellHead", parent=cell, textColor=colors.white)

        def flush_bullets():
            nonlocal bullets
            if bullets:
                story.append(ListFlowable([ListItem(Paragraph(md_inline(b), body)) for b in bullets], bulletType="bullet"))
                bullets = []

        def flush_table():
            nonlocal trows
            if trows:
                ncol = max(len(r) for r in trows)
                data = [[Paragraph(md_inline(c), chead if ri == 0 else cell)
                         for c in (row + [""] * (ncol - len(row)))]
                        for ri, row in enumerate(trows)]
                t = Table(data, repeatRows=1, hAlign="LEFT")
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("GRID", (0, 0), (-1, -1), 0.5, GREY),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF2F7")]),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]))
                story.append(Spacer(1, 4)); story.append(t); story.append(Spacer(1, 6))
                trows = []

        def flush_all():
            flush_bullets(); flush_table()

        for raw in lines:
            line = raw.rstrip()
            s = line.strip()
            # Tabel Markdown: kumpulkan baris '|...|', lewati baris pemisah '|---|'
            if s.startswith("|"):
                if not (set(s) <= set("|-: ")):
                    trows.append([c.strip() for c in s.strip("|").split("|")])
                continue
            flush_table()  # baris non-tabel mengakhiri blok tabel
            if s.startswith("### "):
                flush_bullets(); story.append(Paragraph(md_inline(s[4:]), styles["H3"]))
            elif s.startswith("## "):
                flush_bullets(); story.append(Paragraph(md_inline(s[3:]), styles["H2"]))
            elif s.startswith("# "):
                flush_bullets(); story.append(Paragraph(md_inline(s[2:]), styles["H1"]))
            elif s.startswith(("- ", "* ")):
                bullets.append(s[2:])
            elif re.match(r"^\d+\.\s", s):
                bullets.append(re.sub(r"^\d+\.\s", "", s))
            elif not s:
                flush_bullets()
            else:
                flush_bullets(); story.append(Paragraph(md_inline(s), body))
        flush_all()

    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    SimpleDocTemplate(
        output_file, pagesize=A4,
        topMargin=2.5 * cm, bottomMargin=2.5 * cm, leftMargin=3 * cm, rightMargin=3 * cm,
        title=title, author=author,
    ).build(story)
    print(f"✅ PDF saved: {output_file}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="DTIClaw PDF writer")
    ap.add_argument("--title", required=True)
    ap.add_argument("--author", default="Atok Tajuddin")
    ap.add_argument("--input", help="Markdown content file")
    ap.add_argument("--output", required=True, help="Output .pdf path")
    args = ap.parse_args()
    if args.input and not os.path.exists(args.input):
        sys.exit(f"ERROR: input not found: {args.input}")
    build(args.title, args.author, args.input, args.output)
