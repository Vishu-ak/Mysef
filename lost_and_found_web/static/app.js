const DEFAULT_CENTER = [20.5937, 78.9629];
const DEFAULT_ZOOM = 5;

const map = L.map("map").setView(DEFAULT_CENTER, DEFAULT_ZOOM);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);

const registerForm = document.getElementById("registerForm");
const loginForm = document.getElementById("loginForm");
const authForms = document.getElementById("authForms");
const authActions = document.getElementById("authActions");
const authStatus = document.getElementById("authStatus");
const authUser = document.getElementById("authUser");
const authMessage = document.getElementById("authMessage");
const logoutBtn = document.getElementById("logoutBtn");
const googleLoginBtn = document.getElementById("googleLoginBtn");
const googleCredentialInput = document.getElementById("googleCredentialInput");

const form = document.getElementById("itemForm");
const formMessage = document.getElementById("formMessage");
const latitudeInput = document.getElementById("latitudeInput");
const longitudeInput = document.getElementById("longitudeInput");
const useMyLocationBtn = document.getElementById("useMyLocationBtn");
const itemImageInput = document.getElementById("itemImageInput");
const imagePreview = document.getElementById("imagePreview");

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

let sessionToken = localStorage.getItem("lostfound_session_token") || "";
let currentUser = null;
let appConfig = { google_client_id: "" };

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
  formMessage.classList.remove("error", "success", "info");
  formMessage.classList.add(isError ? "error" : "success");
}

function setAuthMessage(message, isError = false) {
  authMessage.textContent = message;
  authMessage.classList.remove("error", "success", "info");
  authMessage.classList.add(isError ? "error" : "success");
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

  setFormMessage(`Location selected from ${source}.`);
}

function setLoggedInState(user, token = "") {
  currentUser = user;
  if (token) {
    sessionToken = token;
    localStorage.setItem("lostfound_session_token", token);
  }
  authForms.classList.add("hidden");
  authActions.classList.remove("hidden");
  authStatus.textContent = "Logged in";
  authUser.textContent = `${user.name} (${user.email})`;
}

function setLoggedOutState() {
  currentUser = null;
  sessionToken = "";
  localStorage.removeItem("lostfound_session_token");
  authForms.classList.remove("hidden");
  authActions.classList.add("hidden");
  authStatus.textContent = "Not logged in";
  authUser.textContent = "";
}

async function apiFetch(url, options = {}) {
  const headers = new Headers(options.headers || {});
  if (sessionToken) {
    headers.set("Authorization", `Bearer ${sessionToken}`);
  }
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(url, { ...options, headers });
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

function buildWhatsappHref(item) {
  const phoneDigits = String(item.contact_phone || "").replace(/\D/g, "");
  if (!phoneDigits) {
    return "";
  }
  const msg = encodeURIComponent(
    `Hi ${item.contact_name}, I am contacting you about "${item.title}" on Lost & Found Connect.`
  );
  return `https://wa.me/${phoneDigits}?text=${msg}`;
}

function buildMailtoHref(item) {
  if (!item.owner_email) {
    return "";
  }
  const subject = encodeURIComponent(`Regarding "${item.title}" (${item.item_type})`);
  const body = encodeURIComponent(
    `Hello ${item.contact_name},\n\nI am reaching out about your item listing: "${item.title}".`
  );
  return `mailto:${item.owner_email}?subject=${subject}&body=${body}`;
}

function createItemCard(item) {
  const fragment = itemCardTemplate.content.cloneNode(true);
  const titleEl = fragment.querySelector(".item-title");
  const metaEl = fragment.querySelector(".item-meta");
  const badgeEl = fragment.querySelector(".item-badge");
  const descriptionEl = fragment.querySelector(".item-description");
  const contactEl = fragment.querySelector(".item-contact");
  const locationEl = fragment.querySelector(".item-location");
  const imageEl = fragment.querySelector(".item-image");
  const whatsappBtn = fragment.querySelector(".contact-whatsapp-btn");
  const emailBtn = fragment.querySelector(".contact-email-btn");
  const showMapBtn = fragment.querySelector(".show-on-map-btn");
  const findMatchesBtn = fragment.querySelector(".find-matches-btn");
  const matchesContainer = fragment.querySelector(".matches-container");

  titleEl.textContent = item.title;
  metaEl.textContent = `${item.category} · Reported ${item.created_at}`;
  badgeEl.textContent = item.item_type.toUpperCase();
  badgeEl.classList.add(item.item_type);
  descriptionEl.textContent = item.description;
  contactEl.textContent = `Contact: ${item.contact_name} (${item.contact_phone})`;
  locationEl.textContent = `Location: ${item.location_label || `${item.latitude.toFixed(5)}, ${item.longitude.toFixed(5)}`}`;

  if (item.image_url) {
    imageEl.src = item.image_url;
    imageEl.classList.remove("hidden");
  } else {
    imageEl.classList.add("hidden");
  }

  const whatsappHref = buildWhatsappHref(item);
  if (whatsappHref) {
    whatsappBtn.href = whatsappHref;
    whatsappBtn.classList.remove("hidden");
  } else {
    whatsappBtn.classList.add("hidden");
  }

  const mailtoHref = buildMailtoHref(item);
  if (mailtoHref) {
    emailBtn.href = mailtoHref;
    emailBtn.classList.remove("hidden");
  } else {
    emailBtn.classList.add("hidden");
  }

  showMapBtn.addEventListener("click", () => {
    map.setView([item.latitude, item.longitude], 15);
  });

  findMatchesBtn.addEventListener("click", async () => {
    findMatchesBtn.disabled = true;
    findMatchesBtn.textContent = "Finding...";
    try {
      const radius = Number(filterRadius.value) || 10;
      const response = await apiFetch(
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

      const rows = payload.matches
        .map((match) => {
          const waHref = buildWhatsappHref(match);
          const emHref = buildMailtoHref(match);
          return `
            <div class="match-row">
              <strong>${escapeHtml(match.title)}</strong>
              <span>${escapeHtml(match.item_type.toUpperCase())}</span>
              <span>${Number(match.distance_km).toFixed(2)} km away</span>
              <span>${escapeHtml(match.contact_name)} (${escapeHtml(match.contact_phone)})</span>
              <div class="match-contact-actions">
                ${
                  waHref
                    ? `<a class="ghost-button" target="_blank" rel="noopener noreferrer" href="${waHref}">WhatsApp</a>`
                    : ""
                }
                ${
                  emHref
                    ? `<a class="ghost-button" target="_blank" rel="noopener noreferrer" href="${emHref}">Email</a>`
                    : ""
                }
              </div>
            </div>
          `;
        })
        .join("");
      matchesContainer.innerHTML = `<h4>Nearby possible matches</h4>${rows}`;
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
  itemMarkersLayer.clearLayers();
  itemsList.innerHTML = "";
  for (const item of items) {
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
  if (filterType.value) params.set("type", filterType.value);
  if (filterCategory.value) params.set("category", filterCategory.value);
  if (searchText.value.trim()) params.set("q", searchText.value.trim());
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
  const file = itemImageInput.files && itemImageInput.files[0];
  if (!file) {
    return { image_url: "", image_filename: "" };
  }
  const body = new FormData();
  body.append("image", file);
  const response = await apiFetch("/api/uploads", { method: "POST", body });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Image upload failed");
  }
  return {
    image_url: payload.image_url || "",
    image_filename: payload.image_filename || "",
  };
}

async function submitItem(event) {
  event.preventDefault();
  if (!sessionToken) {
    throw new Error("Login required before posting items.");
  }

  const formData = new FormData(form);
  const lat = Number(formData.get("latitude"));
  const lon = Number(formData.get("longitude"));
  if (Number.isNaN(lat) || Number.isNaN(lon)) {
    throw new Error("Choose location by map click or fill valid latitude and longitude.");
  }

  const upload = await uploadImageIfPresent();
  const payload = {
    item_type: formData.get("item_type"),
    category: formData.get("category"),
    title: formData.get("title"),
    description: formData.get("description"),
    contact_name: formData.get("contact_name"),
    contact_phone: formData.get("contact_phone"),
    location_label: formData.get("location_label"),
    image_url: upload.image_url,
    image_filename: upload.image_filename,
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

  setFormMessage("Item submitted successfully.");
  form.reset();
  imagePreview.classList.add("hidden");
  await loadItems();
}

function updateGoogleButtonVisibility() {
  if (!googleLoginBtn) {
    return;
  }
  if (appConfig.google_client_id) {
    googleLoginBtn.classList.remove("hidden");
  } else {
    googleLoginBtn.classList.add("hidden");
  }
}

async function refreshCurrentUser() {
  const response = await apiFetch("/api/auth/me");
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Unable to check session");
  }
  if (payload.user) {
    setLoggedInState(payload.user);
  } else {
    setLoggedOutState();
  }
}

async function loadConfig() {
  const response = await fetch("/api/config");
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Failed to load app config");
  }
  appConfig = payload;
  updateGoogleButtonVisibility();
}

async function handleGoogleLogin() {
  const credential = String(googleCredentialInput.value || "").trim();
  if (!credential) {
    throw new Error("Paste Google ID token in the field first.");
  }
  const response = await apiFetch("/api/auth/google", {
    method: "POST",
    body: JSON.stringify({ credential }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Google login failed");
  }
  setLoggedInState(payload.user, payload.session_token || "");
  googleCredentialInput.value = "";
}

function registerAuthHandlers() {
  registerForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const formData = new FormData(registerForm);
      const response = await apiFetch("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({
          name: formData.get("name"),
          email: formData.get("email"),
          password: formData.get("password"),
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Registration failed");
      setLoggedInState(payload.user, payload.session_token || "");
      setAuthMessage("Registered and logged in.");
    } catch (error) {
      setAuthMessage(error.message, true);
    }
  });

  loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const formData = new FormData(loginForm);
      const response = await apiFetch("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({
          email: formData.get("email"),
          password: formData.get("password"),
        }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Login failed");
      setLoggedInState(payload.user, payload.session_token || "");
      setAuthMessage("Logged in successfully.");
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

  if (googleLoginBtn) {
    googleLoginBtn.addEventListener("click", async () => {
      try {
        await handleGoogleLogin();
        setAuthMessage("Google login successful.");
      } catch (error) {
        setAuthMessage(error.message, true);
      }
    });
  }
}

function registerFormHandlers() {
  form.addEventListener("submit", async (event) => {
    try {
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
      () => setFormMessage("Could not read your current location.", true)
    );
  });

  itemImageInput.addEventListener("change", () => {
    const file = itemImageInput.files && itemImageInput.files[0];
    if (!file) {
      imagePreview.classList.add("hidden");
      imagePreview.removeAttribute("src");
      return;
    }
    imagePreview.src = URL.createObjectURL(file);
    imagePreview.classList.remove("hidden");
  });
}

function registerMapHandlers() {
  map.on("click", (event) => {
    setSelectedPoint(event.latlng.lat, event.latlng.lng, "map click");
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
      setFormMessage("Showing all reports.");
    } catch (error) {
      setFormMessage(error.message, true);
    }
  });
}

async function bootstrap() {
  registerAuthHandlers();
  registerFormHandlers();
  registerMapHandlers();
  registerSearchHandlers();

  await loadConfig();
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
  setFormMessage("Click on the map to pin the location before posting.");
}

bootstrap().catch((error) => {
  setFormMessage(error.message, true);
});
