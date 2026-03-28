const DEFAULT_CENTER = [20.5937, 78.9629];
const DEFAULT_ZOOM = 5;

const map = L.map("map").setView(DEFAULT_CENTER, DEFAULT_ZOOM);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const form = document.getElementById("itemForm");
const formMessage = document.getElementById("formMessage");
const authMessage = document.getElementById("authMessage");
const latitudeInput = document.getElementById("latitudeInput");
const longitudeInput = document.getElementById("longitudeInput");
const useMyLocationBtn = document.getElementById("useMyLocationBtn");
const imageInput = document.getElementById("imageInput");

const authForm = document.getElementById("authForm");
const registerForm = document.getElementById("registerForm");
const loginBtn = document.getElementById("loginBtn");
const registerBtn = document.getElementById("registerBtn");
const logoutBtn = document.getElementById("logoutBtn");
const userBadge = document.getElementById("userBadge");

const filterType = document.getElementById("filterType");
const filterCategory = document.getElementById("filterCategory");
const filterRadius = document.getElementById("filterRadius");
const filterLat = document.getElementById("filterLat");
const filterLon = document.getElementById("filterLon");
const searchText = document.getElementById("searchText");
const searchBtn = document.getElementById("searchBtn");
const loadAllBtn = document.getElementById("loadAllBtn");

const itemsList = document.getElementById("itemsList");
const itemCount = document.getElementById("itemCount");
const itemCardTemplate = document.getElementById("itemCardTemplate");

let draftPin = null;
let selectedPoint = null;
const itemMarkersLayer = L.layerGroup().addTo(map);
const itemsById = new Map();
let sessionToken = localStorage.getItem("lostfound_session_token") || "";
let currentUser = null;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setFormMessage(message, isError = false) {
  formMessage.textContent = message;
  formMessage.classList.toggle("error", isError);
  formMessage.classList.toggle("success", !isError && Boolean(message));
}

function setAuthMessage(message, isError = false) {
  authMessage.textContent = message;
  authMessage.classList.toggle("error", isError);
  authMessage.classList.toggle("success", !isError && Boolean(message));
}

function setLoggedInState(user, token) {
  currentUser = user;
  if (token) {
    sessionToken = token;
    localStorage.setItem("lostfound_session_token", token);
  }
  loginBtn.disabled = true;
  registerBtn.disabled = true;
  logoutBtn.disabled = false;
  userBadge.textContent = `Logged in: ${user.name} (${user.email})`;
}

function setLoggedOutState() {
  currentUser = null;
  sessionToken = "";
  localStorage.removeItem("lostfound_session_token");
  loginBtn.disabled = false;
  registerBtn.disabled = false;
  logoutBtn.disabled = true;
  userBadge.textContent = "Not logged in";
}

async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (sessionToken) {
    headers.set("Authorization", `Bearer ${sessionToken}`);
  }
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(url, {
    ...options,
    headers,
  });
  return response;
}

function setSelectedPoint(lat, lon, source) {
  const normalizedLat = Number(lat);
  const normalizedLon = Number(lon);

  if (Number.isNaN(normalizedLat) || Number.isNaN(normalizedLon)) {
    return;
  }

  selectedPoint = { lat: normalizedLat, lon: normalizedLon };
  latitudeInput.value = normalizedLat.toFixed(6);
  longitudeInput.value = normalizedLon.toFixed(6);
  filterLat.value = normalizedLat.toFixed(6);
  filterLon.value = normalizedLon.toFixed(6);

  if (!draftPin) {
    draftPin = L.marker([normalizedLat, normalizedLon]).addTo(map);
  } else {
    draftPin.setLatLng([normalizedLat, normalizedLon]);
  }

  setFormMessage(`Location selected from ${source}.`, false);
}

function markerColorByType(itemType) {
  return itemType === "lost" ? "#ef4444" : "#16a34a";
}

function addItemMarker(item) {
  const marker = L.circleMarker([item.latitude, item.longitude], {
    radius: 8,
    color: markerColorByType(item.item_type),
    fillColor: markerColorByType(item.item_type),
    fillOpacity: 0.9,
    weight: 2,
  }).addTo(itemMarkersLayer);

  marker.bindPopup(
    `<strong>${escapeHtml(item.title)}</strong><br>` +
      `${escapeHtml(item.item_type.toUpperCase())} · ${escapeHtml(item.category)}<br>` +
      `${escapeHtml(item.location_label || "Pinned map location")}<br>` +
      `Contact: ${escapeHtml(item.contact_name)} (${escapeHtml(item.contact_phone)})`
  );
}

function createItemCard(item) {
  const fragment = itemCardTemplate.content.cloneNode(true);
  const card = fragment.querySelector(".item-card");
  card.dataset.itemId = String(item.id);

  const titleEl = fragment.querySelector(".item-title");
  const metaEl = fragment.querySelector(".item-meta");
  const badgeEl = fragment.querySelector(".item-badge");
  const descriptionEl = fragment.querySelector(".item-description");
  const contactEl = fragment.querySelector(".item-contact");
  const locationEl = fragment.querySelector(".item-location");
  const imageEl = fragment.querySelector(".item-image");
  const contactButtonsEl = fragment.querySelector(".contact-buttons");
  const whatsappEl = fragment.querySelector(".whatsapp-btn");
  const emailEl = fragment.querySelector(".email-btn");
  const matchesContainer = fragment.querySelector(".matches-container");

  titleEl.textContent = item.title;
  metaEl.textContent = `${item.category} · Reported ${item.created_at}`;
  badgeEl.textContent = item.item_type.toUpperCase();
  badgeEl.classList.add(item.item_type);
  descriptionEl.textContent = item.description;
  contactEl.textContent = `Contact: ${item.contact_name} (${item.contact_phone})`;
  locationEl.textContent = `Location: ${item.location_label || `${item.latitude.toFixed(5)}, ${item.longitude.toFixed(5)}`}`;
  const imageUrl = item.image_url || "";
  if (imageUrl) {
    imageEl.src = imageUrl;
    imageEl.alt = item.title;
    imageEl.hidden = false;
  }

  const phoneDigits = String(item.contact_phone || "").replace(/\D/g, "");
  if (phoneDigits) {
    const textMessage = encodeURIComponent(
      `Hi ${item.contact_name}, I am contacting you about "${item.title}" on Lost & Found Connect.`
    );
    whatsappEl.href = `https://wa.me/${phoneDigits}?text=${textMessage}`;
  } else {
    whatsappEl.hidden = true;
  }
  if (item.owner_email) {
    const subject = encodeURIComponent(`Regarding "${item.title}" (${item.item_type})`);
    const body = encodeURIComponent(
      `Hello ${item.contact_name},%0D%0A%0D%0AI am reaching out about your item listing: "${item.title}".`
    );
    emailEl.href = `mailto:${item.owner_email}?subject=${subject}&body=${body}`;
  } else {
    emailEl.hidden = true;
  }
  if (whatsappEl.hidden && emailEl.hidden) {
    contactButtonsEl.hidden = true;
  }

  const showMapBtn = fragment.querySelector(".show-on-map-btn");
  showMapBtn.addEventListener("click", () => {
    map.setView([item.latitude, item.longitude], 15);
  });

  const findMatchesBtn = fragment.querySelector(".find-matches-btn");
  findMatchesBtn.addEventListener("click", async () => {
    findMatchesBtn.disabled = true;
    findMatchesBtn.textContent = "Finding...";
    try {
      const radius = Number(filterRadius.value) || 10;
      const response = await fetch(
        `/api/items/${item.id}/matches?distance_km=${encodeURIComponent(radius)}&time_days=30`
      );
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Could not load matches");
      }

      if (!payload.matches.length) {
        matchesContainer.innerHTML = `<p class="match-empty">No matches found within ${radius} km.</p>`;
        return;
      }

      const listHtml = payload.matches
        .map(
          (match) => `
          <div class="match-row">
            <strong>${escapeHtml(match.title)}</strong>
            <span>${escapeHtml(match.item_type.toUpperCase())}</span>
            <span>${Number(match.distance_km).toFixed(2)} km away</span>
            <span>${escapeHtml(match.contact_name)} (${escapeHtml(match.contact_phone)})</span>
          </div>
        `
        )
        .join("");
      matchesContainer.innerHTML = `<h4>Nearby possible matches</h4>${listHtml}`;
    } catch (error) {
      matchesContainer.innerHTML = `<p class="match-empty error">${escapeHtml(error.message)}</p>`;
    } finally {
      findMatchesBtn.disabled = false;
      findMatchesBtn.textContent = "Find matches nearby";
    }
  });

  return fragment;
}

function renderItems(items) {
  itemsById.clear();
  itemMarkersLayer.clearLayers();
  itemsList.innerHTML = "";

  for (const item of items) {
    itemsById.set(item.id, item);
    addItemMarker(item);
    itemsList.appendChild(createItemCard(item));
  }

  itemCount.textContent = `${items.length} item${items.length === 1 ? "" : "s"}`;

  if (!items.length) {
    itemsList.innerHTML = `<p class="match-empty">No items found for the selected filters.</p>`;
  }
}

function collectQueryParams() {
  const params = new URLSearchParams();
  if (filterType.value) {
    params.set("type", filterType.value);
  }
  if (filterCategory.value) {
    params.set("category", filterCategory.value);
  }
  if (searchText.value.trim()) {
    params.set("q", searchText.value.trim());
  }

  const lat = filterLat.value.trim();
  const lon = filterLon.value.trim();
  if (lat && lon) {
    params.set("lat", lat);
    params.set("lon", lon);
    params.set("radius_km", String(Number(filterRadius.value) || 10));
  }
  return params;
}

async function loadItems() {
  const params = collectQueryParams();
  const url = `/api/items${params.toString() ? `?${params.toString()}` : ""}`;
  const response = await apiFetch(url);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Could not fetch items");
  }
  renderItems(payload.items);
}

async function uploadImageIfPresent() {
  const file = imageInput.files && imageInput.files[0];
  if (!file) {
    return "";
  }
  const body = new FormData();
  body.append("image", file);
  const response = await apiFetch("/api/uploads", { method: "POST", body });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Image upload failed");
  }
  return payload.image_url || "";
}

async function submitItem(event) {
  event.preventDefault();
  const formData = new FormData(form);

  const lat = Number(formData.get("latitude"));
  const lon = Number(formData.get("longitude"));
  if (Number.isNaN(lat) || Number.isNaN(lon)) {
    throw new Error("Choose location by map click or fill valid latitude and longitude.");
  }

  const imageUrl = await uploadImageIfPresent();
  const payload = {
    item_type: formData.get("item_type"),
    category: formData.get("category"),
    title: formData.get("title"),
    description: formData.get("description"),
    contact_name: formData.get("contact_name"),
    contact_phone: formData.get("contact_phone"),
    location_label: formData.get("location_label"),
    reward_note: formData.get("reward_note"),
    image_url: imageUrl,
    lat,
    lon,
  };

  const response = await apiFetch("/api/items", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  const created = await response.json();
  if (!response.ok) {
    throw new Error(created.error || "Could not submit item");
  }

  setFormMessage("Item submitted. Looking for nearby matches...", false);
  await loadItems();

  const savedItem = created.item;
  map.setView([savedItem.latitude, savedItem.longitude], 15);
  form.reset();
  imageInput.value = "";
}

function registerMapHandlers() {
  map.on("click", (event) => {
    setSelectedPoint(event.latlng.lat, event.latlng.lng, "map click");
  });
}

function registerFormHandlers() {
  form.addEventListener("submit", async (event) => {
    try {
      if (!sessionToken) {
        throw new Error("Login required before posting items.");
      }
      await submitItem(event);
    } catch (error) {
      setFormMessage(error.message, true);
    }
  });

  useMyLocationBtn.addEventListener("click", () => {
    if (!navigator.geolocation) {
      setFormMessage("Your browser does not support geolocation.", true);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const { latitude, longitude } = position.coords;
        setSelectedPoint(latitude, longitude, "device location");
        map.setView([latitude, longitude], 14);
      },
      () => {
        setFormMessage("Could not read your current location.", true);
      }
    );
  });
}

async function refreshCurrentUser() {
  const response = await apiFetch("/api/auth/me");
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Failed to read session");
  }
  if (payload.user) {
    setLoggedInState(payload.user, sessionToken);
  } else {
    setLoggedOutState();
  }
}

function registerAuthHandlers() {
  loginBtn.addEventListener("click", async () => {
    const formData = new FormData(authForm);
    const email = String(formData.get("email") || "").trim();
    const password = String(formData.get("password") || "");
    if (!email || !password) {
      setAuthMessage("Email and password are required for login.", true);
      return;
    }
    try {
      const response = await apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Login failed");
      }
      setLoggedInState(payload.user, payload.session_token || "");
      setAuthMessage("Logged in successfully.");
    } catch (error) {
      setAuthMessage(error.message, true);
    }
  });

  registerBtn.addEventListener("click", async () => {
    const formData = new FormData(registerForm);
    const name = String(formData.get("name") || "").trim();
    const email = String(formData.get("email") || "").trim();
    const password = String(formData.get("password") || "");
    if (!name || !email || !password) {
      setAuthMessage("Name, email, and password are required for register.", true);
      return;
    }
    try {
      const response = await apiFetch("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({ name, email, password }),
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || "Registration failed");
      }
      setLoggedInState(payload.user, payload.session_token || "");
      setAuthMessage("Registered and logged in successfully.");
    } catch (error) {
      setAuthMessage(error.message, true);
    }
  });

  logoutBtn.addEventListener("click", async () => {
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } finally {
      setLoggedOutState();
      setAuthMessage("Logged out.");
    }
  });
}

function registerSearchHandlers() {
  searchBtn.addEventListener("click", async () => {
    try {
      await loadItems();
    } catch (error) {
      setFormMessage(error.message, true);
    }
  });

  loadAllBtn.addEventListener("click", async () => {
    filterType.value = "";
    filterCategory.value = "";
    searchText.value = "";
    filterLat.value = "";
    filterLon.value = "";
    filterRadius.value = "10";

    try {
      await loadItems();
      setFormMessage("Showing all reports.", false);
    } catch (error) {
      setFormMessage(error.message, true);
    }
  });
}

async function bootstrap() {
  registerAuthHandlers();
  registerMapHandlers();
  registerFormHandlers();
  registerSearchHandlers();
  setFormMessage("Click on the map to pin the location before posting.");
  if (sessionToken) {
    try {
      await refreshCurrentUser();
    } catch {
      setLoggedOutState();
    }
  } else {
    setLoggedOutState();
  }
  await loadItems();
}

bootstrap().catch((error) => {
  setFormMessage(error.message, true);
});
