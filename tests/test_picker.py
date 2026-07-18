from qwik.ui.picker import _build_style


def test_picker_style_respects_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    style = _build_style()
    rules = dict(style.style_rules)
    assert rules.get("") == ""
    assert rules.get("dim") == ""