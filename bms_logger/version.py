from __future__ import annotations

from datetime import datetime

APP_NAME = "ESS-AIO"
APP_TITLE = "ESS-AIO | Energy Storage System All-in-One Platform"
APP_VERSION = "3.11.0"
APP_STAGE = "Communication Analyzer Pro"
BUILD_DATE = "2026-05-03"
BUILD_ID = "v3.11.0-communication-analyzer-pro"
PROFILE_SCHEMA_VERSION = 3


def version_dict() -> dict[str, str | int]:
    return {
        "name": APP_NAME,
        "title": APP_TITLE,
        "version": APP_VERSION,
        "stage": APP_STAGE,
        "build_date": BUILD_DATE,
        "build_id": BUILD_ID,
        "profile_schema_version": PROFILE_SCHEMA_VERSION,
    }


def version_text() -> str:
    return (
        f"{APP_NAME} v{APP_VERSION}\n"
        f"{APP_STAGE}\n"
        f"Build: {BUILD_ID}\n"
        f"Date: {BUILD_DATE}\n"
        f"Profile schema: {PROFILE_SCHEMA_VERSION}"
    )
