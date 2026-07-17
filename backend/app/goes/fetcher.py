"""Download e navegação dos arquivos ABI-L2-RRQPEF (Rainfall Rate) do GOES-19.

O bucket público `noaa-goes19` (AWS us-east-1) organiza as chaves assim:

    ABI-L2-RRQPEF/<ano>/<dia_do_ano>/<hora>/OR_ABI-L2-RRQPEF-M6_G19_sYYYYJJJHHMMSSs_e..._c....nc

O produto RRQPEF entrega a taxa de chuva instantânea (mm/h) na grade fixa do ABI,
2 km, Full Disk, a cada 10 minutos. Acesso é anônimo (sem credenciais).
"""

from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import dataclass
from typing import Optional

import numpy as np

from ..config import get_settings

# ─── Constantes de navegação GOES-R (ABI fixed grid) ──────────────────
# Fonte: GOES-R Product User Guide (PUG), Vol. 3, seção 5.1.2.8.
_REQ = 6378137.0            # semieixo maior (m)
_RPOL = 6356752.31414       # semieixo menor (m)
_H = 42164160.0             # altura do ponto de perspectiva + REQ (m)
_LON0_DEG = -75.0           # longitude do subsatélite do GOES-19 (GOES-East)

_FILENAME_RE = re.compile(r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})")


@dataclass
class RainField:
    """Um quadro de taxa de chuva já recortado ao redor do local monitorado."""

    rate_mmh: np.ndarray          # matriz (lat x lon aproximado) em mm/h
    lats: np.ndarray              # vetor de latitudes das linhas
    lons: np.ndarray              # vetor de longitudes das colunas
    timestamp: dt.datetime        # início da varredura (UTC)


def _s3():
    # Imports tardios: boto3/botocore só são necessários em runtime (não nos testes).
    import boto3
    from botocore import UNSIGNED
    from botocore.client import Config

    settings = get_settings()
    return boto3.client(
        "s3",
        region_name=settings.goes_region,
        config=Config(signature_version=UNSIGNED),
    )


def _parse_scan_time(key: str) -> Optional[dt.datetime]:
    m = _FILENAME_RE.search(key)
    if not m:
        return None
    year, doy, hh, mm, ss = (int(g) for g in m.groups())
    base = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc) + dt.timedelta(days=doy - 1)
    return base.replace(hour=hh, minute=mm, second=ss)


def list_recent_keys(n: int = 3, now: Optional[dt.datetime] = None) -> list[str]:
    """Lista as `n` chaves RRQPEF mais recentes, olhando a hora atual e a anterior."""
    settings = get_settings()
    s3 = _s3()
    now = now or dt.datetime.now(dt.timezone.utc)

    keys: list[str] = []
    # Olha a hora atual e as 2 anteriores (cobre viradas de hora / atrasos).
    for delta_h in (0, 1, 2):
        t = now - dt.timedelta(hours=delta_h)
        prefix = f"{settings.goes_product}/{t.year}/{t.timetuple().tm_yday:03d}/{t.hour:02d}/"
        resp = s3.list_objects_v2(Bucket=settings.goes_bucket, Prefix=prefix)
        for obj in resp.get("Contents", []):
            keys.append(obj["Key"])

    # Ordena por horário de varredura (mais recente por último) e pega os últimos n.
    keys = [k for k in keys if _parse_scan_time(k)]
    keys.sort(key=lambda k: _parse_scan_time(k))  # type: ignore[arg-type]
    return keys[-n:]


def _download_nc(key: str) -> bytes:
    settings = get_settings()
    buf = io.BytesIO()
    _s3().download_fileobj(settings.goes_bucket, key, buf)
    return buf.getvalue()


# ─── Navegação: (lat, lon) -> índices da grade ABI ────────────────────

def _latlon_to_scan_angle(lat_deg: float, lon_deg: float) -> tuple[float, float]:
    """Converte geodésico -> ângulos de varredura (x, y) em radianos (PUG Vol.3)."""
    lat = np.deg2rad(lat_deg)
    lon = np.deg2rad(lon_deg)
    lon0 = np.deg2rad(_LON0_DEG)

    e2 = 1.0 - (_RPOL**2) / (_REQ**2)
    lat_c = np.arctan((_RPOL**2 / _REQ**2) * np.tan(lat))   # latitude geocêntrica
    rc = _RPOL / np.sqrt(1.0 - e2 * np.cos(lat_c) ** 2)

    sx = _H - rc * np.cos(lat_c) * np.cos(lon - lon0)
    sy = -rc * np.cos(lat_c) * np.sin(lon - lon0)
    sz = rc * np.sin(lat_c)

    y = np.arctan(sz / sx)
    x = np.arcsin(-sy / np.sqrt(sx**2 + sy**2 + sz**2))
    return float(x), float(y)


def _clean_rate(sub) -> np.ndarray:
    """Converte um recorte do netCDF em mm/h limpo: sem máscara, sem fill, ≥ 0.

    Pixels sem dado (fora do disco, _FillValue como 65535, NaN, negativos ou
    absurdamente altos) viram 0. Valores válidos ficam na escala real (mm/h).
    """
    arr = np.ma.filled(np.ma.masked_invalid(sub), 0.0).astype("float32")
    arr[(arr < 0.0) | (arr >= 1000.0)] = 0.0   # 1000 mm/h é fisicamente impossível => fill
    return arr


def load_crop(
    key: str, lat: float, lon: float, radius_km: float
) -> RainField:
    """Baixa um arquivo RRQPEF e recorta uma janela em torno de (lat, lon).

    Lê apenas a janela desejada direto do disco (fatiamento preguiçoso do netCDF),
    sem carregar o Full Disk inteiro (~117 MB) na memória — essencial para rodar em
    VMs pequenas (ex.: Oracle E2.1.Micro, 1 GB de RAM).
    """
    import netCDF4  # import tardio: pesado e opcional em ambiente de teste

    data = _download_nc(key)
    ds = netCDF4.Dataset("inmem", memory=data)
    try:
        # Vetores de coordenadas (1D, pequenos) — só para localizar o centro.
        x = np.array(ds.variables["x"][:], dtype="float64")  # ângulos de varredura (rad)
        y = np.array(ds.variables["y"][:], dtype="float64")
        scan = _parse_scan_time(key) or dt.datetime.now(dt.timezone.utc)

        cx, cy = _latlon_to_scan_angle(lat, lon)

        # 1 pixel = 2 km. Converte o raio em número de pixels na grade.
        px_per_km = 1.0 / 2.0
        half = int(radius_km * px_per_km)

        ix = int(np.argmin(np.abs(x - cx)))
        iy = int(np.argmin(np.abs(y - cy)))

        var = ds.variables["RRQPE"]  # (y, x) em mm/h
        var.set_auto_maskandscale(True)   # aplica scale_factor/add_offset e mascara _FillValue
        ny, nx = int(var.shape[0]), int(var.shape[1])
        y0, y1 = max(0, iy - half), min(ny, iy + half)
        x0, x1 = max(0, ix - half), min(nx, ix + half)

        # Lê SÓ a janela do disco (netCDF faz o slicing sem trazer o resto),
        # preenche pixels sem dado com 0 e descarta valores inválidos/fill.
        crop = _clean_rate(var[y0:y1, x0:x1])
    finally:
        ds.close()

    # Latitudes/longitudes aproximadas do recorte (grade pequena ~ linear).
    lat_span = radius_km / 111.0
    lon_span = radius_km / (111.0 * np.cos(np.deg2rad(lat)))
    lats = np.linspace(lat + lat_span, lat - lat_span, crop.shape[0])
    lons = np.linspace(lon - lon_span, lon + lon_span, crop.shape[1])

    return RainField(rate_mmh=crop, lats=lats, lons=lons, timestamp=scan)


def load_recent_fields(
    lat: float, lon: float, radius_km: float, n: int = 3
) -> list[RainField]:
    """Baixa os n quadros mais recentes já recortados, em ordem cronológica."""
    keys = list_recent_keys(n=n)
    fields = [load_crop(k, lat, lon, radius_km) for k in keys]
    fields.sort(key=lambda f: f.timestamp)
    return fields


def diagnostics(lat: float, lon: float, radius_km: float = 120.0) -> dict:
    """Diagnóstico: lê o quadro mais recente por inteiro e compara com a janela.

    Ajuda a distinguir problema de LEITURA (máximo global 0 → escala/variável errada)
    de problema de NAVEGAÇÃO (máximo global alto, mas janela sempre 0 → índice errado).
    """
    import netCDF4

    keys = list_recent_keys(n=1)
    if not keys:
        return {"error": "nenhum arquivo GOES encontrado"}
    key = keys[-1]

    data = _download_nc(key)
    ds = netCDF4.Dataset("inmem", memory=data)
    try:
        var = ds.variables["RRQPE"]
        var.set_auto_maskandscale(True)
        attrs = {k: str(getattr(var, k)) for k in var.ncattrs()}
        full = _clean_rate(var[:])
        x = np.array(ds.variables["x"][:], dtype="float64")
        y = np.array(ds.variables["y"][:], dtype="float64")

        gmax = float(full.max())
        giy, gix = (int(v) for v in np.unravel_index(int(np.argmax(full)), full.shape))

        cx, cy = _latlon_to_scan_angle(lat, lon)
        cix = int(np.argmin(np.abs(x - cx)))
        ciy = int(np.argmin(np.abs(y - cy)))

        half = int(radius_km * 0.5)
        y0, y1 = max(0, ciy - half), min(full.shape[0], ciy + half)
        x0, x1 = max(0, cix - half), min(full.shape[1], cix + half)
        crop = full[y0:y1, x0:x1]

        return {
            "frame_time": (_parse_scan_time(key) or dt.datetime.now(dt.timezone.utc)).isoformat(),
            "grid_shape": [int(full.shape[0]), int(full.shape[1])],
            "var_dtype": str(var.dtype),
            "var_units": attrs.get("units", "?"),
            "var_scale_factor": attrs.get("scale_factor", "?"),
            "var_add_offset": attrs.get("add_offset", "?"),
            "var_fill_value": attrs.get("_FillValue", "?"),
            "global_max_mmh": round(gmax, 2),
            "global_pixels_ge_2p5": int((full >= 2.5).sum()),
            "global_argmax_index": [giy, gix],
            "target_index": [ciy, cix],
            "crop_max_mmh": round(float(crop.max()) if crop.size else 0.0, 2),
            "crop_pixels_ge_2p5": int((crop >= 2.5).sum()),
        }
    finally:
        ds.close()
