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

  function initializeMap() {
    var mapElement = document.querySelector("[data-kyrauga-gps-map]");
    var latitudeInput = document.querySelector('[data-kyrauga-gps-target="latitude"]');
    var longitudeInput = document.querySelector('[data-kyrauga-gps-target="longitude"]');

    if (!mapElement || !latitudeInput || !longitudeInput || typeof L === "undefined") {
      return;
    }

    var openMapLink = document.querySelector('[data-kyrauga-gps-target="open-map-link"]');
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

    latitudeInput.addEventListener("input", syncMarkerFromInputs);
    longitudeInput.addEventListener("input", syncMarkerFromInputs);

    setMarker(latitude, longitude, false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initializeMap);
  } else {
    initializeMap();
  }
})();
