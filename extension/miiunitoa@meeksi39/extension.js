import GObject from 'gi://GObject';
import St from 'gi://St';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import Clutter from 'gi://Clutter';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as ModalDialog from 'resource:///org/gnome/shell/ui/modalDialog.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const SCRIPT = GLib.build_filenamev([GLib.get_home_dir(), '.local', 'bin', 'monitor-layout']);
const LAYOUT_DIR = GLib.build_filenamev([GLib.get_home_dir(), '.config', 'monitor-layouts']);

const DISPLAY_CONFIG = 'org.gnome.Mutter.DisplayConfig';
const DISPLAY_CONFIG_PATH = '/org/gnome/Mutter/DisplayConfig';

const KEY_AUTO_SWITCH = 'auto-switch';
const KEY_DEFAULT = 'default-layout';
const KEY_CYCLE = 'cycle-layouts';

// Run the monitor-layout CLI; onDone(success, stdout, stderr).
function runScript(argv, onDone) {
    try {
        const proc = Gio.Subprocess.new(
            [SCRIPT, ...argv],
            Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
        proc.communicate_utf8_async(null, null, (p, res) => {
            try {
                const [, stdout, stderr] = p.communicate_utf8_finish(res);
                onDone?.(p.get_successful(), (stdout || '').trim(), (stderr || '').trim());
            } catch (e) {
                logError(e, 'monitor-layout: subprocess failed');
            }
        });
    } catch (e) {
        Main.notify('ミーウニトア', `Failed to run switcher: ${e.message}`);
    }
}

// Apply a layout by name, notifying the user only on failure.
function applyLayout(name) {
    runScript(['apply', name], (ok, _out, stderr) => {
        if (!ok)
            Main.notify('ミーウニトア', `Could not apply "${name}".\n${stderr}`);
    });
}

// Sorted list of saved layout names (reads the layout dir directly).
function layoutNames() {
    const names = [];
    let en;
    try {
        en = Gio.File.new_for_path(LAYOUT_DIR)
            .enumerate_children('standard::name', Gio.FileQueryInfoFlags.NONE, null);
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

// One-line summary of a saved layout (monitor count + connectors).
function layoutSummary(name) {
    try {
        const path = GLib.build_filenamev([LAYOUT_DIR, `${name}.json`]);
        const [ok, bytes] = GLib.file_get_contents(path);
        if (!ok)
            return '';
        const data = JSON.parse(new TextDecoder().decode(bytes));
        const conns = [];
        for (const lm of data.logical_monitors || [])
            for (const m of lm.monitors || [])
                conns.push(m.connector);
        const n = conns.length;
        return `${n} monitor${n === 1 ? '' : 's'} · ${conns.join(', ')}`;
    } catch (e) {
        return '';
    }
}

// Small text-entry dialog for "Save current layout…".
const SaveDialog = GObject.registerClass(
class SaveDialog extends ModalDialog.ModalDialog {
    _init(onSave) {
        super._init({destroyOnClose: true});
        this._onSave = onSave;

        const box = new St.BoxLayout({vertical: true, style_class: 'message-dialog-content'});
        box.add_child(new St.Label({text: 'Name for this layout:'}));
        this._entry = new St.Entry({can_focus: true, x_expand: true});
        this._entry.clutter_text.connect('activate', () => this._save());
        box.add_child(this._entry);
        this.contentLayout.add_child(box);

        this.addButton({label: 'Cancel', key: Clutter.KEY_Escape,
            action: () => this.close()});
        this.addButton({label: 'Save', default: true, action: () => this._save()});

        this.setInitialKeyFocus(this._entry.clutter_text);
    }

    _save() {
        const name = this._entry.get_text().trim();
        if (!name)
            return;
        this.close();
        this._onSave(name);
    }
});

const Indicator = GObject.registerClass(
class Indicator extends PanelMenu.Button {
    _init(settings) {
        super._init(0.0, 'ミーウニトア');
        this._settings = settings;
        this._itemsByName = new Map();

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

    _rebuild() {
        this.menu.removeAll();
        this._itemsByName.clear();

        const names = layoutNames();
        const def = this._settings.get_string(KEY_DEFAULT);

        if (names.length === 0) {
            const item = new PopupMenu.PopupMenuItem('No saved layouts');
            item.setSensitive(false);
            this.menu.addMenuItem(item);
        } else {
            for (const name of names)
                this._addLayoutItem(name, def);
        }

        this._markActive();

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const autoSwitch = new PopupMenu.PopupSwitchMenuItem(
            'Auto-switch on hotplug', this._settings.get_boolean(KEY_AUTO_SWITCH));
        autoSwitch.connect('toggled', (_item, state) =>
            this._settings.set_boolean(KEY_AUTO_SWITCH, state));
        this.menu.addMenuItem(autoSwitch);

        const saveItem = new PopupMenu.PopupMenuItem('Save current layout…');
        saveItem.connect('activate', () => this._saveCurrent());
        this.menu.addMenuItem(saveItem);

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

    _addLayoutItem(name, def) {
        const sub = new PopupMenu.PopupSubMenuMenuItem(
            name + (name === def ? '  ★' : ''));
        this._itemsByName.set(name, sub);

        const detail = new PopupMenu.PopupMenuItem(layoutSummary(name));
        detail.setSensitive(false);
        sub.menu.addMenuItem(detail);
        sub.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const apply = new PopupMenu.PopupMenuItem('Apply');
        apply.connect('activate', () => applyLayout(name));
        sub.menu.addMenuItem(apply);

        const setDefault = new PopupMenu.PopupMenuItem('Set as default');
        setDefault.connect('activate', () => {
            this._settings.set_string(KEY_DEFAULT, name === def ? '' : name);
            this._rebuild();
        });
        sub.menu.addMenuItem(setDefault);

        const del = new PopupMenu.PopupMenuItem('Delete');
        del.connect('activate', () => {
            runScript(['delete', name], () => this._rebuild());
        });
        sub.menu.addMenuItem(del);

        this.menu.addMenuItem(sub);
    }

    // Mark the layout matching the live config with a check ornament.
    _markActive() {
        runScript(['active'], (ok, out) => {
            if (!ok || !out)
                return;
            const item = this._itemsByName.get(out);
            if (item) {
                try {
                    item.setOrnament(PopupMenu.Ornament.CHECK);
                } catch (e) {
                    // item may have been destroyed by a rebuild; ignore
                }
            }
        });
    }

    _saveCurrent() {
        const dialog = new SaveDialog((name) => {
            runScript(['save', name], (ok, _out, stderr) => {
                if (!ok)
                    Main.notify('ミーウニトア', `Could not save "${name}".\n${stderr}`);
            });
        });
        dialog.open();
    }
});

export default class MonitorLayoutExtension extends Extension {
    enable() {
        this._settings = this.getSettings();
        this._cycleIndex = -1;
        this._pendingId = 0;

        this._indicator = new Indicator(this._settings);
        // Add to the right status box, just left of the existing system
        // indicators (input source / language switcher live here too).
        Main.panel.addToStatusArea(this.uuid, this._indicator, 0, 'right');

        Main.wm.addKeybinding(
            KEY_CYCLE, this._settings, Meta.KeyBindingFlags.NONE,
            Shell.ActionMode.NORMAL | Shell.ActionMode.OVERVIEW,
            () => this._cycle());

        this._dbusSub = Gio.DBus.session.signal_subscribe(
            DISPLAY_CONFIG, DISPLAY_CONFIG, 'MonitorsChanged', DISPLAY_CONFIG_PATH,
            null, Gio.DBusSignalFlags.NONE,
            () => this._onMonitorsChanged());
    }

    disable() {
        if (this._dbusSub) {
            Gio.DBus.session.signal_unsubscribe(this._dbusSub);
            this._dbusSub = 0;
        }
        if (this._pendingId) {
            GLib.source_remove(this._pendingId);
            this._pendingId = 0;
        }
        Main.wm.removeKeybinding(KEY_CYCLE);
        this._indicator?.destroy();
        this._indicator = null;
        this._settings = null;
    }

    _cycle() {
        const names = layoutNames();
        if (names.length === 0) {
            Main.notify('ミーウニトア', 'No saved layouts to cycle through.');
            return;
        }
        this._cycleIndex = (this._cycleIndex + 1) % names.length;
        applyLayout(names[this._cycleIndex]);
    }

    // Hotplug: mutter fires MonitorsChanged in bursts, so debounce, then
    // apply the layout that matches the now-connected monitors.
    _onMonitorsChanged() {
        if (this._pendingId)
            GLib.source_remove(this._pendingId);
        this._pendingId = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 1500, () => {
            this._pendingId = 0;
            if (this._settings?.get_boolean(KEY_AUTO_SWITCH))
                this._autoSwitch();
            return GLib.SOURCE_REMOVE;
        });
    }

    _autoSwitch() {
        const def = this._settings.get_string(KEY_DEFAULT);
        const argv = ['match', '--apply'];
        if (def)
            argv.push('--prefer', def);
        runScript(argv, (ok, out, stderr) => {
            if (ok) {
                // Notify only when a layout was actually applied. A no-op
                // ("already active") prints a different line and stays quiet.
                const m = out.match(/Applied layout '(.+)'/);
                if (m)
                    Main.notify('ミーウニトア', `Applied "${m[1]}".`);
            } else if (stderr && !stderr.startsWith('No saved layout')) {
                // Ambiguous match or real error — worth surfacing. A plain
                // "no match" is normal on hotplug and stays silent.
                Main.notify('ミーウニトア', stderr);
            }
        });
    }
}
