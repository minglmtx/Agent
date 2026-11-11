"""Pure bounded NVIDIA XML decoding; no environment-derived device identity.

Accept the vendor's inert external DTD declaration without resolving it; reject
other declarations/entities. Full GPUs only. Raw capture and actual Slurm IDX
comparison belong to the allocation observer, not this parser.
"""

import re
from xml.etree import ElementTree as ET

from lab_generate_skill.domain.slurm_allocation import SlurmGpuDevice

GPU_MAX_BYTES = 1024 * 1024
_DOCTYPE = re.compile(
    r'<!DOCTYPE nvidia_smi_log SYSTEM "nvsmi_device_v[0-9]{1,3}\.dtd">'
)


def _one(parent: ET.Element, name: str) -> ET.Element:
    nodes = parent.findall(name)
    if len(nodes) != 1:
        raise ValueError("GPU field missing or duplicated: " + name)
    return nodes[0]


def _text(parent: ET.Element, name: str) -> str:
    element = _one(parent, name)
    if len(element) or element.attrib or element.text is None:
        raise ValueError("GPU field must have only scalar text: " + name)
    return element.text.strip()


def parse_gpu_device(raw: bytes) -> SlurmGpuDevice:
    """Decode exactly one visible physical device; malformed data raises."""
    if type(raw) is not bytes:
        raise TypeError("NVIDIA output must be bytes")
    if not 0 < len(raw) <= GPU_MAX_BYTES:
        raise ValueError("NVIDIA output exceeds byte bounds")
    text = raw.decode("utf-8")
    text, declarations = _DOCTYPE.subn("", text)
    if declarations > 1 or "<!DOCTYPE" in text or "<!ENTITY" in text:
        raise ValueError("Untrusted XML declaration")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError("Malformed NVIDIA XML") from error
    if root.tag != "nvidia_smi_log" or root.attrib:
        raise ValueError("Unexpected NVIDIA document root")
    if _text(root, "attached_gpus") != "1":
        raise ValueError("Exactly one visible full GPU is required")
    gpu = _one(root, "gpu")
    mig = _one(gpu, "mig_mode")
    if (
        _text(mig, "current_mig") not in ("Disabled", "N/A")
        or _text(mig, "pending_mig") not in ("Disabled", "N/A")
        or _text(gpu, "mig_devices") != "None"
    ):
        raise ValueError("MIG and pending MIG transitions are unsupported")
    pci_bus = _text(_one(gpu, "pci"), "pci_bus_id")
    if gpu.attrib != {"id": pci_bus}:
        raise ValueError("GPU PCI identity differs within the device record")
    minor = _text(gpu, "minor_number")
    if re.fullmatch(r"0|[1-9][0-9]{0,6}", minor) is None:
        raise ValueError("Invalid physical GPU minor")
    return SlurmGpuDevice(
        uuid=_text(gpu, "uuid"),
        pci_bus_id=pci_bus,
        minor_number=int(minor),
        product_name=_text(gpu, "product_name"),
    )
