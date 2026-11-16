from kernel_client import files
from kernel_protocol.configuration.errors import ConfigurationError
from kernel_protocol.configuration.model import Configuration
from kernel_protocol.configuration.syntax import MAX_DOCUMENT_BYTES
from kernel_protocol.configuration.validation import Limits, load
from kernel_protocol.errors.codes import NOT_FOUND, KernelError, error_name
from kernel_protocol.services.files import OPEN_READ

CONFIGURATION_PATH = b"boot/system/config"
PROCESS_LIMIT = 16
MISSING_DOCUMENT = "missing-document"
UNREADABLE = "unreadable"


def read_document(namespace: files.Namespace) -> str:
    try:
        document = namespace.open(CONFIGURATION_PATH, OPEN_READ)
    except KernelError as error:
        if error.code == NOT_FOUND:
            raise ConfigurationError(MISSING_DOCUMENT, str(CONFIGURATION_PATH, "utf-8")) from None
        raise ConfigurationError(UNREADABLE, error_name(error.code)) from None
    try:
        content = document.read(0, MAX_DOCUMENT_BYTES + 1)
        document.close()
    except KernelError as error:
        raise ConfigurationError(UNREADABLE, error_name(error.code)) from None
    return str(content, "utf-8")


def read_configuration(namespace: files.Namespace) -> Configuration:
    return load(read_document(namespace), Limits(PROCESS_LIMIT))
