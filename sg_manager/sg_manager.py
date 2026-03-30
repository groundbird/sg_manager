#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from time import sleep
from argparse import ArgumentParser
from argparse import RawTextHelpFormatter

from quicksyn import QuickSyn, FUnit as QFUnit, path_fromserial as quicksyn_path_fromserial, BASEDIR as QUICKSYN_BASEDIR
from valon import Valon5015, path_fromserial as valon_path_fromserial


def parse_bool_onoff(value):
    if value is None:
        return None
    v = value.strip().lower()
    if v in ('on', '1', 'true'):
        return True
    if v in ('off', '0', 'false'):
        return False
    raise ValueError("Select 'on' or 'off'")


def hz_to_ghz(freq_hz):
    return freq_hz / 1e9


def list_devices():
    print('[QuickSyn]')
    ret = quicksyn_path_fromserial(QUICKSYN_BASEDIR, showlist=True)
    if ret.strip():
        print('device path : serial #')
        print(ret, end='' if ret.endswith('\n') else '\n')
    else:
        print('(not found)')
    print()

    print('[Valon]')
    ret = valon_path_fromserial(showlist=True)
    if ret and ret.strip():
        print('device path : serial #')
        print(ret, end='' if ret.endswith('\n') else '\n')
    else:
        print('(not found)')


def resolve_driver(args=None):
    if args is not None and args.driver:
        return args.driver.lower()

    return 'auto'


def create_device(args=None):
    driver = resolve_driver(args)

    if driver == 'quicksyn':
        if args.path is not None:
            return QuickSyn(path=args.path)
        elif args.serial is not None:
            return QuickSyn(serialnum=args.serial)
        elif args.channel is not None:
            return QuickSyn(channel=int(args.channel))
        else:
            return QuickSyn()

    if driver == 'valon':
        if args.path is not None:
            return Valon5015(path=args.path)
        elif args.serial is not None:
            path = valon_path_fromserial(serialnum=args.serial)
            if path is None:
                print(f'ERROR:: Valon serial# {args.serial} not found')
                sys.exit(1)
            return Valon5015(path=path)
        else:
            path = valon_path_fromserial()
            if path is None:
                print('ERROR:: Valon not found')
                sys.exit(1)
            return Valon5015(path=path)

    if driver == 'auto':
        # quicksyn first
        try:
            if args is None:
                return QuickSyn()
            if args.path is not None:
                return QuickSyn(path=args.path)
            elif args.serial is not None:
                return QuickSyn(serialnum=args.serial)
            elif args.channel is not None:
                return QuickSyn(channel=int(args.channel))
            else:
                return QuickSyn()
        except Exception:
            pass

        try:
            if args is None:
                path = valon_path_fromserial()
                return Valon5015(path=path)
            if args.path is not None:
                return Valon5015(path=args.path)
            elif args.serial is not None:
                path = valon_path_fromserial(serialnum=args.serial)
                if path is None:
                    raise RuntimeError('Valon serial not found')
                return Valon5015(path=path)
            else:
                path = valon_path_fromserial()
                if path is None:
                    raise RuntimeError('Valon not found')
                return Valon5015(path=path)
        except Exception:
            pass

        print('ERROR:: device could not be opened as QuickSyn nor Valon')
        sys.exit(1)

    print(f'ERROR:: unknown driver: {driver}')
    sys.exit(1)


def print_compact_status(dev):
    state = dev.get_common_state()
    freq_ghz = hz_to_ghz(state['frequency_hz'])
    print('freq =', freq_ghz, 'GHz', '[', 'On' if state['rf_output_on'] else 'Off', ']')


def print_verbose(dev):
    if hasattr(dev, 'print'):
        dev.print()
    else:
        state = dev.get_common_state()
        for k, v in state.items():
            print(f'{k}\t{v}')


def main():
    desc = (
        f'{__file__} [Args] [Options]\n'
        '- Supports QuickSyn FSL-0010 and Valon 5015\n'
        '- Detailed options -h or --help\n'
    )
    parser = ArgumentParser(description=desc,
                            formatter_class=RawTextHelpFormatter)

    parser.add_argument('--driver',
                        type=str,
                        dest='driver',
                        default=None,
                        help='Select driver: quicksyn or valon')

    parser.add_argument('-f', '--frequency',
                        type=str,
                        dest='frequency',
                        default=None,
                        help='Frequency with unit.\nex) 650MHz, 4.5GHz\n')

    parser.add_argument('-c', '--channel',
                        type=str,
                        dest='channel',
                        default=None,
                        help=QUICKSYN_BASEDIR + '{} (QuickSyn only)')

    parser.add_argument('-s', '--serial',
                        dest='serial',
                        default=None,
                        help='Serial number')

    parser.add_argument('--path',
                        type=str,
                        dest='path',
                        default=None,
                        help='device path')

    parser.add_argument('-p', '--power',
                        type=str,
                        dest='power',
                        default=None,
                        help='Select [on] or [off] for RF output')

    parser.add_argument('--ref',
                        type=str,
                        dest='refsource',
                        default=None,
                        help='Select [ext(ernal)] or [int(ernal)]')

    parser.add_argument('--refpower',
                        type=str,
                        dest='refpower',
                        default=None,
                        help='Select [on] or [off] (QuickSyn only)')

    parser.add_argument('--power-dbm',
                        type=float,
                        dest='power_dbm',
                        default=None,
                        help='Set RF output power in dBm (Valon only)')

    parser.add_argument('-v', '--verbose',
                        action='store_true',
                        help='Verbose mode.')

    parser.add_argument('--list',
                        action='store_true',
                        help='List available devices.')

    args = parser.parse_args()

    if args.list:
        list_devices()
        sys.exit()

    if args.power:
        try:
            parse_bool_onoff(args.power)
        except ValueError:
            parser.print_help()
            sys.exit()

    if args.refpower:
        try:
            parse_bool_onoff(args.refpower)
        except ValueError:
            parser.print_help()
            sys.exit()

    dev = create_device(args)

    try:
        if args.verbose:
            print_verbose(dev)

        has_action = False

        if args.frequency:
            if args.verbose:
                print('Frequency set mode')
            if hasattr(dev, 'set_freq_str'):
                dev.set_freq_str(args.frequency)
            else:
                # Valon
                # "4.5GHz" のような文字列を最低限パース
                import re
                m = re.match(r'\s*([0-9]+(?:\.[0-9]+)?)\s*([kKmMgG]?[hH][zZ]|[kKmMgG])\s*$', args.frequency)
                if m is None:
                    raise ValueError(f'Invalid frequency string: {args.frequency}')
                val = float(m.group(1))
                unit = m.group(2).lower()
                scale = {
                    'g': 1e9, 'ghz': 1e9,
                    'm': 1e6, 'mhz': 1e6,
                    'k': 1e3, 'khz': 1e3,
                    'hz': 1.0,
                }[unit]
                dev.set_frequency_hz(val * scale)

            sleep(0.1)
            has_action = True
            if args.verbose:
                state = dev.get_common_state()
                print('Frequency set to', state['frequency_hz'] / 1e9, 'GHz')

        if args.power:
            on = parse_bool_onoff(args.power)
            if args.verbose:
                print('RF output will be set to', args.power)

            if hasattr(dev, 'set_rfout'):
                dev.set_rfout(on=on)
            else:
                dev.set_rf_output_enabled(enabled=on)

            has_action = True
            if args.verbose:
                state = dev.get_common_state()
                print('RF output set to', 'On' if state['rf_output_on'] else 'Off')

        if args.refsource:
            ref = args.refsource.strip().lower()
            if args.verbose:
                print('Ref source will be set to', args.refsource)

            if ref[:3] == 'int':
                if hasattr(dev, 'set_ref_int'):
                    dev.set_ref_int()
                else:
                    dev.set_reference_source('internal')
                has_action = True

            elif ref[:3] == 'ext':
                if hasattr(dev, 'set_ref_ext'):
                    dev.set_ref_ext()
                else:
                    dev.set_reference_source('external')
                has_action = True

            if has_action and args.verbose:
                state = dev.get_common_state()
                print('Ref source set to', state['reference_source'])

        if args.refpower:
            on = parse_bool_onoff(args.refpower)
            if hasattr(dev, 'set_refout'):
                if args.verbose:
                    print('Ref output will be set to', args.refpower)
                dev.set_refout(on=on)
                has_action = True
                if args.verbose:
                    state = dev.get_common_state()
                    print('Ref output set to', 'On' if state.get('ref_output_on', False) else 'Off')
            else:
                print('WARNING:: --refpower is supported only for QuickSyn')

        if args.power_dbm is not None:
            if hasattr(dev, 'set_power_dbm'):
                if args.verbose:
                    print('Power will be set to', args.power_dbm, 'dBm')
                dev.set_power_dbm(args.power_dbm)
                has_action = True
                if args.verbose:
                    state = dev.get_common_state()
                    print('Power set to', state.get('power_dbm'), 'dBm')
            else:
                print('WARNING:: --power-dbm is supported only for Valon')

        if (not has_action) and (not args.verbose):
            print_compact_status(dev)

    finally:
        dev.close()

if __name__ == '__main__':
    main()
