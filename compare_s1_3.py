import os
import numpy as np
from multiprocessing import Pool
import json
import time
import datetime

PROCESSES = 4

with open('default_config.json') as config_file:
    config = json.load(config_file)

with open('nodes/node_config.json') as node_config:
    node = json.load(node_config)

total_pilots = config.get("no_pilots")
slot_time = config.get("frame_length")

mmtc_period = node.get("deadline_par").get(node.get("mmtc").get("deadline"))
mmtc_pilot = 1

period = {"long": 10,
          "short": 1}
pilots = {"high": 3,
          "low": 1}

reliability = "low"
deadline = "long"

urllc_period = period[deadline]
urllc_pilot = pilots[reliability]

SEED = round(time.time() / 100)


def rho2urllc(rho):
    urllc = rho * total_pilots * urllc_period / (urllc_pilot * slot_time)
    return int(round(urllc))


def rho2mmtc(rho):
    mmtc = rho * total_pilots * mmtc_period / (mmtc_pilot * slot_time)
    return int(round(mmtc))


simulations = []

mmtc_load = 0.5
no_mmtc = rho2mmtc(mmtc_load)
urllc_loads = np.linspace(0.1, 1, 10)
no_urllc_list = [rho2urllc(rho) for rho in urllc_loads]

scheduler = "FCFS_FCFS"
for no_urllc in no_urllc_list:
    SEED += np.random.randint(100)
    simulations.append("python3 main.py \
                        --scheduler {} --reliability {} --deadline {} \
                        --urllc_node {} --mmtc_node {} \
                        --seed {}".format(
        scheduler, reliability, deadline, no_urllc, no_mmtc, SEED))

scheduler = "RRN_FCFS"
for no_urllc in no_urllc_list:
    SEED += np.random.randint(100)
    simulations.append("python3 main.py \
                        --scheduler {} --reliability {} --deadline {} \
                        --urllc_node {} --mmtc_node {} \
                        --seed {}".format(
        scheduler, reliability, deadline, no_urllc, no_mmtc, SEED))

scheduler = "RRQ_FCFS"
for no_urllc in no_urllc_list:
    SEED += np.random.randint(100)
    simulations.append("python3 main.py \
                        --scheduler {} --reliability {} --deadline {} \
                        --urllc_node {} --mmtc_node {} \
                        --seed {}".format(
        scheduler, reliability, deadline, no_urllc, no_mmtc, SEED))


pool = Pool(processes=PROCESSES)
for k, simulation in enumerate(simulations):
    pool.apply_async(os.system, (simulation,))

pool.close()
pool.join()
print("All simulations completed")

date = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%f")
file = open("time.txt", "w+")
file.write(date)
file.close
