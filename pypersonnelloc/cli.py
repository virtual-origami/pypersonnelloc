import argparse
import asyncio
import functools
import os
import sys
import yaml
import signal
import logging
from pypersonnelloc.localization.Localization import get_tracker

logging.basicConfig(level=logging.WARNING, format='%(levelname)-8s [%(filename)s:%(lineno)d] %(message)s')

# logger for this file
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('/tmp/personnel_localization.log')
handler.setLevel(logging.ERROR)
formatter = logging.Formatter('%(levelname)-8s-[%(filename)s:%(lineno)d]-%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# TURN OFF asyncio logger
asyncio_logger = logging.getLogger('asyncio')
asyncio_logger.setLevel(logging.WARNING)

is_sighup_received = False


def parse_arguments():
    """Arguments to run the script"""
    parser = argparse.ArgumentParser(description='Personnel localization Service')
    parser.add_argument('--config', '-c', required=True,
                        help='YAML Configuration File for Personnel localization Service '
                             'with path')
    return parser.parse_args()


def signal_handler(name):
    print(f'signal_handler {name}')
    global is_sighup_received
    is_sighup_received = True


async def app(eventloop, config):
    """Main application for personnel localization service"""
    tracker_in_ws = []
    global is_sighup_received

    while True:
        # Read configuration
        try:
            tracker_config = read_config(config)
        except Exception as e:
            logger.error(f'Error while reading configuration: {e}')
            break

        logger.debug("Personnel localization Service Version: %s", tracker_config['version'])

        # check if amq or mqtt key description present in configuration
        if ("amq" not in tracker_config) and ("mqtt" not in tracker_config):
            logger.critical("Please provide either 'amq' or 'mqtt' configuration")
            sys.exit(-1)

        try:
            # robot instantiation
            for tracker in tracker_config["trackers"]:
                # check for protocol key
                if "protocol" not in tracker:
                    logger.critical("no 'protocol' key found.")
                    sys.exit(-1)

                if tracker['algorithm']['type'] == 'rakf':
                    tracker_rakf = get_tracker(event_loop=eventloop,
                                               config_file=tracker,
                                               algorithm="RAKF")
                    await tracker_rakf.connect()
                    tracker_in_ws.append(tracker_rakf)
                else:
                    logger.critical("Algorithm not support. Check configuration.")
                    sys.exit(-1)

        except Exception as e:
            logger.error(f'Error while reading configuration: {e}')
            break

        # continuously monitor signal handle and update tracker
        while not is_sighup_received:
            for each_tracker in tracker_in_ws:
                await each_tracker.update()
            await asyncio.sleep(each_tracker.interval)

        # If SIGHUP Occurs, Delete the instances
        for each_tracker in tracker_in_ws:
            del each_tracker

        # reset sighup handler flag
        is_sighup_received = False


def read_config(yaml_config_file):
    """Parse the given Configuration File"""
    if os.path.exists(yaml_config_file):
        with open(yaml_config_file, 'r') as config_file:
            yaml_as_dict = yaml.load(config_file, Loader=yaml.FullLoader)
        return yaml_as_dict['localization']
    else:
        raise FileNotFoundError
        logger.error('YAML Configuration File not Found.')


def main():
    """Initialization"""
    args = parse_arguments()
    if not os.path.isfile(args.config):
        logging.error("configuration file not readable. Check path to configuration file")
        sys.exit()

    event_loop = asyncio.get_event_loop()
    event_loop.add_signal_handler(signal.SIGHUP, functools.partial(signal_handler, name='SIGHUP'))
    event_loop.run_until_complete(app(event_loop, args.config))


if __name__ == "__main__":
    main()
