"""Format readers. Each turns a project/exchange file into a `media_collector.model.Project`."""

import xml.etree.ElementTree as ET
from pathlib import Path

from media_collector.model import Project


def _xml_root_tag(path: Path) -> str:
    for _event, el in ET.iterparse(path, events=("start",)):
        return el.tag
    return ""


def normalize_project_path(path: str | Path) -> Path:
    """The file that represents a project: inside a `.fcpxmld` bundle, `Info.fcpxml` means the bundle."""
    path = Path(path)
    if path.name.lower() == "info.fcpxml" and path.parent.suffix.lower() == ".fcpxmld":
        return path.parent
    return path


_UNSUPPORTED = {
    ".fcpbundle": "This is a Final Cut Pro library. In Final Cut choose File > Export XML and open "
    "that file instead.",
    ".drp": "DaVinci Resolve project files are not supported. In Resolve export the timeline as "
    "XML, FCPXML, OTIO or AAF and open that instead.",
    ".drt": "DaVinci Resolve timeline files are not supported. In Resolve export the timeline as "
    "XML, FCPXML, OTIO or AAF and open that instead.",
    ".edl": "EDL files hold clip names but no file locations, so they cannot be used to find media.",
    ".aepx": "After Effects XML (.aepx) is not supported; open the .aep file instead.",
}


def read_project(path: str | Path) -> Project:
    """Pick a reader from the file type (extension, and the root element for `.xml`)."""
    path = normalize_project_path(path)
    suffix = path.suffix.lower()
    if path.is_dir() and suffix == ".fcpxmld":  # FCPXML bundle
        path, suffix = path / "Info.fcpxml", ".fcpxml"
    if suffix in _UNSUPPORTED:
        raise ValueError(_UNSUPPORTED[suffix])
    if suffix == ".aep":
        from media_collector.readers.aep import read_aep

        return read_aep(path)
    if suffix == ".prproj":
        from media_collector.readers.premiere import read_premiere

        return read_premiere(path)
    if suffix == ".aaf":
        from media_collector.readers.aaf import read_aaf

        return read_aaf(path)
    if suffix == ".otio":
        from media_collector.readers.otio import read_otio

        return read_otio(path)
    if suffix == ".fcpxml":
        from media_collector.readers.fcpxml import read_fcpxml

        return read_fcpxml(path)
    if suffix == ".xml":
        tag = _xml_root_tag(path)
        if tag == "xmeml":
            from media_collector.readers.fcp7xml import read_fcp7xml

            return read_fcp7xml(path)
        if tag == "fcpxml":
            from media_collector.readers.fcpxml import read_fcpxml

            return read_fcpxml(path)
        raise ValueError(f"Unrecognised XML project (root element <{tag}>)")
    raise ValueError(f"Unsupported project format: {suffix or path.name}")
