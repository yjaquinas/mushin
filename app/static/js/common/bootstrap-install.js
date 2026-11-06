window.MushinBootstrapInstall = async function (html, url, signal) {
  "use strict";
  const incoming = new DOMParser().parseFromString(html, "text/html");
  if (incoming.documentElement.hasAttribute("data-bootstrap-pending")) throw new Error("Repeated startup response");
  const loaded = new Set(Array.from(document.scripts, script => script.src));
  const scripts = Array.from(incoming.querySelectorAll("script[src]"));
  for (const script of scripts) {
    const src = new URL(script.getAttribute("src"), url).href;
    if (loaded.has(src)) continue;
    if (signal.aborted) throw new Error("Startup expired");
    await new Promise((resolve, reject) => {
      const node = script.cloneNode(false);
      node.src = src;
      node.async = false;
      node.onload = resolve;
      node.onerror = () => reject(new Error("Startup asset failed"));
      document.head.append(node);
    });
    loaded.add(src);
  }
  if (signal.aborted) throw new Error("Startup expired");
  document.head.querySelectorAll("title, meta, link[rel=canonical], script[type='application/ld+json']")
    .forEach(node => node.remove());
  for (const node of incoming.head.children) {
    if (!node.matches("title, meta, link, script[type='application/ld+json']")) continue;
    const copy = node.cloneNode(true);
    if (node.matches("link")) {
      copy.href = new URL(node.getAttribute("href"), url).href;
      if (Array.from(document.head.querySelectorAll("link")).some(link => link.rel === copy.rel && link.href === copy.href)) continue;
    }
    document.head.append(copy);
  }
  incoming.body.querySelectorAll("script:not([type='application/ld+json'])").forEach(node => node.remove());
  incoming.body.querySelectorAll(".app-splash").forEach(node => node.remove());
  const cover = document.getElementById("bootstrap-splash");
  for (const attribute of Array.from(document.body.attributes)) document.body.removeAttribute(attribute.name);
  for (const attribute of incoming.body.attributes) document.body.setAttribute(attribute.name, attribute.value);
  document.documentElement.lang = incoming.documentElement.lang || "en";
  const theme = incoming.documentElement.getAttribute("data-theme");
  if (theme) document.documentElement.setAttribute("data-theme", theme);
  window.history.replaceState(null, "", url);
  document.body.replaceChildren(cover, ...Array.from(incoming.body.childNodes));
  window.htmx.process(document.body);
  window.MushinAppReady.complete();
  document.documentElement.removeAttribute("data-bootstrap-pending");
  document.documentElement.classList.remove("app-booting");
  document.body.dispatchEvent(new CustomEvent("app:ready"));
};
