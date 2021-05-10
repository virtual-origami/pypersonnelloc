# pypersonnelloc

pypersonnelloc is personnel localization service to extract estimate of position coordinate in a noisy indoor environment.

Following algorithm are supported

1. Robust Adaptive Kalman Filter

## Development

### Python3.x

1. Create a Virtual Environment
   
        $ virtualenv -m venv venv

2. Activate Virtual Environment

        $ . venv/bin/activate 

3. Install the Dependencies

        pip install -r requirements.txt

4. Install `pypersonnelloc` as python package for development:

        pip install -e .

   This makes the `personnel-localization` binary available as a CLI

### Usage
Basic usage:

    $ personnel-localization -c config.yaml

### Message Broker (RabbitMQ)

Use the [rabbitmqtt](https://github.com/virtual-origami/rabbitmqtt) stack for the Message Broker

__NOTE__: The `rabbitmqtt` stack needs an external docker network called `iotstack` make sure to create one using `docker network create iotstack`

### Docker

1. To build Docker Images locally use:

        docker build -t pypersonnelloc .

2. To run the Application along with the RabbitMQ Broker connect the container with the `iotstack` network using:

        docker run --rm --network=iotstack pypersonnelloc
    
    __INFO__: Change the broker address in the `config.yaml` file to `rabbitmq` (name of the RabbitMQ Container in _rabbitmqtt_ stack)

3. To run the a custom configuration for the Container use:

        docker run --rm -v $(pwd)/config.yaml:/pypersonnelloc/config.yaml --network=iotstack pypersonnelloc

### Reference Paper

1. Heading Estimation for Pedestrian Dead Reckoning Based on Robust Adaptive Kalman Filtering 

   https://doi.org/10.3390/s18061970 

