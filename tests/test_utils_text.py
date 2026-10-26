from ytkb.utils.text import (
    contains_normalized,
    fmt_duration,
    fmt_ts,
    fmt_ts_file,
    format_number_it,
    normalize_for_match,
    sanitize_filename,
)


def test_sanitize_filename_removes_windows_forbidden_and_emoji():
    assert sanitize_filename('🔥 BTC: "settimana" decisiva? | Parte 2/3') == "BTC_settimana_decisiva_Parte_2_3"


def test_sanitize_filename_keeps_accents_and_limits_length():
    name = sanitize_filename("Perché l'oro è salito " * 10, max_len=30)
    assert len(name) <= 30
    assert name.startswith("Perché_l_oro_è_salito")


def test_sanitize_filename_reserved_and_empty():
    assert sanitize_filename("CON") == "_CON"
    assert sanitize_filename("???") == "senza_titolo"


def test_time_formats():
    assert fmt_ts(0) == "00:00"
    assert fmt_ts(792) == "13:12"
    assert fmt_ts(3723) == "1:02:03"
    assert fmt_ts_file(798) == "13m18s"
    assert fmt_ts_file(3723) == "1h02m03s"
    assert fmt_duration(2520) == "42 min"
    assert fmt_duration(3900) == "1 h 05 min"


def test_normalize_for_match_numbers():
    assert normalize_for_match("Supporto dei 60.000, poi 1,5%") == "supporto dei 60000 poi 1.5"
    assert normalize_for_match("1.234.567") == "1234567"
    assert normalize_for_match("Perché") == "perche"


def test_contains_normalized_tolerates_formatting():
    hay = "come vedete qui il prezzo è tornato sul supporto dei 60000 dollari"
    assert contains_normalized(hay, "supporto dei 60.000")
    assert not contains_normalized(hay, "supporto dei 61.000")
    assert not contains_normalized(hay, "")


def test_format_number_it():
    assert format_number_it(60000) == "60.000"
    assert format_number_it(1.085) == "1,085"
    assert format_number_it(5821.25) == "5.821,25"
    assert format_number_it(0.00012345) == "0,000123"
    assert format_number_it(-42.5) == "-42,5"
