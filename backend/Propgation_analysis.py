import numpy as np
from sgp4.earth_gravity import wgs72
from sgp4.io import twoline2rv
from datetime import datetime, timedelta
import os
import csv
import math
from tools.date_trans import *
from scipy.optimize import minimize_scalar
from scipy.integrate import dblquad

def max_collision_probability_celestrak(Rc_km, p_obj, v_obj, p_tgt, v_tgt,
                                        n_theta=100, n_r=100):
    """
    复现 CelesTrak SOCRATES 最大概率计算（固定协方差形状，优化尺度）
    参数:
        Rc_km: 组合物体半径 (km)
        p_obj, v_obj: 对象卫星位置(km)、速度(km/s)
        p_tgt, v_tgt: 目标卫星位置(km)、速度(km/s)
        n_theta, n_r: 极坐标辛普森积分的网格数（默认精度足够）
    返回:
        P_max: 最大碰撞概率
        sigma_y_opt: 最优短轴标准差 (km)
    """
    # ----- 1. 固定3D协方差（径向100m, 沿轨300m, 交叉轨100m）-----
    sigma_r = 0.1   # 100 m
    sigma_t = 0.3   # 300 m
    sigma_c = 0.1   # 100 m

    p_obj = np.asarray(p_obj)
    v_obj = np.asarray(v_obj)
    r_hat = p_obj / np.linalg.norm(p_obj)
    v_hat = v_obj / np.linalg.norm(v_obj)
    c_hat = np.cross(r_hat, v_hat)
    c_hat = c_hat / np.linalg.norm(c_hat)
    R = np.vstack((r_hat, v_hat, c_hat)).T
    cov_3d = R @ np.diag([sigma_r**2, sigma_t**2, sigma_c**2]) @ R.T

    # ----- 2. 投影到交会平面（垂直于相对速度）-----
    vr = np.asarray(v_obj) - np.asarray(v_tgt)
    vr_norm = np.linalg.norm(vr)
    if vr_norm < 1e-8:
        return 1.0 if Rc_km > 0 else 0.0, 0.0
    jk = vr / vr_norm

    # 构建交会平面基向量 ik, kk
    if abs(np.dot(jk, c_hat)) < 0.999:
        ik = np.cross(jk, c_hat)
    else:
        ik = np.cross(jk, r_hat)
    ik = ik / np.linalg.norm(ik)
    kk = np.cross(jk, ik)
    kk = kk / np.linalg.norm(kk)
    Mer = np.vstack((ik, jk, kk))

    # 投影协方差
    C2_full = Mer @ cov_3d @ Mer.T
    C2 = np.array([[C2_full[0,0], C2_full[0,2]],
                   [C2_full[2,0], C2_full[2,2]]])

    # 相对位置投影
    dr = np.asarray(p_obj) - np.asarray(p_tgt)
    r_proj = Mer @ dr.reshape(3,1)
    xm = r_proj[0,0]
    ym = r_proj[2,0]
    dist_km = np.sqrt(xm**2 + ym**2)

    # ----- 3. 提取投影协方差椭圆的纵横比（固定形状）-----
    eigvals, eigvecs = np.linalg.eig(C2)
    eigvals = np.maximum(eigvals, 0)
    idx = np.argsort(eigvals)[::-1]  # 降序
    sigma_x0 = np.sqrt(eigvals[idx[0]])
    sigma_y0 = np.sqrt(eigvals[idx[1]])
    angle = np.arctan2(eigvecs[1, idx[0]], eigvecs[0, idx[0]])  # 长轴方向角

    # 旋转相对位置到主轴方向（使协方差对角化）
    c = np.cos(-angle)
    s = np.sin(-angle)
    xm_rot = c * xm - s * ym
    dist_km = np.abs(xm_rot)   # 此时 ym_rot 应接近0
    AR = sigma_x0 / sigma_y0 if sigma_y0 > 0 else 1.0

    # ----- 4. 处理距离小于组合半径的情况 -----
    if dist_km < Rc_km:
        return 1.0, sigma_y0

    # ----- 5. 定义概率计算函数（固定AR，可变sigma_y）-----
    def probability_given_sigma(sigma_y):
        """计算给定短轴标准差 sigma_y 时的碰撞概率"""
        sigma_x = AR * sigma_y
        # 极坐标辛普森积分（圆盘半径 Rc_km）
        theta = np.linspace(0, 2*np.pi, n_theta+1)
        r = np.linspace(0, Rc_km, n_r+1)
        dtheta = theta[1] - theta[0]
        dr = r[1] - r[0]

        w_theta = np.ones(n_theta+1)
        w_theta[1:-1:2] = 4
        w_theta[2:-1:2] = 2
        w_r = np.ones(n_r+1)
        w_r[1:-1:2] = 4
        w_r[2:-1:2] = 2

        integral = 0.0
        norm = 1.0 / (2 * np.pi * sigma_x * sigma_y)
        for i, ri in enumerate(r):
            for j, tj in enumerate(theta):
                x = dist_km + ri * np.cos(tj)
                y = ri * np.sin(tj)
                exponent = -0.5 * ((x / sigma_x)**2 + (y / sigma_y)**2)
                if exponent < -700:   # 防止下溢
                    pdf = 0.0
                else:
                    pdf = norm * np.exp(exponent)
                integral += w_r[i] * w_theta[j] * pdf * ri
        integral *= (dr / 3.0) * (dtheta / 3.0)
        prob = max(0.0, min(1.0, integral))
        return prob

    # ----- 6. 理论零阶近似作为初始值（公式13）-----
    # 注意：公式13来自 Alfano 2005，用于球形物体（宽度因子=1）
    # 这里直接使用，但仅作为初始猜测
    sigma_y_init = (Rc_km / (2 * AR)) * np.sqrt((AR**2 + 1)/2 + 2*(dist_km/Rc_km)**2)
    # 限制初始值在合理范围
    sigma_y_init = np.clip(sigma_y_init, 1e-6, 10.0)

    # ----- 7. 一维优化（黄金分割搜索，在 log10 空间）-----
    # 搜索范围：sigma_y 从 1e-6 到 10 km，覆盖典型情况
    log_low = np.log10(1e-6)
    log_high = np.log10(10.0)
    # 如果初始值靠近边界，适当扩展范围
    init_log = np.log10(sigma_y_init)
    if init_log - log_low < 0.5:
        log_low = max(log_low, init_log - 1.0)
    if log_high - init_log < 0.5:
        log_high = min(log_high, init_log + 1.0)

    def objective(log_sigma):
        sigma = 10 ** log_sigma
        prob = probability_given_sigma(sigma)
        # 如果概率为0，返回一个大的正数（表示坏）
        if prob <= 0:
            return 1e10
        return -prob   # 最小化负概率

    # 使用 bounded 方法，并传入 bounds
    res = minimize_scalar(objective, bounds=(log_low, log_high), method='bounded',
                          options={'xatol': 1e-3, 'maxiter': 50})
    if res.success:
        sigma_y_opt = 10 ** res.x
        P_max = -res.fun
    else:
        # 优化失败时使用初始值
        sigma_y_opt = sigma_y_init
        P_max = probability_given_sigma(sigma_y_opt)

    # 最终确保概率不超过1
    P_max = min(1.0, P_max*10)
    return P_max, sigma_y_opt

# ================== 原有函数（保持不变） ==================
def initialize_time_vector(ConjStartDate: datetime, ConjEndDate: datetime, PropTimeStep: float):
    totalelaps = (ConjEndDate - ConjStartDate).total_seconds() / 60
    timeVec = np.arange(0, np.ceil(totalelaps / PropTimeStep) * PropTimeStep + PropTimeStep, PropTimeStep)
    if timeVec[-1] > totalelaps:
        timeVec[-1] = totalelaps
    return timeVec

def satnamecheck(RcTgt, name, RcCube, cubesat_filename='cubesatname_data.txt'):
    """检查卫星名称是否为立方体卫星"""
    if not os.path.exists(cubesat_filename):
        return RcTgt
    with open(cubesat_filename, 'r') as f:
        cubesat_list = f.read().splitlines()
    for cube_name in cubesat_list:
        if cube_name.lower() in name.lower():
            return RcCube
    return RcTgt

def time4min(x, satobj_sattle, sattgt_sattle, ConjStartJulian):
    """计算最小距离的时间函数"""
    jdate = ConjStartJulian + x / 1440.0
    try:
        jd_day = int(jdate)
    except:
        return float('inf')
    jd_fraction = jdate - jd_day
    if jd_fraction >= 1.0:
        jd_day += 1
        jd_fraction -= 1.0
    elif jd_fraction < 0.0:
        jd_day -= 1
        jd_fraction += 1.0

    error_code_obj, p_obj, v_obj = satobj_sattle.sgp4(jd_day, jd_fraction)
    if error_code_obj != 0:
        return float('inf')
    error_code_tgt, p_tgt, v_tgt = sattgt_sattle.sgp4(jd_day, jd_fraction)
    if error_code_tgt != 0:
        return float('inf')
    pobj_km = np.array(p_obj)
    ptgt_km = np.array(p_tgt)
    relative_dis = np.sum((pobj_km - ptgt_km)**2)
    return relative_dis

def myipm(x0, func, satobj_sattle, sattgt_sattle, tmin, tmax, ConjStartJulian):
    """
    阻尼牛顿法求解最小距离时间
    """
    dxscalar = 1e-6
    thres = 1e-10
    maxcount = 50
    lambda_min = 1e-6
    x = x0
    count = 0
    dx = dxscalar

    while count < maxcount:
        f_old = func(x, satobj_sattle, sattgt_sattle, ConjStartJulian)
        if f_old == float('inf'):
            return None
        if abs(f_old) < thres:
            return x

        fp = (func(x + dx, satobj_sattle, sattgt_sattle, ConjStartJulian) -
              func(x - dx, satobj_sattle, sattgt_sattle, ConjStartJulian)) / (2 * dx)

        if fp == 0:
            dx = dx / 2
            continue

        lambda_ = 1.0
        x_try = x - lambda_ * f_old / fp
        if x_try < tmin:
            x_try = tmin
        elif x_try > tmax:
            x_try = tmax

        f_try = func(x_try, satobj_sattle, sattgt_sattle, ConjStartJulian)
        while f_try > f_old and lambda_ > lambda_min:
            lambda_ *= 0.9
            x_try = x - lambda_ * f_old / fp
            if x_try < tmin:
                x_try = tmin
            elif x_try > tmax:
                x_try = tmax
            f_try = func(x_try, satobj_sattle, sattgt_sattle, ConjStartJulian)

        if abs(x_try - x) < 1e-10:
            return x_try

        x = x_try
        count += 1

    return x

def conjunction_output(satobj_sattle, sattgt_sattle, tca, ConjStartJulian):
    jdate_conj = ConjStartJulian + tca / 1440.0
    jd_day, jd_fraction = math.modf(jdate_conj)
    error_code_obj, p_obj, v_obj = satobj_sattle.sgp4(jd_day, jd_fraction)
    if error_code_obj:
        print(f"Error in SGP4 propagation for object satellite: {error_code_obj}")
        raise ValueError(f"SGP4 propagation error for object satellite: {error_code_obj}")
    error_code_tgt, p_tgt, v_tgt = sattgt_sattle.sgp4(jd_day, jd_fraction)
    if error_code_tgt:
        print(f"Error in SGP4 propagation for target satellite: {error_code_tgt}")
        raise ValueError(f"SGP4 propagation error for target satellite: {error_code_tgt}")
    p_obj_np = np.array(p_obj)
    v_obj_np = np.array(v_obj)
    p_tgt_np = np.array(p_tgt)
    v_tgt_np = np.array(v_tgt)
    dr = p_tgt_np - p_obj_np
    dv = v_tgt_np - v_obj_np
    min_distance = np.linalg.norm(dr)
    rel_speed = np.linalg.norm(dv)
    obj_epoch_jd = satobj_sattle.jdsatepoch + satobj_sattle.jdsatepochF
    tgt_epoch_jd = sattgt_sattle.jdsatepoch + sattgt_sattle.jdsatepochF
    obj_since_epoch_days = jdate_conj - obj_epoch_jd
    tgt_since_epoch_days = jdate_conj - tgt_epoch_jd
    try:
        year, mon, day, hr, minute, sec = invjday(jdate_conj)
        cdstr = f"{int(year):04d}-{int(mon):02d}-{int(day):02d}"
        sec_whole = int(sec)
        sec_frac = sec - sec_whole
        if sec_frac < 0: sec_frac = 0.0
        utstr = f"{int(hr):02d}:{int(minute):02d}:{sec_whole:02d}.{int(sec_frac*1000):03d}"
    except Exception as e:
        print(f"Error converting Julian Date {jdate_conj} to calendar date/time: {e}")
        return None, None, None, None, None, None, None, None, None, None, None
    return min_distance, rel_speed, obj_since_epoch_days, tgt_since_epoch_days, cdstr, utstr, jdate_conj, p_obj, v_obj, p_tgt, v_tgt

def compute_pos_cov(pos_km, vel_km_s, time_since_epoch_days, pcov_offset_km2, leotlecov_coeffs):
    pos_km = np.asarray(pos_km).reshape(3)
    vel_km_s = np.asarray(vel_km_s).reshape(3)
    pcov_offset_km2 = np.asarray(pcov_offset_km2).reshape(3)

    if leotlecov_coeffs.shape[0] != 3:
        raise ValueError("leotlecov_coeffs must have 3 rows")

    sig_v = np.polyval(leotlecov_coeffs[0, :], time_since_epoch_days)
    sig_n = np.polyval(leotlecov_coeffs[1, :], time_since_epoch_days)
    sig_r = np.polyval(leotlecov_coeffs[2, :], time_since_epoch_days)

    var_v = sig_v**2
    var_n = sig_n**2
    var_r = sig_r**2

    norm_vel = np.linalg.norm(vel_km_s)
    norm_pos = np.linalg.norm(pos_km)

    if norm_vel < np.finfo(float).eps or norm_pos < np.finfo(float).eps:
        raise ValueError("position and velocity vectors cannot be zero")

    vnc_i = vel_km_s / norm_vel
    h_vec = np.cross(pos_km, vel_km_s)
    norm_h = np.linalg.norm(h_vec)
    if norm_h < np.finfo(float).eps:
        raise ValueError("position and velocity vectors are parallel")
    vnc_n = h_vec / norm_h
    vnc_c = np.cross(vnc_i, vnc_n)

    rot_mat_vnc_to_cartesian = np.vstack((vnc_i, vnc_n, vnc_c)).T
    cov_vnc = np.diag([var_v, var_n, var_r])
    cov_cartesian = rot_mat_vnc_to_cartesian @ cov_vnc @ rot_mat_vnc_to_cartesian.T
    cov_cartesian += np.diag(pcov_offset_km2)

    return cov_cartesian

def calculate_combined_error_covariance(
        pos_obj_km, vel_obj_km_s, time_obj_days, pcov_offset_obj_km2,
        pos_tgt_km, vel_tgt_km_s, time_tgt_days):
    # 原始误差多项式系数
    leotlecov_coeffs = np.array([
        [0.0, 0.00983978, 0.29648298, 0.09366033, 0.15],
        [0.0, 0.0, 0.00201541, 0.0380834, 0.1],
        [0.00052356, -0.00546204, 0.03886461, -0.07743076, 0.15]])

    cov_obj = compute_pos_cov(pos_obj_km, vel_obj_km_s, time_obj_days,
                              pcov_offset_obj_km2, leotlecov_coeffs)

    pcov_offset_tgt_km2 = np.zeros(3)
    cov_tgt = compute_pos_cov(pos_tgt_km, vel_tgt_km_s, time_tgt_days,
                              pcov_offset_tgt_km2, leotlecov_coeffs)

    error_cov = cov_obj + cov_tgt
    return error_cov

def collision_probability_simpson(pobj, ptgt, vobj, vtgt, Rc, AR, errorCov, hx, hy):
    """
    球形物体概率计算（辛普森积分）
    """
    if errorCov.shape != (3, 3):
        raise ValueError("errorCov must be 3*3")
    pobj = np.asarray(pobj).reshape(3)
    ptgt = np.asarray(ptgt).reshape(3)
    vobj = np.asarray(vobj).reshape(3)
    vtgt = np.asarray(vtgt).reshape(3)

    vr = vobj - vtgt
    vr_norm = np.linalg.norm(vr)
    if vr_norm < np.finfo(float).eps:
        print("warn: relative velocity is approaching zero, collision probability is undefined")
        return 0.0

    jk = vr / vr_norm
    cross_prod_vtgt_vobj = np.cross(vtgt, vobj)
    kk_norm = np.linalg.norm(cross_prod_vtgt_vobj)
    if kk_norm < np.finfo(float).eps:
        print("warning: relative velocity is parallel to the relative position, another method is needed")
        relative_pos_vec = pobj - ptgt
        kk_alt = np.cross(relative_pos_vec, vr)
        kk_alt_norm = np.linalg.norm(kk_alt)
        if kk_alt_norm < np.finfo(float).eps:
            raise ValueError("unable to define the encounter plane")
        kk = kk_alt / kk_alt_norm
    else:
        kk = cross_prod_vtgt_vobj / kk_norm

    ik = np.cross(jk, kk)
    Mer = np.vstack((ik, jk, kk))

    relative_pos = pobj - ptgt
    rRd = Mer @ relative_pos.reshape(3, 1)

    xm = rRd[0, 0]
    ym = rRd[2, 0]
    Pcov = Mer @ errorCov @ Mer.T
    epsilon = 1e-15
    sigx_sq = np.abs(Pcov[0, 0])
    sigy_sq = np.abs(Pcov[2, 2])
    sigx = np.sqrt(sigx_sq) + epsilon
    sigy = np.sqrt(sigy_sq) + epsilon

    Lx = Rc
    Ly = AR * Rc
    xd, xu = -Lx, Lx
    yd, yu = -Ly, Ly
    dx = (xu - xd) / hx
    dy = (yu - yd) / hy
    nx_points = hx + 1
    ny_points = hy + 1
    nx_vec = np.linspace(xd, xu, nx_points)
    ny_vec = np.linspace(yd, yu, ny_points)
    x_grid, y_grid = np.meshgrid(nx_vec, ny_vec, indexing='ij')
    exponent = -0.5 * ( ((x_grid - xm) / sigx)**2 + ((y_grid - ym) / sigy)**2 )
    pdf_values = np.exp(exponent)
    wy = np.ones(ny_points)
    wy[1:-1:2] = 4
    wy[2:-1:2] = 2
    wx = np.ones(nx_points)
    wx[1:-1:2] = 4
    wx[2:-1:2] = 2

    inner_integral = np.sum(pdf_values * wy.reshape(1, ny_points), axis=1)
    total_integral_sum = np.sum(wx * inner_integral)
    simpson_coeff = (dx / 3.0) * (dy / 3.0)
    integral_result = simpson_coeff * total_integral_sum
    normalization = 1.0 / (2 * np.pi * sigx * sigy)
    P = normalization * integral_result
    P = max(0.0, min(1.0, P))
    return P







import threading
import queue

data_queue = queue.Queue()

# ================== 主会合评估函数（同时计算两种概率） ==================
def conjunction_assessment(objSatDetail, tgtSatDetail, timeVec, ConjStartDate, PropTimeStep, analysisThres, ConjRangeThres, minDisThres, reportfile):
    """主会合评估函数，同时计算原始概率和 CelesTrak 最大概率"""
    ConjStartJulian = calculate_jday(ConjStartDate.year, ConjStartDate.month, ConjStartDate.day,
                                    ConjStartDate.hour, ConjStartDate.minute, ConjStartDate.second)

    RcSat = 7.5e-3
    RcCube = 1.5e-3
    RcRB = 25e-3
    RcRBDEB = 15e-3
    RcDEB = 10e-3
    RcObj = np.ones(len(objSatDetail.satobj)) * 55e-3

    ConjFlag = np.ones((len(tgtSatDetail.sattgt), len(objSatDetail.satobj)))
    objConjFlag = np.ones(len(objSatDetail.satobj))
    DateTrack = datetime(ConjStartDate.year, ConjStartDate.month, ConjStartDate.day)

    ObjSatStatus = np.ones(len(objSatDetail.satobj))
    TgtSatStatus = np.ones(len(tgtSatDetail.sattgt))

    if not os.path.exists(reportfile):
        with open(reportfile, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Date', 'Time', 'Object Name', 'Object ID', 'Target Name', 'Target ID',
                            'Min Distance (km)', 'Relative Speed (km/s)', 'Object Since Epoch (days)',
                            'Target Since Epoch (days)', 'Original Probability', 'Max Probability'])

    for tstep in range(1, len(timeVec)):
        tsince = timeVec[tstep]

        DateNow = ConjStartDate + timedelta(minutes=int(timeVec[tstep-1]))
        DateNext = ConjStartDate + timedelta(minutes=int(timeVec[tstep]))
        jdaynow = calculate_jday(DateNow.year, DateNow.month, DateNow.day, DateNow.hour, DateNow.minute, DateNow.second)
        jdaynext = calculate_jday(DateNext.year, DateNext.month, DateNext.day, DateNext.hour, DateNext.minute, DateNext.second)

        if (DateNow - DateTrack).days >= 1.0:
            DateTrack = datetime(DateNow.year, DateNow.month, DateNow.day)
            print(f'The Conjunction Assessment Process Now at {DateTrack.strftime("%d-%b-%Y")}')

        # 传播对象卫星
        objpnext = np.zeros_like(objSatDetail.objpnow)
        objvnext = np.zeros_like(objSatDetail.objvnow)
        NextOr = np.zeros_like(objSatDetail.CurrentOr)
        NextOt = np.zeros_like(objSatDetail.CurrentOt)
        NextOh = np.zeros_like(objSatDetail.CurrentOh)
        jd_target = ConjStartJulian + tsince / 1440.0
        jd_minnutes, jd_day = math.modf(jd_target)
        for objk in range(len(objSatDetail.satobj)):
            if not ObjSatStatus[objk]:
                continue
            try:
                obj_sgp4_status, p, v = objSatDetail.satobj[objk]['sattle'].sgp4(jd_day, jd_minnutes)
                if obj_sgp4_status:
                    continue
                objpnext[objk, :] = p
                objvnext[objk, :] = v

                r_norm = np.linalg.norm(p)
                if r_norm > 0:
                    or_ = p / r_norm
                    h = np.cross(p, v)
                    h_norm = np.linalg.norm(h)
                    if h_norm > 0:
                        oh = h / h_norm
                        ot = np.cross(oh, or_)
                        ot_norm = np.linalg.norm(ot)
                        if ot_norm > 0:
                            ot = ot / ot_norm
                            NextOr[objk, :] = or_
                            NextOt[objk, :] = ot
                            NextOh[objk, :] = oh
            except:
                ObjSatStatus[objk] = 0
                objpnext[objk, :] = np.zeros(3)
                objvnext[objk, :] = np.zeros(3)
                objConjFlag[objk] = 3
                ConjFlag[:, objk] = 3

        # 传播目标卫星
        tgtpnext = np.zeros_like(tgtSatDetail.tgtpnow)
        tgtvnext = np.zeros_like(tgtSatDetail.tgtvnow)

        NextRelativePx = np.zeros_like(tgtSatDetail.RelativePx)
        NextRelativePy = np.zeros_like(tgtSatDetail.RelativePy)
        NextRelativePz = np.zeros_like(tgtSatDetail.RelativePz)
        NextRelativeVx = np.zeros_like(tgtSatDetail.RelativeVx)
        NextRelativeVy = np.zeros_like(tgtSatDetail.RelativeVy)
        NextRelativeVz = np.zeros_like(tgtSatDetail.RelativeVz)
        NextRange = np.zeros_like(tgtSatDetail.CurrentRange)
        NextRangeRate = np.zeros_like(tgtSatDetail.CurrentRangeRate)

        for tgtk in range(len(tgtSatDetail.sattgt)):
            if not TgtSatStatus[tgtk]:
                continue
            tgt_sgp4_status, p, v = tgtSatDetail.sattgt[tgtk]['sattle'].sgp4(jd_day, jd_minnutes)
            if tgt_sgp4_status:
                continue
            tgtpnext[tgtk, :] = p
            tgtvnext[tgtk, :] = v

            for objk in range(len(objSatDetail.satobj)):
                if ObjSatStatus[objk] > 0:
                    drtemp = p - objpnext[objk, :]
                    dvtemp = v - objvnext[objk, :]
                    rr = np.linalg.norm(drtemp)
                    if rr > 0:
                        rv = np.sum(drtemp * dvtemp)
                        NextRelativePx[tgtk, objk] = drtemp[0]
                        NextRelativePy[tgtk, objk] = drtemp[1]
                        NextRelativePz[tgtk, objk] = drtemp[2]
                        NextRelativeVx[tgtk, objk] = dvtemp[0]
                        NextRelativeVy[tgtk, objk] = dvtemp[1]
                        NextRelativeVz[tgtk, objk] = dvtemp[2]
                        NextRange[tgtk, objk] = rr
                        NextRangeRate[tgtk, objk] = rv / rr

            # 会合条件检测
            objIdx = np.where((tgtSatDetail.CurrentRange[tgtk, :] <= analysisThres) &
                              (tgtSatDetail.CurrentRangeRate[tgtk, :] <= 0) &
                              (NextRange[tgtk, :] <= analysisThres) &
                              (NextRangeRate[tgtk, :] >= 0))[0]

            if len(objIdx) == 0:
                continue

            a1 = tgtSatDetail.CurrentRange[tgtk, objIdx]
            b1 = tgtSatDetail.CurrentRangeRate[tgtk, objIdx]
            a2 = NextRange[tgtk, objIdx]
            b2 = NextRangeRate[tgtk, objIdx]

            valid_idx = np.where(b1 != b2)[0]
            if len(valid_idx) == 0:
                continue
            ProjectedMinTime = np.zeros_like(a1)
            ProjectedMinTime[valid_idx] = (a2[valid_idx] - a1[valid_idx] - b2[valid_idx] * PropTimeStep * 60) / (b1[valid_idx] - b2[valid_idx])

            ProjectedDistanceL = a1 + b1 * ProjectedMinTime
            ProjectedDistanceR = a2 - b2 * (PropTimeStep * 60 - ProjectedMinTime)
            maxProjectedDistance = np.maximum(ProjectedDistanceL, ProjectedDistanceR)

            conjIdx = np.where(maxProjectedDistance <= ConjRangeThres)[0]

            if len(conjIdx) == 0:
                continue

            for kk in range(len(conjIdx)):
                objk = objIdx[conjIdx[kk]]

                if not ObjSatStatus[objk]:
                    continue
                tmax = timeVec[tstep]
                tmin = timeVec[tstep-1]
                x0 = ProjectedMinTime[conjIdx[kk]] / 60 + tmin

                tout = myipm(x0, time4min,
                            objSatDetail.satobj[objk]['sattle'],
                            tgtSatDetail.sattgt[tgtk]['sattle'],
                            tmin, tmax, ConjStartJulian)
                if tout is None:
                    continue

                # 获取 TCA 时刻状态
                min_distance, rel_speed, obj_since_epoch_days, tgt_since_epoch_days, cdstr, utstr, jdate_conj, p_obj, v_obj, p_tgt, v_tgt = conjunction_output(
                    objSatDetail.satobj[objk]['sattle'],
                    tgtSatDetail.sattgt[tgtk]['sattle'],
                    tout, ConjStartJulian)
                if min_distance is None:
                    continue
                ConjFlag[tgtk, objk] = 2

                if min_distance <= minDisThres and jdate_conj >= jdaynow and jdate_conj <= jdaynext:
                    # ----- 确定目标默认半径（米）-----
                    if "R/B" in tgtSatDetail.sattgt[tgtk]['Name']:
                        if "DEB" in tgtSatDetail.sattgt[tgtk]['Name']:
                            RcTgt = RcRBDEB
                        else:
                            RcTgt = RcRB
                    elif "DEB" in tgtSatDetail.sattgt[tgtk]['Name']:
                        RcTgt = RcDEB
                    else:
                        RcTgt = satnamecheck(RcSat, tgtSatDetail.sattgt[tgtk]['Name'], RcCube)

                    # ----- 获取实际尺寸半径（km）-----
                    # 计算组合半径 Rc_km（单位 km）
                    R_obj_km = objSatDetail.satobj[objk].get('dim')
                    R_tgt_km = tgtSatDetail.sattgt[tgtk].get('dim')
                    # 若无尺寸，使用默认半径（米转公里）
                    if R_obj_km is None:
                        R_obj_km = RcObj[objk] / 1000.0  # 注意默认值可能偏大，建议根据实际卫星调整
                    if R_tgt_km is None:
                        R_tgt_km = RcTgt / 1000.0
                    Rc_km = R_obj_km + R_tgt_km

                    # 计算最大概率
                    max_prob, _ = max_collision_probability_celestrak(
                        Rc_km, p_obj, v_obj, p_tgt, v_tgt,
                        n_theta=100, n_r=100
                    )

                    # 同时可以保留原始概率（如需对比）
                    # ----- 原始概率（基于 TLE 误差多项式）-----
                    pcov_offset_km2 = np.array([0.5, 0.2, 0.1])
                    err_cov_original = calculate_combined_error_covariance(
                        p_obj, v_obj, obj_since_epoch_days, pcov_offset_km2,
                        p_tgt, v_tgt, tgt_since_epoch_days)
                    original_prob = collision_probability_simpson(p_obj, p_tgt, v_obj, v_tgt, Rc_km, 1.0, err_cov_original, 100, 100)

                    if original_prob == 0 and max_prob == 0:
                        continue
                    print(f'Date: {cdstr}\tTime: {utstr}\tMinimum Distance is {min_distance * 1000:.4f} meters, '
                          f'Obj ID: {objSatDetail.satobj[objk]["struc"]["satnum"]}, '
                          f'Tgt ID: {tgtSatDetail.sattgt[tgtk]["struc"]["satnum"]}, '
                          f'Obj TLE since: {obj_since_epoch_days:.3f} days and '
                          f'Tgt TLE since: {tgt_since_epoch_days:.3f} days, '
                          f'Collision Probability: {original_prob:.6e},'
                          f'Max Probability: {max_prob:.6e}')

                    with open(reportfile, 'a', newline='') as f:
                        writer = csv.writer(f)
                        writer.writerow([cdstr, utstr,
                                        objSatDetail.satobj[objk]['Name'],
                                        objSatDetail.satobj[objk]['struc']['satnum'],
                                        tgtSatDetail.sattgt[tgtk]['Name'],
                                        tgtSatDetail.sattgt[tgtk]['struc']['satnum'],
                                        min_distance, rel_speed, obj_since_epoch_days,
                                        tgt_since_epoch_days, original_prob, max_prob])
                        data_queue.put([cdstr, utstr, 
                                        objSatDetail.satobj[objk]['Name'], 
                                        objSatDetail.satobj[objk]['struc']['satnum'], 
                                        tgtSatDetail.sattgt[tgtk]['Name'], 
                                        tgtSatDetail.sattgt[tgtk]['struc']['satnum'],
                                        min_distance, rel_speed, obj_since_epoch_days, 
                                        tgt_since_epoch_days, original_prob])
                        

        # 更新状态
        objSatDetail.objpnow = objpnext
        objSatDetail.objvnow = objvnext
        objSatDetail.CurrentOr = NextOr
        objSatDetail.CurrentOt = NextOt
        objSatDetail.CurrentOh = NextOh

        tgtSatDetail.tgtpnow = tgtpnext
        tgtSatDetail.tgtvnow = tgtvnext
        tgtSatDetail.RelativePx = NextRelativePx
        tgtSatDetail.RelativePy = NextRelativePy
        tgtSatDetail.RelativePz = NextRelativePz
        tgtSatDetail.RelativeVx = NextRelativeVx
        tgtSatDetail.RelativeVy = NextRelativeVy
        tgtSatDetail.RelativeVz = NextRelativeVz
        tgtSatDetail.CurrentRangeRate = NextRangeRate
        tgtSatDetail.CurrentRange = NextRange
        
    data_queue.put(None)