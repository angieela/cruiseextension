import json
import shutil
import subprocess
from pathlib import Path

import pytest

from date_utils import build_sailing_identifier, format_sailing_date_range


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def content_script_identifier(card_dataset):
    if shutil.which("node") is None:
        pytest.skip("Node.js is required to execute the real content script")

    script = r"""
const fs = require("fs");
const vm = require("vm");
const contentSource = fs.readFileSync(process.argv[1], "utf8");
const dataset = JSON.parse(process.argv[2]);
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
sandbox.result = vm.runInContext("getSailingIdentifier", sandbox)(card);
process.stdout.write(JSON.stringify(sandbox.result));
"""
    result = subprocess.run(
        [
            "node",
            "-e",
            script,
            str(PROJECT_ROOT / "content.js"),
            json.dumps(card_dataset),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def content_script_embarkation_date_parts(card_dataset):
    if shutil.which("node") is None:
        pytest.skip("Node.js is required to execute the real content script")

    script = r"""
const fs = require("fs");
const vm = require("vm");
const contentSource = fs.readFileSync(process.argv[1], "utf8");
const dataset = JSON.parse(process.argv[2]);
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
const dateParts = vm.runInContext("getEmbarkationDateParts", sandbox)(card);
process.stdout.write(JSON.stringify(dateParts));
"""
    result = subprocess.run(
        [
            "node",
            "-e",
            script,
            str(PROJECT_ROOT / "content.js"),
            json.dumps(card_dataset),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_scraper_and_content_script_build_the_same_identifier():
    dataset = {
        "packageCode": "OV07HNL-001",
        "shipCode": "OV",
        "startDate": "2027-09-07",
        "endDate": "2027-09-14",
    }
    extension_identifier = content_script_identifier(dataset)

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
    assert content_script_embarkation_date_parts(dataset) == expected
