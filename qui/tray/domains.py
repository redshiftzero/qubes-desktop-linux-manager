#!/usr/bin/env python3
# -*- coding: utf-8 -*-
''' A menu listing domains '''
import asyncio
import subprocess
import sys
import os
import traceback

import qubesadmin
import qubesadmin.events

import dbus.mainloop.glib
dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

import gbulb
gbulb.install()

# pylint: disable=wrong-import-position
import qui.decorators
import gi  # isort:skip
gi.require_version('Gtk', '3.0')  # isort:skip
from gi.repository import Gio, Gtk  # isort:skip


class ShutdownItem(Gtk.ImageMenuItem):
    ''' Shutdown menu Item. When activated shutdowns the domain. '''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        icon = Gtk.IconTheme.get_default().load_icon('media-playback-stop', 16,
                                                     0)
        image = Gtk.Image.new_from_pixbuf(icon)

        self.set_image(image)
        self.set_label('Shutdown')

        self.connect('activate', self.perform_shutdown)

    def perform_shutdown(self, *args, **kwargs):
        self.vm.shutdown()


class KillItem(Gtk.ImageMenuItem):
    ''' Kill domain menu Item. When activated kills the domain. '''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        icon = Gtk.IconTheme.get_default().load_icon('media-record', 16, 0)
        image = Gtk.Image.new_from_pixbuf(icon)

        self.set_image(image)
        self.set_label('Kill')

        self.connect('activate', self.perform_kill)

    def perform_kill(self, *args, **kwargs):
        self.vm.kill()


class PreferencesItem(Gtk.ImageMenuItem):
    ''' Preferences menu Item. When activated shows preferences dialog '''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm
        icon = Gtk.IconTheme.get_default().load_icon('preferences-system', 16,
                                                     0)
        image = Gtk.Image.new_from_pixbuf(icon)

        self.set_image(image)
        self.set_label('Preferences')

        self.connect('activate', self.launch_preferences_dialog)

    def launch_preferences_dialog(self, _item):
        subprocess.Popen(['qubes-vm-settings', self.vm.name])


class LogItem(Gtk.ImageMenuItem):
    def __init__(self, name, path):
        super().__init__()
        self.path = path

        image = Gtk.Image.new_from_file(
            "/usr/share/icons/HighContrast/16x16/apps/logviewer.png")

        self.set_image(image)
        self.set_label(name)

        self.connect('activate', self.launch_log_viewer)

    def launch_log_viewer(self, *args, **kwargs):
        subprocess.Popen(['qubes-log-viewer', self.path])


class RunTerminalItem(Gtk.ImageMenuItem):
    ''' Run Terminal menu Item. When activated runs a terminal emulator. '''
    def __init__(self, vm):
        super().__init__()
        self.vm = vm
        icon = Gtk.IconTheme.get_default().load_icon('utilities-terminal', 16,
                                                     0)
        image = Gtk.Image.new_from_pixbuf(icon)

        self.set_image(image)
        self.set_label('Run Terminal')

        self.connect('activate', self.run_terminal)

    def run_terminal(self, _item):
        self.vm.RunService('qubes.StartApp+qubes-run-terminal')


class StartedMenu(Gtk.Menu):
    ''' The sub-menu for a started domain'''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        preferences = PreferencesItem(self.vm)
        shutdown_item = ShutdownItem(self.vm)
        runterminal_item = RunTerminalItem(self.vm)

        self.add(preferences)
        self.add(shutdown_item)
        self.add(runterminal_item)


class DebugMenu(Gtk.Menu):
    ''' Sub-menu providing multiple MenuItem for domain logs. '''

    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        logs = [
            ("Console Log", "/var/log/xen/console/guest-" + vm.name + ".log"),
            ("QEMU Console Log", "/var/log/xen/console/guest-" + vm.name + "-dm.log"),
            ]

        for name, path in logs:
            if os.path.isfile(path):
                item = LogItem(name, path)
                self.add(item)

        kill = KillItem(self.vm)
        preferences = PreferencesItem(self.vm)

        self.add(preferences)
        self.add(kill)


class DomainMenuItem(Gtk.ImageMenuItem):
    def __init__(self, vm):
        super().__init__()
        self.vm = vm

        self.decorator = qui.decorators.DomainDecorator(vm)

        hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.name = self.decorator.name()
        hbox.pack_start(self.name, True, True, 0)

        self.spinner = Gtk.Spinner()
        hbox.pack_start(self.spinner, False, True, 0)
        self.spinner.start()

        if self.vm.get_power_state() != 'Running':
            self.show_spinner()
        else:
            self.hide_spinner()

        self.memory = self.decorator.memory()
        hbox.pack_start(self.memory, False, True, 0)

        self.add(hbox)

        self._set_submenu(self.vm.get_power_state())
        self._set_image()

    def _set_image(self):
        self.set_image(self.decorator.icon())

    def _set_submenu(self, state):
        if state == 'Running':
            submenu = StartedMenu(self.vm)
        else:
            submenu = DebugMenu(self.vm)
        # This is a workaround for a bug in Gtk which occurs when a
        # submenu is replaced while it is open.
        # see https://bugzilla.redhat.com/show_bug.cgi?id=1435911
        current_submenu = self.get_submenu()
        if current_submenu:
            current_submenu.grab_remove()
        self.set_submenu(submenu)

    def show_spinner(self):
        self.spinner.start()
        self.spinner.set_no_show_all(False)
        self.spinner.show()
        self.show_all()

    def hide_spinner(self):
        self.spinner.stop()
        self.spinner.set_no_show_all(True)
        self.spinner.hide()

    def update_state(self, state):
        if state == "Running":
            self.hide_spinner()
        else:
            self.show_spinner()
        self._set_submenu(state)

    def update_stats(self, memory_kb):
        text = '{0} MB'.format(int(memory_kb)//1024)
        self.memory.set_text(text)


class DomainTray(Gtk.Application):
    ''' A tray icon application listing all but halted domains. ” '''

    def __init__(self, app_name, qapp, dispatcher, stats_dispatcher):
        super().__init__()
        self.qapp = qapp
        self.dispatcher = dispatcher
        self.stats_dispatcher = stats_dispatcher

        self.widget_icon = Gtk.StatusIcon()
        self.widget_icon.set_from_icon_name('qubes-logo-icon')
        self.widget_icon.connect('button-press-event', self.show_menu)
        self.widget_icon.set_tooltip_markup(
            '<b>Qubes Domains</b>\nView and manage running domains.')

        self.tray_menu = Gtk.Menu()

        self.menu_items = {}

        self.register_events()
        self.set_application_id(app_name)
        self.register()  # register Gtk Application

    def register_events(self):
        self.dispatcher.add_handler('domain-pre-start', self.add_domain_item)
        self.dispatcher.add_handler('domain-start', self.update_domain_item)
        self.dispatcher.add_handler('domain-start-failed',
                                    self.remove_domain_item)
        self.dispatcher.add_handler('domain-stopped', self.update_domain_item)
        self.dispatcher.add_handler('domain-shutdown', self.remove_domain_item)

        self.dispatcher.add_handler('domain-pre-start', self.emit_notification)
        self.dispatcher.add_handler('domain-start', self.emit_notification)
        self.dispatcher.add_handler('domain-start-failed',
                                    self.emit_notification)
        self.dispatcher.add_handler('domain-pre-shutdown',
                                    self.emit_notification)
        self.dispatcher.add_handler('domain-shutdown', self.emit_notification)

        self.stats_dispatcher.add_handler('vm-stats', self.update_stats)

    def show_menu(self, _, event):
        self.tray_menu.show_all()
        self.tray_menu.popup(None,  # parent_menu_shell
                             None,  # parent_menu_item
                             None,  # func
                             None,  # data
                             event.button,  # button
                             Gtk.get_current_event_time())  # activate_time

    def emit_notification(self, vm, event, **kwargs):
        notification = Gio.Notification.new("Qube Status: {}". format(vm.name))
        notification.set_priority(Gio.NotificationPriority.NORMAL)

        if event == 'domain-start-failed':
            notification.set_body('Domain {} has failed to start: {}'.format(
                vm.name, kwargs['reason']))
            notification.set_priority(Gio.NotificationPriority.HIGH)
            notification.set_icon(
                Gio.ThemedIcon.new('dialog-warning'))
        elif event == 'domain-pre-start':
            notification.set_body('Domain {} is starting.'.format(vm.name))
        elif event == 'domain-start':
            notification.set_body('Domain {} has started.'.format(vm.name))
        elif event == 'domain-pre-shutdown':
            notification.set_body('Domain {} is halting.'.format(vm.name))
        elif event == 'domain-shutdown':
            notification.set_body('Domain {} has halted.'.format(vm.name))
        else:
            return
        self.send_notification('', notification)

    def add_domain_item(self, vm, event, **kwargs):
        # check if it already exists
        if vm in self.menu_items:
            return
        domain_item = DomainMenuItem(vm)
        position = 0
        for i in self.tray_menu:
            if i.vm.name > vm.name:
                break
            position += 1
        self.tray_menu.insert(domain_item, position)
        self.menu_items[vm] = domain_item
        self.tray_menu.show_all()
        self.tray_menu.queue_draw()

    def remove_domain_item(self, vm, event, **kwargs):
        ''' Remove the menu item for the specified domain from the tray'''
        vm_widget = self.menu_items[vm]
        self.tray_menu.remove(vm_widget)
        del self.menu_items[vm]
        self.tray_menu.queue_draw()

    def update_domain_item(self, vm, event, **kwargs):
        ''' Update the menu item with the started menu for the specified vm in the tray'''
        if vm not in self.menu_items:
            self.add_domain_item(vm, None)
        self.menu_items[vm].update_state(vm.get_power_state())

    def update_stats(self, vm, event, **kwargs):
        if vm not in self.menu_items:
            return
        self.menu_items[vm].update_stats(kwargs['memory_kb'])

    def initialize_menu(self):
        for vm in self.qapp.domains:
            if vm.is_running() and vm.klass != 'AdminVM':
                self.add_domain_item(vm, None)
        self.connect('shutdown', self._disconnect_signals)

    def run(self):  # pylint: disable=arguments-differ
        self.initialize_menu()

    def _disconnect_signals(self, _):
        self.dispatcher.remove_handler('domain-pre-start', self.add_domain_item)
        self.dispatcher.remove_handler('domain-start', self.update_domain_item)
        self.dispatcher.remove_handler('domain-start-failed',
                                    self.update_domain_item)
        self.dispatcher.remove_handler('domain-stopped', self.update_domain_item)
        self.dispatcher.remove_handler('domain-shutdown', self.remove_domain_item)

        self.dispatcher.remove_handler('domain-pre-start', self.emit_notification)
        self.dispatcher.remove_handler('domain-start', self.emit_notification)
        self.dispatcher.remove_handler('domain-start-failed',
                                    self.emit_notification)
        self.dispatcher.remove_handler('domain-stopped', self.emit_notification)
        self.dispatcher.remove_handler('domain-shutdown', self.emit_notification)


def main():
    ''' main function '''
    qapp = qubesadmin.Qubes()
    dispatcher = qubesadmin.events.EventsDispatcher(qapp)
    stats_dispatcher = qubesadmin.events.EventsDispatcher(
        qapp, api_method='admin.vm.Stats')
    app = DomainTray(
        'org.qubes.qui.tray.Domains', qapp, dispatcher, stats_dispatcher)
    app.run()

    loop = asyncio.get_event_loop()
    tasks = [
        asyncio.ensure_future(dispatcher.listen_for_events()),
        asyncio.ensure_future(stats_dispatcher.listen_for_events()),
    ]

    done, _ = loop.run_until_complete(asyncio.wait(
            tasks, return_when=asyncio.FIRST_EXCEPTION))

    for d in done:
        try:
            d.result()
        except Exception as ex:
            exc_type, exc_value = sys.exc_info()[:2]
            dialog = Gtk.MessageDialog(
                None, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK)
            dialog.set_title("Houston, we have a problem...")
            dialog.set_markup(
                "<b>Whoops. A critical error in Domains Widget has occured.</b>"
                " This is most likely a bug in the widget. To restart the "
                "widget, run 'qui-domains' in dom0.")
            dialog.format_secondary_markup(
                "\n<b>{}</b>: {}\n{}".format(
                   exc_type.__name__, exc_value, traceback.format_exc(limit=10)
                ))
            dialog.run()


if __name__ == '__main__':
    sys.exit(main())
