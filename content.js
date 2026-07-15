function getCruiseData(card) {
    const titleElement = card.querySelector("h2");
    const dateElement = card.querySelector(".date");
    const priceElement = card.querySelector(".price");

    function parsePrice(priceText) {
        return Number(priceText.replace("$", "").replace(",", ""))
    }
    const title = titleElement ? titleElement.innerText : "No title found";
    const date = dateElement ? dateElement.innerText : "No date found";
    const priceText = priceElement ? priceElement.innerText : "No price found";
    const price = priceText !== "No price found" ? parsePrice(priceText) : null;
    return {
      title: title,
      date: date,
      priceText: priceText,
      price: price
    };
  }
  
  function addBadge(card, label) {
    if (card.querySelector(".deal-badge")) {
      return;
    }
  
    const badge = document.createElement("div");
    badge.className = "deal-badge";
    badge.textContent = label;
  
    badge.style.position = "absolute";
    badge.style.top = "10px";
    badge.style.right = "10px";
    badge.style.backgroundColor = "#e6f7e6";
    badge.style.color = "#0b7a0b";
    badge.style.border = "2px solid #0b7a0b";
    badge.style.borderRadius = "999px";
    badge.style.padding = "6px 10px";
    badge.style.fontSize = "14px";
    badge.style.fontWeight = "bold";
    badge.style.zIndex = "999999";
  
    card.style.position = "relative";
    card.appendChild(badge);
  }
  
  function processCruiseCards() {
    const cards = document.querySelectorAll(".cruise-card");
  
    cards.forEach((card) => {
      const cruise = getCruiseData(card);
  
      console.log("Cruise data:", cruise);
  
      if (cruise.price < 1000){
        addBadge(card, "🟢 Great Deal");
      } else {
        addBadge(card, "🔴 Expensive")
      }
    })
  }
  
  processCruiseCards();
