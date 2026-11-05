#!/usr/bin/env python3

import gi, os, json, sys, dbus, subprocess, re
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from multiprocessing import Process

gi.require_version('Gtk', '3.0')
try:
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3
    HAS_APP_INDICATOR = True
except (ValueError, ImportError):
    HAS_APP_INDICATOR = False
from gi.repository import Gtk, GdkPixbuf, GLib


class DBUSService(dbus.service.Object):
    def __init__(self, window):
        self.window = window
        bus_name = dbus.service.BusName('me.linuxheki.xmrigui', bus=dbus.SessionBus())
        dbus.service.Object.__init__(self, bus_name, '/me/linuxheki/xmrigui')
        args = ''
        for i, arg in enumerate(sys.argv):
            if i > 1: args += f' {arg}'
            elif i > 0: args += arg
        self.args_manager(args)

    @dbus.service.method('me.linuxheki.xmrigui', in_signature='s')
    def startup(self, args):
        self.args_manager(args)

    def args_manager(self, args):
        args = args.split(' ')

        start = False
        stop = False
        close_window = False
        open_window = False
        for arg in args:
            if arg == 'stop': stop = True
            if arg == 'start': start = True
            if arg == '--close': close_window = True
            if arg == '--open': open_window = True

        if stop:
            for profile in self.profiles:
                self.window.widgets[profile]['mine_switch'].set_active(False)
        elif start:
            for profile in self.profiles:
                self.window.widgets[profile]['mine_switch'].set_active(True)
        if close_window: self.window.hide()
        elif open_window:
            self.window.show_window()

def call_instance():
    try:
        bus = dbus.SessionBus()
        programinstance = bus.get_object('me.linuxheki.xmrigui',  '/me/linuxheki/xmrigui')
        startup = programinstance.get_dbus_method('startup', 'me.linuxheki.xmrigui')
        args = ''
        for i, arg in enumerate(sys.argv):
            if i > 1: args += f' {arg}'
            elif i > 0: args += arg

        startup(args)
        print('Another instance was running and notified.')
    except dbus.exceptions.DBusException:
        exit(-1)


class Window(Gtk.Window):
    def __init__(self):
        super().__init__()
        self.widgets = {}
        self.processes = {}
        self.load_data()
        self._initialize_profile_widgets() # Initialize widgets before config and mining calls
        self.config = self.get_config()
        self.stop_mining(self.profiles[0], restart=False, save=False)
        if self.config[self.profiles[0]]['mine']: self.start_mining(self.profiles[0], save=False)
        if self.config[self.profiles[1]]['mine']: self.start_mining(self.profiles[1], save=False)
        if self.config[self.profiles[2]]['mine']: self.start_mining(self.profiles[2], save=False)
        self.show_window() # Always show the window unless explicitly closed by D-Bus args

    def get_config(self):
        try:
            with open(self.settings_path, 'r') as f: pass
            try:
                with open(self.settings_path, 'r') as f:
                    config = json.loads(f.read())
                    test = config[self.profiles[2]]
                return config
            except:
                with open(self.settings_path, 'w') as f:
                    f.write(self.raw_config)
                return json.loads(self.raw_config)
        except:
            with open(self.settings_path, 'x'): pass
            with open(self.settings_path, 'w') as f: f.write(self.raw_config)
            return json.loads(self.raw_config)

    def start_mining(self, profile, save=True):
        if save:
            self.config[profile]['mine'] = True
            self.save(restart=False)
        self.widgets[profile]['status_label'].set_text('Status: Mining...')

        args = ''
        if not self.config[profile]['default_args']:
            args += f' --algo={self.algos[self.config[profile]["coin"]]}'
            args += f' --url={self.config[profile]["pool"]}'
            args += f' --user={self.config[profile]["user"]}'
            args += f' --pass={self.config[profile]["password"]}'
            args += f' --donate-level={self.config[profile]["donate"]}'
            if (self.config[profile]['threads'] != '0') or (not self.config[profile]['threads']): args += f' --threads={self.config[profile]["threads"]} --randomx-init={self.config[profile]["threads"]}'
            if self.config[profile]['cuda']: args += f' --cuda --cuda-loader={self.cuda_plugin_path}'
            if self.config[profile]['opencl']: args += ' --opencl'
            if not self.config[profile]['cpu']: args += ' --no-cpu'
        if self.config[profile]['args']: args += f' {self.config[profile]["args"]}'

        # Start XMRig and capture output
        cmd = f"{self.xmrig_path} --no-color {args}"
        try:
            self.processes[profile] = subprocess.Popen(
                cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            # Watch the output pipe for new lines
            GLib.io_add_watch(self.processes[profile].stdout, GLib.IO_IN | GLib.IO_HUP, self.update_log, profile)
        except Exception as e:
            self.widgets[profile]['status_label'].set_text(f"Error: {str(e)}")

    def stop_mining(self, profile, restart=True, save=True):
        os.system('killall xmrig')
        if profile in self.processes:
            del self.processes[profile]

        self.widgets[profile]['status_label'].set_text('Status: Stopped.')
        if restart:
            if profile == self.profiles[0] and self.config[self.profiles[1]]['mine']: self.start_mining(self.profiles[1], save=False)
            if profile == self.profiles[0] and self.config[self.profiles[2]]['mine']: self.start_mining(self.profiles[2], save=False)
            if profile == self.profiles[1] and self.config[self.profiles[0]]['mine']: self.start_mining(self.profiles[0], save=False)
            if profile == self.profiles[1] and self.config[self.profiles[2]]['mine']: self.start_mining(self.profiles[2], save=False)
            if profile == self.profiles[2] and self.config[self.profiles[0]]['mine']: self.start_mining(self.profiles[0], save=False)
            if profile == self.profiles[2] and self.config[self.profiles[1]]['mine']: self.start_mining(self.profiles[1], save=False)

        if save:
            self.config[profile]['mine'] = False
            self.save(restart=False)

    def save(self, restart=True):
        try:
            for profile in self.profiles:
                self.config[profile]['pool'] = self.widgets[profile]['pool_entry'].get_text()
                self.config[profile]['user'] = self.widgets[profile]['user_entry'].get_text()
                self.config[profile]['password'] = self.widgets[profile]['pass_entry'].get_text()
                self.config[profile]['donate'] = self.widgets[profile]['donate_entry'].get_text()
                self.config[profile]['threads'] = self.widgets[profile]['threads_entry'].get_text()
                self.config[profile]['cuda'] = self.widgets[profile]['cuda_switch'].get_active()
                self.config[profile]['opencl'] = self.widgets[profile]['opencl_switch'].get_active()
                self.config[profile]['cpu'] = self.widgets[profile]['cpu_switch'].get_active()
                self.config[profile]['args'] = self.widgets[profile]['args_entry'].get_text()
                self.config[profile]['default_args'] = self.widgets[profile]['default_args_switch'].get_active()
                self.config[profile]['coin'] = self.widgets[profile]['crypto_chooser'].get_active()
        except:
            pass

        with open(self.settings_path, 'w') as f: f.write(json.dumps(self.config))

        if restart:
            for profile in self.profiles:
                if self.config[profile]['mine']:
                    self.stop_mining(profile, save=False)
                    self.start_mining(profile, save=False)

    def show_window(self):
        self.draw()
        if not self.get_visible():
            self.show_all()

    def hide_window(self, widget):
        self.hide()

    def draw(self):
        self.set_title('XMRiGUI v1.8.3')
        self.icon = GdkPixbuf.Pixbuf.new_from_file(filename=self.icon_path)
        self.set_icon(self.icon)
        self.set_border_width(20)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)


        for profile in self.profiles:
            self.widgets[profile]['box'] = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=30)
            self.widgets[profile]['main_box'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)

            self.widgets[profile]['pixbuf'] = GdkPixbuf.Pixbuf.new_from_file_at_scale(filename=self.icon_path, width=128, height=128, preserve_aspect_ratio=True)
            self.widgets[profile]['image'] = Gtk.Image.new_from_pixbuf(self.widgets[profile]['pixbuf'])
            self.widgets[profile]['name'] = Gtk.Label()
            self.widgets[profile]['name'].set_markup('<big>XMRiGUI</big>\nmade by Freetime Maker\n<a href="https://github.com/FreetimeMaker/XMRiGUI">Source code</a>')

            self.widgets[profile]['mine_box'] = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            self.widgets[profile]['mine_label'] = Gtk.Label()
            self.widgets[profile]['mine_label'].set_markup('<big>Mine</big>')
            self.widgets[profile]['mine_switch'] = Gtk.Switch()
            self.widgets[profile]['mine_switch'].set_active(self.config[profile]['mine'])
            if profile == self.profiles[0]: self.widgets[profile]['mine_switch'].connect('state-set', self.on_mine_switch0)
            elif profile == self.profiles[1]: self.widgets[profile]['mine_switch'].connect('state-set', self.on_mine_switch1)
            elif profile == self.profiles[2]: self.widgets[profile]['mine_switch'].connect('state-set', self.on_mine_switch2)
            self.widgets[profile]['mine_switch'].props.valign = Gtk.Align.CENTER

            self.widgets[profile]['mine_box'].pack_start(self.widgets[profile]['mine_label'], False, False, 10)
            self.widgets[profile]['mine_box'].pack_start(self.widgets[profile]['mine_switch'], False, False, 10)
            self.widgets[profile]['mine_box'].pack_start(self.widgets[profile]['status_label'], False, False, 10)
            self.widgets[profile]['mine_box'].pack_start(self.widgets[profile]['info_label'], False, False, 10)
            self.widgets[profile]['main_box'].pack_start(self.widgets[profile]['image'], False, False, 10)
            self.widgets[profile]['main_box'].pack_start(self.widgets[profile]['name'], False, False, 10)
            self.widgets[profile]['main_box'].pack_start(self.widgets[profile]['mine_box'], False, False, 10)

            # Log Output View
            self.widgets[profile]['log_expander'] = Gtk.Expander(label='Miner Output (Live)')
            self.widgets[profile]['log_view'] = Gtk.TextView(buffer=self.widgets[profile]['log_buffer'])
            self.widgets[profile]['log_view'].set_editable(False)
            self.widgets[profile]['log_scroll'] = Gtk.ScrolledWindow()
            self.widgets[profile]['log_scroll'].set_min_content_height(150)
            self.widgets[profile]['log_scroll'].add(self.widgets[profile]['log_view'])
            self.widgets[profile]['log_expander'].add(self.widgets[profile]['log_scroll'])

            self.widgets[profile]['settings'] = Gtk.Grid(column_homogeneous=True, column_spacing=10, row_spacing=10)

            self.widgets[profile]['pool_box'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            self.widgets[profile]['pool_label'] = Gtk.Label(label='Pool:')
            self.widgets[profile]['pool_entry'] = Gtk.Entry()
            self.widgets[profile]['pool_entry'].set_text(self.config[profile]['pool'])
            self.widgets[profile]['pool_box'].pack_start(self.widgets[profile]['pool_label'], False, False, 10)
            self.widgets[profile]['pool_box'].pack_start(self.widgets[profile]['pool_entry'], True, True, 0)

            self.widgets[profile]['user_box'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            self.widgets[profile]['user_label'] = Gtk.Label(label='User:')
            self.widgets[profile]['user_entry'] = Gtk.Entry()
            self.widgets[profile]['user_entry'].set_text(self.config[profile]['user'])
            self.widgets[profile]['user_box'].pack_start(self.widgets[profile]['user_label'], False, False, 10)
            self.widgets[profile]['user_box'].pack_start(self.widgets[profile]['user_entry'], True, True, 0)

            self.widgets[profile]['pass_box'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            self.widgets[profile]['pass_label'] = Gtk.Label(label='Password:')
            self.widgets[profile]['pass_entry'] = Gtk.Entry()
            self.widgets[profile]['pass_entry'].set_text(self.config[profile]['password'])
            self.widgets[profile]['pass_box'].pack_start(self.widgets[profile]['pass_label'], False, False, 10)
            self.widgets[profile]['pass_box'].pack_start(self.widgets[profile]['pass_entry'], True, True, 0)

            self.widgets[profile]['donate_box'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            self.widgets[profile]['donate_label'] = Gtk.Label(label='Donate:')
            self.widgets[profile]['donate_entry'] = Gtk.Entry()
            self.widgets[profile]['donate_entry'].set_text(self.config[profile]['donate'])
            self.widgets[profile]['donate_box'].pack_start(self.widgets[profile]['donate_label'], False, False, 10)
            self.widgets[profile]['donate_box'].pack_start(self.widgets[profile]['donate_entry'], True, True, 0)

            self.widgets[profile]['threads_box'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            self.widgets[profile]['threads_label'] = Gtk.Label(label='Threads:')
            self.widgets[profile]['threads_entry'] = Gtk.Entry()
            self.widgets[profile]['threads_entry'].set_text(self.config[profile]['threads'])
            self.widgets[profile]['threads_box'].pack_start(self.widgets[profile]['threads_label'], False, False, 10)
            self.widgets[profile]['threads_box'].pack_start(self.widgets[profile]['threads_entry'], True, True, 0)

            self.widgets[profile]['save_button'] = Gtk.Button(label='Save')
            self.widgets[profile]['save_button'].connect('clicked', self.on_save)

            self.widgets[profile]['settings'].attach(self.widgets[profile]['pool_box'], 0,0,1,1)
            self.widgets[profile]['settings'].attach(self.widgets[profile]['user_box'], 0,1,1,1)
            self.widgets[profile]['settings'].attach(self.widgets[profile]['pass_box'], 0,2,1,1)
            self.widgets[profile]['settings'].attach(self.widgets[profile]['donate_box'], 1,0,1,1)
            self.widgets[profile]['settings'].attach(self.widgets[profile]['threads_box'], 1,1,1,1)
            self.widgets[profile]['settings'].attach(self.widgets[profile]['save_button'], 1,2,1,1)

            self.widgets[profile]['advanched_settings'] = Gtk.Expander(label='Advanched options')
            self.widgets[profile]['advanched_box'] = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.widgets[profile]['advanched_grid'] = Gtk.Grid(column_homogeneous=True, row_spacing=10)

            self.widgets[profile]['cuda_box'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            self.widgets[profile]['cuda_label'] = Gtk.Label(label='NVidia GPU')
            self.widgets[profile]['cuda_switch'] = Gtk.Switch()
            self.widgets[profile]['cuda_switch'].set_active(self.config[profile]['cuda'])
            self.widgets[profile]['cuda_switch'].connect('state-set', self.on_save)
            self.widgets[profile]['cuda_box'].pack_start(self.widgets[profile]['cuda_label'], False, False, 10)
            self.widgets[profile]['cuda_box'].pack_start(self.widgets[profile]['cuda_switch'], False, False, 10)

            self.widgets[profile]['opencl_box'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            self.widgets[profile]['opencl_label'] = Gtk.Label(label='AMD GPU')
            self.widgets[profile]['opencl_switch'] = Gtk.Switch()
            self.widgets[profile]['opencl_switch'].set_active(self.config[profile]['opencl'])
            self.widgets[profile]['opencl_switch'].connect('state-set', self.on_save)
            self.widgets[profile]['opencl_box'].pack_start(self.widgets[profile]['opencl_label'], False, False, 10)
            self.widgets[profile]['opencl_box'].pack_start(self.widgets[profile]['opencl_switch'], False, False, 10)

            self.widgets[profile]['cpu_box'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            self.widgets[profile]['cpu_label'] = Gtk.Label(label='CPU')
            self.widgets[profile]['cpu_switch'] = Gtk.Switch()
            self.widgets[profile]['cpu_switch'].set_active(self.config[profile]['cpu'])
            self.widgets[profile]['cpu_switch'].connect('state-set', self.on_save)
            self.widgets[profile]['cpu_box'].pack_start(self.widgets[profile]['cpu_label'], False, False, 10)
            self.widgets[profile]['cpu_box'].pack_start(self.widgets[profile]['cpu_switch'], False, False, 10)

            self.widgets[profile]['crypto_chooser'] = Gtk.ComboBoxText()
            self.widgets[profile]['crypto_chooser'].set_entry_text_column(0)
            for crypto in self.cryptos: self.widgets[profile]['crypto_chooser'].append_text(crypto)
            self.widgets[profile]['crypto_chooser'].set_active(self.config[profile]['coin'])
            self.widgets[profile]['crypto_chooser'].connect('changed', self.on_save)

            self.widgets[profile]['default_args_box'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            self.widgets[profile]['default_args_label'] = Gtk.Label(label='Disable default args')
            self.widgets[profile]['default_args_switch'] = Gtk.Switch()
            self.widgets[profile]['default_args_switch'].set_active(self.config[profile]['default_args'])
            self.widgets[profile]['default_args_switch'].connect('state-set', self.on_save)
            self.widgets[profile]['default_args_box'].pack_start(self.widgets[profile]['default_args_label'], False, False, 10)
            self.widgets[profile]['default_args_box'].pack_start(self.widgets[profile]['default_args_switch'], False, False, 10)

            self.widgets[profile]['args_box'] = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
            self.widgets[profile]['args_label'] = Gtk.Label(label='Additional args:')
            self.widgets[profile]['args_entry'] = Gtk.Entry()
            self.widgets[profile]['args_entry'].set_text(self.config[profile]['args'])
            self.widgets[profile]['args_box'].pack_start(self.widgets[profile]['args_label'], False, False, 10)
            self.widgets[profile]['args_box'].pack_start(self.widgets[profile]['args_entry'], True, True, 0)

            self.widgets[profile]['advanched_save_button'] = Gtk.Button(label='Save')
            self.widgets[profile]['advanched_save_button'].connect('clicked', self.on_save)

            self.widgets[profile]['advanched_grid'].attach(self.widgets[profile]['cuda_box'], 0,0,1,2)
            self.widgets[profile]['advanched_grid'].attach(self.widgets[profile]['opencl_box'], 0,2,1,2)
            self.widgets[profile]['advanched_grid'].attach(self.widgets[profile]['cpu_box'], 0,4,1,2)
            self.widgets[profile]['advanched_grid'].attach(self.widgets[profile]['crypto_chooser'], 1,0,1,3)
            self.widgets[profile]['advanched_grid'].attach(self.widgets[profile]['default_args_box'], 1,4,1,2)
            self.widgets[profile]['advanched_grid'].attach(self.widgets[profile]['args_box'], 0,6,2,1)
            self.widgets[profile]['advanched_grid'].attach(self.widgets[profile]['advanched_save_button'], 0,7,2,1)
            self.widgets[profile]['advanched_box'].pack_start(self.widgets[profile]['advanched_grid'], False, False, 10)
            self.widgets[profile]['advanched_settings'].add(self.widgets[profile]['advanched_box'])

            self.widgets[profile]['box'].pack_start(self.widgets[profile]['main_box'], False, False, 10)
            self.widgets[profile]['box'].pack_start(self.widgets[profile]['settings'], False, False, 10)
            self.widgets[profile]['box'].pack_start(self.widgets[profile]['advanched_settings'], False, False, 10)
            self.widgets[profile]['box'].pack_start(self.widgets[profile]['log_expander'], True, True, 10)



        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(850)
        self.stack.add_titled(self.widgets[self.profiles[0]]['box'], self.profiles[0], 'Profile 1')
        self.stack.add_titled(self.widgets[self.profiles[1]]['box'], self.profiles[1], 'Profile 2')
        self.stack.add_titled(self.widgets[self.profiles[2]]['box'], self.profiles[2], 'Profile 3')
        self.stack_switcher = Gtk.StackSwitcher()
        self.stack_switcher.set_stack(self.stack)
        self.box.pack_start(self.stack_switcher, False, False, 10)
        self.box.pack_start(self.stack, False, False, 10)
        self.add(self.box)

    def on_mine_switch0(self, widget, state):
        if state:
            self.start_mining(self.profiles[0])
        else: self.stop_mining(self.profiles[0])

    def on_mine_switch1(self, widget, state):
        if state:
            self.start_mining(self.profiles[1])
        else: self.stop_mining(self.profiles[1])

    def on_mine_switch2(self, widget, state):
        if state:
            self.start_mining(self.profiles[2])
        else: self.stop_mining(self.profiles[2])

    def on_save(self, widget, state=None):
        self.save()

    def profile0_menu(self, widget):
        if self.config[self.profiles[0]]['mine']: self.stop_mining(self.profiles[0])
        else: self.start_mining(self.profiles[0])

    def profile1_menu(self, widget):
        if self.config[self.profiles[1]]['mine']: self.stop_mining(self.profiles[1])
        else: self.start_mining(self.profiles[1])

    def profile2_menu(self, widget):
        if self.config[self.profiles[2]]['mine']: self.stop_mining(self.profiles[2])
        else: self.start_mining(self.profiles[2])

    def update_log(self, source, condition, profile):
        if condition & GLib.IO_HUP:
            return False

        line = source.readline().decode('utf-8', errors='replace')
        if line:
            buffer = self.widgets[profile]['log_buffer']
            lower_line = line.lower()

            # Farbschema bestimmen
            tag = None
            if "accepted" in lower_line:
                tag = "success"
            elif "error" in lower_line or "rejected" in lower_line or "failed" in lower_line:
                tag = "error"
            elif "net" in lower_line or "pool" in lower_line:
                tag = "info"
            elif "speed" in lower_line:
                tag = "warning"

            # Text mit Farbe einfügen
            if tag:
                buffer.insert_with_tags_by_name(buffer.get_end_iter(), line, tag)
            else:
                buffer.insert(buffer.get_end_iter(), line)

            # Limit buffer to last 500 lines
            if buffer.get_line_count() > 500:
                buffer.delete(buffer.get_start_iter(), buffer.get_iter_at_line(1))

            # Auto-scroll
            adj = self.widgets[profile]['log_scroll'].get_vadjustment()
            adj.set_value(adj.get_upper() - adj.get_page_size())

            # Suche nach Hashrate und Shares
            speed_match = re.search(r"speed 10s/60s/15m\s+([\d.]+)", line)
            if speed_match:
                self.widgets[profile]['last_speed'] = speed_match.group(1)

            shares_match = re.search(r"accepted\s+\((\d+)/(\d+)\)", line)
            if shares_match:
                self.widgets[profile]['last_shares'] = f"{shares_match.group(1)}/{shares_match.group(2)}"

            # Labels aktualisieren
            speed = self.widgets[profile].get('last_speed', '0.0')
            shares = self.widgets[profile].get('last_shares', '0/0')
            self.widgets[profile]['info_label'].set_markup(f"<b>Speed:</b> {speed} H/s | <b>Shares:</b> {shares}")

            # Erweiterte Status-Anzeige
            if "connected to" in lower_line:
                pool_addr = re.search(r"to\s+([^\s]+)", line)
                status_text = f"Status: Connected with {pool_addr.group(1) if pool_addr else 'Pool'}"
                self.widgets[profile]['status_label'].set_text(status_text)
            elif "new job" in lower_line:
                self.widgets[profile]['status_label'].set_text("Status: Neuer Job erhalten")
            elif "ready" in lower_line:
                self.widgets[profile]['status_label'].set_text("Status: Bereit")
            elif "accepted" in lower_line:
                self.widgets[profile]['status_label'].set_text("Status: Mining (Share akzeptiert!)")

            return True
        return False

    def _initialize_profile_widgets(self):
        """Initializes basic widgets for each profile, especially status labels."""
        for profile in self.profiles:
            self.widgets[profile] = {}
            self.widgets[profile]['status_label'] = Gtk.Label()
            self.widgets[profile]['status_label'].set_text('Status: Initializing...') # Default status before actual state is known
            self.widgets[profile]['info_label'] = Gtk.Label()
            self.widgets[profile]['info_label'].set_markup('<b>Speed:</b> 0 H/s | <b>Shares:</b> 0/0')

            # Log Buffer mit Farbtags initialisieren
            buffer = Gtk.TextBuffer()
            buffer.create_tag("info", foreground="#3498db")    # Blau für Netzwerk
            buffer.create_tag("success", foreground="#2ecc71") # Grün für Shares
            buffer.create_tag("warning", foreground="#f1c40f") # Gelb für Speed-Updates
            buffer.create_tag("error", foreground="#e74c3c")   # Rot für Fehler
            self.widgets[profile]['log_buffer'] = buffer
    def load_data(self):
        self.user = os.environ.get('USER') or 'user'
        self.settings_path = os.path.expanduser('~/.config/xmrigui.json')
        self.xmrig_path = '/opt/xmrigui/xmrig'
        self.icon_path = '/usr/share/icons/hicolor/256x256/apps/xmrigui.png'
        if not os.path.exists(self.icon_path):
            self.icon_path = 'xmrigui.png' # Fallback auf lokales Icon
        self.cuda_plugin_path = '/opt/xmrigui/libxmrig-cuda.so'
        self.profiles = ['profile-0', 'profile-1', 'profile-2']
        self.cryptos = [
            'Monero',
            'Ravencoin',
            'Uplexa',
            'Chukwa',
            'Chukwa v2',
            'CCX',
            'Keva',
            'Dero',
            'Talleo',
            'Safex',
            'ArQmA',
            'NINJA',
            'Raptoreum',
            'Wownero',
            'Scala',
            'Haven Protocol',
            'MoneroV',
            'Epic Cash',
            'Graft',
            'Oxen',
            'Stellite'
        ]
        self.algos = [
            'rx/0',
            'kawpow',
            'cn/upx2',
            'argon2/chukwa',
            'argon2/chukwav2',
            'cn/ccx',
            'rx/keva',
            'astrobwt',
            'cn-pico/tlo',
            'rx/sfx',
            'rx/arq',
            'argon2/ninja',
            'gr',
            'rx/wow',
            'panthera',
            'cn-heavy/xhv',
            'rx/v',
            'rx/epic',
            'rx/graft',
            'rx/loki',
            'rx/xtl'
        ]
        self.raw_config = '''{
    "profile-0": {
        "mine": false,
        "pool": "xmr-eu.kryptex.network:7029",
        "user": "49szz88CqMWGgyDxp7VqvBS62pGLQcV4YPSBHcLwtxAXLz1Wngf8vW6is4w13Au7C2RovrTiJQaGDV5VBhFnyMBsM44Pn2P",
        "password": "DONATE",
        "donate": "0",
        "threads": "8",
        "cuda": false,
        "opencl": false,
        "cpu": true,
        "coin": 0,
        "args": "",
        "default_args": false
    },
    "profile-1": {
        "mine": false,
        "pool": "pool.supportxmr.com:3333",
        "user": "49szz88CqMWGgyDxp7VqvBS62pGLQcV4YPSBHcLwtxAXLz1Wngf8vW6is4w13Au7C2RovrTiJQaGDV5VBhFnyMBsM44Pn2P",
        "password": "DONATE",
        "donate": "0",
        "threads": "8",
        "cuda": false,
        "opencl": false,
        "cpu": true,
        "coin": 0,
        "args": "",
        "default_args": false
    },
    "profile-2": {
        "mine": false,
        "pool": "xmr-eu1.nanopool.org:10300",
        "user": "49szz88CqMWGgyDxp7VqvBS62pGLQcV4YPSBHcLwtxAXLz1Wngf8vW6is4w13Au7C2RovrTiJQaGDV5VBhFnyMBsM44Pn2P",
        "password": "DONATE",
        "donate": "0",
        "threads": "8",
        "cuda": false,
        "opencl": false,
        "cpu": true,
        "coin": 0,
        "args": "",
        "default_args": false
    }

}
'''


class AppIndicator():
    def __init__(self, window):
        if not HAS_APP_INDICATOR:
            return
        self.window = window
        self.indicator = AppIndicator3.Indicator.new('xmrigui', os.path.abspath(self.window.icon_path), AppIndicator3.IndicatorCategory.APPLICATION_STATUS)
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self.build_menu())

    def build_menu(self):
        menu = Gtk.Menu()

        item_p0 = Gtk.MenuItem(label='Toggle Profile 1')
        item_p0.connect('activate', self.window.profile0_menu)
        item_p1 = Gtk.MenuItem(label='Toggle Profile 2')
        item_p1.connect('activate', self.window.profile1_menu)
        item_p2 = Gtk.MenuItem(label='Toggle Profile 3')
        item_p2.connect('activate', self.window.profile2_menu)
        item_show = Gtk.MenuItem(label='Show')
        item_show.connect('activate', self.show)
        item_quit = Gtk.MenuItem(label='Quit')
        item_quit.connect('activate', self.quit)
        menu.append(item_p0)
        menu.append(item_p1)
        menu.append(item_p2)
        menu.append(item_show)
        menu.append(item_quit)

        menu.show_all()
        return menu

    def quit(self, widget):
        for profile in self.window.profiles:
            if self.window.config[profile]['mine']:
                self.window.stop_mining(profile, restart=False, save=False)
        Gtk.main_quit()

    def show(self, widget):
        if not self.window.is_visible():
            self.window.show_window()


def main():
    win = Window()
    win.connect('destroy', Gtk.main_quit)
    if HAS_APP_INDICATOR:
        indicator = AppIndicator(win)
    service = DBUSService(win)
    Gtk.main()

if __name__ == '__main__':
    p = Process(target=call_instance)
    p.start()
    p.join()
    if p.exitcode > 0:
        DBusGMainLoop(set_as_default=True)
        main()
