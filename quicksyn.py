#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import glob
import os
import platform
import re
import stat
import sys
import time
from time import sleep

import serial


class FUnit(object):
    mHz, Hz, kHz, MHz, GHz = 1e-3, 1.0, 1e+3, 1e+6, 1e+9


OSNAME = platform.system()
BASEDIR = '/dev/ttyACM'
if OSNAME == 'Linux':
    BASEDIR = '/dev/ttyACM'
    if 'microsoft' in platform.version().lower():
        BASEDIR = '/dev/ttyS'
elif OSNAME == 'Darwin':
    BASEDIR = '/dev/tty.usbmodem'
elif OSNAME == 'Java':
    pass
elif OSNAME == 'Windows':
    BASEDIR = 'COM'


class Status(object):
    def __init__(self, status_str):
        if isinstance(status_str, bytes):
            status_str = status_str.decode('utf-8', errors='ignore').strip()
        bincode = bin(int(status_str[0:2], 16))[2:].zfill(8)[::-1]
        self.ext_ref_detected = bincode[0] == '1'
        self.rf_locked        = bincode[1] == '0'
        self.ref_locked       = bincode[2] == '0'
        self.rf_output_on     = bincode[3] == '1'
        self.voltage_ok       = bincode[4] == '0'
        self.ref_output_on    = bincode[5] == '1'
        self.lock_recovery    = bincode[7] == '1'


class ID(object):
    def __init__(self, id_str):
        if isinstance(id_str, bytes):
            id_str = id_str.decode('utf-8', errors='ignore').strip()
        self.model_number  = id_str[0:4]
        self.option_number = id_str[4:8]
        self.soft_version  = id_str[8:12]
        self.serial_number = int(id_str[12:22])


def str_to_hex(f_str):
    result = re.search(r'\d+(\.\d+)?', f_str)
    if result is None:
        raise ValueError(f'Invalid frequency string: {f_str}')
    f_num_str = result.group()
    unit_str = f_str[result.end():].strip()
    if not hasattr(FUnit, unit_str):
        raise ValueError(f'Invalid frequency unit: {unit_str}')
    return frequency_formatter(float(f_num_str), getattr(FUnit, unit_str))


def hex_to_freq(f_hex, unit=FUnit.GHz):
    if isinstance(f_hex, bytes):
        f_hex = f_hex.decode('utf-8', errors='ignore').strip()
    mhz_val = int(f_hex, 16)
    return mhz_val / unit * FUnit.mHz


def frequency_formatter(f_num, hz_scale):
    return hex_conv(f_num * hz_scale / FUnit.mHz)


def hex_conv(f_mHz, n_byte=6):
    if f_mHz > 0xffffffffffff:
        raise Exception('over 12 characters')
    fmt_str = '{' + f':0{2*n_byte}X' + '}'
    return fmt_str.format(int(f_mHz))


class QuickSyn(object):
    driver_name = 'quicksyn'

    def __init__(self, channel=None, dirname=BASEDIR, path=None, serialnum=None, lockfile_timeout=1):
        if path is None:
            if channel is not None:
                path = dirname + '{0}'.format(channel)
            if serialnum is not None:
                path = path_fromserial(dirname, serialnum=serialnum)
            if path is None:
                path = path_fromserial(dirname)

        self.__lockf = None
        self.__lock_path = '/tmp/.' + path.split('/')[-1] + '.lock'
        t = 0
        while t == 0 or time.time() - t < lockfile_timeout:
            try:
                if not OSNAME == 'Windows':
                    import fcntl
                    if not os.path.isfile(self.__lock_path):
                        self.__lockf = open(self.__lock_path, 'a', encoding='utf-8')
                        self.__lockf.close()
                        os.chmod(
                            self.__lock_path,
                            mode=stat.S_IRUSR |
                                 stat.S_IWUSR |
                                 stat.S_IRGRP |
                                 stat.S_IWGRP |
                                 stat.S_IROTH |
                                 stat.S_IWOTH
                        )
                    self.__lockf = open(self.__lock_path, 'a', encoding='utf-8')
                    fcntl.flock(self.__lockf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except IOError:
                if t == 0:
                    print(f'{self.__lock_path} is locked. Waiting till {lockfile_timeout} sec...')
                    t = time.time()
                continue
        else:
            print(f"Timeout. Please check whether this QuickSyn '{path}' is being used.")
            sys.exit(1)

        self._ser = serial.Serial(path, timeout=0.1)
        self._path = path

    def _wr(self, command):
        self._ser.reset_input_buffer()
        self._ser.write(command.encode('utf-8'))
        sleep(0.1)
        return self._ser.readline()

    def reset(self):
        self._wr("0E")

    def get_id(self):
        return ID(self._wr('01'))

    def get_status(self):
        return Status(self._wr('02'))

    def get_frequency(self, unit=FUnit.GHz):
        return hex_to_freq(self._wr('04'), unit=unit)

    def get_temperature(self):
        readstr = self._wr('10')
        if isinstance(readstr, bytes):
            readstr = readstr.decode('utf-8', errors='ignore').strip()
        return int(readstr, 16) / 10.

    def set_freq_mHz(self, freq_mHz):
        self._wr('0C' + hex_conv(freq_mHz))

    def set_freq_str(self, freq_str):
        self._wr('0C' + str_to_hex(freq_str))

    def set_frequency_hz(self, freq_hz):
        self._wr('0C' + frequency_formatter(freq_hz, FUnit.Hz))

    def set_rfout(self, on=True):
        self._wr('0F01' if on else '0F00')

    def set_refout(self, on=True):
        self._wr('0801' if on else '0800')

    def set_ref_ext(self):
        self._wr('0601')

    def set_ref_int(self):
        self._wr('0600')

    def get_refsource(self):
        readstr = self._wr('07')
        if isinstance(readstr, bytes):
            readstr = readstr.decode('utf-8', errors='ignore').strip()
        return int(readstr, 16) == 1

    def detect_refext(self):
        if not self.get_refsource():
            print('WARNING:: detect_refext: Current setup is internal reference')
        status = self.get_status()
        return status.ext_ref_detected

    def adjust_refint(self, value):
        if self.get_refsource():
            print('WARNING:: adjust_refint: Current setup is external reference')
        if value > 0xffff:
            raise Exception(f'adjust_refint: Invalid input 0x{value:X}: over 4 characters')
        self._wr(f'1B{value:04X}')

    def set_lock_recovery(self, on=True):
        self._wr('2801' if on else '2800')

    def save_current_state(self, channel=1):
        self._wr('260{0}'.format(channel))

    def restore_current_state(self, channel=0):
        self._wr('270{0}'.format(channel))

    def get_common_state(self):
        status = self.get_status()
        qid = self.get_id()
        return {
            'driver': self.driver_name,
            'model': qid.model_number,
            'serial_number': qid.serial_number,
            'path': self._path,
            'frequency_hz': self.get_frequency(unit=FUnit.Hz),
            'rf_output_on': status.rf_output_on,
            'rf_locked': status.rf_locked,
            'ref_locked': status.ref_locked,
            'ref_output_on': status.ref_output_on,
            'reference_source': 'external' if self.get_refsource() else 'internal',
            'temperature_c': self.get_temperature(),
        }

    def close(self):
        self._ser.close()

    def print(self):
        idf = self.get_id()
        print('Model #\t\t', idf.model_number)
        print('Option #\t',  idf.option_number)
        print('Soft ver\t',  idf.soft_version)
        print('Serial #\t',  idf.serial_number)
        print('Dev path\t',  self._path)
        print()

        def bool_str(x):
            return 'On' if x else 'Off'

        status = self.get_status()
        print('Voltage OK\t',    status.voltage_ok)
        refsource = self.get_refsource()
        refstatus = "INVALID"
        if refsource:
            refstatus = "External: "
            refstatus += "detected" if status.ext_ref_detected else "no ref signals"
        else:
            refstatus = "Internal"
        print('Ref source\t',    refstatus)
        print('RF locked\t',     status.rf_locked)
        print('Ref locked\t',    status.ref_locked)
        print('RF output\t',     bool_str(status.rf_output_on))
        print('Ref output\t',    bool_str(status.ref_output_on))
        print('Lock recovery\t', bool_str(status.lock_recovery))
        print('Inst temp\t',     self.get_temperature(), 'degC')
        print()
        freq = self.get_frequency(unit=FUnit.GHz)
        print('Current freq.\t', freq, 'GHz')


def path_fromserial(dirname, serialnum=None, showlist=False):
    ret = ""
    if OSNAME == 'Windows':
        import serial.tools.list_ports
        pathlist = [com.device for com in serial.tools.list_ports.comports()]
    else:
        pathlist = glob.glob(dirname + "*")

    for _p in sorted(pathlist):
        try:
            _q = QuickSyn(path=_p)
            qid = _q.get_id()
            if showlist:
                ret += f'{_p}: {qid.serial_number} (model: {qid.model_number})\n'
            elif serialnum is not None and str(qid.serial_number) == str(serialnum):
                _q.close()
                return _p
            elif serialnum is None and not showlist:
                _q.close()
                return _p
            _q.close()
        except Exception:
            pass

    if showlist:
        return ret

    print(f"ERROR:: Not found the serial# == {serialnum}")
    sys.exit()
