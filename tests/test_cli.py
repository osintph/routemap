import json
import pathlib

from routemap import cli

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "routemap"


def test_parse_prints_the_route_model(capsys):
    code = cli.main(["parse", str(FIXTURES / "heise_traceroute.txt"),
                     "--origin", "14.6,121.0", "--offline"])
    assert code == 0
    body = json.loads(capsys.readouterr().out)
    assert body["parser"] == "traceroute" and len(body["hops"]) == 16


def test_parse_accepts_a_city_as_origin(capsys):
    assert cli.main(["parse", str(FIXTURES / "amazon_tracert.txt"),
                     "--origin", "Manila", "--offline"]) == 0
    assert json.loads(capsys.readouterr().out)["origin"]["label"].startswith("Manila")


def test_parse_reports_text_that_is_not_a_trace(tmp_path, capsys):
    junk = tmp_path / "junk.txt"
    junk.write_text("hello\n")
    assert cli.main(["parse", str(junk), "--offline"]) == 1
    assert "could not read" in capsys.readouterr().err
