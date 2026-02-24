/* ==========================================================================
   RobotJudge-CI — Canvas Grid Renderer
   Renders testcase grids with obstacles, start/goal, and path overlay
   ========================================================================== */

class GridRenderer {
    constructor(canvas, options = {}) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.tooltip = options.tooltip || null;

        // Colors
        this.colors = {
            free: '#1a1a2e',
            obstacle: '#4a4a6a',
            start: '#4CAF50',
            goal: '#F44336',
            path: '#42A5F5',
            pathGlow: 'rgba(66, 165, 245, 0.3)',
            gridLine: 'rgba(255,255,255,0.04)',
            hover: 'rgba(255,255,255,0.15)',
            ...options.colors,
        };

        // State
        this.grid = null;
        this.rows = 0;
        this.cols = 0;
        this.start = null;
        this.goal = null;
        this.path = null;
        this.cellSize = 1;
        this.offsetX = 0;
        this.offsetY = 0;
        this.scale = 1;
        this.hoverCell = null;

        // Interaction
        this._setupEvents();
    }

    /* ---------- Load data ---------- */
    setCase(caseData) {
        const g = caseData.grid;
        if (Array.isArray(g)) {
            this.grid = g;
            this.rows = g.length;
            this.cols = g[0] ? g[0].length : 0;
        } else {
            // RLE — decode
            this.rows = g.rows;
            this.cols = g.cols;
            this.grid = this._decodeRLE(g.data, g.rows, g.cols);
        }
        this.start = caseData.start;
        this.goal = caseData.goal;
        this.path = null;
        this._fitToCanvas();
        this.render();
    }

    setPath(pathData) {
        if (!pathData) { this.path = null; this.render(); return; }

        const p = pathData.path || pathData;
        if (!p || p.length === 0) { this.path = null; this.render(); return; }

        // If action-list, convert to cells
        if (typeof p[0] === 'string') {
            this.path = this._actionsToPath(p, this.start);
        } else {
            this.path = p;
        }
        this.render();
    }

    /* ---------- Rendering ---------- */
    render() {
        const ctx = this.ctx;
        const w = this.canvas.width;
        const h = this.canvas.height;
        const cs = this.cellSize * this.scale;

        ctx.clearRect(0, 0, w, h);
        ctx.fillStyle = '#0d0d1a';
        ctx.fillRect(0, 0, w, h);

        if (!this.grid) return;

        const ox = this.offsetX;
        const oy = this.offsetY;

        // Determine visible range
        const startRow = Math.max(0, Math.floor(-oy / cs));
        const endRow = Math.min(this.rows, Math.ceil((h - oy) / cs));
        const startCol = Math.max(0, Math.floor(-ox / cs));
        const endCol = Math.min(this.cols, Math.ceil((w - ox) / cs));

        // Draw cells
        for (let r = startRow; r < endRow; r++) {
            for (let c = startCol; c < endCol; c++) {
                const x = ox + c * cs;
                const y = oy + r * cs;
                const val = this.grid[r][c];

                ctx.fillStyle = val === 1 ? this.colors.obstacle : this.colors.free;
                ctx.fillRect(x, y, cs, cs);

                // Grid lines for larger cells
                if (cs > 3) {
                    ctx.strokeStyle = this.colors.gridLine;
                    ctx.lineWidth = 0.5;
                    ctx.strokeRect(x, y, cs, cs);
                }
            }
        }

        // Draw path
        if (this.path && this.path.length > 1) {
            this._drawPath(ctx, ox, oy, cs);
        }

        // Draw start
        if (this.start) {
            this._drawMarker(ctx, this.start[0], this.start[1], ox, oy, cs, this.colors.start, 'S');
        }

        // Draw goal
        if (this.goal) {
            this._drawMarker(ctx, this.goal[0], this.goal[1], ox, oy, cs, this.colors.goal, 'G');
        }

        // Hover highlight
        if (this.hoverCell) {
            const [hr, hc] = this.hoverCell;
            const hx = ox + hc * cs;
            const hy = oy + hr * cs;
            ctx.strokeStyle = this.colors.hover;
            ctx.lineWidth = 2;
            ctx.strokeRect(hx, hy, cs, cs);
        }
    }

    _drawPath(ctx, ox, oy, cs) {
        // Path glow
        ctx.strokeStyle = this.colors.pathGlow;
        ctx.lineWidth = cs * 0.6;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.beginPath();
        for (let i = 0; i < this.path.length; i++) {
            const [r, c] = this.path[i];
            const x = ox + c * cs + cs / 2;
            const y = oy + r * cs + cs / 2;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Path line with gradient
        const p0 = this.path[0];
        const pN = this.path[this.path.length - 1];
        const x0 = ox + p0[1] * cs + cs / 2;
        const y0 = ox + p0[0] * cs + cs / 2;
        const xN = ox + pN[1] * cs + cs / 2;
        const yN = oy + pN[0] * cs + cs / 2;

        const grad = ctx.createLinearGradient(x0, y0, xN, yN);
        grad.addColorStop(0, this.colors.start);
        grad.addColorStop(1, this.colors.goal);

        ctx.strokeStyle = grad;
        ctx.lineWidth = Math.max(1.5, cs * 0.25);
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.beginPath();
        for (let i = 0; i < this.path.length; i++) {
            const [r, c] = this.path[i];
            const x = ox + c * cs + cs / 2;
            const y = oy + r * cs + cs / 2;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Path dots for small cell sizes
        if (cs >= 6) {
            for (let i = 0; i < this.path.length; i++) {
                const [r, c] = this.path[i];
                const x = ox + c * cs + cs / 2;
                const y = oy + r * cs + cs / 2;
                const t = i / (this.path.length - 1);
                ctx.fillStyle = this._lerpColor(this.colors.start, this.colors.goal, t);
                ctx.beginPath();
                ctx.arc(x, y, Math.max(1, cs * 0.12), 0, Math.PI * 2);
                ctx.fill();
            }
        }
    }

    _drawMarker(ctx, row, col, ox, oy, cs, color, label) {
        const x = ox + col * cs;
        const y = oy + row * cs;

        // Glow
        ctx.shadowColor = color;
        ctx.shadowBlur = Math.max(4, cs * 0.5);
        ctx.fillStyle = color;
        ctx.fillRect(x + 1, y + 1, cs - 2, cs - 2);
        ctx.shadowBlur = 0;

        // Label
        if (cs >= 12) {
            ctx.fillStyle = '#fff';
            ctx.font = `bold ${Math.max(8, cs * 0.5)}px ${getComputedStyle(document.body).getPropertyValue('--mono') || 'monospace'}`;
            ctx.textAlign = 'center';
            ctx.textBaseline = 'middle';
            ctx.fillText(label, x + cs / 2, y + cs / 2);
        }
    }

    /* ---------- Interaction ---------- */
    _setupEvents() {
        let isDragging = false;
        let dragStart = { x: 0, y: 0 };
        let origOffset = { x: 0, y: 0 };

        this.canvas.addEventListener('wheel', (e) => {
            e.preventDefault();
            const rect = this.canvas.getBoundingClientRect();
            const mx = e.clientX - rect.left;
            const my = e.clientY - rect.top;

            const oldScale = this.scale;
            const factor = e.deltaY > 0 ? 0.9 : 1.1;
            this.scale = Math.max(0.1, Math.min(20, this.scale * factor));

            // Zoom toward mouse
            this.offsetX = mx - (mx - this.offsetX) * (this.scale / oldScale);
            this.offsetY = my - (my - this.offsetY) * (this.scale / oldScale);

            this.render();
        }, { passive: false });

        this.canvas.addEventListener('mousedown', (e) => {
            isDragging = true;
            dragStart = { x: e.clientX, y: e.clientY };
            origOffset = { x: this.offsetX, y: this.offsetY };
            this.canvas.style.cursor = 'grabbing';
        });

        window.addEventListener('mousemove', (e) => {
            if (isDragging) {
                this.offsetX = origOffset.x + (e.clientX - dragStart.x);
                this.offsetY = origOffset.y + (e.clientY - dragStart.y);
                this.render();
            } else {
                this._updateHover(e);
            }
        });

        window.addEventListener('mouseup', () => {
            isDragging = false;
            this.canvas.style.cursor = 'crosshair';
        });

        this.canvas.addEventListener('mouseleave', () => {
            this.hoverCell = null;
            if (this.tooltip) this.tooltip.style.display = 'none';
            this.render();
        });
    }

    _updateHover(e) {
        const rect = this.canvas.getBoundingClientRect();
        const mx = e.clientX - rect.left;
        const my = e.clientY - rect.top;
        const cs = this.cellSize * this.scale;

        const col = Math.floor((mx - this.offsetX) / cs);
        const row = Math.floor((my - this.offsetY) / cs);

        if (row >= 0 && row < this.rows && col >= 0 && col < this.cols) {
            this.hoverCell = [row, col];
            if (this.tooltip) {
                const val = this.grid[row][col];
                const isStart = this.start && this.start[0] === row && this.start[1] === col;
                const isGoal = this.goal && this.goal[0] === row && this.goal[1] === col;
                let label = `(${row}, ${col}) ${val === 1 ? 'obstacle' : 'free'}`;
                if (isStart) label += ' [START]';
                if (isGoal) label += ' [GOAL]';
                this.tooltip.textContent = label;
                this.tooltip.style.display = 'block';
                this.tooltip.style.left = (mx + 12) + 'px';
                this.tooltip.style.top = (my - 24) + 'px';
            }
        } else {
            this.hoverCell = null;
            if (this.tooltip) this.tooltip.style.display = 'none';
        }
        this.render();
    }

    /* ---------- Fit / Resize ---------- */
    _fitToCanvas() {
        const rect = this.canvas.parentElement.getBoundingClientRect();
        const w = rect.width || 800;
        const h = Math.min(w * 0.7, 500);

        this.canvas.width = w * window.devicePixelRatio;
        this.canvas.height = h * window.devicePixelRatio;
        this.canvas.style.width = w + 'px';
        this.canvas.style.height = h + 'px';
        this.ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

        const csW = (w - 4) / this.cols;
        const csH = (h - 4) / this.rows;
        this.cellSize = Math.min(csW, csH);
        this.scale = 1;

        // Center
        this.offsetX = (w - this.cols * this.cellSize) / 2;
        this.offsetY = (h - this.rows * this.cellSize) / 2;
    }

    resetView() {
        this._fitToCanvas();
        this.render();
    }

    /* ---------- Helpers ---------- */
    _decodeRLE(data, rows, cols) {
        const grid = [];
        const runs = data.split(',');
        let idx = 0;
        let flat = [];

        for (const run of runs) {
            const [val, count] = run.split(':').map(Number);
            for (let i = 0; i < count; i++) flat.push(val);
        }

        for (let r = 0; r < rows; r++) {
            const row = [];
            for (let c = 0; c < cols; c++) {
                row.push(flat[idx++] || 0);
            }
            grid.push(row);
        }
        return grid;
    }

    _actionsToPath(actions, start) {
        const dirs = {
            'U': [-1, 0], 'D': [1, 0], 'L': [0, -1], 'R': [0, 1],
            'UL': [-1, -1], 'UR': [-1, 1], 'DL': [1, -1], 'DR': [1, 1],
        };
        const path = [[...start]];
        let [r, c] = start;
        for (const a of actions) {
            const [dr, dc] = dirs[a] || [0, 0];
            r += dr;
            c += dc;
            path.push([r, c]);
        }
        return path;
    }

    _lerpColor(c1, c2, t) {
        // Simple hex lerp
        const h2r = (hex) => {
            const m = hex.match(/\w{2}/g);
            return m ? m.map(x => parseInt(x, 16)) : [0, 0, 0];
        };
        const r2h = (rgb) => '#' + rgb.map(v => Math.round(v).toString(16).padStart(2, '0')).join('');

        const [r1, g1, b1] = h2r(c1);
        const [r2, g2, b2] = h2r(c2);
        return r2h([
            r1 + (r2 - r1) * t,
            g1 + (g2 - g1) * t,
            b1 + (b2 - b1) * t,
        ]);
    }
}
