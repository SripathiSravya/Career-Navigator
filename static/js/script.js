document.addEventListener('DOMContentLoaded', function () {
  const links = document.querySelectorAll('.feature-nav[data-target]');
  const panels = document.querySelectorAll('[data-feature-panel]');
  if (!links.length || !panels.length) return;
  function show(target) {
    panels.forEach(function (panel) { panel.hidden = panel.dataset.featurePanel !== target; });
    links.forEach(function (link) { link.classList.toggle('active', link.dataset.target === target); });
    const first = document.querySelector('[data-feature-panel="' + target + '"]');
    if (first) first.scrollTop = 0;
  }
  links.forEach(function (link) { link.addEventListener('click', function (event) { event.preventDefault(); show(link.dataset.target); history.replaceState(null, '', '#' + link.dataset.target); }); });
  const requested = location.hash.slice(1);
  show(Array.from(links).some(function (link) { return link.dataset.target === requested; }) ? requested : 'overview');
});
