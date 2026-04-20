import datetime
from typing import Union

def getdateform(dateform: int) -> str:
    """根据日期格式编号返回日期格式字符串"""
    date_formats = {
        -1: "%d-%b-%Y %H:%M:%S",
        0: "%d-%b-%Y %H:%M:%S",
        1: "%d-%b-%Y",
        2: "%m/%d/%y",
        3: "%b",
        4: "%m",
        5: "%m",
        6: "%m/%d",
        7: "%d",
        8: "%a",
        9: "%d",
        10: "%Y",
        11: "%y",
        12: "%b%y",
        13: "%H:%M:%S",
        14: "%I:%M:%S %p",
        15: "%H:%M",
        16: "%I:%M %p",
        17: "Q%q-%y",
        18: "Q%q",
        19: "%d/%m",
        20: "%d/%m/%y",
        21: "%b.%d,%Y %H:%M:%S",
        22: "%b.%d,%Y",
        23: "%m/%d/%Y",
        24: "%d/%m/%Y",
        25: "%y/%m/%d",
        26: "%Y/%m/%d",
        27: "Q%q-%Y",
        28: "%b%Y",
        29: "%Y-%m-%d",
        30: "%Y%m%dT%H%M%S",
        31: "%Y-%m-%d %H:%M:%S",
    }
    if dateform in date_formats:
        return date_formats[dateform]
    else:
        raise ValueError(f"Unknown date format: {dateform}")

def datestr(DateTrack,dateform) -> str:
    if isinstance(DateTrack, str):
        try:
            dtnumber = datetime.datetime.strptime(DateTrack, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            dtnumber = datetime.datetime.strptime(DateTrack, "%Y-%m-%d")
    elif isinstance(DateTrack, (float, int)):
        dtnumber = datetime.datetime(1, 1, 1) + datetime.timedelta(days=DateTrack - 366)
    elif isinstance(DateTrack, datetime.datetime):
        dtnumber = DateTrack
    else:
        raise ValueError("Unsupported date type")
    if isinstance(dateform, int):
        dateformstr = getdateform(dateform)
    elif isinstance(dateform, str):
        dateformstr = dateform
    else:
        raise ValueError("Invalid date format type")

    return dtnumber.strftime(dateformstr)

# 示例测试
if __name__ == "__main__":
    # 测试日期字符串输入
    print(datestr("2023-11-17 14:30:00", 1))  # 输出：17-Nov-2023
    print(datestr("2023-11-17", 23))          # 输出：11/17/2023
    
    # 测试浮点数输入（假设输入为 MATLAB datenum）
    print(datestr(738847.0, 1))               # 输出：17-Nov-2023
    
    # 测试 datetime 对象输入
    now = datetime.datetime.now()
    print(datestr(now, 0))                     # 输出：当前日期时间
