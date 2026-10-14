import json
import shutil
import subprocess
from pathlib import Path

import pytest


EXTENSION = Path(__file__).resolve().parents[1] / "extension"


def run_node(script, file_name):
    if shutil.which("node") is None:
        pytest.skip("Node.js is required to execute the extension scripts")
    return subprocess.run(
        ["node", "-e", script, str(EXTENSION / file_name)],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_service_worker_validates_messages_and_uses_fixed_api_url():
    script = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
let listener;
let requestedUrls = [];
let nextResponse = { status: 200, ok: true, json: async () => ({ status: "rated" }) };
const sandbox = {
  chrome: { runtime: { onMessage: { addListener(fn) { listener = fn; } } } },
  URLSearchParams,
  fetch: async (url) => { requestedUrls.push(url); return nextResponse; },
};
vm.runInNewContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);
const valid = {
  type: "GET_CRUISE_RATING",
  package_code: "LE07M870",
  ship_code: "LE",
  sailing_date_range: "Oct 3 - Oct 10",
  year: 2027,
  current_price: 1412,
};
function dispatch(message) {
  return new Promise((resolve) => listener(message, {}, resolve));
}
(async () => {
  assert.deepEqual(JSON.parse(JSON.stringify(await dispatch(valid))), {
    status: 200, rating: { status: "rated" },
  });
  const url = new URL(requestedUrls[0]);
  assert.equal(url.origin, "http://127.0.0.1:8000");
  assert.equal(url.pathname, "/cruise-rating");
  assert.deepEqual(Object.fromEntries(url.searchParams), {
    package_code: "LE07M870",
    ship_code: "LE",
    sailing_date_range: "Oct 3 - Oct 10",
    year: "2027",
    current_price: "1412",
  });

  assert.equal((await dispatch({ ...valid, package_code: "" })).error, "Invalid cruise identifier");
  assert.equal((await dispatch({ ...valid, year: "2027" })).error, "Invalid cruise identifier");
  assert.equal(requestedUrls.length, 1);

  await dispatch({ ...valid, url: "https://example.com/secret" });
  assert.equal(requestedUrls[1].startsWith("http://127.0.0.1:8000/cruise-rating?"), true);

  nextResponse = { status: 404, ok: false };
  assert.equal((await dispatch(valid)).status, 404);
  sandbox.fetch = async () => { throw new Error("API unavailable"); };
  assert.match((await dispatch(valid)).error, /API unavailable/);
})().catch((error) => { console.error(error); process.exitCode = 1; });
"""
    run_node(script, "service-worker.js")


def test_content_script_messages_worker_without_direct_fetch():
    script = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
let message;
let rendered;
let messageCount = 0;
const sandbox = {
  console,
  chrome: { runtime: { sendMessage: async (request) => {
    messageCount += 1;
    message = request;
    return {
      status: 200,
      rating: { status: "not_enough_history", current_price: 1510.92, message: "4 days" },
    };
  } } },
  fetch: () => { throw new Error("content script must not fetch"); },
  window: { clearTimeout() {}, setTimeout() {} },
  document: { documentElement: {}, querySelectorAll() { return []; } },
  MutationObserver: class { observe() {} },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);
vm.runInContext(`
  ensureWidget = () => ({});
  findDetailsView = () => ({});
  renderWidgetState = (state, rating) => { capturedRender = { state, rating }; };
`, sandbox);
(async () => {
  await vm.runInContext("requestRating", sandbox)({
    packageCode: "LE07M870",
    shipCode: "LE",
    sailingDateRange: "Oct 3 - Oct 10",
    year: 2027,
  }, 1412);
  assert.deepEqual(JSON.parse(JSON.stringify(message)), {
    type: "GET_CRUISE_RATING",
    package_code: "LE07M870",
    ship_code: "LE",
    sailing_date_range: "Oct 3 - Oct 10",
    year: 2027,
    current_price: 1412,
  });
  rendered = JSON.parse(JSON.stringify(sandbox.capturedRender));
  assert.equal(rendered.state, "rating");
  assert.equal(rendered.rating.current_price, 1510.92);
  await vm.runInContext("requestRating", sandbox)({
    packageCode: "LE07M870",
    shipCode: "LE",
    sailingDateRange: "Oct 3 - Oct 10",
    year: 2027,
  }, 1412);
  assert.equal(messageCount, 1);
})().catch((error) => { console.error(error); process.exitCode = 1; });
"""
    run_node(script, "content.js")


def test_content_script_only_recognizes_the_details_panel_with_date_carousel():
    script = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const sandbox = {
  console,
  chrome: { runtime: { sendMessage: async () => ({ status: 404 }) } },
  window: { clearTimeout() {}, setTimeout() {} },
  document: { documentElement: {}, querySelectorAll() { return []; } },
  MutationObserver: class { observe() {} },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);
const carousel = { closest() { return panel; } };
const panel = { contains(value) { return value === carousel; } };
sandbox.document.querySelector = (selector) => {
  if (selector === '[data-testid="room-view-panel-container"]') return panel;
  if (selector === '[data-testid="room-view-dates-carousel"]') return carousel;
  return null;
};
assert.equal(vm.runInContext("findDetailsView", sandbox)().panel, panel);
sandbox.document.querySelector = () => null;
assert.equal(vm.runInContext("findDetailsView", sandbox)(), null);
"""
    run_node(script, "content.js")


def test_content_script_extracts_tile_identifier_and_formats_rating_copy():
    script = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const sandbox = {
  console,
  chrome: { runtime: { sendMessage: async () => ({ status: 404 }) } },
  window: { clearTimeout() {}, setTimeout() {} },
  document: { documentElement: {}, querySelectorAll() { return []; } },
  MutationObserver: class { observe() {} },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);
const panel = { dataset: {}, parentElement: null };
const tile = {
  dataset: {
    packageCode: "LE07M870",
    shipCode: "LE",
    startDate: "2027-10-03",
    endDate: "2027-10-10",
  },
  textContent: "Oct 3 - Oct 10 $1,412",
  parentElement: panel,
  querySelector() { return null; },
  getAttribute() { return null; },
};
const carousel = { querySelectorAll() { return [tile]; } };
const identifier = JSON.parse(JSON.stringify(
  vm.runInContext("getIdentifierForTile", sandbox)(tile, panel, carousel)
));
assert.deepEqual(identifier, {
  packageCode: "LE07M870",
  shipCode: "LE",
  sailingDateRange: "Oct 3 - Oct 10",
  year: 2027,
});
assert.equal(vm.runInContext("visiblePrice", sandbox)(tile), 1412);
assert.equal(vm.runInContext("percentageText", sandbox)(30.25), "30.25% below average");
assert.equal(vm.runInContext("percentageText", sandbox)(-12.5), "12.50% above average");
"""
    run_node(script, "content.js")


def test_hovered_tile_range_wins_over_previously_selected_panel_dates():
    script = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const sandbox = {
  console,
  chrome: { runtime: { sendMessage: async () => ({ status: 404 }) } },
  window: { clearTimeout() {}, setTimeout() {} },
  document: { documentElement: {}, querySelectorAll() { return []; } },
  MutationObserver: class { observe() {} },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);

// The panel still contains the selected Oct 3 sailing while Oct 11 is hovered.
const panel = {
  dataset: {
    packageCode: "LE07M870",
    shipCode: "LE",
    startDate: "2027-10-03",
    endDate: "2027-10-10",
  },
  parentElement: null,
};
const yearLabel = { textContent: "2027" };
const hoveredTile = {
  dataset: {},
  textContent: "Oct 11 - Oct 18 $1,906",
  parentElement: panel,
  querySelector() { return null; },
  getAttribute() { return null; },
};
const carousel = { querySelectorAll() { return [yearLabel, hoveredTile]; } };
const identifier = JSON.parse(JSON.stringify(
  vm.runInContext("getIdentifierForTile", sandbox)(hoveredTile, panel, carousel)
));
assert.equal(identifier.sailingDateRange, "Oct 11 - Oct 18");
assert.equal(identifier.year, 2027);
assert.notEqual(identifier.sailingDateRange, "Oct 3 - Oct 10");
"""
    run_node(script, "content.js")


def test_content_script_widget_is_unique_and_toggle_collapses_and_expands():
    script = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

class FakeElement {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.style = {};
    this.attributes = {};
    this.className = "";
    this.hidden = false;
    this.listeners = {};
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  getAttribute(name) { return this.attributes[name] ?? null; }
  addEventListener(type, listener) { this.listeners[type] = listener; }
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.children.push(child); }
  replaceChildren(...children) { this.children = children; }
  remove() {}
}

const elementsById = new Map();
const body = new FakeElement("body");
body.appendChild = (child) => {
  body.children.push(child);
  if (child.id) elementsById.set(child.id, child);
};
const document = {
  documentElement: {},
  body,
  createElement(tag) { return new FakeElement(tag); },
  getElementById(id) { return elementsById.get(id) || null; },
  querySelector(selector) {
    if (selector.startsWith("#cruiseka-rating-widget ")) {
      return elementsById.get("cruiseka-rating-widget")?.children
        .find((child) => child.className === "cruiseka-rating-content") || null;
    }
    return null;
  },
  querySelectorAll() { return []; },
  addEventListener() {},
};
const sandbox = {
  console,
  chrome: { runtime: { sendMessage: async () => ({ status: 404 }) } },
  window: { clearTimeout() {}, setTimeout() {} },
  document,
  MutationObserver: class { observe() {} },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);
const ensureWidget = vm.runInContext("ensureWidget", sandbox);
const first = ensureWidget();
const second = ensureWidget();
assert.equal(first, second);
assert.equal(body.children.length, 1);

const toggle = first.children.find((child) => child.className === "cruiseka-rating-toggle");
const content = first.children.find((child) => child.className === "cruiseka-rating-content");
const event = { preventDefault() {}, stopPropagation() {} };
toggle.listeners.click(event);
assert.equal(toggle.getAttribute("aria-expanded"), "false");
assert.equal(content.hidden, true);
assert.equal(first.style.width, "28px");
toggle.listeners.click(event);
assert.equal(toggle.getAttribute("aria-expanded"), "true");
assert.equal(content.hidden, false);
assert.equal(first.style.width, "158px");
"""
    run_node(script, "content.js")


def test_content_script_delegates_dynamic_carousel_interactions():
    script = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const listeners = {};
function element(text, parent = null) {
  return {
    nodeType: 1,
    textContent: text,
    parentElement: parent,
    contains(other) {
      let current = other;
      while (current) {
        if (current === this) return true;
        current = current.parentElement;
      }
      return false;
    },
  };
}
const carousel = element("Oct 3 - Oct 10 $1,412 Oct 11 - Oct 18 $1,906");
carousel.addEventListener = (type, listener) => { listeners[type] = listener; };
const panel = {};
const wrapper = element(carousel.textContent, carousel);
const firstTile = element("Oct 3 - Oct 10 $1,412", wrapper);
const firstDate = element("Oct 3 - Oct 10", firstTile);
const firstPrice = element("$1,412", firstTile);
const secondTile = element("Oct 11 - Oct 18 $1,906", wrapper);
const secondDate = element("Oct 11 - Oct 18", secondTile);
const sandbox = {
  console,
  chrome: { runtime: { sendMessage: async () => ({ status: 404 }) } },
  window: { clearTimeout() {}, setTimeout(callback) { callback(); } },
  document: { documentElement: {}, querySelectorAll() { return []; } },
  MutationObserver: class { observe() {} },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);
vm.runInContext("interactions = []", sandbox);
vm.runInContext("showTileRating = (tile) => { interactions = [...(interactions || []), tile]; }", sandbox);
vm.runInContext("initializeCarousel", sandbox)(panel, carousel);

// Entering the first sailing triggers exactly one update.
listeners.pointerover({ target: firstDate, relatedTarget: null });
assert.equal(sandbox.interactions.length, 1);
assert.equal(sandbox.interactions[0], firstTile);

// Moving across children inside the same sailing does not retrigger it.
listeners.pointerover({ target: firstPrice, relatedTarget: firstDate });
assert.equal(sandbox.interactions.length, 1);

// Moving off the sailing into a carousel wrapper/gap keeps the last rating.
listeners.pointerover({ target: wrapper, relatedTarget: firstPrice });
assert.equal(sandbox.interactions.length, 1);

// Entering a different sailing still updates the rating.
listeners.pointerover({ target: secondDate, relatedTarget: wrapper });
assert.equal(sandbox.interactions.length, 2);
assert.equal(sandbox.interactions[1], secondTile);
"""
    run_node(script, "content.js")


def test_carousel_rerender_preserves_last_valid_sailing_without_selection():
    script = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const sandbox = {
  console,
  chrome: { runtime: { sendMessage: async () => ({ status: 404 }) } },
  window: { clearTimeout() {}, setTimeout() {} },
  document: { documentElement: {}, querySelectorAll() { return []; } },
  MutationObserver: class { observe() {} },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);

function tile(packageCode, startDate, endDate, range) {
  return {
    dataset: { packageCode, shipCode: "LE", startDate, endDate },
    textContent: range,
    parentElement: panel,
    querySelector() { return null; },
    getAttribute() { return null; },
  };
}
const panel = { dataset: {}, parentElement: null };
const carousel = { querySelectorAll() { return []; }, addEventListener() {} };
const sailingA = tile("LE07M870", "2027-09-05", "2027-09-12", "Sep 5 - Sep 12");
const sailingB = tile("LE07M870", "2027-10-03", "2027-10-10", "Oct 3 - Oct 10 $1,510.92");
const sailingC = tile("LE07M870", "2027-10-10", "2027-10-17", "Oct 10 - Oct 17 $1,612");
sailingA.textContent += " $1,585.92";

vm.runInContext(`
  requests = [];
  displayedRange = null;
  selectedCandidate = null;
  ensureWidget = () => ({});
  initializeCarousel = () => {};
  requestRating = (identifier) => {
    requests.push(identifier);
    displayedRange = identifier.sailingDateRange;
  };
  renderWidgetState = () => { throw new Error("rerender must not clear the badge"); };
`, sandbox);

const showTileRating = vm.runInContext("showTileRating", sandbox);
showTileRating(sailingA, panel, carousel);
showTileRating(sailingB, panel, carousel);
assert.equal(sandbox.displayedRange, "Oct 3 - Oct 10");
assert.equal(sandbox.requests.length, 2);

sandbox.view = { panel, carousel };
vm.runInContext("findDetailsView = () => view; selectedTile = () => selectedCandidate; latestRequest = 7", sandbox);
const syncDetailsView = vm.runInContext("syncDetailsView", sandbox);

// A rerender with no genuine selected marker preserves Sailing B.
syncDetailsView();
assert.equal(sandbox.displayedRange, "Oct 3 - Oct 10");
assert.equal(sandbox.requests.length, 2);
assert.equal(vm.runInContext("latestRequest", sandbox), 7);
assert.equal(
  JSON.parse(vm.runInContext("JSON.stringify(lastValidIdentifier)", sandbox)).sailingDateRange,
  "Oct 3 - Oct 10"
);

// A later genuine selection still changes the active sailing.
sandbox.selectedCandidate = sailingC;
syncDetailsView();
assert.equal(sandbox.displayedRange, "Oct 10 - Oct 17");
assert.equal(sandbox.requests.length, 3);

// Losing the marker again does not fall back to Sailing A.
sandbox.selectedCandidate = null;
sandbox.view = { panel, carousel: { querySelectorAll() { return []; }, addEventListener() {} } };
syncDetailsView();
assert.equal(sandbox.displayedRange, "Oct 10 - Oct 17");
assert.equal(sandbox.requests.length, 3);
"""
    run_node(script, "content.js")


def test_content_script_still_ignores_stale_rating_responses():
    script = r"""
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const pending = {};
const sandbox = {
  console,
  chrome: { runtime: { sendMessage(message) {
    return new Promise((resolve) => { pending[message.sailing_date_range] = resolve; });
  } } },
  window: { clearTimeout() {}, setTimeout() {} },
  document: { documentElement: {}, querySelectorAll() { return []; } },
  MutationObserver: class { observe() {} },
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), sandbox);
vm.runInContext(`
  ensureWidget = () => ({});
  findDetailsView = () => ({});
  renderedRatings = [];
  renderWidgetState = (state, rating) => {
    if (state === "rating") renderedRatings.push(rating.current_price);
  };
`, sandbox);
const requestRating = vm.runInContext("requestRating", sandbox);
const base = { packageCode: "LE07M870", shipCode: "LE", year: 2027 };
(async () => {
  const first = requestRating({ ...base, sailingDateRange: "Sep 5 - Sep 12" }, 1585.92);
  const second = requestRating({ ...base, sailingDateRange: "Oct 3 - Oct 10" }, 1510.92);
  pending["Oct 3 - Oct 10"]({ status: 200, rating: { status: "rated", current_price: 1510.92 } });
  await second;
  pending["Sep 5 - Sep 12"]({ status: 200, rating: { status: "rated", current_price: 1585.92 } });
  await first;
  assert.deepEqual(Array.from(sandbox.renderedRatings), [1510.92]);
})().catch((error) => { console.error(error); process.exitCode = 1; });
"""
    run_node(script, "content.js")


def test_manifest_registers_worker_with_only_local_api_host_permission():
    manifest = json.loads((EXTENSION / "manifest.json").read_text())

    assert manifest["manifest_version"] == 3
    assert manifest["background"] == {"service_worker": "service-worker.js"}
    assert manifest["host_permissions"] == ["http://127.0.0.1:8000/*"]
    assert "permissions" not in manifest
