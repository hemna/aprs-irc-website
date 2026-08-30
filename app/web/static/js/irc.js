/**
 * APRS IRC Website — frontend logic
 * Vanilla JS, no jQuery, no implicit globals.
 * Addresses issues #9 (XSS), #10 (implicit globals), #11 (console.log),
 * #12 (meta-refresh) and #13 (live polling).
 */

'use strict';

// ── Callsign colour palette (deterministic hash → CSS custom property) ──────

const CALLSIGN_PALETTE = [
    '#79c0ff', '#7ee787', '#ffa657', '#d2a8ff',
    '#39d353', '#58a6ff', '#ff7b72', '#f0883e',
];

function callsignColour(name) {
    let hash = 0;
    for (let i = 0; i < name.length; i++) {
        hash = name.charCodeAt(i) + ((hash << 5) - hash);
    }
    return CALLSIGN_PALETTE[Math.abs(hash) % CALLSIGN_PALETTE.length];
}

// ── Safe DOM text helper (prevents XSS — issue #9) ───────────────────────────

function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = String(text);
    return d.innerHTML;
}

// ── Date formatting (replaces jquery-date.js) ─────────────────────────────────

function formatTimestamp(unixSeconds) {
    const d = new Date(unixSeconds * 1000);
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ` +
           `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

// ── State ─────────────────────────────────────────────────────────────────────

let activeChannel = null;              // currently-displayed channel name (no #)

// Track the newest message timestamp we have seen per channel so we can
// show a dot when new messages arrive while the user is on another pane.
const channelLastSeen   = {};          // channel → unix timestamp (last shown)
const channelKnownMsgTs = {};          // channel → Set of timestamps already rendered

// ── DOM helpers ───────────────────────────────────────────────────────────────

function channelId(name) {
    // Strip leading # and turn special chars into safe id suffixes
    return 'ch_' + name.replace(/^#/, '').replace(/[^a-zA-Z0-9_-]/g, '_');
}

function paneEl(name)      { return document.getElementById(channelId(name)); }
function feedEl(name)      { return document.getElementById(channelId(name) + '_feed'); }
function usersEl(name)     { return document.getElementById(channelId(name) + '_users'); }
function channelBtnEl(name){ return document.getElementById(channelId(name) + '_btn'); }
function unreadDotEl(name) { return document.getElementById(channelId(name) + '_dot'); }

// ── Channel list (sidebar) ────────────────────────────────────────────────────

function renderChannelList(channelData) {
    const list = document.getElementById('channelList');
    list.innerHTML = '';
    channelData.forEach((ch, idx) => {
        const li  = document.createElement('li');
        const btn = document.createElement('button');
        btn.className   = 'channel-btn' + (idx === 0 ? ' active' : '');
        btn.id          = channelId(ch.name) + '_btn';
        btn.setAttribute('aria-selected', idx === 0 ? 'true' : 'false');
        btn.onclick     = () => selectChannel(ch.name);

        const hash = document.createElement('span');
        hash.className = 'ch-hash';
        hash.textContent = '#';

        const label = document.createElement('span');
        label.textContent = ch.name.replace(/^#/, '');

        const dot = document.createElement('span');
        dot.className = 'unread-dot';
        dot.id        = channelId(ch.name) + '_dot';
        dot.hidden    = true;

        btn.append(hash, label, dot);
        li.appendChild(btn);
        list.appendChild(li);
    });
}

// ── Channel panes ─────────────────────────────────────────────────────────────

function renderChannelPanes(channelData) {
    const container = document.getElementById('channelPanes');
    container.innerHTML = '';

    if (channelData.length === 0) {
        container.innerHTML = `
          <div class="no-channels">
            <div class="no-channels-title">No channels yet</div>
            <div>Send <code>/join #lounge</code> to <strong>IRC</strong> via APRS to create one.</div>
          </div>`;
        return;
    }

    channelData.forEach((ch, idx) => {
        const pane = document.createElement('div');
        pane.className = 'channel-pane' + (idx === 0 ? ' visible' : '');
        pane.id        = channelId(ch.name);

        // Message feed
        const feed = document.createElement('div');
        feed.className = 'msg-feed';
        feed.id        = channelId(ch.name) + '_feed';

        // Users panel
        const users = document.createElement('div');
        users.className = 'users-panel';
        users.id        = channelId(ch.name) + '_users';
        users.innerHTML = '<div class="users-heading">Active</div>';

        pane.append(feed, users);
        container.appendChild(pane);

        // Seed known timestamps so we don't re-render initial messages on poll
        channelKnownMsgTs[ch.name] = new Set();

        renderMessages(ch.name, ch.messages || [], false);
        renderUsers(ch.name, ch.users   || []);
    });
}

// ── Render messages ───────────────────────────────────────────────────────────

function renderMessages(channelName, messages, append) {
    const feed = feedEl(channelName);
    if (!feed) return;

    const knownTs = channelKnownMsgTs[channelName] || (channelKnownMsgTs[channelName] = new Set());

    if (!append) {
        feed.innerHTML = '';
    }

    if (messages.length === 0 && !append) {
        feed.innerHTML = `<div class="empty-state">
            <span class="empty-icon">📻</span>
            <span>No messages yet</span>
        </div>`;
        return;
    }

    // Remove empty-state placeholder if present
    const empty = feed.querySelector('.empty-state');
    if (empty) empty.remove();

    messages.forEach(msg => {
        const ts = msg.timestamp;
        if (knownTs.has(ts)) return;   // already rendered
        knownTs.add(ts);

        const row  = document.createElement('div');
        row.className = 'msg-row';

        const timeEl = document.createElement('span');
        timeEl.className = 'msg-time';
        timeEl.textContent = formatTimestamp(ts);

        const callEl = document.createElement('span');
        callEl.className = 'msg-call';
        callEl.style.color = callsignColour(msg.from_call);
        callEl.title = msg.from_call;
        callEl.textContent = msg.from_call;

        const textEl = document.createElement('span');
        textEl.className = 'msg-text';
        // Use textContent assignment — safe against XSS (issue #9)
        textEl.textContent = msg.message_text;

        row.append(timeEl, callEl, textEl);
        feed.appendChild(row);
    });

    // Scroll to bottom
    feed.scrollTop = feed.scrollHeight;
}

// ── Render users ──────────────────────────────────────────────────────────────

function renderUsers(channelName, users) {
    const panel = usersEl(channelName);
    if (!panel) return;
    panel.innerHTML = '<div class="users-heading">Active</div>';
    (users || []).forEach(callsign => {
        const entry = document.createElement('span');
        entry.className = 'user-entry';
        entry.style.color = callsignColour(callsign);
        entry.textContent = callsign;
        panel.appendChild(entry);
    });
}

// ── Channel switching ─────────────────────────────────────────────────────────

function selectChannel(name) {
    if (activeChannel === name) return;

    // Hide current pane
    if (activeChannel) {
        const prev = paneEl(activeChannel);
        if (prev) prev.classList.remove('visible');
        const prevBtn = channelBtnEl(activeChannel);
        if (prevBtn) {
            prevBtn.classList.remove('active');
            prevBtn.setAttribute('aria-selected', 'false');
        }
    }

    // Show new pane
    activeChannel = name;
    const next = paneEl(name);
    if (next) next.classList.add('visible');
    const nextBtn = channelBtnEl(name);
    if (nextBtn) {
        nextBtn.classList.add('active');
        nextBtn.setAttribute('aria-selected', 'true');
    }

    // Clear unread dot
    const dot = unreadDotEl(name);
    if (dot) dot.hidden = true;
}

// ── Help panel toggle ─────────────────────────────────────────────────────────

function initHelp() {
    const btn   = document.getElementById('helpToggle');
    const panel = document.getElementById('helpPanel');
    if (!btn || !panel) return;

    btn.addEventListener('click', () => {
        const expanded = btn.getAttribute('aria-expanded') === 'true';
        btn.setAttribute('aria-expanded', String(!expanded));
        panel.hidden = expanded;
    });
}

// ── Stats polling ─────────────────────────────────────────────────────────────

function pollStats() {
    fetch('/stats')
        .then(r => r.ok ? r.json() : null)
        .then(data => {
            if (!data) return;
            const aprsd = (data.stats || {}).APRSDStats || {};
            const versionEl = document.getElementById('version');
            const uptimeEl  = document.getElementById('uptime');
            if (versionEl && aprsd.version) versionEl.textContent = 'v' + aprsd.version;
            if (uptimeEl  && aprsd.uptime)  uptimeEl.textContent  = aprsd.uptime;
        })
        .catch(() => {});  // silently ignore — stats are non-critical
}

// ── SSE live updates (closes #23) ────────────────────────────────────────────

function startSSE() {
    const es = new EventSource('/events');

    // Each channel gets its own named event (channel name without leading #).
    // The server emits:  event: lounge\ndata: [{...}, ...]\n\n
    if (typeof channels !== 'undefined') {
        channels.forEach(ch => {
            const name = ch.name.replace(/^#/, '');
            es.addEventListener(name, e => {
                let messages;
                try { messages = JSON.parse(e.data); } catch { return; }
                if (!Array.isArray(messages) || messages.length === 0) return;

                renderMessages(ch.name, messages, true);

                // Show unread dot when this isn't the active channel
                if (ch.name !== activeChannel) {
                    const dot = unreadDotEl(ch.name);
                    if (dot) dot.hidden = false;
                }
            });
        });
    }

    es.onerror = () => {
        // Browser will auto-reconnect on error; nothing to do here.
    };
}

// ── Initialise ────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    const data = (typeof channels !== 'undefined') ? channels : [];

    renderChannelList(data);
    renderChannelPanes(data);

    if (data.length > 0) {
        activeChannel = data[0].name;
    }

    initHelp();

    // Stats still polled (lightweight, non-critical)
    pollStats();
    setInterval(pollStats, 60_000);

    // Live message updates via SSE (replaces 30s polling)
    startSSE();
});
