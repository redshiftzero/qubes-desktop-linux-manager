# pylint: disable=wrong-import-position,import-error
import asyncio
import sys
import time
import traceback

import gi
gi.require_version('Gdk', '3.0')  # isort:skip
gi.require_version('Gtk', '3.0')  # isort:skip
gi.require_version('AppIndicator3', '0.1')  # isort:skip
from gi.repository import Gdk, Gtk, Gio  # isort:skip

import qubesadmin
import qubesadmin.events
import qubesadmin.devices
import qubesadmin.exc
import qui.decorators

import gbulb
gbulb.install()

import gettext
t = gettext.translation("desktop-linux-manager", localedir="/usr/locales",
                        fallback=True)
_ = t.gettext

DEV_TYPES = ['block', 'mic', 'usb']


class DomainMenuItem(Gtk.MenuItem):
    """ A submenu item for the device menu. Displays attachment status.
     Allows attaching/detaching the device."""

    def __init__(self, device, vm, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.vm = vm

        self.device = device

        self._hbox = qui.decorators.device_domain_hbox(self.vm, self.attached)
        self.add(self._hbox)

    @property
    def attached(self):
        return str(self.vm) in self.device.attachments


class DomainMenu(Gtk.Menu):
    def __init__(self, device, domains, qapp, gtk_app, **kwargs):
        super(DomainMenu, self).__init__(**kwargs)
        self.device = device
        self.domains = domains
        self.qapp = qapp
        self.gtk_app = gtk_app

        for vm in self.domains:
            if vm != device.backend_domain:
                menu_item = DomainMenuItem(self.device, vm)
                menu_item.connect('activate', self.toggle)
                self.append(menu_item)

    def toggle(self, menu_item):
        if menu_item.attached:
            self.detach_item()
        else:
            self.attach_item(menu_item)

    def attach_item(self, menu_item):
        detach_successful = self.detach_item()

        # FIXME: this sleep is nasty, but seems to be enough
        # to let devices be moved without "already attached"
        # errors
        time.sleep(1)

        if not detach_successful:
            return

        try:
            assignment = qubesadmin.devices.DeviceAssignment(
                self.device.backend_domain, self.device.ident, persistent=False)

            vm_to_attach = self.qapp.domains[str(menu_item.vm)]
            vm_to_attach.devices[menu_item.device.devclass].attach(assignment)

            self.gtk_app.emit_notification(
                _("Attaching device"),
                _("Attaching {} to {}").format(self.device.description,
                                               menu_item.vm),
                Gio.NotificationPriority.NORMAL)
        except Exception as ex:  # pylint: disable=broad-except
            self.gtk_app.emit_notification(
                _("Error"),
                _("Attaching device {0} to {1} failed. "
                  "Error: {2} - {3}").format(
                    self.device.description, menu_item.vm, type(ex).__name__,
                    ex),
                Gio.NotificationPriority.HIGH,
                error=True)
            traceback.print_exc(file=sys.stderr)

    def detach_item(self):
        for vm in self.device.attachments:
            self.gtk_app.emit_notification(
                _("Detaching device"),
                _("Detaching {} from {}").format(self.device.description, vm),
                Gio.NotificationPriority.NORMAL)
            try:
                assignment = qubesadmin.devices.DeviceAssignment(
                    self.device.backend_domain, self.device.ident,
                    persistent=False)
                self.qapp.domains[vm].devices[self.device.devclass].detach(
                    assignment)
            except qubesadmin.exc.QubesException as ex:
                self.gtk_app.emit_notification(
                    _("Error"),
                    _("Detaching device {0} from {1} failed. "
                      "Error: {2}").format(self.device.description, vm, ex),
                    Gio.NotificationPriority.HIGH,
                    error=True)
                return False
        return True


class DeviceClassItem(Gtk.MenuItem):
    """ MenuItem separating device classes. """

    def __init__(self, device_class, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device_class = device_class
        self.hbox = qui.decorators.device_class_hbox(device_class)  # type: Gtk.Box
        self.add(self.hbox)
        self.get_style_context().add_class("deviceClassMenuItem")


class DeviceItem(Gtk.MenuItem):
    """ MenuItem showing the device data and a :class:`DomainMenu`. """

    def __init__(self, device, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device = device
        self.hbox = qui.decorators.device_hbox(self.device, with_icon=False)  # type: Gtk.Box
        self.add(self.hbox)
        self.get_style_context().add_class("deviceMenuItem")



class Device:
    def __init__(self, dev):
        self.dev_name = str(dev)
        self.ident = dev.ident
        self.description = dev.description
        self.devclass = dev.devclass
        self.attachments = set()
        self.backend_domain = dev.backend_domain.name
        self.vm_icon = dev.backend_domain.label.icon

    def __str__(self):
        return self.dev_name

    def __eq__(self, other):
        return str(self) == str(other)


class VM:
    def __init__(self, vm):
        self.__hash = hash(vm)
        self.vm_name = vm.name
        self.icon = vm.label.icon

    def __str__(self):
        return self.vm_name

    def __eq__(self, other):
        return str(self) == str(other)

    def __lt__(self, other):
        return str(self) < str(other)

    def __hash__(self):
        return self.__hash


class DevicesTray(Gtk.Application):
    tray_menu = None

    def __init__(self, app_name, qapp, dispatcher, update_queue):
        super(DevicesTray, self).__init__()
        self.name = app_name

        self.devices = {}
        self.vms = set()

        self.dispatcher = dispatcher
        self.qapp = qapp
        self.update_queue = update_queue

        self.set_application_id(self.name)
        self.style()
        self.register()  # register Gtk Application

        self.initialize_vm_data()
        self.initialize_dev_data()

        for devclass in DEV_TYPES:
            self.dispatcher.add_handler('device-attach:' + devclass,
                                        self.device_attached)
            self.dispatcher.add_handler('device-detach:' + devclass,
                                        self.device_detached)
            self.dispatcher.add_handler('device-list-change:' + devclass,
                                        self.device_list_update)

        self.dispatcher.add_handler('domain-shutdown',
                                    self.vm_shutdown)
        self.dispatcher.add_handler('domain-start-failed',
                                    self.vm_shutdown)
        self.dispatcher.add_handler('domain-start', self.vm_start)
        self.dispatcher.add_handler('property-set:label', self.on_label_changed)

        self.widget_icon = Gtk.StatusIcon()
        self.widget_icon.set_from_icon_name('media-removable')
        self.widget_icon.connect('button-press-event', self.show_menu)
        self.widget_icon.set_tooltip_markup(
            _('<b>Qubes Devices</b>\nView and manage devices.'))

    def style(self):
        css = "".join([
            """.deviceClassMenuItem {border-bottom: 2px solid #eee; padding-top: 1em;}""",
            """.deviceClassMenuItem label {color: #aaa; font-size: 0.9em; letter-spacing: 0.1em;;}""",
            """.deviceMenu .deviceClassMenuItem:first-child {padding-top: 0.5em;}""",
        ]).encode("utf-8")
        style_provider = Gtk.CssProvider()
        style_provider.load_from_data(css)

        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            style_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def device_list_update(self, vm, _event, **_kwargs):
        print("device list updated")
        try:
            self.update_queue.put_nowait("update_request")
            print("added update request")
        except asyncio.QueueFull:
            print("update requests are pending; not adding to the storm")

    def initialize_vm_data(self):
        for vm in self.qapp.domains:
            if vm.klass != 'AdminVM' and vm.is_running():
                self.vms.add(VM(vm))

    def initialize_dev_data(self):
        print("idd started")
        start = time.perf_counter()
        updated_devices = {}

        # list all devices
        for domain in self.qapp.domains:
            for devclass in DEV_TYPES:
                for device in domain.devices[devclass]:
                    updated_devices[str(device)] = Device(device)

        # list existing device attachments
        for domain in self.qapp.domains:
            for devclass in DEV_TYPES:
                for device in domain.devices[devclass].attached():
                    dev = str(device)
                    if dev in updated_devices:
                        # occassionally ghost UnknownDevices appear when a
                        # device was removed but not detached from a VM
                        updated_devices[dev].attachments.add(domain.name)

        previous = set(self.devices.keys())
        current = set(updated_devices.keys())
        removals = previous - current
        for removal in removals:
            self.emit_notification(
                _("Device removed"),
                _("Device {} was removed").format(
                    self.devices[removal].description
                ),
                Gio.NotificationPriority.NORMAL)

        additions = current - previous
        for addition in additions:
            self.emit_notification(
                _("Device available"),
                _("Device {} is available").format(
                    updated_devices[addition].description),
                Gio.NotificationPriority.NORMAL)

        self.devices = updated_devices
        self.populate_menu()

        print("idd took {:.2f}s".format(time.perf_counter() - start))

    def device_attached(self, vm, _event, device, **_kwargs):
        if not vm.is_running() or device.devclass not in DEV_TYPES:
            return

        if str(device) not in self.devices:
            self.devices[str(device)] = Device(device)

        self.devices[str(device)].attachments.add(str(vm))

    def device_detached(self, vm, _event, device, **_kwargs):
        if not vm.is_running():
            return

        device = str(device)

        if device in self.devices:
            self.devices[device].attachments.discard(str(vm))

    def vm_start(self, vm, _event, **_kwargs):
        self.vms.add(VM(vm))
        for devclass in DEV_TYPES:
            for device in vm.devices[devclass].attached():
                dev = str(device)
                if dev in self.devices:
                    self.devices[dev].attachments.add(vm.name)

    def vm_shutdown(self, vm, _event, **_kwargs):
        self.vms.discard(vm)

        for dev in self.devices.values():
            dev.attachments.discard(str(vm))

    def on_label_changed(self, vm, _event, **_kwargs):
        if not vm:  # global properties changed
            return
        try:
            name = vm.name
        except qubesadmin.exc.QubesPropertyAccessError:
            return  # the VM was deleted before its status could be updated

        for domain in self.vms:
            if domain.name == name:
                domain.icon = vm.label.icon

        for device in self.devices:
            if device.backend_domain == name:
                device.vm_icon = vm.label.icon

    def populate_menu(self):
        if self.tray_menu is None:
            self.tray_menu = Gtk.Menu()
            self.tray_menu.get_style_context().add_class("deviceMenu")

        for c in self.tray_menu.get_children():
            self.tray_menu.remove(c)

        # create menu items
        menu_items = {dc: [] for dc in DEV_TYPES}
        sorted_vms = sorted(self.vms)
        for dev in self.devices.values():
            domain_menu = DomainMenu(dev, sorted_vms, self.qapp, self)
            device_menu = DeviceItem(dev)
            device_menu.set_submenu(domain_menu)
            menu_items[dev.devclass].append(device_menu)

        for device_class, device_menu_items in sorted(menu_items.items()):
            device_class_item = DeviceClassItem(device_class)
            self.tray_menu.add(device_class_item)
            device_menu_items.sort(
                key=(lambda x: x.device.devclass + str(x.device))
            )
            for item in device_menu_items:
                self.tray_menu.add(item)

        self.tray_menu.show_all()

    def show_menu(self, _unused, _event):
        self.populate_menu()
        self.tray_menu.popup_at_pointer(None)  # use current event

    def emit_notification(self, title, message, priority, error=False):
        notification = Gio.Notification.new(title)
        notification.set_body(message)
        notification.set_priority(priority)
        if error:
            notification.set_icon(Gio.ThemedIcon.new('dialog-error'))
        self.send_notification(None, notification)


async def updater(app: DevicesTray, queue: asyncio.Queue):
    while True:
        print("waiting for update request")
        await queue.get()
        print("update request received")
        count = 1
        try:
            while queue.get_nowait():
                count += 1
                print("popped extra update request {}".format(count))
        except asyncio.QueueEmpty:
            print("queue emptied")
        print("update requests received: {}".format(count))
        app.initialize_dev_data()
        while count > 0:
            queue.task_done()
            count -= 1
        print("update cycle done")


def main():
    qapp = qubesadmin.Qubes()
    dispatcher = qubesadmin.events.EventsDispatcher(qapp)

    update_queue = asyncio.Queue()

    app = DevicesTray(
        'org.qubes.qui.tray.Devices', qapp, dispatcher, update_queue)

    loop = asyncio.get_event_loop()

    worker = loop.create_task(updater(app, update_queue))

    done, _unused = loop.run_until_complete(asyncio.ensure_future(
        dispatcher.listen_for_events()))

    worker.cancel()

    exit_code = 0
    for d in done:  # pylint: disable=invalid-name
        try:
            d.result()
        except Exception:  # pylint: disable=broad-except
            exc_type, exc_value = sys.exc_info()[:2]
            dialog = Gtk.MessageDialog(
                None, 0, Gtk.MessageType.ERROR, Gtk.ButtonsType.OK)
            dialog.set_title(_("Houston, we have a problem..."))
            dialog.set_markup(_(
                "<b>Whoops. A critical error in Domains Widget has occured.</b>"
                " This is most likely a bug in the widget. To restart the "
                "widget, run 'qui-devices' in dom0."))
            dialog.format_secondary_markup(
                "\n<b>{}</b>: {}\n{}".format(
                   exc_type.__name__, exc_value, traceback.format_exc(limit=10)
                ))
            dialog.run()
            exit_code = 1
    del app
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
