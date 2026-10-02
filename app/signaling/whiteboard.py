"""Shared whiteboard of a live class.

The lecturer draws; every stroke operation is applied here (so students who
join late get the whole board) and relayed to the other participants over the
signaling socket. Coordinates and widths are fractions of the board size
(0..1), so the board scales to any screen.
"""

from typing import Optional

MAX_STROKES = 2000
MAX_POINTS_PER_STROKE = 5000
MAX_POINTS_PER_MESSAGE = 500


class Whiteboard:
    def __init__(self) -> None:
        self.active = False
        self.strokes: list[dict] = []

    def state(self) -> dict:
        return {"type": "board_state", "active": self.active, "strokes": self.strokes}

    def apply(self, data: dict) -> Optional[dict]:
        """Applies one operation; returns the cleaned message to broadcast,
        or None when it is malformed."""
        op = data.get("op")
        if op in ("show", "hide"):
            self.active = op == "show"
            return {"type": "board", "op": op}
        if op == "clear":
            self.strokes.clear()
            return {"type": "board", "op": "clear"}
        if op == "undo":
            if self.strokes:
                self.strokes.pop()
            return {"type": "board", "op": "undo"}
        if op == "begin":
            stroke_id = data.get("id")
            color = data.get("color")
            width = data.get("width")
            points = _points(data.get("points"))
            if not isinstance(stroke_id, str) or not isinstance(color, int) or not _number(width) or points is None:
                return None
            stroke = {"id": stroke_id[:64], "color": color, "width": float(width), "points": points}
            self.strokes.append(stroke)
            del self.strokes[:-MAX_STROKES]
            return {"type": "board", "op": "begin", **stroke}
        if op == "extend":
            stroke_id = data.get("id")
            points = _points(data.get("points"))
            if not isinstance(stroke_id, str) or not points:
                return None
            for stroke in reversed(self.strokes):
                if stroke["id"] == stroke_id:
                    room = MAX_POINTS_PER_STROKE - len(stroke["points"])
                    stroke["points"].extend(points[: max(room, 0)])
                    break
            return {"type": "board", "op": "extend", "id": stroke_id, "points": points}
        return None


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _points(value) -> Optional[list[list[float]]]:
    if not isinstance(value, list) or len(value) > MAX_POINTS_PER_MESSAGE:
        return None
    points = []
    for p in value:
        if not (isinstance(p, list) and len(p) == 2 and _number(p[0]) and _number(p[1])):
            return None
        points.append([float(p[0]), float(p[1])])
    return points
