# backend/app.py
import sys
import os
import logging
import threading
import json
import datetime
import shutil
from pathlib import Path
from flask import Flask, jsonify, request, Response, stream_with_context, send_from_directory
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
import numpy as np

import webbrowser
import subprocess

import download_TLEs_data
import download_JSONs_data
import setup_TLEfiles
from setup_TLEfiles import generate_objSat_from_temptle, generate_tarSat_from_temptle

from celestrak_collision_events import get_satellite_collision_events, filter_events_by_date_range, clean_socrates_dataframe

from crash_analysis_prepare import *
from Propgation_analysis import *
from dataestr import *
from tools.date_trans import *
from tools.common_tools import *

from collision_avoidance import *

# ==========================================
# 路径自适应系统
# ==========================================
def get_base_paths():
    """
    智能获取资源路径
    Returns:
        dist_folder: 前端静态资源目录 (只读)
        data_root:   数据存储目录 (可读写)
    """
    if getattr(sys, 'frozen', False):
        # [EXE 模式]
        base_dir = Path(sys._MEIPASS)
        dist_folder = base_dir / 'dist'
        exe_location = Path(sys.executable).parent
        data_root = exe_location / 'processed_data'
    else:
        # [开发模式]
        current_dir = Path(__file__).parent
        dist_folder = current_dir.parent / 'frontend' / 'dist'
        data_root = current_dir.parent / 'processed_data'

    return dist_folder, data_root

# 获取路径
DIST_FOLDER, PROCESSED_DATA_DIR = get_base_paths()
JSON_DATA_DIR = PROCESSED_DATA_DIR / "json_data"

# 确保数据目录存在
if not PROCESSED_DATA_DIR.exists():
    try:
        PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
        JSON_DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Warning: Could not create data dir: {e}")

# ==========================================
# 模块路径修正 (Monkey Patching)
# ==========================================
print(f"System Paths Configured:\n -> Frontend: {DIST_FOLDER}\n -> Data: {PROCESSED_DATA_DIR}")

# 修正 download_JSONs_data.py
download_JSONs_data.SAVE_DIR = str(PROCESSED_DATA_DIR)
download_JSONs_data.SAVE_JSON_DIR = str(JSON_DATA_DIR)

download_TLEs_data.SAVE_DIR = str(PROCESSED_DATA_DIR)

# 修正 setup_TLEfiles.py
setup_TLEfiles.WORKSPACE_DIR = str(PROCESSED_DATA_DIR)
setup_TLEfiles.tempfile = str(PROCESSED_DATA_DIR / 'temptle.tle')

# ==========================================
# Flask 初始化
# ==========================================
app = Flask(__name__, static_folder=str(DIST_FOLDER), static_url_path='')
CORS(app)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(asctime)s - %(message)s")

# 数据文件常量
SAT_DATA_TLE = PROCESSED_DATA_DIR / "temptle.tle"
SAT_DATA_JSON = JSON_DATA_DIR / "active_satellite_unique.json"
SAT_DATA_STATIONS = JSON_DATA_DIR / "stations_unique.json" 
SAT_DATA_DEBRIS = JSON_DATA_DIR / "debris_unique.json"
USERS_DB_FILE = PROCESSED_DATA_DIR / "users.json"

if getattr(sys, 'frozen', False):
    # EXE 模式：从打包的内部临时目录读取只读 CSV
    SAT_DIMENSIONS_CSV = str(Path(sys._MEIPASS) / "satellite_dimensions.csv")
else:
    # 开发模式：从常规的 processed_data 读取
    SAT_DIMENSIONS_CSV = str(PROCESSED_DATA_DIR / "satellite_dimensions.csv")

# ==========================================
# 路由定义 (前端托管)
# ==========================================
@app.route('/')
def serve_index():
    if not (DIST_FOLDER / 'index.html').exists():
        return "Frontend build not found! Please run 'npm run build' in frontend folder.", 404
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static_files(path):
    if (DIST_FOLDER / path).exists():
        return send_from_directory(app.static_folder, path)
    return "File not found", 404

# ==========================================
# 业务逻辑与 API
# ==========================================

def load_satellite_json(file_path: Path):
    if not file_path.exists():
        logging.warning("Data file missing: %s", file_path)
        return []
    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data
    except Exception as e:
        logging.error(f"JSON Parse Error: {e}")
        return []

def convert_to_datetime(date_str):
    try:
        year, month, day = map(int, date_str.split('-'))
        return datetime(year, month, day, 0, 0, 0)
    except ValueError:
        return None

def grab_orbit_data(satellite_id, start_date_str, end_date_str):
    ConjStartDate = convert_to_datetime(start_date_str)
    ConjEndDate = convert_to_datetime(end_date_str)

    if ConjStartDate is None or ConjEndDate is None:
        return "Invalid date format!"

    ConjStartJulian = date_to_julian(ConjStartDate)

    ObjCatID = np.array([[satellite_id]])
    
    # 使用修正后的路径
    temp_json_path = str(SAT_DATA_TLE)
    
    if not os.path.exists(temp_json_path):
        logging.info("TLE file missing, downloading...")
        download_TLEs_data.download_tle()
    
    target_file = str(PROCESSED_DATA_DIR / "targets.tle")

    ObjSat_list, objsma = generate_objSat_from_temptle(temp_json_path, ObjCatID)
    TgtSat_list = generate_tarSat_from_temptle(temp_json_path, target_file, ObjSat_list, objsma)

    objNum, tgtNum = len(ObjSat_list), len(TgtSat_list)
    PropTimeStep = 5 
    timeVec = initialize_time_vector(ConjStartDate, ConjEndDate, PropTimeStep)
    
    objSatDetail = ObjSatDetail(objNum)
    objSatDetail.calculate_objSat_detail(ObjSat_list, objNum, ConjStartJulian, SAT_DIMENSIONS_CSV)
    tgtSatDetail = TgtSatDetail(tgtNum, objNum)
    tgtSatDetail.calculate_tgtSat_detail(TgtSat_list, objNum, ConjStartJulian, objSatDetail.objpnow, objSatDetail.objvnow, SAT_DIMENSIONS_CSV)

    analysis_threshold = 3000
    conj_range_threshold = 1000
    min_dis_threshold = 10
    time_step_minutes = 5
    report_file = str(PROCESSED_DATA_DIR / "conjunction_report.csv")
    
    conjunction_assessment(objSatDetail, tgtSatDetail, timeVec, ConjStartDate, time_step_minutes, 
                            analysis_threshold, conj_range_threshold, min_dis_threshold, report_file)
    return "Done"



def maneuver_orbit_data(satellite_id, start_date_str, end_date_str, maneuver_plan):
    ConjStartDate = convert_to_datetime(start_date_str)
    ConjEndDate = convert_to_datetime(end_date_str)

    if ConjStartDate is None or ConjEndDate is None:
        return "Invalid date format!"

    ConjStartJulian = date_to_julian(ConjStartDate)

    ObjCatID = np.array([[satellite_id]])
    
    # 使用修正后的路径
    temp_json_path = str(SAT_DATA_TLE)
    
    if not os.path.exists(temp_json_path):
        logging.info("TLE file missing, downloading...")
        download_TLEs_data.download_tle()

    ObjSat_list, objsma = generate_objSat_from_temptle(temp_json_path, ObjCatID)


    generator = CollisionAvoidanceTLEGenerator(ObjSat_list)

    print(maneuver_plan)
    # 生成机动后数据
    maneuvered_ObjSat_list, maneuvered_objsma = generator.generate_maneuvered_data(maneuver_plan)
    output_file = str(PROCESSED_DATA_DIR / "maneuvered_satellites.tle")
    generator.batch_generate(maneuver_plan, output_file)
    print("机动参数设置完成")

    # 规避后计算新概率
    maneuvered_target_file = str(PROCESSED_DATA_DIR / "maneuvered_targets.tle")
    maneuvered_TgtSat_list = generate_tarSat_from_temptle(temp_json_path, maneuvered_target_file, maneuvered_ObjSat_list, maneuvered_objsma)

    # 初始化用于卫星对象间联合碰撞分析变量
    maneuvered_objNum, maneuvered_tgtNum = len(maneuvered_ObjSat_list), len(maneuvered_TgtSat_list)

    PropTimeStep = 5 
    timeVec = initialize_time_vector(ConjStartDate, ConjEndDate, PropTimeStep)
    
    maneuvered_objSatDetail = ObjSatDetail(maneuvered_objNum)
    maneuvered_objSatDetail.calculate_objSat_detail(maneuvered_ObjSat_list, maneuvered_objNum, ConjStartJulian, SAT_DIMENSIONS_CSV)
    maneuvered_tgtSatDetail = TgtSatDetail(maneuvered_tgtNum, maneuvered_objNum)
    maneuvered_tgtSatDetail.calculate_tgtSat_detail(maneuvered_TgtSat_list, maneuvered_objNum, ConjStartJulian, maneuvered_objSatDetail.objpnow, maneuvered_objSatDetail.objvnow, SAT_DIMENSIONS_CSV)

    analysis_threshold = 3000
    conj_range_threshold = 1000
    min_dis_threshold = 10
    time_step_minutes = 5
    report_file = str(PROCESSED_DATA_DIR / "maneuvered_conjunction_report.csv")
    print(f"start maneuvered_conjunction assessment,total {len(timeVec)} timestamps")

    
    conjunction_assessment(maneuvered_objSatDetail, maneuvered_tgtSatDetail, timeVec, ConjStartDate, time_step_minutes, 
                            analysis_threshold, conj_range_threshold, min_dis_threshold, report_file)
    return "Done"




def load_users():
    if not USERS_DB_FILE.exists(): return {}
    try:
        with USERS_DB_FILE.open('r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def save_users(users_data):
    with USERS_DB_FILE.open('w', encoding='utf-8') as f:
        json.dump(users_data, f, ensure_ascii=False, indent=2)

# --- API Endpoints ---

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.json
    username, password = data.get('username'), data.get('password')
    if not username or not password:
        return jsonify({"success": False, "message": "Missing credentials"}), 400
    users = load_users()
    if username in users:
        return jsonify({"success": False, "message": "User ID already exists"}), 409
    users[username] = {"hash": generate_password_hash(password), "created_at": datetime.now().isoformat()}
    save_users(users)
    return jsonify({"success": True, "message": "Identity created successfully"})

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    username, password = data.get('username'), data.get('password')
    users = load_users()
    if username not in users:
        return jsonify({"success": False, "message": "User ID not found"}), 404
    if check_password_hash(users[username].get('hash'), password):
        return jsonify({"success": True, "message": "Access Granted"})
    return jsonify({"success": False, "message": "Invalid Access Code"}), 401   

@app.get("/api/active")
def list_active():
    sats = load_satellite_json(SAT_DATA_JSON)
    return jsonify({"category": "active", "satellites": sats})

@app.get("/api/stations")
def list_stations():
    sats = load_satellite_json(SAT_DATA_STATIONS)
    return jsonify({"category": "station", "satellites": sats})

@app.get("/api/debris")
def list_debris():
    sats = load_satellite_json(SAT_DATA_DEBRIS)
    return jsonify({"category": "debris", "satellites": sats})

@app.route('/api/grab_orbit', methods=['POST'])
def api_grab_orbit():
    data = request.json
    if not data: return jsonify({"status": "error", "message": "No data"}), 400
    start, end, sat_id = data.get('start_time'), data.get('end_time'), data.get('sat_id')
    
    # 启动后台线程
    thread = threading.Thread(target=grab_orbit_data, args=(sat_id, start, end), daemon=True)
    thread.start()

    def generate():
        while True:
            # data_queue 位于 Propgation_analysis.py 中
            item = data_queue.get() 
            if item is None: break
            yield json.dumps(item) + "\n"

    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')


@app.route('/api/maneuver_orbit', methods=['POST'])
def api_maneuver_orbit():
    data = request.json
    if not data: return jsonify({"status": "error", "message": "No data"}), 400
    start, end, sat_id = data.get('start_time'), data.get('end_time'), data.get('sat_id')
    
    man_date_str = data.get('man_date')
    dv_val = data.get('dv_val')
    v_sign = data.get('v_sign')
    
    try:
        # 如果前端传了包含 'T' 的格式或者尾部带有 'Z'，将其清理兼容
        clean_date_str = man_date_str.replace('Z', '+00:00').replace('T', ' ')
        
        # 兼容处理：如果前端没传秒数（只有 HH:MM），手动补齐 :00
        if clean_date_str.count(':') == 1:
            clean_date_str += ":00"
            
        man_date_dt = datetime.fromisoformat(clean_date_str)
    except Exception as e:
        return jsonify({"status": "error", "message": f"机动时间格式错误: {str(e)}"}), 400
    
    maneuver_plan = [
        {
            'obj_idx': 0, 
            'maneuver_start': man_date_dt,
            'duration_seconds': 0.0,          # 恒定设置为 0.0
            'delta_v_kms': float(dv_val),     # 确保转为浮点数
            'v_sign': int(v_sign)             # 确保转为整数
        }
    ]
    
    # 启动后台线程
    thread = threading.Thread(
        target=maneuver_orbit_data, 
        args=(sat_id, start, end, maneuver_plan), 
        daemon=True
    )
    
    thread.start()

    def generate():
        while True:
            # data_queue 位于 Propgation_analysis.py 中
            item = data_queue.get() 
            if item is None: break
            yield json.dumps(item) + "\n"

    return Response(stream_with_context(generate()), mimetype='application/x-ndjson')

@app.route('/api/update_data', methods=['POST'])
def api_update_data():
    try:
        import download_TLEs_data
        
        logging.info("Updating TLEs...")
        download_TLEs_data.download_tle()
        
        base_groups = ['active', 'stations']
        DEBRIS_GROUPS_LIST = ['analyst', 'last-30-days','iridium-33-debris', 'cosmos-2251-debris', 'fengyun-1c-debris', 'cosmos-1408-debris']
        target_groups = base_groups + DEBRIS_GROUPS_LIST
        
        download_JSONs_data.download_json(target_groups)
        download_JSONs_data.process_and_categorize(target_groups)
        download_JSONs_data.cleanup_raw_files(target_groups)
        
        return jsonify({"status": "success", "message": "Database Updated"})
    except Exception as e:
        logging.error(f"Update failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route('/api/socrates', methods=['POST'])
def api_socrates():
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "没有接收到请求数据"}), 400
        
    # 与 grab_orbit 保持完全一致的参数获取方式
    start_time_str = data.get('start_time') 
    end_time_str = data.get('end_time')
    sat_id = data.get('sat_id')

    if not sat_id or not start_time_str or not end_time_str:
        return jsonify({"status": "error", "message": "缺失参数: sat_id, start_time 或 end_time"}), 400

    # 同时转换开始和结束时间
    start_date = convert_to_datetime(start_time_str)
    end_date = convert_to_datetime(end_time_str)

    if not start_date or not end_date:
        return jsonify({"status": "error", "message": "时间格式不正确，请使用 YYYY-MM-DD"}), 400

    # 【重要细节】：convert_to_datetime 默认生成的是 00:00:00
    # 为了让 end_time 包含那一整天的数据（比如包含 3月10日晚上的事件），
    # 我们将结束时间手动调整为当天的 23:59:59
    end_date = end_date.replace(hour=0,  minute=0, second=0)

    # 1. 获取所有数据
    df_all_events = get_satellite_collision_events(sat_id)
    
    if df_all_events is None or df_all_events.empty:
        return jsonify({"status": "success", "data": [], "message": "未找到该卫星的碰撞预测"})

    df_filtered = filter_events_by_date_range(df_all_events, start_date, end_date)

    df_cleaned = clean_socrates_dataframe(df_filtered)

    if df_cleaned.empty:
        return jsonify({"status": "success", "data": [], "message": f"在 {start_time_str} 至 {end_time_str} 期间没有潜在的碰撞事件"})

    # 将 Pandas 的时间对象转换为标准 ISO 字符串
    if 'TCA_UTC' in df_cleaned.columns:
        df_cleaned['TCA_UTC'] = df_cleaned['TCA_UTC'].dt.strftime('%Y-%m-%dT%H:%M:%S.%f')

    # 处理 DataFrame 中的 NaN 值，替换为 None
    df_cleaned = df_cleaned.replace({np.nan: None})

    # 将 DataFrame 转换为字典列表格式
    result_data = df_cleaned.to_dict(orient='records')

    return jsonify({
        "status": "success",
        "data": result_data,
        "total_events": len(result_data)
    })
    
    
if __name__ == "__main__":
    print("Starting Flask server...")
    print(f"Serving frontend from: {DIST_FOLDER}")
    
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        
        frontend_dir = Path(__file__).parent.parent / 'frontend'
        if frontend_dir.exists():
            print(">>> 检测到前端目录，正在后台自动启动 npm 进程...")
            is_windows = sys.platform.startswith('win')

            subprocess.Popen(['npm', 'run', 'dev'], cwd=frontend_dir, shell=is_windows)
        else:
            print(">>> 未找到前端目录，跳过 npm 启动。")

        # 2. 自动打开浏览器
        def open_browser():
            target_url = "http://127.0.0.1:8000" 
            print(f">>> 正在自动唤起浏览器访问: {target_url}")
            webbrowser.open(target_url)
            
        # 延迟 1.5 秒，给 Flask（和 npm）一点初始化启动的时间
        threading.Timer(1.5, open_browser).start()

    # 启动 Flask
    app.run(host="127.0.0.1", port=8000, debug=True)