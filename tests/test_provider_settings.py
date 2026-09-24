from audio_library_organizer.domain.provider_settings import ProviderSettings


class Store:
    def __init__(self): self.d={}
    def value(self,k,default=None): return self.d.get(k,default)
    def setValue(self,k,v): self.d[k]=v


def test_provider_settings_roundtrip():
    s=Store(); cfg=ProviderSettings('ak','dt','me@example.com',True); cfg.save(s)
    out=ProviderSettings.from_store(s)
    assert out == cfg


def test_provider_settings_persist_filename_template_and_contact_email():
    s = Store()
    cfg = ProviderSettings(
        acoustid_key='ak', discogs_token='dt', musicbrainz_contact='me@example.com', auto_identify_after_scan=False,
        filename_template='{Year} - {Artist} - {Title}', contact_email='damian@example.com',
    )
    cfg.save(s)
    out = ProviderSettings.from_store(s)
    assert out.filename_template == '{Year} - {Artist} - {Title}'
    assert out.contact_email == 'damian@example.com'
