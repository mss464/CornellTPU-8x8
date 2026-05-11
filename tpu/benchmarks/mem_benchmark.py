#!/usr/bin/env python3
import argparse
import contextlib
import json
import os
import statistics
import sys
import time

import numpy as np

# Prefer the runtime deployed beside this benchmark over stale copies in $HOME.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
for _path in (
    os.path.join(_THIS_DIR, "runtime"),
    os.path.join(_THIS_DIR, "..", "runtime"),
    os.path.join(_THIS_DIR, "..", "..", "runtime"),
    os.path.join(_THIS_DIR, "compiler", "tpu_deploy"),
    os.path.join(_THIS_DIR, "..", "compiler", "tpu_deploy"),
):
    _path = os.path.abspath(_path)
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    import pynq_host as _host_module
except ImportError:
    import host as _host_module


class DriverAdapter:
    def __init__(self, bitstream, program=False, latency_mode=0):
        self.legacy_module = None
        driver_cls = getattr(_host_module, "MemDriver", None)
        if driver_cls is None:
            driver_cls = getattr(_host_module, "TpuDriver", None)
        if driver_cls is None:
            if all(hasattr(_host_module, name) for name in ("Overlay", "write_bram", "read_bram")):
                self._init_legacy_module(bitstream, program)
                return
            raise RuntimeError("host module must expose MemDriver/TpuDriver or write_bram/read_bram functions")

        attempts = [
            ((), {"bitstream": bitstream, "program": program, "latency_mode": latency_mode}),
            ((), {"bitstream": bitstream, "program": program}),
            ((bitstream,), {}),
            ((), {}),
        ]
        last_error = None
        for args, kwargs in attempts:
            try:
                self.impl = driver_cls(*args, **kwargs)
                break
            except TypeError as exc:
                last_error = exc
        else:
            raise last_error

    def _init_legacy_module(self, bitstream, program):
        self.legacy_module = _host_module
        self.overlay = _host_module.Overlay(bitstream)
        if program and hasattr(self.overlay, "download"):
            self.overlay.download()
        self.dma = self.overlay.axi_dma_0
        ctrl = None
        for name in ("tpu_top_v6_0", "tpu_top_0", "mem_top_0", "tpu_0"):
            if hasattr(self.overlay, name):
                ctrl = getattr(self.overlay, name)
                break
        if ctrl is None:
            raise RuntimeError("Could not find TPU control IP in overlay")
        self.mmio = ctrl.mmio
        self.impl = self

    def _call_first(self, names, *args, **kwargs):
        if self.legacy_module is not None:
            raise AttributeError("legacy module lacks required method: %s" % " or ".join(names))
        for name in names:
            fn = getattr(self.impl, name, None)
            if fn is not None:
                return fn(*args, **kwargs)
        raise AttributeError("Driver lacks required method: %s" % " or ".join(names))

    def send_bytes(self, addr, data):
        if self.legacy_module is not None:
            return self.legacy_module.write_bram(self.mmio, self.dma, addr,
                                                np.asarray(data, dtype=np.float32).reshape(-1))
        return self._call_first(("send_bytes", "write_bram"), addr, data)

    def read_bytes(self, addr, length):
        if self.legacy_module is not None:
            return self.legacy_module.read_bram(self.mmio, self.dma, addr, length)
        return self._call_first(("read_bytes", "read_bram"), addr, length)

    def sysmem_to_onchip(self, sys_addr, oc_addr, length):
        return self._call_first(("sysmem_to_onchip", "devmem_to_l2"),
                                sys_addr, oc_addr, length)

    def onchip_to_sysmem(self, oc_addr, sys_addr, length):
        return self._call_first(("onchip_to_sysmem", "l2_to_devmem"),
                                oc_addr, sys_addr, length)

    def load_instructions(self, instr64, instr_words):
        if self.legacy_module is not None:
            wait = self.legacy_module.wait_for_flag
            reg = self.legacy_module.REG_ADDR
            instrs_np = np.asarray(instr64, dtype=np.uint64)
            instr_buf = self.legacy_module.allocate(shape=instrs_np.shape, dtype=np.uint64)
            try:
                wait(self.mmio, "instr_ready", 1)
                self.mmio.write(reg["addr_ram"], 0)
                self.mmio.write(reg["length"], len(instrs_np))
                self.mmio.write(reg["tpu_mode"], self.legacy_module.WRITE_IRAM)
                wait(self.mmio, "stream_ready", 1)
                instr_buf[:] = instrs_np
                self.dma.sendchannel.transfer(instr_buf)
                self.dma.sendchannel.wait()
                wait(self.mmio, "instr_ready", 1)
                self.mmio.write(reg["tpu_mode"], 0)
            finally:
                instr_buf.freebuffer()
            return
        if hasattr(self.impl, "load_instructions"):
            return self.impl.load_instructions(instr_words)
        if hasattr(self.impl, "write_instructions"):
            return self.impl.write_instructions(np.asarray(instr64, dtype=np.uint64))
        raise AttributeError("Driver lacks instruction loading API")

    def run_compute(self, async_run=False):
        if self.legacy_module is not None:
            if async_run:
                raise AttributeError("Legacy host.py does not support async compute")
            wait = self.legacy_module.wait_for_flag
            reg = self.legacy_module.REG_ADDR
            wait(self.mmio, "instr_ready", 1)
            self.mmio.write(reg["tpu_mode"], self.legacy_module.COMPUTE)
            wait(self.mmio, "instr_ready", 1)
            self.mmio.write(reg["tpu_mode"], 0)
            return
        if hasattr(self.impl, "run_compute"):
            try:
                return self.impl.run_compute(async_run=async_run)
            except TypeError:
                if async_run:
                    raise
                return self.impl.run_compute()
        if hasattr(self.impl, "compute"):
            if async_run:
                raise AttributeError("Legacy compute() API does not support async_run")
            return self.impl.compute()
        raise AttributeError("Driver lacks compute API")

    def send_bytes_async(self, addr, data):
        if hasattr(self.impl, "send_bytes_async"):
            return self.impl.send_bytes_async(addr, data)
        return self.send_bytes(addr, data)

    def wait_dma_idle(self):
        if self.legacy_module is not None:
            return
        return self._call_first(("wait_dma_idle",))

    def wait_compute_idle(self):
        if self.legacy_module is not None:
            return
        return self._call_first(("wait_compute_idle",))

    def supports_l1_copy(self):
        return self.legacy_module is None and (
            hasattr(self.impl, "sysmem_to_onchip")
            or hasattr(self.impl, "devmem_to_l2")
        )

    def supports_overlap(self):
        if self.legacy_module is not None:
            return False
        return (
            hasattr(self.impl, "send_bytes_async")
            and hasattr(self.impl, "wait_dma_idle")
            and hasattr(self.impl, "wait_compute_idle")
            and hasattr(self.impl, "run_compute")
        )

    def compute_is_single_shot(self):
        return self.legacy_module is not None

    def is_legacy(self):
        return self.legacy_module is not None


def make_instr(mode, addr_a, addr_b, addr_out, length, opcode):
    instr = (int(mode) & 0x3) << 62
    instr |= (int(addr_a) & 0x1FFF) << 49
    instr |= (int(addr_b) & 0x1FFF) << 36
    instr |= (int(addr_out) & 0x1FFF) << 23
    instr |= (int(length) & 0x7FFFFF)
    if opcode:
        instr = (instr & ~0x3FF) | (int(opcode) & 0x3FF)
    return instr


def make_vpu_simd_instr(vpu_type, addr_a=0, addr_b=0, addr_out=0,
                        vreg_dst=0, vreg_a=0, vreg_b=0,
                        vpu_opcode=0, scalar_b=False):
    instr = make_instr(mode=0, addr_a=addr_a, addr_b=addr_b,
                       addr_out=addr_out, length=0, opcode=0)
    instr |= (int(vpu_type) & 0x7) << 20
    instr |= (int(vreg_dst) & 0x7) << 17
    instr |= (int(vreg_a) & 0x7) << 14
    instr |= (int(vreg_b) & 0x7) << 11
    instr |= (int(vpu_opcode) & 0x7) << 4
    instr |= (1 if scalar_b else 0) << 3
    return instr


def split_instr64(instr64):
    words = []
    for instr in instr64:
        words.append(instr & 0xFFFFFFFF)
        words.append((instr >> 32) & 0xFFFFFFFF)
    return words


def make_vadd_program(vadd_len, repeats):
    if repeats < 1 or repeats > 255:
        raise ValueError("vadd repeats must be in [1, 255] so the HALT fits in 8-bit IRAM")

    addr_a = 0
    addr_b = addr_a + vadd_len
    addr_out = addr_b + vadd_len
    if addr_out + vadd_len > 8192:
        raise ValueError("VADD arrays do not fit in the 8K-word L1 scratchpad")

    vadd = make_instr(mode=2, addr_a=addr_a, addr_b=addr_b, addr_out=addr_out,
                      length=vadd_len, opcode=0)
    halt = make_instr(mode=3, addr_a=0, addr_b=0, addr_out=0, length=0, opcode=0x3FF)

    instr64 = ([vadd] * repeats) + [halt]
    return instr64, split_instr64(instr64), addr_a, addr_b, addr_out


def make_vpu_scalar_add_program(elems):
    if elems < 1:
        raise ValueError("vpu elems must be positive")
    if elems + 1 > 255:
        raise ValueError("legacy scalar VPU program must fit in 8-bit IRAM PC")

    addr_a = 0
    addr_b = elems
    addr_out = 2 * elems
    if addr_out + elems > 8192:
        raise ValueError("VPU arrays do not fit in the 8K-word memory")

    instr64 = [
        make_instr(mode=0, addr_a=addr_a + i, addr_b=addr_b + i,
                   addr_out=addr_out + i, length=0, opcode=0)
        for i in range(elems)
    ]
    instr64.append(make_instr(mode=3, addr_a=0, addr_b=0,
                              addr_out=0, length=0, opcode=0x3FF))
    return instr64, split_instr64(instr64), addr_a, addr_b, addr_out


def make_vpu_simd_add_program(elems):
    if elems < 8 or elems % 8 != 0:
        raise ValueError("SIMD VPU benchmark element count must be a positive multiple of 8")
    rows = elems // 8
    if rows * 4 + 1 > 255:
        raise ValueError("SIMD VPU program must fit in 8-bit IRAM PC")

    addr_a = 0
    addr_b = elems
    addr_out = 2 * elems
    if addr_out + elems > 8192:
        raise ValueError("VPU arrays do not fit in the 8K-word L1 scratchpad")

    VPU_VLOAD = 1
    VPU_VSTORE = 2
    VPU_VCOMPUTE = 3
    VPU_ADD = 0
    instr64 = []
    for row in range(rows):
        a_row = addr_a + row * 8
        b_row = addr_b + row * 8
        out_row = addr_out + row * 8
        instr64.extend([
            make_vpu_simd_instr(VPU_VLOAD, addr_a=a_row, vreg_dst=0),
            make_vpu_simd_instr(VPU_VLOAD, addr_a=b_row, vreg_dst=1),
            make_vpu_simd_instr(VPU_VCOMPUTE, vreg_dst=2, vreg_a=0,
                                vreg_b=1, vpu_opcode=VPU_ADD),
            make_vpu_simd_instr(VPU_VSTORE, addr_out=out_row, vreg_a=2),
        ])
    instr64.append(make_instr(mode=3, addr_a=0, addr_b=0,
                              addr_out=0, length=0, opcode=0x3FF))
    return instr64, split_instr64(instr64), addr_a, addr_b, addr_out


@contextlib.contextmanager
def maybe_quiet(verbose):
    if verbose:
        yield
        return
    with open(os.devnull, "w") as sink:
        with contextlib.redirect_stdout(sink):
            yield


def timed_call(fn, repeats, warmups, verbose):
    for _ in range(warmups):
        with maybe_quiet(verbose):
            fn()

    samples = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        with maybe_quiet(verbose):
            fn()
        samples.append(time.perf_counter() - t0)
    return samples


def median(values):
    return statistics.median(values) if values else 0.0


def add_record(records, category, metric, samples, words=0, bytes_moved=0, extra=None):
    best_s = min(samples) if samples else 0.0
    med_s = median(samples)
    mean_s = statistics.mean(samples) if samples else 0.0
    record = {
        "category": category,
        "metric": metric,
        "words": int(words),
        "bytes": int(bytes_moved),
        "best_ms": best_s * 1000.0,
        "median_ms": med_s * 1000.0,
        "mean_ms": mean_s * 1000.0,
        "samples_ms": [x * 1000.0 for x in samples],
    }
    if bytes_moved and best_s > 0:
        record["best_MBps"] = (bytes_moved / 1e6) / best_s
        record["median_MBps"] = (bytes_moved / 1e6) / med_s if med_s > 0 else 0.0
    if extra:
        record.update(extra)
    records.append(record)
    return record


def add_skipped(records, category, metric, reason, words=0, extra=None):
    record = {
        "category": category,
        "metric": metric,
        "words": int(words),
        "bytes": 0,
        "skipped": True,
        "reason": reason,
        "best_ms": 0.0,
        "median_ms": 0.0,
        "mean_ms": 0.0,
        "samples_ms": [],
    }
    if extra:
        record.update(extra)
    records.append(record)
    return record


def parse_sizes(text):
    sizes = []
    for part in text.split(","):
        part = part.strip()
        if part:
            sizes.append(int(part, 0))
    return sizes


def verify_equal(name, got, expected):
    got_bits = np.asarray(got, dtype=np.float32).view(np.uint32)
    exp_bits = np.asarray(expected, dtype=np.float32).view(np.uint32)
    if not np.array_equal(got_bits, exp_bits):
        bad = np.flatnonzero(got_bits != exp_bits)[:8]
        details = []
        for idx in bad:
            details.append("[%d] got 0x%08X expected 0x%08X" %
                           (idx, int(got_bits[idx]), int(exp_bits[idx])))
        raise AssertionError("%s mismatch: %s" % (name, "; ".join(details)))


def bench_dma(records, drv, sizes, repeats, warmups, verbose, verify):
    rng = np.random.RandomState(1234)
    write_addr = 0
    read_addr = 16384

    for words in sizes:
        data = rng.rand(words).astype(np.float32)

        samples = timed_call(lambda: drv.send_bytes(write_addr, data), repeats, warmups, verbose)
        add_record(records, "dma", "host_to_sysmem_write", samples,
                   words=words, bytes_moved=words * 4)

        with maybe_quiet(verbose):
            drv.send_bytes(read_addr, data)
        samples = timed_call(lambda: drv.read_bytes(read_addr, words), repeats, warmups, verbose)
        add_record(records, "dma", "sysmem_to_host_read", samples,
                   words=words, bytes_moved=words * 4)

        if verify:
            with maybe_quiet(verbose):
                got = drv.read_bytes(read_addr, words)
            verify_equal("dma_read_%d" % words, got, data)


def bench_l1_copy(records, drv, sizes, repeats, warmups, verbose, verify):
    if not drv.supports_l1_copy():
        for words in sizes:
            add_skipped(records, "l1_copy", "sysmem_to_l1",
                        "driver/design does not expose a separate L1 copy path",
                        words=words)
            add_skipped(records, "l1_copy", "l1_to_sysmem",
                        "driver/design does not expose a separate L1 copy path",
                        words=words)
        return

    rng = np.random.RandomState(5678)
    sys_src = 8192
    sys_dst = 24576
    oc_addr = 0

    for words in sizes:
        data = rng.rand(words).astype(np.float32)
        with maybe_quiet(verbose):
            drv.send_bytes(sys_src, data)

        samples = timed_call(lambda: drv.sysmem_to_onchip(sys_src, oc_addr, words),
                             repeats, warmups, verbose)
        add_record(records, "l1_copy", "sysmem_to_l1", samples,
                   words=words, bytes_moved=words * 4)

        # Make sure L1 contains the source data before measuring readback copies.
        with maybe_quiet(verbose):
            drv.sysmem_to_onchip(sys_src, oc_addr, words)

        samples = timed_call(lambda: drv.onchip_to_sysmem(oc_addr, sys_dst, words),
                             repeats, warmups, verbose)
        add_record(records, "l1_copy", "l1_to_sysmem", samples,
                   words=words, bytes_moved=words * 4)

        if verify:
            with maybe_quiet(verbose):
                got = drv.read_bytes(sys_dst, words)
            verify_equal("l1_copy_%d" % words, got, data)


def prepare_vadd(drv, vadd_len, vadd_repeats, verbose):
    instr64, words, addr_a, _addr_b, addr_out = make_vadd_program(vadd_len, vadd_repeats)
    data_a = np.arange(vadd_len, dtype=np.float32)
    data_b = np.arange(vadd_len, 2 * vadd_len, dtype=np.float32)
    expected_bits = data_a.view(np.uint32) + data_b.view(np.uint32)

    with maybe_quiet(verbose):
        drv.load_instructions(instr64, words)
        drv.send_bytes(0, np.concatenate([data_a, data_b]))
        if drv.supports_l1_copy():
            drv.sysmem_to_onchip(0, addr_a, 2 * vadd_len)
    return addr_out, expected_bits


def verify_vadd_output(drv, addr_out, expected_bits, verbose):
    result_sys = 32768
    with maybe_quiet(verbose):
        if drv.supports_l1_copy():
            drv.onchip_to_sysmem(addr_out, result_sys, expected_bits.size)
            got = drv.read_bytes(result_sys, expected_bits.size)
        else:
            got = drv.read_bytes(addr_out, expected_bits.size)
    got_bits = got.view(np.uint32)
    if not np.array_equal(got_bits, expected_bits):
        bad = np.flatnonzero(got_bits != expected_bits)[:8]
        details = []
        for idx in bad:
            details.append("[%d] got 0x%08X expected 0x%08X" %
                           (idx, int(got_bits[idx]), int(expected_bits[idx])))
        raise AssertionError("VADD output mismatch: %s" % "; ".join(details))


def prepare_vpu_add(drv, elems, verbose):
    if drv.is_legacy():
        instr64, words, addr_a, _addr_b, addr_out = make_vpu_scalar_add_program(elems)
        path = "legacy_scalar_vpu"
    else:
        instr64, words, addr_a, _addr_b, addr_out = make_vpu_simd_add_program(elems)
        path = "banked_8lane_vpu_simd"

    data_a = np.linspace(-1.0, 1.0, elems, dtype=np.float32)
    data_b = np.linspace(0.25, 2.25, elems, dtype=np.float32)
    expected = (data_a + data_b).astype(np.float32)

    with maybe_quiet(verbose):
        drv.load_instructions(instr64, words)
        drv.send_bytes(0, np.concatenate([data_a, data_b]))
        if drv.supports_l1_copy():
            drv.sysmem_to_onchip(0, addr_a, 2 * elems)
    return addr_out, expected, path, len(instr64)


def verify_vpu_output(drv, addr_out, expected, verbose):
    result_sys = 40960
    with maybe_quiet(verbose):
        if drv.supports_l1_copy():
            drv.onchip_to_sysmem(addr_out, result_sys, expected.size)
            got = drv.read_bytes(result_sys, expected.size)
        else:
            got = drv.read_bytes(addr_out, expected.size)
    if not np.allclose(got, expected, rtol=1e-5, atol=1e-6):
        bad = np.flatnonzero(~np.isclose(got, expected, rtol=1e-5, atol=1e-6))[:8]
        details = []
        for idx in bad:
            details.append("[%d] got %.8g expected %.8g" %
                           (idx, float(got[idx]), float(expected[idx])))
        raise AssertionError("VPU output mismatch: %s" % "; ".join(details))


def add_banked_vpu_model(records, drv, elems):
    lanes = 1 if drv.is_legacy() else 8
    rows = (elems + lanes - 1) // lanes

    if drv.is_legacy():
        memory_transactions = 3 * elems
        instruction_count = elems + 1
        path = "legacy_scalar_vpu_model"
    else:
        memory_transactions = 3 * rows
        instruction_count = 4 * rows + 1
        path = "banked_8lane_vpu_model"

    samples = [memory_transactions / 100e6]
    add_record(records, "banked_compute", "vpu_vector_add_model", samples,
               words=elems,
               extra={
                   "model_only": True,
                   "path": path,
                   "elements": int(elems),
                   "simd_lanes": int(lanes),
                   "instruction_count": int(instruction_count),
                   "memory_transactions": int(memory_transactions),
                   "note": (
                       "Model only: vector add needs two reads and one write per element; "
                       "the banked design moves 8 elements per wide L1 row."
                   ),
               })


def bench_banked_vpu(records, drv, elems, repeats, warmups, verbose, verify):
    add_banked_vpu_model(records, drv, elems)

    try:
        addr_out, expected, path, instr_count = prepare_vpu_add(drv, elems, verbose)
    except (AttributeError, ValueError) as exc:
        add_skipped(records, "banked_compute", "vpu_vector_add",
                    "driver/design cannot run VPU vector add: %s" % exc,
                    words=elems)
        return

    sample_repeats = repeats
    sample_warmups = warmups
    extra = {
        "path": path,
        "elements": int(elems),
        "instruction_count": int(instr_count),
        "simd_lanes": 1 if drv.is_legacy() else 8,
    }
    if drv.compute_is_single_shot():
        sample_repeats = 1
        sample_warmups = 0
        extra["single_shot"] = True
        extra["single_shot_reason"] = (
            "legacy mem-base PC does not reset between COMPUTE launches"
        )

    try:
        samples = timed_call(lambda: drv.run_compute(async_run=False),
                             sample_repeats, sample_warmups, verbose)
        if verify:
            verify_vpu_output(drv, addr_out, expected, verbose)
    except Exception as exc:
        add_skipped(records, "banked_compute", "vpu_vector_add",
                    "VPU vector program did not complete correctly on this bitstream: %s" % exc,
                    words=elems,
                    extra=extra)
        return

    add_record(records, "banked_compute", "vpu_vector_add", samples,
               words=elems, extra=extra)


def bench_compute(records, drv, vadd_len, vadd_repeats, repeats, warmups, verbose, verify):
    try:
        addr_out, expected_bits = prepare_vadd(drv, vadd_len, vadd_repeats, verbose)
    except AttributeError as exc:
        add_skipped(records, "compute", "vadd_program",
                    "driver/design cannot load or execute VADD program: %s" % exc,
                    words=vadd_len,
                    extra={"vadd_repeats": int(vadd_repeats),
                           "vadd_ops": int(vadd_len * vadd_repeats)})
        return None, None, None

    sample_repeats = repeats
    sample_warmups = warmups
    extra = {
        "vadd_repeats": int(vadd_repeats),
        "vadd_ops": int(vadd_len * vadd_repeats),
    }
    if drv.compute_is_single_shot():
        sample_repeats = 1
        sample_warmups = 0
        extra["single_shot"] = True
        extra["single_shot_reason"] = (
            "legacy mem-base PC does not reset between COMPUTE launches"
        )

    compute_samples = timed_call(lambda: drv.run_compute(async_run=False),
                                 sample_repeats, sample_warmups, verbose)
    compute = add_record(records, "compute", "vadd_program", compute_samples,
                         words=vadd_len, extra=extra)
    if verify:
        verify_vadd_output(drv, addr_out, expected_bits, verbose)
    return compute, addr_out, expected_bits


def bench_overlap(records, drv, vadd_len, vadd_repeats, dma_words,
                  repeats, warmups, verbose, verify, compute_record=None,
                  prepared_vadd=None):
    if not drv.supports_overlap():
        add_skipped(records, "double_buffer", "dma_only_next_tile_write",
                    "driver does not expose async DMA waits",
                    words=dma_words)
        add_skipped(records, "double_buffer", "overlapped_compute_and_dma",
                    "driver does not expose async compute + independent DMA waits",
                    words=dma_words,
                    extra={"vadd_repeats": int(vadd_repeats),
                           "vadd_ops": int(vadd_len * vadd_repeats)})
        add_skipped(records, "double_buffer", "serial_estimate_compute_plus_dma",
                    "driver does not expose async compute + independent DMA waits",
                    words=dma_words)
        return

    rng = np.random.RandomState(9012)
    dma_addr = 49152
    dma_data = rng.rand(dma_words).astype(np.float32)

    if prepared_vadd is None:
        addr_out, expected_bits = prepare_vadd(drv, vadd_len, vadd_repeats, verbose)
    else:
        addr_out, expected_bits = prepared_vadd
    compute = compute_record
    if compute is None:
        compute_samples = timed_call(lambda: drv.run_compute(async_run=False),
                                     repeats, warmups, verbose)
        compute = add_record(records, "compute", "vadd_program", compute_samples,
                             words=vadd_len,
                             extra={"vadd_repeats": int(vadd_repeats),
                                    "vadd_ops": int(vadd_len * vadd_repeats)})

    dma_samples = timed_call(lambda: drv.send_bytes(dma_addr, dma_data),
                             repeats, warmups, verbose)
    dma = add_record(records, "double_buffer", "dma_only_next_tile_write", dma_samples,
                     words=dma_words, bytes_moved=dma_words * 4)

    def run_overlap():
        drv.run_compute(async_run=True)
        drv.send_bytes_async(dma_addr, dma_data)
        drv.wait_dma_idle()
        drv.wait_compute_idle()

    overlap_samples = timed_call(run_overlap, repeats, warmups, verbose)
    overlap = add_record(records, "double_buffer", "overlapped_compute_and_dma",
                         overlap_samples, words=dma_words,
                         bytes_moved=dma_words * 4,
                         extra={"vadd_repeats": int(vadd_repeats),
                                "vadd_ops": int(vadd_len * vadd_repeats)})

    serial_ms = compute["median_ms"] + dma["median_ms"]
    overlap_ms = overlap["median_ms"]
    add_record(records, "double_buffer", "serial_estimate_compute_plus_dma",
               [serial_ms / 1000.0], words=dma_words,
               bytes_moved=dma_words * 4,
               extra={
                   "speedup_vs_overlap": serial_ms / overlap_ms if overlap_ms > 0 else 0.0,
                   "compute_median_ms": compute["median_ms"],
                   "dma_median_ms": dma["median_ms"],
                   "overlap_median_ms": overlap["median_ms"],
               })

    if verify:
        with maybe_quiet(verbose):
            got_dma = drv.read_bytes(dma_addr, dma_words)
        verify_equal("overlap_dma", got_dma, dma_data)
        verify_vadd_output(drv, addr_out, expected_bits, verbose)


def add_l1_bank_model(records, sizes):
    for words in sizes:
        lanes = 8
        one_bank_cycles = 3 * words
        eight_bank_cycles = 3 * ((words + lanes - 1) // lanes)
        samples = [eight_bank_cycles / 100e6]  # illustrative at 100 MHz
        add_record(records, "model", "wide_l1_8bank_vector_add_cycles", samples,
                   words=words,
                   extra={
                       "one_bank_cycles": int(one_bank_cycles),
                       "eight_bank_cycles": int(eight_bank_cycles),
                       "ideal_bank_speedup": (
                           float(one_bank_cycles) / float(eight_bank_cycles)
                           if eight_bank_cycles else 0.0
                       ),
                       "note": "Model only: 2 reads + 1 write per element, 8 lanes per wide L1 row.",
                   })


def print_table(records):
    columns = ["category", "metric", "words", "best_ms", "median_ms", "best_MBps"]
    header = "%-14s %-32s %8s %10s %10s %10s" % tuple(columns)
    print(header)
    print("-" * len(header))
    for rec in records:
        if rec.get("skipped"):
            print("%-14s %-32s %8d %10s %10s %10s" % (
                rec.get("category", ""),
                rec.get("metric", ""),
                rec.get("words", 0),
                "SKIP",
                "SKIP",
                "-",
            ))
            continue
        print("%-14s %-32s %8d %10.3f %10.3f %10s" % (
            rec.get("category", ""),
            rec.get("metric", ""),
            rec.get("words", 0),
            rec.get("best_ms", 0.0),
            rec.get("median_ms", 0.0),
            ("%.1f" % rec["best_MBps"]) if "best_MBps" in rec else "-",
        ))


def main():
    parser = argparse.ArgumentParser(description="Memory subsystem benchmark suite")
    parser.add_argument("--bitstream", default="mem_bd.bit")
    parser.add_argument("--program", action="store_true")
    parser.add_argument("--latency", type=int, default=0)
    parser.add_argument("--variant", default="8bank-l1")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--sizes", default="256,512,1024,2048,4096,8192")
    parser.add_argument("--copy-sizes", default="256,512,1024,2048,4096")
    parser.add_argument("--vadd-len", type=int, default=1024)
    parser.add_argument("--vadd-repeats", type=int, default=128)
    parser.add_argument("--vpu-elems", type=int, default=248)
    parser.add_argument("--dma-words", type=int, default=1024)
    parser.add_argument("--banked-vpu-only", action="store_true",
                        help="Run only the scalar-vs-banked VPU benchmark. Useful for legacy baselines with single-shot compute PCs.")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-verify", action="store_true")
    args = parser.parse_args()

    verify = not args.no_verify
    sizes = parse_sizes(args.sizes)
    copy_sizes = parse_sizes(args.copy_sizes)

    print("Memory Subsystem Benchmark Suite")
    print("variant=%s bitstream=%s repeats=%d warmups=%d" %
          (args.variant, args.bitstream, args.repeats, args.warmups))
    print("Using host module from: %s" % _host_module.__file__)

    drv = DriverAdapter(bitstream=args.bitstream, program=args.program,
                        latency_mode=args.latency)

    records = []
    if args.banked_vpu_only:
        bench_banked_vpu(records, drv, args.vpu_elems,
                         args.repeats, args.warmups, args.verbose, verify)
    else:
        bench_dma(records, drv, sizes, args.repeats, args.warmups, args.verbose, verify)
        bench_l1_copy(records, drv, copy_sizes, args.repeats, args.warmups, args.verbose, verify)
        compute, addr_out, expected_bits = bench_compute(
            records, drv, args.vadd_len, args.vadd_repeats,
            args.repeats, args.warmups, args.verbose, verify)
        bench_overlap(records, drv, args.vadd_len, args.vadd_repeats, args.dma_words,
                      args.repeats, args.warmups, args.verbose, verify,
                      compute_record=compute,
                      prepared_vadd=(addr_out, expected_bits) if addr_out is not None else None)
        if drv.compute_is_single_shot():
            add_skipped(records, "banked_compute", "vpu_vector_add",
                        "legacy baseline can only run one compute program per FPGA program; rerun with --banked-vpu-only",
                        words=args.vpu_elems)
        else:
            bench_banked_vpu(records, drv, args.vpu_elems,
                             args.repeats, args.warmups, args.verbose, verify)
    add_l1_bank_model(records, copy_sizes)

    payload = {
        "variant": args.variant,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "bitstream": args.bitstream,
        "pynq_host": _host_module.__file__,
        "repeats": args.repeats,
        "warmups": args.warmups,
        "records": records,
    }

    print("")
    print("Benchmark Summary")
    print_table(records)
    print("")
    print("RESULT_JSON: %s" % json.dumps(payload, sort_keys=True))

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.write("\n")
        print("Wrote JSON results to %s" % args.json_out)


if __name__ == "__main__":
    main()
