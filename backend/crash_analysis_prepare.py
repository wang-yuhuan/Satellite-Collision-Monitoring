import numpy as np
import pandas as pd
import os
from sgp4.api import Satrec
from tools.date_trans import calculate_jday
from datetime import datetime
from tools.sgp4 import *

# ========== 全局卫星尺寸缓存 ==========
_SAT_DF = None

def load_satellite_cache(csv_file="satellite_dimensions.csv"):
    """加载本地 CSV 文件到全局缓存"""
    global _SAT_DF
    if _SAT_DF is not None:
        return _SAT_DF
    if not os.path.exists(csv_file):
        # 文件不存在时静默返回 None，不打印警告
        return None
    try:
        df = pd.read_csv(csv_file)
        # 确保 satno 列为整数类型
        df['satno'] = pd.to_numeric(df['satno'], errors='coerce')
        _SAT_DF = df
        return df
    except Exception:
        # 出错时不打印任何警告
        return None

def fetch_satellite_dimensions(norad_id, csv_file):
    """
    从本地 CSV 缓存中查询卫星尺寸，返回等效球半径（单位：km）。
    半径 = 所有可用尺寸（height, width, depth, diameter）中的最大值的一半。
    若无任何尺寸数据，返回 None。
    """
    try:
        satno_int = int(str(norad_id).strip())
    except ValueError:
        return None

    df = load_satellite_cache(csv_file)
    if df is None:
        return None

    match = df[df['satno'] == satno_int]
    if match.empty:
        return None

    row = match.iloc[0]
    height = row.get('height')
    width = row.get('width')
    depth = row.get('depth')
    diameter = row.get('diameter')

    def to_km(val):
        return float(val) / 1000.0 if not pd.isna(val) else None

    h_km = to_km(height)
    w_km = to_km(width)
    d_km = to_km(depth)
    dia_km = to_km(diameter)

    dims_vals = [v for v in (h_km, w_km, d_km, dia_km) if v is not None]
    if dims_vals:
        max_dim_km = max(dims_vals)
        return max_dim_km / 2.0
    else:
        return None

# ========== 原有类定义 ==========
class ObjSatDetail:
    def __init__(self, objNum):
        self.satobj = [dict() for _ in range(objNum)]
        self.objpnow = np.zeros((objNum, 3))
        self.objvnow = np.zeros((objNum, 3))
        self.CurrentOr = np.zeros((objNum, 3))
        self.CurrentOt = np.zeros((objNum, 3))
        self.CurrentOh = np.zeros((objNum, 3))

    def calculate_objSat_detail(self, ObjSat, objNum, ConjStartJulian, csv_file):
        for ii in range(objNum):
            # 解析 TLE 数据
            self.satobj[ii]['struc'] = {'satnum': ObjSat[ii]['CatID']}
            self.satobj[ii]['Name'] = ObjSat[ii]['Name']
            self.satobj[ii]['sattle'] = Satrec.twoline2rv(ObjSat[ii]['Line2'], ObjSat[ii]['Line3'])

            # 计算初始时间和偏移
            self.satobj[ii]['initialepoch'] = self.satobj[ii]['sattle'].jdsatepoch - calculate_jday(1950, 1, 0, 0, 0, 0)
            self.satobj[ii]['initialjulian'] = self.satobj[ii]['sattle'].jdsatepoch
            self.satobj[ii]['offset'] = (ConjStartJulian - self.satobj[ii]['initialjulian']) * 1440

            # 获取卫星尺寸信息
            norad_id = ObjSat[ii]['CatID']
            radius_km = fetch_satellite_dimensions(norad_id, csv_file)
            self.satobj[ii]['dim'] = radius_km  # 存储半径（km）或 None

            # 计算卫星的位置和速度
            _, p, v = self.satobj[ii]['sattle'].sgp4(self.satobj[ii]['initialjulian'], self.satobj[ii]['offset'] / 1440.0)
            self.objpnow[ii, :] = p
            self.objvnow[ii, :] = v

            # 计算径向、沿轨、交叉轨向量
            or_ = p / np.linalg.norm(p)
            h = np.cross(p, v)
            oh = h / np.linalg.norm(h)
            ot = np.cross(oh, or_)
            ot = ot / np.linalg.norm(ot)
            self.CurrentOr[ii, :] = or_
            self.CurrentOt[ii, :] = ot
            self.CurrentOh[ii, :] = oh


class TgtSatDetail:
    def __init__(self, tgtNum, objNum):
        self.sattgt = [dict() for _ in range(tgtNum)]
        self.tgtpnow = np.zeros((tgtNum, 3))
        self.tgtvnow = np.zeros((tgtNum, 3))
        self.RelativePx = np.zeros((tgtNum, objNum))
        self.RelativePy = np.zeros((tgtNum, objNum))
        self.RelativePz = np.zeros((tgtNum, objNum))
        self.RelativeVx = np.zeros((tgtNum, objNum))
        self.RelativeVy = np.zeros((tgtNum, objNum))
        self.RelativeVz = np.zeros((tgtNum, objNum))
        self.CurrentRangeRate = np.zeros((tgtNum, objNum))
        self.CurrentRange = np.zeros((tgtNum, objNum))

    def calculate_tgtSat_detail(self, TgtSat, objNum, ConjStartJulian, objpnow, objvnow, csv_file):
        for ii in range(len(TgtSat)):
            # 解析 TLE 数据
            self.sattgt[ii]['struc'] = {'satnum': TgtSat[ii]['CatID']}
            self.sattgt[ii]['Name'] = TgtSat[ii]['Name']
            self.sattgt[ii]['sattle'] = Satrec.twoline2rv(TgtSat[ii]['Line2'], TgtSat[ii]['Line3'])

            # 计算初始时间和偏移
            self.sattgt[ii]['initialepoch'] = self.sattgt[ii]['sattle'].jdsatepoch - calculate_jday(1950, 1, 0, 0, 0, 0)
            self.sattgt[ii]['initialjulian'] = self.sattgt[ii]['sattle'].jdsatepoch
            self.sattgt[ii]['offset'] = (ConjStartJulian - self.sattgt[ii]['initialjulian']) * 1440

            # 获取卫星尺寸信息
            norad_id = TgtSat[ii]['CatID']
            radius_km = fetch_satellite_dimensions(norad_id, csv_file)
            self.sattgt[ii]['dim'] = radius_km  # 存储半径（km）或 None

            # 计算目标卫星的位置和速度
            _, p, v = self.sattgt[ii]['sattle'].sgp4(self.sattgt[ii]['initialjulian'], self.sattgt[ii]['offset'] / 1440.0)
            self.tgtpnow[ii, :] = p
            self.tgtvnow[ii, :] = v

            # 计算目标卫星与对象卫星的相对位置和速度
            for kk in range(objNum):
                drtemp = self.tgtpnow[ii, :] - objpnow[kk, :]
                dvtemp = self.tgtvnow[ii, :] - objvnow[kk, :]
                rv = np.sum(drtemp * dvtemp)
                rr = np.linalg.norm(drtemp)
                self.RelativePx[ii, kk] = drtemp[0]
                self.RelativePy[ii, kk] = drtemp[1]
                self.RelativePz[ii, kk] = drtemp[2]
                self.RelativeVx[ii, kk] = dvtemp[0]
                self.RelativeVy[ii, kk] = dvtemp[1]
                self.RelativeVz[ii, kk] = dvtemp[2]
                if rr > 0:
                    self.CurrentRangeRate[ii, kk] = rv / rr
                else:
                    self.CurrentRangeRate[ii, kk] = 0.0
                self.CurrentRange[ii, kk] = rr


if __name__ == "__main__":
    from setup_TLEfiles import generate_objSat_from_temptle, generate_tarSat_from_temptle
    from tools.date_trans import date_to_julian
    import datetime

    # input
    ObjCatID = np.array([['00005'], ['25544'], ['49256'], ['52488'], ['41382'], ['20410']])  # object Sat,can be changed ", ['04737'], ['43910']"
    objfile = 'objtle.tle'

    ConjStartDate = datetime.datetime(2026, 3, 22, 18, 0, 0)
    ConjStartJulian = date_to_julian(ConjStartDate)
    tempfile = 'temptle.tle'
    target_file = "targets.tle"
    ObjSat_list, objsma= generate_objSat_from_temptle(tempfile, objfile, ObjCatID)
    TgtSat_list = generate_tarSat_from_temptle(tempfile, target_file, ObjSat_list, objsma)
    objNum, tgtNum = len(ObjSat_list), len(TgtSat_list)
    objSatDetail = ObjSatDetail(objNum)
    objSatDetail.calculate_objSat_detail(ObjSat_list, objNum, ConjStartJulian)
    tgtSatDetail = TgtSatDetail(tgtNum, objNum)
    tgtSatDetail.calculate_tgtSat_detail(TgtSat_list, objNum, ConjStartJulian, objSatDetail.objpnow, objSatDetail.objvnow)
    print("=================Object Sat and Target Sat parameters' initialization completed!=========================")
