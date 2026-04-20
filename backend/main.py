import numpy as np
import datetime
from scipy.io import loadmat
from download_TLEs_data import download_tle
from setup_TLEfiles import *
from crash_analysis_prepare import *
from Propgation_analysis import *
from dataestr import *
from tools.date_trans import *
from tools.common_tools import *
#initialize
ConjStartDate = datetime.datetime(2025, 4, 7, 0, 0, 0)
ConjEndDate = datetime.datetime(2025, 4, 8, 0, 0, 0)
ConjStartJulian = date_to_julian(ConjStartDate)
ConjEndJulian = date_to_julian(ConjEndDate)


#获取卫星数据并生成卫星对象
# download_tle()
tempfile = 'temptle.tle'
ObjSat_list, objsma = generate_objSat_from_temptle(tempfile)
TgtSat_list = generate_tarSat_from_temptle(tempfile, ObjSat_list, objsma)


# 初始化用于卫星对象间联合碰撞分析变量
objNum, tgtNum = len(ObjSat_list), len(TgtSat_list)
PropTimeStep = 5 

# data preparation
timeVec=initialize_time_vector(ConjStartDate, ConjEndDate, PropTimeStep)
objSatDetail = ObjSatDetail(objNum)
objSatDetail.calculate_objSat_detail(ObjSat_list, objNum, ConjStartJulian)
tgtSatDetail = TgtSatDetail(tgtNum, objNum)
tgtSatDetail.calculate_tgtSat_detail(TgtSat_list, objNum, ConjStartJulian, objSatDetail.objpnow, objSatDetail.objvnow)

analysis_threshold = 3000  # 分析阈值（km）
conj_range_threshold = 1000  # 会合距离阈值（km）
min_dis_threshold = 10  # 最小距离阈值（km）
duration_days = 30  # 评估持续时间
time_step_minutes = 5  # 时间步长
report_file = "conjunction_report.csv"
print(f"start conjunction assessment,total {len(timeVec)} timestamps")
conjunction_assessment(objSatDetail, tgtSatDetail, timeVec, ConjStartDate, time_step_minutes, 
                        analysis_threshold, conj_range_threshold, min_dis_threshold, report_file)
print("Conjunction assessment completed.")



# 测试碰撞规避系统
from collision_avoidance import *
import datetime

# 设置机动参数
generator = CollisionAvoidanceTLEGenerator(ObjSat_list)
maneuver_plan = [
        {
            'obj_idx': 0,
            'maneuver_start': datetime.datetime(2025, 4, 7, 0, 0, 0),
            'duration_seconds': 0.0,
            'delta_v_kms': 0.1,
            'v_sign': 1
        },
        {
            'obj_idx': 1,
            'maneuver_start': datetime.datetime(2025, 4, 7, 0, 0, 0),
            'duration_seconds': 0.0,
            'delta_v_kms': 0.1,
            'v_sign': -1
        },
        {
            'obj_idx': 2,
            'maneuver_start': datetime.datetime(2025, 4, 7, 0, 0, 0),
            'duration_seconds': 0.0,
            'delta_v_kms': 0.1,
            'v_sign': 1
        }
    ]

# 生成机动后数据
maneuvered_ObjSat_list, maneuvered_objsma = generator.generate_maneuvered_data(maneuver_plan)
output_file = "maneuvered_satellites.tle"
generator.batch_generate(maneuver_plan, output_file)

print("机动参数设置完成")

# 规避后计算新概率
maneuvered_target_file = "maneuvered_targets.tle"
maneuvered_TgtSat_list = generate_tarSat_from_temptle(tempfile, maneuvered_target_file, maneuvered_ObjSat_list, maneuvered_objsma)
# 初始化用于卫星对象间联合碰撞分析变量
maneuvered_objNum, maneuvered_tgtNum = len(maneuvered_ObjSat_list), len(maneuvered_TgtSat_list)

#initialize
ConjStartDate = datetime.datetime(2025, 4, 7, 0, 0, 0)
ConjEndDate = datetime.datetime(2025, 4, 8, 0, 0, 0)
ConjStartJulian = date_to_julian(ConjStartDate)
ConjEndJulian = date_to_julian(ConjEndDate)

# data preparation
timeVec=initialize_time_vector(ConjStartDate, ConjEndDate, PropTimeStep)
maneuvered_objSatDetail = ObjSatDetail(maneuvered_objNum)
maneuvered_objSatDetail.calculate_objSat_detail(maneuvered_ObjSat_list, maneuvered_objNum, ConjStartJulian)
maneuvered_tgtSatDetail = TgtSatDetail(maneuvered_tgtNum, maneuvered_objNum)
maneuvered_tgtSatDetail.calculate_tgtSat_detail(maneuvered_TgtSat_list, maneuvered_objNum, ConjStartJulian, maneuvered_objSatDetail.objpnow, maneuvered_objSatDetail.objvnow)

analysis_threshold = 3000  # 分析阈值（km）
conj_range_threshold = 1000  # 会合距离阈值（km）
min_dis_threshold = 10  # 最小距离阈值（km）
duration_days = 30  # 评估持续时间
time_step_minutes = 5  # 时间步长
report_file = "maneuvered_conjunction_report.csv"
print(f"start maneuvered_conjunction assessment,total {len(timeVec)} timestamps")
conjunction_assessment(maneuvered_objSatDetail, maneuvered_tgtSatDetail, timeVec, ConjStartDate, time_step_minutes,
                        analysis_threshold, conj_range_threshold, min_dis_threshold, report_file)
print("Maneuvered_Conjunction assessment completed.")


