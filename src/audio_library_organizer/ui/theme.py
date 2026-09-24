APP_STYLE = r'''
QWidget { background:#10141a; color:#eef3f7; font-family:"Segoe UI"; font-size:10pt; }
QMainWindow { background:#0c1015; }

QFrame#TopNav { background:#090d12; border-bottom:1px solid #23302b; }
QLabel#BrandLogo { background:transparent; }
QLabel#BrandName { color:#eef8f1; font-size:14pt; font-weight:800; }
QLabel#BrandVersion { color:#7f9388; font-size:8.5pt; font-weight:600; }
QPushButton#TopNavButton { background:transparent; border:0; border-radius:8px; padding:10px 15px; color:#b8c4cf; font-weight:650; }
QPushButton#TopNavButton:hover { background:#151d21; color:#ffffff; }
QPushButton#TopNavButton:checked { background:#173125; color:#72efa2; border-bottom:2px solid #43d17d; }
QLabel#SessionBadge { background:#151d1a; border:1px solid #294a37; border-radius:10px; padding:8px 12px; color:#9be9b7; font-weight:600; }

QFrame#ToolbarFrame { background:#121820; border-bottom:1px solid #242d38; }
QFrame#WorkflowToolbarGroup { background:#0f151b; border:1px solid #27323d; border-radius:10px; }
QLabel#WorkflowStepArrow { color:#617181; font-size:14pt; font-weight:800; padding:0 1px; }
QFrame#WorkflowToolbarSeparator { background:#43515e; border:0; margin:4px 3px; }
QPushButton { background:#1a212a; border:1px solid #2d3846; border-radius:9px; padding:9px 14px; }
QPushButton:hover { background:#242d38; border-color:#405164; }
QPushButton:pressed { background:#303b49; }
QPushButton:disabled { color:#637080; background:#151a20; border-color:#252c35; }
QPushButton#Primary { background:#16844d; border:1px solid #269a60; color:white; font-weight:700; padding:10px 18px; }
QPushButton#Primary:hover { background:#1c9c5b; }
QPushButton[running="true"] { border:2px solid #9cf0bc; background:#25583d; color:#ffffff; font-weight:800; }
QPushButton#Primary[operationActive="true"], QPushButton#ToolbarAction[operationActive="true"], QPushButton#ReviewAction[operationActive="true"], QPushButton#ExportAction[operationActive="true"] { border:2px solid #7cf0a7; background:#23543a; color:#ffffff; }
QPushButton#ToolbarAction { background:#18344e; border-color:#2f638d; color:#d8edff; font-weight:650; padding:10px 17px; }
QPushButton#ToolbarAction:hover { background:#204663; }
QPushButton#ExportAction { background:#123f46; border:1px solid #25737d; color:#e3fbff; font-weight:800; padding:10px 17px; }
QPushButton#ExportAction:hover { background:#19545d; border-color:#3f96a1; }
QPushButton#CancelScanAction { background:#6b2428; border:1px solid #b94c53; color:#fff1f1; font-weight:800; padding:10px 17px; }
QPushButton#CancelScanAction:hover { background:#843037; border-color:#e0646c; }
QPushButton#ReviewAction { background:#4a3517; border:1px solid #8a6329; color:#ffe5b8; font-weight:700; padding:10px 17px; }
QPushButton#ReviewAction:hover { background:#5c431d; border-color:#b27a31; }
QPushButton#CancelAction { background:#422323; border:1px solid #794343; color:#ffdada; font-weight:650; padding:10px 17px; }
QPushButton#CancelAction:hover { background:#542c2c; }
QPushButton#ApproveButton { background:#176e43; border:1px solid #2b9c62; color:white; font-weight:800; padding:10px 14px; }
QPushButton#ApproveButton:hover { background:#1c8750; }

QFrame#OperationFrame { background:#0e1319; border:1px solid #27313c; border-left:5px solid #596675; border-radius:8px; }
QFrame#OperationFrame[operationKind="scan"] { background:#102239; border:1px solid #284b73; border-left:6px solid #5ca3ff; }
QFrame#OperationFrame[operationKind="online"] { background:#201936; border:1px solid #4b3f70; border-left:6px solid #a77dff; }
QFrame#OperationFrame[operationKind="review"] { background:#2b2011; border:1px solid #6b4d22; border-left:6px solid #ffb84d; }
QFrame#OperationFrame[operationKind="export"] { background:#10272a; border:1px solid #285a61; border-left:6px solid #49d6cf; }
QFrame#OperationFrame[operationKind="done"] { background:#102019; border-left:5px solid #67e495; }
QFrame#OperationFrame[operationKind="error"] { background:#271415; border-left:5px solid #ff6b6b; }
QLabel#OperationIcon { color:#d8e5ef; font-size:16pt; font-weight:900; min-width:24px; }
QLabel#OperationHeading { color:#8fa1b3; font-size:9.5pt; font-weight:850; letter-spacing:1px; }
QLabel#OperationKindTitle { color:#dfeaf3; font-size:10pt; font-weight:850; padding-left:7px; }
QLabel#OperationStatus { color:#f1f6fb; font-size:14.5pt; font-weight:800; padding:3px 1px 5px 1px; }
QProgressBar { background:#151b23; border:1px solid #344354; border-radius:7px; text-align:center; min-height:22px; font-weight:700; }
QProgressBar::chunk { background:#32c878; border-radius:5px; }

QFrame#ContentArea { background:#10141a; }
QLineEdit, QComboBox, QTextEdit { background:#151b23; border:1px solid #2d3744; border-radius:7px; padding:8px 10px; selection-background-color:#286549; }
QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border-color:#43d17d; }
QTableView, QListWidget, QTextBrowser { background:#11171e; alternate-background-color:#151c24; border:1px solid #26313d; border-radius:9px; }
QHeaderView::section { background:#19212a; color:#c3ceda; border:0; border-right:1px solid #27313c; padding:8px; font-weight:700; }
QTableView::item { padding:7px; border-bottom:1px solid #1f2831; }
QTableView::item:selected { background:#304052; color:#ffffff; }
QTableView::item:focus { border:0; outline:none; }

QFrame#DetailPanel { background:#121820; border:1px solid #293441; border-radius:10px; }
QFrame#PrimaryMetadataCard { background:#101b18; border:1px solid #315b47; border-radius:9px; }
QFrame#AdditionalMetadataCard { background:#151922; border:1px solid #343e50; border-radius:9px; }
QFrame#MatchInfoCard { background:#101a18; border:1px solid #29483a; border-radius:9px; }
QFrame#TechnicalPanel { background:#0f151b; border:1px solid #27323d; border-radius:8px; }
QFrame#HistoryCard { background:#10161d; border:1px solid #27323d; border-radius:8px; }
QFrame#CompareCard { background:#121a1d; border:1px solid #2c4540; border-radius:8px; }
QPushButton#DisclosureButton { background:#151c23; border:1px solid #2c3945; color:#b7c4d0; text-align:left; font-weight:750; padding:8px 10px; }
QPushButton#DisclosureButton:hover { background:#1d2630; color:#ffffff; }
QFrame#PinnedDetailActions { background:#0e141a; border-top:1px solid #2d3945; }
QFrame#ReviewReasonCard, QFrame#MetadataStatusCard { background:#171d24; border:1px solid #303b48; border-radius:9px; }
QLabel#ConfirmedHeading { color:#67e495; background:#14281d; border:1px solid #2d6142; border-radius:7px; padding:7px 9px; font-size:10pt; font-weight:850; }
QLabel#ConfirmedText { color:#89e9a9; line-height:1.4; }
QLabel#MissingHeading { color:#ffc66d; background:#2c2112; border:1px solid #6c4b1d; border-radius:7px; padding:7px 9px; font-size:10pt; font-weight:850; }
QLabel#MissingText { color:#ffbf66; font-weight:700; }
QLabel#CompleteText { color:#8ff0ad; background:#13271b; border:1px solid #2d6142; border-radius:8px; padding:9px; font-weight:750; }
QLabel#MetadataSectionTitle { color:#70e59b; font-size:10pt; font-weight:900; letter-spacing:1px; padding:2px 0 4px 0; }
QLabel#MetadataSectionTitleOptional { color:#9caabd; font-size:9.5pt; font-weight:850; letter-spacing:1px; padding:2px 0 4px 0; }
QLabel#DetailFieldHeading { color:#8090a1; font-size:8.5pt; font-weight:800; padding-top:1px; }
QLabel#DetailFieldValue { color:#edf3f8; font-size:10.2pt; padding:1px 1px 3px 1px; }
QLabel#FieldHeading { color:#8ea0b2; font-size:8.5pt; font-weight:800; }
QLabel#SetupHeading { color:#eef5f8; font-size:12pt; font-weight:800; }
QLabel#PathPreview { color:#dff7e7; font-family:Consolas; font-size:10pt; font-weight:650; }

QGroupBox { border:1px solid #28323e; border-radius:10px; margin-top:11px; padding-top:13px; font-weight:650; }
QGroupBox::title { subcontrol-origin:margin; left:11px; padding:0 6px; color:#c8d4df; }
QFrame#WorkflowStep { background:#141b22; border:1px solid #28333e; border-radius:10px; }
QFrame#CompactWorkflow { background:#11171d; border:1px solid #26323d; border-radius:10px; }
QFrame#WorkflowMiniStep { background:#151c23; border:1px solid #293641; border-radius:8px; }
QFrame#SessionCard { background:#131b1a; border:1px solid #294536; border-radius:10px; }
QFrame#NextStepCard { background:#151b24; border:1px solid #344252; border-radius:10px; }
QFrame#SafeIntroCard { background:#102019; border:1px solid #28513b; border-radius:10px; }
QFrame#SetupCard { background:#141b22; border:1px solid #2b3744; border-radius:12px; }
QFrame#PathPreviewCard { background:#102019; border:1px solid #2f6145; border-radius:12px; }
QLabel#FirstRunBrand { color:#ecf8f0; font-size:25pt; font-weight:850; }
QLabel#FirstRunSubtitle { color:#8da098; font-size:10pt; font-weight:650; }
QLabel#MutedText { color:#9daab9; }

QFrame#LocationCard { background:#111b18; border:1px solid #28513b; border-radius:12px; }
QFrame#NamingCard { background:#141b22; border:1px solid #314052; border-radius:12px; }
QFrame#ProviderCard { background:#111923; border:1px solid #2d4057; border-radius:10px; }
QFrame#ContactFooter { background:#11161b; border-top:1px solid #303943; border-radius:7px; }
QLabel#ContactAuthor { color:#b8c1cb; font-weight:650; }
QLabel#ContactLabel { color:#8b98a6; font-weight:700; }
QLabel#ContactEmail a { color:#5bd9cf; font-weight:800; text-decoration:none; }
QFrame#FilenamePreviewCard { background:#101b18; border:1px solid #315641; border-radius:10px; }
QLabel#FilenamePreview { color:#dff8e8; font-family:Consolas; font-size:10pt; font-weight:700; background:#0c1512; border:1px solid #284736; border-radius:7px; padding:8px 10px; }
QPushButton#PathOpenButton { background:#172d23; border:1px solid #356349; color:#d9f5e4; font-weight:700; padding:7px 11px; }
QPushButton#PathOpenButton:hover { background:#20402f; border-color:#4a8b64; }
QPushButton#PathOpenButton:disabled { background:#151a1d; border-color:#293137; color:#67727a; }
QFrame#IntegrationCard { background:#101927; border:1px solid #294c70; border-radius:12px; }
QFrame#FolderOrganizationCard { background:#112021; border:1px solid #2d5d60; border-radius:12px; }
QFrame#TargetLibraryCard { background:#0f2018; border:1px solid #35694b; border-radius:10px; }
QLabel#FinalFolderBadge { color:#effff4; background:#1b6540; border:1px solid #45a56d; border-radius:7px; padding:2px 8px; font-size:9.5pt; font-weight:850; }
QLabel#DiskFreeLabel { color:#8bc0ac; font-size:9pt; }
QLabel#FolderStructurePreview { color:#d8fbf4; background:#0d191a; border:1px solid #2b4b4d; border-radius:7px; padding:8px 10px; font-family:Consolas; }
QFrame#PathRow { background:#151d24; border:1px solid #2a3541; border-radius:8px; }
QLabel#InfoBanner, QFrame#InfoBanner { color:#d8e5ed; background:#151d22; border:1px solid #2d4141; border-radius:9px; padding:11px; }
QLabel#HelpCard { color:#cbd7e3; background:#151c25; border:1px solid #2b3b50; border-radius:8px; padding:10px; }
QLabel#FinePrint { color:#748292; font-size:9pt; }
QLabel#SavedNotice { color:#72e89c; font-weight:700; padding:7px; }
QPushButton#DetailsToggle { background:#202733; border:1px solid #526070; color:#e2e9f0; font-weight:800; }
QPushButton#DetailsToggle:checked { background:#26394b; border-color:#6b9bc0; color:#ffffff; }
QPushButton#DuplicateKeep { background:#174d38; border:1px solid #3b9b6d; color:#e8fff2; font-weight:850; }
QPushButton#DuplicateMark { background:#38244d; border:1px solid #8457ad; color:#f0ddff; font-weight:800; }
QPushButton#DuplicateReject { background:#30343a; border:1px solid #5a616a; color:#e0e4e8; font-weight:800; }
QPushButton#DuplicateVersion { background:#17374f; border:1px solid #397ca8; color:#e0f3ff; font-weight:800; }
QLabel#DuplicateCount { color:#c8a8ff; font-weight:850; padding:7px 9px; background:#211b2b; border:1px solid #4e3a64; border-radius:7px; }
QLabel#DecisionCount { color:#ffc66d; font-weight:800; padding:6px 8px; background:#2a2114; border:1px solid #5a4322; border-radius:7px; }

QWidget#PlayerBar { background:#090d12; }
QFrame#PlayerCard { background:#0f151d; border:1px solid #2a3948; border-radius:13px; }
QFrame#CoverGallery { background:#10151c; border:1px solid #2b3745; border-radius:10px; }
QFrame#CoverChoiceCard { background:#141b23; border:1px solid #2d3947; border-radius:9px; }
QLabel#CoverChoicePreview { background:#0b0f14; border:1px solid #2d3844; border-radius:7px; color:#778392; }
QPushButton#CoverChoiceButton:checked { background:#19543a; border:2px solid #58c886; color:#ffffff; font-weight:850; }
QFrame#FooterSeparator { background:#33443d; border:0; }
QLabel#FooterVersion { color:#74877e; font-size:8.5pt; font-weight:650; }
QLabel#FooterAttribution { color:#91a49a; font-size:8.8pt; font-weight:650; }
QPushButton#FooterLink { background:transparent; border:0; padding:2px 4px; color:#7eb4ff; font-size:8.8pt; font-weight:700; }
QPushButton#FooterLink:hover { color:#a8ccff; text-decoration:underline; }
QLabel#PlayerCover { background:#0d1218; border:1px solid #2a3542; border-radius:9px; color:#6f7d8d; }
QLabel#PlayerArtist { color:#f0f5f9; font-size:12pt; font-weight:800; }
QPushButton#PlayerTitleLink { background:transparent; border:0; padding:1px 0; color:#d3dee8; font-size:10.8pt; font-weight:700; text-align:left; }
QPushButton#PlayerTitleLink:hover { color:#ffffff; text-decoration:underline; }
QLabel#PlaybackStatus { color:#72e89c; font-size:8.5pt; font-weight:750; }
QLabel#PlayerMeta { color:#8190a0; font-size:9pt; }
QLabel#PlayerTime { color:#9caab8; font-family:Consolas; font-size:9pt; }
QPushButton#PlayButton { background:#22a861; color:white; border:0; border-radius:34px; font-size:22pt; font-weight:800; padding:0; }
QPushButton#PlayButton:hover { background:#2dc875; }
QPushButton#PlayButton:pressed { background:#18854b; }
QSlider::groove:horizontal { height:6px; background:#2a333e; border-radius:3px; }
QSlider::handle:horizontal { width:16px; margin:-5px 0; border-radius:8px; background:#43d17d; }
QSlider#SeekSlider::groove:horizontal { height:8px; background:#2a333e; border-radius:4px; }
QSlider#SeekSlider::handle:horizontal { width:18px; margin:-5px 0; border-radius:9px; background:#43d17d; }
QSlider#VolumeSlider::groove:horizontal { height:6px; background:#2a333e; border-radius:3px; }
QSlider#VolumeSlider::handle:horizontal { width:16px; margin:-5px 0; border-radius:8px; background:#43d17d; }

QToolTip { background:#25303b; color:white; border:1px solid #43d17d; padding:6px; }


/* v0.2.2 stronger visual hierarchy */
QLabel#DuplicateNavBadge {
    background:#4b2d69; color:#f4eaff; border:1px solid #8d5bc4;
    border-radius:11px; min-width:22px; max-width:36px; min-height:22px;
    padding:0 5px; font-weight:850; qproperty-alignment:AlignCenter;
}
QFrame#DuplicateNavWrap { background:transparent; border:none; }
QListWidget#DuplicateFiles::item { padding:10px 8px; border-bottom:1px solid #252d39; }
QListWidget#DuplicateFiles::item:selected {
    color:#ffffff; border:1px solid #8ea0b2; border-radius:6px; font-weight:750;
}
QPushButton#DisclosureButton {
    background:#18222d; border:1px solid #3b4b5e; border-left:4px solid #65d8cf;
    color:#e8f5f5; border-radius:8px; padding:9px 12px; text-align:left;
    font-size:10.5pt; font-weight:800;
}
QPushButton#DisclosureButton:hover { background:#1d2b37; border-color:#5d7188; border-left-color:#7be8df; }
QFrame#SettingsSectionDivider { background:#26323d; border:0; margin:2px 12px; }
QFrame#LocationCard { background:#101c18; border:1px solid #2b6546; border-left:4px solid #43d17d; border-radius:12px; }
QFrame#NamingCard { background:#171826; border:1px solid #4a4162; border-left:4px solid #a77dff; border-radius:12px; }
QFrame#FolderOrganizationCard { background:#102124; border:1px solid #2c6065; border-left:4px solid #49d6cf; border-radius:12px; }
QFrame#IntegrationCard { background:#101a2a; border:1px solid #315a83; border-left:4px solid #5ca3ff; border-radius:12px; }
QFrame#ContactFooter { background:#11161b; border:1px solid #29323c; border-left:4px solid #5a6674; border-radius:9px; }
QFrame#FolderChoiceRow { background:#12191f; border:1px solid #29353f; border-radius:8px; }
QFrame#FolderChoiceRow[selected="true"] { background:#12302e; border:1px solid #3d8d89; }
QLabel#FolderOptionExample { color:#82909f; font-family:Consolas; font-size:8.7pt; padding-left:24px; }
QLabel#FolderStructurePreview { color:#d8fbf4; background:#091719; border:1px solid #347074; border-radius:8px; padding:10px 12px; font-family:Consolas; }


QFrame#PreOnlineSnapshotCard { background:#161923; border:1px solid #48425d; border-left:4px solid #a77dff; border-radius:9px; }
QLabel#PreOnlineSnapshotText { color:#d7dce7; font-size:9.3pt; }
QPushButton#RestoreOnlineButton { background:#173a5e; border:1px solid #5ca3ff; color:#eaf4ff; font-weight:800; padding:7px 10px; }
QLabel#SuspiciousOnlineWarning { color:#ffd08a; background:#332312; border:1px solid #8b5d22; border-radius:8px; padding:8px 10px; font-weight:800; }
QToolButton#MetadataSourceBadge { border-radius:6px; padding:2px 6px; font-size:8pt; font-weight:800; min-height:18px; }
QToolButton#MetadataSourceBadge[sourceKind="tag"], QLabel#SourceLegendBadge[sourceKind="tag"] { color:#dcecff; background:#173a5e; border:1px solid #5ca3ff; }
QToolButton#MetadataSourceBadge[sourceKind="discogs"], QLabel#SourceLegendBadge[sourceKind="discogs"] { color:#e8fff1; background:#17462f; border:1px solid #43d17d; }
QToolButton#MetadataSourceBadge[sourceKind="musicbrainz"], QLabel#SourceLegendBadge[sourceKind="musicbrainz"] { color:#eef0ff; background:#222d5c; border:1px solid #7289ff; }
QToolButton#MetadataSourceBadge[sourceKind="manual"], QLabel#SourceLegendBadge[sourceKind="manual"] { color:#fff2df; background:#4d3214; border:1px solid #ffb84d; }
QToolButton#MetadataSourceBadge[sourceKind="analysis"], QLabel#SourceLegendBadge[sourceKind="analysis"] { color:#e6fffd; background:#153f40; border:1px solid #49d6cf; }
QToolButton#MetadataSourceBadge[sourceKind="filename"], QLabel#SourceLegendBadge[sourceKind="filename"] { color:#e4e9ef; background:#2a3038; border:1px solid #7d8894; }
QLineEdit[sourceKind="tag"], QTextEdit[sourceKind="tag"] { border-color:#5ca3ff; }
QLineEdit[sourceKind="discogs"], QTextEdit[sourceKind="discogs"] { border-color:#43d17d; }
QLineEdit[sourceKind="musicbrainz"], QTextEdit[sourceKind="musicbrainz"] { border-color:#7289ff; }
QLineEdit[sourceKind="manual"], QTextEdit[sourceKind="manual"] { border-color:#ffb84d; }
QLineEdit[sourceKind="analysis"], QTextEdit[sourceKind="analysis"] { border-color:#49d6cf; }
QLineEdit[sourceKind="filename"], QTextEdit[sourceKind="filename"] { border-color:#7d8894; }
QFrame#SourceLegend { background:#10161d; border:1px solid #29343f; border-radius:8px; }
QLabel#SourceLegendBadge { border-radius:5px; padding:2px 5px; font-size:7.8pt; font-weight:800; }
QLineEdit[missingRequired="true"] { border:2px solid #e45b5b; background:#2b1719; color:#fff4f4; }
QFrame#MetadataStatusCard[lowConfidence="true"], QFrame#MatchInfoCard[lowConfidence="true"] { border:2px solid #e45b5b; background:#291719; }
QLabel#LowConfidenceText { color:#ff8585; font-weight:850; }
QLabel#UnsavedNotice { color:#ffb84d; font-weight:800; }
QLabel#MetadataSavedNotice { color:#72e89c; font-weight:800; }
QToolButton#MetadataSourceBadge[sourceKind="none"] { color:#aeb8c2; background:#232a32; border:1px solid #4a5662; }
QLabel#MetadataFieldLabel { color:#b7c2ce; font-weight:650; }
QLineEdit[changed="true"], QTextEdit[changed="true"] { background:#1b222a; color:#f0fff5; }
QLineEdit[missingRequired="true"] { border:2px solid #e45b5b; background:#2b1719; color:#fff4f4; }


/* v0.2.2 player rebuild */
QFrame#PlayerTransportPanel {
    background:#111a23; border:1px solid #2c3b49; border-radius:10px;
}
QFrame#PlayerTimelinePanel {
    background:#0c1218; border:1px solid #27333f; border-radius:9px;
}
QLabel#PlayerMiniHeading {
    color:#6f8192; font-size:8pt; font-weight:850; letter-spacing:1px;
}
QPushButton#PlayerSkipButton {
    background:#171f28; border:1px solid #344351; color:#cbd5df;
    border-radius:8px; padding:7px 11px; font-weight:750;
}
QPushButton#PlayerSkipButton:hover { background:#202b36; border-color:#53687b; color:#ffffff; }
QPushButton#PlayerSkipButton:pressed { background:#111820; }


/* v0.2.3 radio selection */
QRadioButton::indicator { width:15px; height:15px; border:2px solid #66727f; border-radius:8px; background:#11171d; }
QRadioButton::indicator:checked { border:2px solid #43d17d; background:#43d17d; }
QRadioButton::indicator:unchecked:hover { border-color:#8d99a6; }

'''

# v0.3.0 additions
APP_STYLE += r'''
QFrame#MetadataSummaryCard {
    background:#151b23; border:1px solid #303a48; border-radius:12px;
}
QFrame#MetadataSummaryCard[summaryKind="confirmed"] { border-color:#295f43; }
QFrame#MetadataSummaryCard[summaryKind="missing"] { border-color:#6a4b2a; }
QFrame#MetadataSummaryCard[summaryKind="confidence"][lowConfidence="true"] { border:2px solid #e75f5f; }
QProgressBar#ConfidenceBar { background:#252d38; border:0; border-radius:4px; }
QProgressBar#ConfidenceBar::chunk { background:#7d8894; border-radius:4px; }
QProgressBar#ConfidenceBar[confidenceKind="high"]::chunk { background:#43d17d; }
QProgressBar#ConfidenceBar[confidenceKind="medium"]::chunk { background:#ffb84d; }
QProgressBar#ConfidenceBar[confidenceKind="low"]::chunk { background:#ef6262; }
QLabel#ConfidencePercent { font-size:16pt; font-weight:800; }
QFrame#CompactPlayerBar { background:#0c1117; border:1px solid #2c3542; border-radius:10px; }
QPushButton#CompactPlayButton { background:#173c2d; border:1px solid #43d17d; border-radius:8px; color:#8fe9ad; font-size:13pt; font-weight:800; }
QLabel#CompactPlayerTime { color:#aab6c4; font-size:9pt; }
QPushButton#TopNavButton[hasItems="true"] { background:#392951; border-color:#8b60ca; color:#eadcff; }
QCheckBox[requiredLocked="true"] { color:#8fe9ad; font-weight:700; }
QCheckBox[requiredLocked="true"]::indicator:checked { border:0; background:transparent; }
QPushButton#CancelOnlineAction { background:#5b2f23; border:1px solid #dd805f; color:#ffd1c2; font-weight:800; }
QPushButton#LibraryCollectionAction { background:#173c2d; border:1px solid #43d17d; color:#8fe9ad; font-weight:700; }
QFrame#LibraryHealthCard { background:#141b22; border:1px solid #2b3542; border-radius:12px; }
QFrame#MissingFilesBanner { background:#3a2719; border:1px solid #a36c35; border-radius:10px; }
'''
APP_STYLE += r'''
QFrame#ReviewReasonCard[hasMissing="true"] { border:2px solid #e75f5f; }
'''

# v0.4.0 refinements
APP_STYLE += r'''
QFrame#CompactPlayerBar { background:#0b1319; border:2px solid #4f6877; border-radius:11px; }
QLabel#CompactPlayerHeading { color:#78d9e6; font-size:8.5pt; font-weight:900; letter-spacing:1px; }
QToolButton#GenreChip { background:#192833; border:1px solid #477386; border-radius:9px; color:#cfeef5; padding:4px 8px; font-weight:700; }
QToolButton#GenreChip:hover { background:#203746; border-color:#66a6bb; }
QFrame#ConfidenceWidget { background:transparent; border:0; padding:2px 0; }
QProgressBar#ConfidenceBar { background:#242d37; border:1px solid #2f3a46; border-radius:6px; min-height:12px; max-height:12px; }
QProgressBar#ConfidenceBar::chunk { border-radius:5px; }
QLabel#ConfidencePercent { font-size:17pt; font-weight:900; padding:0 0 2px 0; }
QLabel#ConfidenceDescription { color:#9ba8b5; font-size:8.5pt; padding-top:3px; }
QLabel#MissingEmptyTitle { color:#8fe9ad; font-weight:850; font-size:10pt; }
QLabel#MissingEmptySubtitle { color:#7f8e9c; font-size:8.5pt; }
QPushButton#LibraryPlaylistAction { background:#2f2a19; border:1px solid #9a7a2d; color:#ffe29b; font-weight:750; }
QPushButton#LibraryPlaylistAction:hover { background:#413820; border-color:#c69a35; }
QLabel#QuickFileInfo { background:#0f171d; border:1px solid #273844; border-radius:7px; color:#8ea4b3; padding:6px 9px; }
QLabel#DuplicateRecommendation { background:#17271e; border:1px solid #3e8058; border-radius:8px; color:#9cebb8; padding:8px 10px; font-weight:700; }
QLineEdit[invalidYear="true"] { border:2px solid #e45b5b; background:#2b1719; color:#fff4f4; }
QPushButton#AddFilesAction { background:#123947; border:1px solid #39b9d1; color:#bceef7; font-weight:800; }
QPushButton#AddFilesAction:hover { background:#184d5e; border-color:#66d1e5; }
QPushButton#IdentifyOnlineAction { background:#493a12; border:1px solid #d5a833; color:#ffe49a; font-weight:800; }
QPushButton#IdentifyOnlineAction:hover { background:#604c17; border-color:#f0c457; }
QPushButton#ActiveLibraryBadge { background:#171f28; border:1px solid #41505f; color:#c7d4df; border-radius:9px; padding:6px 10px; font-weight:750; }
QFrame#AppearanceCard, QFrame#NormalizationCard, QFrame#BackupCard { background:#151b23; border:1px solid #303a48; border-radius:10px; }
QPushButton#ManageLibrariesAction { background:#242b35; border:1px solid #556373; color:#dbe5ed; font-weight:750; }
'''

# v0.4.0 appearance modes. Keep APP_STYLE as the dark compatibility alias.
DARK_STYLE = APP_STYLE

# v0.4.21 metadata-editor design tokens; final selectors are repeated at the
# end of the layered compatibility stylesheet.
APP_STYLE += r'''
QFrame#StatusRecognitionColumn { background:transparent; border:0; }
QFrame#PrimaryMetadataCard,
QFrame#MetadataStatusCompact,
QFrame#RecognitionInfoCompact,
QFrame#CoverGallery {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0d1921,stop:1 #091219);
    border:1px solid #2a4856;
    border-radius:9px;
}
QFrame#PrimaryMetadataCard { border-color:#295244; }

QLabel#MetadataFieldLabel {
    color:#b9c7cf;
    font-size:8.2pt;
    font-weight:560;
}
QFrame#MetadataValueShell {
    background:transparent;
    border:0;
}
QLabel#MetadataFieldWarning[statusKind="missing"] {
    background:#e6a83b;
    border:1px solid #ffd06d;
    border-radius:7px;
    color:#241807;
    font-size:8pt;
    font-weight:850;
    margin-left:2px;
}
QLabel#EditorSectionTitle {
    color:#e5edf2;
    font-size:9pt;
    font-weight:720;
}
QLabel#TrackHeaderTitle { font-weight:680; }
QLabel#TrackHeaderTechnical { font-weight:650; }
QLabel#RecognitionFieldName { color:#8498a4; font-weight:500; }
QLabel#RecognitionFieldValue { color:#d5e2e8; font-weight:630; }
QLabel#MetadataStatusText[statusKind="ok"] { font-weight:650; }
QLabel#MetadataStatusText[statusKind="missing"] { font-weight:700; }

QPushButton#OnlineLockButton {
    background:#0d1a23;
    border:1px solid #304d5c;
    color:#bdcad2;
    border-radius:7px;
    min-height:29px;
    padding:5px 9px;
    font-size:8pt;
    font-weight:600;
}
QPushButton#OnlineLockButton:hover { background:#122630; border-color:#477284; color:#ffffff; }
QPushButton#OnlineLockButton[lockedOnline="true"] {
    background:#102a3b; border-color:#3684ae; color:#bde9ff;
}

QTableWidget#SourceComparisonTable {
    background:#081117;
    alternate-background-color:#0a151c;
    border:1px solid #213844;
    border-radius:6px;
    gridline-color:#162832;
    selection-background-color:#233e50;
    selection-color:#ffffff;
}
QTableWidget#SourceComparisonTable QHeaderView::section {
    background:#101f28;
    color:#b9cad3;
    border-right:1px solid #1d323c;
    border-bottom:1px solid #263e49;
    font-weight:650;
}
QTableWidget#SourceComparisonTable::item { border-bottom:1px solid #14252e; }
QWidget#UseSourceDataCell { background:transparent; }
QPushButton#UseSourceDataButton {
    background:#101d25;
    border:1px solid #36515e;
    color:#d9e4e9;
    border-radius:5px;
    min-width:82px; max-width:82px;
    min-height:18px; max-height:18px;
    padding:0 5px;
    font-size:7.1pt;
    font-weight:600;
}
QPushButton#UseSourceDataButton:hover {
    background:#10261d;
    border-color:#2fc879;
    color:#a9efc5;
}
QToolButton#SourceLegendInfoButton {
    background:transparent;
    border:1px solid #58717d;
    border-radius:11px;
    padding:2px;
}
QToolButton#SourceLegendInfoButton:hover { background:#13242d; border-color:#79b9ce; }

QLabel#CoverMainPreview {
    background:#070d12;
    border:2px solid #20cf7b;
    border-radius:8px;
}
QWidget#CoverProposalsHost {
    background:#09161e;
    border:1px solid #274654;
    border-radius:7px;
}
QFrame#CoverProposalCard { background:#0b141b; border:1px solid #293b45; border-radius:6px; }
QFrame#CoverProposalCard:hover { background:#10202a; border-color:#456473; }
QFrame#CoverProposalCard[selected="true"] { background:#0d2118; border:1px solid #28ce7c; }
QLabel#CoverProposalSelectedBadge {
    background:#1bd17c;
    border:1px solid #5bf0a5;
    border-radius:8px;
    color:#062316;
    font-size:7pt;
    font-weight:900;
}
QLabel#CoverProposalsHeading {
    color:#99adb8;
    background:transparent;
    border:0;
    padding:1px 2px;
    font-size:7.8pt;
    font-weight:620;
}
QPushButton#CoverSmallAction,
QPushButton#CoverMoreAction {
    min-height:28px;
    font-weight:600;
}

QPushButton#EditorSecondaryAction {
    background:#0d171e;
    border:1px solid #334a57;
    color:#cbd7dd;
    font-weight:600;
}
QPushButton#CurrentStatusButton { font-weight:750; }
QPushButton#SaveMetadataButton {
    background:#0b3d52;
    border:1px solid #24a6d1;
    color:#ebfaff;
    font-weight:720;
}
QPushButton#SaveMetadataButton:hover {
    background:#0d526d;
    border-color:#55ccef;
    color:#ffffff;
}
QPushButton#SingleTrackOnlineButton,
QPushButton#RestoreOnlineButton,
QPushButton#CoverSmallAction,
QPushButton#CoverMoreAction,
QPushButton#RestoreFilenameButton {
    font-weight:600;
}
'''
DARK_STYLE = APP_STYLE


# v0.4.21-dev round 2 — metadata editor polish based on reference 2.
APP_STYLE += r'''
/* Track identity strip: one calm hierarchy for file name and technical facts. */
QFrame#PreOnlineSnapshotCard {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #091722,stop:1 #0b141c);
    border:1px solid #254758;
    border-left:3px solid #28c9e8;
    border-radius:8px;
}
QLabel#TrackHeaderIcon { background:transparent; }
QLabel#TrackHeaderTitle {
    color:#edf4f7;
    font-size:9.2pt;
    font-weight:780;
    padding:0 2px;
}
QLabel#TrackHeaderSeparator { color:#42606d; font-size:9pt; }
QLabel#TrackHeaderTechnical {
    color:#c4d5df;
    font-size:8.3pt;
    font-weight:760;
    min-width:43px;
}

/* Warning is part of the field edge; correct fields stay visually silent. */
QLabel#MetadataFieldWarning[statusKind="missing"] {
    background:#edae3e;
    border:1px solid #ffd06f;
    border-radius:9px;
    color:#241807;
    font-size:8.5pt;
    font-weight:950;
}

/* Status cards: stronger header separation and quieter, premium content. */
QFrame#MetadataStatusCompact,
QFrame#RecognitionInfoCompact {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0d1b23,stop:1 #091219);
    border:1px solid #31515f;
    border-radius:9px;
}
QFrame#MetadataStatusCompact QWidget#EditorSectionHeader,
QFrame#RecognitionInfoCompact QWidget#EditorSectionHeader {
    background:#10212a;
    border-bottom:1px solid #294854;
    border-radius:5px;
    padding:2px 4px;
}
QFrame#MetadataStatusRow { min-height:22px; }
QLabel#RecognitionFieldName { color:#8195a2; font-size:7.9pt; }
QLabel#RecognitionFieldValue { color:#d9e5eb; font-size:8.1pt; font-weight:730; }
QProgressBar#RecognitionConfidenceBar {
    background:#1b303a;
    border:1px solid #294650;
    border-radius:3px;
}
QProgressBar#RecognitionConfidenceBar::chunk {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #20c986,stop:1 #55e9b0);
    border-radius:2px;
}

/* Cover section: artwork and proposals first, one simple action row below. */
QLabel#CoverProposalsHeading {
    color:#9fb5c1;
    background:transparent;
    border:0;
    border-radius:0;
    padding:1px 2px;
    font-size:7.9pt;
    font-weight:780;
}
QWidget#CoverActions {
    background:transparent;
    border-top:1px solid #203b47;
}
QPushButton#CoverSmallAction,
QPushButton#CoverMoreAction {
    background:#0e1b23;
    border:1px solid #385260;
    color:#dce7ed;
    border-radius:7px;
    min-height:27px;
    padding:5px 10px;
    font-size:8pt;
    font-weight:720;
}
QPushButton#CoverSmallAction:hover,
QPushButton#CoverMoreAction:hover {
    background:#142832;
    border-color:#4d8298;
    color:#ffffff;
}
QPushButton#CoverMoreAction { color:#abd5e7; }

/* A compact, centered source action with breathing room around it. */
QWidget#UseSourceDataCell { background:transparent; }
QPushButton#UseSourceDataButton {
    background:#111e26;
    border:1px solid #3a5663;
    color:#dce7ec;
    border-radius:5px;
    min-width:100px;
    max-width:100px;
    min-height:22px;
    max-height:22px;
    padding:0 7px;
    font-size:7.2pt;
    font-weight:720;
}
QPushButton#UseSourceDataButton:hover {
    background:#112a20;
    border-color:#31cf80;
    color:#a9efc6;
}

/* Footer contains one reversible status toggle and one save action. */
QPushButton#CurrentStatusButton {
    background:#3a2a0e;
    border:1px solid #d39a2b;
    color:#ffd476;
    border-radius:8px;
    min-height:38px;
    min-width:168px;
    padding:7px 15px;
    font-weight:880;
}
QPushButton#CurrentStatusButton:hover {
    background:#4a3611;
    border-color:#f0b849;
}
QPushButton#CurrentStatusButton[currentStatusKind="ready"] {
    background:#0d5634;
    border-color:#1cd37d;
    color:#f1fff7;
}
QPushButton#CurrentStatusButton[currentStatusKind="ready"]:hover {
    background:#0f6b40;
    border-color:#47e99d;
}
QPushButton#CurrentStatusButton[statusSeverity="reviewCritical"] {
    background:#482019;
    border-color:#d76254;
    color:#ffb2a9;
}
QPushButton#SaveMetadataButton {
    background:#0d2e26;
    border-color:#238d66;
    color:#dcf8eb;
    font-weight:820;
}
QPushButton#SaveMetadataButton:hover {
    background:#104235;
    border-color:#32c887;
}
'''
DARK_STYLE = APP_STYLE
LIGHT_OVERRIDE = r'''
QWidget { background:#f4f6f8; color:#1d2730; }
QMainWindow { background:#eef1f4; }
QFrame#TopNav { background:#ffffff; border-bottom:1px solid #d5dce3; }
QLabel#BrandName { color:#15211a; }
QLabel#BrandVersion, QLabel#MutedText, QLabel#CompactPlayerTime { color:#66727e; }
QPushButton#TopNavButton { color:#4f5c68; }
QPushButton#TopNavButton:hover { background:#edf2f5; color:#16202a; }
QPushButton#TopNavButton:checked { background:#e6f5ec; color:#177647; border-bottom:2px solid #27a865; }
QFrame#ToolbarFrame { background:#f8fafb; border-bottom:1px solid #d7dde4; }
QPushButton { background:#ffffff; border-color:#cbd4dd; color:#26323d; }
QPushButton:hover { background:#eef3f7; border-color:#9eacb9; }
QPushButton:disabled { color:#9aa5af; background:#f0f2f4; border-color:#dde2e6; }
QFrame#ContentArea, QFrame#DetailPanel, QFrame#PrimaryMetadataCard, QFrame#AdditionalMetadataCard,
QFrame#MatchInfoCard, QFrame#TechnicalPanel, QFrame#HistoryCard, QFrame#CompareCard,
QFrame#MetadataSummaryCard, QFrame#LibraryHealthCard { background:#ffffff; border-color:#d7dee5; }
QLineEdit, QComboBox, QTextEdit { background:#ffffff; color:#1f2932; border-color:#c9d2db; selection-background-color:#b7e4ca; }
QLineEdit:focus, QComboBox:focus, QTextEdit:focus { border-color:#2cad68; }
QTableView, QListWidget, QTextBrowser { background:#ffffff; alternate-background-color:#f6f8fa; border-color:#d2dae2; color:#1e2832; }
QHeaderView::section { background:#edf1f4; color:#44515d; border-right:1px solid #d6dde4; }
QTableView::item { border-bottom:1px solid #e6eaee; }
QTableView::item:selected { background:#dbe8f4; color:#15202a; }
QFrame#CompactPlayerBar { background:#f4f8fb; border:2px solid #92a6b7; }
QProgressBar { background:#e4e9ee; border-color:#c8d1da; }
QFrame#OperationFrame { background:#ffffff; border-color:#d4dce3; }
QLabel#OperationStatus, QLabel#OperationKindTitle { color:#25313c; }
QFrame#SourceLegend, QFrame#FilenamePreviewCard { background:#ffffff; border-color:#d7dee5; }
QCheckBox::indicator, QRadioButton::indicator { background:#ffffff; border-color:#7b8792; }
'''
LIGHT_STYLE = DARK_STYLE + LIGHT_OVERRIDE


def style_for_theme(theme: str, *, system_is_dark: bool | None = None) -> str:
    theme = theme if theme in {'dark', 'light', 'system'} else 'dark'
    if theme == 'light':
        return LIGHT_STYLE
    if theme == 'system':
        if system_is_dark is None:
            try:
                from PySide6.QtGui import QGuiApplication
                color = QGuiApplication.palette().window().color()
                system_is_dark = color.lightness() < 128
            except Exception:
                system_is_dark = True
        return DARK_STYLE if system_is_dark else LIGHT_STYLE
    return DARK_STYLE

# v0.4.2 library manager
APP_STYLE += r'''
QFrame#ActiveLibraryCard { background:#10251b; border:2px solid #43d17d; border-radius:11px; }
QPushButton#ActiveLibraryBadge { background:#10251b; border:2px solid #43d17d; color:#d9ffe6; border-radius:10px; padding:7px 12px; font-weight:900; }
QPushButton#ActiveLibraryBadge:hover { background:#173126; border-color:#68e49a; }
QLabel#ActiveLibraryHeading { color:#8fe9ad; font-size:8.5pt; font-weight:900; letter-spacing:1px; }
QLabel#ActiveLibraryName { color:#f1fff6; font-size:15pt; font-weight:900; }
QPushButton#MainLibraryCard { text-align:left; background:#151b23; border:1px solid #34404c; border-radius:10px; padding:10px 14px; color:#dbe5ed; font-weight:700; }
QPushButton#MainLibraryCard:hover { background:#19242d; border-color:#5a7183; }
QPushButton#MainLibraryCard:checked { background:#1d3f5c; border:1px solid #5ca3d6; color:#e7f4ff; }
QPushButton#MainLibraryCard[activeLibrary="true"] { background:#173126; border:2px solid #43d17d; color:#d9ffe6; }
QListWidget#LibraryProfileList { background:#0f151b; border:1px solid #2d3844; border-radius:9px; padding:4px; }
QListWidget#LibraryProfileList::item { border-bottom:1px solid #202a34; padding:6px 8px; }
QListWidget#LibraryProfileList::item:selected { background:#1d3f5c; color:#e7f4ff; border:1px solid #5ca3d6; border-radius:7px; }
QPushButton#RemoveLibraryAction { background:#351b1d; border:1px solid #8c454b; color:#ffc9cd; }
QPushButton#RemoveLibraryAction:hover { background:#482327; border-color:#bc5c65; }
'''
# refresh dark compatibility alias after v0.4.2 additions
DARK_STYLE = APP_STYLE

# v0.4.4 review/status/player clarity
APP_STYLE += r'''
QFrame#CurrentStatusBanner { background:#171d24; border:1px solid #36414e; border-left:6px solid #718090; border-radius:9px; }
QFrame#CurrentStatusBanner[statusKind="ready"] { background:#10251b; border-color:#2b6946; border-left:6px solid #43d17d; }
QFrame#CurrentStatusBanner[statusKind="review"] { background:#2d2111; border-color:#735225; border-left:6px solid #ffb84d; }
QFrame#CurrentStatusBanner[statusKind="reviewCritical"] { background:#311719; border-color:#8f3b42; border-left:6px solid #ff666f; }
QFrame#CurrentStatusBanner[statusKind="duplicate"] { background:#261a33; border-color:#67458c; border-left:6px solid #b987ff; }
QFrame#CurrentStatusBanner[statusKind="not_selected"] { background:#20252c; border-color:#48525e; border-left:6px solid #9ba6b2; }
QFrame#CurrentStatusBanner[statusKind="error"] { background:#35191b; border-color:#8f3b42; border-left:6px solid #ff666f; }
QLabel#CurrentStatusText { color:#f3f7fb; font-size:11pt; font-weight:900; letter-spacing:.4px; }
QLabel#CurrentStatusHint { color:#b8c4cf; font-size:9pt; font-weight:750; }
QPushButton#ApproveButton[currentStatusKind="review"] { background:#5a401b; border-color:#a9782f; color:#ffe4b4; }
QPushButton#ApproveButton[currentStatusKind="reviewCritical"] { background:#63272d; border-color:#bd525c; color:#ffe4e6; }
QPushButton#ApproveButton[currentStatusKind="duplicate"] { background:#452b5e; border-color:#8154ac; color:#f0ddff; }
QPushButton#OpenMetadataUrlButton { background:#152b36; border:1px solid #3d788d; color:#bdebf4; font-weight:750; padding:8px 11px; }
QPushButton#OpenMetadataUrlButton:hover { background:#1d3b49; border-color:#5ea6bf; }
QPushButton#OpenMetadataUrlButton:disabled { background:#171b20; border-color:#2b333c; color:#5e6974; }
QLabel#PlayerSource { color:#69cbd8; font-size:8.7pt; font-weight:750; }
QLabel#PlayerQueue { color:#ffc66d; font-size:8.7pt; font-weight:750; }
'''
DARK_STYLE = APP_STYLE


# v0.4.5 metadata snapshot emphasis
APP_STYLE += r'''
QFrame#PreOnlineSnapshotCard { background:#171a24; border:1px solid #544a70; border-left:4px solid #a77dff; border-radius:9px; }
QLabel#PreOnlineSnapshotText { color:#f2f5f8; font-size:12.2pt; font-weight:760; padding:4px 0; }
'''
DARK_STYLE = APP_STYLE

APP_STYLE += r'''
QTableWidget#DuplicateFiles { background:#0f151b; border:1px solid #2d3844; border-radius:9px; gridline-color:#252e38; }
QTableWidget#DuplicateFiles::item { padding:6px 7px; border-bottom:1px solid #222b34; }
QTableWidget#DuplicateFiles::item:selected { color:#ffffff; border:1px solid #8ea0b2; font-weight:750; }
'''
DARK_STYLE = APP_STYLE

APP_STYLE += r'''
QFrame#VersionFamilyCard { background:#151d25; border:1px solid #355267; border-left:4px solid #63a8d1; border-radius:9px; }
QLabel#VersionFamilyHeading { color:#9fd4f0; font-size:9pt; font-weight:900; letter-spacing:.5px; }
QLabel#VersionFamilyText { color:#dce9f1; font-size:9.5pt; }
'''
DARK_STYLE = APP_STYLE

APP_STYLE += r'''
QFrame#PlayerTransportPanel { background:#101820; border:1px solid #384a59; border-radius:11px; }
QLabel#PlayerMiniHeading { color:#8c9cab; font-size:7.8pt; font-weight:900; letter-spacing:1.2px; }
QPushButton#PlayerSkipButton { background:#18212b; border:1px solid #3a4a58; color:#d4dee7; border-radius:8px; padding:5px 9px; font-weight:800; }
QPushButton#PlayerSkipButton:hover { background:#202c37; border-color:#607486; color:#ffffff; }
QPushButton#PlayButton { background:#22a861; color:#ffffff; border:1px solid #56dc91; border-radius:31px; font-size:20pt; font-weight:900; padding:0; }
QPushButton#PlayButton:hover { background:#2cc574; border-color:#83e7ad; }
QFrame#PlayerTimelinePanel { background:#0d141a; border:1px solid #2d3a45; border-radius:9px; }

QPushButton#ActivateLibraryAction { background:#173a5e; border:1px solid #5ca3ff; color:#eaf4ff; font-weight:800; padding:8px 12px; }
QPushButton#ActivateLibraryAction:hover { background:#214a70; border-color:#79b8ff; }
QPushButton#ActivateLibraryAction:disabled { background:#173126; border:1px solid #3a7653; color:#86d9a4; }
QToolButton#LibraryActionsMenuButton { min-width:38px; background:#19212b; border:1px solid #3d4a58; border-radius:8px; color:#e3ebf2; font-size:15pt; font-weight:900; padding:4px 7px; }
QToolButton#LibraryActionsMenuButton:hover { background:#24303c; border-color:#617487; }

QLabel#ActiveLibraryPathLink { color:#8fe9ad; font-size:9.4pt; }
QFrame#ScanHistoryCard { background:#111820; border:1px solid #2f3d49; border-radius:10px; }
QListWidget#ScanHistoryList { background:#0c1217; border:1px solid #283540; border-radius:7px; padding:3px; }
QListWidget#ScanHistoryList::item { padding:7px 8px; border-bottom:1px solid #202a32; color:#d1dae2; }
'''
DARK_STYLE = APP_STYLE

# v0.4.6 navigation/library cleanup
APP_STYLE += r'''
QPushButton#ManageLibrariesNavAction { background:#151c25; border:1px solid #46586a; color:#d8e5ef; border-radius:9px; padding:8px 13px; font-weight:800; }
QPushButton#ManageLibrariesNavAction:hover { background:#1d2935; border-color:#6f879d; color:#ffffff; }
QPushButton#AddFilesAction { background:#122b4a; border:1px solid #4a91ff; color:#d7e9ff; font-weight:850; padding:10px 18px; }
QPushButton#AddFilesAction:hover { background:#183a61; border-color:#76aeff; color:#ffffff; }
QPushButton#SubtleDangerAction { background:transparent; border:1px solid #704047; color:#e4a9ae; padding:5px 9px; font-size:8.5pt; font-weight:700; }
QPushButton#SubtleDangerAction:hover { background:#311a1d; border-color:#a6545c; color:#ffd5d8; }
'''
DARK_STYLE = APP_STYLE

# v0.4.7 whole-track online identification lock / v0.4.8 button presentation
APP_STYLE += r'''
QPushButton#OnlineLockButton {
    background:#172331; border:1px solid #3c5e7a; border-radius:9px; padding:9px 13px;
    color:#cfe8ff; font-weight:800;
}
QPushButton#OnlineLockButton:hover { background:#1b2d40; border-color:#5f8eb3; color:#ffffff; }
QPushButton#OnlineLockButton[lockedOnline="true"] {
    background:#173957; border:1px solid #5ca3d6; color:#e8f5ff;
}
QPushButton#OnlineLockButton[lockedOnline="true"]:hover { background:#1d476b; border-color:#79bde9; }
'''
DARK_STYLE = APP_STYLE

# v0.4.10 persistent library view summary.
APP_STYLE += r'''
QLabel#LibraryViewState {
    color:#8ea0b2;
    font-size:8.8pt;
    font-weight:650;
    padding:1px 3px;
}
'''
DARK_STYLE = APP_STYLE


# v0.4.16 elegant controls + metadata editor refresh
APP_STYLE += r'''
/* Navigation: one quiet visual language; only the active item is accented. */
QPushButton#TopNavButton {
    background:transparent; border:1px solid transparent; border-radius:8px;
    color:#aeb9c4; padding:7px 11px; font-weight:700;
}
QPushButton#TopNavButton:hover { background:#121b22; border-color:#33424e; color:#e5edf3; }
QPushButton#TopNavButton:checked {
    background:#111d19; border:1px solid #43d17d; color:#7ee7a5;
}
QPushButton#TopNavButton[hasItems="true"]:!checked {
    background:transparent; border-color:#3a4652; color:#b7c2cc;
}

/* Workflow buttons: no rainbow fills. */
QFrame#ToolbarFrame QPushButton#Primary,
QFrame#ToolbarFrame QPushButton#IdentifyOnlineAction,
QFrame#ToolbarFrame QPushButton#ReviewAction,
QFrame#ToolbarFrame QPushButton#ExportAction,
QFrame#ToolbarFrame QPushButton#AddFilesAction {
    background:#121920; border:1px solid #35424f; border-radius:8px;
    color:#c7d0d9; padding:9px 14px; font-weight:780;
}
QFrame#ToolbarFrame QPushButton#Primary:hover,
QFrame#ToolbarFrame QPushButton#IdentifyOnlineAction:hover,
QFrame#ToolbarFrame QPushButton#ReviewAction:hover,
QFrame#ToolbarFrame QPushButton#ExportAction:hover,
QFrame#ToolbarFrame QPushButton#AddFilesAction:hover {
    background:#172129; border-color:#586a79; color:#ffffff;
}
QFrame#ToolbarFrame QPushButton[operationActive="true"] {
    background:#101e19; border:1px solid #43d17d; color:#7ee7a5;
}
QFrame#ToolbarFrame QPushButton#CancelScanAction,
QFrame#ToolbarFrame QPushButton#CancelOnlineAction {
    background:#231719; border:1px solid #94505a; color:#ffcbd0;
}

/* Settings / providers. */
QFrame#ProviderCard {
    background:#101820; border:1px solid #2d3a46; border-radius:10px;
}
QFrame#ProviderCard:hover { border-color:#405363; }
QLabel#ProviderIcon {
    color:#79dca0; font-size:17pt; font-weight:900; min-width:28px;
}
QLabel#ProviderKeyBadge {
    color:#dce5ed; background:#202934; border:1px solid #4a5866;
    border-radius:7px; padding:3px 7px; font-size:7.8pt; font-weight:850;
}
QLabel#ProviderNoKeyBadge {
    color:#8fe9ad; background:#13281c; border:1px solid #356d4c;
    border-radius:7px; padding:3px 7px; font-size:7.8pt; font-weight:850;
}
QLineEdit#ProviderSecretField {
    background:#0d141a; border:1px solid #40515f; border-radius:7px;
    color:#e7edf2; padding:7px 9px;
}
QLineEdit#ProviderSecretField:focus { border-color:#66a7d5; }

/* Metadata editor. */
QFrame#MetadataStatusCompact,
QFrame#RecognitionInfoCompact,
QFrame#SourceComparisonCard {
    background:#0f171e; border:1px solid #2b3945; border-radius:9px;
}
QLabel#CompactPanelTitle {
    color:#b9c7d2; font-size:8.7pt; font-weight:850; letter-spacing:.3px;
}
QLabel#MetadataStatusItem {
    color:#9aa8b5; font-size:8.7pt; padding:1px 2px;
}
QLabel#MetadataStatusItem[statusKind="ok"] { color:#79dda0; }
QLabel#MetadataStatusItem[statusKind="missing"] { color:#ffbd61; font-weight:760; }
QLabel#MetadataStatusItem[statusKind="neutral"] { color:#7f8d99; }
QLabel#RecognitionInfoText {
    color:#85939f; font-size:7.9pt; line-height:1.1;
}
QFrame#RecognitionInfoCompact QFrame#ConfidenceWidget { max-height:52px; }
QFrame#RecognitionInfoCompact QLabel#ConfidencePercent { font-size:10pt; color:#9daab5; }
QFrame#RecognitionInfoCompact QLabel#ConfidenceDescription { font-size:7.3pt; color:#687580; }
QFrame#RecognitionInfoCompact QProgressBar#ConfidenceBar {
    min-height:5px; max-height:5px; border:0; background:#222c35;
}
QFrame#PrimaryMetadataCard { background:#101820; border:1px solid #2f4f43; border-radius:9px; }
QLabel#MetadataHintText { color:#66737f; font-size:8pt; padding:0 3px; }
QFrame#FilenamePreviewCard { background:#0f1816; border:1px solid #294738; border-radius:9px; }

/* Source badges are informative but visually quiet. */
QToolButton#MetadataSourceBadge {
    background:#171f27; border:1px solid #3a4651; color:#aeb9c3;
    min-width:72px; padding:3px 6px; font-size:7.6pt; font-weight:780;
}
QToolButton#MetadataSourceBadge:hover { border-color:#617282; color:#eef4f8; }
QToolButton#MetadataSourceBadge[sourceKind="tag"],
QToolButton#MetadataSourceBadge[sourceKind="discogs"],
QToolButton#MetadataSourceBadge[sourceKind="musicbrainz"],
QToolButton#MetadataSourceBadge[sourceKind="apple"],
QToolButton#MetadataSourceBadge[sourceKind="manual"],
QToolButton#MetadataSourceBadge[sourceKind="analysis"],
QToolButton#MetadataSourceBadge[sourceKind="filename"] {
    background:#171f27; border-color:#3a4651; color:#b7c3cd;
}

/* Cover chooser: larger selected art + dense all-at-once proposals. */
QLabel#CoverMainPreview {
    background:#080d11; border:1px solid #3d7d5b; border-radius:9px; color:#7e8b96;
}
QFrame#CoverProposalCard {
    background:#111820; border:1px solid #283641; border-radius:7px;
}
QFrame#CoverProposalCard[selected="true"] {
    background:#102019; border:1px solid #43d17d;
}
QLabel#CoverProposalPreview {
    background:#090e13; border:0; border-radius:5px; color:#687580;
}
QLabel#CoverProposalCaption {
    color:#7f8d99; font-size:7.1pt; max-width:76px;
}
QFrame#CoverProposalCard[selected="true"] QLabel#CoverProposalCaption { color:#8fe9ad; font-weight:800; }
QPushButton#CoverSmallAction, QPushButton#CoverMoreAction {
    background:#131b23; border:1px solid #344552; color:#b8c5cf;
    border-radius:7px; padding:6px 9px; font-size:8.5pt;
}
QPushButton#CoverSmallAction:hover, QPushButton#CoverMoreAction:hover {
    border-color:#5f7484; color:#ffffff; background:#18232c;
}

/* Source comparison and its tiny legend icon. */
QTableWidget#SourceComparisonTable {
    background:#0b1218; alternate-background-color:#0e161d;
    border:1px solid #24313b; border-radius:6px; gridline-color:#1d2932;
    font-size:8.2pt;
}
QTableWidget#SourceComparisonTable QHeaderView::section {
    background:#131d25; color:#8596a5; padding:4px 6px; font-size:7.7pt;
}
QToolButton#SourceLegendInfoButton {
    background:transparent; border:1px solid #40505d; border-radius:10px;
    color:#8fa2b2; min-width:20px; max-width:20px; min-height:20px; max-height:20px; padding:0;
}
QToolButton#SourceLegendInfoButton:hover { border-color:#6d8496; color:#dce8f0; }
QPushButton#UseSourceDataButton {
    background:transparent; border:1px solid #3b4a56; color:#aab7c1;
    border-radius:6px; padding:3px 7px; font-size:7.8pt;
}
QPushButton#UseSourceDataButton:hover { border-color:#43d17d; color:#8fe9ad; }

/* Minimal editor player: intentionally no artwork, very wide scrubber. */
QFrame#CompactPlayerBar {
    background:#0b1217; border:1px solid #31424d; border-radius:9px;
}
QLabel#CompactPlayerHeading { color:#65cfd9; font-size:7.8pt; font-weight:900; letter-spacing:.7px; }
QPushButton#CompactPlayButton {
    background:#142a20; border:1px solid #43d17d; border-radius:7px;
    color:#8fe9ad; font-size:11pt; font-weight:900; padding:0;
}
QSlider#CompactSeekSlider::groove:horizontal { height:7px; background:#26313a; border-radius:3px; }
QSlider#CompactSeekSlider::handle:horizontal { width:15px; margin:-4px 0; border-radius:7px; background:#43d17d; }
QSlider#CompactVolumeSlider::groove:horizontal { height:5px; background:#26313a; border-radius:2px; }
QSlider#CompactVolumeSlider::handle:horizontal { width:13px; margin:-4px 0; border-radius:6px; background:#43d17d; }
QLabel#CompactPlayerMeta { color:#788693; font-size:8pt; }

/* Global footer player: compact, flat, functional. */
QWidget#PlayerBar { background:#090d12; }
QFrame#PlayerCard { background:#0e151b; border:1px solid #293844; border-radius:11px; }
QLabel#PlayerCover { background:#080c10; border:1px solid #283944; border-radius:7px; }
QPushButton#PlayerIconButton {
    background:transparent; border:1px solid #33414d; color:#b4c0ca;
    border-radius:8px; padding:4px; font-weight:800;
}
QPushButton#PlayerIconButton:hover { border-color:#5e7180; color:#ffffff; background:#151e25; }
QPushButton#PlayerIconButton:checked { border-color:#43d17d; color:#8fe9ad; background:#102019; }
QPushButton#PlayButton {
    background:#142a20; color:#dffff0; border:1px solid #43d17d;
    border-radius:28px; font-size:18pt; font-weight:900; padding:0;
}
QPushButton#PlayButton:hover { background:#183727; border-color:#65e19a; }
QLabel#PlaybackStatus { color:#67d995; font-size:8pt; font-weight:800; }
QLabel#PlayerArtist { font-size:10.5pt; font-weight:850; color:#f0f5f8; }
QPushButton#PlayerTitleLink { color:#d9e2e9; font-size:9pt; text-align:left; padding:0; border:0; background:transparent; }
QPushButton#PlayerTitleLink:hover { color:#ffffff; text-decoration:underline; }
QLabel#PlayerMeta { color:#71808d; font-size:8pt; }
QSlider#SeekSlider::groove:horizontal { height:6px; background:#26313a; border-radius:3px; }
QSlider#SeekSlider::handle:horizontal { width:15px; margin:-4px 0; border-radius:7px; background:#43d17d; }
QSlider#VolumeSlider::groove:horizontal { height:5px; background:#26313a; border-radius:2px; }
QSlider#VolumeSlider::handle:horizontal { width:13px; margin:-4px 0; border-radius:6px; background:#43d17d; }
'''
DARK_STYLE = APP_STYLE


# v0.4.16 final metadata-editor visual pass
APP_STYLE += r'''
/* Status should read instantly: green = complete, amber = needs attention. */
QFrame#MetadataStatusCompact {
    background:#0f171e; border:1px solid #31414d; border-radius:9px;
}
QFrame#MetadataStatusRow {
    background:transparent; border:1px solid transparent; border-radius:6px;
}
QFrame#MetadataStatusRow[statusKind="missing"] {
    background:#2a2013; border-color:#60471f;
}
QFrame#MetadataStatusRow[statusKind="neutral"] {
    background:#111820; border-color:#26333d;
}
QLabel#MetadataStatusIcon {
    border-radius:9px; min-width:18px; max-width:18px; min-height:18px; max-height:18px;
    font-size:9pt; font-weight:950;
}
QLabel#MetadataStatusIcon[statusKind="ok"] {
    background:#123d26; border:1px solid #32b96c; color:#b5f3cb;
}
QLabel#MetadataStatusIcon[statusKind="missing"] {
    background:#553713; border:1px solid #d08d2e; color:#ffe0a4;
}
QLabel#MetadataStatusIcon[statusKind="neutral"] {
    background:#1b252d; border:1px solid #52606c; color:#9ca9b4;
}
QLabel#MetadataStatusText {
    color:#aeb9c3; font-size:8.7pt; padding:0;
}
QLabel#MetadataStatusText[statusKind="ok"] { color:#d6e8dd; }
QLabel#MetadataStatusText[statusKind="missing"] { color:#ffc76b; font-weight:820; }
QLabel#MetadataStatusText[statusKind="neutral"] { color:#7f8c97; }

/* Recognition is supportive information, not the visual headline. */
QFrame#RecognitionInfoCompact {
    background:#0d151b; border:1px solid #293843; border-radius:9px;
}
QLabel#RecognitionInfoText {
    color:#a5b1bc; font-size:8pt; padding:1px 0;
}
QLabel#RecognitionConfidenceLabel {
    color:#72808b; font-size:7.7pt; font-weight:700;
}
QLabel#RecognitionConfidencePercent {
    color:#8a97a2; font-size:8.4pt; font-weight:850;
}
QLabel#RecognitionConfidencePercent[confidenceKind="high"] { color:#67d995; }
QLabel#RecognitionConfidencePercent[confidenceKind="medium"] { color:#f2b654; }
QLabel#RecognitionConfidencePercent[confidenceKind="low"] { color:#ef7077; }
QProgressBar#RecognitionConfidenceBar {
    background:#202a32; border:0; border-radius:3px; min-height:6px; max-height:6px;
}
QProgressBar#RecognitionConfidenceBar::chunk { background:#596873; border-radius:3px; }
QProgressBar#RecognitionConfidenceBar[confidenceKind="high"]::chunk { background:#43d17d; }
QProgressBar#RecognitionConfidenceBar[confidenceKind="medium"]::chunk { background:#e9a947; }
QProgressBar#RecognitionConfidenceBar[confidenceKind="low"]::chunk { background:#e75f67; }

/* Cover area follows available results instead of leaving a large empty grid. */
QFrame#CoverGallery {
    background:#0f171e; border:1px solid #30414d; border-radius:9px;
}
QWidget#CoverProposalsHost { background:transparent; }
QLabel#CoverMainPreview {
    background:#080d11; border:1px solid #3a7957; border-radius:9px; color:#7e8b96;
}
QFrame#CoverProposalCard {
    background:#111920; border:1px solid #2c3943; border-radius:7px;
}
QFrame#CoverProposalCard[selected="true"] {
    background:#102219; border:1px solid #43d17d;
}
QLabel#CoverProposalCaption {
    color:#8997a3; font-size:7pt;
}
QFrame#CoverProposalCard[selected="true"] QLabel#CoverProposalCaption {
    color:#91ebb0; font-weight:850;
}
QPushButton#CoverSmallAction {
    min-height:28px; padding:4px 8px;
}

/* Compact comparison: readable source names and a real action button. */
QFrame#SourceComparisonCard {
    background:#0e161d; border:1px solid #2d3c47; border-radius:9px;
}
QTableWidget#SourceComparisonTable {
    background:#0a1117; alternate-background-color:#0c141a;
    border:1px solid #27343e; border-radius:6px; gridline-color:#202b34;
    font-size:8pt;
}
QTableWidget#SourceComparisonTable::item {
    padding:3px 7px; color:#c5d0d9; border-bottom:1px solid #1d2830;
}
QTableWidget#SourceComparisonTable QHeaderView::section {
    background:#141e26; color:#94a4b1; padding:4px 7px;
    border-right:1px solid #26343e; font-size:7.7pt; font-weight:800;
}
QPushButton#UseSourceDataButton {
    background:#16212a; border:1px solid #4a5b68; color:#e0e8ee;
    border-radius:6px; padding:3px 8px; font-size:7.8pt; font-weight:800;
}
QPushButton#UseSourceDataButton:hover {
    background:#14271d; border-color:#43d17d; color:#a8efc0;
}
QToolButton#SourceLegendInfoButton {
    background:#142538; border:1px solid #4f8fc2; border-radius:12px;
    color:#c5e6ff; min-width:24px; max-width:24px; min-height:24px; max-height:24px;
    padding:0; font-size:9pt; font-weight:950;
}
QToolButton#SourceLegendInfoButton:hover {
    background:#1a3047; border-color:#75b9ed; color:#ffffff;
}
QMenu#SourceLegendMenu {
    background:#111920; color:#d6e0e7; border:1px solid #40515e; padding:5px;
}
QMenu#SourceLegendMenu::item {
    padding:6px 12px; border-radius:5px;
}
QMenu#SourceLegendMenu::item:selected {
    background:#1c2b36; color:#ffffff;
}
QMenu#SourceLegendMenu::separator {
    height:1px; background:#31404b; margin:4px 8px;
}

/* Required empty controls stay visibly marked, including the genre editor. */
QLineEdit[missingRequired="true"] {
    border:1px solid #a56b2c; background:#221a12;
}
QLineEdit[missingRequired="true"]:focus {
    border:1px solid #d89236; background:#291e12;
}
'''
DARK_STYLE = APP_STYLE


# v0.4.17 — final pass based on approved editor mockup and review screenshots
APP_STYLE += r'''
/* Navigation and workflow: real icons come from Qt; buttons stay calm and consistent. */
QPushButton#TopNavButton {
    border-radius:10px; padding:7px 12px; min-height:26px;
}
QFrame#ToolbarFrame QPushButton#Primary,
QFrame#ToolbarFrame QPushButton#IdentifyOnlineAction,
QFrame#ToolbarFrame QPushButton#ReviewAction,
QFrame#ToolbarFrame QPushButton#ExportAction,
QFrame#ToolbarFrame QPushButton#AddFilesAction {
    border-radius:10px; min-height:28px; padding:8px 14px;
}

/* File status: the state must be readable before the text is read. */
QFrame#MetadataStatusRow[statusKind="ok"] {
    background:transparent; border-color:transparent;
}
QLabel#MetadataStatusText[statusKind="ok"] {
    color:#73dea0; font-weight:780;
}
QFrame#MetadataStatusRow[statusKind="missing"] {
    background:#2a2013; border:1px solid #6c4d20;
}
QLabel#MetadataStatusText[statusKind="missing"] {
    color:#ffc568; font-weight:820;
}
QLabel#MetadataStatusIcon[statusKind="ok"] {
    background:#123d26; border:1px solid #39c876; color:#c5f6d6;
}
QLabel#MetadataStatusIcon[statusKind="missing"] {
    background:#5b3911; border:1px solid #df952d; color:#ffe1a7;
}
QLabel#MetadataStatusIcon[statusKind="neutral"] {
    background:#1a242c; border:1px solid #55636e; color:#a2adb6;
}

/* Recognition: one clear line per fact, then confidence. */
QFrame#RecognitionInfoCompact {
    background:#0d151b; border:1px solid #2d3b46; border-radius:10px;
}
QLabel#RecognitionFieldName {
    color:#778692; font-size:7.9pt; font-weight:700;
}
QLabel#RecognitionFieldValue {
    color:#c8d2da; font-size:8.2pt; font-weight:760;
}
QLabel#RecognitionConfidencePercent {
    font-size:8.2pt; font-weight:850;
}

/* Filename helper is deliberately secondary. */
QLabel#MetadataHintText {
    color:#5e6b76; font-size:7.8pt; font-style:italic; padding:1px 3px;
}

/* Source comparison: whole-row selection, no white focus rectangle. */
QTableWidget#SourceComparisonTable {
    selection-background-color:#18372a;
    selection-color:#f1f8f4;
    outline:0;
}
QTableWidget#SourceComparisonTable::item {
    padding:4px 7px;
    border:0;
    border-bottom:1px solid #1d2932;
}
QTableWidget#SourceComparisonTable::item:selected {
    background:#18372a;
    color:#f1f8f4;
    border:0;
}
QPushButton#UseSourceDataButton {
    background:#17232b; border:1px solid #52626e; color:#e5edf2;
    border-radius:7px; min-height:29px; padding:3px 9px;
    font-size:8.2pt; font-weight:820;
}
QPushButton#UseSourceDataButton:hover {
    background:#153024; border-color:#48d681; color:#b7f2cb;
}
QToolButton#SourceLegendInfoButton {
    background:#132535; border:1px solid #4b809f; border-radius:14px;
    min-width:28px; max-width:28px; min-height:28px; max-height:28px;
    padding:0;
}
QToolButton#SourceLegendInfoButton:hover {
    background:#193145; border-color:#70b5dc;
}
QMenu#SourceLegendMenu {
    icon-size:12px;
}

/* Editor mini-player: compact but not cramped. */
QFrame#CompactPlayerBar {
    background:#0b1217; border:1px solid #31434e; border-radius:12px;
}
QPushButton#CompactPlayButton {
    background:#153425; border:1px solid #49d681; border-radius:20px;
    color:#dffff0; padding:0;
}
QPushButton#CompactPlayButton:hover {
    background:#1a422e; border-color:#72e9a2;
}

/* Main player: round transport controls instead of hard rectangles. */
QFrame#PlayerCard {
    background:#0e151b; border:1px solid #2b3b46; border-radius:16px;
}
QPushButton#PlayerIconButton {
    background:#121b22; border:1px solid #3a4955; color:#c2ccd4;
    border-radius:22px; padding:0;
}
QPushButton#PlayerIconButton:hover {
    background:#18242d; border-color:#607380; color:#ffffff;
}
QPushButton#PlayerIconButton:checked {
    background:#153125; border-color:#48d681; color:#aef0c5;
}
QPushButton#PlayButton {
    background:#153425; border:1px solid #48d681; border-radius:29px;
    color:#effff5; padding:0;
}
QPushButton#PlayButton:hover {
    background:#1b4630; border-color:#71e9a2;
}
'''
DARK_STYLE = APP_STYLE


# v0.4.18 — visual baseline aligned with the approved mockup
APP_STYLE += r'''
/* Top navigation: one dark language, custom ALO icons provide the color. */
QPushButton#TopNavButton {
    background:transparent;
    border:1px solid transparent;
    border-radius:9px;
    color:#c3ced7;
    padding:8px 12px;
    min-height:28px;
    font-weight:760;
}
QPushButton#TopNavButton:hover {
    background:#101a21;
    border-color:#334651;
    color:#ffffff;
}
QPushButton#TopNavButton:checked {
    background:#0f251c;
    border:1px solid #1bcf7a;
    color:#52e59b;
}
QPushButton#TopNavButton[hasItems="true"]:!checked {
    background:transparent;
    border-color:transparent;
    color:#c3ced7;
}
QPushButton#ManageLibrariesNavAction {
    background:#10171e;
    border:1px solid #34434f;
    color:#c6d0d8;
}

/* Workflow: remove old green/amber/teal fills; only active step is accented. */
QFrame#ToolbarFrame QPushButton#Primary,
QFrame#ToolbarFrame QPushButton#IdentifyOnlineAction,
QFrame#ToolbarFrame QPushButton#ReviewAction,
QFrame#ToolbarFrame QPushButton#ExportAction,
QFrame#ToolbarFrame QPushButton#AddFilesAction {
    background:#101820;
    border:1px solid #344551;
    color:#d1d9df;
    border-radius:9px;
    min-height:30px;
    padding:9px 15px;
    font-weight:800;
}
QFrame#ToolbarFrame QPushButton#Primary:hover,
QFrame#ToolbarFrame QPushButton#IdentifyOnlineAction:hover,
QFrame#ToolbarFrame QPushButton#ReviewAction:hover,
QFrame#ToolbarFrame QPushButton#ExportAction:hover,
QFrame#ToolbarFrame QPushButton#AddFilesAction:hover {
    background:#15222a;
    border-color:#527080;
    color:#ffffff;
}
QFrame#ToolbarFrame QPushButton#Primary[operationActive="true"],
QFrame#ToolbarFrame QPushButton#IdentifyOnlineAction[operationActive="true"],
QFrame#ToolbarFrame QPushButton#ReviewAction[operationActive="true"],
QFrame#ToolbarFrame QPushButton#ExportAction[operationActive="true"],
QFrame#ToolbarFrame QPushButton#AddFilesAction[operationActive="true"],
QFrame#ToolbarFrame QPushButton[running="true"] {
    background:#0f2a1e;
    border:1px solid #1fd27d;
    color:#63e6a0;
}
QFrame#WorkflowToolbarGroup {
    background:#0b1319;
    border:1px solid #263943;
    border-radius:10px;
}
QLabel#WorkflowStepArrow { color:#6d7c88; }

/* Settings provider section. */
QLabel#SettingsCardTitle {
    color:#e2edf5;
    font-size:13pt;
    font-weight:820;
}
QFrame#IntegrationCard {
    background:#0d1720;
    border:1px solid #2c4557;
    border-radius:12px;
}
QFrame#ProviderCard {
    background:#101920;
    border:1px solid #2f3f4b;
    border-radius:10px;
}
QFrame#ProviderCard[providerKind="acoustid"] { border-color:#31576a; }
QFrame#ProviderCard[providerKind="discogs"] { border-color:#315c46; }
QFrame#ProviderCard[providerKind="musicbrainz"] { border-color:#55406f; }
QFrame#ProviderCard[providerKind="apple"] { border-color:#623c45; }
QLabel#ProviderIcon { background:transparent; border:0; }
QLabel#ProviderKeyBadge {
    color:#e4edf3;
    background:#202b34;
    border:1px solid #53636f;
    border-radius:8px;
    padding:4px 8px;
    font-size:8pt;
    font-weight:850;
}
QLabel#ProviderNoKeyBadge {
    color:#7ce8a3;
    background:#10291c;
    border:1px solid #32764e;
    border-radius:8px;
    padding:4px 8px;
    font-size:8pt;
    font-weight:850;
}

/* Metadata editor cards use the same table/card language as the approved design. */
QFrame#PrimaryMetadataCard,
QFrame#MetadataStatusCompact,
QFrame#RecognitionInfoCompact,
QFrame#CoverGallery,
QFrame#FilenamePreviewCard,
QFrame#SourceComparisonCard {
    background:#0c151c;
    border:1px solid #2d4654;
    border-radius:10px;
}
QFrame#PrimaryMetadataCard { border-color:#2a5b45; }
QFrame#FilenamePreviewCard { border-color:#294b3b; }

QLabel#MetadataSectionTitle {
    color:#65e2a0;
    font-size:9.5pt;
    font-weight:900;
    letter-spacing:.8px;
}
QLabel#CompactPanelTitle {
    color:#d2dce3;
    font-size:8.6pt;
    font-weight:850;
}

/* Status rows intentionally stay clean; icons + text carry the state color. */
QFrame#MetadataStatusRow,
QFrame#MetadataStatusRow[statusKind="ok"],
QFrame#MetadataStatusRow[statusKind="missing"],
QFrame#MetadataStatusRow[statusKind="neutral"] {
    background:transparent;
    border:0;
    border-radius:0;
}

/* Recognition remains compact and ordered like a small information table. */
QLabel#RecognitionFieldName {
    color:#7e8c97;
    font-size:8pt;
    font-weight:700;
}
QLabel#RecognitionFieldValue {
    color:#d1dbe2;
    font-size:8.2pt;
    font-weight:780;
}
QProgressBar#RecognitionConfidenceBar {
    background:#1c2931;
    border:0;
    border-radius:3px;
}

/* Strongly secondary filename help text. */
QLabel#MetadataHintText {
    color:#596773;
    font-size:8pt;
    font-style:italic;
    padding:2px 3px;
}

/* Cover presentation: selected artwork + compact candidate cards. */
QLabel#CoverMainPreview {
    background:#080d11;
    border:2px solid #2fcf7c;
    border-radius:8px;
}
QFrame#CoverProposalCard {
    background:#101820;
    border:1px solid #2c3b47;
    border-radius:7px;
}
QFrame#CoverProposalCard[selected="true"] {
    background:#0d2118;
    border:1px solid #2fcf7c;
}
QLabel#CoverProposalCaption {
    color:#9aa8b3;
    font-size:7.2pt;
}
QFrame#CoverProposalCard[selected="true"] QLabel#CoverProposalCaption {
    color:#66e29d;
    font-weight:850;
}

/* Source table: roomy action column and readable full button. */
QTableWidget#SourceComparisonTable {
    background:#091117;
    alternate-background-color:#0c151c;
    border:1px solid #2b3e49;
    border-radius:7px;
    gridline-color:#21313a;
    selection-background-color:#153b2b;
    selection-color:#f2fff7;
}
QTableWidget#SourceComparisonTable QHeaderView::section {
    background:#14212a;
    color:#d3dde4;
    min-height:28px;
    padding:5px 8px;
    border-right:1px solid #263a45;
    font-weight:820;
}
QTableWidget#SourceComparisonTable::item {
    padding:5px 8px;
    border-bottom:1px solid #1c2b33;
}
QTableWidget#SourceComparisonTable::item:selected {
    background:#153b2b;
    color:#ffffff;
    border:0;
}
QPushButton#UseSourceDataButton {
    background:#15212a;
    border:1px solid #536875;
    color:#f0f5f8;
    border-radius:7px;
    min-height:32px;
    padding:4px 12px;
    font-size:8.4pt;
    font-weight:830;
}
QPushButton#UseSourceDataButton:hover {
    background:#123021;
    border-color:#38d787;
    color:#bff5d1;
}

/* Source legend uses the same quiet info-icon language as the Library. */
QToolButton#SourceLegendInfoButton {
    background:transparent;
    border:1px solid #566875;
    border-radius:12px;
    min-width:24px;
    max-width:24px;
    min-height:24px;
    max-height:24px;
    padding:0;
}
QToolButton#SourceLegendInfoButton:hover {
    background:#16212a;
    border-color:#8aa0ae;
}

/* White media symbol, green transport surface. */
QPushButton#CompactPlayButton {
    background:#0e4a2d;
    border:1px solid #2bdd82;
    border-radius:20px;
    color:#ffffff;
}
QPushButton#PlayButton {
    background:#0f6038;
    border:1px solid #2ce186;
    border-radius:29px;
    color:#ffffff;
}
'''
DARK_STYLE = APP_STYLE


# v0.4.19 — exact visual follow-up from the approved reference screenshots
APP_STYLE += r'''
/* ===== TOP NAVIGATION ===== */
QFrame#TopNav {
    background:#081018;
    border-bottom:1px solid #17313d;
}
QPushButton#TopNavButton {
    background:transparent;
    border:1px solid transparent;
    border-radius:8px;
    color:#d2dbe2;
    padding:8px 12px;
    min-height:30px;
    font-weight:720;
}
QPushButton#TopNavButton:hover {
    background:#0d1a22;
    border-color:#274653;
    color:#ffffff;
}
QPushButton#TopNavButton:checked {
    background:#0b2a1d;
    border:1px solid #13d47a;
    color:#42e79b;
}
QPushButton#ManageLibrariesNavAction {
    background:#101922;
    border:1px solid #38505f;
    color:#d1dbe2;
    border-radius:8px;
    min-height:30px;
    padding:7px 12px;
}

/* Workflow bar follows the approved reference:
   step 1 green filled, 2/3 green outlined, 4 cyan-blue, add-files blue. */
QFrame#WorkflowToolbarGroup {
    background:#08131a;
    border:1px solid #173947;
    border-radius:10px;
}
QFrame#ToolbarFrame QPushButton#Primary {
    background:#116b45;
    border:1px solid #18c878;
    color:#ffffff;
    border-radius:9px;
    min-height:32px;
    padding:9px 18px;
    font-weight:820;
}
QFrame#ToolbarFrame QPushButton#Primary:hover {
    background:#148153;
    border-color:#2be294;
}
QFrame#ToolbarFrame QPushButton#IdentifyOnlineAction {
    background:#0a1b18;
    border:1px solid #23885f;
    color:#f3f8f5;
    border-radius:9px;
    min-height:32px;
    padding:9px 18px;
    font-weight:800;
}
QFrame#ToolbarFrame QPushButton#IdentifyOnlineAction:hover {
    background:#0d2b22;
    border-color:#2dd990;
}
QFrame#ToolbarFrame QPushButton#ReviewAction {
    background:#0b211b;
    border:1px solid #258c67;
    color:#f2f9f5;
    border-radius:9px;
    min-height:32px;
    padding:9px 18px;
    font-weight:800;
}
QFrame#ToolbarFrame QPushButton#ReviewAction:hover {
    background:#103025;
    border-color:#31d995;
}
QFrame#ToolbarFrame QPushButton#ExportAction {
    background:#0b2330;
    border:1px solid #177ca7;
    color:#eef8ff;
    border-radius:9px;
    min-height:32px;
    padding:9px 18px;
    font-weight:800;
}
QFrame#ToolbarFrame QPushButton#ExportAction:hover {
    background:#103349;
    border-color:#31a6d8;
}
QFrame#ToolbarFrame QPushButton#AddFilesAction {
    background:#0a1e35;
    border:1px solid #2385d4;
    color:#f1f7ff;
    border-radius:9px;
    min-height:32px;
    padding:9px 20px;
    font-weight:820;
}
QFrame#ToolbarFrame QPushButton#AddFilesAction:hover {
    background:#0f2c4c;
    border-color:#4ca5ed;
}
QFrame#ToolbarFrame QPushButton[operationActive="true"] {
    border-width:2px;
    color:#ffffff;
}
QLabel#WorkflowStepArrow {
    color:#9baab5;
    font-size:14pt;
    font-weight:760;
}

/* ===== EDITOR SECTION HEADERS ===== */
QWidget#EditorSectionHeader {
    background:transparent;
}
QLabel#EditorSectionTitle {
    color:#e7eef3;
    font-size:9.2pt;
    font-weight:820;
    letter-spacing:0;
    padding:1px 0 3px 0;
}

/* The cards stay dark and thin like the reference, never green-headed blocks. */
QFrame#PrimaryMetadataCard,
QFrame#MetadataStatusCompact,
QFrame#RecognitionInfoCompact,
QFrame#CoverGallery,
QFrame#FilenamePreviewCard,
QFrame#SourceComparisonCard {
    background:#0b141b;
    border:1px solid #29414d;
    border-radius:9px;
}
QFrame#PrimaryMetadataCard { border-color:#294d3f; }
QFrame#FilenamePreviewCard { border-color:#29483b; }

/* ===== TOP EDITOR ACTIONS ===== */
QPushButton#SingleTrackOnlineButton,
QPushButton#RestoreOnlineButton {
    background:#0e1820;
    border:1px solid #334d5b;
    color:#e3edf3;
    border-radius:8px;
    min-height:32px;
    padding:7px 12px;
    font-weight:720;
}
QPushButton#SingleTrackOnlineButton:hover,
QPushButton#RestoreOnlineButton:hover {
    background:#13232d;
    border-color:#4a7184;
    color:#ffffff;
}
QPushButton#RestoreOnlineButton {
    background:#0c2340;
    border-color:#2979b9;
    color:#edf7ff;
}
QPushButton#RestoreOnlineButton:hover {
    background:#10325a;
    border-color:#46a3e4;
}

/* ===== FILE STATUS ===== */
QLabel#MetadataStatusText[statusKind="ok"] {
    color:#39e58f;
    font-weight:800;
}
QLabel#MetadataStatusText[statusKind="missing"] {
    color:#f2b244;
    font-weight:820;
}
QLabel#MetadataStatusText[statusKind="neutral"] {
    color:#8796a2;
    font-weight:720;
}

/* ===== COVER PANEL ===== */
QLabel#CoverMainPreview {
    background:#070d12;
    border:2px solid #1fd27d;
    border-radius:8px;
}
QLabel#CoverSelectedBadge {
    background:#18d27d;
    border:1px solid #4cf0a2;
    border-radius:11px;
    color:#062417;
    font-size:10pt;
    font-weight:950;
}
QPushButton#CoverSmallAction,
QPushButton#CoverBrowseAction,
QPushButton#CoverMoreAction {
    background:#101a22;
    border:1px solid #344a58;
    color:#e0e8ee;
    border-radius:8px;
    min-height:28px;
    padding:6px 10px;
    font-size:8.3pt;
}
QPushButton#CoverSmallAction:hover,
QPushButton#CoverBrowseAction:hover,
QPushButton#CoverMoreAction:hover {
    background:#15232d;
    border-color:#557083;
    color:#ffffff;
}
QLabel#CoverProposalsHeading {
    color:#e3ebf0;
    background:#0f2634;
    border:1px solid #24526a;
    border-radius:6px;
    padding:4px 7px;
    font-size:8pt;
    font-weight:800;
}
QLabel#CoverProposalsCount {
    color:#8eb5ca;
    background:transparent;
    font-size:8pt;
    font-weight:760;
}
QWidget#CoverProposalsHost {
    background:transparent;
}
QFrame#CoverProposalCard {
    background:#0d151c;
    border:1px solid #293944;
    border-radius:6px;
}
QFrame#CoverProposalCard[selected="true"] {
    background:#0d2118;
    border:1px solid #24d07a;
}
QLabel#CoverProposalCaption {
    color:#8998a3;
    font-size:6.9pt;
    font-weight:650;
}
QFrame#CoverProposalCard[selected="true"] QLabel#CoverProposalCaption {
    color:#5de49b;
}

/* ===== FILENAME NOTE ===== */
QLabel#MetadataHintText {
    color:#53616d;
    font-size:7.7pt;
    font-style:italic;
    padding:2px 3px;
}

/* ===== SOURCE COMPARISON ===== */
QTableWidget#SourceComparisonTable {
    background:#081017;
    alternate-background-color:#0b141b;
    border:1px solid #273c47;
    border-radius:6px;
    gridline-color:#1c2a32;
    selection-background-color:#334b61;
    selection-color:#ffffff;
    font-size:7.9pt;
}
QTableWidget#SourceComparisonTable QHeaderView::section {
    background:#13202a;
    color:#d1dbe2;
    min-height:0;
    max-height:27px;
    padding:2px 7px;
    border-right:1px solid #263844;
    font-size:7.6pt;
    font-weight:800;
}
QTableWidget#SourceComparisonTable::item {
    padding:2px 7px;
    border-bottom:1px solid #1b2931;
}
QTableWidget#SourceComparisonTable::item:selected {
    background:#334b61;
    color:#ffffff;
    border:0;
}
QPushButton#UseSourceDataButton {
    background:#14202a;
    border:1px solid #455966;
    color:#e8eef2;
    border-radius:6px;
    min-height:27px;
    max-height:27px;
    padding:2px 10px;
    font-size:7.6pt;
    font-weight:760;
}
QPushButton#UseSourceDataButton:hover {
    background:#12281d;
    border-color:#2dcc7b;
    color:#adf0c5;
}
QToolButton#SourceLegendInfoButton {
    background:transparent;
    border:1px solid #6b7c88;
    border-radius:11px;
    min-width:22px;
    max-width:22px;
    min-height:22px;
    max-height:22px;
    padding:0;
}
QToolButton#SourceLegendInfoButton:hover {
    background:#152029;
    border-color:#a1b2bd;
}

/* ===== BOTTOM EDITOR ACTIONS ===== */
QPushButton#EditorSecondaryAction,
QPushButton#OnlineLockButton,
QPushButton#EditorCancelAction,
QPushButton#SaveMetadataButton,
QPushButton#EditorCloseAction {
    background:#0e1820;
    border:1px solid #344b59;
    color:#dce7ed;
    border-radius:8px;
    min-height:38px;
    padding:7px 12px;
    font-weight:720;
}
QPushButton#EditorSecondaryAction:hover,
QPushButton#OnlineLockButton:hover,
QPushButton#EditorCancelAction:hover,
QPushButton#SaveMetadataButton:hover,
QPushButton#EditorCloseAction:hover {
    background:#14232c;
    border-color:#547182;
    color:#ffffff;
}
QPushButton#OnlineLockButton[lockedOnline="true"] {
    background:#0d2942;
    border-color:#3a83b8;
    color:#dff3ff;
}
QPushButton#CurrentStatusButton {
    background:#3b2a0d;
    border:1px solid #d19120;
    color:#ffd271;
    border-radius:8px;
    min-height:38px;
    padding:7px 13px;
    font-weight:850;
}
QPushButton#CurrentStatusButton[currentStatusKind="ready"] {
    background:#0e3823;
    border-color:#28b86e;
    color:#93edb4;
}
QPushButton#CurrentStatusButton[currentStatusKind="reviewCritical"] {
    background:#4a1d18;
    border-color:#db5c51;
    color:#ffaaa2;
}
QPushButton#ApproveButton {
    background:#0d5c37;
    border:1px solid #18d47b;
    color:#ffffff;
    border-radius:8px;
    min-height:38px;
    padding:7px 15px;
    font-weight:880;
}
QPushButton#ApproveButton:hover {
    background:#0f7543;
    border-color:#35e894;
}
'''
DARK_STYLE = APP_STYLE


APP_STYLE += r'''
QFrame#ToolbarFrame QPushButton#Primary[operationActive="true"] {
    background:#137448; border-color:#43e59a; color:#ffffff;
}
QFrame#ToolbarFrame QPushButton#IdentifyOnlineAction[operationActive="true"] {
    background:#0d2a21; border-color:#32e3a1; color:#ffffff;
}
QFrame#ToolbarFrame QPushButton#ReviewAction[operationActive="true"] {
    background:#0e2e24; border-color:#35e3a0; color:#ffffff;
}
QFrame#ToolbarFrame QPushButton#ExportAction[operationActive="true"] {
    background:#0d3042; border-color:#58cfff; color:#ffffff;
}
QFrame#ToolbarFrame QPushButton#AddFilesAction[operationActive="true"] {
    background:#0d2946; border-color:#6db7f1; color:#ffffff;
}
'''
DARK_STYLE = APP_STYLE


APP_STYLE += r'''
QWidget#CoverProposalsHost {
    background:#0a1720;
    border:1px solid #1f6b8c;
    border-radius:7px;
}
QLabel#CoverProposalsHeading {
    color:#eaf6fc;
    background:#0c2840;
    border:1px solid #2378a0;
    border-radius:6px;
    padding:5px 9px;
    font-size:8pt;
    font-weight:820;
}
QFrame#CoverProposalCard {
    min-width:64px;
    max-width:64px;
    min-height:64px;
    max-height:64px;
}
'''
DARK_STYLE = APP_STYLE


APP_STYLE += r'''
/* Final v0.4.20 visual corrections confirmed by rendered screenshot. */
QFrame#PrimaryMetadataCard,
QFrame#MetadataStatusCompact,
QFrame#RecognitionInfoCompact,
QFrame#CoverGallery,
QFrame#FilenamePreviewCard,
QFrame#SourceComparisonCard {
    background:#0b141b;
    border:1px solid #2a4654;
}
QFrame#CoverProposalsHost {
    background:#091923;
    border:1px solid #2b7fa4;
    border-radius:7px;
}
QPushButton#ApproveButton[approveMode="ready"] {
    background:#0d5c37;
    border:1px solid #18d47b;
    color:#ffffff;
}
QPushButton#ApproveButton[approveMode="ready"]:hover {
    background:#0f7543;
    border-color:#35e894;
}
QPushButton#ApproveButton[approveMode="reopen"] {
    background:#332710;
    border:1px solid #b47b22;
    color:#ffd27a;
}
QPushButton#ApproveButton[approveMode="reopen"]:hover {
    background:#443314;
    border-color:#d89b36;
}
'''
DARK_STYLE = APP_STYLE

# Follow-up to v0.4.20: reference-player proportions, without decorative controls.
APP_STYLE += r'''
QFrame#PlayerCard {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #102421,stop:0.5 #111c23,stop:1 #131a20);
    border:1px solid #344d55; border-radius:18px;
}
QLabel#PlayerCover { border:1px solid #365653; border-radius:7px; background:#081713; }
QPushButton#PlayerTitleLink { font-size:10pt; font-weight:700; color:#f0f5f8; }
QLabel#PlayerArtist { font-size:9pt; font-weight:400; color:#a8bdca; }
QLabel#PlayerMeta { font-size:8pt; color:#718c9b; }
QPushButton#PlayerIconButton {
    background:transparent; border:1px solid transparent; border-radius:22px; padding:0;
}
QPushButton#PlayerIconButton:hover { background:#20352f; border-color:#386957; }
QPushButton#PlayerIconButton:checked { background:#16342c; border-color:#32d5a1; }
QPushButton#PlayButton {
    background:#103a2f; border:2px solid #32e3ae; border-radius:29px; padding:0;
}
QPushButton#PlayButton:hover { background:#185443; border-color:#78ffd7; }
QLabel#CompactTrackTitle { color:#edf7fa; font-size:9pt; font-weight:700; }
QLabel#CompactTrackArtist { color:#a8bdca; font-size:8pt; font-weight:400; }
'''
DARK_STYLE = APP_STYLE

# Keep round-2 editor selectors last: this file intentionally layers visual
# revisions and the final block is the authoritative metadata-editor skin.
APP_STYLE += r'''
QFrame#PreOnlineSnapshotCard {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #091722,stop:1 #0b141c);
    border:1px solid #254758; border-left:3px solid #28c9e8; border-radius:8px;
}
QLabel#TrackHeaderIcon { background:transparent; }
QLabel#TrackHeaderTitle { color:#edf4f7; font-size:9.2pt; font-weight:780; padding:0 2px; }
QLabel#TrackHeaderSeparator { color:#42606d; font-size:9pt; }
QLabel#TrackHeaderTechnical { color:#c4d5df; font-size:8.3pt; font-weight:760; min-width:43px; }
QLabel#MetadataFieldWarning[statusKind="missing"] {
    background:#edae3e; border:1px solid #ffd06f; border-radius:9px;
    color:#241807; font-size:8.5pt; font-weight:950;
}
QFrame#MetadataStatusCompact, QFrame#RecognitionInfoCompact {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0d1b23,stop:1 #091219);
    border:1px solid #31515f; border-radius:9px;
}
QFrame#MetadataStatusCompact QWidget#EditorSectionHeader,
QFrame#RecognitionInfoCompact QWidget#EditorSectionHeader {
    background:#10212a; border-bottom:1px solid #294854; border-radius:5px; padding:2px 4px;
}
QFrame#MetadataStatusRow { min-height:22px; }
QLabel#RecognitionFieldName { color:#8195a2; font-size:7.9pt; }
QLabel#RecognitionFieldValue { color:#d9e5eb; font-size:8.1pt; font-weight:730; }
QProgressBar#RecognitionConfidenceBar { background:#1b303a; border:1px solid #294650; border-radius:3px; }
QProgressBar#RecognitionConfidenceBar::chunk {
    background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #20c986,stop:1 #55e9b0); border-radius:2px;
}
QLabel#CoverProposalsHeading {
    color:#9fb5c1; background:transparent; border:0; border-radius:0;
    padding:1px 2px; font-size:7.9pt; font-weight:780;
}
QWidget#CoverActions { background:transparent; border-top:1px solid #203b47; }
QPushButton#CoverSmallAction, QPushButton#CoverMoreAction {
    background:#0e1b23; border:1px solid #385260; color:#dce7ed; border-radius:7px;
    min-height:27px; padding:5px 10px; font-size:8pt; font-weight:720;
}
QPushButton#CoverSmallAction:hover, QPushButton#CoverMoreAction:hover {
    background:#142832; border-color:#4d8298; color:#ffffff;
}
QPushButton#CoverMoreAction { color:#abd5e7; }
QWidget#UseSourceDataCell { background:transparent; }
QPushButton#UseSourceDataButton {
    background:#111e26; border:1px solid #3a5663; color:#dce7ec; border-radius:5px;
    min-width:100px; max-width:100px; min-height:22px; max-height:22px;
    padding:0 7px; font-size:7.2pt; font-weight:720;
}
QPushButton#UseSourceDataButton:hover { background:#112a20; border-color:#31cf80; color:#a9efc6; }
QPushButton#CurrentStatusButton {
    background:#3a2a0e; border:1px solid #d39a2b; color:#ffd476; border-radius:8px;
    min-height:38px; min-width:168px; padding:7px 15px; font-weight:880;
}
QPushButton#CurrentStatusButton:hover { background:#4a3611; border-color:#f0b849; }
QPushButton#CurrentStatusButton[currentStatusKind="ready"] {
    background:#0d5634; border-color:#1cd37d; color:#f1fff7;
}
QPushButton#CurrentStatusButton[currentStatusKind="ready"]:hover { background:#0f6b40; border-color:#47e99d; }
QPushButton#CurrentStatusButton[statusSeverity="reviewCritical"] {
    background:#482019; border-color:#d76254; color:#ffb2a9;
}
QPushButton#SaveMetadataButton { background:#0d2e26; border-color:#238d66; color:#dcf8eb; font-weight:820; }
QPushButton#SaveMetadataButton:hover { background:#104235; border-color:#32c887; }
'''
DARK_STYLE = APP_STYLE

# Authoritative v0.4.21 editor overrides.
APP_STYLE += r'''
QFrame#StatusRecognitionColumn { background:transparent; border:0; }
QFrame#PrimaryMetadataCard,
QFrame#MetadataStatusCompact,
QFrame#RecognitionInfoCompact,
QFrame#CoverGallery {
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #0d1921,stop:1 #091219);
    border:1px solid #2a4856; border-radius:9px;
}
QFrame#PrimaryMetadataCard { border-color:#295244; }
QLabel#MetadataFieldLabel { color:#b9c7cf; font-size:8.2pt; font-weight:560; }
QFrame#MetadataValueShell { background:transparent; border:0; }
QLabel#MetadataFieldWarning[statusKind="missing"] {
    background:#e6a83b; border:1px solid #ffd06d; border-radius:7px;
    color:#241807; font-size:8pt; font-weight:850; margin-left:2px;
}
QLabel#EditorSectionTitle { color:#e5edf2; font-size:9pt; font-weight:720; }
QLabel#TrackHeaderTitle { font-weight:680; }
QLabel#TrackHeaderTechnical { font-weight:650; }
QLabel#RecognitionFieldName { color:#8498a4; font-weight:500; }
QLabel#RecognitionFieldValue { color:#d5e2e8; font-weight:630; }
QLabel#MetadataStatusText[statusKind="ok"] { font-weight:650; }
QLabel#MetadataStatusText[statusKind="missing"] { font-weight:700; }
QPushButton#OnlineLockButton {
    background:#0d1a23; border:1px solid #304d5c; color:#bdcad2; border-radius:7px;
    min-height:29px; padding:5px 9px; font-size:8pt; font-weight:600;
}
QPushButton#OnlineLockButton:hover { background:#122630; border-color:#477284; color:#ffffff; }
QPushButton#OnlineLockButton[lockedOnline="true"] { background:#102a3b; border-color:#3684ae; color:#bde9ff; }
QTableWidget#SourceComparisonTable {
    background:#081117; alternate-background-color:#0a151c; border:1px solid #213844;
    border-radius:6px; gridline-color:#162832; selection-background-color:#233e50;
}
QTableWidget#SourceComparisonTable QHeaderView::section {
    background:#101f28; color:#b9cad3; border-right:1px solid #1d323c;
    border-bottom:1px solid #263e49; font-weight:650;
}
QTableWidget#SourceComparisonTable::item { border-bottom:1px solid #14252e; }
QWidget#UseSourceDataCell { background:transparent; }
QPushButton#UseSourceDataButton {
    background:#101d25; border:1px solid #36515e; color:#d9e4e9; border-radius:5px;
    min-width:82px; max-width:82px; min-height:18px; max-height:18px;
    padding:0 5px; font-size:7.1pt; font-weight:600;
}
QPushButton#UseSourceDataButton:hover { background:#10261d; border-color:#2fc879; color:#a9efc5; }
QToolButton#SourceLegendInfoButton {
    background:transparent; border:1px solid #58717d; border-radius:11px; padding:2px;
}
QToolButton#SourceLegendInfoButton:hover { background:#13242d; border-color:#79b9ce; }
QLabel#CoverMainPreview { background:#070d12; border:2px solid #20cf7b; border-radius:8px; }
QWidget#CoverProposalsHost { background:#09161e; border:1px solid #274654; border-radius:7px; }
QFrame#CoverProposalCard { background:#0b141b; border:1px solid #293b45; border-radius:6px; }
QFrame#CoverProposalCard:hover { background:#10202a; border-color:#456473; }
QFrame#CoverProposalCard[selected="true"] { background:#0d2118; border:1px solid #28ce7c; }
QLabel#CoverProposalSelectedBadge {
    background:#1bd17c; border:1px solid #5bf0a5; border-radius:8px;
    color:#062316; font-size:7pt; font-weight:900;
}
QLabel#CoverProposalsHeading {
    color:#99adb8; background:transparent; border:0; padding:1px 2px;
    font-size:7.8pt; font-weight:620;
}
QPushButton#CoverSmallAction, QPushButton#CoverMoreAction { min-height:28px; font-weight:600; }
QPushButton#EditorSecondaryAction {
    background:#0d171e; border:1px solid #334a57; color:#cbd7dd; font-weight:600;
}
QPushButton#CurrentStatusButton { font-weight:750; }
QPushButton#SaveMetadataButton {
    background:#0b3d52; border:1px solid #24a6d1; color:#ebfaff; font-weight:720;
}
QPushButton#SaveMetadataButton:hover { background:#0d526d; border-color:#55ccef; color:#ffffff; }
QPushButton#SingleTrackOnlineButton,
QPushButton#RestoreOnlineButton,
QPushButton#CoverSmallAction,
QPushButton#CoverMoreAction,
QPushButton#RestoreFilenameButton { font-weight:600; }
'''
DARK_STYLE = APP_STYLE

# Targeted v0.4.21 follow-up: compact recognition lock and conditional cover action.
APP_STYLE += r'''
QPushButton#OnlineLockButton {
    min-width:32px; max-width:32px; min-height:32px; max-height:32px;
    padding:0; border-radius:7px;
}
QPushButton#CoverShowMoreAction {
    background:transparent; border:0; color:#75cce2; padding:2px 4px;
    min-height:20px; font-size:7.5pt; font-weight:600;
}
QPushButton#CoverShowMoreAction:hover { color:#b7efff; text-decoration:underline; }
QWidget#SourceNameCell { background:transparent; border:0; }
QLabel#SourceNameDot, QLabel#SourceNameText { background:transparent; border:0; }
'''
DARK_STYLE = APP_STYLE

# Authoritative final selectors for the v0.4.21 convenience pass.
APP_STYLE += r'''
QLabel#EditorHeadingIcon { background:transparent; border:0; }
QLabel#EditorFileCounter { color:#9fb2bd; font-size:8.3pt; font-weight:600; padding:0 5px; }
QPushButton#EditorPreviousFileButton, QPushButton#EditorNextFileButton {
    background:#0d1921; border:1px solid #2d4a58; border-radius:7px; padding:0;
}
QPushButton#EditorPreviousFileButton:hover, QPushButton#EditorNextFileButton:hover {
    background:#12303b; border-color:#4fa8c1;
}
QPushButton#EditorPreviousFileButton:disabled, QPushButton#EditorNextFileButton:disabled {
    background:#0a1117; border-color:#202e35;
}
QLineEdit#TrackHeaderTitle {
    background:transparent; border:0; color:#edf4f7; padding:0 2px;
    font-size:9.2pt; font-weight:680; selection-background-color:#17677a; selection-color:#ffffff;
}
QPushButton#SingleTrackOnlineButton {
    min-height:36px; max-height:36px; padding:0 13px; border-radius:7px;
    background:#0b4b55; border:1px solid #25bed0; color:#edfdff; font-weight:760;
}
QPushButton#SingleTrackOnlineButton:hover { background:#0e6571; border-color:#62deeb; }
QPushButton#RestoreOnlineButton {
    min-height:36px; max-height:36px; padding:0 12px; border-radius:7px;
    background:#0d1921; border:1px solid #344c58; color:#cbd8de; font-weight:600;
}
QPushButton#RestoreOnlineButton:hover { background:#14232c; border-color:#58707d; color:#edf5f8; }
QPushButton#OnlineLockButton {
    min-width:38px; max-width:38px; min-height:36px; max-height:36px;
    padding:0; border-radius:7px;
}
QWidget#SourceMenuOption { background:#0d171e; border:0; }
QWidget#SourceMenuOption:hover { background:#152630; }
QLabel#SourceMenuDot, QLabel#SourceMenuProvider, QLabel#SourceMenuValue, QLabel#SourceMenuSeparator {
    background:transparent; border:0;
}
QLabel#SourceMenuValue, QLabel#SourceMenuSeparator {
    qproperty-displayColor:"#c8d3da"; font-weight:500;
}
QFrame#CoverProposalCard {
    min-width:90px; max-width:90px; min-height:90px; max-height:90px;
}
QDialog#EditorCloseGuardDialog { background:#0b141b; }
QLabel#CloseGuardHeaderIcon { background:transparent; border:0; }
QLabel#CloseGuardTitle { color:#edf5f8; font-size:13pt; font-weight:760; }
QLabel#CloseGuardNote { color:#aab9c2; font-weight:500; }
QFrame#CloseGuardIssues { background:#091219; border:1px solid #29404b; border-radius:8px; }
QFrame#CloseGuardIssue[severity="amber"] { background:#211b0e; border:1px solid #6b5524; border-radius:6px; }
QFrame#CloseGuardIssue[severity="critical"] { background:#251211; border:1px solid #743a35; border-radius:6px; }
QLabel#CloseGuardIssueText[severity="amber"] { color:#f1c76b; font-weight:620; }
QLabel#CloseGuardIssueText[severity="critical"] { color:#ff9289; font-weight:700; }
QPushButton#CloseReturnAction { background:#101a21; border-color:#3a505b; color:#c9d5db; }
QPushButton#CloseDiscardAction { background:#261716; border-color:#7b413c; color:#e8aaa4; }
QPushButton#CloseSaveAction { background:#0b4b55; border-color:#25bed0; color:#edfdff; font-weight:740; }
QPushButton#CloseDespiteWarningsAction { background:#2a210f; border-color:#8b6927; color:#f1cd79; }

/* v0.4.22 — A1 icons, quick locations and provider cards. */
QPushButton#CancelScanAction, QPushButton#CancelOnlineAction,
QFrame#ToolbarFrame QPushButton#CancelScanAction,
QFrame#ToolbarFrame QPushButton#CancelOnlineAction {
    background:#32181c; border:1px solid #e45f68; color:#ffe4e6;
    border-radius:8px; font-weight:760; padding:9px 14px;
}
QPushButton#CancelScanAction:hover, QPushButton#CancelOnlineAction:hover,
QFrame#ToolbarFrame QPushButton#CancelScanAction:hover,
QFrame#ToolbarFrame QPushButton#CancelOnlineAction:hover {
    background:#4a1c22; border-color:#ff7b84; color:#ffffff;
}
QLabel#DashboardSectionTitle { color:#e1edf3; font-size:12.5pt; font-weight:760; }
QFrame#QuickAccessCard {
    background:#0d171e; border:1px solid #29404b; border-radius:10px;
    min-height:104px;
}
QFrame#QuickAccessCard:hover { border-color:#3a6070; background:#101d25; }
QLabel#QuickAccessIcon { background:transparent; border:0; }
QLabel#QuickAccessTitle { background:transparent; border:0; font-weight:740; }
QFrame#QuickAccessAccentLine { border:0; }
QLabel#QuickAccessPath { color:#8fa7b4; font-size:8.5pt; }
QLabel#QuickAccessAvailability { color:#718793; font-size:7.5pt; font-weight:650; }
QLabel#QuickAccessAvailability[available="true"] { color:#66d99a; }
QPushButton#QuickAccessOpen, QPushButton#QuickAccessCopy {
    min-height:28px; padding:3px 9px; background:#111d25;
    border:1px solid #314854; border-radius:6px; color:#c7d5dc; font-weight:560;
}
QPushButton#QuickAccessOpen:hover, QPushButton#QuickAccessCopy:hover {
    background:#162832; border-color:#4d7d8d; color:#f1fbff;
}
QPushButton#QuickAccessOpen:disabled { color:#566771; border-color:#25343c; background:#0c1419; }
QFrame#DashboardStatisticsSeparator { background:transparent; border:0; min-height:42px; }
QFrame#DashboardStatisticsLine { color:#344852; background:#344852; border:0; max-height:1px; }
QLabel#DashboardStatisticsIcon { background:transparent; border:0; }
QLabel#DashboardStatisticsTitle {
    background:transparent; border:0; color:#86cce9; font-size:10.5pt; font-weight:740;
}
QPushButton#OnlineLockButton[lockedOnline="true"] {
    background:#32181c; border:1px solid #e45f68; color:#ffe4e6;
}
QPushButton#OnlineLockButton[lockedOnline="true"]:hover {
    background:#4a1c22; border-color:#ff7b84; color:#ffffff;
}
QLabel#MetadataStatusText[statusKind="warning"] { color:#f5b64f; font-weight:760; }
QLabel#MetadataStatusText[statusKind="critical"] { color:#ff8179; font-weight:780; }
QLabel#MetadataFieldWarning[statusKind="warning"],
QLabel#MetadataFieldWarning[statusKind="critical"] {
    background:transparent; border:0; margin-left:2px;
}
QLabel#CoverSelectedBadge, QLabel#CoverProposalSelectedBadge {
    background:#13b968; border:2px solid #d8ffeb; color:#ffffff;
}
QLabel#CoverSelectedBadge { border-radius:12px; }
QLabel#CoverProposalSelectedBadge { border-radius:10px; }
QLabel#ProviderName { color:#edf5f8; font-size:11pt; font-weight:760; }
QLabel#ProviderStatusBadge {
    border-radius:8px; padding:4px 8px; font-size:7.8pt; font-weight:760;
    background:#19242b; border:1px solid #445660; color:#b9c7ce;
}
QLabel#ProviderStatusBadge[providerState="ready"] {
    background:#10291c; border-color:#32764e; color:#7ce8a3;
}
QLabel#ProviderStatusBadge[providerState="missing"] {
    background:#2a210f; border-color:#8b6927; color:#f1cd79;
}
QLabel#ProviderStatusBadge[providerState="no-key"] {
    background:#102431; border-color:#2d667d; color:#7adbf5;
}
QFrame#SettingsSection {
    background:#0d151b; border:1px solid #293943; border-radius:12px;
}
QLabel#SettingsSectionTitle { font-size:13.5pt; font-weight:780; background:transparent; border:0; }
QLabel#SettingsSectionDescription { color:#8296a2; font-size:9.2pt; background:transparent; border:0; }
QLabel#LibraryAvailabilityStatus { background:transparent; border:0; }
QLabel#LibraryLocationPath {
    color:#d8e6ec; background:#0b1217; border:1px solid #293a44;
    border-radius:7px; padding:9px 11px; font-family:Consolas;
}
QFrame#OnlineRecognitionCard, QFrame#SafeDefaultsCard {
    background:#101920; border:1px solid #2d3f4a; border-radius:10px;
}
QPushButton#ChangeLibraryLocationAction, QPushButton#RestoreDefaultsAction {
    background:#14232b; border:1px solid #3b5966; color:#d4e4eb; font-weight:650;
}
QPushButton#ChangeLibraryLocationAction:hover, QPushButton#RestoreDefaultsAction:hover {
    background:#1a3039; border-color:#598292; color:#ffffff;
}
QDialog#RestoreDefaultsDialog { background:#0d141a; }
QLabel#SettingsDialogTitle { color:#edf7fa; font-size:13pt; font-weight:760; }
QLabel#SafeResetNotice {
    color:#8ee5ad; background:#10251a; border:1px solid #2f6845;
    border-radius:8px; padding:9px 11px; font-weight:620;
}
'''
DARK_STYLE = APP_STYLE

# Light-theme counterparts for controls introduced in the final editor pass.
LIGHT_STYLE += r'''
QLabel#EditorFileCounter { color:#526975; font-size:8.3pt; font-weight:600; padding:0 5px; }
QPushButton#EditorPreviousFileButton, QPushButton#EditorNextFileButton {
    background:#f5f9fb; border:1px solid #aec4cf; border-radius:7px; padding:0;
}
QPushButton#EditorPreviousFileButton:hover, QPushButton#EditorNextFileButton:hover {
    background:#e6f3f7; border-color:#4c9eb5;
}
QPushButton#EditorPreviousFileButton:disabled, QPushButton#EditorNextFileButton:disabled {
    background:#eef2f4; border-color:#d6e0e5;
}
QLineEdit#TrackHeaderTitle {
    background:transparent; border:0; color:#17303c; padding:0 2px;
    font-size:9.2pt; font-weight:680; selection-background-color:#58bed0; selection-color:#07161b;
}
QPushButton#SingleTrackOnlineButton {
    min-height:36px; max-height:36px; padding:0 13px; border-radius:7px;
    background:#0d7180; border:1px solid #0795a8; color:#ffffff; font-weight:760;
}
QPushButton#SingleTrackOnlineButton:hover { background:#0b8292; border-color:#18adbf; }
QPushButton#RestoreOnlineButton {
    min-height:36px; max-height:36px; padding:0 12px; border-radius:7px;
    background:#f5f8fa; border:1px solid #b9c9d1; color:#29414d; font-weight:600;
}
QPushButton#OnlineLockButton {
    min-width:38px; max-width:38px; min-height:36px; max-height:36px;
    padding:0; border-radius:7px; background:#f5f8fa; border:1px solid #b9c9d1;
}
QWidget#SourceMenuOption { background:#ffffff; border:0; }
QWidget#SourceMenuOption:hover { background:#e8f3f7; }
QLabel#SourceMenuDot, QLabel#SourceMenuProvider, QLabel#SourceMenuValue, QLabel#SourceMenuSeparator {
    background:transparent; border:0;
}
QLabel#SourceMenuValue, QLabel#SourceMenuSeparator {
    qproperty-displayColor:"#304b58"; font-weight:500;
}
QFrame#CoverProposalCard {
    min-width:90px; max-width:90px; min-height:90px; max-height:90px;
}
QDialog#EditorCloseGuardDialog { background:#f4f8fa; }
QLabel#CloseGuardTitle { color:#17303c; font-size:13pt; font-weight:760; }
QLabel#CloseGuardNote { color:#506672; font-weight:500; }
QFrame#CloseGuardIssues { background:#ffffff; border:1px solid #bfd0d8; border-radius:8px; }
QFrame#CloseGuardIssue[severity="amber"] { background:#fff8e9; border:1px solid #d5a844; border-radius:6px; }
QFrame#CloseGuardIssue[severity="critical"] { background:#fff0ee; border:1px solid #d56b62; border-radius:6px; }
QLabel#CloseGuardIssueText[severity="amber"] { color:#805d12; font-weight:620; }
QLabel#CloseGuardIssueText[severity="critical"] { color:#a13b34; font-weight:700; }
QPushButton#CloseReturnAction { background:#f5f8fa; border-color:#b5c7d0; color:#29414d; }
QPushButton#CloseDiscardAction { background:#fff2f0; border-color:#cc746d; color:#963f38; }
QPushButton#CloseSaveAction { background:#0d7180; border-color:#0795a8; color:#ffffff; font-weight:740; }
QPushButton#CloseDespiteWarningsAction { background:#fff7e7; border-color:#c99c3d; color:#76550e; }
'''

# v0.4.22 repair parity — light
LIGHT_STYLE += r'''
/* v0.4.22 repair parity — light */
QPushButton#CancelScanAction, QPushButton#CancelOnlineAction,
QFrame#ToolbarFrame QPushButton#CancelScanAction,
QFrame#ToolbarFrame QPushButton#CancelOnlineAction {
    background:#fff0f1; border:1px solid #c93f49; color:#9d202a;
    border-radius:8px; font-weight:760; padding:9px 14px;
}
QPushButton#CancelScanAction:hover, QPushButton#CancelOnlineAction:hover,
QFrame#ToolbarFrame QPushButton#CancelScanAction:hover,
QFrame#ToolbarFrame QPushButton#CancelOnlineAction:hover {
    background:#ffdfe2; border-color:#a92832; color:#76131b;
}
QPushButton#OnlineLockButton[lockedOnline="true"] {
    background:#fff0f1; border:1px solid #c93f49; color:#9d202a;
}
QPushButton#OnlineLockButton[lockedOnline="true"]:hover {
    background:#ffdfe2; border-color:#a92832; color:#76131b;
}
QFrame#QuickAccessCard {
    background:#ffffff; border:1px solid #bdced6; border-radius:10px; min-height:104px;
}
QFrame#QuickAccessCard:hover { background:#f2f8fa; border-color:#83aebd; }
QFrame#QuickAccessAccentLine, QLabel#QuickAccessIcon, QLabel#QuickAccessTitle {
    background:transparent; border:0;
}
QLabel#QuickAccessPath { color:#526975; font-size:8.5pt; }
QLabel#QuickAccessAvailability { color:#71828b; font-size:7.5pt; font-weight:650; }
QLabel#QuickAccessAvailability[available="true"] { color:#288757; }
QPushButton#QuickAccessOpen, QPushButton#QuickAccessCopy {
    min-height:28px; padding:3px 9px; background:#f5f8fa;
    border:1px solid #b9c9d1; border-radius:6px; color:#29414d; font-weight:560;
}
QPushButton#QuickAccessOpen:hover, QPushButton#QuickAccessCopy:hover {
    background:#e6f3f7; border-color:#6b9dad; color:#17303c;
}
QFrame#DashboardStatisticsSeparator { background:transparent; border:0; min-height:42px; }
QFrame#DashboardStatisticsLine { color:#aebfc7; background:#aebfc7; border:0; max-height:1px; }
QLabel#DashboardStatisticsIcon { background:transparent; border:0; }
QLabel#DashboardStatisticsTitle {
    background:transparent; border:0; color:#267da0; font-size:10.5pt; font-weight:740;
}
QLabel#MetadataStatusText[statusKind="warning"] { color:#8a5e08; font-weight:760; }
QLabel#MetadataStatusText[statusKind="critical"] { color:#b8323b; font-weight:780; }
QLabel#MetadataFieldWarning[statusKind="warning"],
QLabel#MetadataFieldWarning[statusKind="critical"] {
    background:transparent; border:0; margin-left:2px;
}
QLabel#CoverSelectedBadge, QLabel#CoverProposalSelectedBadge {
    background:#11a85e; border:2px solid #effff6; color:#ffffff;
}
QLabel#CoverSelectedBadge { border-radius:12px; }
QLabel#CoverProposalSelectedBadge { border-radius:10px; }
QFrame#SettingsSection {
    background:#f7fafb; border:1px solid #bdced6; border-radius:12px;
}
QLabel#SettingsSectionTitle { font-size:13.5pt; font-weight:780; background:transparent; border:0; }
QLabel#SettingsSectionDescription { color:#607681; font-size:9.2pt; background:transparent; border:0; }
QLabel#LibraryAvailabilityStatus { background:transparent; border:0; }
QLabel#LibraryLocationPath {
    color:#29414d; background:#ffffff; border:1px solid #bdced6;
    border-radius:7px; padding:9px 11px; font-family:Consolas;
}
QFrame#OnlineRecognitionCard, QFrame#SafeDefaultsCard {
    background:#ffffff; border:1px solid #c3d2d9; border-radius:10px;
}
QPushButton#ChangeLibraryLocationAction, QPushButton#RestoreDefaultsAction {
    background:#f5f8fa; border:1px solid #b5c7d0; color:#29414d; font-weight:650;
}
QPushButton#ChangeLibraryLocationAction:hover, QPushButton#RestoreDefaultsAction:hover {
    background:#e6f3f7; border-color:#6b9dad; color:#17303c;
}
QDialog#RestoreDefaultsDialog { background:#f4f8fa; }
QLabel#SettingsDialogTitle { color:#17303c; font-size:13pt; font-weight:760; }
QLabel#SafeResetNotice {
    color:#246f45; background:#edf9f1; border:1px solid #7ab691;
    border-radius:8px; padding:9px 11px; font-weight:620;
}
'''
