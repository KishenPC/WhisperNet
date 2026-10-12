"""Export the measured Markdown report and charts to a readable PDF."""

from html import escape
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle


def export(folder, destination=None):
    folder = Path(folder)
    destination = Path(destination) if destination else folder / "report.pdf"
    destination.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    styles["Title"].fontName = "Times-Bold"
    styles.add(ParagraphStyle("ReportBody", parent=styles["BodyText"], fontName="Times-Roman", fontSize=10.5, leading=14, spaceAfter=8))
    styles.add(ParagraphStyle("Cell", parent=styles["BodyText"], fontName="Times-Roman", fontSize=8, leading=10, alignment=TA_LEFT))
    styles["Heading1"].fontName = "Times-Bold"
    styles["Heading1"].textColor = colors.black
    styles["Heading1"].fontSize = 15
    styles["Heading1"].leading = 19
    styles["Heading1"].spaceBefore = 14
    styles["Heading1"].spaceAfter = 8
    styles["Heading1"].keepWithNext = True
    width = A4[0] - 36 * mm
    story, paragraph = [], []

    def markup(text):
        text = escape(text)
        text = re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', text)
        return text.replace(" -> ", " -&gt; ")

    def flush():
        if paragraph:
            story.append(Paragraph(markup(" ".join(paragraph)), styles["ReportBody"]))
            paragraph.clear()

    lines = (folder / "report.md").read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if line.startswith("|"):
            flush()
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                cells = [x.strip() for x in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", x) for x in cells):
                    rows.append([Paragraph(markup(x), styles["Cell"]) for x in cells])
                index += 1
            count = len(rows[0])
            # Leave more room for lengthy trial IDs and recovery status.
            fractions = [0.49, .15, .36] if count == 3 and "Trial" in rows[0][0].text else [1 / count] * count
            table = LongTable(rows, colWidths=[width * x for x in fractions], repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.white),
                                       ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                                       ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                                       ("LINEABOVE", (0, 0), (-1, 0), .7, colors.black),
                                       ("LINEBELOW", (0, 0), (-1, 0), .6, colors.black),
                                       ("LINEBELOW", (0, -1), (-1, -1), .6, colors.black)]))
            story.extend([table, Spacer(1, 8)])
            continue
        if line.startswith("# "):
            flush()
            story.append(Paragraph(markup(line[2:]), styles["Title"]))
        elif line.startswith("## "):
            flush()
            story.append(Paragraph(markup(line[3:]), styles["Heading1"]))
        elif line.startswith("- "):
            flush()
            story.append(Paragraph(markup(line[2:]), styles["ReportBody"], bulletText="-"))
        elif not line:
            flush()
        else:
            paragraph.append(line)
            if lines[index].endswith("  "):
                flush()
        index += 1
    flush()
    for name, caption in (("performance", "Reliability and verified goodput"),
                           ("adaptation", "Adaptation, estimator variability and verified frames"),
                           ("roc", "Descriptive ROC curves from captured arrival times"),
                           ("false-alarms", "False alarms during benign network and application drift")):
        story.extend([PageBreak(), Paragraph(caption, styles["Heading1"])])
        image = Image(str(folder / f"{name}.png"))
        factor = min(width / image.imageWidth, 220 * mm / image.imageHeight)
        image.drawWidth, image.drawHeight = image.imageWidth * factor, image.imageHeight * factor
        story.append(image)

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.black)
        canvas.setFont("Times-Roman", 8)
        canvas.drawString(18 * mm, 12 * mm, "WhisperNet | BCSE308P | Draft")
        canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, str(doc.page))
        canvas.restoreState()

    SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                      topMargin=18 * mm, bottomMargin=20 * mm,
                      title="WhisperNet project report (draft)", author="Kishen Pathiyan Cherumanal and Aarav Gupta").build(story, onFirstPage=footer, onLaterPages=footer)
    return destination
