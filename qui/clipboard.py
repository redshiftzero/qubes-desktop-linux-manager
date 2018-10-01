#!/usr/bin/env python3
#
# The Qubes OS Project, http://www.qubes-os.org
#
# Copyright (C) 2017 Bahtiar `kalkin-` Gadimov <bahtiar@gadimov.de>
# Copyright (C) 2017 itinerarium <code@0n0e.com>
# Copyright (C) 2016 Jean-Philippe Ouellet <jpo@vt.edu>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# pylint: disable=import-error

''' Sends notifications via Gio.Notification when something is Copy-Pasted
via Qubes RPC '''
# pylint: disable=invalid-name,wrong-import-position

import asyncio
import math
import os
import time

import gi
gi.require_version('Gtk', '3.0')  # isort:skip
from gi.repository import Gtk, Gio  # isort:skip

import gbulb
import pyinotify

gbulb.install()


class EventHandler(pyinotify.ProcessEvent):
    # pylint: disable=arguments-differ
    def my_init(self, loop=None, gtk_app=None):
        '''  This method is called from ProcessEvent.__init__(). '''
        self.notification_id = "org.qubes.qui.clipboard"
        self.gtk_app = gtk_app
        self._copy()
        self.loop = loop if loop else asyncio.get_event_loop()

    def _copy(self, vmname: str = None):
        ''' Sends Copy notification via Gio.Notification
        '''
        if vmname is None:
            with open(FROM, 'r') as vm_from_file:
                vmname = vm_from_file.readline().strip('\n')

        size = clipboard_formatted_size()

        body = "Qubes Clipboard fetched from VM: <b>'{0}'</b>\n" \
               "Copied <b>{1}</b> to the clipboard.\n" \
               "<small>Press Ctrl-Shift-v to copy this clipboard into dest" \
               " VM's clipboard.</small>".format(vmname, size)

        self._notify(body)

    def _paste(self):
        ''' Sends Paste notification via Gio.Notification.
        '''
        body = "Qubes Clipboard has been copied to the VM and wiped.<i/>\n" \
                "<small>Trigger a paste operation (e.g. Ctrl-v) to insert " \
                "it into an application.</small>"
        self._notify(body)

    def _notify(self, body):
        # pylint: disable=attribute-defined-outside-init
        notification = Gio.Notification.new("Qubes Clipboard")
        notification.set_body(body)
        notification.set_priority(Gio.NotificationPriority.NORMAL)
        self.gtk_app.send_notification(self.notification_id, notification)

    def process_IN_CLOSE_WRITE(self, _):
        ''' Reacts to modifications of the FROM file '''
        with open(FROM, 'r') as vm_from_file:
            vmname = vm_from_file.readline().strip('\n')
        if vmname == "":
            self._paste()
        else:
            self._copy(vmname=vmname)

    def process_IN_MOVE_SELF(self, _):
        ''' Stop loop if file is moved '''
        self.loop.stop()

    def process_IN_DELETE(self, _):
        ''' Stop loop if file is deleted '''
        self.loop.stop()


def clipboard_formatted_size() -> str:
    units = ['B', 'KiB', 'MiB', 'GiB']

    try:
        file_size = os.path.getsize(DATA)
    except OSError:
        return '? bytes'
    else:
        if file_size == 1:
            formatted_bytes = '1 byte'
        else:
            formatted_bytes = str(file_size) + ' bytes'

        if file_size > 0:
            magnitude = min(
                int(math.log(file_size) / math.log(2) * 0.1), len(units) - 1)
            if magnitude > 0:
                return '%s (%.1f %s)' % (formatted_bytes,
                                         file_size / (2.0**(10 * magnitude)),
                                         units[magnitude])
        return '%s' % (formatted_bytes)


DATA = "/var/run/qubes/qubes-clipboard.bin"
FROM = "/var/run/qubes/qubes-clipboard.bin.source"


class NotificationApp(Gtk.Application):
    def __init__(self, **properties):
        super().__init__(**properties)
        self.set_application_id("org.qubes.qui.clipboard")
        self.register()  # register Gtk Application


def main():
    loop = asyncio.get_event_loop()
    mask = pyinotify.ALL_EVENTS
    gtk_app = NotificationApp()
    wm = pyinotify.WatchManager()

    while True:
        if not os.path.exists(DATA):
            time.sleep(0.5)
        else:
            wm.add_watch(FROM, mask)
            handler = EventHandler(loop=loop, gtk_app=gtk_app)
            pyinotify.AsyncioNotifier(wm, loop, default_proc_fun=handler)
            loop.run_forever()


if __name__ == '__main__':
    main()
