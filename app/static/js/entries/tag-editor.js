(function () {
  "use strict";
  const word = /[\p{L}\p{N}_]/u;
  const states = new WeakMap();
  function state(text) {
    if (!text || text.name !== "memo") return null;
    const toolbar = text.parentElement.querySelector('[data-tag-toolbar]');
    if (!toolbar) return null;
    if (!states.has(text)) states.set(text, {text, toolbar, tags: JSON.parse(toolbar.dataset.tags), active: null, index: -1});
    return states.get(text);
  }
  function token(text) {
    if (text.selectionStart !== text.selectionEnd) return null;
    let start = text.selectionStart, end = start;
    while (start && word.test(text.value[start - 1])) start--;
    if (!start || text.value[start - 1] !== '#') return null;
    while (end < text.value.length && word.test(text.value[end])) end++;
    return {start: start - 1, end, prefix: text.value.slice(start, text.selectionStart).toLowerCase()};
  }
  function render(s) {
    s.active = token(s.text);
    s.index = -1;
    s.toolbar.querySelector('[data-insert-tag]').hidden = !!s.active;
    const results = s.toolbar.querySelector('[data-tag-results]');
    results.hidden = true;
    results.replaceChildren();
    if (!s.active) return;
    const matches = s.tags.filter(name => name.startsWith(s.active.prefix)).slice(0, 6);
    results.hidden = matches.length === 0;
    matches.forEach(name => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'entry-tag-action';
      button.textContent = '#' + name;
      button.addEventListener('click', () => {
        const active = token(s.text);
        if (!active) return;
        const suffix = s.text.value.slice(active.end);
        insert(s, '#' + name + (/^\s/.test(suffix) ? '' : ' '), active.start, active.end);
      });
      results.append(button);
    });
  }
  function insert(s, value, start, end) {
    const text = s.text;
    const next = text.value.slice(0, start) + value + text.value.slice(end);
    if (next.length > Number(text.dataset.boundedMaxChars) || next.split('\n').length > Number(text.dataset.boundedMaxLines)) return;
    text.focus({preventScroll: true});
    text.setRangeText(value, start, end, 'end');
    text.dispatchEvent(new Event('input', {bubbles: true}));
    render(s);
  }
  document.addEventListener('pointerdown', event => {
    if (event.target.closest('[data-tag-toolbar] button')) event.preventDefault();
  });
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-insert-tag]');
    if (button) {
      const s = state(button.closest('.entry-notes').querySelector('textarea'));
      if (!s) return;
      s.text.focus({preventScroll: true});
      if (token(s.text)) return render(s);
      const start = s.text.selectionStart;
      insert(s, (start && !/\s/.test(s.text.value[start - 1]) ? ' ' : '') + '#', start, s.text.selectionEnd);
    } else {
      const s = state(event.target);
      if (s) render(s);
    }
  });
  document.addEventListener('focusin', event => {
    const s = state(event.target);
    if (s) render(s);
  });
  ['input', 'keyup', 'compositionend'].forEach(type => document.addEventListener(type, event => {
    const s = state(event.target);
    if (type === 'keyup' && ['ArrowDown', 'ArrowUp', 'Enter', 'Escape'].includes(event.key)) return;
    if (s && !event.isComposing) render(s);
  }));
  document.addEventListener('keydown', event => {
    const s = state(event.target);
    if (!s || !s.active || event.isComposing) return;
    const buttons = [...s.toolbar.querySelector('[data-tag-results]').children];
    if (event.key === 'Escape') {
      event.preventDefault(); event.stopPropagation();
      s.active = null;
      s.toolbar.querySelector('[data-tag-results]').replaceChildren();
      s.toolbar.querySelector('[data-tag-results]').hidden = true;
      s.toolbar.querySelector('[data-insert-tag]').hidden = false;
    } else if (['ArrowDown', 'ArrowUp'].includes(event.key) && buttons.length) {
      event.preventDefault();
      s.index = (s.index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length;
      buttons.forEach((b, i) => b.classList.toggle('entry-tag-action--highlighted', i === s.index));
    } else if (event.key === 'Enter' && s.index >= 0) {
      event.preventDefault(); buttons[s.index].click();
    }
  });
  function viewport() {
    document.documentElement.style.setProperty('--entry-viewport', (window.visualViewport?.height || window.innerHeight) + 'px');
  }
  window.visualViewport?.addEventListener('resize', viewport);
  window.addEventListener('resize', viewport);
  viewport();
})();
