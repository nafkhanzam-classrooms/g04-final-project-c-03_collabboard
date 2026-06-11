// =============================================================================
// CollabBoard — Canvas Renderer
// =============================================================================
// Owner : M2 (Frontend Engineer)
// Sprint: Day 4
//
// Manages the HTML5 Canvas, maintains the authoritative list of committed
// drawing objects, and runs the requestAnimationFrame render loop.
//
// Features:
//   - Fixed 1920x1080 logical coordinate space.
//   - 60fps render loop clearing and redrawing all objects.
//   - Delegates rendering of the in-progress tool stroke to ToolManager.
//   - Listens to network events for incoming snapshot and broadcast data.
// =============================================================================

'use strict';

class CanvasRenderer {
    constructor() {
        this.canvas = document.getElementById('canvas');
        /** @type {CanvasRenderingContext2D} */
        this.ctx = this.canvas.getContext('2d');
        
        // Logical canvas dimensions defined in SPECIFICATION.md
        this.WIDTH = 1920;
        this.HEIGHT = 1080;

        /** 
         * The committed state of the canvas.
         * A Map of object payloads received from the server or local. 
         * @type {Map<string, Object>} 
         */
        this.objects = new Map();
        
        /**
         * Queue of temporary IDs awaiting op_ack for 'add' operations.
         * @type {string[]}
         */
        this.pendingAdds = [];

        // Bind the render loop to this instance
        this.renderLoop = this.renderLoop.bind(this);
    }

    init() {
        console.log(`[CollabCanvas] Initialized. Logical size: ${this.WIDTH}x${this.HEIGHT}`);

        // Set up network listeners for incoming canvas data
        if (window.network) {
            window.network.on('canvas_snapshot', (data) => this.handleSnapshot(data));
            window.network.on('op_broadcast', (data) => this.handleOpBroadcast(data));
            window.network.on('op_ack', (data) => this.handleOpAck(data));
        }

        // Start the render loop
        requestAnimationFrame(this.renderLoop);
    }

    /**
     * Replaces the local state with a full snapshot from the server.
     * @param {Object} data - The canvas_snapshot payload
     */
    handleSnapshot(data) {
        console.log(`[CollabCanvas] Received snapshot with ${data.objects.length} objects.`);
        this.objects.clear();
        this.pendingAdds = [];
        for (const obj of data.objects) {
            this.objects.set(obj.obj_id, obj);
        }
    }

    /**
     * Handles an operation broadcast from another user.
     * @param {Object} data - The op_broadcast payload
     */
    handleOpBroadcast(data) {
        if (data.op === 'add') {
            const obj = data.object;
            if (data.seq !== undefined) obj.seq = data.seq;
            this.objects.set(obj.obj_id, obj);
        } else if (data.op === 'modify') {
            const existing = this.objects.get(data.obj_id);
            if (existing) {
                const changes = data.changes || {};
                if (changes.color) existing.color = changes.color;
                if (changes.stroke_width !== undefined) existing.stroke_width = changes.stroke_width;
                if (changes.z_index !== undefined) existing.z_index = changes.z_index;
                if (changes.properties) {
                    existing.properties = { ...existing.properties, ...changes.properties };
                }
                if (data.seq !== undefined) existing.seq = data.seq;
            }
        } else if (data.op === 'delete') {
            const existing = this.objects.get(data.obj_id);
            if (existing) {
                existing.is_deleted = true;
                if (data.seq !== undefined) existing.seq = data.seq;
            }
        }
    }

    /**
     * Handles acknowledgment of our own operation.
     * @param {Object} data - The op_ack payload
     */
    handleOpAck(data) {
        if (!this.objects.has(data.obj_id)) {
            // Ack for a new 'add' operation
            if (this.pendingAdds.length > 0) {
                const tempId = this.pendingAdds.shift();
                const obj = this.objects.get(tempId);
                if (obj) {
                    obj.obj_id = data.obj_id;
                    obj.seq = data.seq;
                    this.objects.delete(tempId);
                    this.objects.set(data.obj_id, obj);
                }
            }
        } else {
            // Ack for modify or delete
            const obj = this.objects.get(data.obj_id);
            if (obj) {
                obj.seq = data.seq;
            }
        }
    }

    /**
     * Adds an object directly to the local state (optimistic update).
     * @param {Object} obj 
     */
    addOptimisticObject(obj) {
        this.objects.set(obj.obj_id, obj);
        if (obj.obj_id.startsWith('temp-')) {
            this.pendingAdds.push(obj.obj_id);
        }
    }

    /**
     * Core render loop called by requestAnimationFrame.
     */
    renderLoop() {
        // 1. Clear the canvas
        this.ctx.clearRect(0, 0, this.WIDTH, this.HEIGHT);

        // 2. Set default styles
        this.ctx.lineCap = 'round';
        this.ctx.lineJoin = 'round';

        // Sort objects by z_index, then by seq (fallback)
        const sortedObjects = Array.from(this.objects.values()).sort((a, b) => {
            if (a.z_index !== b.z_index) return a.z_index - b.z_index;
            return (a.seq || 0) - (b.seq || 0);
        });

        // 3. Draw all committed objects
        for (const obj of sortedObjects) {
            if (!obj.is_deleted) {
                this.drawObject(obj);
            }
        }

        // 4. Draw the in-progress tool stroke on top
        if (window.ToolManager) {
            window.ToolManager.renderPreview(this.ctx);
        }

        // Schedule next frame
        requestAnimationFrame(this.renderLoop);
    }

    /**
     * Renders a single canvas object based on its obj_type.
     * @param {Object} obj 
     */
    drawObject(obj) {
        const { obj_type, color, stroke_width, properties } = obj;

        this.ctx.strokeStyle = color;
        this.ctx.lineWidth = stroke_width;
        
        if (properties.fill_color) {
            this.ctx.fillStyle = properties.fill_color;
        } else {
            this.ctx.fillStyle = 'transparent';
        }

        this.ctx.beginPath();

        switch (obj_type) {
            case 'pencil':
                if (properties.points && properties.points.length > 0) {
                    this.ctx.moveTo(properties.points[0][0], properties.points[0][1]);
                    for (let i = 1; i < properties.points.length; i++) {
                        this.ctx.lineTo(properties.points[i][0], properties.points[i][1]);
                    }
                    this.ctx.stroke();
                }
                break;

            case 'rectangle':
                if (properties.fill_color) {
                    this.ctx.fillRect(properties.x, properties.y, properties.width, properties.height);
                }
                if (stroke_width > 0) {
                    this.ctx.strokeRect(properties.x, properties.y, properties.width, properties.height);
                }
                break;
                
            // Other shapes (circle, line, etc.) will be added in Day 5
            default:
                break;
        }
    }
}

// Export as global
window.CollabCanvas = new CanvasRenderer();
