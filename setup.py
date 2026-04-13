from setuptools import setup
import os

ICON = 'assets/icon.icns' if os.path.exists('assets/icon.icns') else None

APP = ['app.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': False,
    'iconfile': ICON,
    'plist': {
        'CFBundleName': 'WhisperTranscribe',
        'CFBundleDisplayName': 'WhisperTranscribe',
        'CFBundleIdentifier': 'com.whispertranscribe.app',
        'CFBundleVersion': '2.0.0',
        'CFBundleShortVersionString': '2.0.0',
        'LSMinimumSystemVersion': '13.0',
        'NSHighResolutionCapable': True,
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'Audio/Video File',
                'CFBundleTypeRole': 'Viewer',
                'LSItemContentTypes': [
                    'public.audio',
                    'public.movie',
                    'public.mpeg-4',
                    'public.mp3',
                ],
            }
        ],
    },
    'packages': ['customtkinter'],
    'includes': [
        'tkinter', 'json', 'threading', 'subprocess', 'pathlib',
        'shared', 'macos_drop', 'batch_queue', 'export_modal', 'whisper_server',
        'objc', 'Foundation', 'AppKit',
    ],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
