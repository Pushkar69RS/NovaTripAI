"""demo_up.py creates the three demo trips once; a second run finds them."""

from __future__ import annotations

import demo_up


class Calls:
    def __init__(self) -> None:
        self.created: list[str] = []
        self.found: dict[str, str] = {}

    def find_demo(self, conn):
        return self.found.get("canonical")

    def find(self, conn, key, status):
        return self.found.get("mangalore" if "Mangalore" in str(key) else "nofit")

    def create(self, request, conn, owner, llm=None):
        name = (
            "canonical"
            if request.places == ["Mysuru", "Srirangapatna"]
            else "mangalore"
            if request.destination_cities == ["Mangalore"]
            else "nofit"
        )
        self.created.append(name)
        self.found[name] = f"id-{name}"
        return {"id": f"id-{name}", "status": "planned", "cold_start": []}


def test_a_second_run_creates_nothing(monkeypatch) -> None:
    calls = Calls()
    monkeypatch.setattr(demo_up, "find_demo_trip", calls.find_demo)
    monkeypatch.setattr(demo_up, "find_trip", calls.find)
    monkeypatch.setattr(demo_up, "create", calls.create)
    first = demo_up.ensure_trips(object(), 4, llm=lambda *a, **k: None)
    assert calls.created == ["canonical", "mangalore", "nofit"]
    second = demo_up.ensure_trips(object(), 4, llm=lambda *a, **k: None)
    assert calls.created == ["canonical", "mangalore", "nofit"]  # nothing new
    assert (
        first
        == second
        == {
            "canonical": "id-canonical",
            "mangalore": "id-mangalore",
            "nofit": "id-nofit",
        }
    )


def test_a_failing_model_skips_mangalore_and_carries_on(monkeypatch, capsys) -> None:
    calls = Calls()

    def create(request, conn, owner, llm=None):
        if request.destination_cities == ["Mangalore"]:
            raise RuntimeError("no network")
        return calls.create(request, conn, owner)

    monkeypatch.setattr(demo_up, "find_demo_trip", calls.find_demo)
    monkeypatch.setattr(demo_up, "find_trip", calls.find)
    monkeypatch.setattr(demo_up, "create", create)
    ids = demo_up.ensure_trips(object(), 4, llm=lambda *a, **k: None)
    assert ids["mangalore"] is None and ids["nofit"] == "id-nofit"
    assert "Mangalore demo skipped: no network" in capsys.readouterr().out


def test_the_cue_sheet_has_five_lines(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(demo_up, "ROOT", tmp_path)
    lines = demo_up.cue_sheet({"canonical": "a", "mangalore": None, "nofit": "c"})
    assert (
        len(lines) == 5
        and "(skipped)" in lines[1]
        and lines[4].endswith("rohan@travelyantra.in")
    )
    assert (tmp_path / "var" / "cue.txt").read_text(encoding="utf-8").count("\n") == 5
