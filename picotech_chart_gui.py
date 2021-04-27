"""Qt based GUI client for ni-daqmx-tmux."""

import sys
import pathlib

from qtpy import QtCore, QtGui, QtWidgets  # type: ignore
import pyqtgraph as pg  # type: ignore
import qtypes  # type: ignore
import yaqc  # type: ignore
import toml
import numpy as np  # type: ignore
import time
# from io import StringIO

ranges = [0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20]
allowed_ranges = ["{0:0.2f}".format(r) for r in ranges]

class Channel:

    ranges =  [0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20]
    couplings = None

    def __init__(
        self,
        nsamples,
        range,
        enabled,
        coupling,
        invert,
    ):
        range_ = range

        self.enabled = qtypes.Bool(value=enabled)
        self.range = qtypes.Enum(allowed_values=Channel.ranges, initial_value=range_)
        self.invert = qtypes.Bool(value=invert)
        self.coupling = qtypes.Enum(allowed_values=Channel.couplings, initial_value=coupling)


    def get_range(self):
        """
        Returns
        -------
        tuple
            (minimum_voltage, maximum_voltage)
        """
        r = float(Channel.ranges[self.range.get_index()].split(" ")[0])
        return -r, r

    def get_widget(self):
        self.input_table = qtypes.widgets.InputTable()
        self.input_table.append(self.range, "Range +/-V")
        self.input_table.append(self.invert, "Invert")
        self.input_table.append(self.coupling, "Coupling")
        return self.input_table


class ConfigWidget(QtWidgets.QWidget):
    def __init__(self, port):
        super().__init__()
        self.port = port
        
        self.client = yaqc.Client(self.port)
        config = toml.loads(self.client.get_config())
        self.time = self.client.get_mappings()['time']
        self.nsamples = config["max_samples"]
        self.channels = {}
        self.types = {v["name"]: v for v in self.client._protocol["types"]}
        Channel.ranges = self.types["adc_range"]["symbols"]
        Channel.couplings = self.types["adc_coupling"]["symbols"]
        for name, d in config["channels"].items():
            self.channels[name] = Channel(**d, nsamples=self.nsamples)
        
        # self.client.set_nshots(50)
        self.signal_channel_key="B"
        self.signal_channel_index=int(1)
        self.norm_interval=100 #msec
        self.nchunks=int(1)
        self.beginning_sample=int(0)
        self.ending_sample=int(5)
        self.shotsdata=[]
        self.chartdata=[]
        self.charttimedata=[]
        self.wait_time=0.1
        self.busy=False
        self.stopchart=False
        self.chartstopped=True
        self.stopchartboolean=False
        self.singleshot=False
        
        self.config = toml.loads(self.client.get_config())

        self.create_frame()
        self.poll_timer = QtCore.QTimer()
        self.poll_timer.start(self.norm_interval)  # milliseconds
        self.poll_timer.timeout.connect(self.update)


    def create_frame(self):
        self.setLayout(QtWidgets.QHBoxLayout())
        self.layout().setContentsMargins(0, 10, 0, 0)
        self.tabs = QtWidgets.QTabWidget()
        # samples tab
        samples_widget = QtWidgets.QWidget()
        samples_box = QtWidgets.QHBoxLayout()
        samples_box.setContentsMargins(0, 10, 0, 0)
        samples_widget.setLayout(samples_box)
        self.tabs.addTab(samples_widget, "Samples")
        self.create_samples_tab(samples_box)
        # shots tab
        shots_widget = QtWidgets.QWidget()
        shots_box = QtWidgets.QHBoxLayout()
        shots_box.setContentsMargins(0, 10, 0, 0)
        shots_widget.setLayout(shots_box)
        self.tabs.addTab(shots_widget, "Shots")
        self.create_shots_tab(shots_box)
        # chart tab
        chart_widget = QtWidgets.QWidget()
        chart_box = QtWidgets.QHBoxLayout()
        chart_box.setContentsMargins(0, 10, 0, 0)
        chart_widget.setLayout(chart_box)
        self.tabs.addTab(chart_widget, "Chart")
        self.create_chart_tab(chart_box)
        # finish
        self.layout().addWidget(self.tabs)
        self.update_samples_tab()

    def create_samples_tab(self, layout):
        display_container_widget = QtWidgets.QWidget()
        display_container_widget.setLayout(QtWidgets.QVBoxLayout())
        display_layout = display_container_widget.layout()
        layout.addWidget(display_container_widget)

        textbox=QtWidgets.QLabel()
        textbox.setText(f"Channel {self.signal_channel_key} trace and current voltage range")
        textbox.show()

        self.samples_plot_widget = Plot1D(yAutoRange=False)    
        self.samples_plot_scatter = self.samples_plot_widget.add_scatter()
        self.samples_plot_widget.set_labels(xlabel="sample time(ns)", ylabel="volts")
        self.samples_plot_max_voltage_line = self.samples_plot_widget.add_infinite_line(
            color="y", angle=0
        )
        self.samples_plot_min_voltage_line = self.samples_plot_widget.add_infinite_line(
            color="y", angle=0
        )
        
        display_layout.addWidget(self.samples_plot_widget)
        line = qtypes.widgets.Line("V")
        layout.addWidget(line)
        
        settings_container_widget = QtWidgets.QWidget()
        settings_scroll_area = qtypes.widgets.ScrollArea()
        settings_scroll_area.setWidget(settings_container_widget)
        settings_container_widget.setLayout(QtWidgets.QVBoxLayout())
        settings_layout = settings_container_widget.layout()
        settings_layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(settings_scroll_area)
        
        input_table = qtypes.widgets.InputTable()
        settings_layout.addWidget(input_table)
        self.voltage_range = qtypes.Enum(allowed_values=Channel.ranges, initial_value=self.config["channels"][self.signal_channel_key]["range"],  name="voltage_range")
        self.voltage_range.updated.connect(self.on_voltage_range_updated)
        input_table.append(self.voltage_range)
        
        self.single_shot_button = QtWidgets.QCheckBox("SINGLE SHOT")
        settings_layout.addWidget(self.single_shot_button)

        settings_layout.addStretch(1)
        self.sample_xi = self.client.get_mappings()['time']

    def create_shots_tab(self, layout):
        display_container_widget = QtWidgets.QWidget()
        display_container_widget.setLayout(QtWidgets.QVBoxLayout())
        display_layout = display_container_widget.layout()
        display_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(display_container_widget)
        
        self.shots_plot_widget = Plot1D()
        self.shots_plot_scatter = self.shots_plot_widget.add_scatter()
        self.shots_plot_widget.set_labels(xlabel="time (nsec)", ylabel="volts")
        display_layout.addWidget(self.shots_plot_widget)
        line = qtypes.widgets.Line("V")
        layout.addWidget(line)
        
        settings_container_widget = QtWidgets.QWidget()
        settings_scroll_area = qtypes.widgets.ScrollArea()
        settings_scroll_area.setWidget(settings_container_widget)
        settings_container_widget.setLayout(QtWidgets.QVBoxLayout())
        settings_layout = settings_container_widget.layout()
        settings_layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(settings_scroll_area)

        input_table = qtypes.widgets.InputTable()
        self.nchunks_temp = qtypes.Number(name=f"Num of chunks of {self.client.get_nshots()} Shots", value=1, decimals=0)
        self.nchunks_temp.updated.connect(self.on_nchunks_updated)
        input_table.append(self.nchunks_temp)
        settings_layout.addWidget(input_table)
               
        self.run_shots_button = qtypes.widgets.PushButton("ACQUIRE", background="green")
        self.run_shots_button.clicked.connect(self.acquire_nchunks)
        settings_layout.addWidget(self.run_shots_button)
        line = qtypes.widgets.Line("H")
        settings_layout.addWidget(line)

        input_table2= qtypes.widgets.InputTable()
        self.chunk_temp = qtypes.Number(name="Current chunk:", value=1, decimals=0)
        input_table2.append(self.chunk_temp)
        settings_layout.addWidget(input_table2)
        line = qtypes.widgets.Line("H")
        settings_layout.addWidget(line)
        
        self.save_nchunks_button = qtypes.widgets.PushButton("SAVE", background="orange")
        self.save_nchunks_button.clicked.connect(self.on_save_nchunks_updated)
        settings_layout.addWidget(self.save_nchunks_button)
        line = qtypes.widgets.Line("H")
        settings_layout.addWidget(line)
        
        settings_layout.addStretch(1)
        #self.shot_channel_combo.updated.emit()

    def create_chart_tab(self, layout):
        display_container_widget = QtWidgets.QWidget()
        display_container_widget.setLayout(QtWidgets.QVBoxLayout())
        display_layout = display_container_widget.layout()
        display_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(display_container_widget)
        
        self.chart_plot_widget = Plot1D()
        self.chart_plot_scatter = self.chart_plot_widget.add_scatter()
        self.chart_plot_widget.set_labels(xlabel="chart time (sec)", ylabel="volts")
        display_layout.addWidget(self.chart_plot_widget)
        line1 = qtypes.widgets.Line("V")
        layout.addWidget(line1)
        
        settings_container_widget = QtWidgets.QWidget()
        settings_scroll_area = qtypes.widgets.ScrollArea()
        settings_scroll_area.setWidget(settings_container_widget)
        settings_container_widget.setLayout(QtWidgets.QVBoxLayout())
        self.settings_layout = settings_container_widget.layout()
        self.settings_layout.setContentsMargins(5, 5, 5, 5)
        layout.addWidget(settings_scroll_area)
        
        input_table1 = qtypes.widgets.InputTable()
        self.wait_time_temp = qtypes.Number(name="Wait Time (sec)", value=0.00, decimals=3)
        self.wait_time_temp.updated.connect(self.on_wait_time_updated)
        input_table1.append(self.wait_time_temp)
        self.settings_layout.addWidget(input_table1)
                
        input_table2 = qtypes.widgets.InputTable()
        self.beginning_sample_temp = qtypes.Number(name="Beginning Sample", value=1, decimals=0)
        self.beginning_sample_temp.updated.connect(self.on_beginning_sample_updated)
        input_table2.append(self.beginning_sample_temp)
        self.settings_layout.addWidget(input_table2)
                    
        input_table3 = qtypes.widgets.InputTable()
        self.ending_sample_temp = qtypes.Number(name="Ending Sample", value=5, decimals=0)
        self.ending_sample_temp.updated.connect(self.on_ending_sample_updated)
        input_table3.append(self.ending_sample_temp)
        self.settings_layout.addWidget(input_table3)

        line2 = qtypes.widgets.Line("H")
        self.settings_layout.addWidget(line2)

        # run button
        self.run_chart_button = qtypes.widgets.PushButton("RUN", background="green")
        self.run_chart_button.clicked.connect(self.run_chart)
        self.settings_layout.addWidget(self.run_chart_button)
        
        # stop button
        self.stop_chart_button = QtWidgets.QCheckBox("STOP")
        self.settings_layout.addWidget(self.stop_chart_button)

        # save button
        self.save_chart_button = qtypes.widgets.PushButton("SAVE", background="orange")
        self.save_chart_button.clicked.connect(self.on_save_chart_updated)
        self.settings_layout.addWidget(self.save_chart_button)

        # finish
        self.settings_layout.addStretch(1)
        #self.shot_channel_combo.updated.emit()

    def write_config_single_key_range(self,key,value):
        # create dictionary, starting from existing
        config = toml.loads(self.client.get_config())
        # search channel fo key equal to channel letter
        for k in config["channels"].keys():
            #channel = self.channels[k]
            if k==key:
                
                config["channels"][k]["range"] = value

        """
        print(toml.dumps({
            self.client.id()["name"]: {"channels": config["channels"]}
        }))
        """
        with open(self.client.get_config_filepath(), "w") as f:
            toml.dump({self.client.id()["name"]: config}, f)
        self.client.shutdown(restart=True)
        while True:
            try:
                self.client = yaqc.Client(self.port)
            except:
                print("tried to connect")
                time.sleep(0.1)
            else:
                break

    def on_beginning_sample_updated(self):
        new = int(self.beginning_sample_temp.get())
        assert new > 0
        self.beginning_sample=new
    
    def on_ending_sample_updated(self):
        new = int(self.ending_sample_temp.get())
        assert new > 0
        self.ending_sample=new
 
    def on_nchunks_updated(self):
        new = int(self.nchunks_temp.get())
        assert new > 0
        self.nchunks=new

    def on_save_nchunks_updated(self):
        if self.busy != True:
            xdata = self.sample_xi
            ydata = self.shotsdata
            data=np.asarray([xdata,ydata], dtype=float).T
            f=open('shotsdata.dat','w')
            np.savetxt(f,data,fmt='%.5f')
            f.close()
            print('Shots Data saved...any older file overwritten.')
        else:
            print('Shots not fully collected and/or system busy.')

    def on_save_chart_updated(self):
        if self.chartstopped:
            xdata = self.charttimedata
            ydata = self.chartdata
            data=np.asarray([xdata,ydata], dtype=float).T
            f=open('chartdata.dat','w')
            np.savetxt(f,data,fmt='%.5f')
            f.close()
            print('Chart Data saved...any older file overwritten.')
        else:
            print('Chart not stopped.')

    def on_voltage_range_updated(self):
        if self.busy != True:
            self.busy=True
            newrange = self.voltage_range.get()
            time.sleep(2*self.norm_interval/1000)
            self.on_shot_channel_updated(newrange)
            self.busy=False
        else:
            print('System busy...range not updated.')

    def on_wait_time_updated(self):
        new = float(self.wait_time_temp.get())
        assert new >= 0
        self.wait_time=new
        
    def on_shot_channel_updated(self,rangevalue):
        channel_index=self.signal_channel_index
        channel_key=self.signal_channel_key
        self.write_config_single_key_range(channel_key,rangevalue)
        active_channels = [channel for channel in self.channels.values() if channel.enabled.get()]
        channel = active_channels[channel_index]
        ymin, ymax = channel.get_range()
        self.shots_plot_widget.set_ylim(ymin * 1.05, ymax * 1.05)
        self.samples_plot_widget.set_ylim(ymin * 1.05, ymax * 1.05)
        self.chart_plot_widget.set_ylim(ymin * 1.05, ymax * 1.05)

    def acquire_nchunks(self):
        if self.busy==False:
            self.busy=True
            chunks=self.nchunks
            time.sleep(self.norm_interval/1000)
            self.singleshot=bool(self.single_shot_button.isChecked())
            shotsdata=np.zeros(len(self.sample_xi))
            index=0
            begtime=0
            midtime=0
            for i in range(chunks):
                if index != 0:
                    begtime=time.perf_counter()
                self.chunk_temp.set(i+1)
                yi = self.client.get_measured_samples()  # samples:  (channel, shot, sample)
                yi2 = yi[self.signal_channel_index].mean(axis=0)
                if self.singleshot:
                    yitemp=yi[self.signal_channel_index][0]
                else:
                    yitemp=yi2
                self.update_samples_graph(yitemp)
                shotsdata=shotsdata+yi2
                self.update_shots_graph(shotsdata/(i+1))
                self.eventloop.processEvents()
                if index != 0:
                    midtime=time.perf_counter()-begtime
                    time.sleep(midtime)
                index=index+1    
        
            self.shotsdata=shotsdata/chunks
            self.busy=False
            return shotsdata/chunks
        else:
            return self.shotsdata    
    
    def run_chart(self):
        if self.busy==False:
            self.busy=True
            time.sleep(self.norm_interval/1000)
            waittime=self.wait_time
            beg_index=self.beginning_sample
            end_index=self.ending_sample
            self.singleshot=bool(self.single_shot_button.isChecked())
            starttime=time.perf_counter()
            chunks=self.nchunks
            shotsdata=np.zeros(len(self.sample_xi))
           
            self.chartstopped=False
            chartdata=[]
            timedata=[]
            index=0
            begtime=0
            midtime=0
            # inlined (hardcode) instead of used acquire_nchunks to avoid racing on self.busy
            # can instead go to subroutine if self.busy conditional on update unnecessary
            while (self.stop_chart_button.isChecked() != True):
                if self.singleshot:
                    yi = self.client.get_measured_samples()  # samples:  (channel, shot, sample)
                    yi2 = yi[self.signal_channel_index][0]
                    self.shotsdata=yi2
                    time.sleep(self.norm_interval/1000)
                    self.eventloop.processEvents()
                else:
                    for i in range(chunks):
                        if index != 0:
                            begtime=time.perf_counter()
                        self.chunk_temp.set(i+1)
                        yi = self.client.get_measured_samples()  # samples:  (channel, shot, sample)
                        yi2 = yi[self.signal_channel_index].mean(axis=0)
                        self.update_samples_graph(yi2)
                        shotsdata=shotsdata+yi2
                        self.update_shots_graph(shotsdata/(i+1))
                        self.eventloop.processEvents()
                        if index != 0:
                            midtime=time.perf_counter()-begtime
                            time.sleep(midtime)
                        index=index+1    
                    self.shotsdata=shotsdata/chunks
            
                currenttime=time.perf_counter()-starttime
                shotsdataab = self.shotsdata[beg_index:end_index]
                #currently averaging the data within the indices
                datum=np.sum(shotsdataab)/(end_index-beg_index+1)
            
                timedata.append(currenttime)
                chartdata.append(datum)
                self.update_chart_graph(np.array(timedata, dtype=float),np.array(chartdata,dtype=float))
                self.charttimedata=timedata
                self.chartdata=chartdata
                time.sleep(waittime)
        
            self.stop_chart_button.setChecked(False)
            self.stopchart=False
            self.chartstopped=True
            self.busy=False
            return chartdata
        else:
            return self.chartdata

    def set_slice_xlim(self, xmin, xmax):
        self.values_plot_widget.set_xlim(xmin, xmax)

    def update_samples_graph(self,data):
        self.samples_plot_scatter.clear()
        self.samples_plot_scatter.setData(self.sample_xi,data)

    def update_shots_graph(self,data):
        self.shots_plot_scatter.clear()
        self.shots_plot_scatter.setData(self.sample_xi, data)

    def update_chart_graph(self,xdata,ydata):
        self.chart_plot_scatter.clear()
        self.chart_plot_scatter.setData(xdata, ydata)

    def update_samples_tab(self):
        # buttons
        #num_channels = len(self.samples_channel_combo.allowed_values)
        # channel ui
        #channel_index = self.samples_channel_combo.get_index()
        channel_index=self.signal_channel_index
        #for widget in self.channel_widgets:
        #    widget.hide()
        #self.channel_widgets[channel_index].show()
        # lines on plot
        self.samples_plot_max_voltage_line.hide()
        self.samples_plot_min_voltage_line.hide()
        current_channel_object = list(self.channels.values())[channel_index]
        if current_channel_object.enabled.get():
            channel_min, channel_max = current_channel_object.get_range()
            self.samples_plot_max_voltage_line.show()
            self.samples_plot_max_voltage_line.setValue(channel_max * 1.05)
            self.samples_plot_min_voltage_line.show()
            self.samples_plot_min_voltage_line.setValue(channel_min * 1.05)
        # finish
        ymin, ymax = current_channel_object.get_range()
        self.samples_plot_widget.set_ylim(ymin, ymax)

    def update(self):
        # self.busy conditional probably not necessary
        self.singleshot=bool(self.single_shot_button.isChecked())
        if self.busy == False:
            if self.singleshot:
                yi = self.client.get_measured_samples()  # samples:  (channel, shot, sample)
                yi2 = yi[self.signal_channel_index][0]
                self.update_samples_graph(yi2)
            else:
                yi = self.client.get_measured_samples()  # samples:  (channel, shot, sample)
                yi2 = yi[self.signal_channel_index].mean(axis=0)
                self.update_samples_graph(yi2)
                #don't need to process Eventloop here but may put it in anyway
        self.busy=False


class Plot1D(pg.GraphicsView):
    def __init__(self, title=None, xAutoRange=True, yAutoRange=True):
        pg.GraphicsView.__init__(self)
        # create layout
        self.graphics_layout = pg.GraphicsLayout(border="w")
        self.setCentralItem(self.graphics_layout)
        self.graphics_layout.layout.setSpacing(0)
        self.graphics_layout.setContentsMargins(0.0, 0.0, 1.0, 1.0)
        # create plot object
        self.plot_object = self.graphics_layout.addPlot(0, 0)
        self.labelStyle = {"color": "#FFF", "font-size": "14px"}
        self.x_axis = self.plot_object.getAxis("bottom")
        self.x_axis.setLabel(**self.labelStyle)
        self.y_axis = self.plot_object.getAxis("left")
        self.y_axis.setLabel(**self.labelStyle)
        self.plot_object.showGrid(x=True, y=True, alpha=0.5)
        self.plot_object.setMouseEnabled(False, True)
        self.plot_object.enableAutoRange(x=xAutoRange, y=yAutoRange)
        # title
        if title:
            self.plot_object.setTitle(title)

    def add_scatter(self, color="c", size=3, symbol="o"):
        curve = pg.ScatterPlotItem(symbol=symbol, pen=(color), brush=(color), size=size)
        self.plot_object.addItem(curve)
        return curve

    def add_line(self, color="c", size=3, symbol="o"):
        curve = pg.PlotCurveItem(symbol=symbol, pen=(color), brush=(color), size=size)
        self.plot_object.addItem(curve)
        return curve

    def add_infinite_line(self, color="y", style="solid", angle=90.0, movable=False, hide=True):
        """
        Add an InfiniteLine object.
        Parameters
        ----------
        color : (optional)
            The color of the line. Accepts any argument valid for `pyqtgraph.mkColor <http://www.pyqtgraph.org/documentation/functions.html#pyqtgraph.mkColor>`_. Default is 'y', yellow.
        style : {'solid', 'dashed', dotted'} (optional)
            Linestyle. Default is solid.
        angle : float (optional)
            The angle of the line. 90 is vertical and 0 is horizontal. 90 is default.
        movable : bool (optional)
            Toggles if user can move the line. Default is False.
        hide : bool (optional)
            Toggles if the line is hidden upon initialization. Default is True.
        Returns
        -------
        InfiniteLine object
            Useful methods: setValue, show, hide
        """
        if style == "solid":
            linestyle = QtCore.Qt.SolidLine
        elif style == "dashed":
            linestyle = QtCore.Qt.DashLine
        elif style == "dotted":
            linestyle = QtCore.Qt.DotLine
        else:
            print("style not recognized in add_infinite_line")
            linestyle = QtCore.Qt.SolidLine
        pen = pg.mkPen(color, style=linestyle)
        line = pg.InfiniteLine(pen=pen)
        line.setAngle(angle)
        line.setMovable(movable)
        if hide:
            line.hide()
        self.plot_object.addItem(line)
        return line

    def set_labels(self, xlabel=None, ylabel=None):
        if xlabel:
            self.plot_object.setLabel("bottom", text=xlabel)
            self.plot_object.showLabel("bottom")
        if ylabel:
            self.plot_object.setLabel("left", text=ylabel)
            self.plot_object.showLabel("left")

    def set_xlim(self, xmin, xmax):
        self.plot_object.setXRange(xmin, xmax)

    def set_ylim(self, ymin, ymax):
        self.plot_object.setYRange(ymin, ymax)

    def clear(self):
        self.plot_object.clear()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app, port):
        super().__init__()
        self.app = app
        self.setWindowTitle("Picoscope")
        self.app.eventloop=QtCore.QEventLoop(app)
        self.setCentralWidget(ConfigWidget(port))
        ConfigWidget.eventloop=self.app.eventloop


def main():
    """Initialize application and main window."""
    
    port = int(sys.argv[1])
    app = QtWidgets.QApplication(sys.argv)
    main_window = MainWindow(app, port)
    main_window.showMaximized()
        
    sys.exit(app.exec_())
    

if __name__ == "__main__":
    main()
