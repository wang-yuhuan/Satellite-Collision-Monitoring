export const CONFIG = Object.freeze({
    // 1. API 端点 (统一管理，修改端口只需改这里)
    API: {
        BASE_URL: '', // 如果是同源部署留空，跨域则写 'http://localhost:8000'
        LOGIN: '/api/login',
        REGISTER: '/api/register',

        ACTIVE: '/api/active',      // 对应现役卫星
        STATION: '/api/stations',  // 对应空间站
        DEBRIS: '/api/debris',      // 对应碎片

        UPDATE_DATA: '/api/update_data',
        GRAB_ORBIT: '/api/grab_orbit',
        MANEUVER_ORBIT: '/api/maneuver_orbit',

        SOCRATES: '/api/socrates'
    },

    // 2. DOM 元素 ID (UI 相关的 ID)
DOM: {
        // --- 布局相关 ---
        TRIGGERS: {
            'trigger-left': 'leftSidebar',
            'trigger-right': 'rightSidebar',
            'trigger-bottom': 'bottomDrawer'
        },
        STATUS_DISPLAY: 'status-display',
        
        // --- 详情/弹窗相关 ---
        DETAIL_OVERLAY: 'detail-overlay',
        TELEMETRY_BODY: 'telemetry-body',
        TABLE_WRAPPER: '.table-wrapper', // 注意：这是类选择器，保持现状
        CHART_ID: 'collisionChart',
        BTN_SHOW_DETAIL: 'btn-show-detail',
        BTN_SHOW_SOCRATES: 'btn-show-socrates',

        TOGGLE_LAYER_ACTIVE: 'cb-layer-active',
        TOGGLE_LAYER_STATIONS: 'cb-layer-stations',
        TOGGLE_LAYER_DEBRIS: 'cb-layer-debris',

        // --- 卫星控制面板 (新增/归纳的部分) ---
        BTN_LOAD_LOCAL: 'btn-load-local',    // 加载本地数据
        BTN_CLEAR: 'btn-clear',              // 清空/Purge
        BTN_SEARCH: 'btn-load-online',       // 搜索/Show Orbit
        INPUT_SEARCH: 'input-ids',           // 搜索输入框
        
        BTN_TRACK: 'btn-track-selected',     // 锁定/Engage
        BTN_UNTRACK: 'btn-stop-track',       // 解锁/Disengage
        
        INPUT_DURATION: 'inp-duration',      // 滑块
        LABEL_DURATION: 'val-duration',      // 滑块数值显示 (24h)
        
        // --- TLE 维护 ---
        BTN_UPDATE_DATA: 'btn-update-data',
        BTN_GRAB_ORBIT: 'btn-grab-orbit',
        
        // --- 顶部输入框 ---
        INPUT_START: 'inp-start',
        INPUT_END: 'inp-end',
        INPUT_SAT_ID: 'inp-sat-id',

        // --- [新增] 左侧面板：碰撞参数与机动规划 ---
        INPUT_MAN_DATE: 'inp-man-date', // 机动时间
        INPUT_DV_VAL: 'inp-dv-val',     // Delta V 数值
        INPUT_V_SIGN: 'inp-v-sign',     // V SIGN (-1/1)
        BTN_MANEUVER_ORBIT: 'btn-maneuver-data', // 机动数据按钮
    },

    // 3. 卫星与地球视觉配置
    VISUALS: {
        EARTH_TEXTURE: "/picture/world.200408.3x5400x2700.png",

        MODELS: {
            ACTIVE: "/models/satellite.glb",
            STATION_CORE: "/models/station_core.glb", 
            STATION_VISITOR: "/models/station_visitor.glb",
            DEBRIS: "/models/debris.glb"
        },

        COLORS: {
            HOLO_CYAN: '#00f3ea',
            ALERT_RED: '#ff5050',
            ORBIT_YELLOW: [255, 255, 0, 178], // RGBA 的前三个值 + Alpha (0.7 * 255)

            // [修改点 4] 为不同类型的光点定义默认颜色
            TYPE_ACTIVE: '#00f3ea',   // 青色 (Active)
            TYPE_STATION: '#d000ff',  // 白色 (Station)
            TYPE_DEBRIS: '#ff5050'    // 红色 (Debris
        }
    },
});