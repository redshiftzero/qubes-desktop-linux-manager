# pylint: disable=wrong-import-position,import-error
import sys
import gi
gi.require_version('Gtk', '3.0')  # isort:skip
from gi.repository import Gtk, GObject, Gio  # isort:skip
from qubesadmin import Qubes
from qubesadmin.utils import size_to_human

# TODO: add configurable warning levels
WARN_LEVEL = 0.9
URGENT_WARN_LEVEL = 0.95


class PoolUsageData:
    def __init__(self):
        self.qubes_app = Qubes()

        self.pools = []
        self.total_size = 0
        self.used_size = 0
        self.warning_message = []

        self.__populate_pools()

    def __populate_pools(self):
        for pool in sorted(self.qubes_app.pools.values()):
            self.pools.append(pool)
            if not pool.size or 'included_in' in pool.config:
                continue
            self.total_size += pool.size
            self.used_size += pool.usage
            if pool.usage/pool.size >= URGENT_WARN_LEVEL:
                self.warning_message.append(
                    "\n{:.1%} space left in pool {}".format(
                        1-pool.usage/pool.size, pool.name))

    def get_pools_widgets(self):
        for p in self.pools:
            yield self.__create_box(p)

    def get_warning(self):
        return self.warning_message

    def get_usage(self):
        return self.used_size/self.total_size

    @staticmethod
    def __create_box(pool):
        pool_name = Gtk.Label(xalign=0)
        percentage_use = Gtk.Label()
        numeric_use = Gtk.Label()

        if pool.size and 'included_in' not in pool.config:
            pool_name.set_markup('<b>{}</b>'.format(pool.name))

            percentage = pool.usage/pool.size
            percentage_use.set_markup(colored_percentage(percentage))
            percentage_use.set_justify(Gtk.Justification.RIGHT)

            numeric_use.set_markup(
                '<span color=\'grey\'><i>{}/{}</i></span>'.format(
                    size_to_human(pool.usage),
                    size_to_human(pool.size)))
            numeric_use.set_justify(Gtk.Justification.RIGHT)

        else:
            pool_name.set_markup(
                '<span color=\'grey\'><i>{}</i></span>'.format(pool.name))

        pool_name.set_margin_left(20)

        return pool_name, percentage_use, numeric_use


def colored_percentage(value):
    if value < WARN_LEVEL:
        color = 'green'
    elif value < URGENT_WARN_LEVEL:
        color = 'orange'
    else:
        color = 'red'

    result = '<span color=\'{}\'>{:.1%}</span>'.format(color, value)

    return result


class DiskSpace(Gtk.Application):
    def __init__(self, **properties):
        super().__init__(**properties)

        self.warned = False

        self.set_application_id("org.qubes.qui.tray.DiskSpace")
        self.register()

        self.icon = Gtk.StatusIcon()
        self.icon.connect('button-press-event', self.make_menu)
        self.refresh_icon()

        GObject.timeout_add_seconds(120, self.refresh_icon)

        Gtk.main()

    def refresh_icon(self):
        pool_data = PoolUsageData()
        warning = pool_data.get_warning()

        if warning:
            self.icon.set_from_icon_name("dialog-warning")
            text = "<b>Qubes Disk Space Monitor</b>\nWARNING! You are running" \
                   " out of disk space." + ''.join(warning)
            self.icon.set_tooltip_markup(text)

            if not self.warned:
                notification = Gio.Notification.new("Disk usage warning!")
                notification.set_priority(Gio.NotificationPriority.HIGH)
                notification.set_body(
                    "You are running out of disk space." + ''.join(warning))
                notification.set_icon(
                    Gio.ThemedIcon.new('dialog-warning'))

                self.send_notification(None, notification)
                self.warned = True

        else:
            self.icon.set_from_icon_name("drive-harddisk")
            self.icon.set_tooltip_markup(
                '<b>Qubes Disk Space Monitor</b>\nView free disk space.')
            self.warned = False

        return True  # needed for Gtk to correctly loop the function

    def make_menu(self, _, _event):
        pool_data = PoolUsageData()

        menu = Gtk.Menu()

        menu.append(self.make_top_box(pool_data))

        title_label = Gtk.Label(xalign=0)
        title_label.set_markup("<b>Volumes</b>")
        title_menu_item = Gtk.MenuItem()
        title_menu_item.add(title_label)
        title_menu_item.set_sensitive(False)
        menu.append(title_menu_item)

        grid = Gtk.Grid()
        col_no = 0
        for (label1, label2, label3) in pool_data.get_pools_widgets():
            grid.attach(label1, 0, col_no, 1, 1)
            grid.attach(label2, 1, col_no, 1, 1)
            grid.attach(label3, 2, col_no, 1, 1)
            col_no += 1

        grid.set_column_spacing(20)
        grid_menu_item = Gtk.MenuItem()
        grid_menu_item.add(grid)
        grid_menu_item.set_sensitive(False)
        menu.append(grid_menu_item)

        menu.set_reserve_toggle_size(False)

        menu.show_all()
        menu.popup_at_pointer(None)  # use current event

    @staticmethod
    def make_top_box(pool_data):
        grid = Gtk.Grid()

        name_label = Gtk.Label(xalign=0)
        name_label.set_markup("<b>Total disk usage</b>")

        percentage_value = Gtk.Label()
        percentage_value.set_markup(colored_percentage(pool_data.get_usage()))
        percentage_value.set_margin_top(10)

        progress_bar = Gtk.LevelBar()
        progress_bar.set_min_value(0)
        progress_bar.set_max_value(100)
        progress_bar.set_value(pool_data.get_usage()*100)
        progress_bar.set_vexpand(True)
        progress_bar.set_hexpand(True)
        progress_bar.set_margin_left(20)
        progress_bar.set_margin_right(10)
        progress_bar.set_margin_top(10)

        grid.attach(name_label, 0, 0, 1, 1)
        grid.attach(progress_bar, 0, 1, 1, 1)
        grid.attach(percentage_value, 1, 1, 1, 1)

        progress_bar_item = Gtk.MenuItem()
        progress_bar_item.add(grid)

        progress_bar_item.set_sensitive(False)

        return progress_bar_item


def main():
    app = DiskSpace()
    app.run()


if __name__ == '__main__':
    sys.exit(main())
