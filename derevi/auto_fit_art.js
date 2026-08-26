(() => {
  const fit = () => {
    if (typeof art === 'undefined' || typeof autoFitArt !== 'function') return;
    const run = () => {
      autoFitArt();
      art.onload = artEdited;
      if (typeof card !== 'undefined') card.onload = null;
    };
    if (art.complete && art.naturalWidth > 0) {
      setTimeout(run, 0);
    } else {
      art.onload = run;
    }
  };
  fit();
})();
