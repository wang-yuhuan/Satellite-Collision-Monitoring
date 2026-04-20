import numpy as np
import math
from datetime import datetime, timedelta
from scipy.integrate import solve_ivp

# 导入必要的模块
from tools.date_trans import date_to_julian, invjday

# 导入sgp4库（2.25版）
from sgp4.api import Satrec

# 物理常数
MU_EARTH = 398600.4  # 地球标准重力参数 (km^3/s^2)
J2 = 1.08262668e-3
R_EARTH_KM = 6378.135  # km  % 6378.137


class OrbitalDynamics:
    """轨道动力学计算类"""

    @staticmethod
    def rv2coe(r, v):
        """与MATLAB eci2orb1函数一致的轨道要素计算"""
        mu = MU_EARTH  # 地球重力参数

        # 位置和速度模
        rmag = np.linalg.norm(r)
        vmag = np.linalg.norm(v)

        # 单位矢量
        rhat = r / rmag if rmag > 0 else np.zeros(3)
        vhat = v / vmag if vmag > 0 else np.zeros(3)

        # 角动量矢量
        hv = np.cross(r, v)
        hnorm = np.linalg.norm(hv)
        if hnorm > 0:
            hhat = hv / hnorm
        else:
            hhat = np.zeros(3)

        # 偏心率矢量
        vtmp = v / mu
        ecc = np.cross(vtmp, hv)
        ecc = ecc - rhat

        # 半长轴
        sma = 1.0 / (2.0 / rmag - vmag * vmag / mu)

        # 等分点要素
        p = hhat[0] / (1 + hhat[2])
        q = -hhat[1] / (1 + hhat[2])
        const1 = 1.0 / (1.0 + p * p + q * q)

        fhat = np.zeros(3)
        fhat[0] = const1 * (1.0 - p * p + q * q)
        fhat[1] = const1 * 2.0 * p * q
        fhat[2] = -const1 * 2.0 * p

        ghat = np.zeros(3)
        ghat[0] = const1 * 2.0 * p * q
        ghat[1] = const1 * (1.0 + p * p - q * q)
        ghat[2] = const1 * 2.0 * q

        # 计算等分点要素中的参数
        h_val = np.dot(ecc, ghat)
        xk = np.dot(ecc, fhat)
        x1 = np.dot(r, fhat)
        y1 = np.dot(r, ghat)

        # 轨道偏心率
        eccm = math.sqrt(h_val * h_val + xk * xk)

        # 轨道倾角（使用p和q）
        inc = 2.0 * math.atan(math.sqrt(p * p + q * q))

        # 真经度
        xlambdat = math.atan2(y1, x1)
        if xlambdat < 0:
            xlambdat += 2.0 * math.pi

        # 升交点赤经
        if inc > 0.00000001:
            raan = math.atan2(p, q)
            if raan < 0:
                raan += 2.0 * math.pi
        else:
            raan = 0.0

        # 近地点幅角
        if eccm > 0.00000001:
            argper = math.atan2(h_val, xk) - raan
            argper = argper % (2.0 * math.pi)
        else:
            argper = 0.0

        # 真近点角
        tanom = xlambdat - raan - argper
        tanom = tanom % (2.0 * math.pi)

        # 计算平近点角（用于TLE）
        if eccm < 1.0:
            # 真近点角 -> 偏近点角 -> 平近点角
            cos_tanom = math.cos(tanom)
            sin_tanom = math.sin(tanom)

            cos_E = (eccm + cos_tanom) / (1.0 + eccm * cos_tanom)
            sin_E = math.sqrt(1.0 - eccm ** 2) * sin_tanom / (1.0 + eccm * cos_tanom)
            E = math.atan2(sin_E, cos_E)

            ma = E - eccm * math.sin(E)
            ma = ma % (2.0 * math.pi)
        else:
            ma = 0.0

        # 平均运动
        n_motion = 0.0
        if sma > 0:
            n_motion = math.sqrt(mu / sma ** 3)

        return {
            'a': sma,
            'e': eccm,
            'i': inc,
            'raan': raan,
            'argp': argper,
            'ma': ma,
            'n': n_motion
        }

    @staticmethod
    def orbit_dynamics_equations(t, state):
        """轨道动力学方程（包含中心引力和J2摄动）"""
        position = state[0:3]
        velocity = state[3:6]
        acceleration = np.zeros(3)

        r_norm = np.linalg.norm(position)
        if r_norm > 0:
            # 中心引力项
            central_gravity = -MU_EARTH * position / (r_norm ** 3)
            acceleration += central_gravity

            # J2摄动项
            x, y, z = position
            r2 = r_norm * r_norm
            r5 = r2 * r2 * r_norm
            d1 = -1.5 * J2 * R_EARTH_KM * R_EARTH_KM * MU_EARTH / r5
            d2 = 1 - 5 * z * z / r2

            j2_accel = np.zeros(3)
            j2_accel[0] = x * d1 * d2
            j2_accel[1] = y * d1 * d2
            j2_accel[2] = z * d1 * (d2 + 2)
            acceleration += j2_accel

        state_derivative = np.zeros(6)
        state_derivative[0:3] = velocity
        state_derivative[3:6] = acceleration
        return state_derivative


class SGP4Propagator:
    """SGP4传播器类"""

    @staticmethod
    def create_sgp4_satellite(tle_line1, tle_line2):
        """从TLE创建SGP4卫星对象"""
        return Satrec.twoline2rv(tle_line1, tle_line2)

    @staticmethod
    def propagate_sgp4(satrec, target_jd):
        """使用SGP4传播到指定儒略日"""
        if satrec is None:
            raise ValueError("SGP4卫星对象为空")

        jd_day = int(target_jd)
        jd_fraction = target_jd - jd_day

        if jd_fraction >= 1.0:
            jd_day += 1
            jd_fraction -= 1.0
        elif jd_fraction < 0.0:
            jd_day -= 1
            jd_fraction += 1.0

        error_code, position, velocity = satrec.sgp4(jd_day, jd_fraction)

        if error_code != 0:
            error_messages = {
                1: "平均运动接近零",
                2: "平均运动超出范围",
                3: "半长轴过小",
                4: "轨道倾角接近零",
                5: "节点数超出范围"
            }
            error_msg = error_messages.get(error_code, f"未知错误代码 {error_code}")
            raise ValueError(f"SGP4传播错误: {error_msg} (代码: {error_code})")

        return np.array(position), np.array(velocity)

    @staticmethod
    def get_satellite_epoch(satrec):
        """获取卫星的TLE历元时间"""
        if satrec is None:
            return None
        try:
            return satrec.jdsatepoch + satrec.jdsatepochF
        except:
            return None


class TLEGenerator:
    """TLE生成器类"""

    def __init__(self):
        pass

    def generate_updated_tle_lines(self, original_line2, original_line3, orbital_elements, epoch_jd):
        """根据原始TLE和新的轨道要素生成更新后的TLE行"""
        # 从轨道要素中提取参数
        i = np.degrees(orbital_elements['i'])
        raan = np.degrees(orbital_elements['raan'])
        e = orbital_elements['e']
        argp = np.degrees(orbital_elements['argp'])
        ma = np.degrees(orbital_elements['ma'])
        n = orbital_elements['n']

        # 确保角度在0-360度范围内
        i = i % 360.0
        raan = raan % 360.0
        argp = argp % 360.0
        ma = ma % 360.0

        # 转换为TLE中使用的单位（圈/天）
        n_rev_per_day = n * 86400 / (2 * np.pi)

        # 生成第一行TLE数据
        sat_id_part = original_line2[2:17]

        # 将儒略日转换为TLE历元时间格式
        year, month, day, hour, minute, second = invjday(epoch_jd)

        days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
        if (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0):
            days_in_month[1] = 29

        day_of_year = sum(days_in_month[:month - 1]) + day
        day_fraction = day_of_year + (hour + minute / 60 + second / 3600) / 24
        year_short = year % 100
        epoch_str = f"{year_short:02d}{day_fraction:012.8f}"

        # 从原始line2中提取其他参数
        first_derivative = original_line2[33:43].strip()
        second_derivative = original_line2[44:52].strip()
        bstar = original_line2[53:61].strip()
        ephemeris_type = original_line2[62]
        element_set_number = original_line2[64:68].strip()

        # 构建第一行
        new_line2 = (f"1 {sat_id_part} {epoch_str} "
                     f"{first_derivative:>10} "
                     f"{second_derivative:>8} "
                     f"{bstar:>8} "
                     f"{ephemeris_type} "
                     f"{element_set_number:>4}")

        # 确保长度为68个字符
        if len(new_line2) > 68:
            new_line2 = new_line2[:68]
        elif len(new_line2) < 68:
            new_line2 = new_line2.ljust(68)

        checksum1 = self.calculate_tle_checksum(new_line2)
        new_line2 = new_line2 + str(checksum1)

        # 生成第二行TLE数据
        sat_num_part = original_line3[2:7] if len(original_line3) >= 7 else "16493"

        # 从原始line3中提取轨道圈数
        orbit_number = "00000"
        if len(original_line3) >= 68:
            orbit_number = original_line3[63:68]

        # 格式化轨道要素
        i_str = f"{i:8.4f}"
        raan_str = f"{raan:8.4f}"
        e_scaled = min(max(e, 0.0), 0.9999999)
        ecc_str = f"{int(e_scaled * 1e7):07d}"
        argp_str = f"{argp:8.4f}"
        ma_normalized = ma % 360.0
        ma_str = f"{ma_normalized:8.4f}"
        n_rev_per_day_clamped = min(max(n_rev_per_day, 0.01), 20.0)
        n_str = f"{n_rev_per_day_clamped:11.8f}"

        # 构建第二行
        new_line3 = (f"2 {sat_num_part} "
                     f"{i_str} "
                     f"{raan_str} "
                     f"{ecc_str} "
                     f"{argp_str} "
                     f"{ma_str} "
                     f"{n_str}"
                     f"{orbit_number}")

        # 确保长度为68个字符
        if len(new_line3) > 68:
            new_line3 = new_line3[:68]
        elif len(new_line3) < 68:
            new_line3 = new_line3.ljust(68)

        checksum2 = self.calculate_tle_checksum(new_line3)
        new_line3 = new_line3 + str(checksum2)

        return new_line2, new_line3

    def calculate_tle_checksum(self, line):
        """计算TLE校验和"""
        checksum = 0
        for i in range(min(len(line), 68)):
            char = line[i]
            if char.isdigit():
                checksum += int(char)
            elif char == '-':
                checksum += 1
        return checksum % 10


class CollisionAvoidanceTLEGenerator:
    """碰撞规避TLE生成器主类"""

    def __init__(self, satellite_list):
        self.satellite_list = satellite_list
        self.sgp4_satellites = []
        self.tle_generator = TLEGenerator()
        self._create_sgp4_satellites()

    def _create_sgp4_satellites(self):
        """为所有卫星创建SGP4对象"""
        for sat in self.satellite_list:
            line2 = sat.get('Line2', '')
            line3 = sat.get('Line3', '')

            if line2 and line3:
                satrec = SGP4Propagator.create_sgp4_satellite(line2, line3)
                self.sgp4_satellites.append(satrec)
            else:
                self.sgp4_satellites.append(None)

    def generate_maneuvered_tle(self, obj_idx, maneuver_start_dt,
                                duration_seconds=60.0,
                                delta_v_kms=1.0,
                                v_sign=1):
        """生成机动后TLE"""
        # 获取卫星数据
        sat_data = self.satellite_list[obj_idx]
        sat_id = sat_data['CatID']
        original_line2 = sat_data.get('Line2', '')
        original_line3 = sat_data.get('Line3', '')

        # 使用SGP4传播到机动开始时间
        maneuver_start_jd = date_to_julian(maneuver_start_dt)
        satrec = self.sgp4_satellites[obj_idx]

        if satrec is None:
            raise ValueError(f"卫星 {sat_id} 的SGP4对象不存在")

        # 传播到机动开始时间
        pre_maneuver_pos, pre_maneuver_vel = SGP4Propagator.propagate_sgp4(satrec, maneuver_start_jd)

        # 执行机动（沿迹方向施加ΔV）
        # delta_v_kms = delta_v_cmps * 0.01 / 1000.0  # cm/s -> km/s
        v_norm = np.linalg.norm(pre_maneuver_vel)

        if v_norm > 1e-6:
            thrust_direction = pre_maneuver_vel / v_norm * v_sign
        else:
            thrust_direction = np.array([1.0, 0.0, 0.0]) * v_sign

        post_maneuver_vel = pre_maneuver_vel + delta_v_kms * thrust_direction

        # 使用数值积分传播机动持续时间（包含J2摄动）
        initial_state = np.concatenate([pre_maneuver_pos, post_maneuver_vel])

        solution = solve_ivp(
            OrbitalDynamics.orbit_dynamics_equations,
            [0, duration_seconds],
            initial_state,
            method='RK45',
            rtol=1e-10,
            atol=1e-13,
            max_step=10.0
        )

        if not solution.success:
            raise ValueError(f"数值积分失败: {solution.message}")

        # 获取最终状态
        final_state = solution.y[:, -1]
        final_position = final_state[0:3]
        final_velocity = final_state[3:6]

        # 计算新的轨道要素
        final_oe = OrbitalDynamics.rv2coe(final_position, final_velocity)

        # 生成新TLE（使用机动结束时间作为新历元）
        maneuver_end_jd = maneuver_start_jd + duration_seconds / 86400.0
        tle_line1, tle_line2 = self.tle_generator.generate_updated_tle_lines(
            original_line2, original_line3, final_oe, maneuver_end_jd
        )

        return tle_line1, tle_line2, final_oe

    def batch_generate(self, maneuver_plan, output_file="maneuvered_satellites.tle"):
        """批量生成机动后TLE"""
        results = []

        with open(output_file, 'w', encoding='utf-8') as f:
            for i, plan in enumerate(maneuver_plan):
                sat_id = self.satellite_list[plan['obj_idx']]['CatID']
                sat_name = self.satellite_list[plan['obj_idx']]['Name']

                try:
                    # 生成机动后TLE
                    line1, line2, final_oe = self.generate_maneuvered_tle(
                        obj_idx=plan['obj_idx'],
                        maneuver_start_dt=plan['maneuver_start'],
                        duration_seconds=plan.get('duration_seconds', 60.0),
                        delta_v_kms=plan.get('delta_v_kms', 1.0),
                        v_sign=plan.get('v_sign', 1)
                    )

                    # 写入文件
                    f.write(f"{sat_name}\n")
                    f.write(f"{line1}\n")
                    f.write(f"{line2}\n")

                    results.append({
                        'satellite_id': sat_id,
                        'satellite_name': sat_name,
                        'final_orbital_elements': final_oe,
                        'tle_lines': {'line1': line1, 'line2': line2}
                    })

                except Exception as e:
                    # 写入原始TLE作为备份
                    original_sat = self.satellite_list[plan['obj_idx']]
                    f.write(f"{original_sat['Name']}\n")
                    f.write(f"{original_sat.get('Line2', '')}\n")
                    f.write(f"{original_sat.get('Line3', '')}\n")

        return results

    def generate_maneuvered_data(self, maneuver_plan):
        """
        生成机动后的卫星数据列表和半长轴列表
        这是原generate_maneuvered_satellite_data函数的类方法版本
        """
        maneuvered_ObjSat_list = []
        maneuvered_objsma = []

        for i, plan in enumerate(maneuver_plan):
            sat_id = self.satellite_list[plan['obj_idx']]['CatID']
            sat_name = self.satellite_list[plan['obj_idx']]['Name']

            try:
                # 生成机动后TLE
                line1, line2, stats = self.generate_maneuvered_tle(
                    obj_idx=plan['obj_idx'],
                    maneuver_start_dt=plan['maneuver_start'],
                    duration_seconds=plan.get('duration_seconds', 60.0),
                    delta_v_kms=plan.get('delta_v_kms', 1.0),
                    v_sign=plan.get('v_sign', 1)
                )

                # 构建机动后卫星数据
                maneuvered_sat = {
                    'CatID': sat_id,
                    'Name': sat_name,
                    'Line1': f'0 {sat_name}',
                    'Line2': line1,
                    'Line3': line2
                }

                # 获取半长轴
                sma = stats['a']

                # 添加到列表
                maneuvered_ObjSat_list.append(maneuvered_sat)
                maneuvered_objsma.append(sma)

            except Exception as e:
                # 如果失败，使用原始TLE作为备份
                original_sat = self.satellite_list[plan['obj_idx']]
                maneuvered_sat = {
                    'CatID': original_sat['CatID'],
                    'Name': original_sat['Name'],
                    'Line1': f'0 {original_sat["Name"]}',
                    'Line2': original_sat.get('Line2', ''),
                    'Line3': original_sat.get('Line3', '')
                }

                # 尝试获取原始半长轴
                try:
                    satrec = self.sgp4_satellites[plan['obj_idx']]
                    maneuver_start_jd = date_to_julian(plan['maneuver_start'])
                    pos, vel = SGP4Propagator.propagate_sgp4(satrec, maneuver_start_jd)
                    initial_oe = OrbitalDynamics.rv2coe(pos, vel)
                    sma = initial_oe['a']
                except:
                    # 使用TLE中的平均运动计算半长轴
                    n_motion = float(original_sat.get('Line3', '')[52:63])
                    if n_motion > 0:
                        sma = (MU_EARTH / (n_motion * 2 * math.pi / 86400) ** 2) ** (1 / 3)
                    else:
                        sma = 0.0

                maneuvered_ObjSat_list.append(maneuvered_sat)
                maneuvered_objsma.append(sma)

        return maneuvered_ObjSat_list, maneuvered_objsma


def test_simplified_generation():
    """测试简化版机动后卫星数据生成"""
    # 示例卫星数据
    sample_satellites = [
        {
            'CatID': '16493',
            'Name': 'COSMOS 1725',
            'Line1': 'COSMOS 1725',
            'Line2': '1 16493U 86005A   24321.33924196  .00000112  00000-0  10188-3 0  9996',
            'Line3': '2 16493  82.9330 251.7579 0022599   8.0684 104.2625 13.74842423993031'
        },
        {
            'CatID': '49256',
            'Name': 'JILIN-01 GAOFEN 2D',
            'Line1': 'JILIN-01 GAOFEN 2D',
            'Line2': '1 49256U 21086A   24322.12484499  .00016174  00000-0  64675-3 0  9997',
            'Line3': '2 49256  97.5966  75.2394 0015947 274.1486  85.7929 15.25067922173514'
        },
        {
            'CatID': '37484',
            'Name': 'COSMOS 2251 DEB',
            'Line1': '0 COSMOS 2251 DEB',
            'Line2': '1 37484U 93036BLM 24317.51444126  .00006305  00000-0  20471-2 0  9991',
            'Line3': '2 37484  73.8205 228.6690 0041615 336.5510 196.9929 14.38575574596886'
        }
    ]

    # 定义机动计划
    maneuver_plan = [
        {
            'obj_idx': 0,
            'maneuver_start': datetime(2024, 11, 16, 12, 0, 0),
            'duration_seconds': 0.0,
            'delta_v_kms': 1.0,
            'v_sign': 1
        },
        {
            'obj_idx': 1,
            'maneuver_start': datetime(2024, 11, 18, 0, 0, 0),
            'duration_seconds': 0.0,
            'delta_v_kms': 5.0,
            'v_sign': -1
        },
        {
            'obj_idx': 2,
            'maneuver_start': datetime(2024, 11, 17, 20, 0, 0),
            'duration_seconds': 0.0,
            'delta_v_kms': 7.0,
            'v_sign': 1
        }
    ]

    # 生成机动后数据
    generator = CollisionAvoidanceTLEGenerator(sample_satellites)
    maneuvered_ObjSat_list, maneuvered_objsma = generator.generate_maneuvered_data(maneuver_plan)
    output_file = "maneuvered_satellites.tle"
    generator.batch_generate(maneuver_plan, output_file)

    return maneuvered_ObjSat_list, maneuvered_objsma


if __name__ == "__main__":
    # 运行测试
    maneuvered_ObjSat_list, maneuvered_objsma = test_simplified_generation()

    print("机动后卫星数据生成完成:")
    print(f"生成卫星数量: {len(maneuvered_ObjSat_list)}")
    print(f"卫星数据列表：{maneuvered_ObjSat_list}")
    print(f"半长轴列表: {maneuvered_objsma}")

