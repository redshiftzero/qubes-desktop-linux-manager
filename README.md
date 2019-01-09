# Widgets

Available widgets are:
- `qui-domains` - Domains Widget, manages running qubes
- `qui-devices` - Devices Widget, manages attachment/detachment for devices
- `qui-disk-space` - Disk Space Widget, warns about low disk space
- `qui-updates` - Updater Widger, notifies about available updates

## How to run

The widgets should be always available in the widget area of the desktop manager.
They are run (and restarted on crash) by systemd services:
- qubes-widget@qui-domains
- qubes-widget@qui-devices
- qubes-widget@qui-disk-space
- qubes-widget@qui-updates

In case of problems, you can view system log with `journalctl --user -u qubes-widget@[widget_name]`.
