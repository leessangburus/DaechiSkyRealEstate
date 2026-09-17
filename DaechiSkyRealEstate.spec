# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [
    ('main_app.py', '.'),
    ('modules/naver_land/app.py', 'modules/naver_land'),
    ('modules/naver_land/core.py', 'modules/naver_land'),
    ('modules/apt_trade/app.py', 'modules/apt_trade'),
    ('modules/apt_trade/core.py', 'modules/apt_trade'),
    ('modules/apt_trade/sigungu_codes.json', 'modules/apt_trade'),
    ('modules/apt_trade/dong_codes.json', 'modules/apt_trade'),
    ('.streamlit', '.streamlit'),
]
binaries = []
hiddenimports = [
    'modules.apt_trade.app',
    'modules.apt_trade.core',
    'modules.naver_land.app',
    'modules.naver_land.core',
    'modules.naver_land.scraper',
]
tmp_ret = collect_all('streamlit')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['desktop_app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DaechiSkyRealEstate',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
