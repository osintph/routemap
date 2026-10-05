"""nginx configs in the repository: the rule that refuses hidden paths comes
before every other regex location (nginx tries regex locations in file order,
so a hidden ".env.txt" or ".git/README.md" was served by an earlier
"\\.(txt|asc|md)$" rule; RM-17)."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def regex_locations(text: str) -> list[str]:
    return re.findall(r"^\s*location\s+~\*?\s+(\S+)", text, flags=re.M)


def test_hidden_paths_are_refused_before_any_other_regex_location():
    confs = sorted(ROOT.glob("docs/**/*.conf"))
    checked = 0
    for conf in confs:
        text = conf.read_text(encoding="utf-8")
        locs = regex_locations(text)
        if not locs:
            continue
        checked += 1
        assert locs[0].startswith("/\\."), f"{conf.name}: first regex location is {locs[0]}, not the hidden-path deny"
        block = text[text.index(locs[0]):].split("}", 1)[0]
        assert "deny all" in block or "return 404" in block, f"{conf.name}: the first regex location does not refuse"
    assert checked, "no nginx config with regex locations found"


def _code(text: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in text.splitlines())


def test_server_headers_isolate_the_site_and_say_each_thing_once():
    """Hardening 11: Cross-Origin-Opener-Policy and Cross-Origin-Resource-Policy
    same-origin on every response, and no header or set_real_ip_from line twice."""
    checked = 0
    for conf in sorted(ROOT.glob("docs/**/*.conf")):
        code = _code(conf.read_text(encoding="utf-8"))
        real_ip = re.findall(r"^\s*set_real_ip_from\s+(\S+);", code, flags=re.M)
        assert len(real_ip) == len(set(real_ip)), f"{conf.name}: a set_real_ip_from line twice"
        for server in re.split(r"^server\s*\{", code, flags=re.M)[1:]:
            headers = re.findall(r"^\s*add_header\s+(\S+)\s+(.+?);", server, flags=re.M)
            if not headers:
                continue
            checked += 1
            names = [h[0].lower() for h in headers]
            assert len(names) == len(set(names)), f"{conf.name}: a header is added twice in one server"
            found = {n.lower(): v for n, v in headers}
            for name in ("cross-origin-opener-policy", "cross-origin-resource-policy"):
                value = found.get(name, "")
                assert value.startswith('"same-origin"') and value.endswith("always"), (conf.name, name)
    assert checked
