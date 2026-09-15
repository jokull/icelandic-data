"""Offline regression tests for the shared Power BI health helper."""

import pytest

from tests.health.conftest import PowerBIPublicEmbed


@pytest.mark.parametrize("identifier_key", ["name", "objectName"])
def test_sections_accepts_both_powerbi_identifier_schemas(identifier_key):
    payload = {
        "exploration": {
            "sections": [
                {
                    identifier_key: "ReportSection123",
                    "displayName": "Overview",
                }
            ]
        }
    }

    assert PowerBIPublicEmbed.sections(payload) == {
        "ReportSection123": "Overview"
    }


def test_sections_rejects_an_unknown_powerbi_identifier_schema():
    payload = {"exploration": {"sections": [{"displayName": "Overview"}]}}

    with pytest.raises(AssertionError, match="neither name nor objectName"):
        PowerBIPublicEmbed.sections(payload)
