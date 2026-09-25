from PySide6.QtWidgets import QMessageBox

from audio_library_organizer.ui.i18n import language_for, ui_text


def confirm_bulk_copy(parent, summary: dict[str, int], *, examples: list[str] | None = None, folder_organization: str = 'none') -> bool:
    language = language_for(parent)
    if language == 'en':
        organization = {
            'none': 'No subfolders',
            'artist': 'By artist',
            'genre': 'By genre',
        }.get(folder_organization, 'No subfolders')
        text = (
            f"The app will create {summary['total']} copies in the new library.\n\n"
            f"READY: {summary['ready']}\n"
            f"NOT SELECTED: {summary.get('duplicate', 0) + summary.get('not_selected', 0)}\n"
            f"NEEDS REVIEW: {summary['review']}\n"
            f"READY organization: {organization}\n"
            f"Name conflicts: {summary.get('name_conflicts', 0)}\n"
            f"Existing target names: {summary.get('existing_targets', 0)}\n"
            f"Files to overwrite: {summary.get('will_overwrite', 0)}\n\n"
        )
        if examples:
            text += 'Example files:\n' + '\n'.join(f'• {line}' for line in examples[:8]) + '\n\n'
        text += 'Original files will NOT be changed or deleted.'
    else:
        organization = {
            'none': 'Bez podfolderów',
            'artist': 'Według wykonawcy',
            'genre': 'Według gatunku',
        }.get(folder_organization, 'Bez podfolderów')
        text = (
            f"Program utworzy {summary['total']} kopii w nowej bibliotece.\n\n"
            f"GOTOWE: {summary['ready']}\n"
            f"NIE WYBRANE: {summary.get('duplicate', 0) + summary.get('not_selected', 0)}\n"
            f"DO SPRAWDZENIA: {summary['review']}\n"
            f"Organizacja GOTOWE: {organization}\n"
            f"Konflikty nazw: {summary.get('name_conflicts', 0)}\n"
            f"Istniejące nazwy w folderze docelowym: {summary.get('existing_targets', 0)}\n"
            f"Pliki do nadpisania: {summary.get('will_overwrite', 0)}\n\n"
        )
        if examples:
            text += 'Przykładowe pliki:\n' + '\n'.join(f'• {line}' for line in examples[:8]) + '\n\n'
        text += 'Oryginalne pliki NIE zostaną zmienione ani usunięte.'
    answer = QMessageBox.question(
        parent, ui_text(parent, 'Podgląd przed utworzeniem plików'), text,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return answer == QMessageBox.StandardButton.Yes
