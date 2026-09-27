import re
from pathlib import Path

import media_collector

ROOT = Path(__file__).parent.parent


def test_versions_agree_everywhere():
    swift = (ROOT / "app/Sources/MediaCollector/AppVersion.swift").read_text()
    app_version = re.search(r'appVersion = "([^"]+)"', swift).group(1)
    changelog = (ROOT / "CHANGELOG.md").read_text()
    latest = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.MULTILINE).group(1)
    assert media_collector.__version__ == app_version == latest


def test_changelog_has_an_unreleased_section():
    text = (ROOT / "CHANGELOG.md").read_text()
    assert "## [Unreleased]" in text
    assert text.index("## [Unreleased]") < text.index("## [0.")  # newest first


def test_semver_shape():
    assert re.fullmatch(r"\d+\.\d+\.\d+", media_collector.__version__)
