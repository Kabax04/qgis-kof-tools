# KOF Tools for QGIS

A QGIS plugin that imports KOF files, the coordinate file format used by
Norwegian surveying instruments and software, and exports point, line and polygon layers to KOF.

The user interface is available in English and Norwegian, following the
QGIS language setting.

## Features

- **Points** from `05` records, as a PointZ layer with name, code, N, E, H,
  calculation code and remark.
- **Lines and polygons** from `09` blocks: straight lines (`91`), arcs (`93`),
  splines (`92`, drawn straight), several simultaneous lines (`72`–`79` saw
  method, `82`–`89` wave method), closed polygons (`96`) and point swarms (`94`).
- **GNSS vectors** (baselines) from post-processing software such as Topcon
  MAGNET Tools: `42` start station (geocentric X Y Z), `43` vector, `44`
  standard deviations and correlations, `46` date and time. They become a
  LineStringZ layer from the start station to start + vector.
- **Coordinate reference system** from the `01` block (all SOSI codes:
  EUREF89 UTM and NTM, NGO1948, ED50, WGS84 UTM …) or from comments such as
  `Projeksjon: EUREF89 UTM 32`, `EXPORT PROJECTION: ETRS_1989_UTM_Zone_32N`
  or `SRID: 25832`. You can always choose another CRS.
- **Axis order** from the `01` block, with a check that corrects files where
  north and east are obviously swapped.
- **Repeated measurements**: points within a tolerance (default 5 cm) are
  merged into a mean layer with standard deviations and largest deviation.
  Pairs just outside the tolerance are reported as warnings.
- Handles Windows-1252 and UTF-8, disabled lines (`-` in column 1), `!`
  comments and files with irregular columns or tabs.
- **Export** of point, line and polygon layers to KOF, with the coordinate
  system code in the `01` block, optional transformation, and warnings for
  values that do not fit the KOF columns. Lines and polygons become `09` blocks.

## Installation

- **From the official QGIS plugin repository** (once approved): search for
  *KOF Tools* in **Plugins → Manage and Install Plugins**.
- **From this repository, with automatic updates:** in **Plugins → Manage and
  Install Plugins → Settings**, click **Add…** and enter
  `https://raw.githubusercontent.com/Kabax04/qgis-kof-tools/main/plugins.xml`
  as URL. KOF Tools then shows up in the plugin list, and QGIS reports new
  versions as they are released.
- **From a zip file:** download `kof_tools.x.y.z.zip` from
  [Releases](https://github.com/Kabax04/qgis-kof-tools/releases) and use
  **Install from ZIP**.

The plugin was called *KOF Import* (folder `kof_import`) up to version 1.1.0.
QGIS treats KOF Tools as a new plugin, so uninstall KOF Import after installing
it. The old repository address still works, as GitHub redirects it.

## Usage

- Drag a `.kof` file onto the map or the layers panel, or
- choose **Vector → KOF Tools → Import KOF file…** (or the toolbar button) to
  set the CRS and tolerance yourself. The algorithm is also in the Processing
  toolbox, so it works in batch mode and in the graphical modeler.

You get a point layer and a mean layer. Files with `09` blocks also give a
line layer and a polygon layer, and files with GNSS vectors a vector layer.

The start stations of GNSS vectors are placed from the coordinates in the `42`
records, read as EUREF89. These are usually approximate (they differ from
session to session), so the vectors are placed to within a few metres, while
`dX`, `dY`, `dZ` and `length` are exact. Z is the ellipsoidal height. `sX`–`sZ`
are standard deviations in metres and `rXY`–`rYZ` correlations; `info` holds
the rest of the `46` record unparsed. A file with only vectors and no
coordinate reference system is shown in the UTM zone of the first station, so
you can drop all the session files on the map to see the network.

To export, select a point, line or polygon layer and choose **Vector → KOF Tools → Export to
KOF…** (or the *Export to KOF file* algorithm in the Processing toolbox). The
fields default to those of the import (`name`, `code`, `H`, `calc_code`,
`remark`); for other layers, pick the fields to use. Without a name field the
points are numbered, and without a height field the Z value is used. The file
is written in the layer's coordinate reference system unless you select
another one, in Windows-1252 unless you choose UTF-8.

Lines are written as `09 91` … `09 99` and polygons as `09 91` … `09 96`.
The vertices take their names from the `points` field that the import writes
in its line layers, or are numbered. Curves (such as imported arcs) are
segmented, so they come back as straight `91` lines with more vertices.

### Layers and fields

| Layer | Fields |
|---|---|
| Points | `name`, `code`, `N`, `E`, `H`, `calc_code`, `remark`, `line_no`, `source_file` |
| Mean | `group`, `name`, `names`, `count`, `N`, `E`, `H`, `std_N`, `std_E`, `std_H`, `max_dev`, `source_file` |
| GNSS vectors | `name`, `from`, `to`, `dX`, `dY`, `dZ`, `length`, `sX`, `sY`, `sZ`, `rXY`, `rXZ`, `rYZ`, `date`, `time`, `info`, `line_no`, `source_file` |
| Lines / polygons | `name`, `type` (`line`, `arc`, `spline`, `polygon`), `code`, `count`, `points`, `pi`, `line_no`, `source_file` |

`line_no` is the line in the KOF file. In the line layers it is the line of
the `09` block that started the line.

## Limitations

- Only coordinate blocks (`05`) are read. Observations (`02`–`04`, `3x`, `4x`,
  `8x`) need a survey adjustment and are skipped with a warning.
- Radius (`08 141`) is not supported; such arcs are drawn as straight lines.
- Line support follows the KOF specification and its examples, but has not
  yet been tested against real files with lines. Example files are welcome as
  [issues](https://github.com/Kabax04/qgis-kof-tools/issues).

## Development

The plugin is in `kof_tools/`. The parser modules (`kof_parser.py`,
`kof_lines.py`, `kof_writer.py`, `crs_detect.py`, `duplicates.py`, `i18n.py`) are plain Python
and can be tested without QGIS:

```bash
python -m pip install pytest
python -m pytest
```

Tests that need QGIS are skipped with plain Python. Run them with the Python
that comes with QGIS, for example on Windows:

```bash
"C:/Program Files/QGIS 3.40.15/bin/python-qgis-ltr.bat" -m pip install --user pytest
"C:/Program Files/QGIS 3.40.15/bin/python-qgis-ltr.bat" -m pytest
```

To try the plugin in QGIS, link or copy `kof_tools/` into the plugin folder of
your QGIS profile and use the Plugin Reloader plugin.

### Releasing

1. Update `version` and `changelog` in `kof_tools/metadata.txt`, and add a
   section for the version to `CHANGELOG.md`.
2. Merge to `main`, then tag and push:

   ```bash
   git tag -a v1.2.3 -m "v1.2.3"
   git push origin v1.2.3
   ```

The [release workflow](.github/workflows/release.yml) runs the tests, builds
`kof_tools.1.2.3.zip`, creates the GitHub Release with the changelog section
as notes, and updates `plugins.xml` on `main`. Uploading to plugins.qgis.org
is still done by hand.

### Translations

Texts are written in English and wrapped in `tr()`. Norwegian translations are
in `kof_tools/i18n.py`; a test checks that every text is translated.

### KOF format notes

- The record type is in columns 2–3; column 1 is blank or `-` (disabled).
- `05` records use fixed columns: name `[4:14]`, code `[15:23]`, N `[24:36]`,
  E `[37:48]`, H `[49:57]` (0-based Python slices). **North comes before east.**
- Files from Topcon Field have no `01` record; the CRS is in `00 Projeksjon: …`.
- Some instruments use `09` for free text; only `09` followed by a number is a
  program code.
- `tests/data/spec_linjer.kof` is built from the examples in the KOF
  specification 2.00 (Norkart, 2005). `tests/data/ngi/` holds real files from
  [NGI kof-parser](https://github.com/norwegian-geotechnical-institute/kof-parser) (MIT).

## License

GPL-2.0, see [LICENSE](LICENSE).
