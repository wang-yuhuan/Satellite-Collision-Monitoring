
import { SatelliteApp } from './src/satellite.js';
import { AuthManager } from './src/auth.js';
import { UIManager } from './src/ui-manager.js';
import { CONFIG } from './src/config.js'; // 引入全局配置

import loginTemplate from './src/login.html?raw';

/**
 * ==========================================
 * API 服务 (完整逻辑)
 * ==========================================
 */
class ApiService {
    
    // 发送 TLE 更新请求
    static async updateDATA() {
        // 使用配置中的路径
        const res = await fetch(CONFIG.API.UPDATE_DATA, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        return res.json();
    }

    // 流式获取轨道数据
    static async fetchOrbitStream(url,payload, onRowCallback) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.body) throw new Error("ReadableStream not supported");

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            
            // 保留最后一个可能不完整的片段
            buffer = lines.pop(); 

            for (const line of lines) {
                if (line.trim()) {
                    try {
                        const jsonItem = JSON.parse(line);
                        onRowCallback(jsonItem);
                    } catch (e) {
                        console.warn("JSON Parse Error:", e, line);
                    }
                }
            }
        }
    }

    // [新增] 一次性获取 SOCRATES 数据的请求
    static async fetchSocratesData(payload) {
        const response = await fetch(CONFIG.API.SOCRATES, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        return response.json();
    }
}





// ==========================================
// 主程序入口
// ==========================================

// 实例化应用，传入配置
const earthSatellite = new SatelliteApp("cesiumContainer", CONFIG);
const ui = new UIManager(CONFIG); 

document.addEventListener('DOMContentLoaded', () => {

  document.body.insertAdjacentHTML('beforeend', loginTemplate);
  new AuthManager(CONFIG);

  document.addEventListener('auth:success', () => {
      // 稍微延迟一点点，等登录框消失的动画开始后再弹出 UI，更有层次感
      setTimeout(() => {
          document.body.classList.remove('awaiting-login');
      }, 200); 
  });

  // 1. 绑定 Cesium UI
  earthSatellite.bindUI(CONFIG.DOM);

  // 2. 详情面板开关
  const btnDetail = document.getElementById(CONFIG.DOM.BTN_SHOW_DETAIL);
  if (btnDetail) {
    btnDetail.addEventListener('click', () => 
        ui.layout.toggleDetailPanel(CONFIG.DOM.DETAIL_OVERLAY, CONFIG.DOM.BTN_SHOW_DETAIL)
    );
  }

  // 3. Update TLE 按钮
  const btnUpdate = document.getElementById(CONFIG.DOM.BTN_UPDATE_DATA);
  if (btnUpdate) {
    btnUpdate.addEventListener('click', async () => {
      ui.updateStatus("UPLINKING... DOWNLOAD IN PROGRESS");
      try {
        await ApiService.updateDATA();
        ui.updateStatus("TLE DATABASE SYNCHRONIZED");
      } catch (err) {
        console.error(err);
        ui.updateStatus("CONNECTION FAILURE", true);
      }
    });
  }

  // [新增] 5. OTHER RESULTS 按钮开关
  const btnSocrates = document.getElementById(CONFIG.DOM.BTN_SHOW_SOCRATES);
  if (btnSocrates) {
      btnSocrates.addEventListener('click', () => {
          // 调用你规划写在 LayoutController 或 UIManager 里的切换方法
          ui.layout.toggleSocratesTable(); 
          // 确保此时底部的详情面板是打开状态
          document.getElementById(CONFIG.DOM.DETAIL_OVERLAY).classList.add('active');
      });
  }


  // 4. Grab Orbit 按钮
  const btnGrab = document.getElementById(CONFIG.DOM.BTN_GRAB_ORBIT);
  if (btnGrab) {
    btnGrab.addEventListener('click', async () => {
      const inputs = ui.input.getSearchParameters();

      if (!inputs.start || !inputs.end || !inputs.satId) {
        ui.updateStatus("ERROR: MISSING PARAMETERS", true);
        return;
      }

      ui.clearAllResults();
      ui.layout.showChartOnly(CONFIG.DOM.DETAIL_OVERLAY, CONFIG.DOM.BTN_SHOW_DETAIL);
      ui.updateStatus("ESTABLISHING STREAM...");

      try {
        // [新增] 异步并行请求 SOCRATES 数据，不使用 await 阻塞下方的主算法流
        ApiService.fetchSocratesData({ 
            start_time: inputs.start, 
            end_time: inputs.end, 
            sat_id: inputs.satId 
        }).then(res => {
            if (res.status === 'success' && res.data) {
                // 将数据丢给 UIManager 批量渲染
                ui.processSocratesData(res.data);
            }
        }).catch(e => console.error("Socrates API 请求失败:", e));
        
        await ApiService.fetchOrbitStream(
          CONFIG.API.GRAB_ORBIT,
          { start_time: inputs.start, end_time: inputs.end, sat_id: inputs.satId },
          (dataItem) => {
            ui.processDataRow(dataItem);
          }
        );
        ui.updateStatus("CALCULATION COMPLETE");
      } catch (err) {
        console.error(err);
        ui.updateStatus("SYSTEM ERROR", true);
      }
    });
  }





// 5. MANEUVER Orbit 按钮
  const btnManeuver = document.getElementById(CONFIG.DOM.BTN_MANEUVER_ORBIT);
  if (btnManeuver) {
    btnManeuver.addEventListener('click', async () => {
      // 通过 UI Manager 优雅地获取两组参数
      const baseInputs = ui.input.getSearchParameters();
      const maneuverInputs = ui.input.getManeuverParameters();

      // 基础参数校验
      if (!baseInputs.start || !baseInputs.end || !baseInputs.satId) {
        ui.updateStatus("ERROR: MISSING BASE PARAMETERS", true);
        return;
      }

      // 机动参数校验
      if (!maneuverInputs.manDate || isNaN(maneuverInputs.dvVal) || isNaN(maneuverInputs.vSign)) {
        ui.updateStatus("ERROR: INVALID MANEUVER PARAMETERS", true);
        return;
      }

      ui.clearAllResults();
      ui.layout.showChartOnly(CONFIG.DOM.DETAIL_OVERLAY, CONFIG.DOM.BTN_SHOW_DETAIL);
      ui.updateStatus("CALCULATING MANEUVER TRAJECTORY...");

      try {
        // 合并所有参数构建最终的 payload
        const payload = { 
            start_time: baseInputs.start, 
            end_time: baseInputs.end, 
            sat_id: baseInputs.satId,
            man_date: maneuverInputs.manDate,
            dv_val: maneuverInputs.dvVal,
            v_sign: maneuverInputs.vSign
        };

        // 异步并行请求 SOCRATES 数据
        ApiService.fetchSocratesData(payload).then(res => {
            if (res.status === 'success' && res.data) {
                ui.processSocratesData(res.data);
            }
        }).catch(e => console.error("Socrates API 请求失败:", e));
        
        // 发送流式轨道请求
        await ApiService.fetchOrbitStream(
          CONFIG.API.MANEUVER_ORBIT,
          payload, (dataItem) => {
            ui.processDataRow(dataItem);
        });
        
        ui.updateStatus("MANEUVER CALCULATION COMPLETE");
      } catch (err) {
        console.error(err);
        ui.updateStatus("SYSTEM ERROR", true);
      }
    });
  }


});