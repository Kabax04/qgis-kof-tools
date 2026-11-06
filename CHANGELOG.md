# Changelog

Entries before 1.0.0 are in Norwegian.

## [1.5.0] – 2026-11-06

### Changed
- Repeated measurements are only merged into a mean point when their heights differ by at most the height tolerance, which now defaults to 10 cm. Before, there was no height limit by default, so the lid and bottom of a manhole, or the top and foot of a kerb, became one mean point with a height nobody measured. Leave the height tolerance empty for the old behaviour.
- Grouping of repeated measurements uses a grid instead of comparing points along east only. A long north–south survey with 100 000 points takes seconds instead of minutes, the grouping runs once per import instead of three times, and it can be cancelled.
- Many lines with the same unknown record type (e.g. `03` observations) give one warning with the count and the first line, instead of one warning per line.

### Added
- The import log shows the file header (`01`: job, date, municipality, observer) and the `00` comments, which do not end up in any layer.
- The tests that need QGIS now run in CI, in QGIS's Docker images for 3.22, the current LTR and the latest release.

### Fixed
- Files from old DOS programs in CP865 or CP850 are read with the right æ, ø and å. Before, they were read as Windows-1252 and the letters became other characters. A file is taken as DOS only when its only non-ASCII bytes are Norwegian letters in those code pages. UTF-16 files with a byte order mark are read too.
- Exporting a curved line or polygon warns that it is written as straight lines through points along the curve. Arcs from the import are still written back as `09 93`.
- Exporting from QGIS 3.22 no longer gives a warning about characters Windows-1252 cannot store, with a `?` in the first line of the file. The release name in the version (`3.22.16-Białowieża`) is left out of the comment.
- The export progress no longer goes negative for layers whose feature count is unknown.
- The objects that style the imported layers are released once used, instead of being kept for the rest of the session.
- Exporting a point with an empty (NULL) height field uses Z from the geometry, and a point with an empty name is numbered. Before, such points were written without height or name. Numbered points skip numbers the layer already uses as point names.
- `!` in a point name or code is replaced with `_` on export, with a warning. Before, the point was lost when the file was imported again, since `!` starts a comment in KOF.
- A warning is shown when the old KOF Import plugin is still installed. The two plugins use the same Processing provider id, so only one of them can provide the algorithms.
- A file with only GNSS vectors in western Norway (zone 32V) or on Svalbard is shown in the UTM zone used there, e.g. 32 for Bergen and 33 for Ny-Ålesund.
- The GNSS vector transformation uses the processing context instead of the current project, so it works from `qgis_process` and in background threads.
- The tests no longer stop when `git` is missing, as in QGIS's own Python; the release tests are skipped instead.

## [1.4.1] – 2026-11-06

### Fixed
- A `05` record that does not follow the KOF columns (tabs, shifted fields) is no longer misread. Before, a point with a numeric code and no height, such as `100 2000 6615798.981 599667.952`, got the code as north and the north as height. The words are now read so that numbers before north must be a whole-number code, a height must be below 10 000 and a calculation code may follow the height; text after the numbers becomes the remark. A line that fits more than one reading is skipped with a warning instead of guessed, and one warning tells how many points were read this way.
- Files where the record type is not in column 2–3 (no blank first column, or more indentation) are read in the right columns. Before, point names and codes were cut short, e.g. `100` became `00`.
- Arcs (`09 93`) from the import are exported back as `09 93` with their measured points and names. Before, every vertex of the drawn arc became a numbered `05` record, so a three-point arc came out as almost 200 points.

### Changed
- Imported arcs are drawn with 16 straight pieces between each pair of measured points, so the export can find the measured points again.

## [1.4.0] – 2026-11-06

### Added
- Import of GNSS vectors (baselines) exported from post-processing software such as Topcon MAGNET Tools: `42` start station with geocentric X Y Z, `43` vector dX dY dZ, `44` standard deviations and correlations, and `46` date and time. They give a line layer from the start station to start + vector, with the fields `name`, `from`, `to`, `dX`, `dY`, `dZ`, `length`, `sX`, `sY`, `sZ`, `rXY`, `rXZ`, `rYZ`, `date`, `time`, `info`, `line_no` and `source_file`.
- The `42` coordinates are read as EUREF89 and converted to latitude, longitude and ellipsoidal height before they are projected. They are usually only approximate, so the vectors are placed to within a few metres, while the vector components and length are exact.
- A file with only vectors and no coordinate reference system is shown in the UTM zone of the first station, and dropping it on the map imports it without opening the dialog. The empty point and mean layers are not added.

### Fixed
- An unreadable `05` record with tabs no longer stops the import with an error. It is reported as a warning like other unreadable points.

## [1.3.1] – 2026-10-31

### Fixed
- Dropping a .kof file on the map only opens the import dialog when no coordinate reference system is found in the file. Other errors, such as a file that cannot be read, are shown in the message bar instead of opening the dialog.
- Exporting a layer that has no coordinate reference system, with a coordinate reference system selected for the file, now warns that the coordinates are written unchanged and labelled with the selected system. Before, the log said it was transforming from an unknown system.

## [1.3.0] – 2026-10-30

### Added
- Export of line and polygon layers to KOF. Lines are written as `09 91` … `09 99` and polygons as `09 91` … `09 96`, with one `05` record per vertex. The vertices take their names from the `points` field of layers made by the import when it has one name per vertex; otherwise they are numbered. Heights come from Z, and the code field applies to every vertex.
- Curves are segmented, multipart features give one block per part, and polygon holes are written as polygons of their own, with a warning.
- Lines with fewer than 2 points and polygons with fewer than 3 are left out, with a warning.

### Changed
- The export algorithm and **Export to KOF…** accept point, line and polygon layers, and the menu item starts with the active layer whatever its geometry.

## [1.2.0] – 2026-10-30

### Added
- Export to KOF: **Vector → KOF Tools → Export to KOF…** and the Processing algorithm `kof:exportkof` write a point layer to a KOF file. The file gets a `01` header with the SOSI coordinate system code and north before east, the EPSG code as a `00` comment, and one `05` record per point with name, code, north, east, height, calculation code and remark.
- The fields default to those of layers made by the import (`name`, `code`, `H`, `calc_code`, `remark`). Without a name field the points are numbered, and without a height field the Z value is used.
- The points can be transformed to another coordinate reference system. Geographic systems are refused, since KOF holds projected coordinates.
- Windows-1252 (default) or UTF-8, with CRLF line endings.
- Names, codes and heights that do not fit the KOF columns are shortened, and points with coordinates that do not fit are skipped, with warnings in the log.

### Changed
- The plugin is renamed from KOF Import to KOF Tools, to make room for export to KOF. The plugin folder and id are now `kof_tools`, the release zip is `kof_tools.x.y.z.zip` and the repository is `Kabax04/qgis-kof-tools`. The Processing ids (`kof`, `kof:importkof`) are unchanged, so saved models and scripts keep working. If you installed KOF Import, uninstall it after installing KOF Tools.

## [1.1.0] – 2026-10-29

### Changed
- The plugin is offered in QGIS 4 (`qgisMaximumVersion=4.99`) and still supports QGIS 3.22 and later.
- Geometry types, Processing enums and message levels use the scoped names that QGIS 4 (Qt6) requires, with a fallback for older QGIS 3 versions.

## [1.0.1] – 2026-10-29

### Fixed
- The axis order check only swaps north and east when the swapped coordinates fit Norway (Svalbard included) in UTM or NTM, and the original ones do not. Local coordinates labelled as UTM are no longer swapped.

## [1.0.0] – 2026-10-29

First stable release.

### Changed
- English user interface with Norwegian translation (bokmål and nynorsk), following the QGIS language setting.
- Field names are now English: `name`, `code`, `calc_code`, `remark`, `line_no`, `source_file`; in the mean layer `group`, `names`, `count`, `max_dev`; in the line layers `count`, `points`, and `type` values `line`, `arc`, `spline`, `polygon`. Layer names use English suffixes (`mean`, `lines`, `polygons`).
- Author and contact in the metadata.

### Added
- Coordinate system codes from the `01` block cover all SOSI codes from NGI kof-parser, including EUREF89 NTM zones 5–30 (codes 205–230), EUREF89 UTM 29–30 and WGS84 UTM.
- CRS recognised from ArcGIS export text (`ETRS_1989_UTM_Zone_32N`, `ETRS_1989_NTM_Zone_10`) and from `SRID`/`EPSG` comments.
- The axis order is checked: if most points have east larger than north in a UTM or NTM system, north and east are swapped with a warning.
- Real test files from NGI kof-parser (MIT) in `tests/data/ngi/`.

### Fixed
- Points with an empty north or east field are reported as missing coordinates instead of being misread from the remaining numbers.

## [0.4.0] – 2026-10-29

### Lagt til
- Linjer og flater fra `09`-blokker etter KOF-spesifikasjonen 2.00: `91` rett linje, `92` spline (tegnes rett), `93` sirkelbue, `94` punktsverm, `72`–`79` og `82`–`89` flere samtidige linjer (sag- og bølgemetoden), `96` lukk polygon og `99` slutt.
- Nye utdatalag «Linjer» (LineStringZ) og «Flater» (PolygonZ) med feltene `navn`, `type`, `kode`, `antall`, `punkter`, `pi`, `linjenr` og `kildefil`. Lagene lages bare når filen har linjer eller flater.
- En ny linjestart avslutter forrige linje. Punkter med beregningskode 37 regnes som enkeltpunkter og tas ikke med i linjen.
- Advarsler for linjer som ikke avsluttes, polygoner med for få punkter, spline og radius (`08 141`, støttes ikke ennå).

### Endret
- `09`-blokker uten programkode (f.eks. `09 Laget av versjon 5.5.1`) tolkes som kommentarer.
- `08`-blokker gir ikke lenger advarsel om ukjent postkode.

## [0.3.1] – 2026-10-29

Rettelser etter gjennomgang av KOF-spesifikasjonen 2.00 (Norkart, 2005).

### Rettet
- Linjer som er satt ut av funksjon med `-` i kolonne 1, hoppes nå over i stedet for å gi advarsel.
- `05`-poster med beregningskode og/eller merknad etter høyden leses nå. Punktlaget har nye felt `bk` og `merknad`.
- Tekst etter `!` på slutten av en linje tolkes som kommentar og legges i `merknad` (gjelder ikke `00`-poster).
- Meldingen ved dra og slipp sier «1 advarsel», ikke «1 advarsler».

### Lagt til
- `01`-hodet i versjon 2-format tolkes: oppdrag, dato, koordinatsystemkode, kommunenr, enheter og observatør.
- Koordinatsystemkoden i `01` brukes til å finne EPSG (NGO1948 akse I–VIII, EUREF89 UTM 31–36, ED50 UTM 31–36), og går foran teksten i `00`-kommentarer.
- Akserekkefølgen i `01` respekteres: står det at 1. akse er øst, byttes koordinatene.

## [0.3.0] – 2026-10-29

### Lagt til
- Dra og slipp: en `.kof`-fil som slippes i kartet eller lagpanelet, importeres direkte med punktlag og middellag. Advarsler vises i meldingslinjen. Mangler filen koordinatsystem, åpnes dialogen.
- Standardstil: punktlaget får mørke sirkler med punktnavn, middellaget røde kryss med navnene på alle målingene i gruppen.
- Ikon i meny, verktøylinje, Processing-verktøykassen og pluginlisten.

## [0.2.0] – 2026-10-29

### Lagt til
- Middellag for gjentatte målinger i «Importer KOF-fil»: ett punkt per gruppe med middel, standardavvik og største avvik.
- Parametere for horisontal toleranse (standard 5 cm), valgfri høydetoleranse og om enkeltmålte punkter skal tas med.
- Advarsel i loggen for punktpar som ligger opptil dobbel toleranse fra hverandre.

## [0.1.0] – 2026-10-29

### Lagt til
- Processing-algoritme «Importer KOF-fil» (`kof:importkof`) som lager et PointZ-lag, med CRS fra filen eller valgt manuelt.
- Menyvalget Vektor → KOF Import → Importer KOF-fil… åpner algoritmen.
- Parser for `00`-metadata, `01`-hoder (rå tekst) og `05`-punkter, med cp1252/UTF-8.
- Gjenkjenning av EPSG fra `Projeksjon:` (EUREF89 UTM/NTM) og NN2000 fra geoidemodell.
- Gruppering av gjentatte målinger med middelverdi og spredning.
- Tester mot eksempelfil fra Topcon Field, og CI med GitHub Actions.

## [0.0.1] – 2026-10-29

### Lagt til
- Plugin-skjelett som lastes i QGIS (meny under Vektor → KOF Import).
