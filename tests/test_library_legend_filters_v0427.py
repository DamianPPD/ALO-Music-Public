"""Stage6.1A: one visible legend and existing semantic category accents."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import pytest
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMenu, QDialogButtonBox
from audio_library_organizer.domain.models import TrackRecord
from audio_library_organizer.ui.library_page import LibraryPage
from audio_library_organizer.ui.library_status_legend import install_library_status_legend
from audio_library_organizer.ui.library_file_state import FILE_STATE_COLORS
from audio_library_organizer.ui.icons import library_icon, alo_icon
from audio_library_organizer.ui.i18n import apply_static_language
from audio_library_organizer.ui.theme import DARK_STYLE
from test_library_controls_v0425 import _page


@pytest.fixture
def page(tmp_path):
    app=QApplication.instance() or QApplication([])
    previous=app.styleSheet(); app.setStyleSheet(DARK_STYLE)
    p,tracks=_page(tmp_path)
    tracks.extend([TrackRecord(tmp_path/'dup.mp3',artist='Other',title='Duplicate',status='duplicate'),
                   TrackRecord(tmp_path/'skip.mp3',artist='Other',title='Skip',status='not_selected')])
    p.set_tracks(tracks); p.resize(1600,800); p.show(); app.processEvents()
    yield p,tracks
    p.close(); app.setStyleSheet(previous)


def open_legend(page):
    button=install_library_status_legend(page)
    assert button.menu() is None, 'All eleven legend entries must be visible without a nested menu'
    button.click(); QApplication.processEvents()
    dialog=page.findChild(QDialog,'LibraryLegendDialog')
    assert dialog is not None and dialog.isVisible()
    return button,dialog


def test_one_click_shows_both_sections_and_all_eleven_names_without_submenus(page):
    page,_=page; _,d=open_legend(page)
    assert [w.text() for w in d.findChildren(QLabel,'LibraryLegendHeading')] == ['STANY UTWORÓW','STANY TECHNICZNE PLIKÓW']
    assert [w.text() for w in d.findChildren(QLabel,'LibraryLegendName')] == ['GOTOWE','DUPLIKAT','DO SPRAWDZENIA','PROBLEM','NIE WYBIERAM','W bibliotece','Tylko źródło','Do aktualizacji','Źródło niedostępne','Brak pliku biblioteki','Konflikt']
    assert not d.findChildren(QMenu)
    assert len(d.findChildren(QLabel,'LibraryLegendDescription'))==11
    assert all(w.text().strip() and w.isVisible() for w in d.findChildren(QLabel,'LibraryLegendDescription'))
    assert d.findChild(QLabel,'LibraryLegendUnconfirmed').text() == 'Stan pliku niepotwierdzony oznacza, że program nie ma wystarczających danych do jego wiarygodnego określenia.'


def test_legend_reuses_exact_status_icons_and_existing_file_colors(page):
    page,_=page; _,d=open_legend(page)
    # These are the five previously shipped icon recipes, not new assets.
    expected=[library_icon('status_ready','#35d893',16),alo_icon('duplicates','#b987ff',16),
              library_icon('status_review','#d8a23a',16),library_icon('status_problem','#f34d64',16),
              alo_icon('cancel','#a8b1bd',16)]
    icons=d.findChildren(QLabel,'LibraryLegendIcon')
    assert len(icons)==5
    for label,icon in zip(icons,expected): assert label.pixmap().toImage()==icon.pixmap(16,16).toImage()
    names=d.findChildren(QLabel,'LibraryLegendName')[5:]
    assert len(names)==6
    for name,color in zip(names,FILE_STATE_COLORS.values()):
        assert name.palette().color(QPalette.ColorRole.WindowText).name()==color.accent
    assert LibraryPage.CATEGORY_ICONS == {'all':'all_tracks','ready':'ready','duplicate':'duplicates','review':'review','not_selected':'unselected','no_cover':'no_cover','no_year':'no_year'}


@pytest.mark.parametrize('language,heading,first,file_first,uncertain',[
    ('pl','STANY UTWORÓW','GOTOWE','W bibliotece','wystarczających danych'),
    ('en','TRACK STATES','READY','In library','enough information'),
])
def test_legend_live_language_and_non_clipped_two_column_layout(page,language,heading,first,file_first,uncertain):
    page,_=page; button,d=open_legend(page)
    apply_static_language(page,language); button.click(); QApplication.processEvents()
    headings=d.findChildren(QLabel,'LibraryLegendHeading'); names=d.findChildren(QLabel,'LibraryLegendName')
    assert headings[0].text()==heading and names[0].text()==first and names[5].text()==file_first
    assert uncertain in d.findChild(QLabel,'LibraryLegendUnconfirmed').text()
    assert len({w.mapTo(d,w.rect().topLeft()).x() for w in names})==1
    for w in names:
        assert w.contentsRect().width() >= w.fontMetrics().horizontalAdvance(w.text())
    for w in d.findChildren(QLabel,'LibraryLegendDescription'):
        assert w.wordWrap() and w.height() >= w.heightForWidth(w.width())
    assert d.width() <= d.screen().availableGeometry().width()
    assert d.height() <= d.screen().availableGeometry().height()


def test_legend_reopens_same_instance_closes_with_owner_and_does_not_change_table(page):
    page,tracks=page
    page.table.selectRow(1); page.model.item(1,0).setCheckState(Qt.CheckState.Checked)
    page.table.sortByColumn(10,Qt.SortOrder.DescendingOrder)
    before=(deepcopy(tracks),[str(t.path) for t in page._selected_tracks()],page._checked_tracks(),page.table.horizontalHeader().sortIndicatorOrder())
    b,d=open_legend(page); b.click(); QApplication.processEvents()
    assert len(page.findChildren(QDialog,'LibraryLegendDialog'))==1
    d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Close).click()
    assert not d.isVisible()
    b.click(); QApplication.processEvents(); assert d.isVisible()
    assert before == (tracks,[str(t.path) for t in page._selected_tracks()],page._checked_tracks(),page.table.horizontalHeader().sortIndicatorOrder())
    page.close(); QApplication.processEvents(); assert not d.isVisible()


@pytest.mark.parametrize('key,color,asset',[
    ('all','#bdcbd3','all_tracks'),('ready','#6de6a5','ready'),('duplicate','#bd9bf7','duplicates'),
    ('review','#f4bd75','review'),('no_cover','#f4bd75','no_cover'),('not_selected','#bdcbd3','unselected'),
])
def test_active_filter_uses_existing_category_color_and_original_icon(page,key,color,asset):
    page,_=page; i=page.status.findData(key); page.status.setCurrentIndex(i); QApplication.processEvents()
    assert page.status.palette().color(QPalette.ColorRole.Text).name()==color
    assert page.status.itemData(i,Qt.ItemDataRole.ForegroundRole).color().name()==color
    assert page.status.itemIcon(i).pixmap(18,18).toImage()==library_icon(asset,color,18).pixmap(18,18).toImage()
    if key!='all': assert color in page.view_state_label.text()
    assert page.status.findData('problem')==-1 and page.status.findData('error')==-1


def test_cover_filter_hover_reset_and_actual_category_results_stay_correct(page):
    page,tracks=page; before=deepcopy(tracks)
    keys=[page.status.itemData(i) for i in range(page.status.count())]
    assert keys==['all',None,'ready','duplicate','review','not_selected',None,'no_cover','no_year']
    expected={'all':{'a.mp3','b.flac','c.wav','d.m4a','e.weird','dup.mp3','skip.mp3'},'ready':{'b.flac','d.m4a','e.weird'},'review':{'a.mp3','c.wav'},'duplicate':{'dup.mp3'},'not_selected':{'skip.mp3'},'no_cover':{'a.mp3','b.flac','c.wav','d.m4a','e.weird','dup.mp3','skip.mp3'}}
    for key,want in expected.items():
        page.status.setCurrentIndex(page.status.findData(key))
        assert {t.path.name for t in page.visible_tracks()}==want
    page.status.setCurrentIndex(page.status.findData('duplicate'))
    page._paint_category_icons(page.status.findData('no_cover')); QApplication.processEvents()
    assert page.status.palette().color(QPalette.ColorRole.Text).name()=='#bd9bf7'
    assert page.status.itemData(page.status.findData('no_cover'),Qt.ItemDataRole.ForegroundRole).color().name()=='#f4bd75'
    page._paint_category_icons(); page.reset_view_btn.click(); QApplication.processEvents()
    assert page.status.currentData()=='all'
    assert page.status.palette().color(QPalette.ColorRole.Text).name()=='#bdcbd3'
    assert tracks==before
