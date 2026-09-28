from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font

HEADERS = ["Matricule", "Full name", "Role", "Status", "Joined (UTC)", "Left (UTC)", "Duration (min)"]


def build_attendance_xlsx(title: str, rows: list[dict]) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Attendance"

    sheet.append([title])
    sheet["A1"].font = Font(bold=True, size=13)
    sheet.append([])
    sheet.append(HEADERS)
    for cell in sheet[3]:
        cell.font = Font(bold=True)

    for row in rows:
        sheet.append(
            [
                row["matricule"],
                row["full_name"],
                row["role"],
                row["status"],
                row["joined_at"],
                row["left_at"],
                row["duration_minutes"],
            ]
        )

    for column in sheet.columns:
        longest = max(len(str(cell.value)) if cell.value is not None else 0 for cell in column)
        sheet.column_dimensions[column[0].column_letter].width = min(longest + 2, 50)

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()