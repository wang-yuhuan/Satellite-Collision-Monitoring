from sgp4.api import Satrec
import numpy as np

def sgp4init(whichconst, satrec, bstar, ecco, epoch, argpo, inclo, mo, no_kozai, nodeo):
    satrec.bstar = bstar
    satrec.ecco = ecco
    satrec.epoch = epoch
    satrec.argpo = argpo
    satrec.inclo = inclo
    satrec.mo = mo
    satrec.no_kozai = no_kozai
    satrec.nodeo = nodeo
    return satrec

def sgp4(satrec, offset):
    jd = satrec.epoch + offset / 1440.0
    fr = 0.0
    # 计算位置和速度
    error, position, velocity = satrec.sgp4(jd, fr)
    return error, np.array(position), np.array(velocity)