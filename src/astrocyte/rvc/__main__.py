"""Console entry point: ``astro-rvc-bridge`` / ``python -m astrocyte.rvc``."""

import argparse
import asyncio
import contextlib
import logging

from astrocyte.rvc.bridge import BridgeSettings, RvcBridge


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="astro-rvc-bridge",
        description=(
            "RV-C SocketCAN <-> MQTT bridge (configured via ASTROCYTE_ env vars)."
        ),
    )
    parser.add_argument(
        "--reset-discovery",
        action="store_true",
        help=(
            "Clear this coach's retained HA discovery, then exit. Run it once "
            "after renaming fixtures or zones in the instance map: HA keeps the "
            "entity_id it assigned at first registration, so entities must be "
            "retired before the next start can re-register them under their "
            "current names."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - daemon shell
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = BridgeSettings()
    bridge = RvcBridge(settings)
    log = logging.getLogger(__name__)

    if args.reset_discovery:
        log.info("clearing retained discovery on %s", settings.mqtt_url)
        asyncio.run(bridge.reset_discovery())
        return 0

    log.info(
        "starting RV-C bridge on %s (listen_only=%s)",
        settings.can_channel,
        settings.listen_only,
    )
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(bridge.run())
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
