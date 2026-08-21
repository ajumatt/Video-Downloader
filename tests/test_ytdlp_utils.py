from videodownloader.ytdlp_utils import parse_extra_ytdlp_args


def test_empty_string_returns_no_extra_opts():
    opts, error = parse_extra_ytdlp_args("")

    assert opts == {}
    assert error is None


def test_valid_flag_produces_only_the_changed_opt():
    opts, error = parse_extra_ytdlp_args("--limit-rate 500K")

    assert error is None
    assert opts == {"ratelimit": 512000}


def test_unknown_flag_returns_an_error_and_no_opts():
    opts, error = parse_extra_ytdlp_args("--not-a-real-flag")

    assert opts is None
    assert "not-a-real-flag" in error


def test_unbalanced_quotes_return_an_error_and_no_opts():
    opts, error = parse_extra_ytdlp_args('--output "unterminated')

    assert opts is None
    assert error is not None
