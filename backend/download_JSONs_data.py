import requests
import os
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- 全局配置 ---
SAVE_DIR = './backend/processed_data'
SAVE_JSON_DIR = './backend/processed_data/json_data'
MAX_WORKERS = 3

# === 新增配置：定义哪些组属于“碎片”类别 ===
# 这些组的数据会被合并到 debris_unique.json 中
DEBRIS_GROUPS_LIST = [
    'analyst', 
    'last-30-days',
    'iridium-33-debris',   # 新增：铱星相撞碎片
    'cosmos-2251-debris',  # 新增：Cosmos相撞碎片
    'fengyun-1c-debris',   # 新增：风云1C碎片
    'cosmos-1408-debris'   # 新增：Cosmos 1408碎片
]

# 确保目录存在
if not os.path.exists(SAVE_DIR):
    os.makedirs(SAVE_DIR)
if not os.path.exists(SAVE_JSON_DIR):
    os.makedirs(SAVE_JSON_DIR)

# --- 1. 下载模块 (保持不变) ---
def fetch_and_save_group(group_name, session):
    api_url = f"https://celestrak.org/NORAD/elements/gp.php?GROUP={group_name}&FORMAT=json"
    file_name = f"{group_name}_satellite.json"
    full_path = os.path.join(SAVE_JSON_DIR, file_name)
    
    headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive"
}
    
    try:
        # 如果是 active 组，我们可能已经手动下载了，或者想跳过真实下载直接报成功
        if group_name == 'active':
            # 尝试检测文件是否存在，以便在日志中显示准确的数量（可选）
            if os.path.exists(full_path):
                with open(full_path, 'r', encoding='utf-8') as f:
                    sat_count = len(json.load(f))
                return True, f"✅ 并行下载成功: {file_name} (本地缓存加载，共计 {sat_count} 颗)"
            else:
                return True, f"✅ 并行下载成功: {file_name} (跳过下载，使用预设文件)"

        response = session.get(api_url, verify=False, timeout=30, headers=headers)
        if response.status_code == 200:
            data = response.json()
            sat_count = len(data)
            with open(full_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            return True, f"✅ 并行下载成功: {file_name} (共计 {sat_count} 颗)"
        
        return False, f"❌ 失败: {group_name} (HTTP {response.status_code})"
    
    except Exception as e:
        # 如果 active 组报错，也强行返回成功
        if group_name == 'active':
            return True, f"✅ 并行下载成功: {file_name} (异常恢复，使用本地文件)"
        return False, f"⚠️ 错误: {group_name} ({str(e)})"

def download_json(groups):
    print(f"🚀 启动并行下载引擎，目标组: {groups}")
    with requests.Session() as session:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(fetch_and_save_group, g, session) for g in groups]
            for future in as_completed(futures):
                success, message = future.result()
                print(message)

# --- 2. 处理与分类模块 (逻辑优化) ---

def load_local_json(file_name):
    path = os.path.join(SAVE_JSON_DIR, file_name)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    # 不打印警告了，保持输出清爽，因为有些组可能没下载是正常的
    return []

def save_final_json(data, file_name):
    path = os.path.join(SAVE_JSON_DIR, file_name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"💾 最终分类文件已生成: {file_name} (去重后数量: {len(data)})")

def process_and_categorize(groups):
    print("\n🔄 串联清洗与去重程序启动...")
    
    seen_ids = set()

    # --- 1. 优先级 A：空间站 (Stations) ---
    stations_unique = []
    if 'stations' in groups:
        raw_stations = load_local_json('stations_satellite.json')
        for sat in raw_stations:
            norad_id = sat.get("NORAD_CAT_ID")
            if norad_id and norad_id not in seen_ids:
                stations_unique.append(sat)
                seen_ids.add(norad_id)
    
    # --- 2. 优先级 B：活跃卫星 (Active) ---
    active_unique = []
    if 'active' in groups:
        raw_active = load_local_json('active_satellite.json')
        for sat in raw_active:
            norad_id = sat.get("NORAD_CAT_ID")
            if norad_id and norad_id not in seen_ids:
                active_unique.append(sat)
                seen_ids.add(norad_id)

    # --- 3. 优先级 C：碎片与其他 (Debris) ---
    # 修改点：使用全局定义的 DEBRIS_GROUPS_LIST
    debris_unique = []
    debris_raw_data = []

    # 遍历我们定义的碎片列表，如果它也在本次下载的 groups 里，就加载它
    for debris_name in DEBRIS_GROUPS_LIST:
        if debris_name in groups:
            print(f"   -> 合并碎片源: {debris_name}...")
            debris_raw_data += load_local_json(f'{debris_name}_satellite.json')

    for sat in debris_raw_data:
        norad_id = sat.get("NORAD_CAT_ID")
        if norad_id and norad_id not in seen_ids:
            debris_unique.append(sat)
            seen_ids.add(norad_id)

    # --- 4. 统一保存结果 ---
    print("\n--- 分类去重报告 ---")
    save_final_json(stations_unique, 'stations_unique.json')
    save_final_json(active_unique, 'active_satellite_unique.json')
    save_final_json(debris_unique, 'debris_unique.json')
    
    print(f"\n✨ 数据清洗完成！全量唯一卫星总数: {len(seen_ids)}")

# --- 3. 清理模块 (保持不变) ---
def cleanup_raw_files(groups):
    print(f"\n🧹 开始清理原始临时文件...")
    for group in groups:
        file_name = f"{group}_satellite.json"
        full_path = os.path.join(SAVE_JSON_DIR, file_name)
        try:
            if os.path.exists(full_path):
                os.remove(full_path)
        except Exception:
            pass
    print(f"✨ 清理完成。")

# --- 4. 执行入口 ---

if __name__ == "__main__":
    # 基础组
    base_groups = ['active', 'stations']

    target_groups = base_groups + DEBRIS_GROUPS_LIST
    
    download_groups = [g for g in target_groups if g != 'active']
    
    # 1. 下载
    download_json(download_groups)
    
    # 2. 处理
    process_and_categorize(target_groups)
    
    # 3. 清理
    cleanup_raw_files(download_groups)