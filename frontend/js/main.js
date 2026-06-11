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

    // -- Day 8: Cursor Chat state --------------------------------------------

    /** Last known logical coordinates of the local cursor */
    lastKnownCursor: { x: 0, y: 0 },

    /** Whether the cursor chat input is currently open */
    isChatInputOpen: false,

    /** Reference to the local chat bubble DOM element */
    activeLocalBubble: null,

    /** Reference to the local chat input wrapper DOM element */
    activeChatInput: null,
};

// ---------------------------------------------------------------------------
// DOM References
// ---------------------------------------------------------------------------
const DOM = {
    // Core containers
    app: document.getElementById('app'),
    canvasContainer: document.getElementById('canvas-container'),
    canvas: document.getElementById('canvas'),
    cursorOverlay: document.getElementById('cursor-overlay'),

    // Toolbar
    toolbar: document.getElementById('toolbar'),
    toolbarRoomName: document.getElementById('toolbar-room-name'),
    toolButtons: document.querySelectorAll('.toolbar__tool'),
    colorInput: document.getElementById('tool-color'),
    colorSwatch: document.getElementById('tool-color-swatch'),
    strokeWidthSelect: document.getElementById('tool-stroke-width'),
    sidebarToggle: document.getElementById('toolbar-sidebar-toggle'),
    menuBtn: document.getElementById('toolbar-menu-btn'),
    moreBtn: document.getElementById('toolbar-more-btn'),
    participants: document.getElementById('toolbar-participants'),

    // Sidebar
    sidebar: document.getElementById('sidebar'),
    sidebarCloseBtn: document.getElementById('sidebar-close-btn'),
    participantList: document.getElementById('sidebar-participant-list'),

    // Status bar
    statusBar: document.getElementById('status-bar'),
    statusConnection: document.getElementById('status-connection'),
    statusRoom: document.getElementById('status-room'),
    statusSave: document.getElementById('status-save'),
    statusUsers: document.getElementById('status-users'),

    // Modal
    roomModal: document.getElementById('room-modal'),
    modalUsername: document.getElementById('modal-username'),
    modalRoomCode: document.getElementById('modal-room-code'),
    modalError: document.getElementById('modal-error'),
    modalJoinBtn: document.getElementById('modal-join-btn'),
    modalCreateBtn: document.getElementById('modal-create-btn'),
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
        select: 'default',
        pencil: 'crosshair',
        text: 'text',
        rectangle: 'crosshair',
        circle: 'crosshair',
        line: 'crosshair',
        arrow: 'crosshair',
        heart: 'crosshair',
        image: 'pointer',
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
// Cursor Chat & Undo/Redo & Keyboard Shortcuts
// ---------------------------------------------------------------------------

/**
 * Renders a cursor chat bubble that auto-dismisses after 4 seconds.
 * @param {string} userId - UUID of the user
 * @param {string} username - Name to display
 * @param {number} logicalX - 1920x1080 coordinate
 * @param {number} logicalY - 1920x1080 coordinate
 * @param {string} message - Chat text
 */
function renderCursorChatBubble(userId, username, logicalX, logicalY, message) {
    // Convert logical coordinates to screen pixels relative to the canvas container
    const rect = DOM.canvasContainer.getBoundingClientRect();
    const scaleX = rect.width / 1920;
    const scaleY = rect.height / 1080;

    const screenX = logicalX * scaleX;
    const screenY = logicalY * scaleY;

    // Create the bubble wrapper
    const bubble = document.createElement('div');
    bubble.className = 'cursor-chat-bubble';
    bubble.style.left = `${screenX}px`;
    // Position slightly above the cursor
    bubble.style.top = `${screenY - 10}px`;
    // Offset so the pointer tail aligns with the cursor
    bubble.style.transform = 'translate(10px, -100%)';

    // Add user's unique color based on name (matching UI avatar color logic)
    const hue = Array.from(username).reduce((acc, char) => acc + char.charCodeAt(0), 0) % 360;
    bubble.style.backgroundColor = `hsl(${hue}, 70%, 40%)`;

    // Name label
    const nameEl = document.createElement('div');
    nameEl.className = 'cursor-chat-bubble__name';
    nameEl.textContent = username;

    // Message body
    const msgEl = document.createElement('div');
    msgEl.className = 'cursor-chat-bubble__message';
    msgEl.textContent = message;

    bubble.appendChild(nameEl);
    bubble.appendChild(msgEl);

    // Attach to the specific remote cursor if available, so it follows naturally
    let attachedToRemote = false;
    if (userId !== AppState.userId && window.CollabCanvas?.cursorManager) {
        const remoteEntry = window.CollabCanvas.cursorManager.cursors.get(userId);
        if (remoteEntry && remoteEntry.element) {
            remoteEntry.element.appendChild(bubble);
            // Override position since parent transforms
            bubble.style.left = '0px';
            bubble.style.top = '-10px';
            attachedToRemote = true;
        }
    }

    if (!attachedToRemote) {
        DOM.cursorOverlay.appendChild(bubble);
        if (userId === AppState.userId) {
            // Remove existing local bubble if present
            if (AppState.activeLocalBubble && AppState.activeLocalBubble.parentNode) {
                AppState.activeLocalBubble.parentNode.removeChild(AppState.activeLocalBubble);
            }
            AppState.activeLocalBubble = bubble;
        }
    }

    // Auto-dismiss after 4 seconds (matches CSS animation)
    setTimeout(() => {
        if (bubble.parentNode) {
            bubble.parentNode.removeChild(bubble);
            if (bubble === AppState.activeLocalBubble) {
                AppState.activeLocalBubble = null;
            }
        }
    }, 4000);
}

/**
 * Opens the floating cursor chat input at the last known cursor position.
 */
function openCursorChatInput() {
    if (AppState.isChatInputOpen) return;
    AppState.isChatInputOpen = true;

    // Convert logical coordinates to screen pixels
    const rect = DOM.canvasContainer.getBoundingClientRect();
    const scaleX = rect.width / 1920;
    const scaleY = rect.height / 1080;
    const screenX = AppState.lastKnownCursor.x * scaleX;
    const screenY = AppState.lastKnownCursor.y * scaleY;

    // Create the input wrapper
    const wrapper = document.createElement('div');
    wrapper.className = 'cursor-chat-input-wrapper';
    wrapper.style.left = `${screenX + 15}px`; // Offset slightly from the exact point
    wrapper.style.top = `${screenY - 15}px`;

    const slashBadge = document.createElement('div');
    slashBadge.className = 'cursor-chat-input-slash';
    slashBadge.textContent = '/';

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'cursor-chat-input';
    input.placeholder = 'Say something...';
    input.maxLength = 200;

    wrapper.appendChild(slashBadge);
    wrapper.appendChild(input);
    DOM.cursorOverlay.appendChild(wrapper);
    AppState.activeChatInput = wrapper;

    // Focus the input immediately
    input.focus();

    // -- Auto-dismiss on inactivity --
    let inactivityTimeout;
    function resetInactivityTimeout() {
        if (inactivityTimeout) clearTimeout(inactivityTimeout);
        inactivityTimeout = setTimeout(() => {
            closeCursorChatInput();
        }, 4000);
    }

    // Start the timer
    resetInactivityTimeout();

    // Handle input keys
    input.addEventListener('keydown', (e) => {
        // Prevent event from bubbling up to global hotkeys
        e.stopPropagation();

        // User interacted, reset the 4s auto-dismiss timer
        resetInactivityTimeout();

        if (e.key === 'Escape') {
            closeCursorChatInput();
        } else if (e.key === 'Enter') {
            const message = input.value.trim();
            if (message && network.isIdentified && AppState.roomId) {
                // Send to server
                network.send({
                    type: 'cursor_chat',
                    x: AppState.lastKnownCursor.x,
                    y: AppState.lastKnownCursor.y,
                    message: message
                });

                // Show optimistic local bubble immediately
                renderCursorChatBubble(
                    AppState.userId,
                    AppState.username,
                    AppState.lastKnownCursor.x,
                    AppState.lastKnownCursor.y,
                    message
                );
            }
            closeCursorChatInput();
        }
    });

    // Close if user clicks outside
    const outsideClickListener = (e) => {
        if (!wrapper.contains(e.target)) {
            closeCursorChatInput();
            document.removeEventListener('mousedown', outsideClickListener);
        }
    };

    // Defer attaching the outside click listener to avoid triggering on the current event
    setTimeout(() => {
        document.addEventListener('mousedown', outsideClickListener);
    }, 0);

    function closeCursorChatInput() {
        if (inactivityTimeout) clearTimeout(inactivityTimeout);

        if (wrapper.parentNode) {
            const fadeOut = wrapper.animate([
                { opacity: 1 },
                { opacity: 0 }
            ], {
                duration: 200,
                easing: 'ease-out'
            });

            fadeOut.onfinish = () => {
                if (wrapper.parentNode) {
                    wrapper.parentNode.removeChild(wrapper);
                }
            };
        }
        AppState.isChatInputOpen = false;
        AppState.activeChatInput = null;
        // Refocus canvas or app so global hotkeys work again
        DOM.canvas.focus();
    }
}

// Track local cursor position for cursor chat spawning and following
DOM.canvas.addEventListener('mousemove', (e) => {
    // Convert to logical coordinates
    const rect = DOM.canvas.getBoundingClientRect();
    const scaleX = 1920 / rect.width;
    const scaleY = 1080 / rect.height;
    AppState.lastKnownCursor = {
        x: Math.round((e.clientX - rect.left) * scaleX),
        y: Math.round((e.clientY - rect.top) * scaleY)
    };

    // Update positioning for local floating elements
    // We can use the raw client offsets relative to the canvas
    const screenX = e.clientX - rect.left;
    const screenY = e.clientY - rect.top;

    if (AppState.activeLocalBubble) {
        AppState.activeLocalBubble.style.left = `${screenX}px`;
        AppState.activeLocalBubble.style.top = `${screenY - 10}px`;
    }
    if (AppState.activeChatInput) {
        AppState.activeChatInput.style.left = `${screenX + 15}px`;
        AppState.activeChatInput.style.top = `${screenY - 15}px`;
    }
});

document.addEventListener('keydown', (e) => {
    // -- Day 8: Undo/Redo Bindings --
    if (e.ctrlKey || e.metaKey) {
        if (e.key.toLowerCase() === 'z') {
            if (e.shiftKey) {
                // Ctrl+Shift+Z -> Redo
                e.preventDefault();
                window.UndoRedoManager?.redo();
                return;
            } else {
                // Ctrl+Z -> Undo
                e.preventDefault();
                window.UndoRedoManager?.undo();
                return;
            }
        }
        if (e.key.toLowerCase() === 'y') {
            // Ctrl+Y -> Redo
            e.preventDefault();
            window.UndoRedoManager?.redo();
            return;
        }
    }

    // Don't capture standard hotkeys when typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
        return;
    }

    // Modifiers mean it's likely a browser shortcut, let it pass
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    // -- Day 8: Cursor Chat trigger --
    if (e.key === '/') {
        e.preventDefault();
        openCursorChatInput();
        return;
    }

    // -- Tool Hotkeys --

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

// -- Day 8: Subscribe to Cursor Chat Broadcast -------------------------------
network.on('cursor_chat_broadcast', (data) => {
    renderCursorChatBubble(data.user_id, data.username, data.x, data.y, data.message);
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

    // Initialize Canvas, Tools, and Cursor overlay (Day 4 / Day 7)
    if (window.CollabCanvas) window.CollabCanvas.init();
    if (window.ToolManager) window.ToolManager.init();
    if (window.CursorManager) window.CursorManager.init();

    // -- Show Room Modal ------------------------------------------------------
    // Day 3: Show the room join/create modal on load
    DOM.roomModal.setAttribute('aria-hidden', 'false');
    DOM.modalUsername.focus();
})();
