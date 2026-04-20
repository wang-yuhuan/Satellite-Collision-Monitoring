import pandas as pd
import requests
from datetime import datetime
import logging


def get_satellite_collision_events(catnr, max_events=100):
    url = f"https://celestrak.org/SOCRATES/table-socrates.php?CATNR={catnr}&ORDER=TCA&MAX={max_events}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    }
    try:
        logging.info(f"正在从 CelesTrak 获取卫星 {catnr} 的所有可能碰撞事件...")
        response = requests.get(url, headers=headers)
        response.raise_for_status() 
        
        tables = pd.read_html(response.text)
        if not tables: return None
            
        target_table = max(tables, key=len)
        if isinstance(target_table.columns, pd.MultiIndex):
            target_table.columns = ['_'.join(col).strip() for col in target_table.columns.values]
            
        tca_col = [col for col in target_table.columns if 'TCA' in col.upper()]
        if tca_col:
            target_table[tca_col[0]] = pd.to_datetime(target_table[tca_col[0]], errors='coerce')
        return target_table
    except Exception as e:
        logging.error(f"获取数据时出错: {e}")
        return None

def filter_events_by_date_range(df, start_date, end_date):
    """
    对获取到的碰撞事件数据进行过滤，返回在 [start_date, end_date] 区间内的所有事件。
    """
    if df is None or df.empty:
        return df

    # 确认 TCA 列的名称
    tca_col = [col for col in df.columns if 'TCA' in df.columns or 'TCA' in col.upper()]
    if not tca_col:
        logging.warning("未找到包含 TCA（最近接近时间）的列，跳过时间过滤。")
        return df
        
    tca_column_name = tca_col[0]
    
    # 核心修改：使用布尔索引，同时满足 >= start_date 且 <= end_date
    filtered_df = df[
        df[tca_column_name].notna() & 
        (df[tca_column_name] >= start_date) & 
        (df[tca_column_name] <= end_date)
    ].copy()
    
    return filtered_df

def clean_socrates_dataframe(raw_df):
    if raw_df is None or raw_df.empty:
        return pd.DataFrame()
        
    cleaned_events = []
    cols = raw_df.columns
    try:
        tca_col = [c for c in cols if 'TCA' in c.upper()][0]
        norad_col = [c for c in cols if 'NORAD' in c.upper()][0]
        name_col = [c for c in cols if 'NAME' in c.upper()][0]
        range_prob_col = [c for c in cols if 'MIN RANGE' in c.upper() or 'PROBABILITY' in c.upper()][0]
        speed_dilution_col = [c for c in cols if 'RELATIVE SPEED' in c.upper() or 'DILUTION' in c.upper()][0]

        for i in range(0, len(raw_df) - 1, 2):
            row1 = raw_df.iloc[i]
            row2 = raw_df.iloc[i+1]
            
            event = {
                'TCA_UTC': row1[tca_col],
                'Target_NORAD': row1[norad_col],
                'Target_Name': row1[name_col],
                'Threat_NORAD': row2[norad_col],
                'Threat_Name': row2[name_col],
                'Min_Range_km': row1[range_prob_col],
                'Relative_Speed_km_s': row1[speed_dilution_col],
                'Max_Probability': row2[range_prob_col],
                'Dilution_Threshold_km': row2[speed_dilution_col]
            }
            cleaned_events.append(event)
    except IndexError as e:
        logging.error(f"数据清洗时找不到对应的列名: {e}")
        
    return pd.DataFrame(cleaned_events)

    
    