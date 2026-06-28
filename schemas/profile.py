#!/usr/bin/env python3
"""
FedoraForgeKDE - Profile Schemas
------------------------------
Pydantic models for combined installation profiles (configs/profiles/*.json).
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProfileAptPackage(BaseModel):
    """DNF/RPM package entry within a profile."""

    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    name: str = Field(..., min_length=1, description="Package name")
    description: str = Field(default="", description="Package description")


class ProfileFlatpak(BaseModel):
    """Flatpak entry within a profile."""

    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    app: str = Field(
        ...,
        min_length=1,
        pattern=r'^[a-zA-Z0-9._-]+$',
        description="Flatpak app ID (e.g., com.example.App)"
    )
    description: str = Field(default="", description="App description")

    @field_validator('app')
    @classmethod
    def validate_app_id(cls, v: str) -> str:
        parts = v.split('.')
        if len(parts) < 2:
            raise ValueError(
                f"Invalid Flatpak app ID: '{v}'. "
                "Should be in format: com.example.App"
            )
        return v.strip()


class ProfileExternal(BaseModel):
    """External package entry within a profile."""

    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    name: str = Field(..., min_length=1, description="Package name")
    description: str = Field(default="", description="Package description")
    cmd: str = Field(..., min_length=1, description="Installation command")


class ProfileRemove(BaseModel):
    """Package to remove within a profile."""

    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    name: str = Field(..., min_length=1, description="Package name or glob pattern")
    description: str = Field(default="", description="Package description")


VALID_ICONS = (
    "box", "wrench", "gamepad", "cpu", "gpu", "code", "film", "shield", "server",
    "docker", "office"
)


class Profile(BaseModel):
    """Combined installation profile (DNF + Flatpak + External + Remove)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    name: str = Field(..., min_length=1, description="Profile display name")
    description: str = Field(default="", description="Profile description")
    icon: str = Field(default="box", description="Icon identifier for the UI")
    apt: list[ProfileAptPackage] = Field(default_factory=list)
    flatpak: list[ProfileFlatpak] = Field(default_factory=list)
    external: list[ProfileExternal] = Field(default_factory=list)
    remove: list[ProfileRemove] = Field(default_factory=list)

    @field_validator('icon')
    @classmethod
    def validate_icon(cls, v: str) -> str:
        if v not in VALID_ICONS:
            raise ValueError(
                f"Unknown icon '{v}'. Valid icons: {', '.join(VALID_ICONS)}"
            )
        return v

    @property
    def total_packages(self) -> int:
        return len(self.apt) + len(self.flatpak) + len(self.external)
