import "cesium/Build/Cesium/Widgets/widgets.css";
import {
  Viewer,
  SingleTileImageryProvider,
  Color,
  Cartesian3,
  DistanceDisplayCondition,
  PointPrimitiveCollection,
  defined,
  Entity,
  CallbackProperty,
  JulianDate,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  Math as CesiumMath,
} from "cesium";
import * as satellite from "satellite.js";

/**
 * ==========================================
 * 1. 全局配置 (Configuration)
 * ==========================================
 */
const INTERNAL_CONFIG = Object.freeze({
  assets: {
    earthTexture: "/picture/world.200408.3x5400x2700.png",
    satModel: "/models/satellite.glb",
  },
  limits: {
    maxSats: 50_000,
    maxActiveModels: 300,
    maxUpgradePerCheck: 50,
  },
  distances: {
    nearModelUpgrade: 5_000_000,
    modelDisplay: { near: 0.0, far: 5_000_000.0 },
    // 调大一点确保都能看到
    primitives: { near: 0.0, far: 5000_000_000.0 },
  },
  orbit: {
    durationMinutes: 24 * 60,
    stepMinutes: 3,
    width: 2,
    color: Color.YELLOW.withAlpha(0.7),
  },
  colors: [
    Color.YELLOW,
    Color.CYAN,
    Color.LIME,
    Color.ORANGE,
    Color.PINK,
    Color.WHITE,
  ],
});

/**
 * ==========================================
 * 2. 工具类 (Utilities)
 * ==========================================
 */
const Utils = {
  $(selector) {
    return document.querySelector(selector);
  },
  getColor(index) {
    return INTERNAL_CONFIG.colors[index % INTERNAL_CONFIG.colors.length];
  },
  isNumeric(str) {
    return /^\d+$/.test(str);
  },
};

/**
 * ==========================================
 * 3. 卫星物理计算类：
 * 处理 TLE 解析、坐标系转换 (TEME -> ECEF -> Cartesian3)
 * ==========================================
 */
class SatelliteCalculator {
  // 修改：直接接收后端传来的 JSON 对象
  static computePosition(satJson, time = new Date()) {
    const name = satJson.OBJECT_NAME || "Unknown"; // 适配 JSON 键名
    let satrec;

    try {
      satrec = satellite.json2satrec(satJson);
    } catch (e) {
      console.error("JSON 转换 SatRec 失败:", name, e);
      return null;
    }

    const pos = this._propagateToCartesian(satrec, time);
    if (!pos) return null;

    return {
      position: pos,
      name: name,
      satrec,
      raw: satJson // 仅保留原始数据对象供 UI 使用
    };
  }

  static computeOrbitPath(satrec, cesiumTime, durationMinutes) {
    const positions = [];
    // 将 Cesium 时间转换为 JS Date
    const startJsDate = JulianDate.toDate(cesiumTime);

    const actualDuration = durationMinutes || INTERNAL_CONFIG.orbit.durationMinutes;
    const step = INTERNAL_CONFIG.orbit.stepMinutes;

    for (let t = 0; t <= actualDuration; t += step) {
      const time = new Date(startJsDate.getTime() + t * 60 * 1000);
      const pos = this._propagateToCartesian(satrec, time);
      if (pos) positions.push(pos);
    }
    return positions;
  }

  static _propagateToCartesian(satrec, time) {
      const pv = satellite.propagate(satrec, time);
      if (!pv || !pv.position || !isFinite(pv.position.x)) return null;

      const gmst = satellite.gstime(time);
      const positionEcf = satellite.eciToEcf(pv.position, gmst);
      
      // satellite.js 单位是 km，Cesium 是 m
      return new Cartesian3(
          positionEcf.x * 1000,
          positionEcf.y * 1000,
          positionEcf.z * 1000
      );
  }
}

/**
 * ==========================================
 * 4. 场景管理类 (SceneManager)
 * 负责 Cesium Viewer 操作、Entity/Primitive 管理
 * ==========================================
 */
class SceneManager {
  constructor(containerId, visualConfig) {
    this.cfg = visualConfig;
    this.viewer = this._initViewer(containerId);
    this.satPointCollection = this.viewer.scene.primitives.add(
      new PointPrimitiveCollection()
    );
    this.orbitEntity = null;
  }

  _initViewer(containerId) {
    const viewer = new Viewer(containerId, {
      animation: false,
      timeline: false,
      baseLayerPicker: false,
      geocoder: false,
      navigationHelpButton: false,
      homeButton: true,
      sceneModePicker: true,
      infoBox: true,
      selectionIndicator: true,
    });

    viewer.cesiumWidget.creditContainer.style.display = "none";
    viewer.scene.globe.baseColor = Color.DARKBLUE;
    viewer.imageryLayers.removeAll();
    viewer.imageryLayers.addImageryProvider(
      new SingleTileImageryProvider({
        url: INTERNAL_CONFIG.assets.earthTexture,
        tileWidth: 5400,
        tileHeight: 2700,
      })
    );
    viewer.scene.globe.enableLighting = true;

    // 降低 FPS 刷新率要求，不强制每帧都算满
    viewer.targetFrameRate = 60;
    viewer.clock.shouldAnimate = true;
    viewer.clock.multiplier = 1;

    return viewer;
  }

  // 创建轻量级视觉点 (Primitive)，不直接创建 Entity 以节省内存
  addSatellitePoint(data, color, type) {
    const { position, name, satrec, raw } = data;
    const satId = String(raw.NORAD_CAT_ID);

    const satData = {
      id: satId,
      name: `${name}(${satId})`,
      satrec,
      raw, 
      staticPosition: position,
      color: color,
      entity: null,
      type: type,
    };

    // 只创建视觉点
    const point = this.satPointCollection.add({
      position: position,
      color: color,
      pixelSize: 2,
      distanceDisplayCondition: new DistanceDisplayCondition(
        INTERNAL_CONFIG.distances.primitives.near,
        INTERNAL_CONFIG.distances.primitives.far
      ),
      id: satData,
    });

    // 双向绑定
    satData.primitive = point;
    return satData;
  }

  // 动态创建 Entity，用于模型显示或轨道追踪
  createEntityForSat(satData) {
    if (satData.entity) return satData.entity;

    const satrec = satData.satrec;

    const positionProp = new CallbackProperty((time, result) => {
      const jsDate = JulianDate.toDate(time);
      const pv = satellite.propagate(satrec, jsDate);

      if (!pv || !pv.position) return satData.staticPosition;

      const gmst = satellite.gstime(jsDate);
      const geo = satellite.eciToGeodetic(pv.position, gmst);

      if (result) {
        return Cartesian3.fromRadians(
          geo.longitude,
          geo.latitude,
          geo.height * 1000,
          undefined, 
          result
        );
      }
      return Cartesian3.fromRadians(
        geo.longitude,
        geo.latitude,
        geo.height * 1000
      );
    }, false);

    const entity = this.viewer.entities.add({
      id: satData.id, 
      name: satData.name,
      position: positionProp,
      point: { show: false }, 
      show: true,
    });

    // 挂载数据以便识别
    entity._satData = satData;
    satData.entity = entity;

    return entity;
  }

  // 销毁 Entity，释放显存和计算资源
  destroyEntityForSat(satData) {
      if (satData.entity) {
          if (this.viewer.selectedEntity === satData.entity) return;
          
          this.viewer.entities.remove(satData.entity);
          satData.entity._satData = null; // [建议] 断开引用
          satData.entity = null;
      }
  }

  // 升级显示级别：从点升级为 3D 模型
  upgradeToModel(satData) {
    const entity = this.createEntityForSat(satData);

    if (!entity.model) {
      let modelUri = INTERNAL_CONFIG.assets.satModel;
      let modelScale = 30.0;
      let minPixel = 64;

      // 根据卫星类型加载不同的模型和缩放比例
      if (satData.type === 'STATION') {
          const satId = Number(satData.raw.NORAD_CAT_ID); // 获取 NORAD ID
          
          // 判断是否为核心空间站 (ISS: 25544, CSS: 48274)
          if (satId === 25544 || satId === 48274) {
              // --- Model A: 核心空间站 ---
              modelUri = (this.cfg && this.cfg.MODELS && this.cfg.MODELS.STATION_CORE) 
                         ? this.cfg.MODELS.STATION_CORE
                         : "/models/station_core.glb";
              // 空间站非常大
              modelScale = 240.0; 
          } else {
              // --- Model B: 访客飞船/其他 ---
              modelUri = (this.cfg && this.cfg.MODELS && this.cfg.MODELS.STATION_VISITOR) 
                         ? this.cfg.MODELS.STATION_VISITOR 
                         : "/models/station_visitor.glb";
              // 飞船比较小，使用普通卫星的大小
              modelScale = 180.0;
          }
      } 
      // 其他类型的处理 (ACTIVE / DEBRIS)
      else if (satData.type === 'DEBRIS') {
          modelUri = this.cfg.MODELS.DEBRIS;
          modelScale = 30.0;
      } 
      else {
          // ACTIVE 类型
          modelUri = this.cfg.MODELS.ACTIVE;
          modelScale = 30.0;
      }

      entity.model = {
        uri: modelUri,
        scale: modelScale,
        minimumPixelSize: minPixel,
        maximumScale: 20000.0,
        distanceDisplayCondition: new DistanceDisplayCondition(
          INTERNAL_CONFIG.distances.modelDisplay.near,
          INTERNAL_CONFIG.distances.modelDisplay.far
        ),
      };
    }

    // 调整 Primitive 的显示距离，防止模型和点重叠
    if (satData.primitive) {
      satData.primitive.show = true; // 确保是开启状态
      satData.primitive.distanceDisplayCondition = new DistanceDisplayCondition(
        INTERNAL_CONFIG.distances.modelDisplay.far, 
        INTERNAL_CONFIG.distances.primitives.far
      );
    }
  }

  // 降级显示级别：销毁模型，恢复为点
  downgradeFromModel(satData) {
    if (satData.entity && satData.primitive) {
      const currentPos = satData.entity.position.getValue(
        this.viewer.clock.currentTime
      );

      if (currentPos) {
        satData.primitive.position = currentPos;
        satData.staticPosition = currentPos;

        if (satData._cacheRef) {
          satData._cacheRef.x = currentPos.x;
          satData._cacheRef.y = currentPos.y;
          satData._cacheRef.z = currentPos.z;
        }
      }
      
      satData.primitive.show = true;
      satData.primitive.distanceDisplayCondition = new DistanceDisplayCondition(
        INTERNAL_CONFIG.distances.primitives.near,
        INTERNAL_CONFIG.distances.primitives.far
      );
    }
    this.destroyEntityForSat(satData);
  }

  drawOrbit(positions) {
    this.clearOrbit();
    if (!positions.length) return;
    this.orbitEntity = this.viewer.entities.add({
      polyline: {
        positions,
        width: INTERNAL_CONFIG.orbit.width,
        material: INTERNAL_CONFIG.orbit.color,
      },
    });
  }

  clearOrbit() {
    if (this.orbitEntity) {
      this.viewer.entities.remove(this.orbitEntity);
      this.orbitEntity = null;
    }
  }

  clearAll() {
    this.viewer.entities.removeAll();
    this.satPointCollection.removeAll();
    this.viewer.trackedEntity = undefined;
    this.orbitEntity = null;
  }
}

/**
 * ==========================================
 * 5. 应用控制器 (SatelliteApp)
 * ==========================================
 */
export class SatelliteApp {
  constructor(containerId, fullConfig) {

    this.config = fullConfig;
    this.api = fullConfig.API;

    this.sceneManager = new SceneManager(containerId, fullConfig.VISUALS);
    this.viewer = this.sceneManager.viewer;

    this.viewer.clock.shouldAnimate = true;

    this.layers = { ACTIVE: [], STATION: [], DEBRIS: [] };
    this.layerVisibility = { ACTIVE: true, STATION: true, DEBRIS: true };

    this.physicsCache = [];
    this.checkPointer = 0;
    this.checkChunkSize = 2000;
    this.activeModelQueue = [];

    this.handler = null; 
    this.removePostRender = null; 

    this._initEventHandlers();
    this._initPostRenderLoop();
  }

  async loadLayer(typeKey) {
    const apiUrl = this.api[typeKey]; 
    if (!apiUrl) return;

    this.clearLayer(typeKey);

    const colorHex = this.config.VISUALS.COLORS['TYPE_' + typeKey] || '#ffffff';
    const color = Color.fromCssColorString(colorHex);

    try {
      const res = await fetch(apiUrl);
      const data = await res.json();
      const sats = data.satellites || [];

      sats.forEach((rec) => {
        const info = SatelliteCalculator.computePosition(rec);
        if (info) {
          const satData = this.sceneManager.addSatellitePoint(info, color, typeKey);

          const cacheItem = {
            x: info.position.x,
            y: info.position.y,
            z: info.position.z,
            satData: satData,
            flags: { hasModel: false },
            type: typeKey 
          };

          satData._cacheRef = cacheItem;
          
          // 存入总表 (用于物理计算)
          this.physicsCache.push(cacheItem);
          // 存入分表 (用于开关图层)
          this.layers[typeKey].push(satData);
        }
      });
    } catch (err) {
      console.error(`Error loading layer ${typeKey}`, err);
    }
  }

  // 切换图层开关
  toggleLayer(typeKey, isVisible) {
    this.layerVisibility[typeKey] = isVisible;
    const layerSats = this.layers[typeKey];
    if (!layerSats) return;

    layerSats.forEach(satData => {
      if (satData.primitive) satData.primitive.show = isVisible;

      if (!isVisible) {
        this.sceneManager.destroyEntityForSat(satData);
        if (satData._cacheRef) satData._cacheRef.flags.hasModel = false;
      }
    });
  }

  clearLayer(typeKey) {
    const layerSats = this.layers[typeKey];
    if (!layerSats || layerSats.length === 0) return;

    // 从场景中移除视觉元素
    layerSats.forEach(satData => {
      // 移除光点
      if (satData.primitive) {
        this.sceneManager.satPointCollection.remove(satData.primitive);
      }
      // 移除 Entity (模型/轨道)
      this.sceneManager.destroyEntityForSat(satData);
    });

    // 从物理计算缓存中剔除该类型的数据
    this.physicsCache = this.physicsCache.filter(item => item.type !== typeKey);

    // 清空图层记录
    this.layers[typeKey] = [];
  }

  clear() {
    this.sceneManager.clearAll();
    this.physicsCache = [];
    this.activeModelQueue = [];
    this.checkPointer = 0;
  }

  // 统一升级入口
  requestModelUpgrade(cacheItem, currentDist) {
    if (!cacheItem || cacheItem.flags.hasModel) return;

    // 队列已满：剔除最远的
    if (this.activeModelQueue.length >= INTERNAL_CONFIG.limits.maxActiveModels) {
      let maxDist = -1;
      let maxIndex = -1;

      for (let i = 0; i < this.activeModelQueue.length; i++) {
        if (this.activeModelQueue[i].dist > maxDist) {
          maxDist = this.activeModelQueue[i].dist;
          maxIndex = i;
        }
      }

      if (maxIndex !== -1 && currentDist < maxDist) {
        const toRemove = this.activeModelQueue[maxIndex];

        // 降级：这会销毁 Entity
        this.sceneManager.downgradeFromModel(toRemove.cacheRef.satData);
        toRemove.cacheRef.flags.hasModel = false;

        this.activeModelQueue.splice(maxIndex, 1);
      } else {
        return;
      }
    }

    // 升级：这会创建 Entity
    this.sceneManager.upgradeToModel(cacheItem.satData);
    cacheItem.flags.hasModel = true;

    this.activeModelQueue.push({
      dist: currentDist,
      cacheRef: cacheItem,
    });
  }

  _initEventHandlers() {
    this.handler = new ScreenSpaceEventHandler(this.viewer.scene.canvas);

    this.handler.setInputAction((movement) => {
      const picked = this.viewer.scene.pick(movement.position);
      
      // 定义一个变量来统一接收 satData
      let satData = null;

      if (defined(picked) && picked.id) {
          // 情况 A: 点击的是光点 (PointPrimitive)
          if (picked.id.satrec) {
              satData = picked.id;
          } 
          // 情况 B: 点击的是模型 (Entity)
          else if (picked.id._satData) {
              satData = picked.id._satData;
          }
      }

      // 如果成功获取到了数据，执行选中逻辑
      if (satData) {
        // 选中时自动开启时间流动，让用户看到轨道动画
        this.viewer.clock.shouldAnimate = true;

        const entity = this.sceneManager.createEntityForSat(satData);
        this.viewer.selectedEntity = entity;

        if (satData._cacheRef) {
          this.requestModelUpgrade(satData._cacheRef, 0);
        }
      } else {
        // 只有当并未点击到任何有效物体时才取消
        if (!defined(picked)) {
            this.viewer.selectedEntity = undefined;
        }
      }
    }, ScreenSpaceEventType.LEFT_CLICK);
  }

  _initPostRenderLoop() {
    this.removePostRender = this.viewer.scene.postRender.addEventListener(
      () => {
        this._checkNearSatellitesChunk();
        this._updateTelemetry();
      }
    );
  }

  destroy() {
    this.clear();
    if (this.handler) {
      this.handler.destroy();
      this.handler = null;
    }
    if (this.removePostRender) {
      this.removePostRender();
      this.removePostRender = null;
    }
  }

  // 核心循环：分块检查卫星距离，处理模型升级/降级逻辑
  _checkNearSatellitesChunk() {
    if (this.physicsCache.length === 0) return;

    const cameraPos = this.viewer.camera.positionWC;
    const currentTime = this.viewer.clock.currentTime;

    const nowJsDate = JulianDate.toDate(currentTime);
    const gmst = satellite.gstime(nowJsDate);

    // 距离阈值配置
    const upgradeDist = INTERNAL_CONFIG.distances.nearModelUpgrade;
    const upgradeDistSq = upgradeDist * upgradeDist; 
    const downgradeDist = upgradeDist + 500000; // 缓冲区域

    const tempSatPos = new Cartesian3();

    // 倒序遍历活跃队列，主动剔除飞远的卫星
    for (let i = this.activeModelQueue.length - 1; i >= 0; i--) {
      const item = this.activeModelQueue[i];
      const entity = item.cacheRef.satData.entity;

      if (
        entity &&
        (this.viewer.trackedEntity === entity ||
          this.viewer.selectedEntity === entity)
      ) {
        continue;
      }

      let remove = false;
      if (entity) {
        const currentPos = entity.position.getValue(currentTime);
        if (currentPos) {
          const dist = Cartesian3.distance(currentPos, cameraPos);
          item.dist = dist; // 更新队列里的距离记录

          if (dist > downgradeDist) {
            remove = true;
          }
        } else {
          remove = true; // 位置失效则移除
        }
      } else {
        remove = true; // Entity 丢失则移除
      }

      if (remove) {
        this.sceneManager.downgradeFromModel(item.cacheRef.satData);
        if (item.cacheRef) item.cacheRef.flags.hasModel = false;
        this.activeModelQueue.splice(i, 1);
      }
    }

    // 遍历静态缓存 (Chunk Loop)
    let processedCount = 0;
    const total = this.physicsCache.length;
    const candidates = [];
    const loopLimit = Math.min(this.checkChunkSize, total);

    while (processedCount < loopLimit) {
      if (this.checkPointer >= total) this.checkPointer = 0;
      const item = this.physicsCache[this.checkPointer];
      this.checkPointer++;
      processedCount++;

      if (item.flags.hasModel) continue;

      const pv = satellite.propagate(item.satData.satrec, nowJsDate);

      if (pv && pv.position && isFinite(pv.position.x)) {
        
        const positionEcf = satellite.eciToEcf(pv.position, gmst);

        // satellite.js 单位是 km，Cesium 是 m
        const satX = positionEcf.x * 1000;
        const satY = positionEcf.y * 1000;
        const satZ = positionEcf.z * 1000;

        // 实时更新光点位置
        const prim = item.satData.primitive;
        if (prim) {
           prim.position.x = satX;
           prim.position.y = satY;
           prim.position.z = satZ;
        }

        item.x = satX;
        item.y = satY;
        item.z = satZ;

        tempSatPos.x = satX;
        tempSatPos.y = satY;
        tempSatPos.z = satZ;

        const distSq = Cartesian3.distanceSquared(tempSatPos, cameraPos);

        if (distSq < upgradeDistSq) {
          candidates.push({ 
            item, 
            dist: Math.sqrt(distSq)
          });
        }
      }
    }

    // 处理升级候选列表
    if (candidates.length > 0) {
      // 按距离最近排序
      candidates.sort((a, b) => a.dist - b.dist);
      
      const count = Math.min(
        candidates.length,
        INTERNAL_CONFIG.limits.maxUpgradePerCheck
      );
      
      for (let k = 0; k < count; k++) {
        this.requestModelUpgrade(candidates[k].item, candidates[k].dist);
      }
    }
  }

  _trackEntity(satData, duration) {
    const entity = this.sceneManager.createEntityForSat(satData);

    if (satData._cacheRef) {
      this.requestModelUpgrade(satData._cacheRef, 0);
    }

    const positions = SatelliteCalculator.computeOrbitPath(
      satData.satrec,
      this.viewer.clock.currentTime,
      duration
    );
    this.sceneManager.drawOrbit(positions);

    this.viewer.selectedEntity = entity;

    this.viewer.trackedEntity = undefined;

    this.viewer.flyTo(entity, {
        duration: 2.0, // 飞行时间 (秒)
        // offset: new Cesium.HeadingPitchRange(0, -0.78, 5000000), // 指定飞过去后的固定角度
    }).then((result) => {
        // 飞行结束后，如果是正常结束（result 为 true），则锁定摄像机
        if (result) {
            this.viewer.trackedEntity = entity;
        }
    });
  }

  _initTelemetryElements() {
    this.telemetryDom = {
      velocity: document.getElementById('val-velocity'),
      altitude: document.getElementById('val-altitude'),
      lat: document.getElementById('val-lat'),
      lon: document.getElementById('val-lon')
    };
  }

  // 实时更新遥测数据面板
  _updateTelemetry() {
    if (!this.telemetryDom) {
        this._initTelemetryElements();
    }

    const dom = this.telemetryDom;
    if (!dom.velocity) return; 

    const entity = this.viewer.selectedEntity;

    if (defined(entity) && entity._satData && entity._satData.satrec) {
        
        const satrec = entity._satData.satrec;
        const now = this.viewer.clock.currentTime;
        const jsDate = JulianDate.toDate(now);

        // propagate 会返回位置 (position) 和速度 (velocity)
        const pv = satellite.propagate(satrec, jsDate);

        if (pv && pv.velocity && pv.position) {
            // A. 计算速度 (km/s)
            const v = pv.velocity; 
            const speedVal = Math.sqrt(v.x*v.x + v.y*v.y + v.z*v.z);
            
            // B. 计算地理坐标 (Lat/Lon/Alt)
            const gmst = satellite.gstime(jsDate);
            const geo = satellite.eciToGeodetic(pv.position, gmst);
            
            // C. 更新 UI
            dom.velocity.innerText = speedVal.toFixed(3); // km/s
            dom.altitude.innerText = geo.height.toFixed(1); // km
            
            const latVal = CesiumMath.toDegrees(geo.latitude);
            const lonVal = CesiumMath.toDegrees(geo.longitude);

            // 纬度处理：绝对值 + N/S
            const latDir = latVal >= 0 ? "N" : "S";
            dom.lat.innerText = `${Math.abs(latVal).toFixed(2)} ${latDir}`; // 例如: 23.68 N

            // 经度处理：绝对值 + E/W
            const lonDir = lonVal >= 0 ? "E" : "W";
            dom.lon.innerText = `${Math.abs(lonVal).toFixed(2)} ${lonDir}`; // 例如: 120.53 E

        }
    } else {
        // 待机状态 (未选中任何卫星)
        if (dom.velocity.innerText !== "--") {
            dom.velocity.innerText = "--";
            dom.altitude.innerText = "--";
            dom.lat.innerText = "--";
            dom.lon.innerText = "--";
        }
    }
  }

  bindUI(domConfig) {
      // 辅助函数：根据 ID 获取元素
      const el = (id) => document.getElementById(id);

      // 直接从配置解构出我们需要的所有 ID Key
      const {
          BTN_LOAD_LOCAL, BTN_CLEAR,
          BTN_SEARCH, INPUT_SEARCH,
          BTN_TRACK, BTN_UNTRACK,
          INPUT_DURATION, LABEL_DURATION,

          TOGGLE_LAYER_ACTIVE, 
          TOGGLE_LAYER_STATIONS, 
          TOGGLE_LAYER_DEBRIS
      } = domConfig;

      // 基础功能绑定
      el(BTN_LOAD_LOCAL)?.addEventListener("click", () => {
         layerMap.forEach(item => {
             const checkbox = el(item.id);

             if (checkbox && checkbox.checked) {
                 this.loadLayer(item.key);
                 this.toggleLayer(item.key, true); 
             } 
             else {
                 this.clearLayer(item.key);
             }
         });
      });

      const layerMap = [
          { key: 'ACTIVE',  id: TOGGLE_LAYER_ACTIVE },
          { key: 'STATION', id: TOGGLE_LAYER_STATIONS },
          { key: 'DEBRIS',  id: TOGGLE_LAYER_DEBRIS }
      ];

      layerMap.forEach(item => {
          const checkbox = el(item.id);
          if (checkbox) {
              checkbox.addEventListener('change', (e) => {
                  // 只控制显隐，不触发 loadLayer
                  this.toggleLayer(item.key, e.target.checked);
              });
          }
      });


      el(BTN_CLEAR)?.addEventListener("click", () => this.clear());


      // 滑块交互 (Duration Slider)
      const durationInput = el(INPUT_DURATION);
      const durationLabel = el(LABEL_DURATION);

      if (durationInput && durationLabel) {
          durationInput.addEventListener("input", (e) => {
              const val = parseInt(e.target.value, 10);
              durationLabel.textContent = `${(val / 60).toFixed(1)}h`;
          });
      }

      // "SHOW ORBIT" 搜索按钮
      const searchBtn = el(BTN_SEARCH);
      const searchInput = el(INPUT_SEARCH);

      if (searchBtn && searchInput && durationInput) {
          searchBtn.addEventListener("click", () => {
              const val = searchInput.value.trim();
              if (!val) return alert("Please enter a NORAD ID or Name.");

              // 查找逻辑
              const found = this.physicsCache.find((c) => {
                  const meta = c.satData;
                  return Utils.isNumeric(val) 
                      ? meta.id === val 
                      : meta.name.toUpperCase().includes(val.toUpperCase());
              });

              if (found) {
                  // 直接使用上面获取到的 durationInput
                  this._trackEntity(found.satData, parseInt(durationInput.value, 10));
              } else {
                  alert("Target not found in local cache.");
              }
          });
      }

      // 锁定与解锁 (Track / Untrack)
      el(BTN_TRACK)?.addEventListener("click", () => {
          if (this.viewer.selectedEntity && this.viewer.selectedEntity._satData) {
              // 再次利用 durationInput 的当前值
              this._trackEntity(this.viewer.selectedEntity._satData, parseInt(durationInput.value, 10));
          }
      });

      el(BTN_UNTRACK)?.addEventListener("click", () => {
          this.viewer.trackedEntity = undefined;
          this.sceneManager.clearOrbit();
      });
    }
}