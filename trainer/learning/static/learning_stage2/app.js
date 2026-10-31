(() => {
  const openButton = document.getElementById('chat-open');
  const panel = document.getElementById('chat');
  if (!openButton || !panel) return;
  const closeButton = document.getElementById('chat-close');
  const backdrop = document.getElementById('chat-backdrop');
  const main = document.querySelector('.workspace');
  const header = document.querySelector('body > .top');
  const footer = document.querySelector('.foot');
  let previousFocus;
  function setOpen(open) {
    if (open) previousFocus = document.activeElement;
    panel.hidden = !open;
    backdrop.hidden = !open;
    openButton.hidden = open;
    openButton.setAttribute('aria-expanded', String(open));
    for (const el of [main, header, footer]) if (el) el.inert = open;
    document.body.style.overflow = open ? 'hidden' : '';
    if (open) closeButton.focus();
    else (previousFocus?.isConnected ? previousFocus : openButton).focus();
  }
  openButton.addEventListener('click', () => setOpen(true));
  closeButton.addEventListener('click', () => setOpen(false));
  backdrop.addEventListener('click', () => setOpen(false));
  document.addEventListener('keydown', e => {
    if (panel.hidden) return;
    if (e.key === 'Escape') setOpen(false);
    if (e.key === 'Tab') { const items=[...panel.querySelectorAll('button:not(:disabled),textarea:not(:disabled),input:not([hidden]):not([type=file])')].filter(n=>n.getClientRects().length);const first=items[0],last=items[items.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();} }
  });
  // Revalidate the server session on a restored history entry after logout.
  window.addEventListener('pageshow', e => { if (e.persisted) window.location.reload(); });
})();
