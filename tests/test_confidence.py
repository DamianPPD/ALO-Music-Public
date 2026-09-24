def test_confidence_presentation_uses_shared_thresholds():
    from audio_library_organizer.ui.confidence import confidence_presentation

    high = confidence_presentation(.95)
    medium = confidence_presentation(.75)
    low = confidence_presentation(.24)
    none = confidence_presentation(None)

    assert (high.percent, high.label, high.kind) == (95, 'WYSOKA', 'high')
    assert (medium.percent, medium.label, medium.kind) == (75, 'ŚREDNIA', 'medium')
    assert (low.percent, low.label, low.kind) == (24, 'NISKA', 'low')
    assert none.kind == 'none'
