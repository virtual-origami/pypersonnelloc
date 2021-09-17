import sys
import logging
import json
import queue
from pypersonnelloc.pub_sub.AMQP import PubSubAMQP
from pypersonnelloc.algorithm.RAKF1D import RAKF1D
from pypersonnelloc.in_mem_db import RedisDB

# logger for this file
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler('/tmp/tracker.log')
handler.setLevel(logging.ERROR)
formatter = logging.Formatter('%(levelname)-8s-[%(filename)s:%(lineno)d]-%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


class RAKFLocalization:
    """Class implementation for Robust Adaptive Kalman Filter for 3 Dimension
    """

    def __init__(self, event_loop, config_file):
        """Initializes RAKF 3D class object

        Args:
            config_file (with extension .yaml): configuration yaml file containing configuration data for RAKF with corresponding Tag ID
            tag_id (int): Configuration data for corresponding Tag ID in configuration file to be used
        """
        try:
            self.track_dimension = config_file["algorithm"]['track_dimension']
            self.interval = config_file["algorithm"]["interval"]
            self.rakf_x = None
            self.rakf_y = None
            self.rakf_z = None
            self.publishers = []
            self.subscribers = []
            self.eventloop = event_loop
            self.consume_telemetry_queue = queue.SimpleQueue()
            self.redis_db = RedisDB(host=config_file["in_mem_db"]["server"]["address"],
                                    port=config_file["in_mem_db"]["server"]["port"],
                                    password=config_file["in_mem_db"]["credentials"]["password"])

            # validate track dimension
            if self.track_dimension > 3:
                logger.error(f"track_dimension {self.track_dimension} not supported. Check 'track_dimension' ")
                exit(-1)

            algorithm = config_file["algorithm"]

            # Based on the track dimension initial the class attributes
            if self.track_dimension > 0:
                self.rakf_x = RAKF1D(initial_state=0,
                                     system_model=algorithm["model"]["coefficient"]["x"],
                                     system_model_error=algorithm["error"]["model"]["x"],
                                     measurement_error=algorithm["error"]["measurement"]["x"],
                                     state_error_variance=algorithm["error"]["state_error_variance"]["x"],
                                     residual_threshold=algorithm["threshold"]["residual"]["x"],
                                     adaptive_threshold=algorithm["threshold"]["adaptive"]["x"],
                                     estimator_parameter_count=algorithm["estimator"]["parameter"]["count"],
                                     gamma=algorithm["threshold"]["gamma"]["x"],
                                     model_type=algorithm["model"]["type"])

            if self.track_dimension > 1:
                self.rakf_y = RAKF1D(initial_state=0,
                                     system_model=algorithm["model"]["coefficient"]["y"],
                                     system_model_error=algorithm["error"]["model"]["y"],
                                     measurement_error=algorithm["error"]["measurement"]["x"],
                                     state_error_variance=algorithm["error"]["state_error_variance"]["y"],
                                     residual_threshold=algorithm["threshold"]["residual"]["y"],
                                     adaptive_threshold=algorithm["threshold"]["adaptive"]["y"],
                                     estimator_parameter_count=algorithm["estimator"]["parameter"]["count"],
                                     gamma=algorithm["threshold"]["gamma"]["y"],
                                     model_type=algorithm["model"]["type"])

            if self.track_dimension > 2:
                self.rakf_z = RAKF1D(initial_state=0,
                                     system_model=algorithm["model"]["coefficient"]["z"],
                                     system_model_error=algorithm["error"]["model"]["z"],
                                     measurement_error=algorithm["error"]["measurement"]["x"],
                                     state_error_variance=algorithm["error"]["state_error_variance"]["z"],
                                     residual_threshold=algorithm["threshold"]["residual"]["z"],
                                     adaptive_threshold=algorithm["threshold"]["adaptive"]["z"],
                                     estimator_parameter_count=algorithm["estimator"]["parameter"]["count"],
                                     gamma=algorithm["threshold"]["gamma"]["z"],
                                     model_type=algorithm["model"]["type"])

            protocol = config_file["protocol"]
            for publisher in protocol["publishers"]:
                if publisher["type"] == "amq":
                    logger.debug('Setting Up AMQP Publisher for Personnel')
                    self.publishers.append(
                        PubSubAMQP(
                            eventloop=self.eventloop,
                            config_file=publisher,
                            binding_suffix=""
                        )
                    )
                else:
                    logger.error("Provide protocol amq config")
                    raise AssertionError("Provide protocol amq config")

            for subscribers in protocol["subscribers"]:
                if subscribers["type"] == "amq":
                    logger.debug('Setting Up AMQP Subcriber for Personnel')
                    self.subscribers.append(
                        PubSubAMQP(
                            eventloop=self.eventloop,
                            config_file=subscribers,
                            binding_suffix="",
                            app_callback=self._consume_telemetry_msg
                        )
                    )
                else:
                    logger.error("Provide protocol amq config")
                    raise AssertionError("Provide protocol amq config")

        except Exception as e:
            logging.critical(e)
            sys.exit(-1)

    async def _process_measurement(self, measurement):
        result = measurement
        pos_est_x = 0
        pos_est_y = 0
        pos_est_z = 0

        convert_g_to_mpss = lambda g: g * 9.8

        try:
            if (self.track_dimension > 0) and (self.rakf_x is not None):
                if self.rakf_x.model_type == 'uwb_imu':
                    pos_est_x = self.rakf_x.run(current_measurement=measurement["x_uwb_pos"],
                                                velocity=measurement['x_imu_vel'],
                                                acceleration=convert_g_to_mpss(g=0),
                                                timestamp_ms=measurement["timestamp"])
                else:
                    pos_est_x = self.rakf_x.run(current_measurement=measurement["x_uwb_pos"],
                                                timestamp_ms=measurement["timestamp"])

            if (self.track_dimension > 1) and (self.rakf_y is not None):
                if self.rakf_x.model_type == 'uwb_imu':
                    pos_est_y = self.rakf_y.run(current_measurement=measurement["y_uwb_pos"],
                                                velocity=measurement['y_imu_vel'],
                                                acceleration=convert_g_to_mpss(g=0),
                                                timestamp_ms=measurement["timestamp"])
                else:
                    pos_est_y = self.rakf_y.run(current_measurement=measurement["y_uwb_pos"],
                                                timestamp_ms=measurement["timestamp"])

            if (self.track_dimension > 2) and (self.rakf_z is not None):
                if self.rakf_x.model_type == 'uwb_imu':
                    pos_est_z = self.rakf_z.run(current_measurement=measurement["z_uwb_pos"],
                                                velocity=measurement['z_imu_vel'],
                                                acceleration=convert_g_to_mpss(g=0),
                                                timestamp_ms=measurement["timestamp"])
                else:
                    pos_est_z = self.rakf_z.run(current_measurement=measurement["z_uwb_pos"],
                                                timestamp_ms=measurement["timestamp"])

            result.update({
                "dimension": self.track_dimension,
                "x_est_pos": pos_est_x,
                "y_est_pos": pos_est_y,
                "z_est_pos": pos_est_z
            })
            return result
        except Exception as e:
            logging.critical(e)
            exit(-1)

    async def personnel_msg_handler(self,exchange_name, binding_name, message_body):

        # validate the message contents looking at the keys
        msg_attributes = message_body.keys()
        if ("id" in msg_attributes) and \
                ("x_imu_vel" in msg_attributes) and \
                ("y_imu_vel" in msg_attributes) and \
                ("z_imu_vel" in msg_attributes) and \
                ("x_uwb_pos" in msg_attributes) and \
                ("y_uwb_pos" in msg_attributes) and \
                ("z_uwb_pos" in msg_attributes) and \
                ("data_aggregator_id" in msg_attributes) and \
                ("timestamp" in msg_attributes):

            logger.debug(f'sub: exchange {exchange_name}: msg {message_body}')
            self.consume_telemetry_queue.put_nowait(item=message_body)

    async def _consume_telemetry_msg(self, **kwargs):
        try:
            # extract message attributes from message
            exchange_name = kwargs["exchange_name"]
            binding_name = kwargs["binding_name"]
            message_body = json.loads(kwargs["message_body"])

            # check for matching subscriber with exchange and binding name in all subscribers
            for subscriber in self.subscribers:
                # if subscriber.exchange_name == exchange_name:
                cb_str = subscriber.get_callback_handler_name()
                if cb_str is not None:
                    try:
                        cb = getattr(self, cb_str)
                    except:
                        logging.critical(f'No Matching handler found for {cb_str}')
                        continue
                    if cb is not None:
                        await cb(exchange_name=exchange_name, binding_name=binding_name, message_body=message_body)

        except Exception as e:
            logging.critical(e)
            sys.exit(-1)

    async def publish(self, exchange_name, msg):
        for publisher in self.publishers:
            if exchange_name == publisher.exchange_name:
                await publisher.publish(message_content=msg)
                logger.debug(f'pub: exchange:{exchange_name}, binding key: {publisher.queue_name}, msg:{msg}')

    async def connect(self):
        for publisher in self.publishers:
            await publisher.connect()

        for subscriber in self.subscribers:
            await subscriber.connect(mode="subscriber")

    def update_states(self, state_information):
        if self.rakf_x is not None:
            self.rakf_x.update_state(state_information["x"])

        if self.rakf_y is not None:
            self.rakf_y.update_state(state_information["y"])

        if self.rakf_z is not None:
            self.rakf_z.update_state(state_information["z"])

    def get_states_from_db(self, personnel_id):
        name = "personnel_"+personnel_id
        db_result = self.redis_db.get(key=name)
        if db_result is None:
            return None
        result = json.loads(db_result)
        return result

    def restore_states_in_db(self, personnel_id):
        state_information = {
            "x": self.rakf_x.state_to_dict(),
            "y": self.rakf_y.state_to_dict(),
            "z": self.rakf_z.state_to_dict()
        }
        name = "personnel_" + personnel_id
        json_state_information = json.dumps(state_information)
        self.redis_db.set(key=name, value=json_state_information)

    async def update(self):
        try:
            if not self.consume_telemetry_queue.empty():
                new_measurement = self.consume_telemetry_queue.get_nowait()

                new_measurement_id = new_measurement["id"]
                state_info = self.get_states_from_db(new_measurement_id)

                if state_info is not None and new_measurement_id is not None:
                    self.update_states(state_information=state_info)
                    result = await self._process_measurement(measurement=new_measurement)
                    self.restore_states_in_db(personnel_id=new_measurement_id)
                    result_plm = {
                        "id": result["id"],
                        "x_est_pos": result["x_est_pos"],
                        "y_est_pos": result["y_est_pos"],
                        "z_est_pos": result["z_est_pos"],
                        "timestamp": result["timestamp"]
                    }
                    await self.publish(exchange_name='plm_walker',
                                       msg=json.dumps(result_plm).encode())

                    await self.publish(exchange_name='visual',
                                       msg=json.dumps(result).encode())
        except queue.Empty as e:
            logging.info(f"Queue empty no pending messages, \n {e}")
