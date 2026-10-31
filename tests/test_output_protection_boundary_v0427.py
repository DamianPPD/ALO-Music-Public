"""Real synthetic backend checks; boundary timing is not a native Win32 test."""
import inspect
from dataclasses import fields
import pytest
from audio_adoption_fixtures import mp3_samples
from test_legacy_adoption_v0427 import library
from test_adopted_output_spec_v0427 import approve,request
from test_output_reconciliation_v0427 import check,protected
from audio_library_organizer.jobs import file_reconciliation as reconciliation
from audio_library_organizer.jobs import adopted_output


def supported():
    assert 'before_output_check' in inspect.signature(reconciliation.check_library).parameters, 'SELECTED_OUTPUT_PROTECTION_BOUNDARY_MISSING'


def test_protection_factory_follows_inventory_and_precedes_real_selected_reads(library,monkeypatch):
    supported();binding=approve(library);events=[]
    from audio_library_organizer.jobs import legacy_adoption
    inventory=legacy_adoption.inventory_legacy_outputs;assessment=adopted_output.assess_adopted_mp3
    def observed_inventory(*a,**kw):
        result=inventory(*a,**kw);events.append('inventory-complete');return result
    def observed_assessment(*a,**kw):
        events.append('selected-assessment');return assessment(*a,**kw)
    def acquire():events.append('acquire-pair');return True
    monkeypatch.setattr(legacy_adoption,'inventory_legacy_outputs',observed_inventory)
    monkeypatch.setattr(adopted_output,'assess_adopted_mp3',observed_assessment)
    before=protected(library)
    result=check(library,binding,include_adoption=True,before_output_check=acquire)
    assert events==['inventory-complete','acquire-pair','selected-assessment']
    assert result.pending_output_assessment.assessment.guard
    assert protected(library)==before


def test_refused_factory_never_falls_back_to_an_unprotected_assessment(library,monkeypatch):
    supported();binding=approve(library);events=[]
    actual=adopted_output.assess_adopted_mp3
    def observe(*a,**kw):events.append('assessment');return actual(*a,**kw)
    monkeypatch.setattr(adopted_output,'assess_adopted_mp3',observe)
    result=check(library,binding,before_output_check=lambda:False)
    assert not events and result.pending_output_assessment is None and result.output_delivery is None


def test_factory_error_is_reported_and_does_not_start_unprotected_reads(library,monkeypatch):
    supported();binding=approve(library);events=[]
    def denied():events.append('denied');raise PermissionError('controlled protection refusal')
    before=protected(library)
    with pytest.raises(PermissionError,match='controlled protection refusal'):
        check(library,binding,before_output_check=denied)
    assert events==['denied'];assert protected(library)==before


def test_factory_without_a_pinned_request_is_rejected(library):
    supported();repo,root,_,_=library;events=[]
    with pytest.raises(ValueError,match='protection requires'):
        reconciliation.check_library(repo,library_root=root,before_output_check=lambda:events.append(True))
    assert not events


def test_history_copies_only_unconfirmed_data_and_pure_context(library):
    binding=approve(library);repo,root,track,_=library
    result=check(library,binding)
    from audio_library_organizer.jobs.output_session import prepare_delivery,history_from_delivery,history_matches
    pending=result.pending_output_assessment
    delivery=prepare_delivery(repo,root,pending,pending.request)
    assert delivery is not None
    history=history_from_delivery(delivery)
    assert not history.evaluation.is_confirmed
    assert not history.evaluation.safe_for_file_mutation
    assert history.evaluation.requires_revalidation
    assert not {'delivery','lease','windows_lease','handles','pending'} & {f.name for f in fields(history)}
    snapshot=repo.adopted_assessment_snapshot(track.track_id)
    assert history_matches(history,snapshot,root,pending.request.policy_revision)
    assert not history_matches(history,snapshot,root,'foreign-policy')
    assert not history_matches(history,snapshot,root/'foreign',pending.request.policy_revision)
