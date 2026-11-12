# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hidden = []
for package in ("app", "uvicorn", "alembic", "sqlalchemy", "openpyxl", "PIL", "barcode", "qrcode", "reportlab"):
    hidden += collect_submodules(package)
hidden += [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "argon2",
]

a = Analysis(
    ["packaging/windows/launcher.py"],
    pathex=["backend"],
    binaries=[],
    datas=[
        ("backend/alembic", "alembic"),
        ("backend/alembic.ini", "."),
        ("backend/data/iSpring_SKU_List.xlsx", "data"),
    ],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StarLinks",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="StarLinks",
)
