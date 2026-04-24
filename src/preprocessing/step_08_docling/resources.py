from __future__ import annotations

# CPU/GPU resource monitoring + memory cleanup. Ported from the old pipeline and
# thinned down to the helpers run_docling.py actually calls.

import gc
import logging
import subprocess
from typing import Optional


def get_gpu_info() -> Optional[dict]:
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            text=True, timeout=10,
        )
        parts = [p.strip() for p in out.strip().split(",")]
        return {
            "gpu_util_pct": int(parts[0]),
            "mem_used_mb": int(parts[1]),
            "mem_total_mb": int(parts[2]),
            "mem_used_pct": round(int(parts[1]) / int(parts[2]) * 100, 1),
            "temp_c": int(parts[3]),
        }
    except Exception:
        return None


def get_ram_info() -> dict:
    try:
        import psutil
        vm = psutil.virtual_memory()
        return {
            "used_gb": round(vm.used / 1024**3, 1),
            "total_gb": round(vm.total / 1024**3, 1),
            "used_pct": round(vm.percent, 1),
        }
    except ImportError:
        return {"used_gb": 0, "total_gb": 0, "used_pct": 0}


def check_cuda_available() -> dict:
    info = {"cuda_available": False, "driver_version": "N/A", "cuda_version": "N/A"}
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            text=True, timeout=10,
        )
        info["driver_version"] = out.strip()
        info["cuda_available"] = True
    except Exception:
        pass
    try:
        out = subprocess.check_output(["nvidia-smi"], text=True, timeout=10)
        for line in out.split("\n"):
            if "CUDA Version" in line:
                idx = line.index("CUDA Version:")
                info["cuda_version"] = line[idx:].split(":")[1].strip().split()[0]
                break
    except Exception:
        pass
    return info


def log_resource_status(logger: logging.Logger) -> dict:
    ram = get_ram_info()
    gpu = get_gpu_info()
    logger.info(f"RAM: {ram['used_gb']}/{ram['total_gb']} GB ({ram['used_pct']}%)")
    if gpu:
        logger.info(
            f"GPU: {gpu['gpu_util_pct']}% util | "
            f"VRAM: {gpu['mem_used_mb']}/{gpu['mem_total_mb']} MB ({gpu['mem_used_pct']}%) | "
            f"Temp: {gpu['temp_c']}°C"
        )
    return {"ram": ram, "gpu": gpu}


def cleanup_memory(logger: logging.Logger) -> None:
    collected = gc.collect()
    logger.debug(f"GC collected {collected} objects")
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
            logger.debug("VRAM cleared")
    except ImportError:
        pass
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
        logger.debug("malloc_trim(0)")
    except Exception:
        pass
