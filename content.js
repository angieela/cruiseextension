const API_URL = "http://127.0.0.1:8000/cruise-rating";
const CARD_SELECTOR = '[data-testid="itinerary-card"]';
const BADGE_CLASS = "cruise-price-rating-badge";
const DATE_PARTS_CLASS = "cruise-embarkation-date-parts";

let apiWarningShown = false;

function formatDatePart(date) {
  return `${date.toLocaleString("en-US", { month: "short" })} ${date.getDate()}`;
}

function getSailingIdentifier(card) {
  const packageCode = card.dataset.packageCode;
  const shipCode = card.dataset.shipCode;
  const startDateText = card.dataset.startDate || card.dataset.sailDate;
  const endDateText = card.dataset.endDate;

  if (!packageCode || !shipCode || !startDateText || !endDateText) {
    return null;
  }

  const startDate = new Date(`${startDateText}T00:00:00`);
  const endDate = new Date(`${endDateText}T00:00:00`);
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
    return null;
  }

  return {
    packageCode,
    shipCode,
    year: startDate.getFullYear(),
    sailingDateRange: `${formatDatePart(startDate)} - ${formatDatePart(endDate)}`,
  };
}

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
  return {
    year: String(identifier.year),
    month,
    day,
  };
}

function applyCruiseCardStyle(element) {
  Object.assign(element.style, {
    background: "#ffffff",
    border: "1px solid #d7dce3",
    borderRadius: "10px",
    boxShadow: "0 2px 8px rgba(0, 32, 91, 0.12)",
    color: "#00205b",
    fontSize: "13px",
    fontWeight: "700",
    lineHeight: "1.25",
    padding: "6px 10px",
  });
}

function addEmbarkationDateCards(card) {
  if (card.querySelector(`.${DATE_PARTS_CLASS}`)) {
    return;
  }

  const dateParts = getEmbarkationDateParts(card);
  if (!dateParts) {
    return;
  }

  const container = document.createElement("div");
  container.className = DATE_PARTS_CLASS;
  container.setAttribute("aria-label", "Cruise embarkation date");
  Object.assign(container.style, {
    display: "flex",
    flexWrap: "wrap",
    gap: "6px",
    marginBottom: "8px",
  });

  Object.entries(dateParts).forEach(([label, value]) => {
    const dateCard = document.createElement("div");
    dateCard.className = `cruise-embarkation-${label}-card`;
    dateCard.setAttribute("role", "group");
    dateCard.setAttribute("aria-label", `Embarkation ${label}: ${value}`);
    dateCard.textContent = `START ${label.toUpperCase()} ${value}`;
    applyCruiseCardStyle(dateCard);
    container.appendChild(dateCard);
  });

  const datesButton = card.querySelector('[data-testid="view-sailings-button"]');
  const insertionPoint = datesButton?.parentElement || card;
  insertionPoint.insertBefore(container, datesButton || insertionPoint.firstChild);
}

function addBadge(card, rating) {
  if (card.querySelector(`.${BADGE_CLASS}`)) {
    return;
  }

  const badge = document.createElement("div");
  badge.className = BADGE_CLASS;
  badge.setAttribute("role", "status");

  if (rating.status === "rated") {
    badge.textContent = `${rating.emoji} ${rating.signed_percentage} ${rating.label}`;
  } else {
    badge.textContent = `⏳ ${rating.message}`;
  }

  applyCruiseCardStyle(badge);
  Object.assign(badge.style, {
    alignSelf: "flex-start",
    borderRadius: "999px",
    marginBottom: "8px",
  });

  const datesButton = card.querySelector('[data-testid="view-sailings-button"]');
  const insertionPoint = datesButton?.parentElement || card;
  insertionPoint.insertBefore(badge, datesButton || insertionPoint.firstChild);
}

async function processCard(card) {
  if (card.dataset.cruiseRatingProcessed === "true") {
    return;
  }
  card.dataset.cruiseRatingProcessed = "true";

  const identifier = getSailingIdentifier(card);
  if (!identifier) {
    return;
  }
  addEmbarkationDateCards(card);

  const query = new URLSearchParams({
    package_code: identifier.packageCode,
    ship_code: identifier.shipCode,
    sailing_date_range: identifier.sailingDateRange,
    year: String(identifier.year),
  });

  try {
    const response = await fetch(`${API_URL}?${query}`);
    if (response.status === 404) {
      return;
    }
    if (!response.ok) {
      throw new Error(`Rating API returned ${response.status}`);
    }

    addBadge(card, await response.json());
  } catch (error) {
    if (!apiWarningShown) {
      console.warn("Cruise price ratings are unavailable. Is the local API running?", error);
      apiWarningShown = true;
    }
  }
}

function processCruiseCards() {
  document.querySelectorAll(CARD_SELECTOR).forEach(processCard);
}

let processTimer;
const observer = new MutationObserver(() => {
  window.clearTimeout(processTimer);
  processTimer = window.setTimeout(processCruiseCards, 250);
});

observer.observe(document.documentElement, { childList: true, subtree: true });
processCruiseCards();
