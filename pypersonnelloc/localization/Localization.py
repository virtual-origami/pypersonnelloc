import sys
import logging
from algorithm.RAKFLocalization import RAKFLocalization

# logger for this file
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('/tmp/tracker.log')
handler.setLevel(logging.ERROR)
formatter = logging.Formatter('%(levelname)-8s-[%(filename)s:%(lineno)d]-%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def get_tracker(event_loop, config_file, algorithm, id, start_coordinates):
    try:
        if algorithm == "RAKF":
            algo = RAKFLocalization(event_loop=event_loop,
                                    config_file=config_file,
                                    id=id,
                                    start_coordinates=start_coordinates)
            return algo
        else:
            raise AssertionError("Algorithm not supported")

    except Exception as e:
        logging.critical(e)
        sys.exit(-1)
