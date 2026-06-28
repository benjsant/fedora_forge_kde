#!/usr/bin/env python3
"""Schemas Pydantic pour les paquets externes."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExternalPackage(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    name: str = Field(..., min_length=1)
    description: str = ""
    cmd: str = Field(..., min_length=1)

    @field_validator('cmd')
    @classmethod
    def validate_command(cls, v):
        if not v or v.isspace():
            raise ValueError("Commande d'installation vide")
        return v.strip()


class ExternalPackageList(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    packages: list[ExternalPackage] = Field(..., min_length=1)
