# Copyright 2026 Capstone MCP contributors.
"""COM-owning command loop loaded by the assigned worker bootstrap."""

import logging
import sys
from typing import Final

from capstone_mcp.automation_models import NativeReply, RequestPacket
from capstone_mcp.automation_worker import MAX_MESSAGE_BYTES
from capstone_mcp.graph_execution import GraphOperationError
from capstone_mcp.native_dispatch import NativeDesktop

LOGGER: Final = logging.getLogger(__name__)


def main() -> None:
    """Execute each request on the one thread owning this runtime's COM wrappers."""
    runtime = NativeDesktop()
    line = sys.stdin.readline(MAX_MESSAGE_BYTES + 1)
    while line:
        packet = RequestPacket.model_validate_json(line)
        try:
            result = runtime.dispatch(packet.command)
        except GraphOperationError as error:
            LOGGER.exception("Native graph operation failed")
            reply = NativeReply(
                identifier=packet.identifier, error=str(error),
                graph_failure=error.failure.model_copy(update={
                    "request_id": packet.identifier,
                }),
            )
        except Exception as error:
            LOGGER.exception("Native Capstone operation failed")
            reply = NativeReply(
                identifier=packet.identifier,
                error=f"{type(error).__name__}: {error}",
            )
        else:
            reply = NativeReply(identifier=packet.identifier, result=result)
        _ = sys.stdout.write(reply.model_dump_json() + "\n")
        _ = sys.stdout.flush()
        line = sys.stdin.readline(MAX_MESSAGE_BYTES + 1)


if __name__ == "__main__":
    main()
