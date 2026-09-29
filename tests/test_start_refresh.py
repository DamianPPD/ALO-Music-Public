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


def test_final_start_polish_adds_only_small_internal_spacing(tmp_path):
    app = QApplication.instance() or QApplication([])
    paths = LibraryPaths(tmp_path / 'library')
    paths.ensure_created()
    page = DashboardPage(AppSettings((), paths))
    try:
        page.resize(1500, 1000)
        page.set_summary({'review': 2})
        page.show()
        app.processEvents()
        assert page.hero.height() == 200
        assert page.hero.layout().contentsMargins().left() == 110
        for card in page.location_cards.values():
            margin = card.layout().contentsMargins()
            assert (margin.left(), margin.top(), margin.right(), margin.bottom()) == (16, 9, 15, 9)
            assert card.height() == 86
        for box in page.metric_cards.values():
            margin = box.layout().contentsMargins()
            assert (margin.left(), margin.top(), margin.right(), margin.bottom()) == (11, 9, 11, 9)
            assert box.minimumHeight() == 84
        margin = page.attention_frame.layout().contentsMargins()
        assert (margin.left(), margin.top(), margin.right(), margin.bottom()) == (10, 7, 10, 7)
        assert set(page.stats_progress) == {'covers', 'online'}
    finally:
        page.close()


def test_music_card_decoration_is_a_soft_multibar_visualization(tmp_path):
    app = QApplication.instance() or QApplication([])
    page = DashboardPage(AppSettings((), LibraryPaths(tmp_path / 'library')))
    try:
        page.resize(1500, 900)
        page.show()
        app.processEvents()
        card = page.cards['total']
        image = card.grab().toImage()
        scale = image.devicePixelRatio()
        def blue_at(x, y):
            return image.pixelColor(round(x * scale), round(y * scale)).blue()
        baseline = blue_at(card.width() - 110, 40)
        colored_columns = sum(
            any(blue_at(x, y) > baseline + 10 for y in range(24, 69))
            for x in range(card.width() - 100, card.width() - 6)
        )
        assert colored_columns >= 32
        assert card.height() == 92
    finally:
        page.close()
