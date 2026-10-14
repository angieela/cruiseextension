import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from backend.date_utils import build_sailing_identifier, format_sailing_date_range


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def evaluate_content_script(function_name, card_dataset, timezone_name=None):
    if shutil.which("node") is None:
        pytest.skip("Node.js is required to execute the real content script")

    script = r"""
const fs = require("fs");
const vm = require("vm");
const contentSource = fs.readFileSync(process.argv[1], "utf8");
const dataset = JSON.parse(process.argv[2]);
const functionName = process.argv[3];
const sandbox = {
  console,
  URLSearchParams,
  fetch: async () => ({ status: 404, ok: false }),
  window: { clearTimeout() {}, setTimeout() {} },
  document: {
    documentElement: {},
    querySelectorAll() { return []; },
    createElement() { return {}; },
  },
  MutationObserver: class { observe() {} },
};
vm.createContext(sandbox);
vm.runInContext(contentSource, sandbox);
const card = { dataset };
const result = vm.runInContext(functionName, sandbox)(card);
process.stdout.write(JSON.stringify(result));
"""
    result = subprocess.run(
        [
            "node",
            "-e",
            script,
            str(PROJECT_ROOT / "extension" / "content.js"),
            json.dumps(card_dataset),
            function_name,
        ],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **({"TZ": timezone_name} if timezone_name else {})},
    )
    return json.loads(result.stdout)


def test_scraper_and_content_script_build_the_same_identifier():
    dataset = {
        "packageCode": "OV07HNL-001",
        "shipCode": "OV",
        "startDate": "2027-09-07",
        "endDate": "2027-09-14",
    }
    extension_identifier = evaluate_content_script("getSailingIdentifier", dataset)

    sailing_range = format_sailing_date_range(
        dataset["startDate"], dataset["endDate"]
    )
    scraper_identifier = build_sailing_identifier(
        dataset["packageCode"],
        dataset["shipCode"],
        sailing_range,
        dataset["startDate"],
    )

    assert scraper_identifier == {
        "package_code": extension_identifier["packageCode"],
        "ship_code": extension_identifier["shipCode"],
        "year": extension_identifier["year"],
        "sailing_date_range": extension_identifier["sailingDateRange"],
    }
    assert scraper_identifier["sailing_date_range"] == "Sep 7 - Sep 14"
    assert ", 2027" not in scraper_identifier["sailing_date_range"]


@pytest.mark.parametrize(
    ("dataset", "expected"),
    [
        (
            {
                "packageCode": "OV07HNL-001",
                "shipCode": "OV",
                "startDate": "2027-09-07",
                "endDate": "2027-09-14",
            },
            {"year": "2027", "month": "Sep", "day": "7"},
        ),
        (
            {
                "packageCode": "OV07HNL-002",
                "shipCode": "OV",
                "startDate": "2027-09-29",
                "endDate": "2027-10-06",
            },
            {"year": "2027", "month": "Sep", "day": "29"},
        ),
        (
            {
                "packageCode": "OV07HNL-003",
                "shipCode": "OV",
                "startDate": "2027-12-29",
                "endDate": "2028-01-05",
            },
            {"year": "2027", "month": "Dec", "day": "29"},
        ),
    ],
)
def test_content_script_derives_embarkation_date_parts(dataset, expected):
    assert evaluate_content_script("getEmbarkationDateParts", dataset) == expected


@pytest.mark.parametrize(
    "timezone_name",
    ["America/Los_Angeles", "UTC", "Asia/Seoul"],
)
def test_sailing_identifier_is_timezone_independent(timezone_name):
    dataset = {
        "packageCode": "OV07HNL-001",
        "shipCode": "OV",
        "startDate": "2027-09-07T23:30:00Z",
        "endDate": "2027-09-14T23:30:00Z",
    }

    identifier = evaluate_content_script(
        "getSailingIdentifier",
        dataset,
        timezone_name=timezone_name,
    )

    assert identifier == {
        "packageCode": "OV07HNL-001",
        "shipCode": "OV",
        "year": 2027,
        "sailingDateRange": "Sep 7 - Sep 14",
    }
