import pycurl
import cStringIO
import xml.etree.ElementTree as ET
import sys
import time

from gi.repository import GObject, Gtk, Pango

AMP_ADDRESS = "192.168.1.158"

class YamahaRemoteControl(GObject.GObject):
    __gproperties__ = {
        "volume": (float, "volume",
                   "Output volume",
                   -60.0, 0.0, -40.0,
                   GObject.PARAM_READWRITE),
        "muted": (bool, "muted",
                  "Is audio muted",
                  False,
                  GObject.PARAM_READWRITE),
        "power": (bool, "power",
                  "Is system powered up",
                  True,
                  GObject.PARAM_READWRITE),
        "source": (str, "source",
                  "Selected input device",
                  "",
                  GObject.PARAM_READWRITE),
        }

    def __init__(self):
        GObject.GObject.__init__(self)

        self.is_power_on = True
        self.volume = 0.0
        self.new_volume = 0.0
        self.is_muted = False
        self.source = None

        self.curl = pycurl.Curl()
        self.curl.setopt(pycurl.POST, 1)
        url = "http://%s/YamahaRemoteControl/ctrl" % AMP_ADDRESS
        self.curl.setopt(pycurl.URL, url)
        self.curl.setopt(pycurl.HTTPHEADER,
                ['Content-Type: text/xml; charset="utf-8"', 'Expect:'])

    def __del__(self):
        self.curl.close()

    def do_get_property(self, prop):
        if prop.name == 'volume':
            return self.volume
        elif prop.name == 'muted':
            return self.is_muted
        elif prop.name == 'power':
            return self.is_power_on
        else:
            raise AttributeError, "Unknown property %s" % prop.name

    def do_set_property(self, prop, value):
        if prop.name == 'volume':
            self.set_volume(value)
        elif prop.name == 'muted':
            self.set_is_muted(value)
        elif prop.name == 'power':
            self.set_is_power_on(value)
        else:
            raise AttributeError, "Unknown property %s" % prop.name

    def _exec(self, cmd="GET", data=None):
        req = """<?xml version="1.0" encoding="utf-8"?><YAMAHA_AV cmd="%s">%s</YAMAHA_AV>""" % (cmd, data)
        self.curl.setopt(pycurl.POSTFIELDSIZE, len(req))
        self.curl.setopt(pycurl.READFUNCTION, cStringIO.StringIO(req).read)
        b = cStringIO.StringIO()
        self.curl.setopt(pycurl.WRITEFUNCTION, b.write)
        self.curl.perform()
        root = ET.fromstring(b.getvalue())
        error_code = int(root.get("RC"))
        if error_code == 2:
            print >>sys.stderr, "Warning: error in node designation"
        elif error_code == 3:
            print >>sys.stderr, "Warning: error in parameter (value/range)"
        elif error_code == 4:
            print >>sys.stderr, "Warning: not successfully set due to a system error"
        elif error_code == 5:
            print >>sys.stderr, "Warning: internal error"
        return root

    def _get(self, data):
        return self._exec("GET", data)

    def _put(self, data):
        return self._exec("PUT", data)

    def get_network_name(self):
        cmd = "<System><Misc><Network><Network_Name>GetParam</Network_Name></Network></Misc></System>"
        return self._get(cmd).find("System/Misc/Network/Network_Name").text

    def set_is_power_on(self, is_power_on):
        if is_power_on != self.is_power_on:
            cmd = "<Main_Zone><Power_Control><Power>%s</Power></Power_Control></Main_Zone>" % ["Standby", "On"][is_power_on]
            self._put(cmd)
            self.is_power_on = is_power_on
            self.notify('power')

    def get_is_power_on(self):
        return self.is_power_on

    def set_volume(self, volume):
        volume = round(volume * 2.0) / 2.0
        if volume != self.volume:
            self.new_volume = volume
            GObject.idle_add(self._set_volume)

    def _set_volume(self):
        if self.volume == self.new_volume:
            return False
        volume = self.new_volume
        req = """<Main_Zone><Volume><Lvl><Val>%d</Val><Exp>1</Exp><Unit>dB</Unit></Lvl></Volume></Main_Zone>""" % round(volume * 10)
        self._put(req)
        if volume != self.volume:
            self.volume = volume
            self.notify('volume')
        return False

    def get_volume(self):
        return self.volume

    def set_is_muted(self, is_muted):
        if is_muted != self.is_muted:
            req = """<Main_Zone><Volume><Mute>%s</Mute></Volume></Main_Zone>""" % ["Off", "On"][is_muted]
            self._put(req)
            self.is_muted = is_muted
            self.notify('muted')

    def get_is_muted(self):
        return self.is_muted

    def refresh(self):
        req = """<Main_Zone><Basic_Status>GetParam</Basic_Status></Main_Zone>"""
        status = self._get(req)[0].find('Basic_Status')

        val = int(status.find("Volume/Lvl/Val").text)
        exp = int(status.find("Volume/Lvl/Exp").text)
        volume = val / 10.0**exp
        if volume != self.volume:
            self.volume = volume
            self.notify('volume')

        is_muted = status.find("Volume/Mute").text == "On"
        if is_muted != self.is_muted:
            self.is_muted = is_muted
            self.notify('muted')

        is_power_on = status.find("Power_Control/Power").text == "On"
        if is_power_on != self.is_power_on:
            self.is_power_on = is_power_on
            self.notify('power')

        source = status.find("Input/Input_Sel").text
        if source != self.source:
            self.source = source
            self.notify('source')

    def get_sources(self):
        cmd = "<Main_Zone><Input><Input_Sel_Item>GetParam</Input_Sel_Item></Input></Main_Zone>"
        items = self._get(cmd).find("Main_Zone/Input/Input_Sel_Item")
        inputs = []
        for item in items.getchildren():
            inputs.append(item.find("Param").text)
        return inputs

    def get_source(self):
        return self.source

    def set_source(self, input_name):
        if input_name != self.source:
            cmd = "<Main_Zone><Input><Input_Sel>%s</Input_Sel></Input></Main_Zone>" % input_name
            self._put(cmd)
            self.source = input_name
            self.notify('source')

    def wait_for_menu_info(self):
        while True:
            cmd = "<%s><List_Info>GetParam</List_Info></%s>" % (self.source, self.source)
            info = self._get(cmd).find("%s/List_Info" % self.source)
            status = info.find("Menu_Status").text
            if status == "Ready":
                return info
            time.sleep(0.05)

    def jump_to_line(self, line):
        cmd = "<%s><List_Control><Jump_Line>%d</Jump_Line></List_Control></%s>" % (self.source, line, self.source)
        self._put(cmd)

    def get_menu_name(self):
        info = self.wait_for_menu_info()
        return info.find("Menu_Name").text

    def get_menu(self):
        if self.source is None:
            return

        info = self.wait_for_menu_info()
        max_line = int(info.find("Cursor_Position/Max_Line").text)

        line = 1
        while line <= max_line:
            self.jump_to_line(line)
            info = self.wait_for_menu_info()
            for e in info.find("Current_List").getchildren():
                if e.find("Attribute").text != "Unselectable":
                    text = e.find("Txt").text
                    # Sometimes, entities are double-encoded.
                    text = text.replace("&amp;", "&")
                    yield (line + int(e.tag[5:]) - 1, text)
            line += 8

    def select_menu(self, line):
        self.jump_to_line(line)
        info = self.wait_for_menu_info()
        cmd = "<%s><List_Control><Direct_Sel>Line_%d</Direct_Sel></List_Control></%s>" % (self.source, (line - 1) % 8 + 1, self.source)
        self._put(cmd)

    def menu_return(self):
        if self.source is None:
            return
        cmd = "<%s><List_Control><Cursor>Return</Cursor></List_Control></%s>" % (self.source, self.source)
        self._put(cmd)

class YamahaRemoteWindow(Gtk.Window):
    def __init__(self):
        Gtk.Window.__init__(self, title="Yamaha Remote Control")
        self.set_size_request(500, -1)
        self.set_resizable(False)
        self.set_border_width(12)

        self.load_id = None

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)

        system_box = Gtk.Box(spacing=12)
        vbox.pack_start(system_box, False, False, 12)

        image = Gtk.Image.new_from_icon_name("audio-speakers", Gtk.IconSize.DIALOG)
        system_box.pack_start(image, False, False, 0)

        name_label = Gtk.Label()
        name_label.set_markup("<b>Receiver</b>")
        system_box.pack_start(name_label, False, False, 0)

        power_box = Gtk.Alignment(xalign=1.0, yalign=0.5, xscale=0.0, yscale=0.0)
        self.power_switch = Gtk.Switch()
        self.power_switch.set_active(True)
        self.power_switch.connect('notify::active', self.on_power_notify)
        power_box.add(self.power_switch)
        system_box.pack_start(power_box, True, True, 0)

        volume_box = Gtk.Box(spacing=12)
        alignment = Gtk.Alignment(xalign=0, yalign=0, xscale=1, yscale=1)
        alignment.add(volume_box)
        vbox.pack_start(alignment, False, False, 12)

        label = Gtk.Label()
        label.set_label("Volume:")
        label.set_alignment(0.0, 0.5)
        volume_box.pack_start(label, False, False, 0)

        adj = Gtk.Adjustment(-40.0, -80.0, 16.0, 0.5, 5.0, 0.0)
        self.volume_bar = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL,
                adjustment=adj)
        self.volume_bar.set_size_request(128, -1)
        self.volume_bar.set_draw_value(False)
        self.volume_bar.add_mark(0.0, Gtk.PositionType.BOTTOM,
                "<small>100%</small>")
        adj.connect('value-changed', self.on_volume_changed)
        volume_box.pack_start(self.volume_bar, True, True, 0)

        mute_box = Gtk.Alignment(xalign=0.5, yalign=0.0, xscale=0.0, yscale=0.0)
        self.mute_switch = Gtk.Switch()
        self.mute_switch.set_active(True)
        self.mute_switch.connect('notify::active', self.on_is_muted_notify)
        mute_box.add(self.mute_switch)
        volume_box.pack_start(mute_box, False, False, 0)

        input_box = Gtk.Box(spacing=12)
        vbox.pack_start(input_box, True, True, 0)

        frame = Gtk.Frame(label="Choose a sound input:")
        frame.set_shadow_type(Gtk.ShadowType.NONE)
        label = frame.get_label_widget()
        font_desc = Pango.FontDescription()
        font_desc.set_weight(Pango.Weight.BOLD)
        label.modify_font(font_desc)
        input_box.pack_start(frame, True, True, 0)

        input_box = Gtk.Alignment(xalign=0.0, yalign=0.0, xscale=1.0, yscale=1.0)
        input_box.set_padding(6, 0, 0, 0)
        frame.add(input_box)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.IN)
        scrolled.set_min_content_height(150)
        input_box.add(scrolled)

        store = Gtk.ListStore(str)
        self.input_tree = Gtk.TreeView(store)
        self.input_tree.set_headers_visible(False)
        selection = self.input_tree.get_selection()
        selection.set_mode(Gtk.SelectionMode.BROWSE)
        selection.connect("changed", self.on_input_selection_changed)
        scrolled.add(self.input_tree)

        renderer = Gtk.CellRendererText()
        column = Gtk.TreeViewColumn("Name", renderer, text=0)
        self.input_tree.append_column(column)

        menu_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        vbox.pack_start(menu_box, True, True, 12)

        path_bar = Gtk.Box()
        path_bar.get_style_context().add_class("linked")
        menu_box.pack_start(path_bar, False, False, 0)

        self.parent_button = Gtk.Button()
        self.parent_button.set_focus_on_click(False)
        self.parent_button.add(Gtk.Arrow(Gtk.ArrowType.LEFT, Gtk.ShadowType.OUT))
        self.parent_button.connect("clicked", self.on_parent_button_clicked)
        path_bar.add(self.parent_button)
        self.current_button = Gtk.ToggleButton("Current")
        self.current_button.set_active(True)
        self.current_button.connect("clicked", self.on_current_button_clicked)
        path_bar.add(self.current_button)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.IN)
        scrolled.set_min_content_height(150)
        menu_box.pack_start(scrolled, True, True, 0)

        self.menu_tree = Gtk.TreeView()
        self.menu_tree.set_rules_hint(True)
        self.menu_tree.set_headers_visible(False)
        self.menu_tree.connect("row-activated", self.on_menu_row_activated)
        scrolled.add(self.menu_tree)

        renderer = Gtk.CellRendererText()
        renderer.set_property("ellipsize", Pango.EllipsizeMode.END);
        column = Gtk.TreeViewColumn("Text", renderer, text=0)
        column.set_cell_data_func(renderer, self.cell_data_func)
        self.menu_tree.append_column(column)

        self.remote = YamahaRemoteControl()
        self.remote.connect("notify::volume", self.on_remote_volume_notify)
        self.remote.connect("notify::muted", self.on_remote_muted_notify)
        self.remote.connect("notify::power", self.on_remote_power_notify)
        self.remote.refresh()

        name_label.set_markup("<b>%s</b>" % self.remote.get_network_name())
        input_iter = self.add_inputs()
        if input_iter is not None:
            selection.handler_block_by_func(self.on_input_selection_changed)
            selection.select_iter(input_iter)
            selection.handler_unblock_by_func(self.on_input_selection_changed)

        self.update_menu()

    def on_power_notify(self, switch, data):
        self.remote.set_is_power_on(switch.get_active())

    def on_remote_power_notify(self, remote, data):
        self.power_switch.freeze_notify()
        self.power_switch.set_active(self.remote.get_is_power_on())
        self.power_switch.thaw_notify()

    def on_volume_changed(self, adjustment):
        volume = adjustment.get_value()
        self.remote.set_volume(volume)

    def on_remote_volume_notify(self, remote, data):
        adj = self.volume_bar.get_adjustment()
        adj.handler_block_by_func(self.on_volume_changed)
        adj.set_value(self.remote.get_volume())
        adj.handler_unblock_by_func(self.on_volume_changed)

    def on_is_muted_notify(self, switch, active):
        self.remote.set_is_muted(not switch.get_active())

    def on_remote_muted_notify(self, remote, data):
        self.mute_switch.freeze_notify()
        self.mute_switch.set_active(not self.remote.get_is_muted())
        self.mute_switch.thaw_notify()

    def add_inputs(self):
        model = self.input_tree.get_model()
        current_input = self.remote.get_source()
        current_iter = None
        for input_name in self.remote.get_sources():
            input_iter = model.append([input_name])
            if input_name == current_input:
                current_iter = input_iter
        return current_iter

    def on_input_selection_changed(self, selection):
        model, treeiter = selection.get_selected()
        if treeiter is not None:
            name = model[treeiter][0]
            self.remote.set_source(name)

    def cell_data_func(self, column, renderer, model, iter_, data):
        text = model.get(iter_, 0)[0]
        if text.startswith("- ") and text.endswith(" -"):
            renderer.set_property("text", text[2:-2])
            renderer.set_property("weight", Pango.Weight.BOLD)
        else:
            renderer.set_property("weight", Pango.Weight.NORMAL)

    def load_menu(self, model, items):
        for item in items:
            model.append([item[1], item[0]])
            yield True
        self.menu_tree.set_model(model)
        self.load_id = None
        yield False

    def update_menu(self):
        if self.load_id is not None:
            GObject.source_remove(self.load_id)
            self.load_id = None
        model = Gtk.ListStore(str, int)
        self.menu_tree.set_model(model)
        menu_name = self.remote.get_menu_name()
        if menu_name.startswith("- ") and menu_name.endswith(" -"):
            menu_name = menu_name[2:-2]
        self.current_button.set_label(menu_name)
        self.load_id = GObject.idle_add(
                self.load_menu(model, self.remote.get_menu()).next)

    def on_menu_row_activated(self, tree, path, column):
        model = tree.get_model()
        menu_iter = model.get_iter(path)
        self.remote.select_menu(model[menu_iter][1])
        self.update_menu()

    def on_parent_button_clicked(self, button):
        self.remote.menu_return()
        self.update_menu()

    def on_current_button_clicked(self, button):
        button.handler_block_by_func(self.on_current_button_clicked)
        button.set_active(True)
        button.handler_unblock_by_func(self.on_current_button_clicked)

def on_activate(app):
    win = app.get_windows()[0]
    win.present()

def on_startup(app):
    settings = Gtk.Settings.get_default()
    settings.set_property("gtk-application-prefer-dark-theme", True)

    win = YamahaRemoteWindow()
    win.set_application(app)
    win.show_all()

if __name__ == '__main__':
    app = Gtk.Application(application_id="ca.deuxpi.YamahaRemote")
    app.connect("activate", on_activate)
    app.connect("startup", on_startup)
    app.run(sys.argv)
