const CARD_SELECTOR = '[id^="cruise-card_"]';
const DETAILS_PANEL_SELECTOR = '[data-testid="room-view-panel-container"]';
const DATES_CAROUSEL_SELECTOR = '[data-testid="room-view-dates-carousel"]';
const WIDGET_ID = "cruiseka-rating-widget";
const DATE_RANGE_PATTERN = /([A-Z][a-z]{2})\s+(\d{1,2})\s*[-–]\s*([A-Z][a-z]{2})\s+(\d{1,2})/;
const PRICE_PATTERN = /\$\s*([\d,]+(?:\.\d{1,2})?)/;
const ISO_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})(?:$|[T ])/;
const MONTH_NAMES = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];
const EXPANDED_WIDGET_STYLE = {
  width: "158px",
  minHeight: "112px",
  padding: "18px 12px 12px",
  borderRadius: "12px",
};
const COLLAPSED_WIDGET_STYLE = {
  width: "28px",
  minHeight: "22px",
  padding: "0",
  borderRadius: "999px",
};

let apiWarningShown = false;
let lastSourceCard = null;
let activePanel = null;
let activeCarousel = null;
let latestRequest = 0;
let currentIdentifierKey = null;
let lastValidIdentifier = null;
let lastSelectedIdentifierKey = null;
let hoverTimer = null;
let syncTimer = null;

const initializedCarousels = new WeakSet();
const ratingCache = new Map();

function parseCalendarDate(value) {
  if (typeof value !== "string") {
    return null;
  }
  const match = value.trim().match(ISO_DATE_PATTERN);
  if (!match) {
    return null;
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const validationDate = new Date(Date.UTC(year, month - 1, day));
  if (validationDate.getUTCFullYear() !== year
      || validationDate.getUTCMonth() !== month - 1
      || validationDate.getUTCDate() !== day) {
    return null;
  }

  return {
    iso: `${match[1]}-${match[2]}-${match[3]}`,
    year,
    month,
    day,
  };
}

function formatDatePart(calendarDate) {
  return `${MONTH_NAMES[calendarDate.month - 1]} ${calendarDate.day}`;
}

function getSailingIdentifier(card) {
  const packageCode = card.dataset.packageCode;
  const shipCode = card.dataset.shipCode;
  const startDateText = card.dataset.startDate || card.dataset.sailDate;
  const endDateText = card.dataset.endDate;

  if (!packageCode || !shipCode || !startDateText || !endDateText) {
    return null;
  }

  const startDate = parseCalendarDate(startDateText);
  const endDate = parseCalendarDate(endDateText);
  if (!startDate || !endDate) {
    return null;
  }

  return {
    packageCode,
    shipCode,
    year: startDate.year,
    sailingDateRange: `${formatDatePart(startDate)} - ${formatDatePart(endDate)}`,
  };
}

// Kept as a reusable parser for identifier-consistency tests and other callers.
function getEmbarkationDateParts(card) {
  const identifier = getSailingIdentifier(card);
  if (!identifier) {
    return null;
  }
  const rangeMatch = identifier.sailingDateRange.match(
    /^([A-Z][a-z]{2}) (\d{1,2}) - [A-Z][a-z]{2} \d{1,2}$/
  );
  if (!rangeMatch) {
    return null;
  }
  const [, month, day] = rangeMatch;
  return { year: String(identifier.year), month, day };
}

function findDetailsView() {
  if (typeof document.querySelector !== "function") {
    return null;
  }
  const carousel = document.querySelector(DATES_CAROUSEL_SELECTOR);
  const panel = carousel?.closest?.(DETAILS_PANEL_SELECTOR)
    || document.querySelector(DETAILS_PANEL_SELECTOR);
  if (!panel || !carousel || !panel.contains(carousel)) {
    return null;
  }
  return { panel, carousel };
}

function normalizeIsoDate(value) {
  return parseCalendarDate(value)?.iso || null;
}

function readData(element, names) {
  for (const name of names) {
    const value = element?.dataset?.[name];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return null;
}

function urlsFromElement(element) {
  const values = [
    element?.href,
    element?.getAttribute?.("href"),
    readData(element, ["productViewLink", "href"]),
    element?.querySelector?.('a[href*="sail"]')?.href,
  ].filter(Boolean);

  return values.flatMap((value) => {
    try {
      return [new URL(value, globalThis.location?.href || "https://www.royalcaribbean.com/")];
    } catch (_error) {
      return [];
    }
  });
}

function elementSources(tile, panel) {
  const sources = [];
  let current = tile;
  while (current && current !== panel) {
    sources.push(current);
    current = current.parentElement;
  }
  if (panel) {
    sources.push(panel);
  }
  const nestedMetadata = tile?.querySelector?.(
    "[data-package-code], [data-sail-date], [data-start-date]"
  );
  if (nestedMetadata) {
    sources.unshift(nestedMetadata);
  }
  return sources;
}

function firstData(sources, names) {
  for (const source of sources) {
    const value = readData(source, names);
    if (value) {
      return value;
    }
  }
  return null;
}

function firstUrlParameter(sources, names) {
  for (const source of sources) {
    for (const url of urlsFromElement(source)) {
      for (const name of names) {
        const value = url.searchParams.get(name);
        if (value) {
          return value;
        }
      }
    }
  }
  return null;
}

function visibleDateRange(element) {
  return visibleDateRanges(element)[0] || null;
}

function visiblePrice(element) {
  const match = element?.textContent?.match(PRICE_PATTERN);
  if (!match) {
    return null;
  }
  const price = Number(match[1].replaceAll(",", ""));
  return Number.isFinite(price) ? price : null;
}

function visibleDateRanges(element) {
  const text = element?.textContent || "";
  const matches = text.matchAll(new RegExp(DATE_RANGE_PATTERN.source, "g"));
  const ranges = new Set();
  for (const match of matches) {
    ranges.add(`${match[1]} ${Number(match[2])} - ${match[3]} ${Number(match[4])}`);
  }
  return Array.from(ranges);
}

function yearNearTile(tile, carousel) {
  const ownTextYear = tile?.textContent?.match(/\b(20\d{2})\b/);
  if (ownTextYear) {
    return Number(ownTextYear[1]);
  }

  const elements = Array.from(carousel?.querySelectorAll?.("*") || []);
  const tileIndex = elements.indexOf(tile);
  for (let index = tileIndex - 1; index >= 0 && index >= tileIndex - 80; index -= 1) {
    const text = elements[index]?.textContent?.trim();
    const match = text?.match(/^(20\d{2})$/);
    if (match) {
      return Number(match[1]);
    }
  }
  return null;
}

function sourceCardIdentifierForRange(range) {
  if (!lastSourceCard) {
    return null;
  }
  const identifier = getSailingIdentifier(lastSourceCard);
  return identifier?.sailingDateRange === range ? identifier : null;
}

function documentIdentifierForRange(range, year) {
  const candidates = Array.from(document.querySelectorAll?.("[data-package-code]") || []);
  for (const candidate of candidates) {
    const identifier = getSailingIdentifier(candidate);
    if (identifier?.sailingDateRange === range
      && (!year || identifier.year === year)) {
      return identifier;
    }
  }
  return null;
}

function getIdentifierForTile(tile, panel, carousel) {
  if (!tile) {
    return null;
  }

  const sources = elementSources(tile, panel);
  let packageCode = firstData(sources, ["packageCode"])
    || firstUrlParameter(sources, ["packageCode", "package-code"]);
  let shipCode = firstData(sources, ["shipCode"]);
  const startDateText = normalizeIsoDate(
    firstData(sources, ["startDate", "sailDate"])
      || firstUrlParameter(sources, ["sail-date", "sailDate"])
  );
  const endDateText = normalizeIsoDate(firstData(sources, ["endDate"]));

  // The tile's visible range/year describe the sailing being hovered. Ancestor
  // metadata can still describe the previously selected sailing until RCL rerenders.
  let sailingDateRange = visibleDateRange(tile);
  let year = yearNearTile(tile, carousel)
    || (startDateText ? Number(startDateText.slice(0, 4)) : null);

  if (startDateText && endDateText) {
    const parsed = getSailingIdentifier({
      dataset: {
        packageCode: packageCode || "placeholder",
        shipCode: shipCode || "XX",
        startDate: startDateText,
        endDate: endDateText,
      },
    });
    sailingDateRange ||= parsed?.sailingDateRange;
  }

  const sourceIdentifier = documentIdentifierForRange(sailingDateRange, year)
    || sourceCardIdentifierForRange(sailingDateRange);
  if (sourceIdentifier) {
    packageCode = sourceIdentifier.packageCode;
    shipCode = sourceIdentifier.shipCode;
    year = sourceIdentifier.year;
  }

  // Royal Caribbean ship codes are the leading two letters of package codes.
  if (!shipCode && /^[A-Za-z]{2}/.test(packageCode || "")) {
    shipCode = packageCode.slice(0, 2).toUpperCase();
  }

  if (!packageCode || !shipCode || !sailingDateRange || !Number.isInteger(year)) {
    return null;
  }

  return { packageCode, shipCode, sailingDateRange, year };
}

function sailingTiles(carousel) {
  // Some Royal Caribbean builds render date tiles as buttons; others use divs.
  // Select the smallest date-range-bearing element rather than a generated class.
  const candidates = Array.from(carousel.querySelectorAll("*"));
  return candidates.filter((element, index) => (
    visibleDateRange(element)
    && !candidates.some((other, otherIndex) => (
      otherIndex !== index && element.contains(other) && visibleDateRange(other)
    ))
  ));
}

function tileFromTarget(target, carousel) {
  let element = target?.nodeType === 1 ? target : target?.parentElement;
  let tile = null;
  while (element && element !== carousel) {
    const ranges = visibleDateRanges(element);
    if (ranges.length === 1) {
      // Keep walking to return the complete tile instead of one of its children.
      tile = element;
    } else if (tile && ranges.length > 1) {
      break;
    }
    element = element.parentElement;
  }
  return tile;
}

function selectedTile(carousel) {
  const semantic = carousel.querySelector(
    '[aria-selected="true"], [aria-pressed="true"], [data-selected="true"], [data-active="true"]'
  );
  if (semantic && visibleDateRange(semantic)) {
    return semantic;
  }

  const selectedClass = carousel.querySelector('[class*="selected" i], [class*="active" i]');
  if (selectedClass && visibleDateRange(selectedClass)) {
    return selectedClass;
  }

  const tiles = sailingTiles(carousel);
  if (lastSourceCard) {
    const sourceRange = getSailingIdentifier(lastSourceCard)?.sailingDateRange;
    const matchingTile = tiles.find((tile) => visibleDateRange(tile) === sourceRange);
    if (matchingTile) {
      return matchingTile;
    }
  }
  return null;
}

function createTextElement(className, text) {
  const element = document.createElement("div");
  element.className = className;
  element.textContent = text;
  return element;
}

function ensureWidget() {
  let widget = document.getElementById(WIDGET_ID);
  if (widget) {
    return widget;
  }

  widget = document.createElement("aside");
  widget.id = WIDGET_ID;
  widget.setAttribute("aria-label", "CruiseKa price rating");
  Object.assign(widget.style, {
    position: "fixed",
    top: "88px",
    right: "24px",
    boxSizing: "border-box",
    background: "#e7fbf8",
    border: "1px solid #172033",
    boxShadow: "0 4px 14px rgba(0, 32, 91, 0.16)",
    color: "#172033",
    fontFamily: "Arial, sans-serif",
    fontSize: "13px",
    lineHeight: "1.3",
    textAlign: "center",
    zIndex: "2147483646",
  }, EXPANDED_WIDGET_STYLE);

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "cruiseka-rating-toggle";
  toggle.textContent = "−";
  toggle.setAttribute("aria-expanded", "true");
  toggle.setAttribute("aria-label", "Collapse CruiseKa rating");
  Object.assign(toggle.style, {
    position: "absolute",
    top: "-1px",
    right: "-1px",
    width: "28px",
    height: "22px",
    padding: "0",
    border: "1px solid #172033",
    borderRadius: "999px",
    background: "#ffffff",
    color: "#172033",
    cursor: "pointer",
    fontSize: "16px",
    lineHeight: "18px",
  });

  const content = document.createElement("div");
  content.className = "cruiseka-rating-content";
  content.setAttribute("role", "status");
  content.setAttribute("aria-live", "polite");

  toggle.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    const expanded = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!expanded));
    toggle.setAttribute(
      "aria-label",
      expanded ? "Expand CruiseKa rating" : "Collapse CruiseKa rating"
    );
    toggle.textContent = expanded ? "+" : "−";
    content.hidden = expanded;
    Object.assign(widget.style, expanded
      ? COLLAPSED_WIDGET_STYLE
      : EXPANDED_WIDGET_STYLE);
  });

  widget.append(toggle, content);
  document.body.appendChild(widget);
  renderWidgetState("loading");
  return widget;
}

function widgetContent() {
  return document.querySelector(`#${WIDGET_ID} .cruiseka-rating-content`);
}

function replaceWidgetContent(...elements) {
  const content = widgetContent();
  if (content) {
    content.replaceChildren(...elements);
  }
}

function formatPrice(price) {
  if (typeof price !== "number" || !Number.isFinite(price)) {
    return "N/A";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: Number.isInteger(price) ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(price);
}

function percentageText(discountPercent) {
  const value = Number(discountPercent);
  if (!Number.isFinite(value) || Math.abs(value) < 0.005) {
    return "At historical average";
  }
  const direction = value > 0 ? "below" : "above";
  return `${Math.abs(value).toFixed(2)}% ${direction} average`;
}

function renderWidgetMessage(message, showTitle = false) {
  const elements = [];
  if (showTitle) {
    elements.push(createTextElement("cruiseka-rating-title", "CruiseKa"));
  }
  elements.push(createTextElement("cruiseka-rating-status", message));
  replaceWidgetContent(...elements);
}

function renderWidgetState(state, rating = null) {
  if (state === "loading") {
    renderWidgetMessage("Loading CruiseKa rating…");
    return;
  }
  if (state === "missing") {
    renderWidgetMessage("No price history yet", true);
    return;
  }
  if (state === "unavailable") {
    renderWidgetMessage("Rating unavailable", true);
    return;
  }

  const price = createTextElement(
    "cruiseka-rating-price",
    `Current: ${formatPrice(rating.current_price)}`
  );
  price.style.marginBottom = "10px";

  if (rating.status === "rated") {
    const comparison = createTextElement(
      "cruiseka-rating-comparison",
      percentageText(rating.discount_percent)
    );
    const label = createTextElement(
      "cruiseka-rating-label",
      `${rating.emoji || ""} ${rating.label || ""}`.trim()
    );
    label.style.fontWeight = "700";
    replaceWidgetContent(price, comparison, label);
    return;
  }

  const collecting = createTextElement("cruiseka-rating-label", "Collecting history");
  collecting.style.fontWeight = "700";
  const remaining = createTextElement(
    "cruiseka-rating-status",
    rating.message || "More daily prices are needed"
  );
  remaining.style.fontSize = "11px";
  replaceWidgetContent(price, collecting, remaining);
}

function identifierKey(identifier) {
  return [identifier.packageCode, identifier.shipCode, identifier.year, identifier.sailingDateRange].join("|");
}

async function requestRating(identifier, currentPrice) {
  const key = `${identifierKey(identifier)}|${currentPrice}`;
  if (key === currentIdentifierKey) {
    return;
  }
  currentIdentifierKey = key;
  const requestNumber = ++latestRequest;
  ensureWidget();

  if (ratingCache.has(key)) {
    renderWidgetState("rating", ratingCache.get(key));
    return;
  }

  renderWidgetState("loading");
  const message = {
    type: "GET_CRUISE_RATING",
    package_code: identifier.packageCode,
    ship_code: identifier.shipCode,
    sailing_date_range: identifier.sailingDateRange,
    year: identifier.year,
    current_price: currentPrice,
  };

  try {
    const response = await chrome.runtime.sendMessage(message);
    if (requestNumber !== latestRequest || !findDetailsView()) {
      return;
    }
    if (response?.status === 404) {
      renderWidgetState("missing");
      return;
    }
    if (response?.error) {
      throw new Error(response.error);
    }
    if (response?.status !== 200 || !response.rating) {
      throw new Error(`Rating API returned ${response?.status ?? "no response"}`);
    }
    ratingCache.set(key, response.rating);
    renderWidgetState("rating", response.rating);
  } catch (error) {
    if (requestNumber !== latestRequest) {
      return;
    }
    renderWidgetState("unavailable");
    if (!apiWarningShown) {
      console.warn("Cruise price ratings are unavailable. Is the local API running?", error);
      apiWarningShown = true;
    }
  }
}

function showTileRating(tile, panel = activePanel, carousel = activeCarousel) {
  const currentPrice = visiblePrice(tile);
  const identifier = getIdentifierForTile(tile, panel, carousel);
  ensureWidget();
  if (!identifier) {
    latestRequest += 1;
    currentIdentifierKey = null;
    renderWidgetState("unavailable");
    return;
  }
  if (currentPrice === null) {
    latestRequest += 1;
    currentIdentifierKey = null;
    renderWidgetState("unavailable");
    return;
  }
  lastValidIdentifier = { ...identifier };
  requestRating(identifier, currentPrice);
}

function initializeCarousel(panel, carousel) {
  if (initializedCarousels.has(carousel)) {
    return;
  }
  initializedCarousels.add(carousel);

  carousel.addEventListener("click", (event) => {
    const tile = tileFromTarget(event.target, carousel);
    if (tile) {
      window.setTimeout(() => showTileRating(tile, panel, carousel), 50);
    }
  });
  carousel.addEventListener("focusin", (event) => {
    const tile = tileFromTarget(event.target, carousel);
    if (tile) {
      showTileRating(tile, panel, carousel);
    }
  });
  carousel.addEventListener("pointerover", (event) => {
    const tile = tileFromTarget(event.target, carousel);
    if (!tile || tile.contains(event.relatedTarget)) {
      return;
    }
    window.clearTimeout(hoverTimer);
    hoverTimer = window.setTimeout(() => showTileRating(tile, panel, carousel), 125);
  });
}

function removeWidget() {
  document.getElementById?.(WIDGET_ID)?.remove();
  latestRequest += 1;
  currentIdentifierKey = null;
  lastValidIdentifier = null;
  lastSelectedIdentifierKey = null;
  activePanel = null;
  activeCarousel = null;
}

function syncDetailsView() {
  const view = findDetailsView();
  if (!view) {
    removeWidget();
    return;
  }
  const changedView = view.panel !== activePanel || view.carousel !== activeCarousel;
  activePanel = view.panel;
  activeCarousel = view.carousel;
  ensureWidget();
  initializeCarousel(view.panel, view.carousel);

  const tile = selectedTile(view.carousel);
  if (tile) {
    const identifier = getIdentifierForTile(tile, view.panel, view.carousel);
    if (identifier) {
      const selectedKey = identifierKey(identifier);
      if (selectedKey !== lastSelectedIdentifierKey) {
        lastSelectedIdentifierKey = selectedKey;
        showTileRating(tile, view.panel, view.carousel);
      }
    }
  } else if (changedView && !lastValidIdentifier) {
    renderWidgetState("unavailable");
  }
}

document.addEventListener?.("click", (event) => {
  const card = event.target?.closest?.(CARD_SELECTOR);
  if (card) {
    lastSourceCard = card;
  }
}, true);

const observer = new MutationObserver(() => {
  window.clearTimeout(syncTimer);
  syncTimer = window.setTimeout(syncDetailsView, 100);
});
observer.observe(document.documentElement, {
  childList: true,
  subtree: true,
  attributes: true,
  attributeFilter: ["aria-selected", "aria-pressed", "data-selected", "data-active", "class"],
});
syncDetailsView();
