# IOM file reader and plotter
import re
import mne
import h5py
import datetime
import numpy as np
import pandas as pd


class IOM_file():
    def __init__(self, path):
        self.path = path
        self.is_ecog_present = True
        self.is_eeg_present = True
        self.offset_hours = 0

        # EEG data
        self.eeg_fs = 500
        self.eeg_data = []
        self.eeg_channels = []
        self.eeg_timestamps = []

        # ECOG data
        self.ecog_data = []
        self.ecog_channels = []
        self.ecog_timestamps = []

        # Stim data
        self.stim_amp = []
        self.stim_duration = []

        self.log = '' # log file
        self.f_name = re.findall(r'[A-Z]{3}_.{6}', self.path)[0]
    
    def format_data(self):
        # Handle log data formatting if log exists
        if len(self.log) > 0:
            log_times = [i[1].decode('utf-8') for i in self.log]
            log_comment = [i[0].decode('utf-8') for i in self.log]
            self.log = pd.DataFrame({'Time':log_times, 'Comment':log_comment})
            self.log['Time'] = pd.to_datetime(self.log['Time'], format='%d-%b-%Y %H:%M:%S')
        else:
            # Create empty DataFrame if no log data
            self.log = pd.DataFrame({'Time': [], 'Comment': []})

        if self.is_ecog_present:
            self.stim_duration = [[i[0].decode('utf-8'), i[1].decode('utf-8')] for i in self.stim_duration]
            self.ecog_timestamps = [i[0].decode('utf-8') for i in self.ecog_timestamps]
            self.ecog_channels = [i.decode('utf-8') for i in self.ecog_channels[0]]
        
        if self.is_eeg_present:
            self.eeg_channels = [i.decode('utf-8')[13:] for i in self.eeg_channels[0]]
            for i in range(len(self.eeg_timestamps)):
                self.eeg_timestamps[i] = [j[0].decode('utf-8') for j in self.eeg_timestamps[i]]
        
    
    def read_data(self, format=True):
        with h5py.File(self.path, "r") as f:
            # Reading EEG Data
            try:
                sig_names = np.array(f['eeg_data'])
                sig_names = sorted(sig_names)
                for i in sig_names:
                    self.eeg_data.append(np.array(f['eeg_data'][i]))
                    self.eeg_timestamps.append(np.array(f['eeg_timestamp'][i]))
                self.eeg_channels = np.array(f['channel_names'])
            except Exception as e:
                self.is_eeg_present = False

            # Reading ECOG Data
            try:
                self.ecog_data = np.array(f['ecog_data'])
                self.ecog_channels = np.array(f['ecog_channels'])
                self.ecog_timestamps = np.array(f['ecog_timestamp'])
                
            except Exception as e:
                self.is_ecog_present = False

            try:
                # Reading Stim data
                self.stim_amp = np.array(f['stim_amp_data'])
                self.stim_duration = np.array(f['stim_duration'])
            except Exception as e:
                self.stim_amp = []
                self.stim_duration = []

            try:
                # Reading Log data
                self.log = np.array(f['log'])
            except Exception as e:
                # If no log data is present, create empty log
                self.log = []
        
        if (format == True):
            self.format_data()
            offset_hours = self.get_timezone_offset(self.log['Time'][0])
            self.offset_hours = offset_hours
                
        
    def get_timezone_offset(self, dt):
        month = dt.month
        if 3 <= month <= 10:
            return 4  # EDT (UTC-4)
        else:
            return 5  # EST (UTC-5)
    
    def set_events(self, sig):
        onsets = []
        durations = []
        descriptions = []
        
        
        for i in range(len(self.log)):
            # Determine the correct timezone offset
            log_time = self.log['Time'][i] - datetime.timedelta(hours=self.offset_hours)
            log_time = log_time.replace(tzinfo=datetime.timezone.utc)
            log_comment = self.log['Comment'][i].strip()
            log_comment = log_comment.replace(',', ';') # Replace commas to avoid issues in CSV
            if log_time >= sig.info['meas_date'] and log_time < (sig.info['meas_date'] + datetime.timedelta(seconds=sig.n_times / sig.info['sfreq'])):
                onsets.append((log_time - sig.info['meas_date']).total_seconds())
                durations.append(0)
                descriptions.append(log_comment)
        events = mne.Annotations(onset=onsets, duration=durations, description=descriptions)
        sig.set_annotations(events)
        return sig      
    
    def plot_ecog(self):
        info_object = mne.create_info(ch_names = self.ecog_channels, sfreq=600)
        mne_arr = mne.io.RawArray(self.ecog_data, info_object)
        start_time = datetime.datetime.strptime(self.ecog_timestamps[0], '%d-%b-%Y %H:%M:%S')
        start_time = start_time.replace(tzinfo=datetime.timezone.utc).timestamp()
        mne_arr.set_meas_date(start_time)
        with mne.viz.use_browser_backend('qt'):
            mne_arr.plot(time_format='clock', block=True, theme="light")
    
    def join_eeg_timestamps(self):
        if len(self.eeg_timestamps) == 1:
            return self.eeg_data[0], self.eeg_timestamps[0][0]
        else:
            all_data = []
            for i in range(len(self.eeg_timestamps)):
                all_data.append({
                    'eeg_data' : self.eeg_data[i],
                    'start_timestamp' : self.eeg_timestamps[i][0],
                    'end_timestamp' : self.eeg_timestamps[i][-1]
                })
            
            sorted_data = sorted(all_data, key=lambda x: datetime.datetime.strptime(x['start_timestamp'], '%d-%b-%Y %H:%M:%S'))
            
            full_eeg_data = sorted_data[0]['eeg_data']
            start_time = sorted_data[0]['start_timestamp']
            for idx in range(1, len(sorted_data)):
                curr_data = sorted_data[idx]
                t1 = datetime.datetime.strptime(curr_data['start_timestamp'], '%d-%b-%Y %H:%M:%S')
                t2 = datetime.datetime.strptime(sorted_data[idx-1]['end_timestamp'], '%d-%b-%Y %H:%M:%S')
                difference = t1 - t2
                if (difference < datetime.timedelta(0)):
                    full_eeg_data = np.concatenate((full_eeg_data, curr_data['eeg_data']), axis=1)
                else:
                    zeros = np.zeros((len(self.eeg_channels), int(difference.total_seconds()) * self.eeg_fs))
                    full_eeg_data = np.concatenate((full_eeg_data, zeros, curr_data['eeg_data']), axis=1)

            return full_eeg_data, start_time
    
    def fix_channels(self, eeg_data):
        chans = self.eeg_channels
        found_ecog_data = []
        other_channel_data = []
        for c in range(len(chans)):
            chan_name = chans[c]
            ans = re.findall('^\s*(?:[A-Za-z]+\d*|\d+)\s*-\s*(?:[A-Za-z]+\d*|\d+)\s*$', chan_name.lower().strip())
            if (len(ans) == 1):
                found_ecog_data.append({
                    'channel' : chan_name,
                    'data' : eeg_data[c, :]
                })
            else:
                other_channel_data.append({
                    'channel' : chan_name,
                    'data' : eeg_data[c, :]
                })
        
        correct_channels = sorted(found_ecog_data, key=lambda x: x['channel'])
        other_channel_data = sorted(other_channel_data, key=lambda x: x['channel'])
        new_eeg_data = correct_channels[0]['data']
        new_channels = [correct_channels[0]['channel']]
        new_eeg_data = np.expand_dims(new_eeg_data, axis=0) 
        for m in correct_channels[1:]:
            c_data = np.expand_dims(m['data'], axis=0) 
            new_eeg_data = np.concatenate((new_eeg_data, c_data), axis=0)
            new_channels.append(m['channel'])
        for m in other_channel_data:
            c_data = np.expand_dims(m['data'], axis=0) 
            new_eeg_data = np.concatenate((new_eeg_data, c_data), axis=0)
            new_channels.append(m['channel'])
        return new_eeg_data, new_channels
    
    def plot_eeg(self, title, block=True, idx=False):
        if idx == False:
            eeg_data, start_time = self.join_eeg_timestamps()
            eeg_data, channels = self.fix_channels(eeg_data)
            start_time = datetime.datetime.strptime(start_time, '%d-%b-%Y %H:%M:%S')
            start_time = start_time.replace(tzinfo=datetime.timezone.utc).timestamp()
            info_object = mne.create_info(ch_names = channels, sfreq=self.eeg_fs)
            mne_arr = mne.io.RawArray(eeg_data, info_object)
        else:
            info_object = mne.create_info(ch_names = self.eeg_channels, sfreq=self.eeg_fs)
            mne_arr = mne.io.RawArray(self.eeg_data[idx], info_object)
            channels = self.eeg_channels
            start_time = datetime.datetime.strptime(self.eeg_timestamps[idx][0], '%d-%b-%Y %H:%M:%S')
            start_time = start_time.replace(tzinfo=datetime.timezone.utc).timestamp()
        
        start_time = start_time - (self.offset_hours * 3600)
        mne_arr.set_meas_date(start_time)
        mne_arr = self.set_events(mne_arr)

        with mne.viz.use_browser_backend('qt'):
            mne_arr.plot(time_format='clock', block=block, theme="light", precompute=False, title=title)
        
        return mne_arr, start_time, channels
