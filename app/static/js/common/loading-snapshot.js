window.MushinLoadingSnapshot = {
  html(root) {
    const copy = root.cloneNode(true);
    const originals = [root, ...root.querySelectorAll("*")];
    const copies = [copy, ...copy.querySelectorAll("*")];
    originals.forEach(function (original, index) {
      const node = copies[index];
      window.MushinRequestLoading.clean(original, node);
      window.MushinRegionLoading?.clean(original, node);
      if (node.hasAttribute("data-disabled-by-htmx")) {
        node.removeAttribute("disabled");
        node.removeAttribute("data-disabled-by-htmx");
      }
      node.classList.remove("htmx-request");
    });
    return copy.innerHTML;
  },
};
