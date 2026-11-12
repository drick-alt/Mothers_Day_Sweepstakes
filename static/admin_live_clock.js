(function () {
  function get(id) {
    return document.getElementById(id);
  }

  function browserTimeZone() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || '';
    } catch (e) {
      return '';
    }
  }

  function tickClock() {
    var now = new Date();
    var time = now.toLocaleTimeString([], {
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit'
    });
    var date = now.toLocaleDateString([], {
      weekday: 'short',
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
    var tz = browserTimeZone();
    var timeEl = get('admin-live-clock-time');
    var dateEl = get('admin-live-clock-date');
    if (timeEl) timeEl.textContent = time;
    if (dateEl) dateEl.textContent = tz ? (date + ' ' + tz) : date;
  }

  function setStatus(isLive) {
    var statusEl = get('admin-live-clock-status');
    var noteEl = get('admin-live-clock-note');
    if (!statusEl) return;
    if (isLive) {
      statusEl.textContent = 'Live';
      statusEl.style.background = '#064e3b';
      statusEl.style.color = '#86efac';
      statusEl.style.borderColor = 'rgba(34,197,94,.75)';
      if (noteEl) noteEl.textContent = 'Health check OK · refresh not required';
    } else {
      statusEl.textContent = 'Closed';
      statusEl.style.background = '#450a0a';
      statusEl.style.color = '#fecaca';
      statusEl.style.borderColor = 'rgba(248,113,113,.85)';
      if (noteEl) noteEl.textContent = 'Health check failed · refresh or check connection';
    }
  }

  function healthUrl() {
    var box = get('admin-live-clock');
    return (box && box.getAttribute('data-health-url')) || '/healthz';
  }

  function pingHealth() {
    if (!window.fetch) {
      setStatus(true);
      return;
    }
    fetch(healthUrl() + '?live_clock=' + Date.now(), {
      cache: 'no-store',
      credentials: 'same-origin'
    }).then(function (res) {
      setStatus(res.ok);
    }).catch(function () {
      setStatus(false);
    });
  }

  function start() {
    if (!get('admin-live-clock')) return;
    tickClock();
    pingHealth();
    window.setInterval(tickClock, 1000);
    window.setInterval(pingHealth, 5000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
