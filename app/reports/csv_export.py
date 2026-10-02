import csv
from io import StringIO


def build_attendance_csv(title: str, sections: list) -> bytes:
    """Sections one after another, separated by an empty line."""
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([title])
    for i, (name, headers, rows) in enumerate(sections):
        if len(sections) > 1:
            if i:
                writer.writerow([])
            writer.writerow([name])
        writer.writerow(headers)
        writer.writerows(rows)
    # BOM so spreadsheet apps detect UTF-8 names correctly.
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")