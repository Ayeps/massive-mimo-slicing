import numpy as np
import scipy.stats as st


class Trace:
    _URLLC_ARRIVAL = 3
    _mMTC_ARRIVAL = 4

    def __init__(self, trace_file_path, log=False):
        self.log = log
        if log is True:
            self.__trace_file = open(trace_file_path, 'w+')
            self.__trace_file.write('Event,Node,Counter,Arrival,Dead,Departure,Pilot\n')
        else:
            self.__trace_file = None
        self.keys = ['event_type', 'node_id', 'counter', 'arrival_time', 'dead_time', 'departure_time', 'pilot']
        self.Dict = dict((key, []) for key in self.keys)
        self.plot_path = None
        self.urllc = {}
        self.mmtc = {}

    def close(self):
        if self.log is True:
            self.__trace_file.close()
        else:
            pass

    def write_trace(self, entry):
        if self.log is True:
            self.__trace_file.write(str(entry[self.keys[0]]) + ',' + str(entry[self.keys[1]]) + ','
                                    + str(entry[self.keys[2]]) + ',' + str(entry[self.keys[3]]) + ','
                                    + str(entry[self.keys[4]]) + ',' + str(entry[self.keys[5]]) + ','
                                    + str(entry[self.keys[6]]) + '\n')

        for i in range(len(entry)):
            k = self.keys[i]
            self.Dict[k] = np.append(self.Dict[k], entry[k])

    def process(self):
        keys = ['arrival_time', 'dead_time', 'departure_time', 'pilot']
        self.urllc = dict((key, []) for key in keys)
        self.mmtc = dict((key, []) for key in keys)
        event_type = self.Dict['event_type']
        arrivals = self.Dict[keys[0]]
        dead = self.Dict[keys[1]]
        departure = self.Dict[keys[2]]
        pilots = self.Dict[keys[3]]
        for i in range(np.size(event_type)):
            if event_type[i] == self._URLLC_ARRIVAL:
                self.urllc[keys[0]] = np.append(self.urllc[keys[0]], arrivals[i])
                self.urllc[keys[1]] = np.append(self.urllc[keys[1]], dead[i])
                self.urllc[keys[2]] = np.append(self.urllc[keys[2]], departure[i])
                self.urllc[keys[3]] = np.append(self.urllc[keys[3]], pilots[i])
            elif event_type[i] == self._mMTC_ARRIVAL:
                self.mmtc[keys[0]] = np.append(self.mmtc[keys[0]], arrivals[i])
                self.mmtc[keys[1]] = np.append(self.mmtc[keys[1]], dead[i])
                self.mmtc[keys[2]] = np.append(self.mmtc[keys[2]], departure[i])
                self.mmtc[keys[3]] = np.append(self.mmtc[keys[3]], pilots[i])

    def get_waiting_time(self):
        urllc_wait = self.__get_urllc_wait()
        mmtc_wait = self.__get_mmtc_wait()
        return urllc_wait, mmtc_wait

    def get_loss_rate(self):
        urllc_loss = self.__get_urllc_loss()
        mmtc_loss = self.__get_mmtc_loss()
        return urllc_loss, mmtc_loss

    def __get_urllc_wait(self):
        arrival_time = self.urllc['arrival_time']
        departure_time = self.urllc['departure_time']
        pilots = self.urllc['pilot']
        wait_time = np.array(departure_time) - np.array(arrival_time)

        for ind in range(len(pilots)):
            if not pilots[ind]:
                np.delete(wait_time, ind)
        avg_wait = np.mean(wait_time)
        std_wait = np.std(wait_time)
        if std_wait > 0.0:
            con_interval = st.t.interval(0.95, len(wait_time) - 1, loc=avg_wait, scale=st.sem(wait_time))
        else:
            con_interval = (avg_wait, avg_wait)

        return avg_wait, std_wait, con_interval[0], con_interval[1]

    def __get_urllc_loss(self):
        pilots = self.urllc['pilot']
        loss_counter = 0
        for ind in range(len(pilots)):
            if not pilots[ind]:
                loss_counter += 1
        return loss_counter/len(pilots)

    def __get_mmtc_loss(self):
        pilots = self.mmtc['pilot']
        loss_counter = 0
        for ind in range(len(pilots)):
            if not pilots[ind]:
                loss_counter += 1
        return loss_counter / len(pilots)

    def __get_mmtc_wait(self):
        arrival_time = self.mmtc['arrival_time']
        departure_time = self.mmtc['departure_time']
        pilots = self.mmtc['pilot']
        wait_time = np.array(departure_time) - np.array(arrival_time)
        for ind in range(len(pilots)):
            if not pilots[ind]:
                np.delete(wait_time, ind)
        avg_wait = np.mean(wait_time)
        std_wait = np.std(wait_time)
        if std_wait > 0.0:
            con_interval = st.t.interval(0.95, len(wait_time) - 1, loc=avg_wait, scale=st.sem(wait_time))
        else:
            con_interval = (avg_wait, avg_wait)
        return avg_wait, std_wait, con_interval[0], con_interval[1]

    def print_results(self):
        print("------------------------------------------------------")
        print("      | Total Arrivals | Packet loss | Avg_wait_time |")
        print("URLLC | {}           |{}          |{}|"
              .format(len(self.urllc['pilot']), self.__get_urllc_loss(), self.__get_urllc_wait()))
        print("mMTC  | {}          |{}|{}|"
              .format(len(self.mmtc['pilot']), self.__get_mmtc_loss(), self.__get_mmtc_wait()))
        print("-------------------------------------------------------")
