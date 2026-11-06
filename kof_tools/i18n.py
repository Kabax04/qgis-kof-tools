"""Translations.

The source language is English. When QGIS runs in Norwegian (bokmål or
nynorsk), texts are looked up in NB below. A plain Python dictionary keeps
the plugin free of compiled .qm files and lets the tests check that every
text is translated.

Every call to tr() must take a single string literal, so the tests can find
all texts in the source code. Values are filled in with str.format().
"""

from typing import Optional

NORWEGIAN = ("nb", "nn", "no")

_language: Optional[str] = None


def set_language(language: Optional[str]) -> None:
    """Set the language explicitly ("en", "nb", ...). None means detect from QGIS."""
    global _language
    _language = language


def language() -> str:
    global _language
    if _language is None:
        _language = _detect_language()
    return _language


def _detect_language() -> str:
    try:
        from qgis.core import QgsApplication
    except ImportError:
        return "en"
    locale = (QgsApplication.locale() or "en")[:2].lower()
    return "nb" if locale in NORWEGIAN else "en"


def tr(text: str, /, **values) -> str:
    if language() in NORWEGIAN:
        text = NB.get(text, text)
    else:
        text = EN.get(text, text)
    return text.format(**values) if values else text


# Long texts are looked up by a short key in both languages.
EN = {
    "HELP": (
        "Reads points (05 records) from a KOF file and creates a PointZ layer.\n\n"
        "The coordinate reference system is taken from the file header (the 01 block or e.g. "
        "\"Projeksjon: EUREF89 UTM 32\"). Select one manually if the file does not state it, or to override.\n\n"
        "Repeated measurements: points within the horizontal tolerance (directly or through a chain of "
        "neighbours) are merged into one mean point with standard deviation and largest deviation. The height "
        "difference must also be within the height tolerance (default 10 cm), so points above each other, "
        "such as the lid and bottom of a manhole, are kept apart; leave it empty for no limit. Point "
        "pairs up to twice the tolerance apart are reported as warnings in the log.\n\n"
        "Lines and polygons: 09 blocks with line codes (91 straight line, 92 spline, 93 arc, 72-79 and 82-89 "
        "several simultaneous lines, 96 close polygon, 99 end) produce a line layer and a polygon layer. These "
        "layers are only created when the file contains such data.\n\n"
        "GNSS vectors: baselines from post-processing software (42 start station with geocentric X Y Z, "
        "43 vector dX dY dZ, 44 standard deviations and correlations, 46 date and time) produce a line layer "
        "from the start station to start + vector. The 42 coordinates are read as EUREF89 and are usually "
        "only approximate, so the vectors are placed to within a few metres, while dX, dY, dZ and the "
        "length in the fields are exact. Z is the ellipsoidal height. A file with only vectors and no "
        "coordinate reference system is shown in the UTM zone of the first station."
    ),
    "HELP_EXPORT": (
        "Writes a point, line or polygon layer to a KOF file, with a 01 header holding the coordinate "
        "system code and north before east. Points become 05 records. Lines become 09 91 blocks ended by "
        "09 99, and polygons 09 91 blocks closed by 09 96, with one 05 record per vertex.\n\n"
        "The fields default to those of layers made by the import (name, code, H, calc_code, remark, points). "
        "Fields the layer does not have are left out. Points without a name (no name field, or an empty "
        "value) are numbered with numbers the layer does not already use as names, and points without a height "
        "value take the Z value of the geometry.\n\n"
        "Lines and polygons: the vertices take their names from the comma-separated point names field when it "
        "has one name per vertex, otherwise they are numbered. Heights come from Z, and the code applies to "
        "every vertex. Arcs from the import are written back as 09 93 with their measured points. Other "
        "curves are segmented, multipart features give one block per part, and polygon holes "
        "become polygons of their own.\n\n"
        "The points are transformed to the selected coordinate reference system, or written in the layer's. "
        "KOF holds projected coordinates, so geographic systems (latitude and longitude) are not accepted.\n\n"
        "Names longer than 10 characters and codes longer than 8 are shortened, and points with coordinates "
        "too large for the KOF columns are skipped. This is reported in the log.\n\n"
        "Windows-1252 suits most instruments and older software. Choose UTF-8 if the program reading the "
        "file expects it."
    ),
    "HELP_EXPORT_LAYERS": (
        "Writes several layers to one KOF file, for example the point, line and polygon layers of an import. "
        "Points become 05 records, and lines and polygons 09 blocks, as in Export to KOF file.\n\n"
        "The fields are found by the names the import uses (name, code, H, calc_code, remark, points, type); "
        "fields a layer does not have are left out. Points that are also points of an exported line or "
        "polygon, with the same name and position to the millimetre, are written only in its 09 block, so "
        "they do not appear twice. The other points come first, then the lines and polygons.\n\n"
        "The file is written in the first layer's coordinate reference system unless you select another one."
    ),
}


NB = {
    # Plugin and menu
    "Import KOF file…": "Importer KOF-fil…",
    "{file} imported.": "{file} importert.",
    "{file} imported with 1 warning.": "{file} importert med 1 advarsel.",
    "{file} could not be imported.": "{file} kunne ikke importeres.",
    "{file} imported with {count} warnings.": "{file} importert med {count} advarsler.",
    # Algorithm
    "Import KOF file": "Importer KOF-fil",
    "KOF file": "KOF-fil",
    "Coordinate reference system (empty = from file)": "Koordinatsystem (tom = fra filen)",
    "KOF points": "KOF-punkter",
    "Tolerance for repeated measurements (horizontal)": "Toleranse for gjentatte målinger (horisontalt)",
    "Height tolerance (empty = no limit)": "Høydetoleranse (tom = ingen krav)",
    "Include points measured only once in the mean layer": "Ta med punkter som bare er målt én gang i middellaget",
    "Mean of repeated measurements": "Middel av gjentatte målinger",
    "Lines (09 blocks)": "Linjer (09-blokker)",
    "Polygons (closed with 09 96)": "Flater (lukket med 09 96)",
    "GNSS vectors (42/43 records)": "GNSS-vektorer (42/43-poster)",
    "GNSS vectors": "GNSS-vektorer",
    "{count} GNSS vectors imported. The start stations are placed from the coordinates in the 42 records, read as EUREF89; Z is the ellipsoidal height.": "{count} GNSS-vektorer importert. Startstasjonene plasseres etter koordinatene i 42-postene, lest som EUREF89; Z er ellipsoidisk høyde.",
    "No coordinate reference system in the file. The GNSS vectors are shown in the UTM zone of the first station: {crs}": "Fant ikke koordinatsystem i filen. GNSS-vektorene vises i UTM-sonen til den første stasjonen: {crs}",
    "mean": "middel",
    "lines": "linjer",
    "polygons": "flater",
    "Using selected coordinate reference system {crs}": "Bruker valgt koordinatsystem {crs}",
    "Coordinate reference system from file: {crs}": "Koordinatsystem fra filen: {crs}",
    "Unknown coordinate system code {code} in the 01 block, ignored": "Ukjent koordinatsystemkode {code} i 01-blokken, ignorert",
    "No coordinate reference system found in the file. Select one manually.": "Fant ikke koordinatsystem i filen. Velg koordinatsystem manuelt.",
    "Heights are in NN2000": "Høyder er oppgitt i NN2000",
    "The coordinates look like east before north for {crs}. North and east have been swapped.": "Koordinatene ser ut til å stå med øst før nord for {crs}. Nord og øst er byttet.",
    "{points} points imported, {warnings} warnings, {disabled} lines disabled (encoding {encoding})": "{points} punkter importert, {warnings} advarsler, {disabled} linjer satt ut av funksjon (tegnkoding {encoding})",
    "{count} groups of repeated measurements (tolerance {tolerance} m, height {height})": "{count} grupper av gjentatte målinger (toleranse {tolerance} m, høyde {height})",
    "no limit": "ingen krav",
    "  {names}: largest deviation {deviation:.1f} mm": "  {names}: største avvik {deviation:.1f} mm",
    "{a} and {b} are {distance:.3f} m apart, just outside the tolerance. Check whether they are the same point.": "{a} og {b} ligger {distance:.3f} m fra hverandre, litt utenfor toleransen. Sjekk om de er samme punkt.",
    "{lines} lines and {polygons} polygons from 09 blocks": "{lines} linjer og {polygons} flater fra 09-blokker",
    "HELP": (
        "Leser punkter (05-poster) fra en KOF-fil og lager et PointZ-lag.\n\n"
        "Koordinatsystemet hentes fra filhodet (01-blokken eller f.eks. «Projeksjon: EUREF89 UTM 32»). "
        "Velg koordinatsystem manuelt hvis filen ikke oppgir det, eller for å overstyre.\n\n"
        "Gjentatte målinger: punkter som ligger innenfor toleransen horisontalt (direkte eller via en kjede "
        "av naboer) slås sammen til ett middelpunkt med standardavvik og største avvik. Høydeforskjellen må "
        "også være innenfor høydetoleransen (standard 10 cm), så punkter over hverandre, som lokk og bunn i en "
        "kum, holdes adskilt; la feltet stå tomt for ingen krav. Punktpar som ligger "
        "opptil dobbel toleranse fra hverandre, rapporteres som advarsel i loggen.\n\n"
        "Linjer og flater: 09-blokker med linjekoder (91 rett linje, 92 spline, 93 bue, 72-79 og 82-89 flere "
        "samtidige linjer, 96 lukk polygon, 99 slutt) gir et linjelag og et flatelag. Lagene lages bare når "
        "filen har slike data.\n\n"
        "GNSS-vektorer: basislinjer fra etterprosesseringsprogrammer (42 startstasjon med geosentriske X Y Z, "
        "43 vektor dX dY dZ, 44 standardavvik og korrelasjoner, 46 dato og tid) gir et linjelag fra "
        "startstasjonen til start + vektor. Koordinatene i 42 leses som EUREF89 og er som regel bare "
        "omtrentlige, så vektorene plasseres med noen meters nøyaktighet, mens dX, dY, dZ og lengden i "
        "feltene er eksakte. Z er ellipsoidisk høyde. En fil med bare vektorer og uten koordinatsystem vises "
        "i UTM-sonen til den første stasjonen."
    ),
    "The old KOF Import plugin is still installed, and the two cannot run together. Uninstall KOF Import in Plugins → Manage and Install Plugins, then restart QGIS.": "Det gamle programtillegget KOF Import er fortsatt installert, og de to kan ikke kjøre samtidig. Avinstaller KOF Import i Programtillegg → Administrer og installer programtillegg, og start QGIS på nytt.",
    "File header (01): job {job}, date {date}, municipality {municipality}, observer {observer}": "Filhode (01): oppdrag {job}, dato {date}, kommune {municipality}, observatør {observer}",
    "File header (01): {text}": "Filhode (01): {text}",
    "Comments in the file:": "Kommentarer i filen:",
    "  … and {count} more": "  … og {count} til",
    # Export
    "Export to KOF…": "Eksporter til KOF…",
    "Export to KOF file": "Eksporter til KOF-fil",
    "Layer to export (points, lines or polygons)": "Lag som skal eksporteres (punkter, linjer eller flater)",
    "Point names of lines and polygons (comma-separated field)": "Punktnavn for linjer og flater (felt med kommadelte navn)",
    "{count} curved feature(s) were written as straight lines through points along the curve": "{count} kurvede objekt(er) ble skrevet som rette linjer gjennom punkter langs kurven",
    "{count} polygon hole(s) were written as separate polygons": "{count} hull i flater ble skrevet som egne flater",
    "{lines} lines and {polygons} polygons written as 09 blocks": "{lines} linjer og {polygons} flater skrevet som 09-blokker",
    "Point name field (empty = number the points)": "Felt for punktnavn (tom = nummerer punktene)",
    "Code field": "Felt for kode",
    "Height field (empty = Z of the geometry)": "Felt for høyde (tom = Z fra geometrien)",
    "Calculation code field": "Felt for beregningskode",
    "Remark field": "Felt for merknad",
    "Coordinate reference system in the file (empty = the layer's)": "Koordinatsystem i filen (tom = lagets)",
    "Encoding": "Tegnkoding",
    "KOF files (*.kof)": "KOF-filer (*.kof)",
    "KOF files hold projected coordinates (north and east in metres), but {crs} is not projected. Select a projected coordinate reference system for the file, e.g. EUREF89 UTM 32 (EPSG:25832).": "KOF-filer har projiserte koordinater (nord og øst i meter), men {crs} er ikke projisert. Velg et projisert koordinatsystem for filen, f.eks. EUREF89 UTM 32 (EPSG:25832).",
    "{crs} has no SOSI coordinate system code. The 01 block is written without one, and some instruments may not recognise the coordinate reference system.": "{crs} har ingen SOSI-kode for koordinatsystem. 01-blokken skrives uten, og noen instrumenter kjenner kanskje ikke igjen koordinatsystemet.",
    "Transforming from {source} to {target}": "Transformerer fra {source} til {target}",
    "The layer has no coordinate reference system. The coordinates are written unchanged and labelled as {crs}.": "Laget har ikke koordinatsystem. Koordinatene skrives uendret og merkes som {crs}.",
    "The layer has no field {field}, not used": "Laget har ikke feltet {field}, brukes ikke",
    "{count} points written to {path} ({encoding})": "{count} punkter skrevet til {path} ({encoding})",
    "HELP_EXPORT": (
        "Skriver et punkt-, linje- eller flatelag til en KOF-fil, med et 01-hode med koordinatsystemkode "
        "og nord før øst. Punkter blir 05-poster. Linjer blir 09 91-blokker avsluttet med 09 99, og flater "
        "09 91-blokker lukket med 09 96, med én 05-post per knekkpunkt.\n\n"
        "Feltene er som standard de samme som i lag fra importen (name, code, H, calc_code, remark, points). "
        "Felt laget ikke har, utelates. Punkter uten navn (uten navnefelt, eller med tom verdi) "
        "nummereres med tall som ikke allerede er brukt som navn i laget, og punkter uten høydeverdi får "
        "Z-verdien i geometrien.\n\n"
        "Linjer og flater: knekkpunktene får navn fra feltet med kommadelte punktnavn når det har ett navn "
        "per knekkpunkt, ellers nummereres de. Høydene hentes fra Z, og koden gjelder alle knekkpunktene. "
        "Buer fra importen skrives tilbake som 09 93 med de målte punktene. Andre kurver deles opp i rette "
        "linjer, objekter med flere deler gir én blokk per del, og hull i flater "
        "blir egne flater.\n\n"
        "Punktene transformeres til valgt koordinatsystem, eller skrives i lagets. KOF har projiserte "
        "koordinater, så geografiske systemer (bredde og lengde) godtas ikke.\n\n"
        "Navn lengre enn 10 tegn og koder lengre enn 8 kortes, og punkter med koordinater som er for store "
        "for KOF-kolonnene, hoppes over. Dette rapporteres i loggen.\n\n"
        "Windows-1252 passer for de fleste instrumenter og eldre programmer. Velg UTF-8 hvis programmet som "
        "leser filen, forventer det."
    ),
    "HELP_EXPORT_LAYERS": (
        "Skriver flere lag til én KOF-fil, for eksempel punkt-, linje- og flatelaget fra en import. Punkter "
        "blir 05-poster, og linjer og flater 09-blokker, som i Eksporter til KOF-fil.\n\n"
        "Feltene finnes ved navnene importen bruker (name, code, H, calc_code, remark, points, type); felt "
        "et lag ikke har, utelates. Punkter som også er punkter i en linje eller flate som eksporteres, med "
        "samme navn og posisjon på millimeteren, skrives bare i 09-blokken, så de ikke kommer to ganger. De "
        "andre punktene kommer først, deretter linjene og flatene.\n\n"
        "Filen skrives i koordinatsystemet til det første laget hvis du ikke velger et annet."
    ),
    "Export layers to KOF…": "Eksporter lag til KOF…",
    "Export layers to one KOF file": "Eksporter lag til én KOF-fil",
    "Layers to export (points, lines and polygons)": "Lag som skal eksporteres (punkter, linjer og flater)",
    "Coordinate reference system in the file (empty = the first layer's)": "Koordinatsystem i filen (tom = det første lagets)",
    "Select at least one point, line or polygon layer.": "Velg minst ett punkt-, linje- eller flatelag.",
    "{count} points that are also in lines or polygons were written in their 09 blocks only": "{count} punkter som også ligger i linjer eller flater, ble bare skrevet i 09-blokkene deres",
    # Parser
    "Line {line_no}: could not read point: {text}": "Linje {line_no}: kunne ikke lese punkt: {text}",
    "Line {line_no}: point {name} is missing north or east coordinate, ignored": "Linje {line_no}: punkt {name} mangler nord- eller østkoordinat, ignorert",
    "Line {line_no}: point {name} has irregular columns, and its code and coordinates cannot be told apart, ignored: {text}": "Linje {line_no}: punkt {name} har uregelmessige kolonner, og kode og koordinater kan ikke skilles fra hverandre, ignorert: {text}",
    "{count} point(s) do not follow the KOF columns and were read word by word. Check their code and coordinates. First at line {line_no}.": "{count} punkt(er) følger ikke KOF-kolonnene og ble lest ord for ord. Kontroller kode og koordinater. Første gang på linje {line_no}.",
    "{count} lines with unknown record type {record} ignored, first at line {line_no}": "{count} linjer med ukjent postkode {record} ignorert, første på linje {line_no}",
    "Line {line_no}: unknown record type {record}, ignored": "Linje {line_no}: ukjent postkode {record}, ignorert",
    "Line {line_no}: radius (08 141) is not supported, drawn as a straight line": "Linje {line_no}: radius (08 141) støttes ikke, tegnes som rett linje",
    # GNSS vectors
    "Line {line_no}: vector (43) without a start station (42), ignored": "Linje {line_no}: vektor (43) uten startstasjon (42), ignorert",
    "Line {line_no}: {record} record without a vector (43) before it, ignored": "Linje {line_no}: {record}-post uten vektor (43) foran, ignorert",
    "Line {line_no}: could not read GNSS vector record: {text}": "Linje {line_no}: kunne ikke lese GNSS-vektorpost: {text}",
    # Lines
    "Line {line_no}: 09 96 (close polygon) without an active line": "Linje {line_no}: 09 96 (lukk polygon) uten aktiv linje",
    "Line {line_no}: the line was not ended with 09 99 or 96": "Linje {line_no}: linjen ble ikke avsluttet med 09 99 eller 96",
    "Line {line_no}: spline (09 92) is drawn as straight lines": "Linje {line_no}: spline (09 92) tegnes som rette linjer",
    "Line {line_no}: polygon with only 2 points, drawn as a line": "Linje {line_no}: polygon med bare 2 punkter, tegnes som linje",
    "Line {line_no}: line with {count} point(s) ignored": "Linje {line_no}: linje med {count} punkt(er) ignorert",
    # Writer
    "{count} point name(s) longer than 10 characters were shortened, e.g. {examples}": "{count} punktnavn lengre enn 10 tegn ble forkortet, f.eks. {examples}",
    "{count} code(s) longer than 8 characters were shortened, e.g. {examples}": "{count} koder lengre enn 8 tegn ble forkortet, f.eks. {examples}",
    "{count} point name(s) or code(s) had '!', which starts a comment in KOF, and it was replaced with '_', e.g. {examples}": "{count} punktnavn eller koder hadde '!', som starter en kommentar i KOF, og det ble byttet ut med '_', f.eks. {examples}",
    "{count} point(s) without north or east coordinate were skipped, e.g. {examples}": "{count} punkt(er) uten nord- eller østkoordinat ble hoppet over, f.eks. {examples}",
    "{count} point(s) with north or east too large for the KOF columns were skipped, e.g. {examples}. Check the coordinate reference system.": "{count} punkt(er) med nord eller øst for store for KOF-kolonnene ble hoppet over, f.eks. {examples}. Sjekk koordinatsystemet.",
    "{count} height(s) too large for the KOF column were left empty, e.g. for point {examples}": "{count} høyde(r) for store for KOF-kolonnen ble stående tomme, f.eks. for punkt {examples}",
    "{count} calculation code(s) that are not a whole number from 0 to 99 were left out, e.g. for point {examples}": "{count} beregningskode(r) som ikke er et heltall fra 0 til 99 ble utelatt, f.eks. for punkt {examples}",
    "{count} line(s) or polygon(s) with too few points were skipped, e.g. starting at point {examples}": "{count} linje(r) eller flate(r) med for få punkter ble hoppet over, f.eks. med startpunkt {examples}",
    "{count} line(s) have characters that {encoding} cannot store, written as '?'. First at line {line_no}.": "{count} linje(r) har tegn som {encoding} ikke kan lagre, skrevet som '?'. Første gang på linje {line_no}.",
}
