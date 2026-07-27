"""Run the API with ``python -m astrocyte.api``."""

import uvicorn


def main() -> None:
    uvicorn.run(
        "astrocyte.api.app:create_app",
        factory=True,
        host="0.0.0.0",  # noqa: S104 - bind all interfaces inside the container
        port=8000,
    )


if __name__ == "__main__":
    main()
