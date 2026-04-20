import numpy as np
from datetime import datetime
from sgp4.api import jday

def load_maneuver_data(fmaneverdata, ObjSat):
    """
    从推进数据文件中读取和加载推进数据
    """
    objNum = len(ObjSat)
    TotalManeuverData = 0
    PropStartjday = np.zeros(objNum)
    PropEndjday = np.zeros(objNum)
    pcovoffset = np.zeros((objNum, 6))
    ManeuverDuration = np.zeros(objNum)
    objmaxfuel = np.zeros(objNum)
    objdrymass = np.zeros(objNum)
    ae = np.zeros(objNum)
    cd = np.zeros(objNum)
    satmass = np.zeros(objNum)
    PropMethod = np.zeros(objNum)
    PropVsign = np.zeros(objNum)
    isSwitch = np.zeros(objNum)
    
    pressureprofile = [None] * objNum
    thrustprofile = [None] * objNum
    ispprofile = [None] * objNum
    
    # 检查文件是否存在
    try:
        with open(fmaneverdata, 'r') as fidmanvr:
            linetemp = fidmanvr.readline()
            if 'SatID' in linetemp:
                eqloc = linetemp.find('=')
                loadSatCatID = linetemp[eqloc+2:].strip()
                
                for objk in range(objNum):
                    if str(ObjSat[objk]['CatID']) in loadSatCatID:
                        TotalManeuverData += 1
                    
                        linetemp = fidmanvr.readline()
                        ManeuverDate = linetemp.split('=')[1].strip()
                        
                        linetemp = fidmanvr.readline()
                        ManeuverTime = linetemp.split('=')[1].strip()
                        
                        linetemp = fidmanvr.readline()
                        ManeuverDuration[objk] = float(linetemp.split('=')[1].strip())
                        
                        linetemp = fidmanvr.readline()
                        objmaxfuel[objk] = float(linetemp.split('=')[1].strip())
                        
                        linetemp = fidmanvr.readline()
                        satmass[objk] = float(linetemp.split('=')[1].strip())
                        
                        linetemp = fidmanvr.readline()
                        objdrymass[objk] = float(linetemp.split('=')[1].strip())
                        
                        linetemp = fidmanvr.readline()
                        PropMethod[objk] = int(linetemp.split('=')[1].strip())
                        
                        linetemp = fidmanvr.readline()
                        PropVsign[objk] = int(linetemp.split('=')[1].strip())
                        
                        linetemp = fidmanvr.readline()
                        ae[objk] = float(linetemp.split('=')[1].strip())
                        
                        linetemp = fidmanvr.readline()
                        cd[objk] = float(linetemp.split('=')[1].strip())
                        
                        linetemp = fidmanvr.readline()
                        pressureprofile[objk] = float(linetemp.split('=')[1].strip())
                        
                        linetemp = fidmanvr.readline()
                        thrustprofile[objk] = float(linetemp.split('=')[1].strip())
                        
                        linetemp = fidmanvr.readline()
                        ispprofile[objk] = float(linetemp.split('=')[1].strip())
                        
                        # 转换为推进开始和结束的儒略日期
                        ManvrDT = datetime.strptime(f"{ManeuverDate} {ManeuverTime}", '%Y-%m-%d %H:%M:%S')
                        PropStartjday[objk] = jday(ManvrDT.year, ManvrDT.month, ManvrDT.day,
                                                   ManvrDT.hour, ManvrDT.minute, ManvrDT.second)
                        PropEndjday[objk] = PropStartjday[objk] + ManeuverDuration[objk] / 86400.0
                        
    except FileNotFoundError:
        print(f"文件 '{fmaneverdata}' 未找到.")
    
    return {
        "TotalManeuverData": TotalManeuverData,
        "PropStartjday": PropStartjday,
        "PropEndjday": PropEndjday,
        "ManeuverDuration": ManeuverDuration,
        "objmaxfuel": objmaxfuel,
        "satmass": satmass,
        "objdrymass": objdrymass,
        "PropMethod": PropMethod,
        "PropVsign": PropVsign,
        "ae": ae,
        "cd": cd,
        "pressureprofile": pressureprofile,
        "thrustprofile": thrustprofile,
        "ispprofile": ispprofile
    }


