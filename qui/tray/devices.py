# pylint: disable=wrong-import-position,import-error
import asyncio
import subprocess
import sys

import traceback

import gi
gi.require_version('Gtk', '3.0')  # isort:skip
gi.require_version('AppIndicator3', '0.1')  # isort:skip
from gi.repository import Gtk  # isort:skip
from gi.repository import AppIndicator3 as appindicator  # isort:skip

import qubesadmin
from qubesadmin import exc
import qui.decorators

import gbulb
gbulb.install()


DEV_TYPES = ['block', 'usb', 'mic']


class DomainMenuItem(Gtk.ImageMenuItem):
    ''' A submenu item for the device menu. Allows attaching and
    detaching the device to a domain. '''

    def __init__(self, device, vm, attached, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.vm = vm

        self.device = device
        self.attached = attached

        icon = self.vm.label.icon
        self.set_image(qui.decorators.create_icon(icon))
        self._hbox = qui.decorators.device_domain_hbox(self.vm,
                                                       self.attached)
        self.devclass = str(self.device.devclass)

        self.add(self._hbox)

    def attach(self):
        assert not self.attached
        self.attached = True

        self.remove(self._hbox)
        self._hbox = qui.decorators.device_domain_hbox(self.vm,
                                                       self.attached)
        self.add(self._hbox)
        self.show_all()

    def detach(self):
        assert self.attached
        self.attached = False
        self.remove(self._hbox)
        self._hbox = qui.decorators.device_domain_hbox(self.vm,
                                                       self.attached)
        self.add(self._hbox)
        self.show_all()


class DomainMenu(Gtk.Menu):
    def __init__(self, device, frontend_domains, qapp,
                 dispatcher, *args, **kwargs):
        super(DomainMenu, self).__init__(*args, **kwargs)
        self.device = device
        self.menu_items = {}
        self.qapp = qapp
        self.attached_items = []
        self.frontend_domains = frontend_domains
        self.dispatcher = dispatcher

        for vm in self.qapp.domains:
            if vm != device.backend_domain\
                    and vm.is_running() and vm.name != 'dom0':
                self.add_vm(vm)

        self.dispatcher.add_handler('domain-start', self.add_vm)
        self.dispatcher.add_handler('domain-shutdown', self.remove_vm)

    def add_vm(self, vm, _event=None, **_kwargs):
        menu_item = DomainMenuItem(self.device, vm, vm in self.frontend_domains)
        menu_item.connect('activate', self.toggle)

        self.menu_items[vm] = menu_item
        if vm in self.frontend_domains:
            self.attached_items.append(menu_item)

        # sort function
        position = 0
        for i in self.menu_items:
            if str(self.menu_items[i].vm) < str(vm.name):
                position += 1

        self.insert(menu_item, position)
        self.show_all()
        self.queue_draw()

    def remove_vm(self, vm, _event=None, **_kwargs):
        if vm not in self.menu_items:
            return
        menu_item = self.menu_items[vm]
        if menu_item in self.attached_items:
            self.attached_items.remove(menu_item)
        self.remove(menu_item)
        self.show_all()
        self.queue_draw()

    def dev_attached(self, vm):
        menu_item = self.menu_items[vm]
        menu_item.attach()
        self.attached_items.append(menu_item)

    def dev_detached(self, vm):
        menu_item = self.menu_items[vm]
        menu_item.detach()
        if menu_item in self.attached_items:
            self.attached_items.remove(menu_item)

    def toggle(self, menu_item):
        if menu_item.attached:
            self.detach_item()
        else:
            self.attach_item(menu_item)

    def attach_item(self, menu_item):
        self.detach_item()

        try:
            assignment = qubesadmin.devices.DeviceAssignment(
                self.device.backend_domain, self.device.ident, persistent=False)
            menu_item.vm.devices[menu_item.devclass].attach(assignment)
            subprocess.call(
                ['notify-send',
                 "Attaching %s to %s" % (
                     self.device.description, menu_item.vm)])
        except exc.QubesException as ex:
            subprocess.call(
                ['notify-send', '-t', '15000', '-i', 'dialog-error',
                 'Attaching device {0} to {1} failed. Error: {2}'.format(
                     self.device.description,
                     menu_item.vm,
                     ex)])
        except Exception:  # pylint: disable=broad-except
            traceback.print_exc(file=sys.stderr)

    def detach_item(self):
        for menu_item in self.attached_items:
            for assignment\
                    in menu_item.vm.devices[menu_item.devclass].assignments():
                if assignment.device == self.device:
                    menu_item.vm.devices[menu_item.devclass].detach(assignment)
            subprocess.call([
                'notify-send',
                "Detaching %s from %s" % (self.device.description,
                                          menu_item.vm.name)
            ])


class DeviceItem(Gtk.ImageMenuItem):
    ''' MenuItem showing the device data and a :class:`DomainMenu`. '''

    def __init__(self, device, frontend_domains, qapp,
                 dispatcher, *args, **kwargs):
        "docstring"
        super().__init__(*args, **kwargs)

        self.qapp = qapp
        self.device = device
        self.devclass = self.device.devclass
        self.frontend_domains = frontend_domains
        self.dispatcher = dispatcher
        vm_icon = self.device.backend_domain.label.icon
        self.hbox = qui.decorators.device_hbox(
            self.device,
            frontend_domains=self.frontend_domains)  # type: Gtk.Box

        self.set_image(qui.decorators.create_icon(vm_icon))
        self.add(self.hbox)
        submenu = DomainMenu(
            self.device, self.frontend_domains, qapp, self.dispatcher)
        self.set_submenu(submenu)

        self.dispatcher.add_handler('domain-shutdown',
                                    self.vm_shutdown)
        self.dispatcher.add_handler('domain-start-failed',
                                    self.vm_shutdown)

    def vm_shutdown(self, vm, _event, **_kwargs):
        if vm in self.frontend_domains:
            self.device_detached(vm)

    def device_attached(self, vm):
        self.frontend_domains.append(vm)
        self.remove(self.hbox)
        self.hbox = qui.decorators.device_hbox(
            self.device, frontend_domains=self.frontend_domains)
        self.add(self.hbox)
        self.get_submenu().dev_attached(vm)
        self.show_all()

    def device_detached(self, vm):
        if vm:
            self.frontend_domains.remove(vm)
        self.remove(self.hbox)
        self.hbox = qui.decorators.device_hbox(
            self.device, frontend_domains=self.frontend_domains)
        self.add(self.hbox)
        self.get_submenu().dev_detached(vm)
        self.show_all()


class DeviceGroups():
    def __init__(self, menu: Gtk.Menu, dispatcher, qapp):
        self.positions = {}
        self.separators = {}
        self.counters = {}
        self.menu = menu
        self.menu_items = {}
        self.qapp = qapp
        self.dispatcher = dispatcher

        for pos, dev_type in enumerate(DEV_TYPES):
            self.counters[dev_type] = 0
            separator = Gtk.SeparatorMenuItem()
            self.menu.add(separator)

            self.positions[dev_type] = pos
            self.separators[dev_type] = separator

        for devclass in DEV_TYPES:
            self.dispatcher.add_handler('device-attach:' + devclass,
                                        self.device_attached)
            self.dispatcher.add_handler('device-detach:' + devclass,
                                        self.device_detached)
            self.dispatcher.add_handler('device-list-change:' + devclass,
                                        self.device_change)

    def update_device_list(self, vm=None):
        devices = {}

        for domain in self.qapp.domains if not vm else [vm]:
            for devclass in DEV_TYPES:
                for device in domain.devices[devclass]:
                    devices[device] = []

        for domain in self.qapp.domains:
            for devclass in DEV_TYPES:
                for device in domain.devices[devclass].attached():
                    if device in devices:
                        # occassionally ghost UnknownDevices appear when a
                        # device was removed but not detached from a VM
                        devices[device].append(domain)

        for device in [dev for dev in devices
                       if dev not in self.menu_items]:
            self.add(device, devices[device])

        for device in [dev for dev in self.menu_items
                       if dev not in devices and
                          (dev.backend_domain == vm or vm is None)]:
            self.remove(device)

    def device_change(self, vm, _event, **_kwargs):
        self.update_device_list(vm)

    def add(self, device, frontend_domains):
        if device.devclass not in DEV_TYPES:
            return

        position = self._position(device.devclass)

        position += len([dev for dev in self.menu_items
                         if dev.devclass == device.devclass and dev < device])

        self._insert(device, frontend_domains, position)

        if device.devclass != DEV_TYPES[0]:
            self.separators[device.devclass].show()

        subprocess.call(
            ['notify-send', "Device %s is available" % device.description])

    def _position(self, dev_type):
        if dev_type == DEV_TYPES[0]:
            return 0
        return self.positions[dev_type] - self.counters[dev_type] + 1

    def _insert(self, device, frontend_domains, position: int) -> None:
        menu_item = DeviceItem(device, frontend_domains, self.qapp,
                               self.dispatcher)
        self.menu.insert(menu_item, position)
        self.counters[device.devclass] += 1
        self.menu_items[device] = menu_item
        self._shift_positions(device.devclass)
        self._recalc_separators()
        menu_item.show_all()

    def remove(self, device):
        for item in self.menu.get_children():
            if getattr(item, 'device', None) == device:
                self.menu.remove(item)
                self.menu_items.pop(device)
                self.counters[item.devclass] -= 1
                self._unshift_positions(item.devclass)
                self._recalc_separators()
                subprocess.call(
                    ['notify-send',
                     "Device %s is removed" % item.device.description])
                return

    def _recalc_separators(self):
        for dev_type, size in self.counters.items():
            separator = self.separators[dev_type]
            if separator is not None:
                if size > 0:
                    separator.show()
                else:
                    separator.hide()

    def _shift_positions(self, dev_type):
        if dev_type == DEV_TYPES[-1]:
            return

        start_index = DEV_TYPES.index(dev_type)
        index_to_update = DEV_TYPES[start_index:]

        for index in index_to_update:
            self.positions[index] += 1

    def _unshift_positions(self, dev_type):
        if dev_type in [DEV_TYPES[0], DEV_TYPES[-1]]:
            return

        for index in DEV_TYPES[1:]:
            assert self.positions[index] > 0
            self.positions[index] -= 1

    def device_attached(self, vm, _event, device, **_kwargs):
        for item in self.menu.get_children():
            if getattr(item, 'device', None) == device \
                    or str(getattr(item, 'device', None)) == str(device):
                item.device_attached(vm)

    def device_detached(self, vm, _event, device, **_kwargs):
        for item in self.menu.get_children():
            if getattr(item, 'device', None) == device \
                    or str(getattr(item, 'device', None)) == str(device):
                item.device_detached(vm)


class DevicesTray(Gtk.Application):
    def __init__(self, app_name, qapp, dispatcher):
        super(DevicesTray, self).__init__()
        self.name = app_name
        self.tray_menu = Gtk.Menu()

        self.dispatcher = dispatcher
        self.qapp = qapp
        self.devices = DeviceGroups(self.tray_menu, self.dispatcher, self.qapp)

        self.ind = appindicator.Indicator.new(
            'Devices Widget', "media-removable",
            appindicator.IndicatorCategory.SYSTEM_SERVICES)
        self.ind.set_status(appindicator.IndicatorStatus.ACTIVE)
        self.ind.set_menu(self.tray_menu)

    def run(self):  # pylint: disable=arguments-differ
        self.devices.update_device_list()

        self.tray_menu.show_all()


def main():
    qapp = qubesadmin.Qubes()
    dispatcher = qubesadmin.events.EventsDispatcher(qapp)
    app = DevicesTray(
        'org.qubes.qui.tray.Domains', qapp, dispatcher)
    app.run()

    loop = asyncio.get_event_loop()

    done, _ = loop.run_until_complete(asyncio.ensure_future(
        dispatcher.listen_for_events()))

    for d in done:  # pylint: disable=invalid-name
        try:
            d.result()
        except Exception:  # pylint: disable=broad-except
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
