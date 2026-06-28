#!/usr/bin/env python3
"""Schemas Pydantic pour les Flatpaks."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FlatpakApp(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    source: Literal["flathub"] = "flathub"
    app: str = Field(..., min_length=1, pattern=r'^[a-zA-Z0-9._-]+$')
    description: str = ""

    @field_validator('app')
    @classmethod
    def validate_app_id(cls, v):
        if not v or v.isspace():
            raise ValueError("ID Flatpak vide")
        if len(v.split('.')) < 2:
            raise ValueError(f"ID Flatpak invalide : '{v}' (format attendu : com.exemple.App)")
        return v.strip()


class FlatpakList(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    flatpaks: list[FlatpakApp] = Field(..., min_length=1)

    @field_validator('flatpaks')
    @classmethod
    def validate_unique_apps(cls, v):
        ids = [app.app for app in v]
        dupes = [a for a in ids if ids.count(a) > 1]
        if dupes:
            raise ValueError(f"IDs en double : {', '.join(set(dupes))}")
        return v
