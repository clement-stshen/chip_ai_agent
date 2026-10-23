"""Cycle-accurate behavioral model of fifo.sv (RTL semantics).

Mirrors the implementation under test: pointer MSB wrap trick, combinational
rdata, gated do_w/do_r, uninitialized memory (None == X), OOB index behavior
for non-power-of-2 depths. Bug injection flags support the debug rounds.

This is the DUT stand-in for the EDA-host-less loop; the spec oracle in
ref_model.py is intentionally independent of everything here.
"""


class RtlFifo:
    def __init__(self, depth: int = 16, bug: str | None = None):
        self.depth = depth
        self.addr_w = (depth - 1).bit_length()      # $clog2(DEPTH)
        self.wrap = 1 << self.addr_w                # MSB position + 1
        self.mem: list[int | None] = [None] * depth  # None == X (uninitialized)
        self.wptr = 0
        self.rptr = 0
        self.bug = bug
        self.sva_ok = True
        self.cycle = 0
        self.trace: list[str] = []                   # poor-man's waveform

    def full(self) -> bool:
        if self.bug == "full_msb":                   # BUG#1: MSB dropped
            return (self.wptr & (self.wrap - 1)) == (self.rptr & (self.wrap - 1))
        return ((self.wptr ^ self.rptr) & self.wrap) != 0 and \
               (self.wptr & (self.wrap - 1)) == (self.rptr & (self.wrap - 1))

    def empty(self) -> bool:
        return self.wptr == self.rptr

    def rdata(self) -> int | None:
        idx = self.rptr & (self.wrap - 1)
        return self.mem[idx] if idx < self.depth else None   # OOB -> X

    def cnt(self) -> int:
        f, e = self.full(), self.empty()
        if e:
            return 0
        if f:
            return self.depth
        d = (self.wptr - self.rptr) & ((self.wrap << 1) - 1)
        return d & (self.wrap - 1) if not ((self.wptr ^ self.rptr) & self.wrap) \
            else d & (self.wrap - 1)

    def step(self, wren: bool, wdata: int, rden: bool) -> tuple[bool, int | None]:
        """One posedge. Returns (rdata_is_x, rdata_sampled) at this edge."""
        f_before, e_before = self.full(), self.empty()
        do_w = wren and not f_before
        do_r = rden and not e_before
        rd = self.rdata() if do_r else None
        rd_x = rd is None
        self.cycle += 1
        if self.trace is not None and len(self.trace) < 4096:
            self.trace.append(
                "t=%-6d wren=%d rden=%d wptr=%-2d rptr=%-2d full=%d empty=%d "
                "rdata=%s" % (self.cycle, int(wren), int(rden), self.wptr,
                              self.rptr, int(f_before), int(e_before),
                              "X" if rd_x else "0x%02x" % (rd or 0)))
        if do_w:
            idx = self.wptr & (self.wrap - 1)
            if idx < self.depth:                     # SV: OOB write dropped
                self.mem[idx] = wdata & 0xFF
            self.wptr = (self.wptr + 1) & ((self.wrap << 1) - 1)
        if do_r:
            self.rptr = (self.rptr + 1) & ((self.wrap << 1) - 1)
        self.sva_ok = not (self.full() and self.empty())
        return rd_x, rd

    def reset(self):
        self.wptr = 0
        self.rptr = 0
        self.sva_ok = True
        self.cycle += 1
