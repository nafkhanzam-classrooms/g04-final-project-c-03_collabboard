// =============================================================================
// CollabBoard — Tool Manager
// =============================================================================
// Owner : M2 (Frontend Engineer)
// Sprint: Day 4
//
// Manages user interaction with the canvas to produce drawing primitives.
// Translates DOM mouse events into 1920x1080 logical coordinates.
// Previews the current stroke during drag and dispatches `op: add` payloads
// to the network upon completion.
//
// Supported Tools (Day 4): Pencil, Rectangle
// =============================================================================

'use strict';

class ToolManagerClass {
    constructor() {
        this.canvas = document.getElementById('canvas');
        
        this.isDrawing = false;
        
        // Stores the state of the current stroke/shape in progress
        this.activePreview = null;

        // Bind event handlers
        this.onMouseDown = this.onMouseDown.bind(this);
        this.onMouseMove = this.onMouseMove.bind(this);
        this.onMouseUp = this.onMouseUp.bind(this);
        this.onMouseLeave = this.onMouseLeave.bind(this);
    }

    init() {
        console.log('[ToolManager] Initialized.');
        
        // Attach pointer events to the canvas
        this.canvas.addEventListener('mousedown', this.onMouseDown);
        this.canvas.addEventListener('mousemove', this.onMouseMove);
        window.addEventListener('mouseup', this.onMouseUp);
        this.canvas.addEventListener('mouseleave', this.onMouseLeave);
    }

    /**
     * Translates a MouseEvent into the 1920x1080 logical canvas space.
     * @param {MouseEvent} e 
     * @returns {{x: number, y: number}}
     */
    getLogicalCoordinates(e) {
        const rect = this.canvas.getBoundingClientRect();
        
        // Calculate scale factors
        const scaleX = 1920 / rect.width;
        const scaleY = 1080 / rect.height;

        // Apply scale to the mouse offset
        const x = (e.clientX - rect.left) * scaleX;
        const y = (e.clientY - rect.top) * scaleY;

        // Return rounded integers
        return { x: Math.round(x), y: Math.round(y) };
    }

    onMouseDown(e) {
        // Only trigger on primary click (left button)
        if (e.button !== 0) return;
        
        // 'select' tool doesn't draw
        if (window.AppState.activeTool === 'select') return;

        this.isDrawing = true;
        const { x, y } = this.getLogicalCoordinates(e);

        // Initialize the preview object based on the active tool
        this.activePreview = {
            obj_type: window.AppState.activeTool,
            color: window.AppState.strokeColor,
            stroke_width: window.AppState.strokeWidth,
            startX: x,
            startY: y,
            properties: {}
        };

        if (this.activePreview.obj_type === 'pencil') {
            this.activePreview.properties.points = [[x, y]];
        }
    }

    onMouseMove(e) {
        if (!this.isDrawing || !this.activePreview) return;

        const { x, y } = this.getLogicalCoordinates(e);

        if (this.activePreview.obj_type === 'pencil') {
            this.activePreview.properties.points.push([x, y]);
        } else if (this.activePreview.obj_type === 'rectangle') {
            // Calculate width and height (can be negative during drag, so we normalize later or draw as is)
            this.activePreview.properties.x = Math.min(this.activePreview.startX, x);
            this.activePreview.properties.y = Math.min(this.activePreview.startY, y);
            this.activePreview.properties.width = Math.abs(x - this.activePreview.startX);
            this.activePreview.properties.height = Math.abs(y - this.activePreview.startY);
        }
    }

    onMouseUp(e) {
        if (!this.isDrawing) return;
        this.isDrawing = false;
        
        this.finishStroke();
    }

    onMouseLeave(e) {
        // If they drag outside the canvas, we can either stop or keep drawing.
        // We'll finish the stroke if they leave.
        if (this.isDrawing) {
            this.isDrawing = false;
            this.finishStroke();
        }
    }

    /**
     * Finalizes the current preview stroke, constructs the payload,
     * optimistically adds it to the local canvas, and sends it over the network.
     */
    finishStroke() {
        if (!this.activePreview) return;

        // Skip invalid strokes (e.g., pencil with only 1 point, rect with 0 width)
        if (this.activePreview.obj_type === 'pencil') {
            if (this.activePreview.properties.points.length < 2) {
                this.activePreview = null;
                return;
            }
        } else if (this.activePreview.obj_type === 'rectangle') {
            if (!this.activePreview.properties.width || !this.activePreview.properties.height) {
                this.activePreview = null;
                return;
            }
            this.activePreview.properties.fill_color = null; // No fill by default in Day 4
        } else {
            // For other tools not yet implemented, just abort
            this.activePreview = null;
            return;
        }

        // Construct the full payload required by API_CONTRACT.md §9
        const payload = {
            obj_type: this.activePreview.obj_type,
            z_index: window.CollabCanvas.objects.length, // Put on top
            color: this.activePreview.color,
            stroke_width: this.activePreview.stroke_width,
            properties: this.activePreview.properties
        };

        // 1. Optimistic Update (Local Render)
        // Give it a temporary UUID until the server acks it
        const tempId = 'temp-' + crypto.randomUUID();
        const optimisticObj = {
            ...payload,
            obj_id: tempId,
            created_by: window.AppState.userId || 'local',
            created_at: new Date().toISOString()
        };
        
        window.CollabCanvas.addOptimisticObject(optimisticObj);

        // 2. Network Send
        if (window.network && window.network.isIdentified) {
            window.network.send({
                type: 'op',
                op: 'add',
                object: payload
            });
        } else {
            console.warn('[ToolManager] Not connected to room. Stroke drawn locally only.');
        }

        // Clear preview
        this.activePreview = null;
    }

    /**
     * Called by CanvasRenderer every frame.
     * Draws the active stroke on top of the committed canvas state.
     * @param {CanvasRenderingContext2D} ctx 
     */
    renderPreview(ctx) {
        if (!this.isDrawing || !this.activePreview) return;

        const { obj_type, color, stroke_width, properties } = this.activePreview;

        ctx.strokeStyle = color;
        ctx.lineWidth = stroke_width;
        ctx.fillStyle = 'transparent';
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';

        ctx.beginPath();

        if (obj_type === 'pencil' && properties.points) {
            ctx.moveTo(properties.points[0][0], properties.points[0][1]);
            for (let i = 1; i < properties.points.length; i++) {
                ctx.lineTo(properties.points[i][0], properties.points[i][1]);
            }
            ctx.stroke();
        } 
        else if (obj_type === 'rectangle' && properties.width && properties.height) {
            ctx.strokeRect(properties.x, properties.y, properties.width, properties.height);
        }
    }
}

// Export as global
window.ToolManager = new ToolManagerClass();
