#!/usr/bin/env python3

import re
from time import sleep
from argparse import ArgumentParser
import sys
from sg_manager import FUnit,hex_conv,QuickSyn,BASEDIR

def freq_to_hex(f,unit=FUnit.Hz):
    return hex_conv(f*unit/FUnit.mHz)

def str_to_freq(f_str,unit=FUnit.Hz):
    result = re.search(r'\d+(\.\d+)?', f_str)    
    f_num_str = result.group()
    unit_str = f_str[result.end():]
    f_ret = float(f_num_str) * getattr(FUnit, unit_str)
    return round(f_ret)/unit

class QuickSynSweep(QuickSyn):
    def __init__(self, mode, start, stop, step, points, dwell, run, channel=None, dirname=BASEDIR, path=None, serialnum=None):
        self.mode      = mode
        self.f_start   = start
        self.f_stop    = stop
        self.f_step    = step
        self.points    = int(points)
        self.dwell     = int(dwell)
        self.run_times = int(run)
        super().__init__(channel,dirname,path,serialnum)

    def send_command(self):
        trigger = 0
        direction = 0

        if self.mode == 'normal':
            main = '1C'
            fineness = freq_to_hex(self.f_step,unit=FUnit.Hz)
        elif self.mode == 'fast':
            main = '17'
            fineness = hex_conv(self.points, n_byte=2)

        swp_comm = [main,
                    freq_to_hex(self.f_start,unit=FUnit.Hz),
                    freq_to_hex(self.f_stop,unit=FUnit.Hz),
                    fineness,
                    '0000',      # must be 0
                    hex_conv(self.dwell, n_byte=4),
                    hex_conv(self.run_times, n_byte=2),
                    hex_conv((1<<2)*trigger | direction, n_byte=1)]
        return self._wr("".join(swp_comm))

if __name__ == '__main__':
    desc = '{0} [Args] [Options]\nDetailed options -h or --help'.format(__file__)
    parser = ArgumentParser(description=desc)

    parser.add_argument('mode',
                        type=str,
                        default='normal',
                        help='Select [normal] or [fast].')

    parser.add_argument('-c', '--channel',
                        type=str,
                        dest='channel',
                        default=None,
                        help=BASEDIR+'{}')

    parser.add_argument('-s', '--serial',
                        type=int,
                        dest='serial',
                        default=None,
                        help=f'Serial number')

    parser.add_argument('--path',
                        type=str,
                        dest='path',
                        default=None,
                        help="device path")

    parser.add_argument('-fc', '--f_center',
                        type=str,
                        dest='f_center',
                        default='4GHz',
                        help='center frequency of sweep with unit.')

    parser.add_argument('-fw', '--f_width',
                        type=str,
                        dest='f_width',
                        default='2MHz',
                        help='sweeping frequency half-width with unit.')

    parser.add_argument('-fs', '--f_step',
                        type=str,
                        dest='f_step',
                        default='10kHz',
                        help='sweep step frequency with unit.')

    parser.add_argument('-p', '--points',
                        type=str,
                        dest='points',
                        default='200',
                        help='# of sweep points.')

    parser.add_argument('-d', '--dwell',
                        type=str,
                        dest='dwell',
                        default='1000',
                        help='dwell time in us.')

    parser.add_argument('-r', '--run_times',
                        type=str,
                        dest='run_times',
                        default='10',
                        help='# of run times.')

    args = parser.parse_args()

    if (args.mode != 'normal') and (args.mode != 'fast'):
        print('invalid argument. first argument must be \'normal\' or \'fast\'.')
        sys.exit()

    f_center_Hz = str_to_freq(args.f_center,unit=FUnit.Hz)
    f_width_Hz  = str_to_freq(args.f_width,unit=FUnit.Hz)
    f_start_Hz  = f_center_Hz - f_width_Hz
    f_stop_Hz   = f_center_Hz + f_width_Hz

    sweep = QuickSynSweep(mode   = args.mode,
                          start  = f_start_Hz,
                          stop   = f_stop_Hz,
                          step   = str_to_freq(args.f_step,unit=FUnit.Hz),
                          points = args.points,
                          dwell  = args.dwell,
                          run    = args.run_times,
                          channel = args.channel,
                          path = args.path,
                          serialnum = args.serial)

    ret_swp = sweep.send_command()

    sweep.close()
