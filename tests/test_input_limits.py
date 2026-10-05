"""Nothing the app reads is read without a ceiling (RM-12, app side): opened
and compared files over 1 MB, a DB-IP download larger than any real one or
redirected anywhere but https on db-ip.com, and a .gz that unpacks past the
database ceiling are all refused, and nothing is left behind."""
import gzip
import os

import httpx
import pytest

from routemap import cli, dbip, imported


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ROUTEMAP_CONFIG_DIR", str(tmp_path / "config"))


def _leftovers():
    d = dbip.data_dir()
    return [p.name for p in d.iterdir()] if d.exists() else []


def test_the_cli_refuses_a_trace_file_over_the_cap(tmp_path, capsys):
    big = tmp_path / "big.txt"
    big.write_bytes(b" 1  router (10.0.0.1)  1.0 ms\n" * (imported.MAX_FILE_BYTES // 20))
    assert cli.main(["parse", str(big), "--offline", "--origin", "Manila, PH"]) == 2
    assert "KB" in capsys.readouterr().err


@pytest.mark.parametrize("location", [
    "http://download.db-ip.com/free/x.mmdb.gz",          # downgraded to http
    "https://download.db-ip.com.example.net/x.mmdb.gz",  # look-alike host
    "https://example.net/x.mmdb.gz",                     # elsewhere
    "file:///etc/passwd",                                # another scheme
], ids=["http", "lookalike", "elsewhere", "file"])
def test_a_download_redirected_anywhere_but_https_db_ip_is_refused(location):
    asked = []

    def handler(request):
        asked.append(str(request.url))
        if request.url.host == "download.db-ip.com" and request.url.scheme == "https":
            return httpx.Response(302, headers={"location": location})
        return httpx.Response(200, content=b"x" * 10)

    with pytest.raises(dbip.DatabaseError):
        dbip.download("asn", user_agent="t", transport=httpx.MockTransport(handler))
    assert all(u.startswith("https://download.db-ip.com/") for u in asked), asked
    assert not _leftovers()


def test_a_download_larger_than_the_ceiling_stops(monkeypatch):
    monkeypatch.setattr(dbip, "MAX_PACKED_BYTES", 100_000, raising=False)
    sent = []

    def stream():
        for _ in range(1000):
            sent.append(1)
            yield b"\0" * 65536

    with pytest.raises(dbip.DatabaseError, match="larger"):
        dbip.download("asn", user_agent="t",
                      transport=httpx.MockTransport(lambda r: httpx.Response(200, content=stream())))
    assert len(sent) < 10, "stopped as soon as it passed the ceiling"
    assert not _leftovers()
    with pytest.raises(dbip.DatabaseError, match="larger"):
        dbip.download("asn", user_agent="t", transport=httpx.MockTransport(
            lambda r: httpx.Response(200, content=b"x", headers={"content-length": "10000000000"})))


def test_a_gzip_that_unpacks_past_the_ceiling_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(dbip, "MAX_UNPACKED_BYTES", 1_000_000, raising=False)
    bomb = tmp_path / "dbip-city-lite-2026-10.mmdb.gz"
    bomb.write_bytes(gzip.compress(b"\0" * 5_000_000))
    with pytest.raises(dbip.DatabaseError, match="larger"):
        dbip.import_file(bomb, "city")
    assert not _leftovers() or _leftovers() == []
    plain = tmp_path / "dbip-city-lite-2026-10.mmdb"
    plain.write_bytes(b"\0" * 2_000_000)
    with pytest.raises(dbip.DatabaseError, match="larger"):
        dbip.import_file(plain, "city")
    assert not [n for n in _leftovers() if n.startswith(".import")]
