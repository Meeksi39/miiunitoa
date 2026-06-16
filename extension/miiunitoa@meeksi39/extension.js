import GObject from 'gi://GObject';
import St from 'gi://St';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const SCRIPT = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'monitor-layout']);
const LAYOUT_DIR = GLib.build_filenamev([GLib.get_home_dir(), '.config', 'monitor-layouts']);

const Indicator = GObject.registerClass(
class Indicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'ミーウニトア');

        this.add_child(new St.Icon({
            icon_name: 'preferences-desktop-display-symbolic',
            style_class: 'system-status-icon',
        }));

        // Rebuild the list each time the menu opens, so newly saved
        // layouts show up without reloading the extension.
        this.menu.connect('open-state-changed', (menu, open) => {
            if (open)
                this._rebuild();
        });

        this._rebuild();
    }

    _listLayouts() {
        const names = [];
        const dir = Gio.File.new_for_path(LAYOUT_DIR);
        let en;
        try {
            en = dir.enumerate_children('standard::name', Gio.FileQueryInfoFlags.NONE, null);
        } catch (e) {
            return names; // directory missing -> no layouts yet
        }
        let info;
        while ((info = en.next_file(null)) !== null) {
            const name = info.get_name();
            if (name.endsWith('.json'))
                names.push(name.slice(0, -5));
        }
        en.close(null);
        names.sort();
        return names;
    }

    _rebuild() {
        this.menu.removeAll();

        const layouts = this._listLayouts();
        if (layouts.length === 0) {
            const item = new PopupMenu.PopupMenuItem('No saved layouts');
            item.setSensitive(false);
            this.menu.addMenuItem(item);
        } else {
            for (const name of layouts) {
                const item = new PopupMenu.PopupMenuItem(name);
                item.connect('activate', () => this._apply(name));
                this.menu.addMenuItem(item);
            }
        }

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const settings = new PopupMenu.PopupMenuItem('Display Settings…');
        settings.connect('activate', () => {
            try {
                Gio.Subprocess.new(
                    ['gnome-control-center', 'display'],
                    Gio.SubprocessFlags.NONE);
            } catch (e) {
                logError(e, 'monitor-layout: failed to open display settings');
            }
        });
        this.menu.addMenuItem(settings);
    }

    _apply(name) {
        try {
            const proc = Gio.Subprocess.new(
                [SCRIPT, 'apply', name],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
            proc.communicate_utf8_async(null, null, (p, res) => {
                try {
                    const [, , stderr] = p.communicate_utf8_finish(res);
                    if (!p.get_successful()) {
                        Main.notify('ミーウニトア',
                            `Could not apply "${name}".\n${(stderr || '').trim()}`);
                    }
                } catch (e) {
                    logError(e, 'monitor-layout: apply failed');
                }
            });
        } catch (e) {
            Main.notify('ミーウニトア', `Failed to run switcher: ${e.message}`);
        }
    }
});

export default class MonitorLayoutExtension extends Extension {
    enable() {
        this._indicator = new Indicator();
        // Add to the right status box, just left of the existing system
        // indicators (input source / language switcher live here too).
        Main.panel.addToStatusArea(this.uuid, this._indicator, 0, 'right');
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
