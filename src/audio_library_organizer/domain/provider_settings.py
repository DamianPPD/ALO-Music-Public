from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ProviderSettings:
    acoustid_key: str = ''
    discogs_token: str = ''
    musicbrainz_contact: str = 'personal-use'
    auto_identify_after_scan: bool = False
    filename_template: str = '{Artist} - {Title} ({Version}) ({Year}) [{BPM}bpm]'
    contact_email: str = ''
    folder_organization: str = 'none'

    @classmethod
    def from_store(cls, store) -> 'ProviderSettings':
        auto = store.value('providers/auto_identify', False)
        if isinstance(auto, str):
            auto = auto.casefold() in {'1','true','yes','tak'}
        return cls(
            acoustid_key=str(store.value('providers/acoustid_key', '') or ''),
            discogs_token=str(store.value('providers/discogs_token', '') or ''),
            musicbrainz_contact=str(store.value('providers/musicbrainz_contact', 'personal-use') or 'personal-use'),
            auto_identify_after_scan=bool(auto),
            filename_template=str(store.value('ui/filename_template', '{Artist} - {Title} ({Version}) ({Year}) [{BPM}bpm]') or '{Artist} - {Title} ({Version}) ({Year}) [{BPM}bpm]'),
            contact_email=str(store.value('ui/contact_email', '') or ''),
            folder_organization=str(store.value('ui/folder_organization', 'none') or 'none') if str(store.value('ui/folder_organization', 'none') or 'none') in {'none','artist','genre'} else 'none',
        )

    def save(self, store) -> None:
        store.setValue('providers/acoustid_key', self.acoustid_key)
        store.setValue('providers/discogs_token', self.discogs_token)
        store.setValue('providers/musicbrainz_contact', self.musicbrainz_contact)
        store.setValue('providers/auto_identify', self.auto_identify_after_scan)
        store.setValue('ui/filename_template', self.filename_template)
        store.setValue('ui/contact_email', self.contact_email)
        store.setValue('ui/folder_organization', self.folder_organization if self.folder_organization in {'none','artist','genre'} else 'none')
