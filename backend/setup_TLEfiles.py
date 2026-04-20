import numpy as np
from download_TLEs_data import download_tle
import math
from tools.date_trans import calculate_jday
import os

WORKSPACE_DIR = './backend/processed_data'
if not os.path.exists(WORKSPACE_DIR):
    os.makedirs(WORKSPACE_DIR)
    
tempfile = './backend/temptle.tle'

def generate_objSat_from_temptle(tempfile ,ObjCatID):
    mu = 398600.8 # 地球标准重力参数 (km^3/s^2)
    objfile = os.path.join(WORKSPACE_DIR, 'objtle.tle')
    # ObjCatID = np.array([['16493'], ['49256'], ['37484'], ['16493'], ['43910']])# object Sat,can be changed
    objNum = len(ObjCatID)
    ObjSat_list = [{} for _ in range(objNum)]
    for objIdx in range(objNum):
        ObjSat_list[objIdx]["CatID"] = ObjCatID[objIdx][0]
    objsma = [0.0] * objNum
    with open(tempfile ,"r") as origin_Satfile:
        l1 = origin_Satfile.readline().strip()
        while l1:
            l2 = origin_Satfile.readline().strip()
            l3 = origin_Satfile.readline().strip()
            tempCatID = l2[2:7]
            tempSatName = l1[:]

            for objIdx in range(objNum):
                if ObjSat_list[objIdx]["CatID"] == tempCatID:
                    ObjSat_list[objIdx]["Name"] = tempSatName
                    ObjSat_list[objIdx]["Line1"] = l1
                    ObjSat_list[objIdx]["Line2"] = l2
                    ObjSat_list[objIdx]["Line3"] = l3

                    tempMeanMotion = float(l3[52:63])
                    tempn = tempMeanMotion * 2 * math.pi / 86400
                    tempSMA = (mu / tempn**2) ** (1/3)
                    objsma[objIdx] = tempSMA

            l1 = origin_Satfile.readline().strip()


    with open(objfile, 'w') as f:
        for objIdx in range(objNum):
            f.write(f"{ObjSat_list[objIdx]['Line1'][2:]}")
            f.write(f"{ObjSat_list[objIdx]['Line2']}\n")
            f.write(f"{ObjSat_list[objIdx]['Line3']}\n")
    return ObjSat_list, objsma


def generate_tarSat_from_temptle(tempfile, target_file, ObjSat_list, objsma):
    mu = 398600.8 # 地球标准重力参数 (km^3/s^2)
    smaThresHold = 50  # 半长轴阈值 (可调整)
    ConjStartJulian = 2451545.0  # 2000年1月1日的儒略日
    tgtNum = 0
    TgtSat = []
    objNum = len(ObjSat_list)
    with open(tempfile, 'r') as fid, open(target_file, 'w') as ftgt:
        l1 = fid.readline().strip()
        while l1:
            l2 = fid.readline().strip()
            l3 = fid.readline().strip()
            tempCatID = l2[2:7]
            tempSatName = l1[2:]

            tempecc = float(f"0.{l3[26:33]}")
            tempMeanMotion = float(l3[52:63])
            tempn = tempMeanMotion * 2 * math.pi / 86400
            tempSMA = (mu / tempn**2) ** (1/3)

            # 检查是否符合条件
            Isqualify = 0
            if (tempSMA <= (max(objsma) + smaThresHold)) and (tempSMA >= (min(objsma) - smaThresHold)):
                Isqualify = 1
            if ((1 + tempecc) * tempSMA >= (max(objsma) + smaThresHold)) and ((1 - tempecc) * tempSMA <= min(objsma)):
                Isqualify = 1
            if ((1 + tempecc) * tempSMA >= max(objsma)) and ((1 - tempecc) * tempSMA <= (min(objsma) - smaThresHold)):
                Isqualify = 1

            for objIdx in range(objNum):
                if tempCatID == ObjSat_list[objIdx]["CatID"]:
                    Isqualify = 0

            if Isqualify:
                iyr = int(l2[18:20])
                dayofyear = float(l2[20:32])
                iyear = 2000 + iyr if iyr < 50 else 1900 + iyr
                jdtmp = calculate_jday(iyear, 1, 0, 0, 0, 0)
                tlejd = jdtmp + dayofyear

                if tlejd >= (ConjStartJulian - 365.0):
                    if tgtNum == 0 or TgtSat[tgtNum - 1]["CatID"] != tempCatID:
                        TgtSat.append({})
                        tgtNum += 1
                    TgtSat[tgtNum - 1]["CatID"] = tempCatID
                    TgtSat[tgtNum - 1]["Name"] = tempSatName
                    TgtSat[tgtNum - 1]["Line1"] = l1
                    TgtSat[tgtNum - 1]["Line2"] = l2
                    TgtSat[tgtNum - 1]["Line3"] = l3

                    ftgt.write(f"{l1[2:]}\n")
                    ftgt.write(f"{l2}\n")
                    ftgt.write(f"{l3}\n")

            l1 = fid.readline().strip()
    return TgtSat

if __name__ == "__main__":
    #ObjCatID = np.array([['16493'], ['49256'], ['37484'], ['16493'], ['43910']])# object Sat,can be changed
    ObjCatID = np.array([['49256']])# object Sat,can be changed
    ObjSat_list, objsma = generate_objSat_from_temptle(tempfile, ObjCatID)
    print(ObjSat_list)
    print(objsma)
    TgtSat_list = generate_tarSat_from_temptle(tempfile, ObjSat_list, objsma)
    print("卫星数据已处理完毕。")

