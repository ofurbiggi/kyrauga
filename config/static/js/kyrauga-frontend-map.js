(function () {
  var OSM_ATTRIBUTION =
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

  function getStyle(mapConfig) {
    var contourConfig = (mapConfig && mapConfig.contours) || {};
    if (
      mapConfig &&
      mapConfig.render_style === "contours" &&
      contourConfig.style_url
    ) {
      return contourConfig.style_url;
    }
    return {
      version: 8,
      sources: {
        osm: {
          type: "raster",
          tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
          tileSize: 256,
          attribution: OSM_ATTRIBUTION,
        },
      },
      layers: [
        {
          id: "osm",
          type: "raster",
          source: "osm",
        },
      ],
    };
  }

  function createMarkerElement() {
    var marker = document.createElement("button");
    marker.type = "button";
    marker.className = "ky-map-marker";
    marker.setAttribute("aria-label", "Open map location");
    marker.innerHTML = '<i class="fa-solid fa-map-pin" aria-hidden="true"></i>';
    return marker;
  }

  function createBoundsFeature(map) {
    var bounds = map.getBounds();
    var west = bounds.getWest();
    var east = bounds.getEast();
    var south = bounds.getSouth();
    var north = bounds.getNorth();
    return {
      type: "Feature",
      properties: {},
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [west, south],
            [east, south],
            [east, north],
            [west, north],
            [west, south],
          ],
        ],
      },
    };
  }

  function syncMiniMap(mainMap, miniMap) {
    var center = mainMap.getCenter();
    var nextZoom = Math.max(mainMap.getZoom() - 5, 0);
    miniMap.jumpTo({
      center: [center.lng, center.lat],
      zoom: nextZoom,
      bearing: 0,
      pitch: 0,
    });

    var source = miniMap.getSource("main-map-bounds");
    if (source) {
      source.setData(createBoundsFeature(mainMap));
    }
  }

  function addMiniMap(container, mainMap, mapConfig) {
    var sdk = window.maptilersdk;
    if (!container || !mainMap || !sdk) {
      return null;
    }

    if (window.getComputedStyle(container).position === "static") {
      container.style.position = "relative";
    }

    var miniMapNode = document.createElement("div");
    miniMapNode.className = "ky-map-minimap";
    miniMapNode.setAttribute("aria-hidden", "true");
    miniMapNode.style.setProperty("position", "absolute", "important");
    miniMapNode.style.setProperty("left", "1rem", "important");
    miniMapNode.style.setProperty("bottom", "2rem", "important");
    miniMapNode.style.setProperty("top", "auto", "important");
    miniMapNode.style.setProperty("right", "auto", "important");
    container.appendChild(miniMapNode);

    var center = mainMap.getCenter();
    var miniMap = new sdk.Map({
      container: miniMapNode,
      style: getStyle(mapConfig),
      center: [center.lng, center.lat],
      zoom: Math.max(mainMap.getZoom() - 5, 0),
      attributionControl: false,
      geolocateControl: false,
      interactive: false,
      maptilerLogo: false,
      navigationControl: false,
    });
    miniMapNode.style.setProperty("left", "1rem", "important");
    miniMapNode.style.setProperty("bottom", "2rem", "important");
    miniMapNode.style.setProperty("top", "auto", "important");
    miniMapNode.style.setProperty("right", "auto", "important");

    miniMap.on("load", function () {
      miniMap.addSource("main-map-bounds", {
        type: "geojson",
        data: createBoundsFeature(mainMap),
      });
      miniMap.addLayer({
        id: "main-map-bounds-fill",
        type: "fill",
        source: "main-map-bounds",
        paint: {
          "fill-color": "#66f1d2",
          "fill-opacity": 0.18,
        },
      });
      miniMap.addLayer({
        id: "main-map-bounds-line",
        type: "line",
        source: "main-map-bounds",
        paint: {
          "line-color": "#2f5fd0",
          "line-width": 2,
        },
      });
      syncMiniMap(mainMap, miniMap);
    });

    mainMap.on("move", function () {
      syncMiniMap(mainMap, miniMap);
    });
    mainMap.on("resize", function () {
      syncMiniMap(mainMap, miniMap);
    });

    return miniMap;
  }

  function escapeHtml(value) {
    return String(value || "").replace(/[&<>"']/g, function (character) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[character];
    });
  }

  function createMap(container, mapConfig, options) {
    var sdk = window.maptilersdk;
    var mapOptions = options || {};
    if (!container || !sdk) {
      return null;
    }
    if (mapConfig && mapConfig.contours && mapConfig.contours.api_key) {
      sdk.config.apiKey = mapConfig.contours.api_key;
    }

    var map = new sdk.Map({
      container: container,
      style: getStyle(mapConfig),
      center: mapOptions.center || [0, 0],
      zoom: mapOptions.zoom == null ? 2 : mapOptions.zoom,
      attributionControl: true,
      geolocateControl: false,
      navigationControl:
        mapOptions.navigationControl === false
          ? false
          : mapOptions.navigationPosition || "bottom-right",
      scrollZoom: mapOptions.scrollZoom !== false,
    });

    if (mapOptions.scrollZoom === false && map.scrollZoom) {
      map.scrollZoom.disable();
    }
    if (mapOptions.miniMap !== false) {
      map.on("load", function () {
        addMiniMap(container, map, mapConfig);
      });
    }
    return map;
  }

  function openMarkerPopup(marker) {
    if (marker && marker.getPopup && !marker.getPopup().isOpen()) {
      marker.togglePopup();
    }
  }

  function closeMarkerPopup(marker) {
    if (marker && marker.getPopup && marker.getPopup().isOpen()) {
      marker.togglePopup();
    }
  }

  function addPointMarker(map, point, options) {
    var sdk = window.maptilersdk;
    var markerOptions = options || {};
    var markerElement = createMarkerElement();
    var marker = new sdk.Marker({
      element: markerElement,
      anchor: "bottom",
    })
      .setLngLat([point.longitude, point.latitude])
      .addTo(map);

    if (markerOptions.popupHtml) {
      marker.setPopup(
        new sdk.Popup({
          closeButton: false,
          closeOnClick: false,
          offset: 12,
        }).setHTML(markerOptions.popupHtml(point)),
      );
      markerElement.addEventListener("mouseenter", function () {
        openMarkerPopup(marker);
      });
      markerElement.addEventListener("mouseleave", function () {
        closeMarkerPopup(marker);
      });
      markerElement.addEventListener("focus", function () {
        openMarkerPopup(marker);
      });
      markerElement.addEventListener("blur", function () {
        closeMarkerPopup(marker);
      });
    }

    if (markerOptions.clickUrl) {
      markerElement.addEventListener("click", function () {
        window.location.href = markerOptions.clickUrl(point);
      });
    }
    return marker;
  }

  function fitToPoints(map, points, options) {
    var fitOptions = options || {};
    if (!Array.isArray(points) || points.length === 0) {
      return;
    }
    if (points.length === 1) {
      map.setCenter([points[0].longitude, points[0].latitude]);
      map.setZoom(fitOptions.singleZoom || 10);
      return;
    }

    var west = Math.min.apply(
      null,
      points.map(function (point) {
        return point.longitude;
      }),
    );
    var east = Math.max.apply(
      null,
      points.map(function (point) {
        return point.longitude;
      }),
    );
    var south = Math.min.apply(
      null,
      points.map(function (point) {
        return point.latitude;
      }),
    );
    var north = Math.max.apply(
      null,
      points.map(function (point) {
        return point.latitude;
      }),
    );
    map.fitBounds(
      [
        [west, south],
        [east, north],
      ],
      {
        padding: fitOptions.padding || 48,
        maxZoom: fitOptions.maxZoom || 10,
      },
    );
  }

  window.kyraugaFrontendMap = {
    addPointMarker: addPointMarker,
    closeMarkerPopup: closeMarkerPopup,
    createMap: createMap,
    escapeHtml: escapeHtml,
    fitToPoints: fitToPoints,
    openMarkerPopup: openMarkerPopup,
  };
})();
