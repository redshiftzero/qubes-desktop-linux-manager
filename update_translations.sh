#!/bin/bash

xgettext -d desktop-linux-manager -o locales/desktop-linux-manager.pot qui/*py qui/tray/*py qui/*glade

find locales/* -maxdepth 2 -mindepth 2 -type f -iname '*.po' -exec msgmerge --update {} locales/desktop-linux-manager.pot \;
