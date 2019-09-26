import sys
import os
from events.event_heap import EventHeap
from slices.slice import Slice


class Simulation:
    """
    Simulation for a network slicing strategy on MAC layer of a massive MIMO network

    Attributes
    ----------


    Methods
    -------
    run()
        Runs the simulation the full simulation length
    """

    _URLLC = 0
    _mMTC = 1

    _DEPARTURE = 2
    _URLLC_ARRIVAL = 3
    _mMTC_ARRIVAL = 4

    def __init__(self, config, stats, trace, no_urllc, no_mmtc, scheduler=None, traffic=None):
        """
        Initialize simulation object

        Parameters
        ----------
        config : dict
            Dictionary containing all configuration parameters
        stats : Stats
            Statistics object for keeping track for measurements
        """

        self.stats = stats
        self.trace = trace
        self.time = 0.0
        self.no_pilots = config.get('no_pilots')
        self.simulation_length = config.get('simulation_length')
        self.frame_length = config.get('frame_length')
        if scheduler is not None:
            self.pilot_strategy = scheduler
        else:
            self.pilot_strategy = config.get('strategy')

        self.strategy_mapping = {
            'FCFS_FCFS': self.__fist_come_first_served,
            'RRQ_RRQ': self.__round_robin_queue_info,
            'RRQ_FCFS': self.__round_robin_queue_first_come_first_served,
            'RRN_FCFS': self.__round_robin_no_queue_info_first_come_first_served,
            'RRN_RRQ': self.__round_robin_half_queue_info
        }
        self.event_heap = EventHeap()
        self.send_queue = {'_URLLC': [], '_mMTC': []}
        # used only in method "RR_NQ"

        self.Slices = [Slice(self._URLLC, no_urllc, traffic), Slice(self._mMTC, no_mmtc)]
        self.frame_counter = 0
        self.frame_loops = self.Slices[self._URLLC].get_node(0).deadline / self.frame_length
        self.node_pointer = 0

        for s in self.Slices:
            # Initialize nodes and their arrival times
            self.__initialize_nodes(s)

        # Initialize departure and measurement event
        self.event_heap.push(self._DEPARTURE, self.time + self.frame_length)

    def __initialize_nodes(self, _slice):
        nodes = _slice.pool
        # counter = 0
        # print("[Time {}] Initial {} nodes.".format(self.time, len(nodes)))
        for _node in nodes:
            next_arrival = _node.event_generator.get_init()
            if _slice.type == self._URLLC:
                self.stats.stats['no_urllc_arrivals'] += 1
                counter = self.stats.stats['no_urllc_arrivals']
            else:
                self.stats.stats['no_mmtc_arrivals'] += 1
                counter = self.stats.stats['no_mmtc_arrivals']
            self.event_heap.push(_slice.type+3,
                                 self.time + next_arrival, self.time + next_arrival + _node.deadline,
                                 nodes.index(_node), counter)

    def __handle_event(self, event):
        # Event switcher to determine correct action for an event
        event_actions = {
            self._URLLC_ARRIVAL: self.__handle_urllc_arrival,
            self._mMTC_ARRIVAL: self.__handle_mmtc_arrival,
            self._DEPARTURE: self.__handle_departure}
        event_actions[event.type](event)

    def __handle_urllc_arrival(self, event):
        # Handle an alarm arrival event
        self.stats.stats['no_urllc_arrivals'] += 1
        # print("[Time {}] No. of urllc_arrivals: {}".format(self.time, self.stats.stats['no_urllc_arrivals']))
        # Store event in send queue until departure (as LIFO)
        self.send_queue['_URLLC'].insert(0, event)
        node = self.Slices[self._URLLC].get_node(event.node_id)
        node.active = True
        next_arrival = node.event_generator.get_next()

        self.event_heap.push(self._URLLC_ARRIVAL,
                             self.time + next_arrival, self.time + next_arrival + node.deadline,
                             event.node_id, self.stats.stats['no_urllc_arrivals'])

    def __handle_mmtc_arrival(self, event):
        # Handle a control arrival event
        self.stats.stats['no_mmtc_arrivals'] += 1
        # print("[Time {}] No. of mmtc_arrivals: {}".format(self.time, self.stats.stats['no_mmtc_arrivals']))
        # Store event in send queue until departure (as LIFO)
        self.send_queue['_mMTC'].insert(0, event)

        node = self.Slices[self._mMTC].get_node(event.node_id)
        node.active = True
        next_arrival = node.event_generator.get_next()
        self.event_heap.push(self._mMTC_ARRIVAL,
                             self.time + next_arrival, self.time + next_arrival + node.deadline,
                             event.node_id, self.stats.stats['no_mmtc_arrivals'])

    def __handle_departure(self, event):
        # Handle a departure event
        # print("[Time {}] Departure".format(self.time))
        # print("[Time {}] Send queue size {}" .format(self.time, len(self.send_queue)))
        del event
        self.__handle_expired_events()
        self.__assign_pilots()
        # self.__check_collisions()
        # Add new departure event to the event list
        self.event_heap.push(self._DEPARTURE, self.time + self.frame_length)

    def __handle_expired_events(self):
        # remove the expired events in the send_queue
        for key in self.send_queue:
            queue = self.send_queue[key]
            queue_length = len(queue)
            remove_indices = []

            for i in range(queue_length):
                event = queue[i]
                if event.dead_time < self.time:
                    remove_indices.append(i)

            # Remove the events in reversed order to not shift subsequent indices
            for i in sorted(remove_indices, reverse=True):
                event = queue[i]
                if event.type == self._URLLC_ARRIVAL:
                    node = self.Slices[self._URLLC].get_node(event.node_id)
                    node.active = False
                    self.stats.stats['no_missed_urllc'] += 1
                    entry = event.get_entry(self.time, False)
                    self.trace.write_trace(entry)
                elif event.type == self._mMTC_ARRIVAL:
                    node = self.Slices[self._mMTC].get_node(event.node_id)
                    node.active = False
                    self.stats.stats['no_missed_mmtc'] += 1
                    entry = event.get_entry(self.time, False)
                # print(entry)
                    self.trace.write_trace(entry)
                del event
                del self.send_queue[key][i]

        # if len(remove_indices) > 0:
        #       print("\n[Time {}] Lost {} URLLC packets, {} mMTC packets\n"
        #               .format(self.time, urllc_counter, mmtc_counter))

    def __assign_pilots(self):
        self.strategy_mapping[self.pilot_strategy]()

    def run(self):
        """ Runs the simulation """

        current_progress = 0
        # print("\n[Time {}] Simulation start.".format(self.time))
        # print("Size: {}".format(self.event_heap.get_size()))
        # for k in self.event_heap.get_heap():
        #     print(k)
        while self.time < self.simulation_length:
            # print("[Time {}] Event heap size {}".format(self.time, self.event_heap.size()))
            next_event = self.event_heap.pop()[3]
            # print("Handle event: {} generated at time {}".format(next_event.type, next_event.time))

            # Advance time before handling event
            self.time = next_event.time

            # progress = round(100 * self.time / self.simulation_length)
            #
            # if progress > current_progress:
            #     current_progress = progress
            #     str1 = "\rProgress: {0}%".format(progress)
            #     sys.stdout.write(str1)
            #     sys.stdout.flush()

            self.__handle_event(next_event)

        # print('\n[Time {}] Simulation complete.'.format(self.time))

    def __fist_come_first_served(self):
        no_pilots = self.no_pilots
        urllc_events = self.send_queue['_URLLC'].copy()
        mmtc_events = self.send_queue['_mMTC'].copy()

        urllc_events.sort(key=lambda x: x.dead_time)
        for event in urllc_events:
            urllc_pilots = self.Slices[self._URLLC].get_node(event.node_id).pilot_samples
            no_pilots -= urllc_pilots
            if no_pilots >= 0:
                # remove the event that assigned the pilots from the list
                entry = event.get_entry(self.time, True)
                # print(entry)
                self.trace.write_trace(entry)
                self.send_queue['_URLLC'].remove(event)
                # print(no_pilots, len(self.send_queue['_URLLC']), len(urllc_events))
            else:
                # print("pilot not enough")
                break

        if no_pilots > 0:
            mmtc_events.sort(key=lambda x: x.dead_time)
            for event in mmtc_events:
                mmtc_pilots = self.Slices[self._mMTC].get_node(event.node_id).pilot_samples
                no_pilots -= mmtc_pilots
                if no_pilots >= 0:
                    entry = event.get_entry(self.time, True)
                    # print(entry)
                    self.trace.write_trace(entry)
                    self.send_queue['_mMTC'].remove(event)
                else:
                    break

    def __round_robin_queue_info(self):
        no_pilots = self.no_pilots
        _urllc_nodes = self.Slices[self._URLLC].pool
        for _node in _urllc_nodes:
            ind = _urllc_nodes.index(_node)
            events = list(filter(lambda e: e.node_id == ind, self.send_queue['_URLLC']))
            for event in events:
                no_pilots -= _node.pilot_samples
                if no_pilots >= 0:
                    entry = event.get_entry(self.time, True)
                    self.trace.write_trace(entry)
                    self.send_queue['_URLLC'].remove(event)
                    del event
                else:
                    return

        if no_pilots > 0:
            _mmtc_nodes = self.Slices[self._mMTC].pool
            for _node in _mmtc_nodes:
                ind = _mmtc_nodes.index(_node)
                events = list(filter(lambda e: e.node_id == ind, self.send_queue['_mMTC']))
                for event in events:
                    no_pilots -= _node.pilot_samples
                    if no_pilots >= 0:
                        entry = event.get_entry(self.time, True)
                        self.trace.write_trace(entry)
                        self.send_queue['_mMTC'].remove(event)
                        del event
                    else:
                        return

    def __round_robin_queue_first_come_first_served(self):
        no_pilots = self.no_pilots
        _urllc_nodes = self.Slices[self._URLLC].pool
        for _node in _urllc_nodes:
            ind = _urllc_nodes.index(_node)
            events = list(filter(lambda e: e.node_id == ind, self.send_queue['_URLLC']))
            for event in events:
                no_pilots -= _node.pilot_samples
                if no_pilots >= 0:
                    entry = event.get_entry(self.time, True)
                    self.trace.write_trace(entry)
                    self.send_queue['_URLLC'].remove(event)
                    del event
                else:
                    return

        if no_pilots > 0:
            mmtc_events = self.send_queue['_mMTC']
            mmtc_events.sort(key=lambda x: x.dead_time, reverse=True)
            for event in mmtc_events:
                mmtc_pilots = self.Slices[self._mMTC].get_node(event.node_id).pilot_samples
                no_pilots -= mmtc_pilots
                if no_pilots >= 0:
                    entry = event.get_entry(self.time, True)
                    # print(entry)
                    self.trace.write_trace(entry)
                    self.send_queue['_mMTC'].remove(event)
                    del event
                else:
                    break

    def __round_robin_half_queue_info(self):
        self.frame_counter = (self.frame_counter + 1) % self.frame_loops
        if self.frame_counter == 1:
            self.node_pointer = 0
        start_ind = self.node_pointer
        no_pilots = self.no_pilots
        for i in range(start_ind, len(self.Slices[self._URLLC].pool)):
            _node = self.Slices[self._URLLC].get_node(i)
            no_pilots -= _node.pilot_samples
            if no_pilots >= 0:
                self.node_pointer += 1
                _node.assigned = True
            else:
                no_pilots += _node.pilot_samples
                break
        if no_pilots > 0:
            _mmtc_nodes = self.Slices[self._mMTC].pool
            for _node in _mmtc_nodes:
                ind = _mmtc_nodes.index(_node)
                events = list(filter(lambda e: e.node_id == ind, self.send_queue['_mMTC']))
                for event in events:
                    no_pilots -= _node.pilot_samples
                    if no_pilots >= 0:
                        entry = event.get_entry(self.time, True)
                        self.trace.write_trace(entry)
                        self.send_queue['_mMTC'].remove(event)
                        del event
                    else:
                        break
        self.__handle_send_queue()
        # handles only queue for first slice

    def __round_robin_no_queue_info_first_come_first_served(self):
        self.frame_counter = (self.frame_counter + 1) % self.frame_loops
        if self.frame_counter == 1:
            self.node_pointer = 0
        start_ind = self.node_pointer
        no_pilots = self.no_pilots
        for i in range(start_ind, len(self.Slices[self._URLLC].pool)):
            _node = self.Slices[self._URLLC].get_node(i)
            no_pilots -= _node.pilot_samples
            if no_pilots >= 0:
                self.node_pointer += 1
                _node.assigned = True
            else:
                no_pilots += _node.pilot_samples
                break
        if no_pilots > 0:
            mmtc_events = self.send_queue['_mMTC']
            mmtc_events.sort(key=lambda x: x.dead_time, reverse=True)
            for event in mmtc_events:
                mmtc_pilots = self.Slices[self._mMTC].get_node(event.node_id).pilot_samples
                no_pilots -= mmtc_pilots
                if no_pilots >= 0:
                    entry = event.get_entry(self.time, True)
                    # print(entry)
                    self.trace.write_trace(entry)
                    self.send_queue['_mMTC'].remove(event)
                    del event
                else:
                    break
        self.__handle_send_queue()

    def __handle_send_queue(self):
        # Used only for RR_NQ method, applied after pilots assignment
        # for key in self.send_queue:
        #     if key == '_URLLC':
        #         s = self._URLLC
        #     else:
        #         s = self._mMTC
        key = '_URLLC'
        s = self._URLLC
        queue = self.send_queue[key].copy()
        events_assigend = list(filter(lambda e: self.Slices[s].get_node(e.node_id).assigned, queue))
        # if key == '_URLLC':
        #     print([e.node_id for e in queue])
        #     print([e.node_id for e in events_assigend])
        overlapped_event = []
        for event in events_assigend:
            if event in overlapped_event:
                continue
            events_from_same_node = list(filter(lambda e: e.node_id == event.node_id, events_assigend))
            if len(events_from_same_node) == 1:
                self.send_queue[key].remove(event)
                # if event.type == self._URLLC_ARRIVAL:
                #     print(event.node_id)
                entry = event.get_entry(self.time, True)
                self.trace.write_trace(entry)
                self.Slices[s].get_node(event.node_id).active = False
            else:
                self.Slices[s].get_node(event.node_id).active = True
                # print("overlapped")
                events_from_same_node.sort(key=lambda e: e.dead_time)
                # print([(e.node_id, e.counter) for e in events_from_same_node])
                # print([(e.node_id, e.counter) for e in self.send_queue[key]])
                self.send_queue[key].remove(events_from_same_node[0])
                entry = events_from_same_node[0].get_entry(self.time, True)
                # if event.type == self._URLLC_ARRIVAL:
                #     print(events_from_same_node[0].node_id)
                self.trace.write_trace(entry)
                for e in events_from_same_node:
                    overlapped_event.append(e)

    def write_result(self):
        result_dir = "results/"+self.pilot_strategy
        reliability = self.Slices[self._URLLC].get_node(0).reliability_profile
        deadline = self.Slices[self._URLLC].get_node(0).deadline_profile
        urllc_file_name = result_dir + "/" + reliability + "_" + deadline + "_URLLC.csv"
        mmtc_file_name = result_dir + "/" + reliability + "_" + deadline + "_mMTC.csv"

        data = self.trace.get_waiting_time()

        try:
            os.mkdir(result_dir)
        except OSError:
            pass
            # print("Directory exists")

        try:
            file = open(urllc_file_name, 'a')
            file.write(str(self.Slices[0].no_nodes) + ','
                       + str(self.Slices[1].no_nodes) + ','
                       + str(data[0][0]) + ','
                       + str(data[0][1]) + ','
                       + str(data[0][2]) + ','
                       + str(data[0][3]) + ','
                       + str(self.trace.get_loss_rate()[0]) + '\n'
                       )
        except FileNotFoundError:
            print("No file found, create the file first")
            file = open(urllc_file_name, 'w+')
            file.write("No.URLLC,No.mMTC,mean,var,conf_inter_up,conf_inter_low,loss\n")
            file.write(str(self.Slices[0].no_nodes) + ','
                       + str(self.Slices[1].no_nodes) + ','
                       + str(data[0][0]) + ','
                       + str(data[0][1]) + ','
                       + str(data[0][2]) + ','
                       + str(data[0][3]) + ','
                       + str(self.trace.get_loss_rate()[0]) + '\n'
                       )
        file.close()
        try:
            file = open(mmtc_file_name, 'a')
            file.write(str(self.Slices[0].no_nodes) + ','
                       + str(self.Slices[1].no_nodes) + ','
                       + str(data[1][0]) + ','
                       + str(data[1][1]) + ','
                       + str(data[1][2]) + ','
                       + str(data[1][3]) + ','
                       + str(self.trace.get_loss_rate()[1]) + '\n'
                       )
        except FileNotFoundError:
            print("No file found, create the file first")
            file = open(mmtc_file_name, 'w+')
            file.write("No.URLLC,No.mMTC,mean,var,conf_inter_up,conf_inter_low,loss\n")
            file.write(str(self.Slices[0].no_nodes) + ','
                       + str(self.Slices[1].no_nodes) + ','
                       + str(data[1][0]) + ','
                       + str(data[1][1]) + ','
                       + str(data[1][2]) + ','
                       + str(data[1][3]) + ','
                       + str(self.trace.get_loss_rate()[1]) + '\n'
                       )
        file.close()


