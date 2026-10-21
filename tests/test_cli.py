import json

from factguard.cli import main


def write(tmp_path, draft):
    facts = tmp_path / "facts.json"
    facts.write_text(json.dumps({"currency": "INR", "facts": [{"key": "spend", "value": 60000, "kind": "money"}]}))
    path = tmp_path / "draft.txt"
    path.write_text(draft)
    return str(facts), str(path)


def test_check_clean(tmp_path, capsys):
    facts, draft = write(tmp_path, "Spend was {{fact:spend}} over the last 28 days.")
    assert main(["check", draft, "--facts", facts, "--window", "2026-09-01:2026-09-28"]) == 0
    assert capsys.readouterr().out == ""


def test_check_reports_line_numbers(tmp_path, capsys):
    facts, draft = write(tmp_path, "Spend was {{fact:spend}}.\nUp 40%.\n")
    assert main(["check", draft, "--facts", facts]) == 1
    assert capsys.readouterr().out == f"{draft}:2: literal_number: `40%`: " + (
        "this is a number you typed. Cite it with a {{fact:...}} placeholder, or say it without the figure.\n"
    )


def test_check_json(tmp_path, capsys):
    facts, draft = write(tmp_path, "Up 40%.")
    assert main(["check", draft, "--facts", facts, "--json"]) == 1
    (v,) = json.loads(capsys.readouterr().out)
    assert v["kind"] == "literal_number" and v["start"] == 3


def test_render(tmp_path, capsys):
    facts, draft = write(tmp_path, "Spend was INR {{fact:spend}}.")
    assert main(["render", draft, "--facts", facts]) == 0
    assert capsys.readouterr().out == "Spend was INR 60K."


def test_render_unknown(tmp_path, capsys):
    facts, draft = write(tmp_path, "{{fact:nope}}")
    assert main(["render", draft, "--facts", facts]) == 1
    assert "nope" in capsys.readouterr().err
