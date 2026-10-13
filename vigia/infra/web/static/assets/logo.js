// Inline-SVG logo helper. The Estúdio AB symbol uses fill="currentColor"
// so glyph color follows the parent's CSS `color`. This script finds
// elements with data-logo="symbol" / "wide" / "modular" and injects the
// SVG markup directly (CSS `mask:` doesn't work reliably for tinting,
// since `currentColor` inside an external SVG used as mask resolves
// against the SVG's own root, not the masked element).
(function () {
  const SYMBOL = '<svg viewBox="0 0 5000 5000" fill="currentColor" fill-rule="evenodd" preserveAspectRatio="xMidYMid meet" aria-hidden="true"><polygon points="818 1888.36 818 2500 1735.45 2500 1735.45 2805.82 818 3723.27 818 2500 206.36 2500 206.36 4334.91 818 4334.91 1123.82 4334.91 1735.45 3723.27 1735.45 4334.91 2347.09 4334.91 2347.09 2500 2347.09 1888.36 818 1888.36"/><polygon points="4182 2500 4182 3723.27 3264.55 2805.82 3264.55 2500 4182 2500 4182 1888.36 3264.55 1888.36 3264.55 665.09 2652.91 665.09 2652.91 4334.91 3264.55 4334.91 3264.55 3723.27 3876.18 4334.91 4182 4334.91 4793.64 4334.91 4793.64 2500 4182 2500"/></svg>';

  const WIDE = '<svg viewBox="0 0 4587.28 3669.82" fill="currentColor" fill-rule="evenodd" preserveAspectRatio="xMidYMid meet" aria-hidden="true"><polygon points="611.64 1223.27 611.64 1834.91 1529.09 1834.91 1529.09 2140.73 611.64 3058.18 611.64 1834.91 0 1834.91 0 3669.82 611.64 3669.82 917.46 3669.82 1529.09 3058.18 1529.09 3669.82 2140.73 3669.82 2140.73 1834.91 2140.73 1223.27 611.64 1223.27"/><polygon points="3975.64 1834.91 3975.64 3058.18 3058.18 2140.73 3058.18 1834.91 3975.64 1834.91 3975.64 1223.27 3058.18 1223.27 3058.18 0 2446.55 0 2446.55 3669.82 3058.18 3669.82 3058.18 3058.18 3669.82 3669.82 3975.64 3669.82 4587.28 3669.82 4587.28 1834.91 3975.64 1834.91"/></svg>';

  // The dot/modular variant is large (~12 KB), so it lives in
  // assets/symbol_modular.svg next to this script. Override the path via
  //   <script src="assets/logo.js" data-modular-url="…"></script>
  // if your assets folder lives elsewhere relative to the page.
  const _scriptEl = document.currentScript;
  const MODULAR_URL = (_scriptEl && _scriptEl.dataset && _scriptEl.dataset.modularUrl)
    || (_scriptEl ? _scriptEl.src.replace(/[^\/]+$/, 'symbol_modular.svg') : 'assets/symbol_modular.svg');
  let MODULAR_MARKUP = null;
  let modularPromise = null;

  function loadModular() {
    if (MODULAR_MARKUP) return Promise.resolve(MODULAR_MARKUP);
    if (modularPromise) return modularPromise;
    modularPromise = fetch(MODULAR_URL)
      .then(r => r.ok ? r.text() : Promise.reject(new Error('logo.js: failed to fetch ' + MODULAR_URL)))
      .then(text => {
        // Strip XML prolog so the markup can be inlined directly.
        MODULAR_MARKUP = text.replace(/<\?xml[^>]*\?>\s*/, '');
        return MODULAR_MARKUP;
      });
    return modularPromise;
  }

  function paint() {
    document.querySelectorAll('[data-logo="symbol"]:not([data-logo-painted])').forEach(el => {
      el.innerHTML = SYMBOL;
      el.setAttribute('data-logo-painted', '1');
    });
    document.querySelectorAll('[data-logo="wide"]:not([data-logo-painted])').forEach(el => {
      el.innerHTML = WIDE;
      el.setAttribute('data-logo-painted', '1');
    });
    const modularEls = document.querySelectorAll('[data-logo="modular"]:not([data-logo-painted])');
    if (modularEls.length) {
      loadModular().then(markup => {
        modularEls.forEach(el => {
          if (el.hasAttribute('data-logo-painted')) return;
          el.innerHTML = markup;
          el.setAttribute('data-logo-painted', '1');
        });
      }).catch(err => console.error(err));
    }
  }

  // Run as soon as possible, then again on DOMContentLoaded for any late nodes.
  paint();
  if (document.readyState !== 'complete') {
    document.addEventListener('DOMContentLoaded', paint);
  }
  // Expose for React or dynamic mounts.
  window.ABLogo = {
    SYMBOL, WIDE,
    get MODULAR() { return MODULAR_MARKUP; },
    loadModular, paint,
  };
})();
