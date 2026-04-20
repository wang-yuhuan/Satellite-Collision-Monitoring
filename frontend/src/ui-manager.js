
/**
 * ============================================
 * 模块 1: 布局控制器 (侧边栏/抽屉开关)
 * ============================================
 */
class LayoutController {
    constructor(triggersConfig) {
        this.triggers = triggersConfig || {};
        this._bindEvents();
    }

    _bindEvents() {
        for (const [btnId, panelId] of Object.entries(this.triggers)) {
            const btn = document.getElementById(btnId);
            const panel = document.getElementById(panelId);
            if (btn && panel) {
                btn.addEventListener('click', () => panel.classList.toggle('closed'));
            }
        }
    }

    // 控制底部详情面板的展开/收起逻辑
    toggleDetailPanel(overlayId, btnId) {
        const panel = document.getElementById(overlayId);
        const btn = document.getElementById(btnId);
        if (!panel || !btn) return;

        const isActive = panel.classList.contains('active');
        const isExpanded = panel.classList.contains('expanded');

        if (!isActive) {
            panel.classList.add('active');
            panel.classList.remove('expanded');
            btn.innerText = "[ SHOW FULL DATA ]";
        } else if (isActive && !isExpanded) {
            panel.classList.add('expanded');
            btn.innerText = "[ HIDE DETAILS ]";
        } else {
            panel.classList.remove('active');
            panel.classList.remove('expanded');
            btn.innerText = "[ SHOW DETAILS ]";
        }
    }

    showChartOnly(overlayId, btnId) {
        const panel = document.getElementById(overlayId);
        const btn = document.getElementById(btnId);
        if (panel) {
            panel.classList.add('active');
            panel.classList.remove('expanded');
        }
        if (btn) btn.innerText = "[ SHOW FULL DATA ]";
    }

    toggleSocratesTable() {
        const wrapper = document.getElementById('socrates-table-wrapper');
        if (!wrapper) return;
        wrapper.style.display = wrapper.style.display === 'none' ? 'block' : 'none';
    }

}

/**
 * ============================================
 * 模块 2: 输入控制器 (滑块与表单)
 * ============================================
 */
class InputController {
    constructor(domConfig) {
        this.dom = domConfig;
        this._initDurationSlider();
    }

    getSearchParameters() {
        const start = document.getElementById(this.dom.INPUT_START);
        const end = document.getElementById(this.dom.INPUT_END);
        const satId = document.getElementById(this.dom.INPUT_SAT_ID);

        return {
            start: start ? start.value : null,
            end: end ? end.value : null,
            satId: satId ? satId.value : null
        };
    }

    getManeuverParameters() {
        
        const manDateInput = document.getElementById(this.dom.INPUT_MAN_DATE);
        const dvValInput = document.getElementById(this.dom.INPUT_DV_VAL);
        const vSignInput = document.getElementById(this.dom.INPUT_V_SIGN);

        return {
            manDate: manDateInput ? manDateInput.value : '',
            dvVal: dvValInput ? parseFloat(dvValInput.value) : 0,
            vSign: vSignInput ? parseInt(vSignInput.value, 10) : 1
        };
    }

    _initDurationSlider() {
        const range = document.getElementById('inp-duration');
        const display = document.getElementById('val-duration');
        if (!range || !display) return;

        const updateUI = () => {
            const val = range.value;
            const min = range.min;
            const max = range.max;
            
            display.innerText = `${(val / 60).toFixed(1)}h`;
            
            const percentage = ((val - min) / (max - min)) * 100;
            range.style.backgroundSize = `${percentage}% 100%`;
        };

        range.addEventListener('input', updateUI);
        updateUI(); 
    }
}

/**
 * ============================================
 * 模块 3: 图表渲染器 (使用全局 Chart 对象)
 * ============================================
 */
class ChartRenderer {
    constructor(canvasId) {
        this.canvasId = canvasId;
        this.chart = null;
        this._init();
    }

    _init() {
        const ctx = document.getElementById(this.canvasId);
        if (!ctx) return;

        if (typeof Chart === 'undefined') {
            console.error("Chart.js is not loaded! Check your index.html");
            return;
        }

        this.chart = new Chart(ctx, {
            type: 'scatter',
            data: {
                datasets: [{
                    label: 'Collision Probability (Log10)',
                    data: [],
                    backgroundColor: '#00f3ea',
                    borderColor: '#00f3ea',
                    pointRadius: 4,
                    pointHoverRadius: 8,
                    pointHoverBackgroundColor: '#fff', // 悬停变白
                    pointHoverBorderColor: '#00f3ea'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: false,
                plugins: {
                    legend: { display: false },
                    // --- [新增] Tooltip 配置 (完全复用参考代码) ---
                    tooltip: {
                        backgroundColor: 'rgba(10, 15, 20, 0.9)',
                        titleColor: '#00f3ea',
                        bodyColor: '#fff',
                        borderColor: '#00f3ea',
                        borderWidth: 1,
                        titleFont: { family: 'Rajdhani' },
                        bodyFont: { family: 'Share Tech Mono' },
                        callbacks: {
                            label: (context) => {
                                const raw = context.raw;
                                // 注意：这里的数据字段名必须与 addPoint 中 push 的对象一致
                                return [
                                    `Sat: ${raw.satName} (ID: ${raw.objId})`,
                                    `Min Dist: ${Number(raw.dist).toFixed(2)} m`,
                                    `Prob: ${raw.prob.toExponential(2)} (Log: ${raw.y.toFixed(2)})`
                                ];
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        type: 'time',
                        time: { 
                            unit: 'minute',
                            displayFormats: {
                                minute: 'HH:mm',
                                hour: 'MM-dd HH:mm'
                            }
                        },
                        grid: { color: 'rgba(0, 243, 234, 0.1)' },
                        ticks: { color: 'rgba(255, 255, 255, 0.5)', font: { family: 'Share Tech Mono' } }
                    },
                    y: {
                        // --- [新增] Y轴左侧标题 ---
                        title: { display: true, text: 'Log10(Prob)', color: '#00f3ea' },
                        grid: { color: 'rgba(0, 243, 234, 0.1)' },
                        suggestedMin: -10,
                        suggestedMax: 0,
                        ticks: { color: '#00f3ea', font: { family: 'Share Tech Mono' }, stepSize: 2 }
                    }
                }
            }
        });
    }

    // --- [修改] 数据添加方法，确保包含 tooltip 需要的所有字段 ---
    addPoint(timeStr, logProb, details) {
        if (!this.chart) return;
        
        this.chart.data.datasets[0].data.push({
            x: timeStr,
            y: logProb,
            // 将详细数据直接展平放在数据点对象中，方便 Tooltip 读取
            satName: details.satName || 'Unknown',
            objId: details.objId,
            dist: details.dist,
            prob: details.prob
        });
    }

    update() {
        if (this.chart) this.chart.update('none');
    }

    clear() {
        if (this.chart) {
            this.chart.data.datasets[0].data = [];
            this.chart.update();
        }
    }
}

/**
 * ============================================
 * 模块 4: 表格渲染器 (DOM 操作)
 * ============================================
 */
class TableRenderer {
    constructor(tbodyId, wrapperSelector) {
        this.tbodyId = tbodyId;
        this.wrapperSelector = wrapperSelector;
    }

    addRow(timeStr, objId, tgtId, distMeters, probVal) {
        const tbody = document.getElementById(this.tbodyId);
        const wrapper = document.querySelector(this.wrapperSelector);
        if (!tbody) return;

        const distColor = distMeters < 5000 ? '#ff5050' : 'var(--holo-cyan)';
        
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td>${timeStr}</td>
            <td>${objId}</td>
            <td>${tgtId}</td>
            <td style="color:${distColor}">${distMeters.toFixed(2)}</td>
            <td>${probVal.toExponential(2)}</td>
        `;

        tbody.appendChild(tr);
        
        if (wrapper) wrapper.scrollTop = wrapper.scrollHeight;
    }

    renderBulkSocrates(dataList) {
        const tbody = document.getElementById(this.tbodyId);
        const wrapper = document.querySelector(this.wrapperSelector);
        if (!tbody) return;

        let htmlString = "";
        
        // 遍历数组，纯字符串拼接，不频繁操作真实 DOM
        dataList.forEach(item => {
            const timeStr = item.TCA_UTC ? item.TCA_UTC.replace('T', ' ').substring(0, 19) : 'UNKNOWN';
            const distMeters = Number(item.Min_Range_km) * 1000;
            const probVal = Number(item.Max_Probability);
            
            const distColor = distMeters < 5000 ? '#ff5050' : 'var(--holo-cyan)';
            
            htmlString += `
                <tr>
                    <td>${timeStr}</td>
                    <td>${item.Target_NORAD}</td>
                    <td>${item.Threat_NORAD}</td>
                    <td style="color:${distColor}">${distMeters.toFixed(2)}</td>
                    <td>${probVal.toExponential(2)}</td>
                </tr>
            `;
        });

        // 一次性挂载到页面上，性能拉满
        tbody.innerHTML = htmlString;
        
        // 批量加载完成后，滚动条默认回到顶部
        if (wrapper) wrapper.scrollTop = 0;
    }

    clear() {
        const tbody = document.getElementById(this.tbodyId);
        if (tbody) tbody.innerHTML = "";
    }
}

/**
 * ============================================
 * 主类: UI 管理器 (Facade)
 * ============================================
 */
export class UIManager {
    constructor(config) {
        this.cfg = config;
        
        // 组合各个子模块
        this.layout = new LayoutController(config.DOM.TRIGGERS);
        this.input = new InputController(config.DOM);
        this.chart = new ChartRenderer('collisionChart'); 
        this.table = new TableRenderer(config.DOM.TELEMETRY_BODY, config.DOM.TABLE_WRAPPER);
        this.socratesTable = new TableRenderer('socrates-body', '#socrates-table-wrapper');
        
        this._statusTimer = null;
    }

    updateStatus(text, isError = false) {
        const el = document.getElementById(this.cfg.DOM.STATUS_DISPLAY);
        if (!el) return;

        el.innerText = `STATUS: ${text}`;
        el.style.color = isError ? '#ff5050' : 'var(--holo-cyan)';
        el.style.textShadow = isError ? '0 0 5px #ff0000' : 'var(--glow-text)';

        clearTimeout(this._statusTimer);
        this._statusTimer = setTimeout(() => {
            el.innerText = "STATUS: STANDBY";
            el.style.color = "rgba(255,255,255,0.5)";
            el.style.textShadow = "none";
        }, 3000);
    }

    processDataRow(item) {
        const [dateStr, timeStr, objName, objId, tgtName, tgtId, min_distance, rel_speed, , , collision_prob] = item;
        
        const fullDateTime = `${dateStr} ${timeStr}`;
        const distInMeters = Number(min_distance) * 1000; 
        const probVal = Number(collision_prob);
        const logProb = probVal > 0 ? Math.log10(probVal) : -15;

        this.table.addRow(fullDateTime, objId, tgtId, distInMeters, probVal);
        this.chart.addPoint(fullDateTime, logProb, { 
            satName: objName, 
            objId: objId,
            dist: distInMeters, // 这里的 Key 对应 tooltip 里的 raw.dist
            prob: probVal       // 这里的 Key 对应 tooltip 里的 raw.prob
        });
        this.chart.update(); 
    }

    processSocratesData(dataList) {
        if (!dataList || dataList.length === 0) {
            this.socratesTable.clear();
            return;
        }
        this.socratesTable.renderBulkSocrates(dataList);
    }
    
    clearAllResults() {
        this.chart.clear();
        this.table.clear();
        this.socratesTable.clear();
    }
}