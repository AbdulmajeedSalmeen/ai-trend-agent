import json

from src import retirements
from src.sources import changelogs

PAGE = """
<h3><span>2026-04-22: Legacy GPT model snapshots</span><button aria-label="Copy link"></button></h3>
<table><thead><tr><th>Shutdown date</th><th>Model snapshot</th><th>Substitute model</th></tr></thead>
<tbody>
<tr><td>October 23, 2026</td><td><code>gpt-3.5-turbo-0125</code> | <code>gpt-3.5-turbo</code>, <code>gpt-3.5-turbo-completions</code></td><td><code>gpt-5.6-terra</code></td></tr>
<tr><td>Oct 1, 2026</td><td><code>o1-pro-2025-03-19</code> | <code>o1-pro</code></td><td><code>gpt-5.6-sol</code> (<code>reasoning.mode: pro</code>)</td></tr>
</tbody></table>
<h3><span>2025-09-26: Legacy GPT model snapshots</span></h3>
<table><tr><th>Shutdown date</th><th>Model / system</th><th>Recommended replacement</th></tr>
<tr><td>2026-09-28</td><td><code>gpt-3.5-turbo-instruct</code></td><td><code>gpt-5.6-terra</code></td></tr>
<tr><td>2026-09-28</td><td><code>gpt-3.5-turbo</code></td><td><code>gpt-5.6-terra</code></td></tr>
</table>
<h3><span>2024-06-06: Prices</span></h3>
<table><tr><th>Deprecated model</th><th>Deprecated model price</th></tr><tr><td>x</td><td>$1</td></tr></table>
"""


def test_every_row_keeps_its_date_its_ids_with_aliases_and_the_replacement():
    rows = changelogs.openai_deprecations(PAGE)

    assert rows[0] == {"shutdown": "2026-10-23", "announced": "2026-04-22",
                       "section": "2026-04-22: Legacy GPT model snapshots",
                       "ids": ["gpt-3.5-turbo-0125", "gpt-3.5-turbo", "gpt-3.5-turbo-completions"],
                       "replacement": "gpt-5.6-terra"}
    assert rows[1]["shutdown"] == "2026-10-01" and rows[1]["replacement"] == "gpt-5.6-sol"


def test_an_id_listed_again_under_an_older_announcement_keeps_the_newest_row():
    rows = changelogs.openai_deprecations(PAGE)
    dates = {model: row["shutdown"] for row in rows for model in row["ids"]}

    assert dates["gpt-3.5-turbo"] == "2026-10-23"
    assert sum(model == "gpt-3.5-turbo" for row in rows for model in row["ids"]) == 1


def test_a_table_with_no_shutdown_date_is_not_a_deprecation():
    rows = changelogs.openai_deprecations(PAGE)

    assert all(row["section"] != "2024-06-06: Prices" for row in rows)


def test_dates_are_read_in_every_way_the_page_writes_them():
    assert changelogs.parse_date("2026-09-28") == "2026-09-28"
    assert changelogs.parse_date("Oct 1, 2026") == "2026-10-01"
    assert changelogs.parse_date("October 23, 2026") == "2026-10-23"
    assert changelogs.parse_date("Sept 3, 2026") == "2026-09-03"
    assert changelogs.parse_date("soon") is None


def test_a_refresh_writes_the_page_and_keeps_the_defaults_read_from_the_source(tmp_path):
    path = tmp_path / "retirements.json"
    path.write_text(json.dumps({"retirements": [{"shutdown": "2026-09-28", "announced": "2025-09-26",
                                                 "ids": ["gpt-3.5-turbo-instruct"], "replacement": "x"},
                                                {"shutdown": "2025-01-01", "announced": "2024-01-01",
                                                 "ids": ["gone-model"], "replacement": "y"}],
                                "defaults": {"OpenAI": {"model": "gpt-3.5-turbo-instruct"}}}), encoding="utf-8")

    data, changed = retirements.refresh(lambda url: PAGE, path)
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved == json.loads(json.dumps(data))
    assert saved["defaults"] == {"OpenAI": {"model": "gpt-3.5-turbo-instruct"}}
    assert "gpt-3.5-turbo" in changed["added"] and changed["removed"] == ["gone-model"]


def test_a_page_with_nothing_to_read_leaves_the_table_on_file(tmp_path):
    path = tmp_path / "retirements.json"
    path.write_text('{"retirements": []}', encoding="utf-8")

    try:
        retirements.refresh(lambda url: "<p>maintenance</p>", path)
    except SystemExit:
        pass

    assert path.read_text(encoding="utf-8") == '{"retirements": []}'
