#!/usr/bin/env python3
"""
panel_bench.py — Phase 0 bench validation for the Auxbeam AC-1200 (Qunchen) BLE switch panel.

Confirms the reverse-engineered protocol in PROTOCOL.md against a REAL panel before you build
anything on top of it. Runs anywhere bleak runs — your laptop, or the van's Raspberry Pi.

    pip install bleak        # (or: pip install -r tools/requirements.txt)

Typical use, in order of increasing commitment:

    # 1) Just find the panel and see signal strength (fully passive):
    python3 tools/panel_bench.py --scan-only

    # 2) Connect, dump the GATT table, read state, and watch for notifications —
    #    including when you flip a PHYSICAL switch. Read-only; actuates nothing:
    python3 tools/panel_bench.py --address AA:BB:CC:DD:EE:FF

    # 3) Also prove a write toggles a relay. This PHYSICALLY SWITCHES a circuit,
    #    so you must name a channel you KNOW is safe to toggle (e.g. a bench LED):
    python3 tools/panel_bench.py --address AA:BB:CC:DD:EE:FF --channel 1

Safety: without --channel, the script never writes to the panel. With --channel it will toggle
that ONE circuit on then off, after a confirmation prompt (skip the prompt with --yes).

macOS note: bleak uses a system-assigned UUID instead of a MAC for --address. Use --scan-only
first to discover the identifier this machine sees, then pass that.
"""
import argparse
import asyncio
import sys

from bleak import BleakClient, BleakScanner

# --- GATT map (from PROTOCOL.md) ---------------------------------------------
SERVICE = "0000fff0-0000-1000-8000-00805f9b34fb"
FFF1 = "0000fff1-0000-1000-8000-00805f9b34fb"  # write: channel control
FFF2 = "0000fff2-0000-1000-8000-00805f9b34fb"  # read + notify: channel state
FFF4 = "0000fff4-0000-1000-8000-00805f9b34fb"  # write + notify: backlight [bright,R,G,B]
FFFA = "0000fffa-0000-1000-8000-00805f9b34fb"  # read + write: pulse timing (byte 4..50)
EXPECTED_CHARS = {FFF1: "FFF1 control", FFF2: "FFF2 state", FFF4: "FFF4 backlight", FFFA: "FFFA pulse"}

NONE_NIBBLE = 8  # "leave this channel unchanged"


# --- protocol helpers (mirror PROTOCOL.md) -----------------------------------
def build_control_frame(channel: int, on: bool, loop_count: int = 12, mode: int = 0) -> bytes:
    """[loop_count][packed nibbles], one nibble/channel. mode: 0 toggle,1 momentary,2 pulsed.
    Target channel = mode*2 + on; all other channels = 8 (no-change). Channel is 1-based."""
    if not 1 <= channel <= loop_count:
        raise ValueError(f"channel {channel} out of range 1..{loop_count}")
    nibbles = [NONE_NIBBLE] * loop_count
    nibbles[channel - 1] = mode * 2 + (1 if on else 0)
    if len(nibbles) % 2:
        nibbles.append(NONE_NIBBLE)  # pad odd loop counts
    body = bytes((nibbles[i] << 4) | nibbles[i + 1] for i in range(0, len(nibbles), 2))
    return bytes([loop_count]) + body


def describe_nibble(nib: int) -> str:
    if nib == NONE_NIBBLE:
        return "unchanged"
    mode = {0: "toggle", 1: "momentary", 2: "pulsed"}.get(nib >> 1, f"mode?{nib >> 1}")
    return f"{mode} {'ON' if nib & 1 else 'off'}"


def decode_state(data: bytes, loop_count: int = 12) -> str:
    """Decode an FFF2 payload. Detects whether it carries the leading loop-count header
    byte (the FFF1 write does; PROTOCOL.md flags the readback framing as 'verify')."""
    hexs = data.hex(" ")
    has_header = len(data) == loop_count // 2 + 1 and data[0] == loop_count
    body = data[1:] if has_header else data
    nibbles = []
    for b in body:
        nibbles.extend((b >> 4, b & 0xF))
    lines = [f"    raw = {hexs}  ({len(data)} bytes)",
             f"    leading header byte present? {'YES (0x%02X)' % data[0] if has_header else 'no'}"]
    for ch, nib in enumerate(nibbles[:loop_count], start=1):
        lines.append(f"    ch{ch:2d}: {nib:X}  {describe_nibble(nib)}")
    return "\n".join(lines)


# --- bench phases ------------------------------------------------------------
async def scan(name_filter: str, timeout: float):
    print(f"[scan] {timeout:.0f}s, matching name contains '{name_filter}' ...")
    found = await BleakScanner.discover(timeout=timeout, return_adv=True)
    hits = []
    for dev, adv in found.values():
        nm = adv.local_name or dev.name or ""
        if name_filter.lower() in nm.lower():
            hits.append((dev, adv, nm))
    if not hits:
        print(f"[scan] no device whose name contains '{name_filter}'. Seen this scan:")
        for dev, adv in sorted(found.values(), key=lambda x: -(x[1].rssi or -999))[:12]:
            print(f"        {dev.address}  rssi={adv.rssi}  name={adv.local_name or dev.name!r}")
        return None
    for dev, adv, nm in sorted(hits, key=lambda x: -(x[1].rssi or -999)):
        rssi = adv.rssi
        note = "good" if rssi and rssi > -70 else "usable" if rssi and rssi > -85 else "weak → an ESP proxy may help"
        print(f"[scan] FOUND  {dev.address}  name={nm!r}  rssi={rssi} dBm ({note})")
    return hits[0][0]


def make_notify_handler(counter: dict, loop_count: int, tag: str):
    def handler(_sender, data: bytes):
        counter["n"] += 1
        print(f"  <notify {tag}> #{counter['n']}\n{decode_state(bytes(data), loop_count)}")
    return handler


async def run(args):
    results = {}  # verify-item -> (ok, detail)

    device = None
    if args.address is None or args.scan_only:
        device = await scan(args.name, args.scan_timeout)
        results["device found"] = (device is not None, "")
        if args.scan_only or device is None:
            summary(results)
            return
    target = args.address or device

    print(f"\n[connect] {target} ...")
    async with BleakClient(target, timeout=args.connect_timeout) as client:
        connected = client.is_connected
        print(f"[connect] connected={connected}  (no pairing prompt appeared ⇒ just-works / no-PIN)")
        results["connect (no PIN)"] = (connected, "no pairing prompt = confirmed")

        # --- GATT enumeration ---
        print("\n[gatt] services / characteristics:")
        present = set()
        svc_ok = False
        for svc in client.services:
            short = svc.uuid.lower()
            is_target = short == SERVICE
            svc_ok = svc_ok or is_target
            print(f"  service {svc.uuid}{'   <-- panel service FFF0' if is_target else ''}")
            for ch in svc.characteristics:
                present.add(ch.uuid.lower())
                label = EXPECTED_CHARS.get(ch.uuid.lower(), "")
                print(f"      char {ch.uuid}  [{','.join(ch.properties)}]  {label}")
        missing = [lbl for u, lbl in EXPECTED_CHARS.items() if u not in present]
        results["service FFF0 present"] = (svc_ok, "")
        results["expected chars present"] = (not missing, f"missing: {missing}" if missing else "all four found")

        # --- subscribe FFF2 so we catch responses to our own writes AND physical changes ---
        counter = {"n": 0}
        notify_ok = False
        if FFF2 in present:
            try:
                await client.start_notify(FFF2, make_notify_handler(counter, args.loops, "FFF2"))
                notify_ok = True
                print("\n[notify] subscribed to FFF2 (state).")
            except Exception as e:  # noqa: BLE001
                print(f"[notify] subscribe FAILED: {e}")

        # --- read current state / pulse (read-only) ---
        if FFF2 in present:
            try:
                data = bytes(await client.read_gatt_char(FFF2))
                print(f"[read] FFF2 state:\n{decode_state(data, args.loops)}")
                results["FFF2 read + framing"] = (True, f"{len(data)} bytes")
            except Exception as e:  # noqa: BLE001
                print(f"[read] FFF2 read failed: {e}")
        if FFFA in present:
            try:
                p = bytes(await client.read_gatt_char(FFFA))
                print(f"[read] FFFA pulse = {p.hex(' ')}"
                      f"{'  (byte %d, expect 4..50)' % p[0] if p else ''}")
            except Exception as e:  # noqa: BLE001
                print(f"[read] FFFA read failed: {e}")

        # --- physical-switch notify test (READ-ONLY; the make-or-break question) ---
        if notify_ok and not args.no_physical:
            before = counter["n"]
            print(f"\n[physical] >>> Flip a PHYSICAL switch (or use the RF remote) in the next "
                  f"{args.watch:.0f}s. Watching FFF2 ...")
            await asyncio.sleep(args.watch)
            got = counter["n"] - before
            results["FFF2 notifies on PHYSICAL change"] = (
                got > 0, f"{got} notification(s) — {'HA state can stay in sync' if got else 'may be optimistic-only'}")
            print(f"[physical] received {got} notification(s) during the watch window.")

        # --- active control test (WRITES — only if a channel was named) ---
        if args.channel is None:
            print("\n[control] skipped (no --channel given). Re-run with --channel N to prove a write "
                  "toggles a relay. Nothing was written to the panel.")
        else:
            if not confirm_actuation(args):
                print("[control] not confirmed — skipping the write test.")
            elif FFF1 not in present:
                print("[control] FFF1 not present — cannot run write test.")
            else:
                on = build_control_frame(args.channel, True, args.loops)
                off = build_control_frame(args.channel, False, args.loops)
                print(f"[control] channel {args.channel} ON  → write FFF1 {on.hex(' ')}")
                await client.write_gatt_char(FFF1, on, response=False)
                await asyncio.sleep(args.dwell)
                print(f"[control] channel {args.channel} OFF → write FFF1 {off.hex(' ')}")
                await client.write_gatt_char(FFF1, off, response=False)
                await asyncio.sleep(1.0)
                ack = counter["n"] > 0
                results["FFF1 write accepted"] = (True, "sent (confirm the relay physically clicked)")
                results["FFF2 notifies on our write"] = (ack, f"{counter['n']} notification(s) total")

        if notify_ok:
            try:
                await client.stop_notify(FFF2)
            except Exception:  # noqa: BLE001
                pass

    summary(results)


def confirm_actuation(args) -> bool:
    if args.yes:
        return True
    print(f"\n  ⚠️  About to PHYSICALLY toggle channel {args.channel} ON then OFF.")
    print("     Make sure that circuit is SAFE to switch (not a winch/pump/anything consequential).")
    try:
        return input(f"     Type 'yes' to toggle channel {args.channel}: ").strip().lower() == "yes"
    except (EOFError, KeyboardInterrupt):
        return False


def summary(results: dict):
    print("\n" + "=" * 60 + "\n  VERIFY CHECKLIST (maps to PROTOCOL.md)\n" + "=" * 60)
    if not results:
        print("  (nothing to report)")
    for item, (ok, detail) in results.items():
        mark = "PASS" if ok else "----"
        print(f"  [{mark}] {item}" + (f"  — {detail}" if detail else ""))
    print("=" * 60)
    print("  Update PROTOCOL.md's 'verify' items with what you observed.")


def parse_args(argv):
    p = argparse.ArgumentParser(description="Bench-validate the Auxbeam/Qunchen switch panel BLE protocol.")
    p.add_argument("--address", help="Panel BLE MAC (or macOS UUID). Omit to scan by name.")
    p.add_argument("--name", default="Controller", help="Name substring to match when scanning (default: Controller)")
    p.add_argument("--loops", type=int, default=12, help="Channel count (12 for AC-1200; default 12)")
    p.add_argument("--channel", type=int, help="Channel to toggle in the WRITE test (1-based). Omit = no writes.")
    p.add_argument("--yes", action="store_true", help="Skip the actuation confirmation prompt")
    p.add_argument("--scan-only", action="store_true", help="Only scan and report; never connect")
    p.add_argument("--no-physical", action="store_true", help="Skip the physical-switch notify watch")
    p.add_argument("--watch", type=float, default=15.0, help="Seconds to watch for a physical-switch notify (default 15)")
    p.add_argument("--dwell", type=float, default=2.0, help="Seconds to leave the test channel ON (default 2)")
    p.add_argument("--scan-timeout", type=float, default=8.0, help="Scan duration (default 8s)")
    p.add_argument("--connect-timeout", type=float, default=20.0, help="Connect timeout (default 20s)")
    return p.parse_args(argv)


if __name__ == "__main__":
    try:
        asyncio.run(run(parse_args(sys.argv[1:])))
    except KeyboardInterrupt:
        print("\ninterrupted.")
    except Exception as e:  # noqa: BLE001
        print(f"\nERROR: {e}")
        sys.exit(1)
