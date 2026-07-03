(function () {
  function parseCoordinate(value) {
    if (value === null || value === undefined || value === "") {
      return null;
    }

    var parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function isValidLatitude(value) {
    return value !== null && value >= -90 && value <= 90;
  }

  function isValidLongitude(value) {
    return value !== null && value >= -180 && value <= 180;
  }

  function buildOpenStreetMapUrl(latitude, longitude) {
    return (
      "https://www.openstreetmap.org/?" +
      new URLSearchParams({
        mlat: latitude,
        mlon: longitude,
        zoom: 14,
      }).toString()
    );
  }

  function buildSearchUrl(query) {
    return (
      "https://nominatim.openstreetmap.org/search?" +
      new URLSearchParams({
        q: query,
        format: "jsonv2",
        limit: 1,
      }).toString()
    );
  }

  function findInput(mapElement, coordinateName) {
    var selector = mapElement.dataset[coordinateName + "Input"];

    if (selector) {
      return document.querySelector(selector);
    }

    return document.querySelector('[data-kyrauga-coordinate-target="' + coordinateName + '"]') ||
      document.querySelector('[data-kyrauga-gps-target="' + coordinateName + '"]');
  }

  function initializeMap(mapElement) {
    var latitudeInput = findInput(mapElement, "latitude");
    var longitudeInput = findInput(mapElement, "longitude");

    if (!mapElement || !latitudeInput || !longitudeInput || typeof L === "undefined") {
      return;
    }

    var mapWrapper = mapElement.closest("[data-kyrauga-coordinate-map-wrapper]") || document;
    var openMapLink = mapWrapper.querySelector('[data-kyrauga-coordinate-target="open-map-link"]') ||
      mapWrapper.querySelector('[data-kyrauga-gps-target="open-map-link"]');
    var searchContainer = mapWrapper.querySelector("[data-kyrauga-coordinate-search]");
    var searchInput = mapWrapper.querySelector('[data-kyrauga-coordinate-target="search-input"]');
    var searchButton = mapWrapper.querySelector('[data-kyrauga-coordinate-target="search-button"]');
    var searchStatus = mapWrapper.querySelector('[data-kyrauga-coordinate-target="search-status"]');
    var defaultCenter = [64.9631, -19.0208];
    var latitude = parseCoordinate(mapElement.dataset.latitude || latitudeInput.value);
    var longitude = parseCoordinate(mapElement.dataset.longitude || longitudeInput.value);
    var hasCoordinates = isValidLatitude(latitude) && isValidLongitude(longitude);

    var map = L.map(mapElement).setView(hasCoordinates ? [latitude, longitude] : defaultCenter, hasCoordinates ? 10 : 5);

    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maxZoom: 19,
      referrerPolicy: "strict-origin-when-cross-origin",
    }).addTo(map);

    var marker = null;

    function syncOpenMapLink(nextLatitude, nextLongitude) {
      if (!openMapLink) {
        return;
      }

      if (isValidLatitude(nextLatitude) && isValidLongitude(nextLongitude)) {
        openMapLink.href = buildOpenStreetMapUrl(nextLatitude, nextLongitude);
        openMapLink.classList.remove("disabled");
        openMapLink.removeAttribute("aria-disabled");
      } else {
        openMapLink.href = "#";
        openMapLink.classList.add("disabled");
        openMapLink.setAttribute("aria-disabled", "true");
      }
    }

    function setMarker(nextLatitude, nextLongitude, shouldPan) {
      if (!isValidLatitude(nextLatitude) || !isValidLongitude(nextLongitude)) {
        if (marker) {
          map.removeLayer(marker);
          marker = null;
        }
        syncOpenMapLink(null, null);
        return;
      }

      if (!marker) {
        marker = L.marker([nextLatitude, nextLongitude], {
          draggable: true,
        }).addTo(map);

        marker.on("dragend", function (event) {
          var nextPosition = event.target.getLatLng();
          latitudeInput.value = nextPosition.lat.toFixed(6);
          longitudeInput.value = nextPosition.lng.toFixed(6);
          syncOpenMapLink(nextPosition.lat, nextPosition.lng);
        });
      } else {
        marker.setLatLng([nextLatitude, nextLongitude]);
      }

      if (shouldPan) {
        map.setView([nextLatitude, nextLongitude], Math.max(map.getZoom(), 10));
      }

      syncOpenMapLink(nextLatitude, nextLongitude);
    }

    map.on("click", function (event) {
      latitudeInput.value = event.latlng.lat.toFixed(6);
      longitudeInput.value = event.latlng.lng.toFixed(6);
      setMarker(event.latlng.lat, event.latlng.lng, false);
    });

    function syncMarkerFromInputs() {
      var nextLatitude = parseCoordinate(latitudeInput.value);
      var nextLongitude = parseCoordinate(longitudeInput.value);
      setMarker(nextLatitude, nextLongitude, false);
    }

    function setSearchStatus(message) {
      if (searchStatus) {
        searchStatus.textContent = message;
      }
    }

    function fitSearchResult(result) {
      if (Array.isArray(result.boundingbox) && result.boundingbox.length === 4) {
        var south = parseCoordinate(result.boundingbox[0]);
        var north = parseCoordinate(result.boundingbox[1]);
        var west = parseCoordinate(result.boundingbox[2]);
        var east = parseCoordinate(result.boundingbox[3]);

        if (isValidLatitude(south) && isValidLatitude(north) && isValidLongitude(west) && isValidLongitude(east)) {
          map.fitBounds([[south, west], [north, east]], {
            maxZoom: 13,
            padding: [32, 32],
          });
          return;
        }
      }

      var resultLatitude = parseCoordinate(result.lat);
      var resultLongitude = parseCoordinate(result.lon);

      if (isValidLatitude(resultLatitude) && isValidLongitude(resultLongitude)) {
        map.setView([resultLatitude, resultLongitude], 12);
      }
    }

    function searchApproximateLocation(query) {
      setSearchStatus("Searching...");

      fetch(buildSearchUrl(query), {
        headers: {
          Accept: "application/json",
        },
      })
        .then(function (response) {
          if (!response.ok) {
            throw new Error("Location search failed.");
          }
          return response.json();
        })
        .then(function (results) {
          if (!Array.isArray(results) || !results.length) {
            setSearchStatus("No matching place found.");
            return;
          }

          fitSearchResult(results[0]);
          setSearchStatus("Map moved to the approximate location.");
        })
        .catch(function () {
          setSearchStatus("Location search is unavailable.");
        });
    }

    function runSearch(event) {
      if (event) {
        event.preventDefault();
      }

      var query = searchInput.value.trim();
      if (!query) {
        setSearchStatus("Enter a place to search for.");
        return;
      }

      searchApproximateLocation(query);
    }

    if (searchContainer && searchInput && searchButton) {
      searchButton.addEventListener("click", runSearch);
      searchInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
          runSearch(event);
        }
      });
    }

    latitudeInput.addEventListener("input", syncMarkerFromInputs);
    longitudeInput.addEventListener("input", syncMarkerFromInputs);

    setMarker(latitude, longitude, false);
  }

  function initializeMaps() {
    var mapElements = document.querySelectorAll("[data-kyrauga-coordinate-map], [data-kyrauga-gps-map]");

    mapElements.forEach(initializeMap);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeMaps);
  } else {
    initializeMaps();
  }
})();
