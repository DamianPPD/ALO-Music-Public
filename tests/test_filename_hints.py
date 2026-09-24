from audio_library_organizer.metadata.filename_hints import artist_search_variants, parse_filename_hint, title_search_variants


def test_parse_filename_hint_extracts_artist_and_keeps_full_version_text():
    artist, title = parse_filename_hint('Abuna E - Watch Me (Double M & D. Bone Mix) - EKWADOR MANIECZKI')
    assert artist == 'Abuna E'
    assert title == 'Watch Me (Double M & D. Bone Mix) - EKWADOR MANIECZKI'


def test_parse_filename_hint_ignores_number_only_filename():
    assert parse_filename_hint('34') == (None, None)


def test_title_search_variants_adds_conservative_trailing_suffix_fallback():
    variants = title_search_variants('Watch Me (Double M & D. Bone Mix) - EKWADOR MANIECZKI')
    assert variants[0] == 'Watch Me (Double M & D. Bone Mix) - EKWADOR MANIECZKI'
    assert 'Watch Me (Double M & D. Bone Mix)' in variants


def test_parse_filename_bpm_hint_reads_suffix_without_changing_identity():
    from audio_library_organizer.metadata.filename_hints import parse_filename_bpm

    stem = 'Armani & Ghost - Airport (Original Mix) [139bpm]'
    assert parse_filename_bpm(stem) == 139.0
    assert parse_filename_hint(stem) == ('Armani & Ghost', 'Airport (Original Mix)')


def test_radio_timestamp_prefix_is_removed_before_artist_title_split():
    artist, title = parse_filename_hint('12-07-56 - RELOCATE - Built To Last (Ferry Tayle rmx)')
    assert artist == 'RELOCATE'
    assert title == 'Built To Last (Ferry Tayle Remix)'


def test_relocate_artist_search_alias_is_non_destructive():
    assert artist_search_variants('Relocate') == ['Relocate', 'Re:Locate']
    assert artist_search_variants('Re:Locate') == ['Re:Locate', 'Relocate']


def test_rmx_search_variant_keeps_original_first_and_adds_remix_form():
    variants = title_search_variants('Built To Last (Ferry Tayle rmx)')
    assert variants[0] == 'Built To Last (Ferry Tayle rmx)'
    assert 'Built To Last (Ferry Tayle Remix)' in variants
