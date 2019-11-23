#!/usr/bin/env python3
''' Decorators wrap a `qui.models.PropertiesModel` in a class
containing helpful representation methods.
'''
# pylint: disable=wrong-import-position,import-error

import gi  # isort:skip
gi.require_version('Gtk', '3.0')  # isort:skip
from gi.repository import Gtk, Pango  # isort:skip
from qubesadmin import exc

import gettext
t = gettext.translation("desktop-linux-manager", localedir="/usr/locales",
                        fallback=True)
_ = t.gettext


class PropertiesDecorator():
    ''' Base class for all decorators '''

    # pylint: disable=too-few-public-methods

    def __init__(self, obj, margins=(5, 5)) -> None:
        self.obj = obj
        self.margin_left = margins[0]
        self.margin_right = margins[1]
        super(PropertiesDecorator, self).__init__()

    def set_margins(self, widget):
        ''' Helper for setting the default margins on a widget '''
        widget.set_margin_left(self.margin_left)
        widget.set_margin_right(self.margin_right)


class DomainDecorator(PropertiesDecorator):
    ''' Useful methods for domain data representation '''

    def __init__(self, vm, margins=(5, 5)) -> None:
        super(DomainDecorator, self).__init__(vm, margins)
        self.vm = vm

    class VMName(Gtk.Box):
        def __init__(self, vm):
            super(DomainDecorator.VMName, self).__init__()
            self.vm = vm

            self.template_name = None
            self.netvm_name = None
            self.cur_storage = None
            self.max_storage = None

            self.updates_available = False
            self.outdated = False

            self.label = Gtk.Label(xalign=0)
            if self.vm:
                self.label.set_label(self.vm.name)
            else:
                self.label.set_markup(_('<b>Qube</b>'))
            self.pack_start(self.label, False, False, 0)

            self.outdated_icon = create_icon('outdated')
            self.updateable_icon = create_icon('software-update-available')

            self.outdated_icon.set_no_show_all(True)
            self.updateable_icon.set_no_show_all(True)

            self.updateable_icon.set_tooltip_text(_("Updates available"))
            self.outdated_icon.set_tooltip_text(
                _("Qube must be restarted to reflect changes in template"))

            self.update_outdated(False)
            self.update_updateable()

            self.pack_start(self.outdated_icon, False, False, 3)
            self.pack_start(self.updateable_icon, False, True, 3)

        def update_outdated(self, state):
            self.outdated_icon.set_visible(state)
            self.outdated = state
            self.update_tooltip()

        def update_updateable(self):
            if self.vm is None or not getattr(self.vm, 'updateable', False):
                return
            updates_state = self.vm.features.get('updates-available', False)
            self.updateable_icon.set_visible(updates_state)
            self.updates_available = updates_state
            self.update_tooltip()

        def update_tooltip(self,
                           netvm_changed=False,
                           storage_changed=False):

            if self.vm is None:
                return

            tooltip = "<b>{vmname}</b>".format(vmname=self.vm.name)

            if self.vm.klass == 'AdminVM':

                tooltip += _("\nAdministrative domain")

            else:
                if not self.template_name:
                    self.template_name = getattr(self.vm, 'template', None)
                    self.template_name = "None" if not self.template_name \
                        else str(self.template_name)

                if not self.netvm_name or netvm_changed:
                    self.netvm_name = getattr(self.vm, 'netvm', None)
                    self.netvm_name = "None" if not self.netvm_name \
                        else str(self.netvm_name)

                if not self.cur_storage or storage_changed:
                    try:
                        self.cur_storage = \
                            self.vm.get_disk_utilization() / 1024 ** 3
                    except (exc.QubesDaemonNoResponseError, KeyError):
                        self.cur_storage = 0

                if not self.max_storage or storage_changed:
                    try:
                        self.max_storage = \
                            self.vm.volumes['private'].size / 1024 ** 3
                    except (exc.QubesDaemonNoResponseError, KeyError):
                        self.max_storage = 0

                if self.max_storage == 0:
                    perc_storage = 0
                else:
                    perc_storage = self.cur_storage / self.max_storage

                tooltip += \
                    _("\nTemplate: <b>{template}</b>"
                      "\nNetworking: <b>{netvm}</b>"
                      "\nPrivate storage: <b>{current_storage:.2f}GB/"
                      "{max_storage:.2f}GB ({perc_storage:.1%})</b>").format(
                        template=self.template_name,
                        netvm=self.netvm_name,
                        current_storage=self.cur_storage,
                        max_storage=self.max_storage,
                        perc_storage=perc_storage)

                if self.outdated:
                    tooltip += _("\n\nRestart qube to "
                                 "apply changes in template.")

                if self.updates_available:
                    tooltip += _("\n\nUpdates available.")

            self.label.set_tooltip_markup(tooltip)

    def name(self):
        namebox = DomainDecorator.VMName(self.vm)
        return namebox

    class VMCPU(Gtk.Box):
        def __init__(self):
            super(DomainDecorator.VMCPU, self).__init__()

            self.cpu_label = Gtk.Label(xalign=1)
            self.cpu_label.set_width_chars(6)
            self.pack_start(self.cpu_label, True, True, 0)

        def update_state(self, cpu=0, header=False):
            if header:
                markup = _('<b>CPU</b>')
            elif cpu > 0:
                markup = '{:3d}%'.format(cpu)
            else:
                color = self.cpu_label.get_style_context() \
                            .get_color(Gtk.StateFlags.INSENSITIVE).to_color()
                markup = '<span color="{}">0%</span>'.format(color.to_string())

            self.cpu_label.set_markup(markup)

    class VMMem(Gtk.Box):
        def __init__(self):
            super(DomainDecorator.VMMem, self).__init__()
            self.mem_label = Gtk.Label(xalign=1)
            self.pack_start(self.mem_label, True, True, 0)

        def update_state(self, memory=0, header=False):
            if header:
                markup = _('<b>RAM</b>')
            else:
                markup = '{} MB'.format(str(int(memory/1024)))

            self.mem_label.set_markup(markup)

    def memory(self):
        mem_widget = DomainDecorator.VMMem()
        self.set_margins(mem_widget)

        return mem_widget

    def cpu(self):
        cpu_widget = DomainDecorator.VMCPU()
        self.set_margins(cpu_widget)

        return cpu_widget


    def icon(self) -> Gtk.Image:
        ''' Returns a `Gtk.Image` containing the colored lock icon '''
        if self.vm is None:   # should not be called
            return None
        try:
            # this is a temporary, emergency fix for unexecpected conflict with
            # qui-devices rewrite
            icon = self.vm.icon
        except AttributeError:
            icon = self.vm.label.icon
        icon_vm = Gtk.IconTheme.get_default().load_icon(
            icon, 16, 0)
        icon_img = Gtk.Image.new_from_pixbuf(icon_vm)
        return icon_img

    def netvm(self) -> Gtk.Label:
        netvm = self.vm.netvm
        if netvm is None:
            label = Gtk.Label('No', xalign=0)
        else:
            label = Gtk.Label(netvm.name, xalign=0)

        self.set_margins(label)
        return label


def device_class_hbox(device_class) -> Gtk.Box:
    ''' Returns a :class:`Gtk.Box` containing the device class name & icon.. '''
    if device_class == 'block':
        name = 'BLOCK'
        icon = 'drive-removable-media'
    elif device_class == 'mic':
        name = 'MICROPHONE'
        icon = 'audio-input-microphone'
    elif device_class == 'usb':
        name = 'USB'
        icon = 'generic-usb'
    else:
        icon = 'emblem-important'
    dev_icon = create_icon(icon)

    name_label = Gtk.Label(xalign=0)
    name_label.set_text('{}'.format(name))
    name_label.set_max_width_chars(64)
    name_label.set_ellipsize(Pango.EllipsizeMode.END)

    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    hbox.pack_start(name_label, True, True, 0)
    hbox.pack_start(dev_icon, False, True, 0)
    return hbox


def device_hbox(device, with_icon=True) -> Gtk.Box:
    ''' Returns a :class:`Gtk.Box` containing the device name & icon.. '''

    name_label = Gtk.Label(xalign=0)
    name = "{}:{} - {}".format(device.backend_domain, device.ident,
                               device.description)
    if device.attachments:
        name_label.set_markup('<b>{} ({})</b>'.format(
            name, ", ".join(list(device.attachments))))
    else:
        name_label.set_text(name)
    name_label.set_max_width_chars(64)
    name_label.set_ellipsize(Pango.EllipsizeMode.END)

    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    hbox.pack_start(name_label, True, True, 0)

    if with_icon:
        if device.devclass == 'block':
            icon = 'drive-removable-media'
        elif device.devclass == 'mic':
            icon = 'audio-input-microphone'
        elif device.devclass == 'usb':
            icon = 'generic-usb'
        else:
            icon = 'emblem-important'
        dev_icon = create_icon(icon)
        hbox.pack_start(dev_icon, False, True, 0)

    return hbox


def device_domain_hbox(vm, attached: bool) -> Gtk.Box:
    hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

    # hbox.pack_start(label, True, True, 5)

    if attached:
        eject_icon = create_icon('media-eject')
        hbox.pack_start(eject_icon, False, False, 5)
    else:
        add_icon = create_icon('list-add')
        hbox.pack_start(add_icon, False, False, 5)

    name = Gtk.Label(xalign=0)
    if attached:
        name.set_markup('<b>{}</b>'.format(vm.vm_name))
    else:
        name.set_text(vm.vm_name)

    hbox.pack_start(name, True, True, 5)
    return hbox


def create_icon(name) -> Gtk.Image:
    ''' Create an icon from string '''
    icon_dev = Gtk.IconTheme.get_default().load_icon(name, 16, 0)
    return Gtk.Image.new_from_pixbuf(icon_dev)
