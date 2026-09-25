"""English help copy, keyed by the stable Polish topic IDs used by the UI."""

HELP_TOPICS_EN = {
    'Pierwsze uruchomienie': ('First launch', '''
<h2>Get started safely</h2>
<p>Add one or more source folders, choose a location for the new library and enter its name. ALO creates the <b>GOTOWE</b>, <b>NIE_WYBRANE</b>, <b>DO_SPRAWDZENIA</b> and <b>raporty</b> folders automatically. These are actual folder names on disk.</p>
<p>Your source folders do not need to be organized first. They can contain subfolders, mixed filenames and incomplete metadata.</p>'''),
    'Bezpieczeństwo plików': ('File safety', '''
<h2>Your originals stay untouched</h2>
<p>ALO reads source files without renaming, overwriting tags or deleting them. It changes names, tags and cover art only on copies in the new library.</p>
<ul><li>No automatic deletion</li><li>No audio transcoding</li><li>No overwriting files with conflicting names</li><li>Batch copying requires confirmation</li></ul>'''),
    'Duplikaty': ('Duplicates', '''
<h2>Compare the files and decide</h2>
<p>ALO groups files that might contain the same recording. Compare filename, duration, BPM, format, bitrate, sample rate and file size. Differences are highlighted; ALO does not pick a winner.</p>
<h3>Resolve a group</h3>
<ol><li>Click a row to select a version; double-click to play it.</li><li>Choose <b>KEEP</b> or <b>NOT SELECTED</b> for each file.</li><li>Use <b>EDIT</b> to correct metadata without leaving Duplicates.</li><li>The Decision cell is green for KEEP, gray for NOT SELECTED and dark if you have not decided.</li></ol>
<h3>Version families</h3>
<p>Radio Edit, Extended Mix, Original Mix, Club Mix and remixes can all be separate valid versions. ALO groups clearly named versions into a version family and does not automatically treat genuinely different versions as duplicates.</p>
<p><b>Remember:</b> the data helps you compare. You decide which files to keep.</p>'''),
    'Jak program podejmuje decyzje': ('How ALO evaluates matches', '''
<h2>More than the first online result</h2>
<p>ALO scores each candidate using the AcoustID fingerprint, artist, title, remix or version, duration, existing album and year, and agreement between MusicBrainz and a specific Discogs release.</p>
<p>The details panel shows confidence and reasons, such as <i>AcoustID 98% · exact title/version · matching duration · matching album</i>. Tracks with low confidence go to <b>NEEDS REVIEW</b>.</p>'''),
    'Rozpoznawanie utworów': ('Track identification', '''
<h2>Data sources</h2>
<p><b>MusicBrainz</b> and the <b>Apple/iTunes</b> catalog work without API keys. MusicBrainz helps confirm a recording; Apple/iTunes provides extra catalog data and cover art suggestions. <b>AcoustID/Chromaprint</b> can identify audio even when the file is called <code>34.mp3</code> (an optional key is required). <b>Discogs</b> can help identify a specific release, remix, genre or year (an optional token is required).</p>
<p>ALO compares sources and considers the exact version, duration and existing track data when evaluating a match.</p>'''),
    'Konfiguracja AcoustID i Discogs': ('Set up AcoustID and Discogs', '''
<h2>Keys for online identification</h2>
<p>Open <b>Settings → Integrations and API keys</b>. MusicBrainz and Apple/iTunes work without keys; AcoustID and Discogs are optional.</p>
<div class="help-card"><h3>1. AcoustID — Application API Key</h3><p>Identifies a recording by audio fingerprint, even with a filename such as <code>34.mp3</code>.</p><ol><li>Open <a href="https://acoustid.org/new-application">acoustid.org/new-application</a> and sign in.</li><li>Register an application, e.g. <b>Audio Library Organizer</b>.</li><li>Copy its <b>Application API Key / client key</b>.</li><li>Paste it into <b>AcoustID client key</b> in ALO Music.</li></ol></div>
<div class="help-card"><h3>2. Discogs — Personal Access Token</h3><p>Helps with release, remix, year and genre details.</p><ol><li>Sign in to Discogs.</li><li>Open <a href="https://www.discogs.com/settings/developers">Settings → Developers</a>.</li><li>Generate and copy a <b>Personal Access Token</b>.</li><li>Paste it into <b>Discogs token</b> in ALO Music.</li></ol></div>
<div class="help-card"><h3>3. MusicBrainz — no API key</h3><p>MusicBrainz does not require a separate key for ordinary lookup.</p></div>
<div class="help-card"><h3>4. Apple/iTunes — no API key</h3><p>ALO uses Apple's public search catalog for additional track, album, year, genre and cover art information. You do not need to sign in to Apple Music.</p></div>
<div class="ok">Save AcoustID and Discogs keys only if you want to use those sources. Keys stay in your local settings and are never included in CSV reports.</div>
<div class="important">Do not share your keys. AcoustID needs an <b>Application API Key</b>; Discogs needs a <b>Personal Access Token</b>.</div>
<p style="color:#9eabbc">This application uses Discogs’ API but is not affiliated with, sponsored or endorsed by Discogs. “Discogs” is a trademark of Zink Media, LLC.</p>'''),
    'BPM': ('BPM', '''
<h2>Tempo analysis runs locally</h2>
<p>ALO preserves an existing BPM tag. If no tag exists but the filename contains <b>[139bpm]</b>, that value takes priority over audio analysis. Otherwise, ALO calculates the tempo from the audio locally.</p>
<p>Analysis accounts for the half-time and double-time readings common in dance music. An uncertain result should not replace a value you have verified.</p>'''),
    'Okładki': ('Cover art', '''
<h2>Automatic cover art</h2>
<p>If the release match is sufficiently confident, ALO retrieves cover art automatically. For embedding, it prefers Cover Art Archive artwork associated with MusicBrainz. Without a reliable match, ALO does not add a random cover.</p>
<p>The editor shows a large preview and a gallery of available suggestions. You can add an image of your own or use the shared <b>NO COVER</b> placeholder. ALO saves your selection in the output file.</p>'''),
    'Statusy i zatwierdzanie': ('Statuses and approval', '''
<h2>Four simple statuses</h2>
<p><b>READY</b> means the main metadata is complete. <b>DUPLICATE</b> marks a possible duplicate. <b>NEEDS REVIEW</b> means the track needs attention. <b>NOT SELECTED</b> means you chose to set it aside.</p>
<p>You do not need to approve thousands of tracks one at a time. The editor's File Status panel shows which fields are complete. READY requires artist, title/version, year, genre and BPM. Album, Discogs URL and comment are optional.</p>'''),
    'Odtwarzacz': ('Player', '''
<h2>Listen without leaving ALO</h2>
<p>The built-in player has play/pause, seeking, volume and ±10-second skips. In Library, one click selects a track and a double-click plays it. Changing the selection does not interrupt playback.</p>
<p>In Duplicates, choose <b>KEEP</b>, <b>NOT SELECTED</b> or <b>EDIT</b>. If a file turns out to be a separate mix or remix, correct its metadata and keep it. DUPLICATE is an automatic technical status, not a separate button.</p>'''),
    'Format nazwy pliku': ('Filename format', '''
<h2>Filename format</h2><p>In Settings, choose which fields appear in output filenames. The default template is:</p>
<p><code>{Artist} - {Title} ({Version}) ({Year}) [{BPM}bpm]</code></p>
<h3>Available fields</h3><ul><li><code>{Artist}</code> — artist</li><li><code>{Title}</code> — title without version</li><li><code>{Version}</code> — remix, edit or mix</li><li><code>{Year}</code> — year</li><li><code>{BPM}</code> — tempo</li><li><code>{Genre}</code> — genre</li><li><code>{Album}</code> — album or release</li></ul>
<p>A preview appears below the template. ALO removes empty brackets or parentheses when optional fields are missing.</p>
<h3>One-track exception</h3><p>You can enter a custom filename for the current track in the metadata editor without changing the template for the rest of the library.</p>'''),
    'DO SPRAWDZENIA i cofanie zmian': ('Review and undo', '''
<h2>One review queue</h2><p>ALO uses <b>NEEDS REVIEW</b> when essential data is missing, confidence is low, data conflicts or a file has an issue. Ordinary cases are amber; serious ones are red. The status name stays the same.</p>
<p>A manually approved READY track with complete metadata does not automatically return to review because of an old warning. The editor shows the current status and a separate panel with the data from before online identification, which you can restore.</p>'''),
    'Ręczne poprawki i blokady': ('Manual edits and locks', '''
<h2>Your edits take priority</h2><p>Manually corrected fields such as artist, title, year and genre take priority over later online identification. Discogs or MusicBrainz cannot silently overwrite a protected field.</p>
<p>Field locks are saved in the library and protect your corrections after restarting ALO.</p>
<p>To keep a whole track as it is, use <b>Lock online</b> in the editor. AcoustID, MusicBrainz, Apple/iTunes and Discogs skip that track, but you can still edit or unlock it at any time.</p>'''),
    'Ponowne skanowanie': ('Rescanning', '''
<h2>Persistent libraries and quick refreshes</h2><p>Each library has its own database and output folder. ALO remembers scanned source folders and their history, but does not rescan them automatically after a restart. A scan starts only when you request it.</p>
<p>A full refresh skips unchanged files and analyzes only new or modified ones. To add another batch of music, use <b>Add tracks to library</b>; existing library files are not reanalyzed.</p>
<p>Missing files appear on Start and are hidden in the normal Library view. A full refresh cleans up obsolete records.</p>'''),
    'Rozwiązywanie problemów': ('Troubleshooting', '''
<h2>Common situations</h2><p><b>34.mp3 was not identified:</b> check the AcoustID client key and your internet connection. Not every track exists in the fingerprint database.</p>
<p><b>No exact release:</b> ALO may recognize a track without enough evidence for a particular Discogs release. It leaves the track for review instead of guessing.</p>
<p><b>No cover art:</b> ALO keeps the source artwork if available. Otherwise it embeds the shared NO COVER placeholder in the output file.</p>
<p><b>Scan interrupted:</b> start it again. The saved library remains on disk and unchanged files do not need another analysis.</p>'''),
    'Kopiowanie i weryfikacja': ('Copying and verification', '''
<h2>How are copies checked?</h2><p>On export, ALO first copies the original bytes and compares the copy with the source using <b>SHA-256 and file size</b>. It writes new tags and cover art only after that check.</p>
<p>ALO then checks that the final file exists and has a nonzero size. This is technical copy verification, not manual metadata review. Before creating files, ALO reminds you to <b>Review in Library</b>. Afterward, you can see the results, open Library or its folder, and read the <code>weryfikacja_kopii_....csv</code> report.</p>
<p>A file that fails verification is not counted as verified.</p>'''),
    'O programie': ('About ALO Music', '''
<h2>ALO Music — Audio Library Organizer</h2><p>Version <b>0.4.23</b> · 2026. A local Windows music organizer with safe copying, track identification, metadata editing, duplicate comparison, version families, cover art and BPM analysis.</p>
<p>Each persistent library separates its output folder from the source folders used for scanning. Scan history is for reference; ALO does not automatically reopen an old source because it was scanned before.</p>'''),
}
