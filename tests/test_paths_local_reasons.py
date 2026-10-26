"""Engine 0.8.1 says why a Paths probe never left this computer
(local_failure_reasons, error name and code) and how many flows it started
over on a new source port (flows_restarted, Windows). The notes under the
Paths list name both; a result from an older engine reads as before."""
from routemap.gui import hoptable


def test_the_note_names_why_probes_could_not_be_sent():
    notes = hoptable.path_notes({"local_failures": 20, "local_failure_reasons": {"WSAEACCES 10013": 20}})
    assert "20 probes could not be sent by this computer (WSAEACCES 10013); they are not counted as loss." in notes


def test_two_reasons_are_listed_commonest_first_with_their_counts():
    notes = hoptable.path_notes({"local_failures": 5,
                                 "local_failure_reasons": {"WSAENETUNREACH 10051": 1, "WSAEACCES 10013": 4}})
    assert "5 probes could not be sent by this computer (WSAEACCES 10013: 4, WSAENETUNREACH 10051: 1); " \
           "they are not counted as loss." in notes


def test_restarted_flows_are_noted():
    notes = hoptable.path_notes({"flows_restarted": 1})
    assert "1 flow was probed again from hop 1 on a new source port (another program took its port)." in notes


def test_a_result_from_an_older_engine_reads_as_before():
    notes = hoptable.path_notes({"local_failures": 3})
    assert "3 probes could not be sent by this computer; they are not counted as loss." in notes
    assert not any("source port" in n for n in notes)
