"""
scripts/build_deb_package.py
============================
Creates a fully compliant Debian / Ubuntu binary package (.deb)
from release/linux-unpacked without requiring Ruby/fpm.
"""

import io
import os
import tarfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LINUX_UNPACKED = REPO_ROOT / "release" / "linux-unpacked"
OUTPUT_DEB = REPO_ROOT / "release" / "ctb_4.0.0_amd64.deb"
ICON_PNG = REPO_ROOT / "frontend" / "public" / "icon.png"

DESKTOP_ENTRY = """[Desktop Entry]
Name=Crypto Brain Terminal
Exec="/opt/Crypto Brain Terminal/ctb" %U
Terminal=false
Type=Application
Icon=ctb
StartupWMClass=Crypto Brain Terminal
Comment=Crypto Brain Terminal quantitative paper trading & desk platform
Categories=Finance;Network;
"""


def create_ar_header(name: str, size: int, mode: int = 0o100644, mtime: int = 0) -> bytes:
    """Creates a 60-byte standard GNU/POSIX ar header."""
    # name is padded to 16 bytes with trailing spaces, ending with / for GNU ar or space
    name_field = f"{name:<16}"[:16]
    mtime_field = f"{mtime:<12}"[:12]
    owner_field = f"{0:<6}"[:6]
    group_field = f"{0:<6}"[:6]
    mode_field = f"{oct(mode)[2:]:<8}"[:8]
    size_field = f"{size:<10}"[:10]
    magic = b"`\n"
    header = (
        name_field.encode("ascii")
        + mtime_field.encode("ascii")
        + owner_field.encode("ascii")
        + group_field.encode("ascii")
        + mode_field.encode("ascii")
        + size_field.encode("ascii")
        + magic
    )
    assert len(header) == 60, f"Header length must be 60, got {len(header)}"
    return header


def build_deb():
    if not LINUX_UNPACKED.exists():
        raise FileNotFoundError(f"Missing {LINUX_UNPACKED}. Build electron linux-unpacked first.")

    print(f"Building {OUTPUT_DEB.name} from {LINUX_UNPACKED}...")

    # 1. debian-binary
    debian_binary = b"2.0\n"

    # 2. Calculate installed size
    total_size_bytes = 0
    for root, dirs, files in os.walk(LINUX_UNPACKED):
        for f in files:
            p = Path(root) / f
            total_size_bytes += p.stat().st_size
    installed_size_kb = (total_size_bytes + 1023) // 1024

    # 3. control file
    control_content = f"""Package: ctb-terminal
Version: 4.0.0
Section: finance
Priority: optional
Architecture: amd64
Maintainer: Crypto Brain Terminal Team <info@cbt-sky.org>
Installed-Size: {installed_size_kb}
Depends: libgtk-3-0, libnotify4, libnss3, libxss1, libxtst6, xdg-utils, libasound2
Description: Crypto Brain Terminal quantitative paper trading & desk platform
 Autonomous institutional quantitative crypto research, execution simulation, and cluster collective intelligence terminal.
"""
    control_bytes = control_content.encode("utf-8")

    control_tar_buf = io.BytesIO()
    with tarfile.open(fileobj=control_tar_buf, mode="w:gz") as tar:
        ti = tarfile.TarInfo("./control")
        ti.size = len(control_bytes)
        ti.mode = 0o644
        ti.uname = "root"
        ti.gname = "root"
        ti.mtime = int(time.time())
        tar.addfile(ti, io.BytesIO(control_bytes))
    control_tar_gz = control_tar_buf.getvalue()

    # 4. data.tar.gz
    data_tar_buf = io.BytesIO()
    with tarfile.open(fileobj=data_tar_buf, mode="w:gz") as tar:
        # Directories
        for dir_path in [
            "./opt",
            "./opt/Crypto Brain Terminal",
            "./usr",
            "./usr/bin",
            "./usr/share",
            "./usr/share/applications",
            "./usr/share/icons",
            "./usr/share/icons/hicolor",
            "./usr/share/icons/hicolor/512x512",
            "./usr/share/icons/hicolor/512x512/apps",
        ]:
            ti = tarfile.TarInfo(dir_path)
            ti.type = tarfile.DIRTYPE
            ti.mode = 0o755
            ti.uname = "root"
            ti.gname = "root"
            ti.mtime = int(time.time())
            tar.addfile(ti)

        # Desktop entry
        dt_bytes = DESKTOP_ENTRY.encode("utf-8")
        ti = tarfile.TarInfo("./usr/share/applications/ctb.desktop")
        ti.size = len(dt_bytes)
        ti.mode = 0o644
        ti.uname = "root"
        ti.gname = "root"
        ti.mtime = int(time.time())
        tar.addfile(ti, io.BytesIO(dt_bytes))

        # Icon
        if ICON_PNG.exists():
            icon_data = ICON_PNG.read_bytes()
            ti = tarfile.TarInfo("./usr/share/icons/hicolor/512x512/apps/ctb.png")
            ti.size = len(icon_data)
            ti.mode = 0o644
            ti.uname = "root"
            ti.gname = "root"
            ti.mtime = int(time.time())
            tar.addfile(ti, io.BytesIO(icon_data))

        # Symlink /usr/bin/ctb -> /opt/Crypto Brain Terminal/ctb
        ti = tarfile.TarInfo("./usr/bin/ctb")
        ti.type = tarfile.SYMTYPE
        ti.linkname = "/opt/Crypto Brain Terminal/ctb"
        ti.mode = 0o777
        ti.uname = "root"
        ti.gname = "root"
        ti.mtime = int(time.time())
        tar.addfile(ti)

        # Linux unpacked files
        for root, dirs, files in os.walk(LINUX_UNPACKED):
            rel_dir = os.path.relpath(root, LINUX_UNPACKED)
            dest_dir = "./opt/Crypto Brain Terminal" if rel_dir == "." else f"./opt/Crypto Brain Terminal/{rel_dir.replace(os.sep, '/')}"
            for d in dirs:
                sub_dir = f"{dest_dir}/{d}"
                ti = tarfile.TarInfo(sub_dir)
                ti.type = tarfile.DIRTYPE
                ti.mode = 0o755
                ti.uname = "root"
                ti.gname = "root"
                ti.mtime = int(time.time())
                tar.addfile(ti)

            for f in files:
                p = Path(root) / f
                sub_file = f"{dest_dir}/{f}"
                ti = tarfile.TarInfo(sub_file)
                ti.size = p.stat().st_size
                # Executable permissions for binaries
                if f in ("ctb", "chrome-sandbox", "chrome_crashpad_handler") or f.endswith(".so"):
                    ti.mode = 0o755
                else:
                    ti.mode = 0o644
                ti.uname = "root"
                ti.gname = "root"
                ti.mtime = int(p.stat().st_mtime)
                with open(p, "rb") as fh:
                    tar.addfile(ti, fh)

    data_tar_gz = data_tar_buf.getvalue()

    # 5. Assemble ar archive
    with open(OUTPUT_DEB, "wb") as deb:
        deb.write(b"!<arch>\n")

        # debian-binary
        deb.write(create_ar_header("debian-binary", len(debian_binary)))
        deb.write(debian_binary)
        if len(debian_binary) % 2 != 0:
            deb.write(b"\n")

        # control.tar.gz
        deb.write(create_ar_header("control.tar.gz", len(control_tar_gz)))
        deb.write(control_tar_gz)
        if len(control_tar_gz) % 2 != 0:
            deb.write(b"\n")

        # data.tar.gz
        deb.write(create_ar_header("data.tar.gz", len(data_tar_gz)))
        deb.write(data_tar_gz)
        if len(data_tar_gz) % 2 != 0:
            deb.write(b"\n")

    size_mb = OUTPUT_DEB.stat().st_size / (1024 * 1024)
    print(f"[OK] Successfully built Debian package: {OUTPUT_DEB} ({size_mb:.2f} MB)")


if __name__ == "__main__":
    build_deb()
