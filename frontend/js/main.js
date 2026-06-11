// =============================================================================
// CollabBoard — Main JS Entry Point
// =============================================================================
// Owner : M2 (Frontend Engineer)
// Sprint: Day 1–2
//
// Initializes the application shell, binds core DOM elements, wires up
// toolbar interactions (tool switching, color picker sync, sidebar toggle),
// and integrates the NetworkManager for WebSocket connectivity.
//
// Day 2 additions:
//   - NetworkManager integration (auto-connect, status bar updates)
//   - AppState expanded with username, userId, roomId
//   - Connection state reflected in status bar indicator
//
// Reference:
//   - IMPLEMENTATION_PLAN.md §F1
//   - SPECIFICATION.md §6.2
//   - WEBSOCKET_PROTOCOL_EXTENSION.md §1, §9
// =============================================================================

'use strict';

/**
 * CollabBoard — Application State
 *
 * Central state object for the entire frontend application.
 * Expanded on Day 2 with network-related fields.
 */
const AppState = window.AppState = {
    /** @type {'select'|'pencil'|'text'|'rectangle'|'circle'|'line'|'arrow'|'heart'|'image'} */
    activeTool: 'select',

    /** Current stroke colour (hex) */
    strokeColor: '#1a1a2e',

    /** Current stroke width (px) */
    strokeWidth: 4,

    /** Current theme */
    theme: 'light',

    /** Whether the sidebar is open */
    sidebarOpen: false,

    // -- Day 2: Network state ------------------------------------------------

    /** Display name used for hello handshake */
    username: null,

    /** UUID assigned by server on hello_ack */
    userId: null,

    /** Current room ID (null = not in a room) */
    roomId: null,
};

// ---------------------------------------------------------------------------
// DOM References
// ---------------------------------------------------------------------------
const DOM = {
    // Core containers
    app:              document.getElementById('app'),
    canvasContainer:  document.getElementById('canvas-container'),
    canvas:           document.getElementById('canvas'),
    cursorOverlay:    document.getElementById('cursor-overlay'),

    // Toolbar
    toolbar:          document.getElementById('toolbar'),
    toolbarRoomName:  document.getElementById('toolbar-room-name'),
    toolButtons:      document.querySelectorAll('.toolbar__tool'),
    colorInput:       document.getElementById('tool-color'),
    colorSwatch:      document.getElementById('tool-color-swatch'),
    strokeWidthSelect:document.getElementById('tool-stroke-width'),
    sidebarToggle:    document.getElementById('toolbar-sidebar-toggle'),
    menuBtn:          document.getElementById('toolbar-menu-btn'),
    moreBtn:          document.getElementById('toolbar-more-btn'),
    participants:     document.getElementById('toolbar-participants'),

    // Sidebar
    sidebar:          document.getElementById('sidebar'),
    sidebarCloseBtn:  document.getElementById('sidebar-close-btn'),
    participantList:  document.getElementById('sidebar-participant-list'),

    // Status bar
    statusBar:        document.getElementById('status-bar'),
    statusConnection: document.getElementById('status-connection'),
    statusRoom:       document.getElementById('status-room'),
    statusSave:       document.getElementById('status-save'),
    statusUsers:      document.getElementById('status-users'),

    // Modal
    roomModal:        document.getElementById('room-modal'),
    modalUsername:     document.getElementById('modal-username'),
    modalRoomCode:    document.getElementById('modal-room-code'),
    modalError:       document.getElementById('modal-error'),
    modalJoinBtn:     document.getElementById('modal-join-btn'),
    modalCreateBtn:   document.getElementById('modal-create-btn'),
};

// ---------------------------------------------------------------------------
// Tool Switching
// ---------------------------------------------------------------------------
function setActiveTool(toolName) {
    AppState.activeTool = toolName;

    DOM.toolButtons.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tool === toolName);
    });

    // Update canvas cursor style based on tool
    const cursorMap = {
        select:    'default',
        pencil:    'crosshair',
        text:      'text',
        rectangle: 'crosshair',
        circle:    'crosshair',
        line:      'crosshair',
        arrow:     'crosshair',
        heart:     'crosshair',
        image:     'pointer',
    };
    DOM.canvas.style.cursor = cursorMap[toolName] || 'default';

    console.log(`[CollabBoard] Active tool: ${toolName}`);
}

DOM.toolButtons.forEach(btn => {
    btn.addEventListener('click', () => {
        setActiveTool(btn.dataset.tool);
    });
});

// ---------------------------------------------------------------------------
// Color Picker Sync
// ---------------------------------------------------------------------------
function syncColorSwatch() {
    const color = DOM.colorInput.value;
    DOM.colorSwatch.style.background = color;
    AppState.strokeColor = color;
}

DOM.colorInput.addEventListener('input', syncColorSwatch);
// Initialize swatch on load
syncColorSwatch();

// ---------------------------------------------------------------------------
// Stroke Width
// ---------------------------------------------------------------------------
DOM.strokeWidthSelect.addEventListener('change', (e) => {
    AppState.strokeWidth = parseInt(e.target.value, 10);
    console.log(`[CollabBoard] Stroke width: ${AppState.strokeWidth}px`);
});

// ---------------------------------------------------------------------------
// Sidebar Toggle
// ---------------------------------------------------------------------------
function toggleSidebar(forceState) {
    const shouldOpen = typeof forceState === 'boolean'
        ? forceState
        : !AppState.sidebarOpen;

    AppState.sidebarOpen = shouldOpen;
    DOM.sidebar.classList.toggle('open', shouldOpen);
    DOM.sidebar.setAttribute('aria-hidden', String(!shouldOpen));
}

DOM.sidebarToggle.addEventListener('click', () => toggleSidebar());
DOM.sidebarCloseBtn.addEventListener('click', () => toggleSidebar(false));

// ---------------------------------------------------------------------------
// Theme Toggle (Ctrl+Shift+D for dev convenience)
// ---------------------------------------------------------------------------
function setTheme(theme) {
    AppState.theme = theme;
    document.documentElement.setAttribute('data-theme', theme);
    console.log(`[CollabBoard] Theme: ${theme}`);
}

document.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.shiftKey && e.key === 'D') {
        e.preventDefault();
        setTheme(AppState.theme === 'light' ? 'dark' : 'light');
    }
});

// ---------------------------------------------------------------------------
// Keyboard Shortcuts (tool hotkeys)
// ---------------------------------------------------------------------------
document.addEventListener('keydown', (e) => {
    // Don't capture when typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    const keyMap = {
        'v': 'select',
        'p': 'pencil',
        't': 'text',
        's': 'rectangle',
        'i': 'image',
    };

    const tool = keyMap[e.key.toLowerCase()];
    if (tool) {
        e.preventDefault();
        setActiveTool(tool);
    }

    // 'u' toggles sidebar
    if (e.key.toLowerCase() === 'u') {
        e.preventDefault();
        toggleSidebar();
    }
});

// ---------------------------------------------------------------------------
// Canvas Resize Handler
// ---------------------------------------------------------------------------
function handleResize() {
    // The CSS handles visual scaling (width/height: 100%).
    // The intrinsic canvas dimensions (1920x1080) remain fixed.
    // This handler is a hook for future coordinate mapping logic.
}

window.addEventListener('resize', handleResize);

// ---------------------------------------------------------------------------
// Network Integration (Day 2)
// ---------------------------------------------------------------------------

/** @type {NetworkManager} Singleton network manager */
const network = window.network = new NetworkManager();

/**
 * Generate a temporary username for auto-connect.
 * Will be replaced by the Room Modal input on Day 3.
 * @returns {string}
 */
function _generateTempUsername() {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let suffix = '';
    for (let i = 0; i < 4; i++) {
        suffix += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return `User_${suffix}`;
}

/**
 * Update the status bar connection indicator.
 * @param {'connected'|'disconnected'|'connecting'} visualState
 * @param {string} label
 */
function updateConnectionStatus(visualState, label) {
    const el = DOM.statusConnection;
    // Remove all state classes
    el.classList.remove(
        'status-bar__indicator--connected',
        'status-bar__indicator--disconnected',
        'status-bar__indicator--connecting',
    );
    el.classList.add(`status-bar__indicator--${visualState}`);
    // Update text (preserve the dot span)
    const dot = el.querySelector('.status-bar__dot');
    el.textContent = '';
    if (dot) el.appendChild(dot);
    el.appendChild(document.createTextNode(' ' + label));
}

// -- Subscribe to network state changes --------------------------------------
network.on('state_change', (newState, _oldState) => {
    switch (newState) {
        case ConnectionState.CONNECTING:
            updateConnectionStatus('connecting', 'Connecting…');
            break;
        case ConnectionState.CONNECTED:
            updateConnectionStatus('connecting', 'Handshaking…');
            break;
        case ConnectionState.IDENTIFIED:
            updateConnectionStatus('connected', 'Connected');
            break;
        case ConnectionState.DISCONNECTED:
            updateConnectionStatus('disconnected', 'Disconnected');
            break;
        case ConnectionState.RECONNECTING:
            updateConnectionStatus('connecting', 'Reconnecting…');
            break;
    }
});

// -- Subscribe to hello_ack --------------------------------------------------
network.on('hello_ack', (data) => {
    AppState.userId = data.user_id;
    console.log(`[CollabBoard] Identified: ${AppState.username} (${data.user_id})`);
});

// -- Subscribe to errors -----------------------------------------------------
network.on('error', (data) => {
    console.warn(`[CollabBoard] Server error: [${data.code}] ${data.message}`);
});

// -- Subscribe to reconnect events -------------------------------------------
network.on('reconnecting', ({ attempt, maxAttempts, delay }) => {
    console.log(`[CollabBoard] Reconnect attempt ${attempt}/${maxAttempts} in ${delay}ms`);
});

network.on('reconnected', () => {
    console.log('[CollabBoard] Reconnected. Re-join room if needed.');
    // Day 3: auto re-send join_room with stored roomId
});

network.on('reconnect_failed', () => {
    console.error('[CollabBoard] All reconnect attempts failed.');
    updateConnectionStatus('disconnected', 'Connection lost');
    // TODO (Day 3): Show a reconnect button in the UI
});

// ---------------------------------------------------------------------------
// Initialization
// ---------------------------------------------------------------------------
(function init() {
    console.log('[CollabBoard] Frontend initialized — Day 2');
    console.log('[CollabBoard] Press Ctrl+Shift+D to toggle dark mode');

    // Set initial canvas cursor
    DOM.canvas.style.cursor = 'default';

    // Initialize Canvas & Tools (Day 4)
    if (window.CollabCanvas) window.CollabCanvas.init();
    if (window.ToolManager) window.ToolManager.init();

    // -- Show Room Modal ------------------------------------------------------
    // Day 3: Show the room join/create modal on load
    DOM.roomModal.setAttribute('aria-hidden', 'false');
    DOM.modalUsername.focus();
})();
