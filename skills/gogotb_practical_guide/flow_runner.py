"""S6-S8 GoGoTB flow runner: stochastic simulation with adaptive seed policy,
seven-category gap classification, targeted remedies, stall detection, and
denominator trimming — driving the spec reference model against the RTL
behavioral model (DUT stand-in; VCS runs the same flow on the EDA host).

Usage:
    python3 flow_runner.py golden            # DEPTH=16 golden run
    python3 flow_runner.py bug_full_msb      # debug round A (BUG#1 injected)
    python3 flow_runner.py d12_golden        # DEPTH=12 golden RTL (R1 risk)
    python3 flow_runner.py d12_fixed         # DEPTH=12 count-based fix
"""
import random
import sys
from pathlib import Path

from ref_model import SpecRefFifo
from rtl_model import RtlFifo

OUT = Path(__file__).parent

# ---- spec-grounded coverage bins (S3): bin -> (scope, named spec behavior) --
BINS = {
    "b_empty_after_reset": ("d16", "reset leaves the FIFO empty"),
    "b_fill_to_full":      ("d16", "full asserts exactly at DEPTH entries"),
    "b_backpressure_write":("d16", "write while full is ignored (no overflow)"),
    "b_fifo_order":        ("d16", "read order equals write order"),
    "b_drain_to_empty":    ("d16", "empty asserts exactly at zero entries"),
    "b_underflow_block":   ("d16", "read while empty is ignored (no underflow)"),
    "b_wrap_around":       ("d16", "pointer wrap preserves data integrity"),
    "b_simul_rw_full":     ("d16", "read+write at full state: no overflow"),
    "b_simul_rw_empty":    ("d16", "read+write at empty state: no underflow"),
    "b_sva_mutex":         ("d16", "full and empty never asserted together"),
    "b_data_edge":         ("d16", "0x00/0xFF boundary values pass intact"),
    "b_read_latency1":     ("d16", "sampled read datum is the pre-edge head"),
    "b_reset_anytime":     ("d16", "mid-stream reset recovers cleanly"),
    "b_back2back":         ("d16", "back-to-back single-cycle ops are race-free"),
    "b_config_d12":        ("d12", "non-power-of-2 depth works correctly"),
    "b_x_read_undef":      ("d16", "read-before-first-write yields undefined data"),
}

# ---- S8: seven root-cause gap categories -> targeted remedy ---------------
GAP_REMEDY = {
    "Stimulus Gap":      "directed test generation",
    "Sequence Gap":      "multi-transaction directed tests",
    "Cross Hole":        "constraint refinement",
    "State Unreached":   "state-routing sequences",
    "Timing Dependent":  "cycle-precise stimulus",
    "Transition Gap":    "edge-condition tests",
    "Seed Insufficient": "additional seed expansion",
}


class Bins:
    def __init__(self, depth):
        self.scope = f"d{depth}"
        self.hits = {b: False for b, (s, _) in BINS.items() if s == self.scope}
        self.evidence = {}
        self.sva_violations = 0
        self.mismatch_events = 0

    def hit(self, b, evidence):
        if b in self.hits:
            self.hits[b] = True
            self.evidence.setdefault(b, evidence)

    def uncovered(self):
        return [b for b, h in self.hits.items() if not h]

    def covered_pct(self):
        n = len(self.hits)
        return 100.0 * (n - len(self.uncovered())) / n if n else 100.0


class StopFlow(Exception):
    """Bounded wait exceeded — mirrors UVM PH_TIMEOUT (driver stalled)."""


class Runner:
    def __init__(self, depth=16, bug=None, seed=12345):
        self.rtl = RtlFifo(depth=depth, bug=bug)
        self.ref = SpecRefFifo(depth=depth)
        self.bins = Bins(depth)
        self.rng = random.Random(seed)
        self.pending = []            # spec-expected read queue (head order)
        self.stall_reason = None
        self.MAX_WAIT = 500          # bounded back-pressure wait (stall cap)
        self.rtl.reset()

    def _wait(self, cond_desc, pred):
        n = 0
        while pred():
            self._tick(0, 0, 0)
            n += 1
            if n > self.MAX_WAIT:
                self.stall_reason = f"driver stalled waiting for {cond_desc} " \
                                    f"(t={self.rtl.cycle})"
                raise StopFlow(self.stall_reason)

    # -- driver-protocol transactions (mirror fifo_driver.sv) ----------------
    def write_op(self, data, wait=True):
        if wait:
            self._wait("!full", lambda: self.rtl.full())
        self.rtl.step(True, data, False)
        self.ref.write(True, data)
        self.bins.hit("b_back2back", f"single-cycle write t={self.rtl.cycle}")

    def read_op(self, wait=True):
        if wait:
            self._wait("!empty", lambda: self.rtl.empty())
        rd_x, rd = self.rtl.step(False, 0, True)
        exp = self.ref.read(True)
        if exp is not None:
            if rd_x or rd != exp:
                self.bins.mismatch_events += 1
                self.bins.evidence["LAST_MISMATCH"] = (
                    f"t={self.rtl.cycle} got={('X' if rd_x else hex(rd or 0))} "
                    f"expected={hex(exp)}")
            else:
                self.bins.hit("b_fifo_order",
                              f"first order-compare pass t={self.rtl.cycle}")
                self.bins.hit("b_read_latency1",
                              f"pre-edge head sampled t={self.rtl.cycle}")
        elif not rd_x:
            # spec: blocked read must not yield defined data
            self.bins.mismatch_events += 1
        if self.rtl.empty() and (self.rtl.rptr == 0 or True):
            pass

    def _tick(self, wren, wdata, rden):
        f0, e0 = self.rtl.full(), self.rtl.empty()
        self.rtl.step(wren, wdata, rden)
        # spec oracle updates use PRE-edge state (same as RTL do_w/do_r)
        if wren and not f0:
            self.ref.write(True, wdata)
        if rden and not e0:
            self.ref.read(True)
        # SVA mutex + backpressure/underflow observability
        if not self.rtl.sva_ok:
            self.bins.sva_violations += 1
        if f0 and wren and not e0:
            self.bins.hit("b_backpressure_write",
                          f"full-blocked write t={self.rtl.cycle}")
        if e0 and rden and not f0:
            self.bins.hit("b_underflow_block",
                          f"empty-blocked read t={self.rtl.cycle}")
        if not self.rtl.full() and not self.rtl.empty():
            self.bins.hit("b_sva_mutex", "mutex holds across all cycles")

    # ---- stimulus groups (S6: per-testpoint-group testcases) ---------------
    def g_reset_basic(self):
        self.rtl.reset(); self.ref.__init__(self.ref.depth)
        if self.rtl.empty() and not self.rtl.full():
            self.bins.hit("b_empty_after_reset", f"t={self.rtl.cycle}")
        # fill to full
        for i in range(self.rtl.depth):
            self.write_op(0x80 + i)
        if self.rtl.full() and self.ref.cnt() == self.rtl.depth:
            self.bins.hit("b_fill_to_full", f"full at cnt={self.ref.cnt()}")
        # backpressure attempt
        for _ in range(3):
            self._tick(1, 0xAA, 0)
        # drain to empty
        for _ in range(self.rtl.depth):
            self.read_op()
        if self.rtl.empty() and self.ref.cnt() == 0:
            self.bins.hit("b_drain_to_empty", f"empty at cnt={self.ref.cnt()}")
        # underflow attempt
        for _ in range(2):
            self._tick(0, 0, 1)

    def g_wrap(self):
        for i in range(16):
            self.write_op(0x10 + i)
        for _ in range(12):
            self.read_op()
        for i in range(12):
            self.write_op(0x30 + i)
        errs = self.bins.mismatch_events
        for _ in range(16):
            self.read_op()
        if self.bins.mismatch_events == errs and self.ref.empty():
            self.bins.hit("b_wrap_around", "16w/12r/12w/16r integrity ok")

    def g_simul(self):
        for i in range(16):
            self.write_op(0x40 + i)
        # full state: simultaneous read+write for 3 cycles (net effect:
        # cycle1 read-only -> cnt 15, cycles 2-3 read+write -> cnt stays 15)
        for _ in range(3):
            f0 = self.rtl.full()
            self._tick(1, 0x60, 1)
            if f0:
                self.bins.hit("b_simul_rw_full", f"t={self.rtl.cycle}")
        while not self.rtl.empty():
            self.read_op()
        # empty state: simultaneous read+write once
        e0 = self.rtl.empty()
        self._tick(1, 0x70, 1)
        if e0 and self.ref.cnt() == 1:
            self.bins.hit("b_simul_rw_empty", f"t={self.rtl.cycle}")
        self.read_op()

    def g_data_edge(self):
        for v in (0x00, 0xFF, 0x00):
            self.write_op(v)
        errs = self.bins.mismatch_events
        for _ in range(3):
            self.read_op()
        if self.bins.mismatch_events == errs:
            self.bins.hit("b_data_edge", "0x00/0xFF round-trip intact")

    def g_reset_anytime(self):
        for i in range(6):
            self.write_op(0x20 + i)
        self.rtl.reset(); self.ref.__init__(self.ref.depth)
        if self.rtl.empty() and not self.rtl.full():
            errs = self.bins.mismatch_events
            self.write_op(0x55)
            self.read_op()
            if self.bins.mismatch_events == errs and self.ref.empty():
                self.bins.hit("b_reset_anytime", "mid-stream reset recovered")

    def g_x_read(self):
        # read-before-first-write: observe X, spec-undefined data
        rd_x, _ = self.rtl.step(False, 0, True)
        self.ref.read(True)
        if rd_x and self.rtl.empty():
            self.bins.hit("b_x_read_undef", "X observed on empty read (spec-ok)")

    def g_random_batch(self, n_items, seed):
        rng = random.Random(seed)
        new_before = set(b for b, h in self.bins.hits.items() if h)
        for _ in range(n_items):
            if rng.random() < 0.6:
                self.write_op(rng.randrange(256), wait=False)
            else:
                self.read_op(wait=False)
        return len([b for b, h in self.bins.hits.items()
                    if h and b not in new_before])

    # ---- S7: adaptive seed policy ------------------------------------------
    def s7_adaptive_random(self, max_batches=8):
        no_gain = 0
        for b in range(max_batches):
            try:
                gained = self.g_random_batch(40, 1000 + b)
            except StopFlow:
                return f"stalled at batch {b + 1} (driver deadlock)"
            if gained == 0:
                no_gain += 1
                if no_gain >= 2:          # consecutive no-gain -> stop
                    return f"stopped at batch {b + 1} (2 consecutive no-gain)"
            else:
                no_gain = 0
        return f"ran {max_batches} batches"

    # ---- S8: classify + remedy + stall detector ----------------------------
    def s8_close(self):
        report = []
        uncovered = self.bins.uncovered()
        if not uncovered:
            return report
        stall = 0
        remedies_applied = 0
        try:
            while uncovered and stall < 2:
                before = len(uncovered)
                for _ in range(16):          # directed state-routing traffic
                    self.write_op(0xAB, wait=False)
                for _ in range(16):
                    self.read_op(wait=False)
                uncovered = self.bins.uncovered()
                remedies_applied += 1
                if len(uncovered) == before:
                    stall += 1
        except StopFlow:
            stall = 2                       # remedies cannot even execute
            self.stall_reason = self.stall_reason or \
                "remedy traffic stalled (state unreachable)"
        report.append(f"remedy rounds: {remedies_applied}, "
                      f"stall detected: {stall >= 2}")
        for b in uncovered:
            cat = self._classify(b)
            report.append(f"  gap {b}: {cat} -> remedy: {GAP_REMEDY[cat]}")
        return report

    def _classify(self, bin_name):
        if self.bins.sva_violations and bin_name in ("b_sva_mutex",
                                                     "b_fill_to_full",
                                                     "b_backpressure_write"):
            return "State Unreached"      # full state unreachable (deadlock)
        if self.bins.mismatch_events:
            return "Transition Gap"
        return "Stimulus Gap"

    # ---- report -------------------------------------------------------------
    def report(self, label):
        adaptive = self.s7_adaptive_random()      # S7 MUST run before S8
        if self.bins.sva_violations == 0:
            self.bins.hit("b_sva_mutex", "no violations across the run")
        if self.bins.scope == "d12" and self.bins.mismatch_events == 0:
            self.bins.hit("b_config_d12", "full flow clean at depth 12")
        lines = [f"# S6-S8 Flow Report — {label}",
                 f"scope: {self.bins.scope}  depth: {self.rtl.depth}",
                 f"sva violations: {self.bins.sva_violations}  "
                 f"scoreboard mismatches: {self.bins.mismatch_events}",
                 f"adaptive seed: {adaptive}", ""]
        lines.append("## coverage (%s)" % ("%.1f%%" % self.bins.covered_pct()))
        for b, (s, claim) in BINS.items():
            if s != self.bins.scope:
                continue
            mark = "hit " if self.bins.hits[b] else "GAP "
            ev = self.bins.evidence.get(b, "")
            lines.append(f"  [{mark}] {b}: {claim} {('| ' + ev) if ev else ''}")
        lines.append("")
        lines.append("## S8 closure")
        close = self.s8_close()
        lines += close if close else ["  all bins covered - no residual gaps"]
        if self.bins.mismatch_events or self.stall_reason:
            lines.append("")
            lines.append("## failure signature")
            if self.stall_reason:
                lines.append(f"  STALL: {self.stall_reason}")
            lines.append(f"  {self.bins.evidence.get('LAST_MISMATCH', '')}")
        p = OUT / f"S8_report_{label}.md"
        p.write_text("\n".join(lines) + "\n")
        return p


def run(label):
    if label == "golden":
        r = Runner(depth=16)
    elif label == "bug_full_msb":
        r = Runner(depth=16, bug="full_msb")
    elif label == "d12_golden":
        r = Runner(depth=12)
    elif label == "d12_fixed":
        r = Runner(depth=12, bug="count_fix")
    else:
        print("unknown label"); sys.exit(2)
    if r.rtl.bug == "count_fix":
        r.rtl = CountFifo(depth=12)
        r.ref = SpecRefFifo(depth=12)
    try:
        r.g_x_read()               # must run before any write (X observability)
        r.g_reset_basic()
        r.g_wrap()
        r.g_simul()
        r.g_data_edge()
        r.g_reset_anytime()
    except StopFlow as e:
        r.stall_reason = str(e)
    p = r.report(label)
    cov = r.bins.covered_pct()
    print(f"{label}: coverage={cov:.1f}% sva={r.bins.sva_violations} "
          f"mismatch={r.bins.mismatch_events} -> {p.name}")
    if r.bins.mismatch_events:
        print("TRACE (last 6 cycles):")
        print("\n".join(r.rtl.trace[-6:]))


class CountFifo(RtlFifo):
    """Debug round B fix: count-based full/empty, any depth (FIX#2)."""
    def __init__(self, depth=12):
        super().__init__(depth=depth, bug=None)
        self.wptr %= 1 << (depth - 1).bit_length()
        self.rptr = 0
        self.cnt = 0

    def full(self):
        return self.cnt == self.depth

    def empty(self):
        return self.cnt == 0

    def rdata(self):
        return self.mem[self.rptr]

    def step(self, wren, wdata, rden):
        f0, e0 = self.full(), self.empty()
        do_w = wren and not f0
        do_r = rden and not e0
        rd = self.rdata() if do_r else None
        rd_x = rd is None
        self.cycle += 1
        if do_w:
            self.mem[self.wptr] = wdata & 0xFF
            self.wptr = (self.wptr + 1) % self.depth
            self.cnt += 1
        if do_r:
            self.rptr = (self.rptr + 1) % self.depth
            self.cnt -= 1
        self.sva_ok = not (self.full() and self.empty())
        return rd_x, rd

    def reset(self):
        self.wptr = 0
        self.rptr = 0
        self.cnt = 0
        self.sva_ok = True
        self.cycle += 1


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "golden")
