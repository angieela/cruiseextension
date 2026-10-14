const API_URL = "http://127.0.0.1:8000/cruise-rating";

function cruiseRatingValidationErrors(message) {
  const errors = [];
  if (message?.type !== "GET_CRUISE_RATING") errors.push("message type");
  if (typeof message?.package_code !== "string"
      || !/^[A-Za-z0-9-]{1,100}$/.test(message.package_code)) {
    errors.push("package_code");
  }
  if (typeof message?.ship_code !== "string"
      || !/^[A-Za-z0-9-]{1,20}$/.test(message.ship_code)) {
    errors.push("ship_code");
  }
  if (typeof message?.sailing_date_range !== "string"
      || !/^[A-Z][a-z]{2} (?:[1-9]|[12]\d|3[01]) - [A-Z][a-z]{2} (?:[1-9]|[12]\d|3[01])$/.test(message.sailing_date_range)) {
    errors.push("sailing_date_range");
  }
  if (!Number.isInteger(message?.year) || message.year < 1900 || message.year > 2100) {
    errors.push("year");
  }
  return errors;
}

function validCruiseRatingMessage(message) {
  return cruiseRatingValidationErrors(message).length === 0;
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "GET_CRUISE_RATING") {
    return false;
  }
  const validationErrors = cruiseRatingValidationErrors(message);
  if (validationErrors.length) {
    sendResponse({ error: "Invalid cruise identifier" });
    return false;
  }

  const query = new URLSearchParams({
    package_code: message.package_code,
    ship_code: message.ship_code,
    sailing_date_range: message.sailing_date_range,
    year: String(message.year),
  });

  const requestUrl = `${API_URL}?${query}`;
  fetch(requestUrl)
    .then(async (response) => ({
      status: response.status,
      rating: response.ok ? await response.json() : null,
    }))
    .then(sendResponse)
    .catch((error) => sendResponse({ error: String(error) }));

  return true;
});
