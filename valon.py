#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import time

import serial
import serial.tools.list_ports


DEFAULT_USB_BAUDRATE = 9600
DEFAULT_TIMEOUT = 0.25

PROMPT = "-->"

# FTDI USB Serial
FTDI_VID = 0x0403
FTDI_PID = 0x6001


class ValonError(RuntimeError):
    pass


class ValonCommandError(ValonError):
    pass


class Valon5015(object):
    driver_name = 'valon'

    # confirmed from measurement
    FREQ_MIN_HZ = 10e6
    FREQ_MAX_HZ = 15e9
    POWER_MIN_DBM = -50.0
    POWER_MAX_DBM = 20.0

    def __init__(
        self,
        path,
        baudrate=DEFAULT_USB_BAUDRATE,
        timeout=DEFAULT_TIMEOUT,
        write_terminator='\r',
    ):
        self._path = path
        self._baudrate = baudrate
        self._timeout = timeout
        self._write_terminator = write_terminator
        self._ser = serial.Serial(
            port=path,
            baudrate=baudrate,
            timeout=timeout,
            write_timeout=timeout,
        )
        time.sleep(0.05)
        self._ser.reset_input_buffer()

    def close(self):
        self._ser.close()

    def _send(self, command):
        self._ser.reset_input_buffer()
        wire = command.strip() + self._write_terminator
        self._ser.write(wire.encode('utf-8'))
        self._ser.flush()
        time.sleep(0.05)

        chunks = []
        deadline = time.time() + max(self._timeout, 0.25)

        while time.time() < deadline:
            line = self._ser.readline().decode('utf-8', errors='ignore')
            if not line:
                if chunks:
                    break
                continue
            line = line.rstrip('\r\n')
            if line.strip():
                chunks.append(line)

        response = '\n'.join(chunks).strip()
        response = self._clean_response(command, response)
        self._raise_if_error_response(command, response)
        return response

    def _query(self, command):
        response = self._send(command)
        if not response:
            raise ValonError(f'no response to command: {command}')
        return response

    @staticmethod
    def _clean_response(command, response):
        """
        Remove echoed command lines and prompt lines like '-->'.
        """
        if not response:
            return response

        cmd = command.strip().lower()
        cleaned = []

        for raw_line in response.splitlines():
            line = raw_line.replace('\r', '').strip()

            if not line:
                continue

            if line.lower() == cmd:
                continue

            if line == PROMPT:
                continue

            if line.endswith(PROMPT):
                line = line[:-len(PROMPT)].rstrip()
                if not line:
                    continue

            cleaned.append(line)

        return '\n'.join(cleaned).strip()

    @staticmethod
    def _raise_if_error_response(command, response):
        if not response:
            return
        lowered = response.lower()
        if (
            'illegal command' in lowered
            or 'command error' in lowered
            or 'illegal parameter' in lowered
        ):
            raise ValonCommandError(
                f'command failed: {command!r}, response={response!r}'
            )

    # ------------------------------------------------------------------
    # Identification / status
    # ------------------------------------------------------------------

    def get_id_raw(self):
        return self._query('ID?')

    def get_id(self):
        return self._parse_id(self.get_id_raw())

    def identify(self):
        info = {}
        try:
            info = self.get_id()
        except Exception:
            info = {}

        model = info.get('model')
        serial_number = info.get('serial_number')
        hardware_revision = info.get('hardware_revision')
        firmware_version = info.get('firmware_version')
        build = info.get('build')
        changeset = info.get('changeset')

        if (
            model is None
            or serial_number is None
            or hardware_revision is None
            or firmware_version is None
            or build is None
        ):
            try:
                status = self.get_status()
                model = model or status.get('model')
                serial_number = serial_number or status.get('serial_number')
                hardware_revision = (
                    hardware_revision or status.get('hardware_revision')
                )
                firmware_version = (
                    firmware_version or status.get('firmware_version')
                )
                build = build or status.get('build')
            except Exception:
                pass

        return {
            'driver': self.driver_name,
            'model': model or '5015',
            'serial_number': serial_number,
            'hardware_revision': hardware_revision,
            'firmware_version': firmware_version,
            'build': build,
            'changeset': changeset,
            'path': self._path,
        }

    def get_status_raw(self):
        return self._query('STATUS?')

    def get_status(self):
        return self._parse_status(self.get_status_raw())

    def get_lock_status_raw(self):
        return self._query('LOCK?')

    def get_lock_status(self):
        return self._parse_lock_status(self.get_lock_status_raw())

    def is_locked(self):
        status = self.get_lock_status()
        if not status:
            return False
        return all(v == 'locked' for v in status.values())

    # ------------------------------------------------------------------
    # Frequency
    # ------------------------------------------------------------------

    def get_frequency_raw(self):
        return self._query('FREQ?')

    def get_frequency_hz(self):
        return self._parse_frequency_to_hz(self.get_frequency_raw())

    def set_frequency_hz(self, frequency_hz):
        frequency_hz = float(frequency_hz)
        if frequency_hz < self.FREQ_MIN_HZ or frequency_hz > self.FREQ_MAX_HZ:
            raise ValueError(
                'frequency must be between '
                f'{self.FREQ_MIN_HZ:g} and {self.FREQ_MAX_HZ:g} Hz'
            )
        self._send(self._format_frequency_command(frequency_hz))

    # ------------------------------------------------------------------
    # RF output
    # ------------------------------------------------------------------

    def get_rf_output_raw(self):
        return self._query('OEN?')

    def get_rf_output_enabled(self):
        return self._parse_oen(self.get_rf_output_raw())

    def set_rf_output_enabled(self, enabled=True):
        if not isinstance(enabled, bool):
            raise ValueError('enabled must be bool')
        self._send(f'OEN {1 if enabled else 0}')

    # ------------------------------------------------------------------
    # Power
    # ------------------------------------------------------------------

    def get_power_raw(self):
        return self._query('POWER?')

    def get_power_dbm(self):
        return self._parse_power_dbm(self.get_power_raw())

    def set_power_dbm(self, power_dbm):
        power_dbm = float(power_dbm)
        if power_dbm < self.POWER_MIN_DBM or power_dbm > self.POWER_MAX_DBM:
            raise ValueError(
                'power must be between '
                f'{self.POWER_MIN_DBM:g} and {self.POWER_MAX_DBM:g} dBm'
            )
        self._send(f'POWER {power_dbm:.2f}')

    # ------------------------------------------------------------------
    # Reference
    # ------------------------------------------------------------------

    def get_reference_source_raw(self):
        return self._query('REFS?')

    def get_reference_source(self):
        return self._parse_reference_source(self.get_reference_source_raw())

    def set_reference_source(self, source):
        source = source.strip().lower()
        if source.startswith('int'):
            self._send('REFS 0')
        elif source.startswith('ext'):
            self._send('REFS 1')
        else:
            raise ValueError(
                'reference source must be internal/int or external/ext'
            )

    def get_reference_raw(self):
        return self._query('REF?')

    def get_reference_hz(self):
        return self._parse_reference_hz(self.get_reference_raw())

    def set_reference_hz(self, reference_hz):
        reference_hz = float(reference_hz)
        if reference_hz <= 0:
            raise ValueError('reference frequency must be positive')
        self._send(self._format_reference_command(reference_hz))

    # ------------------------------------------------------------------
    # Common state
    # ------------------------------------------------------------------

    def get_common_state(self):
        info = self.identify()
        status = self.get_status()
        lock_status = self.get_lock_status()

        return {
            'driver': self.driver_name,
            'model': info.get('model', '5015'),
            'serial_number': info.get('serial_number'),
            'hardware_revision': info.get('hardware_revision'),
            'firmware_version': info.get('firmware_version'),
            'build': info.get('build'),
            'changeset': info.get('changeset'),
            'path': self._path,
            'frequency_hz': self.get_frequency_hz(),
            'rf_output_on': self.get_rf_output_enabled(),
            'reference_source': self.get_reference_source(),
            'reference_hz': self.get_reference_hz(),
            'power_dbm': self.get_power_dbm(),
            'status': status,
            'lock_status': lock_status,
            'locked': self.is_locked(),
        }

    def print(self):
        info = self.identify()
        print('Model #\t\t', info.get('model'))
        print('Serial #\t', info.get('serial_number'))
        print('HW rev\t\t', info.get('hardware_revision'))
        print('FW ver\t\t', info.get('firmware_version'))
        print('Build\t\t', info.get('build'))
        if info.get('changeset'):
            print('Changeset\t', info.get('changeset'))
        print('Dev path\t', self._path)
        print()

        print('RF output\t', 'On' if self.get_rf_output_enabled() else 'Off')
        print('Ref source\t', self.get_reference_source())
        print('Ref freq\t', self.get_reference_hz() / 1e6, 'MHz')
        print('Power\t\t', self.get_power_dbm(), 'dBm')

        lock_status = self.get_lock_status()
        print('Lock')
        for k, v in lock_status.items():
            print(f'  {k}\t{v}')

        status = self.get_status()
        print('Status')
        if 'temperature_c' in status:
            print('  Temp\t\t', status['temperature_c'], 'C')
        if 'battery_voltage_v' in status:
            print('  VBAT\t\t', status['battery_voltage_v'], 'V')
        if 'battery_current_a' in status:
            print('  IBAT\t\t', status['battery_current_a'], 'A')
        if 'battery_power_w' in status:
            print('  Power\t\t', status['battery_power_w'], 'W')
        if 'plus_5v_v' in status:
            print('  +5V\t\t', status['plus_5v_v'], 'V')
        if 'minus_5v_v' in status:
            print('  -5V\t\t', status['minus_5v_v'], 'V')
        if 'plus_3p3vrf_v' in status:
            print('  +3.3VRF\t', status['plus_3p3vrf_v'], 'V')
        if 'plus_3p3v_v' in status:
            print('  +3.3V\t\t', status['plus_3p3v_v'], 'V')
        if 'up_clock_mhz' in status:
            print('  uP clock\t', status['up_clock_mhz'], 'MHz')
        if 'flash_size' in status:
            print('  FLASH\t\t', status['flash_size'])
        if 'max_freq_hz' in status:
            print('  Max freq\t', status['max_freq_hz'] / 1e9, 'GHz')

        print()
        print('Current freq.\t', self.get_frequency_hz() / 1e9, 'GHz')

    # ------------------------------------------------------------------
    # Parsers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_header_info(header):
        """
        Example:
            Valon Technology, 5015, 12204468, R7  version 2.0l
            Build: Sep 15 2025  02:51:54
        """
        result = {}

        if not header:
            return result

        parts = [p.strip() for p in header.split(',')]

        if len(parts) >= 2 and re.fullmatch(r'\d+', parts[1]):
            result['model'] = parts[1]

        if len(parts) >= 3:
            serial_match = re.search(r'(\d+)', parts[2])
            if serial_match:
                result['serial_number'] = serial_match.group(1)

        rev_match = re.search(r'\b(R[0-9A-Za-z]+)\b', header)
        if rev_match:
            result['hardware_revision'] = rev_match.group(1)

        fw_match = re.search(
            r'\bversion\s+(.+?)(?=\s+Build:|$)',
            header,
            re.I,
        )
        if fw_match:
            result['firmware_version'] = fw_match.group(1).strip()

        build_match = re.search(r'\bBuild:\s+(.+)$', header, re.I)
        if build_match:
            result['build'] = build_match.group(1).strip()

        return result

    @staticmethod
    def _parse_id(raw):
        result = {'raw': raw}

        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if not lines:
            return result

        header = lines[0]
        result['header'] = header
        result.update(Valon5015._parse_header_info(header))

        for line in lines[1:]:
            if line.lower().startswith('changeset'):
                result['changeset'] = line

        return result

    @staticmethod
    def _parse_status(raw):
        result = {
            'raw': raw,
            'header': None,
        }

        lines = [line.rstrip() for line in raw.splitlines() if line.strip()]
        if not lines:
            return result

        header = lines[0].strip()
        result['header'] = header
        result.update(Valon5015._parse_header_info(header))

        for line in lines[1:]:
            s = line.strip()

            m = re.match(
                r'^VBAT\s*=\s*(\d+)\s+([-+]?\d+(?:\.\d+)?)\s*V$',
                s,
                re.I,
            )
            if m:
                result['vbat_adc'] = int(m.group(1))
                result['battery_voltage_v'] = float(m.group(2))
                continue

            m = re.match(
                r'^IBAT\s*=\s*(\d+)\s+([-+]?\d+(?:\.\d+)?)\s*Amps?\s+'
                r'([-+]?\d+(?:\.\d+)?)\s*Watts?$',
                s,
                re.I,
            )
            if m:
                result['ibat_adc'] = int(m.group(1))
                result['battery_current_a'] = float(m.group(2))
                result['battery_power_w'] = float(m.group(3))
                continue

            m = re.match(
                r'^UPTS\s*=\s*(\d+)\s+([-+]?\d+(?:\.\d+)?)\s*C$',
                s,
                re.I,
            )
            if m:
                result['upts_adc'] = int(m.group(1))
                result['temperature_c'] = float(m.group(2))
                continue

            m = re.match(
                r'^([+-]?\d+(?:\.\d+)?V(?:RF)?)\s*=\s*(\d+)\s+'
                r'([-+]?\d+(?:\.\d+)?)\s*V$',
                s,
                re.I,
            )
            if m:
                rail_name = (
                    m.group(1)
                    .replace('.', 'p')
                    .replace('+', 'plus_')
                    .replace('-', 'minus_')
                    .lower()
                )
                result[f'{rail_name}_adc'] = int(m.group(2))
                result[f'{rail_name}_v'] = float(m.group(3))
                continue

            m = re.match(r'^LM\s*=\s*(\d+)\s+([01]+)$', s, re.I)
            if m:
                result['lm_decimal'] = int(m.group(1))
                result['lm_bits'] = m.group(2)
                continue

            m = re.match(r'^uP clock\s*=\s*(\d+)\s*MHz$', s, re.I)
            if m:
                result['up_clock_mhz'] = int(m.group(1))
                continue

            m = re.match(r'^UID\s*=\s*(.+)$', s, re.I)
            if m:
                result['uid'] = m.group(1).strip()
                continue

            m = re.match(r'^FLASH size\s*=\s*(.+)$', s, re.I)
            if m:
                result['flash_size'] = m.group(1).strip()
                continue

            m = re.match(
                r'^Max freq\s*=\s*([-+]?\d+(?:\.\d+)?)\s*'
                r'([kmg]?)(?:hz)?$',
                s,
                re.I,
            )
            if m:
                result['max_freq_hz'] = Valon5015._scale_by_unit(
                    float(m.group(1)),
                    m.group(2),
                )
                continue

            result.setdefault('unparsed_lines', []).append(s)

        return result

    @staticmethod
    def _parse_lock_status(raw):
        """
        Example:
            SUB1       : not locked
            SUB2       :     locked
            MAIN SYNTH :     locked
        """
        result = {}

        for line in raw.splitlines():
            line = line.strip()
            if not line or ':' not in line:
                continue

            key, value = line.split(':', 1)
            key = key.strip()
            value = re.sub(r'\s+', ' ', value.strip().lower())
            result[key] = value

        return result

    @staticmethod
    def _parse_frequency_to_hz(raw):
        """
        Example:
            F 8000 MHz; // Act 8000 MHz
            F 7999.5 MHz; // Act 7999.5 MHz
        """
        m = re.search(
            r'Act\s+([-+]?\d+(?:\.\d+)?)\s*([kmg]?)(?:hz)?',
            raw,
            re.I,
        )
        if not m:
            m = re.search(
                r'F\s+([-+]?\d+(?:\.\d+)?)\s*([kmg]?)(?:hz)?',
                raw,
                re.I,
            )
        if not m:
            m = re.search(
                r'([-+]?\d+(?:\.\d+)?)\s*([kmg]?)(?:hz)?',
                raw,
                re.I,
            )
        if not m:
            raise ValonError(
                f'could not parse frequency response: {raw!r}'
            )

        return Valon5015._scale_by_unit(float(m.group(1)), m.group(2))

    @staticmethod
    def _parse_power_dbm(raw):
        """
        Example:
            PWR 18.00; // dBm
        """
        m = re.search(r'PWR\s+([-+]?\d+(?:\.\d+)?)', raw, re.I)
        if not m:
            m = re.search(r'([-+]?\d+(?:\.\d+)?)', raw)
        if not m:
            raise ValonError(f'could not parse power response: {raw!r}')
        return float(m.group(1))

    @staticmethod
    def _parse_oen(raw):
        """
        Example:
            OEN 0;
            OEN 1;
        """
        m = re.search(r'OEN\s+([01])', raw, re.I)
        if not m:
            m = re.search(r'\b([01])\b', raw)
        if not m:
            raise ValonError(f'could not parse OEN response: {raw!r}')
        return m.group(1) == '1'

    @staticmethod
    def _parse_reference_source(raw):
        """
        Example:
            REFS 0;
            REFS 1;
        """
        m = re.search(r'REFS\s+([01])', raw, re.I)
        if not m:
            m = re.search(r'\b([01])\b', raw)
        if not m:
            raise ValonError(f'could not parse REFS response: {raw!r}')
        return 'external' if m.group(1) == '1' else 'internal'

    @staticmethod
    def _parse_reference_hz(raw):
        """
        Example:
            REF 10 MHz;
        """
        m = re.search(
            r'REF\s+([-+]?\d+(?:\.\d+)?)\s*([kmg]?)(?:hz)?',
            raw,
            re.I,
        )
        if not m:
            m = re.search(
                r'([-+]?\d+(?:\.\d+)?)\s*([kmg]?)(?:hz)?',
                raw,
                re.I,
            )
        if not m:
            raise ValonError(f'could not parse REF response: {raw!r}')
        return Valon5015._scale_by_unit(float(m.group(1)), m.group(2))

    @staticmethod
    def _scale_by_unit(value, unit):
        unit = (unit or '').lower()
        scale = {
            '': 1.0,
            'k': 1e3,
            'm': 1e6,
            'g': 1e9,
        }[unit]
        return value * scale

    @staticmethod
    def _format_frequency_command(frequency_hz):
        if frequency_hz >= 1e9:
            return f'FREQ {frequency_hz / 1e9:.9f} GHz'
        if frequency_hz >= 1e6:
            return f'FREQ {frequency_hz / 1e6:.6f} MHz'
        if frequency_hz >= 1e3:
            return f'FREQ {frequency_hz / 1e3:.3f} kHz'
        return f'FREQ {frequency_hz:.0f} Hz'

    @staticmethod
    def _format_reference_command(reference_hz):
        if reference_hz >= 1e9:
            return f'REF {reference_hz / 1e9:.9f} GHz'
        if reference_hz >= 1e6:
            return f'REF {reference_hz / 1e6:.6f} MHz'
        if reference_hz >= 1e3:
            return f'REF {reference_hz / 1e3:.3f} kHz'
        return f'REF {reference_hz:.0f} Hz'


def _is_valon_port(port):
    desc = (port.description or '').lower()

    if port.vid == FTDI_VID and port.pid == FTDI_PID:
        return True
    if 'valon' in desc:
        return True
    if 'usb uart' in desc:
        return True
    return False


def _score_port(port):
    score = 0
    device = port.device or ''
    serial_number = port.serial_number or ''

    if device.startswith('/dev/cu.'):
        score += 100
    elif device.startswith('/dev/tty.'):
        score += 50

    if serial_number and serial_number in device:
        score += 30

    score += len(device) * 0.01
    return score


def list_candidate_ports():
    best_by_key = {}

    for port in serial.tools.list_ports.comports():
        if not _is_valon_port(port):
            continue

        dedup_key = port.serial_number or port.location or port.device
        current_score = _score_port(port)

        if dedup_key not in best_by_key:
            best_by_key[dedup_key] = port
            continue

        prev_port = best_by_key[dedup_key]
        prev_score = _score_port(prev_port)

        if current_score > prev_score:
            best_by_key[dedup_key] = port

    result = []
    for port in best_by_key.values():
        result.append({
            'device': port.device,
            'serial_number': port.serial_number,
            'description': port.description,
            'hwid': port.hwid,
            'vid': port.vid,
            'pid': port.pid,
            'location': port.location,
        })

    result.sort(
        key=lambda x: (
            x['serial_number'] is None,
            '' if x['serial_number'] is None else str(x['serial_number']),
            x['device'],
        )
    )
    return result


def iter_candidate_ports():
    for info in list_candidate_ports():
        yield info['device']


def path_fromserial(
    serialnum=None,
    showlist=False,
    baudrate=DEFAULT_USB_BAUDRATE,
    timeout=DEFAULT_TIMEOUT,
):
    del baudrate, timeout  # kept for API compatibility

    ports = list_candidate_ports()

    if showlist:
        lines = []
        for info in ports:
            lines.append(
                f"{info['device']}: {info['serial_number']} "
                f"(desc: {info['description']})"
            )
        return '\n'.join(lines)

    if serialnum is not None:
        for info in ports:
            if str(info['serial_number']) == str(serialnum):
                return info['device']
        return None

    if ports:
        return ports[0]['device']

    return None
