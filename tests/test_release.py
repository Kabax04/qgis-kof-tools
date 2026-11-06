"""The release script, run against the current commit."""

import importlib.util
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

# The release script reads from git. QGIS's Python (python-qgis.bat) often has no git in PATH.
if shutil.which("git") is None:
    pytest.skip("git is not available", allow_module_level=True)

SCRIPT = Path(__file__).parent.parent / "scripts" / "release.py"
spec = importlib.util.spec_from_file_location("release", SCRIPT)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)

VERSION = release.metadata("HEAD")["version"]


def test_check_rejects_wrong_tag():
    with pytest.raises(SystemExit):
        release.check("HEAD")


def test_zip(tmp_path):
    path = release.build_zip("HEAD", tmp_path)
    assert path.name == f"kof_tools.{VERSION}.zip"
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    assert "kof_tools/metadata.txt" in names
    assert "kof_tools/LICENSE" in names
    assert all(n.startswith("kof_tools/") for n in names)
    assert not [n for n in names if "__pycache__" in n or n.endswith(".pyc")]


def test_changelog_section():
    notes = release.changelog_section("HEAD")
    assert notes.strip()
    assert "## [" not in notes


def test_plugins_xml():
    root = ET.fromstring(release.plugins_xml("HEAD"))
    (plugin,) = root.findall("pyqgis_plugin")
    assert plugin.get("name") == "KOF Tools"
    assert plugin.get("version") == VERSION
    # QGIS identifies the plugin by the part of file_name before the first dot.
    assert plugin.findtext("file_name").partition(".")[0] == "kof_tools"
    assert plugin.findtext("download_url").endswith(f"/releases/download/HEAD/kof_tools.{VERSION}.zip")
    assert plugin.findtext("author_name") == "Jonas Bratland"
    assert plugin.findtext("experimental") == "False"
    assert plugin.findtext("qgis_minimum_version") == "3.22"
    assert plugin.findtext("qgis_maximum_version") == "4.99"
