import numpy as np
import statsmodels.api as sm
import logging

# logger for this file
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)
handler = logging.FileHandler('/tmp/tracker.log')
handler.setLevel(logging.ERROR)
formatter = logging.Formatter('%(levelname)-8s-[%(filename)s:%(lineno)d]-%(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


class RAKF1D:

    def __init__(self,
                 initial_state,
                 system_model,
                 system_model_error,
                 measurement_error,
                 state_error_variance,
                 residual_threshold, adaptive_threshold,
                 estimator_parameter_count=1,
                 gamma=1,
                 model_type="uwb_imu"):
        """Initializes RAKF 1 Dimensional instance

        Args:
            initial_state (float): Initial system state
            system_model (float): System model equation coefficient
            system_model_error (float): System model error (variance of model error)
            measurement_error (float): measurement model error (variance of measurement error)
            state_error_variance (float): Initial state error variance
            residual_threshold (float): residual threshold value
            adaptive_threshold (float): Adaptive threshold value
            estimator_parameter_count (int, optional): Sample count for parameter estimation method. Defaults to 1.
            model_type (str, optional): Type of motion model. Defaults to "constant-position".
        """
        try:
            # timestamp
            self.time_previous = -1.0

            # model type
            self.model_type = model_type

            # states
            self.state_model_prediction = None
            self.state_model = initial_state  # X

            # system model
            self.system_model = system_model  # A
            self.system_model_error = system_model_error  # Q

            # measurement
            self.state_measurement_relation = 1  # C
            self.measurement_standard_deviation = np.sqrt(measurement_error)
            self.measurement_prediction = None

            # residual
            self.residual_threshold = residual_threshold  # c
            self.residual_weight = None
            self.residual_measurement = None
            self.residual_measurement_dash = None
            self.gamma = gamma

            # state error variance
            self.state_error_variance_prediction = None
            self.state_error_variance = state_error_variance  # P

            # state estimation
            self.state_estimation = None
            self.delta_state_estimate = None

            # gain
            self.gain = None

            # adaptive
            self.adaptive_factor = None
            self.adaptive_threshold = adaptive_threshold  # co

            # parameter estimation
            self.measurement_buffer = np.zeros(estimator_parameter_count)
            self.residual_weight_buffer = np.ones(estimator_parameter_count)
            self.position_buffer = np.zeros(estimator_parameter_count)
            self.param_est = sm.WLS(self.measurement_buffer, self.position_buffer, self.residual_weight_buffer)
            self.estimator_parameter_count = estimator_parameter_count

            if self.model_type == 'uwb_imu':
                self.velocity_buffer = np.zeros(estimator_parameter_count)
                self.acceleration_buffer = np.zeros(estimator_parameter_count)
            else:
                self.velocity_buffer = None
                self.acceleration_buffer = None

        except Exception as e:
            logging.critical(e)
            exit(-1)

    def run(self,
            current_measurement,
            timestamp_ms=0,
            velocity=0,
            acceleration=0):
        """Runs RAKF 1D algorithm

        Args:
            :param current_measurement:  Measurement
            :param timestamp_ms: Timestamp in milliseconds (since epoch). Defaults to 0.
            :param velocity: Velocity in meter per second. Defaults to 0.
            :param acceleration: Acceleration in meter per second^2. Defaults to 0.
        Returns:
            eqn_result, variable_result : Equation result and Variable result are dictionaries containing results of
            various parameters used in the algorithm calculation
        """
        try:
            # Get timedelta based on timestamp
            if self.time_previous < 0:
                timedelta = 0.0
            else:
                timedelta = timestamp_ms - self.time_previous
                timedelta /= 1000 # millisec to sec conversion
            self.time_previous = timestamp_ms

            # -----------------  Prediction  -----------------------------------
            # equation 29
            self.state_model_prediction = (self.system_model * self.state_model) + (velocity * timedelta) + \
                                          (acceleration * (timedelta ** 2) * 0.5)

            # equation 30
            self.state_error_variance_prediction = (self.system_model * self.state_error_variance * self.system_model) \
                                                   + self.system_model_error
            # ----------------  Updating  ---------------------------------------

            # equation 35
            self.measurement_prediction = self.state_measurement_relation * self.state_model_prediction

            # equation 34
            self.residual_measurement = current_measurement - self.measurement_prediction

            # equation 33
            self.residual_measurement_dash = abs(self.residual_measurement / self.measurement_standard_deviation)

            # equation 31 & 32
            if self.residual_measurement_dash <= self.residual_threshold:
                self.residual_weight = 1 / self.measurement_standard_deviation
            else:
                # self.residual_weight = self.residual_threshold / (self.residual_measurement_dash * \
                #                                                   self.measurement_standard_deviation)  # as per paper
                self.residual_weight = (self.residual_threshold / (self.residual_measurement_dash * 2 * self.gamma)) \
                                       * (1 / self.measurement_standard_deviation)  # as per avinaash

            # equation 37 (different from paper , because velocity and acceleration)
            # update position buffer
            self.position_buffer = np.roll(self.position_buffer, -1)  # Observed Position
            self.position_buffer[self.estimator_parameter_count - 1] = self.state_model

            self.measurement_buffer = np.roll(self.measurement_buffer, -1)
            self.measurement_buffer[self.estimator_parameter_count - 1] = current_measurement

            if self.model_type == 'uwb_imu':
                self.velocity_buffer = np.roll(self.velocity_buffer, -1)  # Observed velocity
                self.velocity_buffer[self.estimator_parameter_count - 1] = velocity

                self.acceleration_buffer = np.roll(self.acceleration_buffer, -1)  # Observed Acceleration
                self.acceleration_buffer[self.estimator_parameter_count - 1] = acceleration  # Observed acceleration

                uwb_imu_observation_matrix = np.stack(
                    [self.position_buffer, self.velocity_buffer, self.acceleration_buffer], axis=1)

                wls_model = sm.WLS(self.measurement_buffer, uwb_imu_observation_matrix,
                                   self.residual_weight_buffer).fit()  # with imu
                self.state_estimation = wls_model.predict(
                    [uwb_imu_observation_matrix[-1, 0], uwb_imu_observation_matrix[-1, 1],
                     uwb_imu_observation_matrix[-1, 2]])
            else:
                wls_model = sm.WLS(self.measurement_buffer, self.position_buffer,
                                   self.residual_weight_buffer).fit()  # without imu only
                self.state_estimation = wls_model.predict(self.position_buffer[self.estimator_parameter_count - 1])

            # equation 36
            self.delta_state_estimate = (self.state_estimation - self.state_model_prediction) / self.state_error_variance_prediction

            # equation 38
            if self.delta_state_estimate < self.adaptive_threshold:
                self.adaptive_factor = 1.0
            elif self.adaptive_threshold < self.delta_state_estimate < self.residual_threshold:
                self.adaptive_factor = (self.adaptive_threshold / self.delta_state_estimate * self.gamma)
            else:
                self.adaptive_factor = self.delta_state_estimate * self.gamma

            # equation 39
            reciprocal_adaptive_factor = 1 / self.adaptive_factor
            reciprocal_residual_weight = 1 / self.residual_weight
            numerator = reciprocal_adaptive_factor * self.state_error_variance_prediction * self.state_measurement_relation
            denominator = (reciprocal_adaptive_factor * self.state_measurement_relation * self.state_error_variance_prediction * self.state_measurement_relation) + reciprocal_residual_weight
            self.gain = numerator / denominator

            # equation 40
            self.state_model = self.state_model_prediction + (self.gain * self.residual_measurement)

            # equation 41
            # not done here, as normalization is not need for 1 D

            # equation 42
            self.state_error_variance = (1 - self.gain * self.state_measurement_relation) * self.state_error_variance_prediction

            # Activity related to eqn 37 , update parameters in parameter estimation based on states
            # self.param_est.adapt(self.state_model, self.measurement_buffer)
            self.residual_weight_buffer = np.roll(self.residual_weight_buffer, -1)
            self.residual_weight_buffer[self.estimator_parameter_count - 1] = self.residual_weight  # Weight

            eqn_result = {
                "residual_threshold": self.residual_threshold,
                "adaptive_threshold": self.adaptive_threshold,
                "eqn29": self.state_model_prediction,
                "eqn30": self.state_error_variance_prediction,
                "eqn35": self.measurement_prediction,
                "eqn34": self.residual_measurement,
                "eqn33": self.residual_measurement_dash,
                "eqn31": self.residual_weight,
                "eqn37": self.state_estimation,
                "eqn36": self.delta_state_estimate,
                "eqn38": self.adaptive_factor,
                "eqn39": self.gain,
                "eqn39_numerator": numerator,
                "eqn39_denominator": denominator,
                "eqn40": self.state_model,
                "eqn42": self.state_error_variance
            }

            variable_result = {
                "state_model_prediction": self.state_model_prediction,
                "state_error_variance_prediction": self.state_error_variance_prediction,
                "measurement_prediction": self.measurement_prediction,
                "residual_measurement": self.residual_measurement,
                "residual_measurement_dash": self.residual_measurement_dash,
                "residual_threshold": self.residual_threshold,
                "residual_weight": self.residual_weight,
                "state_estimation": self.state_estimation,
                "delta_state_estimate": self.delta_state_estimate,
                "adaptive_threshold": self.adaptive_threshold,
                "adaptive_factor": self.adaptive_factor,
                "gain_numerator": numerator,
                "gain_denominator": denominator,
                "gain": self.gain,
                "state_model": self.state_model,
                "state_error_variance": self.state_error_variance
            }
            logger.debug(eqn_result)
            logger.debug(variable_result)
            return float(self.state_model)
        except Exception as e:
            logging.critical(e)
            exit(-1)
