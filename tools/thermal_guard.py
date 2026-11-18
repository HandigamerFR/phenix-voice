# -*- coding: utf-8 -*-
"""Surveillance thermique GPU/CPU pour l'entraînement LoRA (pause automatique).

GPU : API ADL du pilote AMD (``atiadlxx.dll``), fonction
      ``ADL2_New_QueryPMLogData_Get`` -> capteurs PMLog :
      TEMPERATURE_EDGE (8), TEMPERATURE_HOTSPOT (27), FAN_RPM (14),
      FAN_PERCENTAGE (15), INFO_ACTIVITY_GFX (19), ASIC_POWER (23).

CPU : tentatives WMI / compteurs Windows ; un capteur absent est ignoré
      silencieusement (jamais de blocage pour capteur manquant).

Usage dans ``tools/lora_train.py``::

    guard = ThermalGuard()                 # seuils par defaut 80/70 GPU, 90/80 CPU
    motif = guard.check()                  # None, ou "GPU 82 C >= 80 C"
    if motif:
        guard.wait_cool()                  # pause jusqu'a la reprise
"""

from __future__ import annotations

import ctypes
import time

# --- Capteurs PMLog AMD ---------------------------------------------------
PMLOG_TEMPERATURE_EDGE = 8
PMLOG_TEMPERATURE_MEM = 9
PMLOG_FAN_RPM = 14
PMLOG_FAN_PERCENTAGE = 15
PMLOG_ACTIVITY_GFX = 19
PMLOG_ASIC_POWER = 23
PMLOG_TEMPERATURE_HOTSPOT = 27
PMLOG_MAX_SENSORS = 256

ADL_OK = 0


class _ADLSingleSensorData(ctypes.Structure):
    _fields_ = [("supported", ctypes.c_int), ("value", ctypes.c_int)]


class _ADLPMLogDataOutput(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_int),
        ("sensors", _ADLSingleSensorData * PMLOG_MAX_SENSORS),
    ]


class AdlGpuMonitor:
    """Lecture des capteurs GPU via l'API ADL du pilote AMD (Windows)."""

    def __init__(self) -> None:
        self._dll = None
        self._ctx: ctypes.c_void_p | None = None
        self._adapter = 0
        self._open()

    def _open(self) -> None:
        try:
            dll = ctypes.WinDLL("atiadlxx.dll")
        except OSError:
            return

        malloc_cb = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_int)
        msvcrt = ctypes.CDLL("msvcrt.dll")
        msvcrt.malloc.argtypes = [ctypes.c_size_t]
        msvcrt.malloc.restype = ctypes.c_void_p

        @malloc_cb
        def _adl_malloc(size: int) -> int:
            return msvcrt.malloc(size) or 0

        dll.ADL2_Main_Control_Create.argtypes = [
            malloc_cb,
            ctypes.c_int,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        dll.ADL2_Main_Control_Create.restype = ctypes.c_int
        ctx = ctypes.c_void_p()
        if dll.ADL2_Main_Control_Create(_adl_malloc, 1, ctypes.byref(ctx)) != ADL_OK:
            return
        dll.ADL2_New_QueryPMLogData_Get.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.POINTER(_ADLPMLogDataOutput),
        ]
        dll.ADL2_New_QueryPMLogData_Get.restype = ctypes.c_int

        # Premier adapter renvoyant des capteurs valides (0..7).
        for idx in range(8):
            out = _ADLPMLogDataOutput()
            out.size = ctypes.sizeof(_ADLPMLogDataOutput)
            if dll.ADL2_New_QueryPMLogData_Get(ctx, idx, ctypes.byref(out)) == ADL_OK:
                if any(s.supported for s in out.sensors):
                    self._dll = dll
                    self._ctx = ctx
                    self._adapter = idx
                    return
        self._dll = dll
        self._ctx = ctx
        self._adapter = 0

    @property
    def available(self) -> bool:
        return self._ctx is not None

    def read(self) -> dict[str, float] | None:
        """Retourne les capteurs GPU (°C, %, W) ou None si indisponible."""
        if not self._dll or not self._ctx:
            return None
        out = _ADLPMLogDataOutput()
        out.size = ctypes.sizeof(_ADLPMLogDataOutput)
        rc = self._dll.ADL2_New_QueryPMLogData_Get(
            self._ctx, self._adapter, ctypes.byref(out)
        )
        if rc != ADL_OK:
            return None
        s = {i: d for i, d in enumerate(out.sensors) if d.supported}
        if not s:
            return None
        edge = s.get(PMLOG_TEMPERATURE_EDGE)
        hot = s.get(PMLOG_TEMPERATURE_HOTSPOT)
        temps = [d.value for d in (edge, hot) if d is not None]
        res: dict[str, float] = {}
        if temps:
            res["temp_c"] = float(max(temps))
        if edge is not None:
            res["edge_c"] = float(edge.value)
        if hot is not None:
            res["hotspot_c"] = float(hot.value)
        fan = s.get(PMLOG_FAN_RPM)
        if fan is not None:
            res["fan_rpm"] = float(fan.value)
        power = s.get(PMLOG_ASIC_POWER)
        if power is not None:
            res["power_w"] = float(power.value)
        return res or None


class CpuMonitor:
    """Temperature CPU via les compteurs Windows ; ignore si absent."""

    def __init__(self) -> None:
        self._counter: str | None = None
        try:
            import subprocess

            # Jeu de compteurs localise ("Thermal Zone Information" en anglais,
            # "Informations de zone thermique" en francais).
            script = (
                "$s = Get-Counter -ListSet * -ErrorAction SilentlyContinue | "
                "Where-Object { $_.CounterSetName -match 'thermal|zone thermique' }; "
                "if ($s) { "
                "$t = $s[0].Counter | Where-Object { $_ -match 'Temperature|Temp.rature' } | "
                "Select-Object -First 1; "
                "if ($t) { Write-Output $t } }"
            )
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=20,
            )
            path = (proc.stdout or "").strip()
            if path.startswith("\\"):
                self._counter = path
        except Exception:
            self._counter = None

    @property
    def available(self) -> bool:
        return bool(self._counter)

    def read(self) -> float | None:
        """Temperature CPU en degres C, ou None si indisponible."""
        if not self._counter:
            return None
        try:
            import subprocess

            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"(Get-Counter -Counter '{self._counter}' -ErrorAction Stop)"
                 ".CounterSamples[0].CookedValue"],
                capture_output=True,
                text=True,
                timeout=20,
            )
            raw = (proc.stdout or "").strip().replace(",", ".")
            return float(raw) / 10.0  # WMI/PDW : dixiemes de degre C
        except Exception:
            return None


class ThermalGuard:
    """Decide des pauses thermiques et attend le refroidissement."""

    def __init__(
        self,
        max_gpu: float = 80.0,
        resume_gpu: float = 70.0,
        max_cpu: float = 90.0,
        resume_cpu: float = 80.0,
        interval: float = 15.0,
        log=None,
    ) -> None:
        self.max_gpu = max_gpu
        self.resume_gpu = resume_gpu
        self.max_cpu = max_cpu
        self.resume_cpu = resume_cpu
        self.interval = interval
        self._log = log or (lambda msg: print(msg, flush=True))
        self.gpu = AdlGpuMonitor()
        self.cpu = CpuMonitor()
        self.pauses = 0
        self._last_check = 0.0
        if not self.gpu.available:
            self._log("[thermique] capteur GPU indisponible - surveillance GPU inactive")
        if not self.cpu.available:
            self._log("[thermique] capteur CPU indisponible - surveillance CPU inactive")

    def _gpu_hot(self, gpu: dict[str, float] | None) -> str | None:
        if gpu and "temp_c" in gpu:
            t = gpu["temp_c"]
            if t >= self.max_gpu:
                return f"GPU {t:.0f} C >= {self.max_gpu:.0f} C"
        return None

    def _cpu_hot(self, t: float | None) -> str | None:
        if t is not None and t >= self.max_cpu:
            return f"CPU {t:.0f} C >= {self.max_cpu:.0f} C"
        return None

    def check(self, force: bool = False) -> str | None:
        """Retourne le motif de pause, ou None. Echantillonne a ``interval`` s."""
        now = time.monotonic()
        if not force and (now - self._last_check) < self.interval:
            return None
        self._last_check = now
        gpu = self.gpu.read()
        motif = self._gpu_hot(gpu)
        if motif is None:
            motif = self._cpu_hot(self.cpu.read())
        return motif

    def wait_cool(self) -> float:
        """Pause jusqu'a ce que tout soit sous les seuils de reprise.

        Retourne la duree de pause (s). L'appelant n'a rien a sauvegarder :
        l'etat d'entrainement reste en memoire.
        """
        self.pauses += 1
        debut = time.monotonic()
        self._log(f"[thermique] PAUSE #{self.pauses} - arret des pas le temps du refroidissement")
        while True:
            gpu = self.gpu.read()
            cpu_t = self.cpu.read()
            chaud = self._gpu_hot_residuel(gpu) or self._cpu_hot_residuel(cpu_t)
            if chaud is None:
                break
            self._log(f"[thermique]   {chaud} - veille 10 s")
            time.sleep(10.0)
        duree = time.monotonic() - debut
        self._log(f"[thermique] REPRISE apres {duree:.0f} s de pause")
        return duree

    def _gpu_hot_residuel(self, gpu: dict[str, float] | None) -> str | None:
        if gpu and "temp_c" in gpu and gpu["temp_c"] >= self.resume_gpu:
            return f"GPU {gpu['temp_c']:.0f} C > {self.resume_gpu:.0f} C"
        return None

    def _cpu_hot_residuel(self, t: float | None) -> str | None:
        if t is not None and t >= self.resume_cpu:
            return f"CPU {t:.0f} C > {self.resume_cpu:.0f} C"
        return None

    def snapshot(self) -> dict[str, float]:
        """Mesures actuelles (pour le journal d'entrainement)."""
        res: dict[str, float] = {}
        gpu = self.gpu.read()
        if gpu:
            res.update(gpu)
        cpu_t = self.cpu.read()
        if cpu_t is not None:
            res["cpu_c"] = cpu_t
        return res
