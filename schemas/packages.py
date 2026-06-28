#!/usr/bin/env python3
"""Schemas Pydantic pour les paquets RPM/DNF."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Package(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    name: str = Field(..., min_length=1)
    description: str = ""

    @field_validator('name')
    @classmethod
    def validate_name(cls, v):
        if not v or v.isspace():
            raise ValueError("Nom de paquet vide")
        return v.strip()


class PackageList(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    packages: list[Package] = Field(..., min_length=1)

    @field_validator('packages')
    @classmethod
    def validate_unique_names(cls, v):
        names = [pkg.name for pkg in v]
        dupes = [n for n in names if names.count(n) > 1]
        if dupes:
            raise ValueError(f"Noms en double : {', '.join(set(dupes))}")
        return v
