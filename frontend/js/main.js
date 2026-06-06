// =============================================================================
// CollabBoard — Main JS Entry Point
// =============================================================================
// Owner : M2 (Frontend Engineer)
// Sprint: Day 1
//
// Initializes the application shell, binds core DOM elements, wires up
// toolbar interactions (tool switching, color picker sync, sidebar toggle),
// and prepares the module hook points for Day 2+ JS modules.
//
// Reference:
//   - IMPLEMENTATION_PLAN.md §F1
//   - SPECIFICATION.md §6.2
// =============================================================================

'use strict';

/**
 * CollabBoard — Application State (Day 1 shell)
 *
 * This object will be expanded as modules are added.  For Day 1, it only
 * tracks the active tool, current colors/stroke, and theme.
 */
const AppState = {
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
// Initialization
// ---------------------------------------------------------------------------
(function init() {
    console.log('[CollabBoard] Frontend initialized — Day 1 scaffold');
    console.log('[CollabBoard] Press Ctrl+Shift+D to toggle dark mode');

    // Set initial canvas cursor
    DOM.canvas.style.cursor = 'default';

    // Get 2D context (ready for Day 4 canvas.js)
    const ctx = DOM.canvas.getContext('2d');
    if (ctx) {
        console.log(`[CollabBoard] Canvas 2D context ready (${DOM.canvas.width}×${DOM.canvas.height})`);
    }
})();
