// office.js — Phaser 3 Office Floor

const WORKER_COLORS = [
  0x3b82f6, // blue
  0x10b981, // emerald
  0xf59e0b, // amber
  0xef4444, // red
  0x8b5cf6, // violet
  0x06b6d4, // cyan
  0xf97316, // orange
  0xec4899, // pink
];

const OFFICE_SIZE = 800;
const OFFICE_PAD  = 60;  // margin from edge to first character
const MANAGER_X   = 80;  // fixed x position for manager column (left side)
const WORLD_H     = OFFICE_SIZE;

let scene = null;
let workers = {};     // id (string) → char object
let managerObj = null;
let tobyObj = null;
let routeGraphics = null;
let cursors = null;

// Mouse-drag pan state
let isDragging = false;
let dragStartX = 0;
let dragStartY = 0;
let dragCamStartX = 0;
let dragCamStartY = 0;

// ── Context menu ─────────────────────────────────────────────────────────────

const contextMenuRegistry = [];

function registerContextMenu(matchFn, items) {
  contextMenuRegistry.push({ matchFn, items });
}

function makeClickable(obj, id) {
  obj.circle.setInteractive();
  obj.circle.on('pointerdown', () => showContextMenu(id, obj));
}

function showContextMenu(id, obj) {
  const entries = contextMenuRegistry.filter(e => e.matchFn(id));
  if (!entries.length) return;

  const menu = document.getElementById('ctx-menu');
  menu.innerHTML = '';

  for (const entry of entries) {
    for (const item of entry.items) {
      const btn = document.createElement('button');
      btn.className = 'ctx-menu-item';
      btn.textContent = item.label;
      btn.addEventListener('click', () => {
        hideContextMenu();
        item.action();
      });
      menu.appendChild(btn);
    }
  }

  // Convert world coords → screen coords
  const cam = scene.cameras.main;
  const canvas = scene.game.canvas;
  const rect = canvas.getBoundingClientRect();
  const screenX = (obj.circle.x - cam.worldView.x) * cam.zoom + rect.left;
  const screenY = (obj.circle.y - cam.worldView.y) * cam.zoom + rect.top;

  // Keep menu on screen
  const menuW = 160;
  const left = Math.min(screenX - menuW / 2, window.innerWidth - menuW - 8);
  menu.style.left = Math.max(8, left) + 'px';
  menu.style.top  = (screenY + 28) + 'px';
  menu.style.display = 'block';

  // Dismiss on outside click (defer by one tick so this pointerdown doesn't count)
  const dismiss = (e) => {
    if (!menu.contains(e.target)) {
      hideContextMenu();
      document.removeEventListener('pointerdown', dismiss, true);
    }
  };
  setTimeout(() => document.addEventListener('pointerdown', dismiss, true), 0);
}

function hideContextMenu() {
  const menu = document.getElementById('ctx-menu');
  if (menu) menu.style.display = 'none';
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function initials(name) {
  return (name || '?')
    .split(/\s+/)
    .filter(Boolean)
    .map(p => p[0].toUpperCase())
    .join('')
    .slice(0, 2) || '?';
}

function getWorkerPos(slot) {
  const inner = OFFICE_SIZE - OFFICE_PAD * 2;
  const cols = 4;
  const col = slot % cols;
  const row = Math.floor(slot / cols);
  const cellW = inner / cols;
  const cellH = inner / Math.ceil(8 / cols);
  const x = OFFICE_PAD + col * cellW + cellW / 2;
  const y = OFFICE_PAD + row * cellH + cellH / 2;
  return { x, y };
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str || '';
  return d.innerHTML;
}

function renderMarkdown(text) {
  return DOMPurify.sanitize(marked.parse(text));
}

// ── Floor drawing ─────────────────────────────────────────────────────────────

function drawFloor() {
  const g = scene.add.graphics();
  // Grid lines
  g.lineStyle(1, 0xd1d5db, 0.3);
  for (let x = 0; x <= OFFICE_SIZE; x += 60) { g.moveTo(x, 0); g.lineTo(x, OFFICE_SIZE); }
  for (let y = 0; y <= OFFICE_SIZE; y += 60) { g.moveTo(0, y); g.lineTo(OFFICE_SIZE, y); }
  g.strokePath();
  // Border
  g.lineStyle(2, 0x9ca3af, 1);
  g.strokeRect(0, 0, OFFICE_SIZE, OFFICE_SIZE);
}

// ── Character creation ────────────────────────────────────────────────────────

function createChar(x, y, color, initStr) {
  const circle = scene.add.circle(x, y, 20, color).setStrokeStyle(2, 0xffffff);
  const label = scene.add.text(x, y, initStr, {
    fontSize: '13px', color: '#ffffff', fontStyle: 'bold',
  }).setOrigin(0.5);
  return { x, y, circle, label, thinkDots: null };
}

function makeTooltip(obj, name, role) {
  const tooltip = scene.add.container(0, 0).setVisible(false);
  const padding = 8;
  const nameTxt = scene.add.text(0, 0, name, { fontSize: '12px', color: '#1f2937', fontStyle: 'bold' });
  const roleTxt = scene.add.text(0, nameTxt.height + 2, role, { fontSize: '10px', color: '#6b7280', fontStyle: 'italic' });
  const tw = Math.max(nameTxt.width, roleTxt.width) + padding * 2;
  const th = nameTxt.height + 2 + roleTxt.height + padding * 2;
  const bg = scene.add.graphics();
  bg.fillStyle(0xffffff, 0.97);
  bg.lineStyle(1, 0xd1d5db, 1);
  bg.fillRoundedRect(0, 0, tw, th, 6);
  bg.strokeRoundedRect(0, 0, tw, th, 6);
  nameTxt.setPosition(padding, padding);
  roleTxt.setPosition(padding, padding + nameTxt.height + 2);
  tooltip.add([bg, nameTxt, roleTxt]);

  const { circle } = obj;
  circle.setInteractive();
  circle.on('pointerover', () => {
    const cx = circle.x - tw / 2;
    const cy = circle.y - 28 - th;
    tooltip.setPosition(cx, cy);
    tooltip.setVisible(true);
    tooltip.setDepth(100);
  });
  circle.on('pointerout', () => tooltip.setVisible(false));
}

function createWorkerChar(w) {
  const { x, y } = getWorkerPos(w.slot);
  const color = WORKER_COLORS[w.slot % WORKER_COLORS.length];
  const obj = createChar(x, y, color, initials(w.name));

  makeTooltip(obj, w.name, w.role);

  // Fade in from invisible
  [obj.circle, obj.label].forEach(t => t.setAlpha(0));
  scene.tweens.add({
    targets: [obj.circle, obj.label],
    alpha: 1,
    duration: 400,
  });

  obj.name = w.name;
  obj.role = w.role;
  obj.id   = String(w.id);
  makeClickable(obj, String(w.id));
  registerContextMenu(
    id => id === String(w.id),
    [{ label: `💬 Talk to ${w.name}`, action: () => openWorkerPanel(String(w.id), w.name, w.role) }]
  );
  workers[String(w.id)] = obj;
}

// ── Scene lifecycle ───────────────────────────────────────────────────────────

function buildScene() {
  drawFloor();
  routeGraphics = scene.add.graphics();

  // Manager desk (left column, vertically centered)
  managerObj = createChar(MANAGER_X, WORLD_H / 2, 0x1d4ed8, 'MS');
  makeTooltip(managerObj, 'Michael Scott', 'Regional Manager');
  makeClickable(managerObj, 'michael');

  // Toby's desk — same x-column as Manager, below it
  const tobyY = WORLD_H / 2 + 130;
  tobyObj = createChar(MANAGER_X, tobyY, 0x6b7280, 'TF');
  makeTooltip(tobyObj, 'Toby Flenderson', 'HR Representative');
  makeClickable(tobyObj, 'toby');

  scene.cameras.main.removeBounds();
  // Center the office square in the viewport on load
  scene.cameras.main.setScroll(
    OFFICE_SIZE / 2 - scene.scale.width / 2,
    OFFICE_SIZE / 2 - scene.scale.height / 2
  );

  syncWorkers();
}

function create() {
  console.log('[office] scene create');
  scene = this;
  cursors = this.input.keyboard.createCursorKeys();

  // Don't let Phaser swallow spacebar — breaks typing in input fields
  this.input.keyboard.removeCapture(Phaser.Input.Keyboard.KeyCodes.SPACE);

  window.addEventListener('keydown', (e) => {
    const tag = document.activeElement ? document.activeElement.tagName : '';
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;
    if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
      e.preventDefault();
    }
  });

  // Mouse-drag panning
  this.input.on('pointerdown', (pointer) => {
    if (pointer.button !== 0) return;
    isDragging = true;
    dragStartX = pointer.x;
    dragStartY = pointer.y;
    const cam = scene.cameras.main;
    dragCamStartX = cam.scrollX;
    dragCamStartY = cam.scrollY;
  });
  this.input.on('pointermove', (pointer) => {
    if (!isDragging || !pointer.isDown) return;
    const cam = scene.cameras.main;
    cam.scrollX = dragCamStartX - (pointer.x - dragStartX);
    cam.scrollY = dragCamStartY - (pointer.y - dragStartY);
  });
  this.input.on('pointerup', () => { isDragging = false; });

  // Register Toby's context menu
  registerContextMenu(id => id === 'toby', [
    { label: '👤 Hire Staff', action: openHirePanel },
  ]);

  // Register Michael's context menu
  registerContextMenu(id => id === 'michael', [
    { label: '💬 Talk with Michael', action: openMichaelPanel },
  ]);

  buildScene();

  window.officeScene = { syncWorkers };
  console.log('[office] officeScene registered');

  // Session ID for Michael panel
  michaelPanelSessionId = crypto.randomUUID();

  // Hire chat form
  const hireForm = document.getElementById('hire-chat-form');
  if (hireForm) {
    hireForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const input = document.getElementById('hire-input');
      const msg = input.value.trim();
      if (!msg || !hirePanelSessionId) return;
      input.value = '';
      await sendToToby(msg, true);
    });
  }

  // Michael chat form
  const michaelForm = document.getElementById('michael-chat-form');
  if (michaelForm) {
    michaelForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const input = document.getElementById('michael-input');
      const msg = input.value.trim();
      if (!msg) return;
      input.value = '';
      await sendToMichael(msg);
    });
  }

  // Worker direct-chat form
  const workerForm = document.getElementById('worker-chat-form');
  if (workerForm) {
    workerForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const input = document.getElementById('worker-input');
      const msg = input.value.trim();
      if (!msg) return;
      input.value = '';
      await sendToWorker(msg);
    });
  }

  // Resize handler — rebuild scene
  scene.scale.on('resize', () => {
    if (!scene) return;
    isDragging = false;
    scene.children.removeAll(true);
    workers = {};
    managerObj = null;
    tobyObj = null;
    routeGraphics = null;
    buildScene();
    hideContextMenu();
  });
}

const CAM_SPEED = 400; // world pixels per second

function update(time, delta) {
  if (!cursors || !scene) return;
  const dt  = delta / 1000;
  const cam = scene.cameras.main;
  const spd = CAM_SPEED * dt;
  if (cursors.left.isDown)  cam.scrollX -= spd;
  if (cursors.right.isDown) cam.scrollX += spd;
  if (cursors.up.isDown)    cam.scrollY -= spd;
  if (cursors.down.isDown)  cam.scrollY += spd;
}

// ── Worker sync ───────────────────────────────────────────────────────────────

async function syncWorkers() {
  console.log('[office] syncWorkers fetch');
  try {
    const resp = await fetch('/workers/positions');
    const list = await resp.json();
    renderWorkers(list);
    console.log('[office] syncWorkers ok count=' + list.length);
  } catch (e) {
    console.error('[office] syncWorkers failed:', e);
  }
}

function renderWorkers(list) {
  if (!scene) return;
  const newIds = new Set(list.map(w => String(w.id)));

  // Remove departed workers
  for (const [id, obj] of Object.entries(workers)) {
    if (!newIds.has(id)) {
      const targets = [obj.circle, obj.label];
      scene.tweens.add({
        targets,
        alpha: 0,
        duration: 400,
        onComplete: () => {
          targets.forEach(t => { if (t && t.active) t.destroy(); });
          if (obj.thinkDots) obj.thinkDots.forEach(d => { if (d && d.active) d.destroy(); });
          delete workers[id];
        },
      });
    }
  }

  // Add new workers
  for (const w of list) {
    if (!workers[String(w.id)]) {
      createWorkerChar(w);
    }
  }
}

// ── UI helpers ────────────────────────────────────────────────────────────────

function setInputEnabled(_enabled) {
  // task form removed
}

// ── Animations ────────────────────────────────────────────────────────────────

function flashRouteLine(from, to) {
  return new Promise(resolve => {
    if (!routeGraphics || !scene) { resolve(); return; }
    routeGraphics.clear();
    routeGraphics.lineStyle(2, 0x3b82f6, 0.8);
    routeGraphics.beginPath();
    routeGraphics.moveTo(from.circle.x, from.circle.y);
    routeGraphics.lineTo(to.circle.x, to.circle.y);
    routeGraphics.strokePath();
    scene.tweens.add({
      targets: routeGraphics,
      alpha: 0,
      duration: 600,
      delay: 400,
      onComplete: () => {
        routeGraphics.clear();
        routeGraphics.alpha = 1;
        resolve();
      },
    });
  });
}

function panCamera(x, y) {
  if (!scene) return;
  scene.cameras.main.pan(x, y, 500, 'Power2');
}

function startThinkDots(obj) {
  if (!obj || obj.thinkDots || !scene) return;
  const cx = obj.circle.x;
  const cy = obj.circle.y - 34;
  const dots = [];
  for (let i = 0; i < 3; i++) {
    const dot = scene.add.circle(cx - 8 + i * 8, cy, 4, 0x9ca3af);
    scene.tweens.add({
      targets: dot,
      y: cy - 10,
      duration: 400,
      yoyo: true,
      repeat: -1,
      delay: i * 150,
      ease: 'Sine.easeInOut',
    });
    dots.push(dot);
  }
  obj.thinkDots = dots;
}

function stopThinkDots(obj) {
  if (!obj || !obj.thinkDots) return;
  for (const dot of obj.thinkDots) {
    if (scene && scene.tweens) scene.tweens.killTweensOf(dot);
    if (dot && dot.active) dot.destroy();
  }
  obj.thinkDots = null;
}

function showSpeechBubble(obj, text) {
  if (!scene || !obj) return;
  const cx = obj.circle.x;
  const cy = obj.circle.y;
  const maxWidth = 220;
  const padding = 10;

  // Measure text first
  const tmp = scene.add.text(0, -9999, text, {
    fontSize: '12px',
    color: '#1f2937',
    wordWrap: { width: maxWidth },
  });
  const tw = Math.max(tmp.width + padding * 2, 80);
  const th = tmp.height + padding * 2;
  tmp.destroy();

  // Position bubble above character circle
  const bx = cx - tw / 2;
  const by = cy - 80 - th;

  const bubble = scene.add.graphics();
  bubble.fillStyle(0xffffff, 0.97);
  bubble.lineStyle(1.5, 0xd1d5db, 1);
  bubble.fillRoundedRect(bx, by, tw, th, 8);
  bubble.strokeRoundedRect(bx, by, tw, th, 8);
  // Tail triangle
  bubble.fillStyle(0xffffff, 0.97);
  bubble.fillTriangle(cx - 6, by + th, cx + 6, by + th, cx, by + th + 9);
  bubble.setAlpha(0);

  const textObj = scene.add.text(cx, by + padding, text, {
    fontSize: '12px',
    color: '#1f2937',
    wordWrap: { width: maxWidth },
    align: 'left',
  }).setOrigin(0.5, 0).setAlpha(0);

  scene.tweens.add({ targets: bubble, alpha: 1, duration: 250 });
  scene.tweens.add({ targets: textObj, alpha: 1, duration: 200, delay: 100 });

  // Auto-dismiss after 8 s
  setTimeout(() => {
    if (!scene || !scene.tweens) return;
    scene.tweens.add({
      targets: [bubble, textObj],
      alpha: 0,
      duration: 500,
      onComplete: () => {
        if (bubble.active) bubble.destroy();
        if (textObj.active) textObj.destroy();
      },
    });
  }, 8000);
}

// ── Hire panel ────────────────────────────────────────────────────────────────

let hirePanelSessionId    = null;
let michaelPanelSessionId = null;
let workerPanelWorkerId   = null;
let workerPanelSessionId  = null;
const workerPanelSessions = {};  // worker_id -> session_id (persists across open/close)

function openHirePanel() {
  hideContextMenu();
  hirePanelSessionId = crypto.randomUUID();

  // Reset panel state
  document.getElementById('hire-panel').classList.remove('hidden');
  document.getElementById('hire-chat-area').style.display = '';
  document.getElementById('hire-candidates').classList.add('hidden');
  document.getElementById('hire-chat-messages').innerHTML = '';
  document.getElementById('hire-status').textContent = '';
  document.getElementById('hire-input').value = '';

  // Prime Toby silently — his first question appears but the greeting is not shown
  sendToToby('Hello, I need to hire someone.', false);
}

function closeHirePanel() {
  if (hirePanelSessionId) {
    fetch(`/toby/session/${hirePanelSessionId}`, { method: 'DELETE' }).catch(() => {});
    hirePanelSessionId = null;
  }
  document.getElementById('hire-panel').classList.add('hidden');
}

function openMichaelPanel() {
  hideContextMenu();
  document.getElementById('michael-panel').classList.remove('hidden');
  document.getElementById('michael-input').focus();
}

function closeMichaelPanel() {
  document.getElementById('michael-panel').classList.add('hidden');
}

function appendMichaelMsg(text, who) {
  const el = document.createElement('div');
  el.className = `michael-msg michael-msg--${who}`;
  if (who === 'you') {
    el.textContent = text;
  } else {
    el.classList.add('msg-content');
    el.innerHTML = renderMarkdown(text);
  }
  const container = document.getElementById('michael-chat-messages');
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
  return el;
}

function scrollMichaelChat() {
  const el = document.getElementById('michael-chat-messages');
  if (el) el.scrollTop = el.scrollHeight;
}

async function sendToMichael(message) {
  appendMichaelMsg(message, 'you');
  const placeholder = appendMichaelMsg('…', 'michael');
  startThinkDots(managerObj);

  try {
    const resp = await fetch('/michael/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ michael_session_id: michaelPanelSessionId, message }),
    });
    const data = await resp.json();
    placeholder.innerHTML = renderMarkdown(data.message);
    scrollMichaelChat();
  } catch (e) {
    console.error('[office] michael chat error:', e);
    placeholder.textContent = 'Something went wrong. Please try again.';
  } finally {
    stopThinkDots(managerObj);
  }
}

function openWorkerPanel(workerId, name, role) {
  hideContextMenu();
  workerPanelWorkerId = workerId;
  if (!workerPanelSessions[workerId]) {
    workerPanelSessions[workerId] = crypto.randomUUID();
    // New session for this worker: clear prior chat and start with a greeting
    const container = document.getElementById('worker-chat-messages');
    if (container) container.innerHTML = '';
    greetWorker(workerId, workerPanelSessions[workerId]);
  }
  workerPanelSessionId = workerPanelSessions[workerId];
  document.getElementById('worker-panel-name').textContent = name;
  document.getElementById('worker-panel-role').textContent = role;
  document.getElementById('worker-panel').classList.remove('hidden');
  document.getElementById('worker-input').focus();
}

function closeWorkerPanel() {
  document.getElementById('worker-panel').classList.add('hidden');
}

function appendWorkerMsg(text, who) {
  const el = document.createElement('div');
  el.className = `michael-msg michael-msg--${who}`;
  if (who === 'you') {
    el.textContent = text;
  } else {
    el.classList.add('msg-content');
    el.innerHTML = renderMarkdown(text);
  }
  const container = document.getElementById('worker-chat-messages');
  container.appendChild(el);
  container.scrollTop = container.scrollHeight;
  return el;
}

async function sendToWorker(message) {
  appendWorkerMsg(message, 'you');
  const placeholder = appendWorkerMsg('…', 'worker');
  const workerObj = workers[workerPanelWorkerId];
  if (workerObj) startThinkDots(workerObj);

  try {
    const resp = await fetch(`/worker/${workerPanelWorkerId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: workerPanelSessionId, message }),
    });
    const data = await resp.json();
    placeholder.innerHTML = renderMarkdown(data.message);
    const container = document.getElementById('worker-chat-messages');
    container.scrollTop = container.scrollHeight;
  } catch (e) {
    console.error('[office] worker chat error:', e);
    placeholder.textContent = 'Something went wrong. Please try again.';
  } finally {
    if (workerObj) stopThinkDots(workerObj);
  }
}

async function greetWorker(workerId, sessionId) {
  const placeholder = appendWorkerMsg('…', 'worker');
  const workerObj = workers[workerId];
  if (workerObj) startThinkDots(workerObj);

  try {
    const resp = await fetch(`/worker/${workerId}/greet`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    const data = await resp.json();
    placeholder.innerHTML = renderMarkdown(data.message);
    const container = document.getElementById('worker-chat-messages');
    if (container) container.scrollTop = container.scrollHeight;
  } catch (e) {
    console.error('[office] worker greet error:', e);
    placeholder.textContent = 'Something went wrong. Please try again.';
  } finally {
    if (workerObj) stopThinkDots(workerObj);
  }
}

function appendHireMsg(text, who) {
  const el = document.createElement('div');
  el.className = `hire-msg hire-msg--${who}`;
  if (who === 'you') {
    el.textContent = text;
  } else {
    el.classList.add('msg-content');
    el.innerHTML = renderMarkdown(text);
  }
  const container = document.getElementById('hire-chat-messages');
  container.appendChild(el);
  scrollHireChat();
  return el;
}

function scrollHireChat() {
  const el = document.getElementById('hire-chat-messages');
  if (el) el.scrollTop = el.scrollHeight;
}

async function sendToToby(message, isUserVisible) {
  if (!hirePanelSessionId) return;

  if (isUserVisible && message) {
    appendHireMsg(message, 'you');
  }

  // Thinking placeholder
  const placeholder = appendHireMsg('…', 'toby');

  try {
    const resp = await fetch('/toby/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hire_session_id: hirePanelSessionId, message }),
    });
    const data = await resp.json();
    placeholder.textContent = data.message;
    scrollHireChat();

    if (data.ready) {
      startSearchingAnimation();
      document.getElementById('hire-status').textContent = 'Toby is searching for candidates…';

      const candResp = await fetch('/toby/candidates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hire_session_id: hirePanelSessionId }),
      });
      const candData = await candResp.json();

      stopSearchingAnimation();
      document.getElementById('hire-status').textContent = '';
      showCandidateCards(candData.candidates || []);
    }
  } catch (e) {
    console.error('[office] toby chat error:', e);
    placeholder.textContent = 'Something went wrong. Please try again.';
  }
}

function showCandidateCards(candidates) {
  const chatArea = document.getElementById('hire-chat-area');
  const candidatesArea = document.getElementById('hire-candidates');
  chatArea.style.display = 'none';
  candidatesArea.classList.remove('hidden');
  candidatesArea.innerHTML = '';

  if (!candidates.length) {
    candidatesArea.innerHTML =
      '<p class="text-sm text-gray-400 text-center py-8">No candidates found. Please try again.</p>';
    return;
  }

  candidates.forEach((c) => {
    const card = document.createElement('div');
    card.className = 'candidate-card';
    card.innerHTML = `
      <p class="font-semibold text-sm text-gray-800">${escapeHtml(c.name)}</p>
      <p class="text-xs text-blue-600 font-medium mb-1">${escapeHtml(c.role)}</p>
      <p class="text-xs text-gray-500 italic mb-2">"${escapeHtml(c.tagline)}"</p>
      <p class="text-xs text-gray-600 leading-relaxed">${escapeHtml(c.system_prompt)}</p>
    `;
    const btn = document.createElement('button');
    btn.className = 'candidate-card__btn';
    btn.textContent = `Hire ${c.name.split(' ')[0]}`;
    btn.addEventListener('click', () => hireCandidate(c));
    card.appendChild(btn);
    candidatesArea.appendChild(card);
  });
}

async function hireCandidate(c) {
  try {
    await fetch('/toby/hire', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: c.name,
        role: c.role,
        system_prompt: c.system_prompt,
        hire_session_id: hirePanelSessionId,
      }),
    });

    // Bounce animation on Toby's avatar
    if (tobyObj && scene) {
      const origY = tobyObj.circle.y;
      scene.tweens.add({
        targets: tobyObj.circle,
        y: origY - 15,
        duration: 150,
        yoyo: true,
        repeat: 1,
        onComplete: () => { tobyObj.circle.y = origY; },
      });
    }

    closeHirePanel();
    syncWorkers();
  } catch (e) {
    console.error('[office] hireCandidate error:', e);
  }
}

function startSearchingAnimation() {
  if (tobyObj) startThinkDots(tobyObj);
}

function stopSearchingAnimation() {
  if (tobyObj) stopThinkDots(tobyObj);
}

// ── Panel resize & fullscreen ─────────────────────────────────────────────────

let _resizingPanel = null;

function initPanelResize(panelId) {
  const panel  = document.getElementById(panelId);
  const handle = panel.querySelector('.panel-resize-handle');
  handle.addEventListener('mousedown', (e) => {
    _resizingPanel = panel;
    handle.classList.add('panel-resize-handle--active');
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });
}

document.addEventListener('mousemove', (e) => {
  if (!_resizingPanel) return;
  const newWidth = window.innerWidth - e.clientX;
  const clamped  = Math.max(320, Math.min(newWidth, Math.round(window.innerWidth * 0.85)));
  _resizingPanel.style.width = clamped + 'px';
});

document.addEventListener('mouseup', () => {
  if (!_resizingPanel) return;
  _resizingPanel.querySelector('.panel-resize-handle')
    ?.classList.remove('panel-resize-handle--active');
  _resizingPanel = null;
  document.body.style.userSelect = '';
});

function togglePanelFullscreen(panelId) {
  const panel = document.getElementById(panelId);
  const isFs  = panel.classList.toggle('panel--fullscreen');
  panel.querySelector('.panel-fullscreen-btn').textContent = isFs ? '⊡' : '⤢';
}

document.addEventListener('DOMContentLoaded', () => {
  initPanelResize('michael-panel');
  initPanelResize('worker-panel');
  initPanelResize('hire-panel');
});

// ── Phaser game boot ──────────────────────────────────────────────────────────

const config = {
  type: Phaser.AUTO,
  parent: 'office-floor',
  backgroundColor: '#fef9ef',
  scale: {
    mode: Phaser.Scale.RESIZE,
    autoCenter: Phaser.Scale.CENTER_BOTH,
  },
  scene: { create, update },
};

new Phaser.Game(config);
