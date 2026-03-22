


class UploadFailed(Exception):
    pass

class CommandRequiresAdmin(Exception):
    pass


class CommandRequiresOwner(Exception):
    pass


import sys
from loguru import logger


class MatrixBotError(Exception): pass
class AuthenticationError(MatrixBotError): pass
class NetworkError(MatrixBotError): pass


def handle_error_response(response):
    if response.status_code == 401:
        logger.error("Access token is invalid or missing!")
        logger.info("Check your MATRIX_ACCESS_TOKEN.")
        # Вместо sys.exit(2) лучше выбросить исключение, 
        # чтобы бот мог "красиво" завершиться или переподключиться
        raise AuthenticationError("Invalid token")
        
    elif response.status_code >= 500:
        logger.warning(f"Server error: {response.status_code}")
        raise NetworkError(f"Server side issue: {response.status_code}")