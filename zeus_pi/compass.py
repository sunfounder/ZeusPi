#!/usr/bin/env python3
from robot_hat import I2C, fileDB
import time
from math import pi, atan2, degrees

def convert_2_int16(value):
    if value > 32767:
        value = -(65536 - value)
    return value

class QMC6310(I2C):
    # https://www.qstcorp.com/upload/pdf/202202/%EF%BC%88%E5%B7%B2%E4%BC%A0%EF%BC%8913-52-17%20QMC6310%20Datasheet%20Rev.C(1).pdf

    # I2C address  of QMC6310 compass sensor
    QMC6310_ADDR = 0x1C

    '''
    # Define register address of QMC6310 compass sensor
    '''
    QMC6310_REG_DATA_START = 0x01
    QMC6310_REG_DTAT_X= 0x01 # 0x01, 0x02
    QMC6310_REG_DTAT_Y= 0x03 # 0x03, 0x04
    QMC6310_REG_DTAT_Z= 0x05 # 0x05, 0x06

    QMC6310_REG_STATUS     = 0x09
    QMC6310_REG_CONTROL_1  = 0x0A
    QMC6310_REG_CONTROL_2  = 0x0B

    '''
    # Define the register parameter configuration of the sensor
    '''
    QMC6310_VAL_MODE_SUSPEND    = 0 << 0
    QMC6310_VAL_MODE_NORMAL     = 1 << 0
    QMC6310_VAL_MODE_SINGLE     = 2 << 0
    QMC6310_VAL_MODE_CONTINUOUS = 3 << 0

    QMC6310_VAL_ODR_10HZ  = 0 << 2
    QMC6310_VAL_ODR_50HZ  = 1 << 2
    QMC6310_VAL_ODR_100HZ = 2 << 2
    QMC6310_VAL_ODR_200HZ = 3 << 2

    QMC6310_VAL_OSR1_8 = 0 << 4
    QMC6310_VAL_OSR1_4 = 1 << 4
    QMC6310_VAL_OSR1_2 = 2 << 4
    QMC6310_VAL_OSR1_1 = 3 << 4
    QMC6310_VAL_OSR2_1 = 0 << 6
    QMC6310_VAL_OSR2_2 = 1 << 6
    QMC6310_VAL_OSR2_4 = 2 << 6
    QMC6310_VAL_OSR2_8 = 3 << 6

    QMC6310_VAL_MODE_SET_RESET_ON  = 0 << 0
    QMC6310_VAL_MODE_SET_ON        = 1 << 0
    QMC6310_VAL_MODE_SET_RESET_OFF = 2 << 0

    RANGE = {
        "30G":0 << 2, # 1000 LSB/Gauss
        "12G":1 << 2, # 2500 LSB/Gauss
        "8G":2 << 2, # 3750 LSB/Gauss
        "2G":3 << 2, # 15000 LSB/Gauss
    }

    LSB = {
        "30G":1, # 1 LSB/mGauss
        "12G":2.5, # 2.5 LSB/mGauss
        "8G":3.75, # 3.75 LSB/mGauss
        "2G":15, # 15 LSB/mGauss
    }

    QMC6310_VAL_SELF_TEST_ON  = 1 << 6
    QMC6310_VAL_SELF_TEST_OFF = 0 << 6
    QMC6310_VAL_SOFT_RST_ON   = 1 << 7
    QMC6310_VAL_SOFT_RST_OFF  = 0 << 7

    callabled = False

    _calibration_data = [0]*6
    _x = 0
    _y = 0
    _z = 0

    def __init__(self, range="8G"):

        super().__init__(address=self.QMC6310_ADDR)
        if not self.is_avaliable():
            raise IOError("QMC6310 is not avaliable")
        
        if range in ["30G", "12G", "8G", "2G"]:
            self.range = range
        else:
            self.range = "8G"
            raise ValueError("range must be one of ['30G', '12G', '8G', '2G']")

        #  init
        self._write_byte_data(0x29, 0x06)
        self._write_byte_data(self.QMC6310_REG_CONTROL_2, self.RANGE[range])
        self._write_byte_data(self.QMC6310_REG_CONTROL_1, 
            self.QMC6310_VAL_MODE_NORMAL | self.QMC6310_VAL_ODR_200HZ | self.QMC6310_VAL_OSR1_8 | self.QMC6310_VAL_OSR2_8)

    def read_raw(self):
        result = self._read_i2c_block_data(self.QMC6310_REG_DATA_START, 6)
        x = convert_2_int16(result[1] << 8 | result[0])
        y = convert_2_int16(result[3] << 8 | result[2])
        z = convert_2_int16(result[5] << 8 | result[4])
        return [x, y, z]


class Compass(QMC6310):

    def __init__(self, placement=["x", "y", "z"], range="8G"):
        '''
        placement: '[x','y','z']  ...
                   ...
                   ...
                   ...
        '''
        # qmc6310 init
        super().__init__(range)

        self.placement = placement
        self.x_min = 0
        self.x_max = 0
        self.y_min = 0
        self.y_max = 0
        self.z_min = 0
        self.z_max = 0
        self.x_offset = 0
        self.y_offset = 0
        self.z_offset = 0
        self.magnetic_declination_str = "0°0'W"
        self.magnetic_declination_angle = 0

    def angle_str_2_number(self, str):
        parts = str.split("°")
        degree = int(parts[0])
        parts = parts[1].split("'")
        minute = int(parts[0])
        direction = parts[1]
        if direction == "W":
            return -degree - minute / 60
        elif direction == "E":
            return degree + minute / 60
        
    def angle_number_2_str(self, number):
        degree = int(number)
        minute = int((number - degree) * 60)
        direction = "E"
        if number < 0:
            direction = "W"
            degree = -degree
        return str(degree) + "°" + str(minute) + "'" + direction

    def set_magnetic_declination(self, str):
        self.magnetic_declination_angle = self.angle_str_2_number(str)

    def read(self):
        x, y, z = self.read_raw()

        x = x - self.x_offset
        y = y - self.y_offset
        z = z - self.z_offset

        x_mG = x / self.LSB[self.range]
        y_mG = y / self.LSB[self.range]
        z_mG = z / self.LSB[self.range]

        temp = {
            'x': [x, self.x_offset],
            'y': [y, self.y_offset],
            'z': [z, self.z_offset],
            '-x': [-x, -self.x_offset],
            '-y': [-y, -self.y_offset],
            '-z': [-z, -self.z_offset],
        }
        a = temp[self.placement[0]][0]
        b = temp[self.placement[1]][0]
        a_offset = temp[self.placement[0]][1]
        b_offset = temp[self.placement[1]][1]
        a = a - a_offset
        b = b - b_offset

        # angle = atan2(a, b) *180 / pi
        # if angle < 0:
        #     angle += 360

        angle = degrees(atan2(b, a)) - self.magnetic_declination_angle
        angle = (angle + 360) % 360

        return (x_mG, y_mG, z_mG, round(angle, 2))

    def set_calibration(self, x_min, x_max, y_min, y_max, z_min, z_max):
        self.x_min = x_min
        self.x_max = x_max
        self.y_min = y_min
        self.y_max = y_max
        self.z_min = z_min
        self.z_max = z_max
        self.x_offset = (self.x_min + self.x_max) / 2
        self.y_offset = (self.y_min + self.y_max) / 2
        self.z_offset = (self.z_min + self.z_max) / 2

    def set_magnetic_declination(self, angle):
        if isinstance(angle, str):
            self.magnetic_declination_str = angle
            self.magnetic_declination_angle = self.angle_str_2_number(angle)
        elif isinstance(angle, float) or isinstance(angle, int):
            self.magnetic_declination_angle = float(angle)
            self.magnetic_declination_str = self.angle_number_2_str(angle)

    def clear_calibration(self):
        self.x_min = 0
        self.x_max = 0
        self.y_min = 0
        self.y_max = 0
        self.z_min = 0
        self.z_max = 0
        self.x_offset = 0
        self.y_offset = 0
        self.z_offset = 0

if __name__ == '__main__':
    compass = Compass(placement=['x', 'y'], range='8G')

    while True:
        x, y, z, angle = compass.read()
        print(f"x: {x:.2f} mGuass   y: {y:.2f} mGuass   z: {z:.2f} mGuass   angle: {angle}°")
        time.sleep(0.5)
