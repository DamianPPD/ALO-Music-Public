from pathlib import Path

from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.metadata.change_history import ChangeHistory


def test_history_restores_single_track_snapshot(tmp_path: Path):
    track = TrackRecord(path=tmp_path/'a.mp3', artist='Old', title='Song', status='review', bpm=120)
    history = ChangeHistory()
    history.record([track], 'Edycja metadanych')
    track.artist = 'New'
    track.bpm = 128
    track.status = 'ready'
    track.locked_fields.update({'artist', '__status__'})

    action = history.undo_last([track])
    assert action is not None
    assert action.description == 'Edycja metadanych'
    assert track.artist == 'Old'
    assert track.bpm == 120
    assert track.status == 'review'
    assert track.locked_fields == set()


def test_history_restores_batch_action_atomically(tmp_path: Path):
    a = TrackRecord(path=tmp_path/'a.mp3', status='ready')
    b = TrackRecord(path=tmp_path/'b.mp3', status='duplicate')
    a.locked_fields.add('duplicate_primary')
    history = ChangeHistory()
    history.record([a, b], 'Wybór duplikatu')

    a.status = 'duplicate'; a.locked_fields.clear()
    b.status = 'ready'; b.locked_fields.add('duplicate_primary')

    action = history.undo_last([a, b])
    assert action is not None
    assert a.status == 'ready' and 'duplicate_primary' in a.locked_fields
    assert b.status == 'duplicate' and 'duplicate_primary' not in b.locked_fields


def test_history_for_track_does_not_mix_other_tracks(tmp_path: Path):
    a = TrackRecord(path=tmp_path/'a.mp3')
    b = TrackRecord(path=tmp_path/'b.mp3')
    history = ChangeHistory()
    history.record([a], 'A1')
    history.record([b], 'B1')
    history.record([a], 'A2')

    assert history.history_for(a) == ['A2', 'A1']
    assert history.history_for(b) == ['B1']


def test_history_restores_metadata_source_state(tmp_path: Path):
    track = TrackRecord(
        path=tmp_path/'a.mp3', artist='Tag Artist', cover_choice='source',
        field_sources={'artist': 'Tag'},
        field_source_values={'artist': {'Tag': 'Tag Artist', 'Discogs': 'Online Artist'}},
    )
    history = ChangeHistory(); history.record([track], 'Źródło metadanych')
    track.artist = 'Online Artist'
    track.field_sources['artist'] = 'Discogs'
    track.field_source_values['artist']['Ręcznie'] = 'Temporary'
    track.cover_choice = 'external'

    history.undo_last([track])

    assert track.artist == 'Tag Artist'
    assert track.field_sources == {'artist': 'Tag'}
    assert track.field_source_values == {'artist': {'Tag': 'Tag Artist', 'Discogs': 'Online Artist'}}
    assert track.cover_choice == 'source'
