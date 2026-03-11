sg_manager
====
Python scripts to control synthesizer for both Quicksyn FSL-0010 and Valon 5015.
GroundBIRD uses both synthesizers to control the readout system interchangably, so these scripts are designed to be compatible with both devices.

## Description

- written for `python >=3.6`

## `sg_manager.py`

- `sg_manager.py` manages on-off and frequency of synthesizer
- module dependency

## `sg_sweep.py`

- `sg_sweep.py` changes frequency with input sequence
- this feature is used with `rhea_comm` module for fast resonance scan

## Usage

- Specify device channel number, serial number, or path name for your quicksyn.
- For using device channel number, device path name will be changed by OS as below (`{}` is channel number to be specified).
  - Linux: BASEDIR = `/dev/ttyACM{}`
  - MACOS: BASEDIR = `/dev/tty.usbmodem{}`
  - Java: NOT SUPPORTED
  - Windows: BASEDIR = `COM{}`
    - Linux on windows: BASEDIR = `/dev/ttyS{}`
- All serial numbers and device paths of valon and quicsyn devices connected to this server will be listed by `sg_manager.py --list`.
