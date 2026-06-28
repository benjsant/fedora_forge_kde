#!/usr/bin/env python3
"""Schemas Pydantic pour les themes GTK/Plasma/icones/curseurs."""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Theme(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    name: str = Field(..., min_length=1)
    name_to_use: str = Field(..., min_length=1)
    url: str = ""
    cmd_user: str = ""
    cmd_root: str = ""
    description: str = ""

    @field_validator('url')
    @classmethod
    def validate_url(cls, v):
        if v and not v.isspace() and not v.startswith(('http://', 'https://', 'git://')):
            raise ValueError(f"URL invalide : '{v}' (http/https/git attendu)")
        return v.strip() if v else ""

    @model_validator(mode='after')
    def validate_installation(self):
        if self.url and not (self.cmd_user or self.cmd_root):
            raise ValueError(
                f"Theme '{self.name}' a une URL mais pas de commande d'installation"
            )
        return self


class ThemeList(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')

    themes: list[Theme] = Field(..., min_length=1)

    @field_validator('themes')
    @classmethod
    def validate_unique_themes(cls, v):
        names = [t.name for t in v]
        dupes = [n for n in names if names.count(n) > 1]
        if dupes:
            raise ValueError(f"Noms de themes en double : {', '.join(set(dupes))}")
        return v
