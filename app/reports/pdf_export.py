from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

TABLE_STYLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]
)


def build_attendance_pdf(title: str, sections: list) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=landscape(A4))
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"])]
    for name, headers, rows in sections:
        if len(sections) > 1:
            story += [Spacer(1, 12), Paragraph(name, styles["Heading2"])]
        story.append(Spacer(1, 6))
        if rows:
            table = Table([headers] + [[str(v) for v in row] for row in rows], repeatRows=1)
            table.setStyle(TABLE_STYLE)
            story.append(table)
        else:
            story.append(Paragraph("No attendance recorded yet.", styles["Normal"]))
    document.build(story)
    return buffer.getvalue()