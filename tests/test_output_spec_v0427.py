"""Stage6.2A: partial mismatch is evidence, partial equality never is currentness."""
from dataclasses import replace
import importlib
import importlib.util
from pathlib import Path

import pytest
from mutagen.id3 import ID3, TIT2, TRCK, TPOS, WXXX
from audio_adoption_fixtures import mp3_samples, copy_audio
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.domain.file_state import evaluate_file_state, FileState
from test_file_state_v0427 import api as state_api, state_facts


def api():
    name = 'audio_library_organizer.metadata.mp3_output'
    assert importlib.util.find_spec(name), 'Missing shared MP3 OutputSpec producer'
    return importlib.import_module(name)


def applied(**tags):
    return {'version': 1, 'tag_snapshot': tags}


@pytest.mark.parametrize('field,old,new', [('artist','Old','New'),('album','Before','After')])
def test_explicit_changed_required_field_is_positive_difference(field, old, new):
    m = api(); track = TrackRecord(Path('/synthetic.mp3'), **{field:new})
    result = m.compare_specs(m.build_mp3_spec(track), m.observed_adoption_spec(applied(**{field:old})))
    assert [d.field for d in result.differences] == [field]
    assert not result.complete_match


@pytest.mark.parametrize('field', ['artist','album','title','year','genre','bpm','comment'])
def test_empty_writer_fields_preserve_and_do_not_invent_required_deletion(field):
    m = api(); spec = m.build_mp3_spec(TrackRecord(Path('/synthetic.mp3')))
    assert spec.field(field).action.value == 'PRESERVE'
    assert not m.compare_specs(spec, m.observed_adoption_spec(applied(**{field:'existing'}))).differences


@pytest.mark.parametrize('bpm,title,expected_bpm,expected_title', [
    (128.6,'Tune [80bpm]','129','Tune [129bpm]'),
    (128.5,'Tune','128','Tune [128bpm]'),
    (None,'Tune [80bpm]',None,'Tune'),
])
def test_shared_transformations_match_real_writer(mp3_samples, tmp_path, bpm, title, expected_bpm, expected_title):
    m = api()
    from audio_library_organizer.metadata.tag_writer import write_resolved_tags, build_title_tag
    from audio_library_organizer.audio.identity import _tags
    path = copy_audio(mp3_samples['original'], tmp_path/'out.mp3')
    track = TrackRecord(path, title=title, bpm=bpm, artist='Writer artist')
    spec = m.build_mp3_spec(track)
    assert spec.field('title').value == expected_title == build_title_tag(track)
    assert spec.field('bpm').value == expected_bpm
    write_resolved_tags(path, track)
    observed = _tags(path)
    assert observed['title'] == expected_title
    assert observed['bpm'] == (expected_bpm or '')
    assert not m.compare_specs(spec, m.observed_adoption_spec(applied(**observed))).differences


def test_numbering_and_discogs_directives_match_actual_writer(mp3_samples,tmp_path):
    m = api()
    from audio_library_organizer.metadata.tag_writer import write_resolved_tags
    p = copy_audio(mp3_samples['original'],tmp_path/'out.mp3')
    tags=ID3(p);tags.add(TRCK(encoding=3,text=['7']));tags.add(TPOS(encoding=3,text=['2']))
    tags.add(WXXX(encoding=3,desc='Discogs',url='https://example.invalid/old'));tags.save(p)
    track=TrackRecord(p)
    spec=m.build_mp3_spec(track)
    assert all(spec.field(k).action.value=='REMOVE' for k in ('track_number','disc_number','discogs_url'))
    write_resolved_tags(p,track);tags=ID3(p)
    assert not tags.getall('TRCK') and not tags.getall('TPOS') and not tags.getall('WXXX')
    track.discogs_url='https://example.invalid/new'
    assert m.build_mp3_spec(track).field('discogs_url').value==track.discogs_url
    write_resolved_tags(p,track)
    assert tags.getall('WXXX')==[] and ID3(p).getall('WXXX')[0].url==track.discogs_url


def test_cover_requires_resolved_bytes_not_path_and_routing_defaults_unknown(tmp_path):
    m=api();p=tmp_path/'cover';p.write_bytes(b'cover-v1');t=TrackRecord(Path('/song.mp3'),manual_cover_path=str(p))
    assert m.build_mp3_spec(t).field('cover_sha256').action.value=='UNKNOWN'
    a=m.build_mp3_spec(t,cover_bytes=p.read_bytes());p.write_bytes(b'cover-v2')
    b=m.build_mp3_spec(t,cover_bytes=p.read_bytes())
    assert a.field('cover_sha256').value!=b.field('cover_sha256').value
    assert a.field('relative_path').action.value=='UNKNOWN'
    assert m.build_mp3_spec(t,relative_path='GOTOWE/song.mp3').field('relative_path').value=='GOTOWE/song.mp3'


def test_empty_cover_bytes_do_not_claim_a_written_empty_cover():
    m=api()
    assert m.build_mp3_spec(TrackRecord(Path('/song.mp3')),cover_bytes=b'').field('cover_sha256').action.value=='UNKNOWN'


def test_partial_match_and_unsupported_contract_never_mean_full_match():
    m=api();a=m.build_mp3_spec(TrackRecord(Path('/song.mp3'),artist='Same'))
    b=m.observed_adoption_spec(applied(artist='Same'))
    assert not m.compare_specs(a,b).differences and not m.compare_specs(a,b).complete_match
    assert not m.compare_specs(a,replace(b,version=999)).differences
    assert not m.compare_specs(a,replace(b,namespace='foreign')).complete_match
    assert not m.observed_adoption_spec({'version':999,'tag_snapshot':{'artist':'Other'}}).complete


def test_evaluator_requires_fresh_owned_present_identity_for_partial_difference():
    m=api();state=state_api();facts=replace(state_facts(state,'IN_LIBRARY'),desired=None,applied=None)
    comparison=m.compare_specs(m.build_mp3_spec(TrackRecord(Path('/song.mp3'),artist='New')),
                               m.observed_adoption_spec(applied(artist='Old')))
    difference=comparison.as_difference(facts.track_id,facts.checked_at)
    result=evaluate_file_state(facts,difference=difference)
    assert result.state==FileState.NEEDS_UPDATE and result.is_confirmed
    assert evaluate_file_state(facts).state is None
    for change in ({'track_id':'other'},{'checked_at':facts.checked_at-1}):
        r=evaluate_file_state(facts,difference=replace(difference,**change))
        assert not r.is_confirmed
    assert not evaluate_file_state(replace(facts,is_current=False),difference=difference).is_confirmed
    assert evaluate_file_state(replace(facts,conflict=state.ConflictReason.TARGET_COLLISION),difference=difference).state==FileState.CONFLICT
    assert not evaluate_file_state(replace(facts,ownership=state.Ownership.UNKNOWN),difference=difference).is_confirmed
    for availability in ('UNKNOWN','OFFLINE','ERROR'):
        bad=replace(facts,managed=replace(facts.managed,availability=state.FileAvailability[availability]))
        assert not evaluate_file_state(bad,difference=difference).is_confirmed


def test_zero_difference_cannot_be_encoded_as_positive_proof():
    m=api();result=m.compare_specs(m.build_mp3_spec(TrackRecord(Path('/a.mp3'),artist='Same')),
                                  m.observed_adoption_spec(applied(artist='Same')))
    assert result.as_difference('track',10) is None


def test_arbitrary_subset_is_not_a_complete_spec():
    m=api()
    from audio_library_organizer.domain.output_spec import OutputSpec, OutputField, FieldAction
    subset=OutputSpec((OutputField('artist',FieldAction.SET,'Same'),))
    assert not subset.complete
    assert not m.compare_specs(subset,subset).complete_match


def test_legacy_v1_extra_fields_cannot_extend_its_actual_coverage():
    m=api();spec=m.observed_adoption_spec(applied(track_number='7',disc_number='2',discogs_url='unattested'))
    assert all(spec.field(k).action.value=='UNKNOWN' for k in ('track_number','disc_number','discogs_url'))


@pytest.mark.parametrize('field,value',[('genre','17'),('genre','(17)'),('year','2024-1'),
    ('year','2024-01-01T01:02:03Z'),('artist','A\x00B')])
def test_mutagen_serialized_values_do_not_report_a_just_written_file_as_changed(mp3_samples,tmp_path,field,value):
    m=api()
    from audio_library_organizer.metadata.tag_writer import write_resolved_tags
    from audio_library_organizer.audio.identity import _tags
    p=copy_audio(mp3_samples['original'],tmp_path/'out.mp3')
    track=TrackRecord(p,**{field:value})
    write_resolved_tags(p,track)
    observed=m.observed_adoption_spec(applied(**_tags(p)))
    result=m.compare_specs(m.build_mp3_spec(track),observed)
    assert not result.differences


@pytest.mark.parametrize('url',['https://example.invalid/ok','https://example.invalid/a\x00ignored'])
def test_discogs_value_uses_the_real_id3_url_serialization(mp3_samples,tmp_path,url):
    m=api()
    from audio_library_organizer.metadata.tag_writer import write_resolved_tags
    p=copy_audio(mp3_samples['original'],tmp_path/'url.mp3');track=TrackRecord(p,discogs_url=url)
    write_resolved_tags(p,track)
    assert m.build_mp3_spec(track).field('discogs_url').value==ID3(p).getall('WXXX')[0].url


def test_unserializable_discogs_url_remains_unknown_without_changing_writer(mp3_samples,tmp_path):
    m=api()
    from audio_library_organizer.metadata.tag_writer import write_resolved_tags
    p=copy_audio(mp3_samples['original'],tmp_path/'url.mp3')
    track=TrackRecord(p,discogs_url='https://example.invalid/żółć')
    assert m.build_mp3_spec(track).field('discogs_url').action.value=='UNKNOWN'
    with pytest.raises(UnicodeEncodeError):write_resolved_tags(p,track)
