from lectern.report_charts import bar_chart, histogram


def test_bar_chart_scales_to_max():
    out = bar_chart([("A", 13), ("B", 6), ("F", 3)], max_w=10)
    lines = out.splitlines()
    assert lines[0].startswith("A ▏") and lines[0].endswith(" 13")
    # max value gets the full bar width
    assert "█" * 10 in lines[0]
    # zero-safe: smaller bars are proportionally shorter
    assert lines[1].count("█") < lines[0].count("█")


def test_bar_chart_handles_zero():
    out = bar_chart([("D", 0), ("A", 5)], max_w=8)
    assert out.splitlines()[0].strip().endswith("0")
    assert "█" not in out.splitlines()[0]


def test_histogram_bins_inclusive_last():
    bins = [("<70", 0, 70), ("70-79", 70, 80), ("80-89", 80, 90), ("90-100", 90, 100)]
    out = histogram([100, 95, 90, 84, 70, 43], bins, max_w=10)
    rows = {l.split("▏")[0].strip(): l for l in out.splitlines()}
    assert rows["90-100"].endswith(" 3")   # 100,95,90
    assert rows["70-79"].endswith(" 1")    # 70
    assert rows["<70"].endswith(" 1")      # 43
