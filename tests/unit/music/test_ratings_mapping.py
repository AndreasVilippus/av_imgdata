from music.ratings_mapping import normalize_rating, popm_to_stars


def test_windows_popm_mapping_matches_pg_php():
    assert [popm_to_stars(value) for value in (1, 64, 128, 196, 255)] == [1, 2, 3, 4, 5]
    assert popm_to_stars("Rating=196 Count=0") == 4


def test_rating_formats_normalize_to_stars_and_percent():
    assert normalize_rating(196, "popm")["rating_stars"] == 4
    assert normalize_rating(80, "vorbis_rating")["rating_stars"] == 4
    assert normalize_rating("0.8", "fmps_rating")["rating_percent"] == 80
    assert normalize_rating(4.5, "stars")["rating_percent"] == 90


def test_unknown_or_invalid_rating_does_not_create_candidate():
    assert normalize_rating("not-a-rating", "popm")["rating_stars"] is None
    assert normalize_rating(7, "stars")["rating_stars"] is None
