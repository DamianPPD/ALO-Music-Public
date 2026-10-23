def confirm_bulk_copy(parent, summary: dict[str, int], *, examples: list[str] | None = None,
                      folder_organization: str = 'none', plan=None) -> bool:
    from PySide6.QtWidgets import QDialog
    from audio_library_organizer.ui.export_dialogs import ExportPreviewDialog
    dialog = ExportPreviewDialog(summary, parent, examples=examples, plan=plan,
                                 folder_organization=folder_organization)
    try:
        return dialog.exec() == QDialog.DialogCode.Accepted
    finally:
        dialog.deleteLater()
