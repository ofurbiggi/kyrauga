(function () {
  var script = document.currentScript;
  var mainDir = script && script.dataset.hyphenopolyMainDir
    ? script.dataset.hyphenopolyMainDir
    : "/static/js/hyphenopoly/";
  var patternDir = script && script.dataset.hyphenopolyPatternDir
    ? script.dataset.hyphenopolyPatternDir
    : mainDir + "patterns/";

  if (!window.Hyphenopoly || typeof window.Hyphenopoly.config !== "function") {
    return;
  }

  window.Hyphenopoly.config({
    require: {
      is: "alþjóðaflugmálastofnunin",
    },
    paths: {
      maindir: mainDir,
      patterndir: patternDir,
    },
    setup: {
      defaultLanguage: "is",
      selectors: {
        ".ky-title": {},
        ".ky-hyphenate": {},
        ".ky-prose h1": {},
        ".ky-prose h2": {},
        ".ky-prose h3": {},
        ".ky-prose h4": {},
      },
    },
  });
})();
