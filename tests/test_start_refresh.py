import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication, QFrame, QLabel

from audio_library_organizer.domain.settings import AppSettings, LibraryPaths
from audio_library_organizer.ui.dashboard_page import DashboardPage
from audio_library_organizer.ui.i18n import apply_static_language


def test_refresh_keeps_actions_and_data_but_renders_six_compact_metrics(tmp_path):
    app = QApplication.instance() or QApplication([])
    paths = LibraryPaths(tmp_path / 'library')
    paths.ensure_created()
    page = DashboardPage(AppSettings((), paths))
    try:
        page.resize(1500, 1000)
        page.show()
        app.processEvents()
        assert len(page.location_cards) == 6
        assert len(page.cards) == 4
        assert len(page.stats_values) == 6
        assert len(page.stats_progress) == 2
        assert len({page.stats_values[key].parentWidget().y() for key in page.stats_values}) == 1
        assert all(card.height() == 86 for card in page.location_cards.values())
        for card in page.location_cards.values():
            assert card.open_button.isEnabled()
            assert card.title_icon.width() >= 45
        page.set_summary({'total': 419, 'review': 211, 'duplicate': 0})
        page.set_health({'available': 419, 'missing_covers': 339, 'online_checked': 47, 'missing': 0})
        assert page.cards['review'].value_label.text() == '211'
        assert '211 do sprawdzenia' in page.attention_text.text()
        assert '339 bez okładki' in page.attention_text.text()
        assert page.attention_frame.findChild(QLabel, 'StartAttentionIcon') is not None
        assert page.stats_progress['covers'].value() == 19
        apply_static_language(page, 'en')
        page.refresh_language()
        assert page.hero_title.text() == 'Your music. Your order.'
        assert page.hero_description.text() == 'Organize • complete • analyze'
        apply_static_language(page, 'pl')
        page.refresh_language()
        assert page.hero_title.text() == 'Twoja muzyka. Twój porządek.'
    finally:
        page.close()


def test_refresh_keeps_quick_access_responsive(tmp_path):
    app = QApplication.instance() or QApplication([])
    page = DashboardPage(AppSettings((), LibraryPaths(tmp_path / 'library')))
    try:
        for width in (1500, 1100, 850):
            page.resize(width, 900)
            page.show()
            app.processEvents()
            app.processEvents()
            assert page.scroll.horizontalScrollBar().maximum() == 0
            hero_text = page.hero.findChild(QLabel, 'StartHeroBrand')
            assert hero_text.geometry().left() >= 60
            assert hero_text.geometry().right() < page.hero.width()
            assert page.hero_title.geometry().right() < page.hero.width()
            for card in page.location_cards.values():
                assert card.geometry().right() <= page.quick_access_host.width()
    finally:
        page.close()
