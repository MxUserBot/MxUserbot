from .exceptions import handle_error_response
import urllib
import json
import requests
from loguru import logger

from ....settings import config
from .init_client import init_client
from ...registry import owners

client = init_client()

def set_account_data(data):
    logger.error(data)
    userid = urllib.parse.quote(config.matrix_config.owner)
    logger.error(userid)

    headers = {
        'Authorization': f'Bearer {config.matrix_config.access_token.get_secret_value()}',
    }
    logger.error(headers)
    ad_url = f"{client.homeserver}/_matrix/client/v3/user/{userid}/account_data/{config.matrix_config.appid}"
    logger.error(ad_url)
    response = requests.put(ad_url, json.dumps(data), headers=headers)
    logger.error(response)
    handle_error_response(response)

    if response.status_code != 200:
        logger.error('Setting account data failed. response: %s json: %s', response, response.json())

def get_account_data():
    userid = urllib.parse.quote(config.matrix_config.owner)
    headers = {
        'Authorization': f'Bearer {client.access_token}',
    }
    logger.debug(headers)

    logger.debug(client.homeserver)
    logger.debug(userid)
    ad_url = f"{client.homeserver}/_matrix/client/v3/user/{userid}/account_data/{config.matrix_config.appid}"
    logger.debug(ad_url)
    response = requests.get(ad_url, headers=headers)
    logger.debug(response)
    handle_error_response(response)

    if response.status_code == 200:
        return response.json()
    logger.error(f'Getting account data failed: {response} {response.json()} - this is normal if you have not saved any settings yet.')
    return None


# Returns true if event's sender is owner of the bot
def is_owner(event):
    return event.sender in owners