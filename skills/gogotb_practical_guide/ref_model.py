"""S4 — Spec-derived reference model (GoGoTB oracle isolation, judgment #5).

Written ONLY from the specification text:
  "Synchronous FIFO of capacity DEPTH. Write when not full appends the datum
   in FIFO order. Read when not empty returns the head datum and consumes it.
   full is asserted exactly when the FIFO holds DEPTH entries; empty exactly
   when it holds none. After reset the FIFO is empty. Data written becomes
   readable no later than the following cycle."

It contains NO RTL implementation knowledge: no pointer widths, no MSB wrap
trick, no memory-array indexing. If a mismatch occurs, the DUT is wrong — the
oracle cannot be.
"""


class SpecRefFifo:
    def __init__(self, depth: int = 16):
        self.depth = depth
        self.q: list[int] = []          # capacity DEPTH, FIFO order
        self.mismatches = 0
        self.reads = 0
        self.writes = 0

    # -- spec states ---------------------------------------------------
    def full(self) -> bool:
        return len(self.q) == self.depth

    def empty(self) -> bool:
        return len(self.q) == 0

    def cnt(self) -> int:
        return len(self.q)

    def head(self):
        """Spec: value a read returns when not empty; None (X) when empty."""
        return self.q[0] if self.q else None

    # -- spec transactions (called at the sampling edge) ----------------
    def write(self, wren: bool, wdata: int):
        """Spec: wren with not full appends the datum."""
        if wren and not self.full():
            self.q.append(wdata & 0xFF)
            self.writes += 1
            return True
        return False

    def read(self, rden: bool) -> int | None:
        """Spec: rden with not empty returns head and consumes it.

        Returns None (X) when the read is blocked (empty).
        """
        if rden and not self.empty():
            v = self.q.pop(0)
            self.reads += 1
            return v
        return None

    def check(self, rtl_rdata_is_x: bool, rtl_rdata: int | None):
        """Scoreboard compare of the sampled rdata against the spec head."""
        h = self.head()
        if h is None:
            # spec says: no defined value -> any X is consistent
            return
        if rtl_rdata_is_x or rtl_rdata != h:
            self.mismatches += 1
