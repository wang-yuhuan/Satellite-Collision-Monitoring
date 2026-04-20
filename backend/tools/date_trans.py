import math


def calculate_jday(yr, mon, day, hr, min, sec):
    jd = (367.0 * yr
          - math.floor((7 * (yr + math.floor((mon + 9) / 12.0))) * 0.25)
          + math.floor(275 * mon / 9.0)
          + day + 1721013.5
          + ((sec / 60.0 + min) / 60.0 + hr) / 24.0)
    return jd

def date_to_julian(dt):
    yr = dt.year
    mon = dt.month
    day = dt.day
    hr = dt.hour
    minute = dt.minute
    sec = dt.second
    if mon <= 2:
        mon += 12
        yr -= 1
    A = yr // 100
    B = 2 - A + A // 4
    jd = (367.0 * yr
          - math.floor((7 * (yr + math.floor((mon + 9) / 12.0))) * 0.25)
          + math.floor(275 * mon / 9.0)
          + day + 1721013.5
          + ((sec / 60.0 + minute) / 60.0 + hr) / 24.0)
    return jd

def invjday(jd):
    jd_adj = jd + 0.5
    Z = int(jd_adj)
    F = jd_adj - Z
    if Z < 2299161:
        alpha = int((Z - 1867216.25) / 36524.25)
        A = Z + 1 + alpha - int(alpha / 4)
    else:
        alpha = int((Z - 1867216.25) / 36524.25)
        A = Z + 1 + alpha - int(alpha / 4)
    B = A + 1524
    C = int((B - 122.1) / 365.25)
    D = int(365.25 * C)
    E = int((B - D) / 30.6001)
    day_fractional = B - D - int(30.6001 * E) + F
    day = int(day_fractional)
    if E < 14:
        month = E - 1
    else:
        month = E - 13
    if month > 2:
        year = C - 4716
    else:
        year = C - 4715
    total_seconds_in_day = F * 86400.0
    epsilon = 1e-9
    if total_seconds_in_day >= 86400.0 - epsilon:
        total_seconds_in_day = 0.0
    elif total_seconds_in_day < 0:
        total_seconds_in_day = 0.0
    hour_float = total_seconds_in_day / 3600.0
    hour = int(hour_float)
    minute_float = (hour_float - hour) * 60.0
    minute = int(minute_float)
    second = (minute_float - minute) * 60.0
    if second >= 60.0 - epsilon:
         second = 0.0
         minute += 1
         if minute >= 60:
             minute = 0
             hour += 1
             if hour >= 24:
                 hour = 0
    return int(year), int(month), int(day), int(hour), int(minute), second