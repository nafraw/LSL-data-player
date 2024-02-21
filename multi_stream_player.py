import sys

import time
from threading import Timer
# import pandas as pd
# import numpy as np
from numpy import genfromtxt, floor, vstack
import pylsl
from tqdm import tqdm
import configparser

# from LSL_inlets import Inlet, DataInlet, MarkerInlet, dataBuffer2D, dataBuffer1D
def parseStrList(x):
    y = x.split(',')
    for i, s in enumerate(y):
        y[i] = s.strip()
    return y

class RepeatTimer(Timer):
    def run(self):
        while not self.finished.wait(self.interval):
            self.function(*self.args,**self.kwargs)

class single_stream_playbacker():
    def __init__(self, timer_interval=0.1, config_file='config_signal_player.ini') -> None:
        self.sample_ptr = 0
        self.config_file = config_file
        self.timer = RepeatTimer(timer_interval, self.playback) # set looping timer and decode function        

    def parseConfig(self, config_file=None):
        cfg = configparser.ConfigParser()
        if config_file is None:
            config_file = self.config_file
        cfg.read(config_file)
        self.fs = cfg.getfloat('stream', 'fs')
        self.channel_count = cfg.getint('stream', 'ch_count')
        self.repeat = cfg.getint('stream', 'repeat')
        self.push_interval = cfg.getfloat('stream', 'push_interval')
        self.streamName = cfg.get('stream', 'streamName')
        self.filename = cfg.get('file', 'file')

    def init_by_config(self, config_file=None):
        if config_file is None:
            config_file = self.config_file
        self.parseConfig(config_file=config_file)
        self.timer = RepeatTimer(self.push_interval, self.playback)
        self.init_by_csv(filename=self.filename, fs=self.fs)
        self.create_outlet_stream(streamName=self.streamName, channel_count=self.channel_count, fs=self.fs)

    def start_streaming(self, repeat=None, verbose=False):
        # repeat = 0: no repeat, = 1: repeat one time, = -1: repeat infinite
        if verbose:
            print('Once the playback starts, enter c or C to stop streaming')
            print('playback starts')
        if repeat is None:
            try:
                repeat = self.repeat # from config
            except:
                repeat = 0
        self.repeat = repeat
        self.ref_time = time.time()
        self.prev_time = time.time()
        self.timer.start()

    def stop_streaming(self):
        self.timer.cancel()
        self.tqdmBar.close()
        print('playback finished')

    def init_by_data(self, data, fs):
        self.fs = fs
        self.data = data
        self.nsample = data.shape[0]
        # self.progressBar = Bar('# sample', max=self.nsample)
        self.tqdmBar = tqdm(total=self.nsample)        
        self.cur_sample = 0
        self.last_progress_update_sample = 0

    def init_by_csv(self, filename, fs, col_idx = [1, 2, 3, 4, 5, 6, 7, 8]):
        # D = pd.read_csv(filename)
        # data = D.iloc[:, col_idx]
        # self.init_by_data(data=np.array(data), fs=fs)
        # data=np.genfromtxt(filename, dtype=float, delimiter=',', skip_header=True)
        data=genfromtxt(filename, dtype=float, delimiter=',', skip_header=True)
        self.init_by_data(data=data[:, col_idx], fs=fs)

    def create_outlet_stream(self, streamName, channel_count, fs):
        info = pylsl.stream_info(name=streamName, type='float', channel_count=channel_count, nominal_srate=fs)
        print(f'creating outlet stream: {info.name()}, sampling rate: {fs}, channel #: {channel_count}')
        self.LSLOutlet = pylsl.stream_outlet(info)
        self.fs = fs
        self.channel_count = channel_count
        self.streamName = streamName

    def playback(self):
        cur_time = time.time()
        elapsed_time = cur_time - self.prev_time
        amount = int(floor(self.fs*elapsed_time))
        if amount > 0:
            self.prev_time = self.prev_time + amount/self.fs
            self.cur_sample += amount
           
        if self.sample_ptr + amount < self.nsample:
            data = self.data[self.sample_ptr: self.sample_ptr+amount, :]
            if self.cur_sample - self.last_progress_update_sample > self.fs:
                self.tqdmBar.update(self.cur_sample - self.last_progress_update_sample)
                self.last_progress_update_sample = self.cur_sample
            # self.progressBar.goto(self.cur_sample)
        elif self.repeat == 0:
            data = self.data[self.sample_ptr:, :]
            self.LSLOutlet.push_chunk(x=data.tolist())
            self.sample_ptr = 0
            # self.progressBar.goto(self.nsample)
            self.tqdmBar.update(self.nsample - self.last_progress_update_sample)
            self.stop_streaming()
        else:
            data1 = self.data[self.sample_ptr:, :]
            data2 = self.data[:amount-data1.shape[0], :]
            data = vstack((data1, data2))
            # self.progressBar.goto(self.nsample)
            self.tqdmBar.update(self.nsample - self.last_progress_update_sample - 1)
            # print('\nEnd of data, looping from the start\n')
            while self.cur_sample >= self.nsample:
                self.cur_sample -= self.nsample
            self.last_progress_update_sample = 0            
            # self.progressBar.goto(self.cur_sample)
            self.tqdmBar.reset()
            self.tqdmBar.update(self.cur_sample)
            if self.repeat > 0:
                self.repeat -= 1

        self.sample_ptr += amount
        if self.sample_ptr >= self.nsample:
            self.sample_ptr -= self.nsample
        # print(f'{self.sample_ptr}, {data[0, :]}')
        self.LSLOutlet.push_chunk(x=data.tolist())
        # print(f'{elapsed_time}, ||| {self.sample_ptr} | \n')

class multi_stream_playbacker():
    def __init__(self, config_file) -> None:
        self.config_file = config_file
        self.single_stream_players = []

    def parseConfig(self, config_file=None):
        if config_file is None:
            config_file = self.config_file
        cfg = configparser.ConfigParser()
        cfg.read(config_file)
        self.streamNames = parseStrList(cfg.get('stream', 'streamNames'))
        self.repeat = cfg.getint('stream', 'repeat')
        self.push_interval = cfg.getfloat('stream', 'push_interval')
        self.stream_configs = {x: {} for x in self.streamNames}
        for sn in self.streamNames:
            self.stream_configs[sn]['fs'] = cfg.getfloat(sn, 'fs')
            self.stream_configs[sn]['channel_count'] = cfg.getint(sn, 'ch_count')
            self.stream_configs[sn]['filename'] = cfg.get(sn, 'file')
            self.stream_configs[sn]['skip_first_col'] = cfg.getboolean(sn, 'skip_first_col')            

    def init_streams(self):
        self.single_stream_players = [None] * len(self.streamNames)
        for i, sn in enumerate(self.streamNames):
            col_idx_to_read = [i + self.stream_configs[sn]['skip_first_col'] for i in range(self.stream_configs[sn]['channel_count'])]
            self.single_stream_players[i] = single_stream_playbacker(timer_interval=self.push_interval)
            self.single_stream_players[i].init_by_csv(filename=self.stream_configs[sn]['filename'], fs=self.stream_configs[sn]['fs'], col_idx=col_idx_to_read)
            self.single_stream_players[i].create_outlet_stream(streamName=sn, channel_count=self.stream_configs[sn]['channel_count'], fs=self.stream_configs[sn]['fs'])

    def start_streaming(self, repeat=None):
        # repeat = 0: no repeat, = 1: repeat one time, = -1: repeat infinite
        print('Once the playback starts, enter c or C to stop streaming')
        print('playback starts')
        if repeat is None:
            try:
                repeat = self.repeat # from config
            except:
                repeat = 0
        for sp in self.single_stream_players:
            sp.start_streaming(repeat=repeat)
    
    def stop_streaming(self):
        for sp in self.single_stream_players:
            sp.stop_streaming()

if __name__ == "__main__":
    if len(sys.argv) > 2:
        print('Too many arguments! The program will still continue and assume the first argument is the config file to read!')
    if len(sys.argv) == 1:
        config_file = 'config_multi_stream_player.ini'
    else:
        config_file = sys.argv[1]

    print(f'reading config: {config_file}')

    player = multi_stream_playbacker(config_file=config_file)
    player.parseConfig()
    player.init_streams()
    player.start_streaming()

    key = input('Enter c to stop')
    while key != 'c' and key != 'C':
        key = input('Enter c to stop')
    player.stop_streaming()