#!/usr/bin/env python3
''' Setup.py file '''
import os
import subprocess
import setuptools


def create_mo_files():
    data_files = []
    localedir = 'locales'
    po_dirs = [localedir + '/' + l + '/LC_MESSAGES/'
               for l in next(os.walk(localedir))[1]]
    for d in po_dirs:
        mo_files = []
        po_files = [f
                    for f in next(os.walk(d))[2]
                    if os.path.splitext(f)[1] == '.po']
        for po_file in po_files:
            filename, extension = os.path.splitext(po_file)
            mo_file = filename + '.mo'
            msgfmt_cmd = 'msgfmt {} -o {}'.format(d + po_file, d + mo_file)
            subprocess.check_call(msgfmt_cmd, shell=True)
            mo_files.append(d + mo_file)
        data_files.append((d, mo_files))
    return data_files


setuptools.setup(name='qui',
      version='0.1',
      author='Invisible Things Lab',
      author_email='bahtiar@gadimov.de',
      description='Qubes User Interface Package',
      license='GPL2+',
      url='https://www.qubes-os.org/',
      packages=("qui", "qui.tray"),
      entry_points={
          'gui_scripts': [
              'qui-domains = qui.tray.domains:main',
              'qui-devices = qui.tray.devices:main',
              'qui-disk-space = qui.tray.disk_space:main',
              'qui-updates = qui.tray.updates:main',
              'qubes-update-gui = qui.updater:main',
              'qui-clipboard = qui.clipboard:main'
          ]
      },
      package_data={'qui': ["updater.glade"]},
      data_files=create_mo_files())
