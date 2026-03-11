#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import sys
import time

import serial
from tqdm import tqdm


DEFAULT_BAUDRATE = 9600
DEFAULT_TIMEOUT = 0.3
DEFAULT_COMMAND_WAIT = 0.05
DEFAULT_RESPONSE_TIMEOUT = 5.0
PROMPT = "-->"


def normalize_newlines(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def clean_response_text(command, text):
    """
    Remove echoed command line and trailing prompt line from the captured text.
    """
    text = normalize_newlines(text).strip()
    if not text:
        return ""

    cmd = command.strip().lower()
    lines = [line.strip() for line in text.split("\n") if line.strip()]

    cleaned = []
    for line in lines:
        lowered = line.lower()

        # echoed command
        if lowered == cmd:
            continue

        # prompt only
        if line == PROMPT:
            continue

        # prompt attached at line tail
        if line.endswith(PROMPT):
            line = line[:-len(PROMPT)].rstrip()
            if not line:
                continue

        cleaned.append(line)

    return "\n".join(cleaned).strip()


def read_until_prompt(ser, response_timeout=DEFAULT_RESPONSE_TIMEOUT, prompt=PROMPT):
    """
    Read from serial until the Valon prompt appears, or until response_timeout.
    """
    deadline = time.time() + response_timeout
    chunks = []

    while time.time() < deadline:
        waiting = ser.in_waiting
        if waiting:
            data = ser.read(waiting).decode("utf-8", errors="ignore")
            if data:
                chunks.append(data)
                joined = "".join(chunks)
                if prompt in joined:
                    return joined

        # fall back to line read in case in_waiting stays zero oddly
        line = ser.readline().decode("utf-8", errors="ignore")
        if line:
            chunks.append(line)
            joined = "".join(chunks)
            if prompt in joined:
                return joined
        else:
            time.sleep(0.02)

    return "".join(chunks)


def transact(ser, command, wait=DEFAULT_COMMAND_WAIT, response_timeout=DEFAULT_RESPONSE_TIMEOUT):
    """
    Send one command and collect the multiline response until '-->' prompt.
    Returns the cleaned response string.
    """
    ser.reset_input_buffer()
    ser.write((command.strip() + "\r").encode("utf-8"))
    ser.flush()

    time.sleep(wait)

    raw = read_until_prompt(ser, response_timeout=response_timeout, prompt=PROMPT)
    return clean_response_text(command, raw)


def run_sequence(ser, commands, wait=DEFAULT_COMMAND_WAIT, response_timeout=DEFAULT_RESPONSE_TIMEOUT,
                 stream=sys.stdout, show_progress=True):
    iterable = commands
    if show_progress:
        iterable = tqdm(commands, desc="Running Valon tests", unit="cmd")

    for cmd in iterable:
        if not cmd.strip():
            continue
        if cmd.lstrip().startswith("#"):
            continue

        print(f"--> {cmd}", file=stream)

        response = transact(
            ser,
            cmd,
            wait=wait,
            response_timeout=response_timeout,
        )

        if response:
            print(response, file=stream)
        else:
            print("(no response)", file=stream)

        print(file=stream)
        stream.flush()


def default_commands():
    return [
        # Identification / status
        "ID?",
        "STATUS?",
        "HELP",

        # Basic state
        "FREQ?",
        "OEN?",
        "POWER?",
        "REFS?",
        "REF?",
        "LOCK?",

        # Frequency tests
        "FREQ 10 MHz",
        "FREQ?",
        "FREQ 8000 MHz",
        "FREQ?",
        "FREQ 8 GHz",
        "FREQ?",
        "FREQ 7999.5 MHz",
        "FREQ?",
        "FREQ 15000 MHz",
        "FREQ?",
        "FREQ 15000.1 MHz",
        "FREQ?",

        # RF output / power
        "OEN OFF",
        "OEN?",
        "POWER?",
        "POWER 0",
        "POWER?",
        "POWER -4",
        "POWER?",
        "POWER 5",
        "POWER?",
        "OEN ON",
        "OEN?",
        "POWER?",

        # Reference source / lock
        "REFS 0",
        "REFS?",
        "LOCK?",
        "REFS 1",
        "REFS?",
        "LOCK?",
        "REFS 0",
        "REFS?",
        "LOCK?",

        # Reference frequency
        "REF 10 MHz",
        "REF?",
        "REF 10000000 Hz",
        "REF?",
        "REF 20 MHz",
        "REF?",

        # Error behavior
        "FREQ banana",
        "POWER banana",
        "POWER 100",
        "REFS 2",
        "OEN 2",
        "LOCKED?",
    ]


def safe_commands():
    return [
        "ID?",
        "STATUS?",
        "HELP",
        "FREQ?",
        "OEN?",
        "POWER?",
        "REFS?",
        "REF?",
        "LOCK?",
    ]


def load_commands_from_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return [line.rstrip("\n") for line in f]


def main():
    parser = argparse.ArgumentParser(description="Probe Valon serial responses.")
    parser.add_argument("port", help="serial port (e.g. /dev/cu.usbserial-12204468)")
    parser.add_argument("--baudrate", type=int, default=DEFAULT_BAUDRATE)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT,
                        help="serial read timeout for pyserial")
    parser.add_argument("--wait", type=float, default=DEFAULT_COMMAND_WAIT,
                        help="small delay after write")
    parser.add_argument("--response-timeout", type=float, default=DEFAULT_RESPONSE_TIMEOUT,
                        help="max time to wait for '-->' prompt")
    parser.add_argument("--commands-file", type=str, default=None,
                        help="text file with commands, one per line")
    parser.add_argument("--output", type=str, default=None,
                        help="save transcript to file")
    parser.add_argument("--safe", action="store_true",
                        help="run only safe query commands")
    parser.add_argument("--no-progress", action="store_true",
                        help="disable tqdm progress bar")

    args = parser.parse_args()

    if args.safe:
        commands = safe_commands()
    elif args.commands_file:
        commands = load_commands_from_file(args.commands_file)
    else:
        commands = default_commands()

    out_fp = None
    stream = sys.stdout
    try:
        if args.output:
            out_fp = open(args.output, "w", encoding="utf-8")
            stream = out_fp

        print(f"# Port: {args.port}", file=stream)
        print(f"# Baudrate: {args.baudrate}", file=stream)
        print(f"# Serial timeout: {args.timeout}", file=stream)
        print(f"# Response timeout: {args.response_timeout}", file=stream)
        print(file=stream)
        stream.flush()

        with serial.Serial(
            port=args.port,
            baudrate=args.baudrate,
            timeout=args.timeout,
            write_timeout=args.timeout,
        ) as ser:
            time.sleep(0.1)
            ser.reset_input_buffer()

            # Drain any stale startup prompt/output
            stale = read_until_prompt(ser, response_timeout=0.2, prompt=PROMPT)
            if stale:
                stale = clean_response_text("", stale)
                if stale:
                    print("# Stale startup output:", file=stream)
                    print(stale, file=stream)
                    print(file=stream)

            run_sequence(
                ser,
                commands,
                wait=args.wait,
                response_timeout=args.response_timeout,
                stream=stream,
                show_progress=(not args.no_progress),
            )

    finally:
        if out_fp is not None:
            out_fp.close()


if __name__ == "__main__":
    main()
