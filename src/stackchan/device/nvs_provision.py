"""
個人版 `personal_pend` NVS 佈建產物（host）。

產出 ESP-IDF `nvs_partition_gen` 相容 CSV（及可選 bin）。
不燒錄、不寫 eFuse、不啟用 Flash Encryption／Secure Boot。
"""

from __future__ import annotations

import csv
import io
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from stackchan.device.boot_config import BootConfigError, PersonalPendingBootConfig

NVS_NAMESPACE = "personal_pend"
DEFAULT_PARTITION_SIZE = 0x4000


class NvsProvisionError(RuntimeError):
    """NVS 佈建產物失敗。"""


@dataclass(frozen=True, slots=True)
class NvsCsvRow:
    key: str
    type: str
    encoding: str
    value: str


def personal_pending_nvs_rows(
    boot: PersonalPendingBootConfig, *, ca_pem_path: Path | None = None
) -> list[NvsCsvRow]:
    """
    對齊 firmware `savePersonalPendingBootConfigToNvs` 鍵名。

    ca_pem 若有內容：需提供 ca_pem_path（file,string），避免 CSV 內嵌換行。
    """
    boot.validate()
    if boot.generation > 0xFFFF or boot.session > 0xFFFF:
        raise BootConfigError("generation／session 必須符合 u16")
    if boot.policy_ttl_seconds > 0xFFFFFFFF or boot.fetch_interval_ms > 0xFFFFFFFF:
        raise BootConfigError("ttl／fetch_interval 必須符合 u32")

    rows: list[NvsCsvRow] = [
        NvsCsvRow(NVS_NAMESPACE, "namespace", "", ""),
        NvsCsvRow("host", "data", "string", boot.coordinator_host),
        NvsCsvRow("port", "data", "u16", str(boot.port)),
        NvsCsvRow("device_id", "data", "string", boot.device_id),
        NvsCsvRow("token", "data", "string", boot.device_token),
        NvsCsvRow("policy_ver", "data", "string", boot.policy_version),
        NvsCsvRow("generation", "data", "u16", str(boot.generation)),
        NvsCsvRow("session", "data", "u16", str(boot.session)),
        NvsCsvRow("limit", "data", "u16", str(boot.limit)),
        NvsCsvRow("ttl_sec", "data", "u32", str(boot.policy_ttl_seconds)),
        NvsCsvRow("fetch_ms", "data", "u32", str(boot.fetch_interval_ms)),
    ]
    if boot.coordinator_ca_pem:
        if ca_pem_path is None:
            raise NvsProvisionError("有 coordinator_ca_pem 時必須提供 ca_pem_path")
        rows.append(NvsCsvRow("ca_pem", "file", "string", str(ca_pem_path.resolve())))
    return rows


def render_nvs_csv(rows: Sequence[NvsCsvRow]) -> str:
    """渲染 nvs_partition_gen CSV 文字（含 header）。"""
    lines = ["key,type,encoding,value"]
    for row in rows:
        sio = io.StringIO()
        csv.writer(sio, lineterminator="").writerow([row.key, row.type, row.encoding, row.value])
        lines.append(sio.getvalue())
    return "\n".join(lines) + "\n"


def find_nvs_partition_gen() -> Path | None:
    """尋找 ESP-IDF nvs_partition_gen.py（需 IDF_PATH）。"""
    idf = (os.environ.get("IDF_PATH") or "").strip()
    if not idf:
        return None
    candidate = (
        Path(idf) / "components" / "nvs_flash" / "nvs_partition_generator" / "nvs_partition_gen.py"
    )
    return candidate if candidate.is_file() else None


@dataclass(frozen=True, slots=True)
class NvsProvisionArtifacts:
    """一次佈建產物路徑（皆在 out_dir）。"""

    out_dir: Path
    csv_path: Path
    bin_path: Path | None
    ca_pem_path: Path | None
    readme_path: Path
    public_summary: dict[str, Any]


def write_personal_pending_nvs_provision(
    boot: PersonalPendingBootConfig,
    out_dir: Path,
    *,
    partition_size: int = DEFAULT_PARTITION_SIZE,
    generate_bin: bool = True,
) -> NvsProvisionArtifacts:
    """
    寫入 CSV／可選 bin／README。

    generate_bin=True 且找得到 nvs_partition_gen 時才產 bin；否則僅 CSV。
    """
    if partition_size < 0x1000 or partition_size % 0x1000 != 0:
        raise NvsProvisionError("partition_size 必須為 0x1000 對齊且 >= 0x1000")
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ca_path: Path | None = None
    if boot.coordinator_ca_pem:
        ca_path = out_dir / "personal_pend_ca.pem"
        ca_path.write_text(boot.coordinator_ca_pem if boot.coordinator_ca_pem.endswith("\n")
                           else boot.coordinator_ca_pem + "\n", encoding="utf-8")

    rows = personal_pending_nvs_rows(boot, ca_pem_path=ca_path)
    csv_path = out_dir / "personal_pend_nvs.csv"
    csv_path.write_text(render_nvs_csv(rows), encoding="utf-8")

    bin_path: Path | None = None
    gen = find_nvs_partition_gen() if generate_bin else None
    if generate_bin and gen is not None:
        bin_path = out_dir / "personal_pend_nvs.bin"
        _run_nvs_partition_gen(gen, csv_path, bin_path, partition_size)

    readme_path = out_dir / "README_PERSONAL_PEND_NVS.md"
    readme_path.write_text(
        _readme_text(boot, csv_path=csv_path, bin_path=bin_path, partition_size=partition_size),
        encoding="utf-8",
    )

    summary = boot.to_public_dict()
    summary.update(
        {
            "nvs_namespace": NVS_NAMESPACE,
            "csv": str(csv_path),
            "bin": str(bin_path) if bin_path else None,
            "flashed": False,
            "efuse_written": False,
            "generate_bin_attempted": generate_bin,
            "nvs_partition_gen_found": gen is not None if generate_bin else False,
        }
    )
    return NvsProvisionArtifacts(
        out_dir=out_dir,
        csv_path=csv_path,
        bin_path=bin_path,
        ca_pem_path=ca_path,
        readme_path=readme_path,
        public_summary=summary,
    )


def _run_nvs_partition_gen(script: Path, csv_path: Path, bin_path: Path, size: int) -> None:
    # ESP-IDF: python nvs_partition_gen.py generate <csv> <bin> <size>
    cmd = [
        shutil.which("python3") or shutil.which("python") or "python3",
        str(script),
        "generate",
        str(csv_path),
        str(bin_path),
        hex(size),
    ]
    try:
        completed = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=60)
    except OSError as exc:
        raise NvsProvisionError(f"無法執行 nvs_partition_gen: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise NvsProvisionError("nvs_partition_gen 逾時") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise NvsProvisionError(f"nvs_partition_gen 失敗: {detail or completed.returncode}")
    if not bin_path.is_file() or bin_path.stat().st_size == 0:
        raise NvsProvisionError("nvs_partition_gen 未產出有效 bin")


def _readme_text(
    boot: PersonalPendingBootConfig,
    *,
    csv_path: Path,
    bin_path: Path | None,
    partition_size: int,
) -> str:
    pub = boot.to_public_dict()
    lines = [
        "# personal_pend NVS 佈建產物",
        "",
        "此目錄由 `stackchan device provision-nvs` 產生。",
        "",
        "## 安全",
        "",
        "- **未燒錄**、**未寫 eFuse**、未啟用 Flash Encryption／Secure Boot。",
        "- CSV／bin 含 Device Token，請勿提交 git、勿外流。",
        "- 裝置 NVS Encryption 必須已啟用，韌體才會載入 `personal_pend`。",
        "",
        "## 內容摘要（無 token）",
        "",
        f"- namespace: `{NVS_NAMESPACE}`",
        f"- host: `{pub['coordinator_host']}`",
        f"- port: `{pub['port']}`",
        f"- device_id: `{pub['device_id']}`",
        f"- transport: `{pub['transport']}`",
        f"- token_len: `{pub['device_token_len']}`",
        f"- csv: `{csv_path.name}`",
        f"- bin: `{bin_path.name if bin_path else '(未產生；需 IDF_PATH + nvs_partition_gen)'}`",
        f"- partition_size: `{hex(partition_size)}`",
        "",
        "## 手動寫入（需你明確核准後才執行）",
        "",
        "1. 確認分割表 NVS offset／size（`firmware/verify_nvs_backup.py --show-partition`）。",
        "2. 若僅有 CSV：",
        "   `python $IDF_PATH/components/nvs_flash/nvs_partition_generator/nvs_partition_gen.py generate "
        f"{csv_path.name} personal_pend_nvs.bin {hex(partition_size)}`",
        "3. 寫入 flash（範例；**offset 以實機分割表為準**）：",
        "   `esptool.py write_flash <nvs_offset> personal_pend_nvs.bin`",
        "4. 注意：直接覆蓋整塊 NVS 會清除其他 namespace；個人版建議改走裝置內 "
        "`savePersonalPendingBootConfigToNvs` 或合併既有 NVS 映像。",
        "",
    ]
    return "\n".join(lines)


def redact_csv_for_display(csv_text: str) -> str:
    """測試／日誌用：遮罩 token 列。"""
    out_lines: list[str] = []
    for line in csv_text.splitlines():
        if line.startswith("token,"):
            parts = next(csv.reader([line]))
            if len(parts) >= 4:
                parts[3] = f"<redacted len={len(parts[3])}>"
                buf = __import__("io").StringIO()
                csv.writer(buf, lineterminator="").writerow(parts)
                out_lines.append(buf.getvalue())
                continue
        out_lines.append(line)
    return "\n".join(out_lines) + ("\n" if csv_text.endswith("\n") else "")
